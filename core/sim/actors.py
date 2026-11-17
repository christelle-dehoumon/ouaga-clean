"""Simulation pas à pas des quatre acteurs — membre C.

Les règles sont volontairement courtes (2 à 3 par acteur) et tous les nombres
viennent de ``config/commune_config.json`` ou des hypothèses déclarées dans
``core/sim/hypotheses.py``. ``actors_enabled`` permet de retirer un acteur : le
jury voit alors immédiatement lequel des trois chiffres de sortie change.

La sortie contient :
* ``series`` — un point par jour ;
* ``agent_states`` — l'état des quatre acteurs jour par jour ;
* ``events`` — le journal décisionnel ;
* les trois chiffres historiques (``part_ramassee``, ``cout_m_fcfa``,
  ``depotoirs_restants``) pour ne pas casser les appelants existants.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .hypotheses import charger_configuration, hypotheses, valeur
from .model import Agent, Model, MOTEUR, RACINE

NOMS_ACTEURS = ("menages", "pre_collecteurs", "brigade", "mairie")
ACTIFS_PAR_DEFAUT = {nom: True for nom in NOMS_ACTEURS}


def _nombre(valeur_brute: Any, defaut: float) -> float:
    try:
        resultat = float(valeur_brute)
        return resultat if math.isfinite(resultat) else float(defaut)
    except (TypeError, ValueError):
        return float(defaut)


def _entier(valeur_brute: Any, defaut: int, minimum: int = 0, maximum: int = 500) -> int:
    try:
        resultat = int(valeur_brute)
    except (TypeError, ValueError):
        resultat = int(defaut)
    return max(minimum, min(maximum, resultat))


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance approximative en mètres, sans dépendance externe."""
    rayon_terre_m = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * rayon_terre_m * math.asin(min(1.0, math.sqrt(a)))


def _charger_plan(params: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Plan fourni par l'appelant, sinon plan de démonstration du répertoire mock."""
    plan = params.get("plan")
    if isinstance(plan, dict) and isinstance(plan.get("collection_points"), list):
        return plan, "plan fourni dans params"
    chemins = config.get("paths") if isinstance(config.get("paths"), dict) else {}
    dossier = Path(chemins.get("mock_dir", "data/mock"))
    if not dossier.is_absolute():
        dossier = RACINE / dossier
    for nom in ("plan_real.json", "plan_exemple.json"):
        try:
            donnees = json.loads((dossier / nom).read_text(encoding="utf-8"))
            if isinstance(donnees, dict) and isinstance(donnees.get("collection_points"), list):
                return donnees, "plan de démonstration " + nom
        except Exception:
            continue
    return {"collection_points": [], "routes": []}, "aucun plan disponible"


def _centre_bbox(config: dict[str, Any]) -> tuple[float, float]:
    """Centre de l'emprise de la configuration — aucune coordonnée en dur."""
    bbox = config.get("bbox") if isinstance(config.get("bbox"), dict) else {}
    try:
        return ((_nombre(bbox["south"], 0) + _nombre(bbox["north"], 0)) / 2,
                (_nombre(bbox["west"], 0) + _nombre(bbox["east"], 0)) / 2)
    except KeyError:
        return (0.0, 0.0)


class Foyer(Agent):
    """Ménage synthétique : abonné ou non, avec ou sans dépôt sauvage."""

    def __init__(self, uid: int, model: "SimulationActeurs", centre: dict[str, Any],
                 abonne: bool, distance: float, kg_jour: float):
        super().__init__(model)
        self.uid = uid
        self.centre = centre
        self.abonne = abonne
        self.distance_m = distance
        self.kg_jour = kg_jour
        self.depot = False

    def step(self) -> None:
        modele = self.model
        if not modele.actifs["menages"]:
            self.depot = False  # acteur retiré : aucun déchet généré
            return
        index = self.uid % max(1, len(modele.centres))
        plein = modele.remplissage[index] >= 1.0
        rayon = _nombre(valeur(modele.hyp, "precollect_radius_m", 0), 0)
        if self.abonne and self.distance_m <= rayon and not plein:
            # Règle 1 : l'abonné dépose au point de regroupement.
            modele.remplissage[index] = min(1.0, modele.remplissage[index] + self.kg_jour / max(1.0, modele.capacite_centre))
            self.depot = False
            return
        # Règle 2 (brigade) : sensibilisation des ménages dans son rayon.
        # C'est cette règle qui rend l'effet de la brigade mesurable même quand
        # sa patrouille curative ne trouve aucun dépôt à traiter ce jour-là.
        rayon_brigade = _nombre(valeur(modele.hyp, "brigade_radius_m", 0), 0)
        if modele.actifs["brigade"] and self.distance_m <= rayon_brigade:
            self.depot = False
            return
        # Règle 3 : dépôt sauvage si non desservi, ou si le centre est plein.
        proba = _nombre(valeur(modele.hyp, "menage_dump_rate_served", 0), 0)
        if not self.abonne or plein or self.distance_m > rayon:
            proba = _nombre(valeur(modele.hyp, "menage_dump_rate_unserved", 0), 0)
        self.depot = modele.random.random() < proba
        if self.depot:
            modele.ajouter_evenement("menages", "Ménage {uid} a jeté dans la rue : point de regroupement à {dist:.0f} m".format(
                uid=self.uid, dist=self.distance_m))


class PreCollecteur(Agent):
    """Tricycle : ramasse les dépôts, remplit le centre de regroupement."""

    def __init__(self, uid: int, model: "SimulationActeurs"):
        super().__init__(model)
        self.uid = uid
        self.en_service = True
        self.kg_ramasses = 0.0

    def step(self) -> None:
        modele = self.model
        self.kg_ramasses = 0.0
        if not modele.actifs["pre_collecteurs"]:
            self.en_service = False
            return
        panne = _nombre(valeur(modele.hyp, "precollect_breakdown_rate", 0), 0)
        if modele.pluie:
            panne *= modele.rain_factor
        self.en_service = modele.random.random() >= min(1.0, panne)
        if not self.en_service:
            return
        probabilite = _nombre(valeur(modele.hyp, "precollect_pass_rate", 0), 0)
        capacite = _nombre(valeur(modele.hyp, "tricycle_capacity_kg", 0), 0)
        index = self.uid % max(1, len(modele.centres))
        for foyer in modele.foyers:
            if not foyer.depot or foyer.uid % max(1, modele.nb_pre) != self.uid:
                continue
            if modele.random.random() >= probabilite:
                continue
            prise = min(foyer.kg_jour, max(0.0, capacite - self.kg_ramasses))
            if prise <= 0:
                break
            foyer.depot = False
            self.kg_ramasses += prise
            modele.remplissage[index] = min(1.0, modele.remplissage[index] + prise / max(1.0, modele.capacite_centre))
        if self.kg_ramasses > 0:
            modele.ajouter_evenement("pre_collecteurs", "Pré-collecteur {uid} a ramassé {kg:.1f} kg vers le centre {centre}".format(
                uid=self.uid, kg=self.kg_ramasses, centre=modele.centres[index].get("id", "?")))


class Brigade(Agent):
    """Brigade Laabal : patrouille et évite les dépôts à proximité."""

    def __init__(self, uid: int, model: "SimulationActeurs"):
        super().__init__(model)
        self.uid = uid
        self.patrouilles = 0
        self.depots_evites = 0

    def step(self) -> None:
        modele = self.model
        self.patrouilles = 0
        self.depots_evites = 0
        if not modele.actifs["brigade"]:
            return
        rayon = _nombre(valeur(modele.hyp, "brigade_radius_m", 0), 0)
        reussite = _nombre(valeur(modele.hyp, "brigade_success_rate", 0), 0)
        self.patrouilles = _entier(valeur(modele.hyp, "brigade_patrols_per_day", 0), 0)
        cibles = [f for f in modele.foyers if f.depot and f.distance_m <= rayon]
        # Règle déterministe : la patrouille traite au moins un dépôt lorsqu'il
        # y en a dans son rayon, puis une part croissante avec le taux de
        # réussite (hypothèse à valider). Cela rend l'effet de l'acteur mesurable.
        if cibles:
            a_traiter = min(len(cibles), max(1, round(len(cibles) * reussite)))
            for foyer in cibles[:a_traiter]:
                foyer.depot = False
                self.depots_evites += 1
        if self.depots_evites:
            modele.ajouter_evenement("brigade", "Brigade {uid} : {n} dépôt(s) évité(s) dans un rayon de {r:.0f} m".format(
                uid=self.uid, n=self.depots_evites, r=rayon))


class Mairie(Agent):
    """Mairie : camions, coût de collecte et budget restant."""

    def __init__(self, uid: int, model: "SimulationActeurs"):
        super().__init__(model)
        self.uid = uid
        self.camions_en_service = 0
        self.camions_total = 0
        self.cout_jour = 0.0

    def step(self) -> None:
        modele = self.model
        self.cout_jour = 0.0
        self.camions_total = modele.trucks
        if not modele.actifs["mairie"]:
            self.camions_en_service = 0
            return
        self.camions_en_service = max(0, modele.trucks - len(modele.broken_trucks))
        capacite = _nombre(valeur(modele.hyp, "truck_capacity_kg", 0), 0)
        trips = _entier(valeur(modele.hyp, "truck_trips_per_day", 0), 0)
        # Règle 1 : chaque camion disponible vide les centres et enlève des dépôts.
        for index in range(len(modele.centres)):
            if index >= self.camions_en_service * max(1, trips):
                break
            modele.remplissage[index] = 0.0
        for foyer in modele.foyers:
            if foyer.depot and foyer.uid % max(1, self.camions_en_service) == 0:
                foyer.depot = False
        # Règle 2 : le coût vient des distances du plan et des coûts de la config.
        cout_truck = _nombre(valeur(modele.hyp, "cost_per_km_truck", 0), 0)
        cout_tri = _nombre(valeur(modele.hyp, "cost_per_km_tricycle", 0), 0)
        distance_truck = sum(r.get("distance_km", 0) for r in modele.routes if r.get("type") == "truck")
        distance_tri = sum(r.get("distance_km", 0) for r in modele.routes if r.get("type") == "tricycle")
        part_flotte = self.camions_en_service / max(1, self.camions_total)
        self.cout_jour = distance_truck * cout_truck * part_flotte
        if modele.actifs["pre_collecteurs"]:
            self.cout_jour += distance_tri * cout_tri
        modele.budget_restant = max(0.0, modele.budget - modele.cout_cumule - self.cout_jour)
        if self.camions_en_service < self.camions_total:
            modele.ajouter_evenement("mairie", "Camion en panne : {n} tournée(s) reportée(s)".format(
                n=len(modele.broken_trucks) * trips))


class SimulationActeurs(Model):
    """Orchestrateur : utilise Mesa si disponible, sinon le shim local du module model."""

    def __init__(self, params: dict[str, Any], config: dict[str, Any], plan: dict[str, Any],
                 source_plan: str, hyp: dict[str, dict[str, Any]],
                 actors_enabled: dict[str, bool], seed: int):
        super().__init__(seed=seed)
        self.params = params
        self.config = config
        self.plan = plan
        self.source_plan = source_plan
        self.hyp = hyp
        self.actifs = {nom: bool(actors_enabled.get(nom, True)) for nom in NOMS_ACTEURS}
        self.random = __import__("random").Random(seed)
        self.graine = seed

        self.centres = [p for p in plan.get("collection_points", []) if isinstance(p, dict)
                        and p.get("type", "center") == "center"] or [
            p for p in plan.get("collection_points", []) if isinstance(p, dict)]
        self.depotoirs = [p for p in plan.get("collection_points", []) if isinstance(p, dict)
                          and p.get("type") == "dumpsite"]
        self.routes = [r for r in plan.get("routes", []) if isinstance(r, dict)]
        self.pluie = bool(params.get("rainy_season", config.get("params", {}).get("rainy_season", False)))
        self.trucks = _entier(params.get("trucks", config.get("params", {}).get("trucks", 0)), 0)
        self.tricycles = _entier(params.get("tricycles", config.get("params", {}).get("tricycles", 0)), 0)
        self.broken_trucks = list(params.get("broken_trucks") or config.get("params", {}).get("broken_trucks") or [])
        self.budget = _nombre(params.get("budget", config.get("params", {}).get("budget", 0)), 0)
        self.budget_restant = self.budget
        self.cout_cumule = 0.0
        self.capacite_centre = max(1.0, sum(p.get("demand_kg", 0) for p in self.centres) / max(1, len(self.centres)))

        # Les agents foyers sont un proxy : un foyer synthétique par centre du plan.
        lat0, lon0 = _centre_bbox(config)
        population = _nombre(params.get("population", config.get("params", {}).get("population", 0)), 0)
        abonnement = _nombre(params.get("subscription_rate", config.get("params", {}).get("subscription_rate", 0)), 0)
        if "taux_abonnement_pct" in params:
            abonnement = _nombre(params["taux_abonnement_pct"], 0) / 100.0
        kg_hab = _nombre(valeur(hyp, "waste_kg_per_person_day", 0), 0)
        self.foyers: list[Foyer] = []
        rayon_pre = max(1.0, _nombre(valeur(hyp, "precollect_radius_m", 1500), 1500))
        for i, centre in enumerate(self.centres):
            lat = _nombre(centre.get("lat"), lat0)
            lon = _nombre(centre.get("lon"), lon0)
            # Aucun bâtiment n'est fourni dans data/mock : la distance au point
            # de regroupement est synthétique, bornée par le rayon de la config.
            # Elle est étiquetée « à valider » dans hypotheses().
            distance = self.random.uniform(0.0, 2.0 * rayon_pre)
            self.foyers.append(Foyer(i + 1, self, centre, self.random.random() < abonnement, distance,
                                     population * abonnement * kg_hab / max(1, len(self.centres))))

        self.nb_pre = max(1, min(self.tricycles, len(self.centres)))
        self.pre_collecteurs = [PreCollecteur(i, self) for i in range(self.nb_pre)]
        self.brigade = [Brigade(i, self) for i in range(max(1, _entier(valeur(hyp, "brigade_patrols_per_day", 1), 1)))]
        self.mairie = Mairie(0, self)
        self.remplissage = [0.0 for _ in self.centres]
        self.evenements: list[dict[str, Any]] = []
        self.series: list[dict[str, Any]] = []
        self.agent_states: list[dict[str, Any]] = []
        self.max_evenements = _entier(valeur(hyp, "max_events_per_day", 0), 1, minimum=1)

    def ajouter_evenement(self, acteur: str, texte: str) -> None:
        if sum(1 for e in self.evenements if e["jour"] == self.jour) < self.max_evenements:
            self.evenements.append({"jour": self.jour, "acteur": acteur, "texte": texte, "data_tag": "simulated"})

    def _etat(self) -> dict[str, Any]:
        return {
            "menages": {
                "abonnes": sum(1 for f in self.foyers if f.abonne),
                "total": len(self.foyers),
                "avec_depot": sum(1 for f in self.foyers if f.depot),
                "positions": [{"id": "menage_{}".format(f.uid), "lat": _nombre(f.centre.get("lat"), 0),
                               "lon": _nombre(f.centre.get("lon"), 0), "propre": not f.depot}
                              for f in self.foyers],
            },
            "pre_collecteurs": {
                "en_service": sum(1 for p in self.pre_collecteurs if p.en_service),
                "total": len(self.pre_collecteurs),
                "kg_ramasses": round(sum(p.kg_ramasses for p in self.pre_collecteurs), 2),
                "remplissage_moyen": round(sum(self.remplissage) / max(1, len(self.remplissage)), 3),
            },
            "brigade": {
                "patrouilles_actives": sum(b.patrouilles for b in self.brigade),
                "depots_evites": sum(b.depots_evites for b in self.brigade),
                "rayon_m": _nombre(valeur(self.hyp, "brigade_radius_m", 0), 0),
            },
            "mairie": {
                "camions_en_service": self.mairie.camions_en_service,
                "camions_total": self.mairie.camions_total,
                "budget_restant": round(self.budget_restant, 2),
                "remplissage_centres": [round(x, 3) for x in self.remplissage],
            },
        }

    def step(self, jour: int) -> None:
        self.jour = jour
        for foyer in self.foyers:
            foyer.step()
        for pre in self.pre_collecteurs:
            pre.step()
        for brigadier in self.brigade:
            brigadier.step()
        self.mairie.step()
        self.cout_cumule += self.mairie.cout_jour

        depots = sum(1 for f in self.foyers if f.depot) + sum(1 for d in self.depotoirs if self.actifs["mairie"] is False or not self.mairie.camions_en_service)
        part = round(1.0 - depots / max(1, len(self.foyers) + len(self.depotoirs)), 3)
        self.series.append({
            "jour": jour,
            "part_ramassee": part,
            "cout_m_fcfa": round(self.cout_cumule / 1_000_000, 3),
            "depotoirs_restants": depots,
            "budget_restant_m_fcfa": round(self.budget_restant / 1_000_000, 3),
            "kg_ramasses": round(sum(p.kg_ramasses for p in self.pre_collecteurs), 2),
            "data_tag": "simulated",
        })
        etat = self._etat()
        etat["jour"] = jour
        self.agent_states.append(etat)


def executer(params: dict[str, Any], days: int, actors_enabled: dict[str, bool] | None,
             seed: int) -> dict[str, Any]:
    """Construit le scénario complet et renvoie séries + états + journal."""
    config = charger_configuration()
    hyp = hypotheses(config)
    plan, source_plan = _charger_plan(params, config)
    actifs = {nom: bool((actors_enabled or ACTIFS_PAR_DEFAUT).get(nom, True)) for nom in NOMS_ACTEURS}
    modele = SimulationActeurs(params, config, plan, source_plan, hyp, actifs, seed)
    for jour in range(1, max(1, _entier(days, 7, minimum=1, maximum=365)) + 1):
        modele.step(jour)

    dernier = modele.series[-1]
    etat = modele.agent_states[-1]
    abonnes = etat["menages"]["abonnes"]
    return {
        "fonction": "run_scenario",
        "data_tag": "simulated",
        "moteur": MOTEUR,
        "graine": seed,
        "days": len(modele.series),
        "params_used": params,
        "actors_enabled": actifs,
        "source_plan": source_plan,
        "part_ramassee": dernier["part_ramassee"],
        "cout_m_fcfa": dernier["cout_m_fcfa"],
        "depotoirs_restants": dernier["depotoirs_restants"],
        "unite_depotoirs_restants": "foyers synthétiques et dépotoirs du plan (proxy)",
        "menages_synthetiques": len(modele.foyers),
        "series": modele.series,
        "agent_states": modele.agent_states,
        "events": modele.evenements,
        "indicateurs": {
            "menages": {
                "abonnes_pct": round(100 * abonnes / max(1, len(modele.foyers)), 1),
                "depotoirs_crees": etat["menages"]["avec_depot"],
            },
            "pre_collecteurs": {
                "tonnes_ramassees": round(etat["pre_collecteurs"]["kg_ramasses"] / 1000, 3),
                "remplissage_moyen": etat["pre_collecteurs"]["remplissage_moyen"],
            },
            "brigade": {
                "patrouilles_actives": etat["brigade"]["patrouilles_actives"],
                "depots_evites": etat["brigade"]["depots_evites"],
            },
            "mairie": {
                "budget_restant_m_fcfa": round(modele.budget_restant / 1_000_000, 3),
                "camions_en_service": etat["mairie"]["camions_en_service"],
                "camions_total": etat["mairie"]["camions_total"],
            },
        },
        "hypotheses": [dict(v, cle=k) for k, v in hyp.items()],
        "agents": [
            {"nom": "Ménages", "cle": "menages"},
            {"nom": "Pré-collecteurs", "cle": "pre_collecteurs"},
            {"nom": "Brigade Laabal", "cle": "brigade"},
            {"nom": "Mairie", "cle": "mairie"},
        ],
    }
