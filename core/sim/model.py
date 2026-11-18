"""Simulation multi-agents (Mesa) : ménages, pré-collecteurs, brigade Laabal, mairie.

Le plan de collecte entre, trois chiffres sortent : part des déchets ramassée, coût, dépotoirs restants.
Chaque acteur suit deux ou trois règles écrites ci-dessous ; tous les coefficients viennent de la section
« hypotheses » de la configuration de la commune (aucun n'est mesuré, ils sont recopiés dans la sortie).

La simulation ne lit jamais la base réelle : elle reçoit le plan et, au besoin, les dépotoirs simulés (sim.db).
Tout ce qu'elle produit est étiqueté « simulated ».

Règles :
- Ménage : (1) produit chaque jour personnes × kg/personne/jour ; (2) abonné desservi : attend le pré-collecteur,
  mais vide sa poubelle dans la rue si elle déborde ; (3) abonné non desservi ou non abonné : dépôt sauvage avec une
  probabilité donnée, divisée par l'effet de la sensibilisation.
- Pré-collecteur (tricycle) : (1) peut tomber en panne ; (2) passe avec une probabilité (réduite par la pluie) ;
  (3) vide les poubelles des abonnés desservis jusqu'à sa capacité et dépose au point de regroupement.
- Brigade Laabal : (1) visite les plus gros dépotoirs et les signale à la mairie ; (2) sensibilise les ménages
  dans un rayon autour du dépotoir visité.
- Mairie : (1) les jours de collecte (fréquence), envoie les camions en service (panne, pluie) dans la limite du
  budget ; (2) vide les points de regroupement desservis par le plan ; (3) avec la capacité restante, nettoie les
  dépotoirs signalés.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

import mesa

from core.config import clamp_params, get_config, hypothesis, section

MOTEUR = f"mesa {mesa.__version__}"
ACTEURS = ("menages", "pre_collecteurs", "brigade", "mairie")
NOMS_ACTEURS = {"menages": "Ménages", "pre_collecteurs": "Pré-collecteurs", "brigade": "Brigade Laabal",
                "mairie": "Mairie"}
METRES_PAR_DEGRE = 111_320.0


def _num(value: Any, default: float = 0.0) -> float:
    """Nombre fini, sinon default."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return default
    return float(value)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance approchée en mètres (projection locale)."""
    dy = (lat2 - lat1) * METRES_PAR_DEGRE
    dx = (lon2 - lon1) * METRES_PAR_DEGRE * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


class Menage(mesa.Agent):
    """Un agent = `echelle` ménages réels rattachés au même point de regroupement."""

    def __init__(self, model: "ModeleOuaga", point: dict[str, Any], abonne: bool, lat: float, lon: float):
        super().__init__(model)
        self.point, self.abonne, self.lat, self.lon = point, abonne, lat, lon
        self.stock_kg = 0.0
        self.sensibilise_jusqua = -1

    @property
    def desservi(self) -> bool:
        """Point de regroupement desservi par une tournée du plan."""
        return bool(self.point["desservi"])

    def step(self) -> None:
        m = self.model
        produit = m.kg_par_menage_jour * m.echelle
        self.stock_kg += produit
        m.jour_courant["produit_kg"] += produit
        effet = m.h("menages", "effet_sensibilisation") if self.sensibilise_jusqua >= m.jour else 1.0
        if self.abonne and self.desservi:
            plein = self.stock_kg > m.kg_par_menage_jour * m.echelle * m.h("menages", "jours_avant_debordement")
            proba = m.h("menages", "proba_depot_sauvage_sature") * effet if plein else 0.0
        elif self.abonne:
            proba = m.h("menages", "proba_depot_sauvage_non_desservi") * effet
        else:
            proba = m.h("menages", "proba_depot_sauvage_non_abonne") * effet
        if proba and self.random.random() < proba:
            m.deposer(self, self.stock_kg)
            self.stock_kg = 0.0


class PreCollecteur(mesa.Agent):
    """Tricycle de pré-collecte : ménages abonnés desservis -> point de regroupement."""

    def __init__(self, model: "ModeleOuaga"):
        super().__init__(model)
        self.en_panne = False
        self.ramasse_kg = 0.0

    def step(self) -> None:
        m = self.model
        self.en_panne = self.random.random() < m.h("pre_collecteurs", "proba_panne_jour")
        passage = m.h("pre_collecteurs", "proba_passage") * (m.h("pre_collecteurs", "facteur_pluie") if m.pluie else 1.0)
        if self.en_panne or self.random.random() >= passage:
            return
        capacite = m.capacite_tricycle_kg * m.h("pre_collecteurs", "tournees_par_jour")
        clients = [a for a in m.menages if a.abonne and a.desservi and a.stock_kg > 0]
        self.random.shuffle(clients)
        for menage in clients:
            if capacite <= 0:
                break
            pris = min(menage.stock_kg, capacite)
            menage.stock_kg -= pris
            capacite -= pris
            menage.point["stock_kg"] += pris
            self.ramasse_kg += pris
            m.jour_courant["precollecte_kg"] += pris


class Brigade(mesa.Agent):
    """Patrouille de la brigade Laabal : signale les dépotoirs et sensibilise autour."""

    def __init__(self, model: "ModeleOuaga"):
        super().__init__(model)
        self.patrouilles = 0
        self.sensibilises = 0

    def step(self) -> None:
        m = self.model
        actifs = sorted((d for d in m.depotoirs.values() if d["kg"] > 0 and not d["signale"]),
                        key=lambda d: (-d["kg"], d["id"]))
        rayon = m.h("brigade", "rayon_m")
        for depotoir in actifs[:int(m.h("brigade", "depotoirs_par_patrouille"))]:
            depotoir["signale"] = True
            self.patrouilles += 1
            for menage in m.menages:
                if _distance_m(menage.lat, menage.lon, depotoir["lat"], depotoir["lon"]) <= rayon and \
                        self.random.random() < m.h("brigade", "proba_sensibilisation"):
                    menage.sensibilise_jusqua = m.jour + int(m.h("menages", "duree_sensibilisation_jours"))
                    self.sensibilises += 1


class Mairie(mesa.Agent):
    """Camions de la mairie : points desservis les jours de collecte, puis dépotoirs signalés, dans le budget."""

    def __init__(self, model: "ModeleOuaga"):
        super().__init__(model)
        self.depense_fcfa = 0.0
        self.collecte_kg = 0.0
        self.nettoye_kg = 0.0
        self.jours_collecte = 0

    def step(self) -> None:
        m = self.model
        # Règle 1 : jour de collecte selon la fréquence, camions en service, budget du passage.
        if math.floor((m.jour + 1) * m.frequence / 7) == math.floor(m.jour * m.frequence / 7):
            return
        if m.camions_en_service <= 0 or m.capacite_jour_kg <= 0:
            return
        part_budget = min(1.0, m.budget_passage / m.cout_passage) if m.cout_passage > 0 else 1.0
        capacite = m.capacite_jour_kg * part_budget
        self.jours_collecte += 1
        self.depense_fcfa += m.cout_passage * part_budget
        m.jour_courant["cout_fcfa"] += m.cout_passage * part_budget
        # Règle 2 : vider les points desservis.
        for point in m.points:
            if not point["desservi"] or capacite <= 0:
                continue
            pris = min(point["stock_kg"], capacite)
            point["stock_kg"] -= pris
            capacite -= pris
            self.collecte_kg += pris
            m.jour_courant["collecte_kg"] += pris
        # Règle 3 : nettoyer les dépotoirs signalés avec une part de la capacité restante.
        reste = capacite * m.h("mairie", "part_capacite_nettoyage")
        for depotoir in sorted((d for d in m.depotoirs.values() if d["signale"] and d["kg"] > 0),
                               key=lambda d: (-d["kg"], d["id"])):
            if reste <= 0:
                break
            pris = min(depotoir["kg"], reste)
            depotoir["kg"] -= pris
            reste -= pris
            self.nettoye_kg += pris
            m.jour_courant["collecte_kg"] += pris
            if depotoir["kg"] <= 0:
                depotoir["signale"] = False


class ModeleOuaga(mesa.Model):
    """Modèle journalier ; activation dans l'ordre ménages, pré-collecteurs, brigade, mairie."""

    def __init__(self, plan: dict[str, Any], params: dict[str, Any], cfg: dict[str, Any], seed: int,
                 actifs: dict[str, bool], depotoirs_sim: list[dict[str, Any]]):
        super().__init__(rng=seed)
        self.cfg = cfg
        self.jour = 0
        self.actifs = actifs
        self.pluie = bool(params.get("rainy_season"))
        self.frequence = max(_num(params.get("frequency_per_week"), 1.0), 0.0)
        model_cfg = section(cfg, "model")
        self.kg_personne_jour = _num(model_cfg.get("waste_kg_per_person_day"))
        self.kg_par_menage_jour = self.kg_personne_jour * self.h("menages", "personnes_par_menage")
        self.capacite_tricycle_kg = _num(params.get("tricycle_capacity_kg"))
        trucks = int(_num(params.get("trucks")))
        broken = {t for t in params.get("broken_trucks") or [] if isinstance(t, str)}
        self.camions_en_service = len([i for i in range(1, trucks + 1) if f"truck{i}" not in broken])
        trips = max(int(_num(model_cfg.get("truck_trips_per_day"), 1.0)), 1)
        self.capacite_jour_kg = (self.camions_en_service * _num(params.get("truck_capacity_kg")) * trips
                                 * (self.h("mairie", "facteur_pluie_camions") if self.pluie else 1.0))
        totals = plan.get("totals") if isinstance(plan.get("totals"), dict) else {}
        self.cout_passage = _num(totals.get("cost"))
        self.budget_passage = max(_num(params.get("budget")), 0.0)
        self.points = self._points(plan)
        self.depotoirs: dict[str, dict[str, Any]] = {}
        for d in depotoirs_sim:
            if _num(d.get("lat"), None) is not None and _num(d.get("lon"), None) is not None:
                did = str(d.get("id") or f"sim_{len(self.depotoirs)}")
                self.depotoirs[did] = {"id": did, "lat": float(d["lat"]), "lon": float(d["lon"]),
                                       "kg": _num(d.get("kg"), self.h("mairie", "seuil_depotoir_kg") * 4),
                                       "signale": False, "source": "sim", "origine": "ajouté par la mairie"}
        self.menages: list[Menage] = []
        self.echelle = 1.0
        self.ignores: list[str] = []
        self._creer_menages(plan, params)
        self.tricycles = [PreCollecteur(self) for _ in range(int(_num(params.get("tricycles"))))] \
            if actifs["pre_collecteurs"] else []
        self.patrouilles = [Brigade(self) for _ in range(int(self.h("brigade", "patrouilles_par_jour")))] \
            if actifs["brigade"] else []
        self.mairie = Mairie(self) if actifs["mairie"] else None
        self.jour_courant: dict[str, float] = {}
        self.series: list[dict[str, Any]] = []

    def h(self, groupe: str, cle: str) -> float:
        """Coefficient d'hypothèse lu dans la configuration."""
        return hypothesis(self.cfg, groupe, cle)

    @staticmethod
    def _points(plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Points de regroupement du plan (parties découpées regroupées) et leur desserte."""
        servis = {s for r in plan.get("routes") or [] if isinstance(r, dict) for s in r.get("stops") or []}
        groupes: dict[str, dict[str, Any]] = {}
        for p in plan.get("collection_points") or []:
            if not isinstance(p, dict) or p.get("type") != "center":
                continue
            pid = str(p.get("split_of") or p.get("id"))
            g = groupes.setdefault(pid, {"id": pid, "lat": _num(p.get("lat")), "lon": _num(p.get("lon")),
                                         "demand_kg": 0.0, "parts": 0, "servies": 0, "stock_kg": 0.0})
            g["demand_kg"] += _num(p.get("demand_kg"))
            g["parts"] += 1
            g["servies"] += int(p.get("id") in servis)
        for g in groupes.values():
            g["desservi"] = g["servies"] == g["parts"]
        return sorted(groupes.values(), key=lambda g: g["id"])

    def _creer_menages(self, plan: dict[str, Any], params: dict[str, Any]) -> None:
        """Ménages abonnés et non abonnés répartis sur les points selon leur demande (proportions du plan)."""
        if not self.points or self.kg_par_menage_jour <= 0 or not self.actifs["menages"]:
            return
        # La demande du plan est calculée par passage, à la fréquence du plan (pas celle simulée).
        freq_plan = _num((plan.get("params_used") or {}).get("frequency_per_week"), self.frequence) or self.frequence
        jours = 7 / freq_plan if freq_plan > 0 else 7
        abonnes_kg = sum(p["demand_kg"] for p in self.points)
        totals = plan.get("totals") if isinstance(plan.get("totals"), dict) else {}
        non_abonnes_kg = _num(totals.get("uncollected_kg"))
        reels_ab = abonnes_kg / (self.kg_par_menage_jour * jours)
        reels_non = non_abonnes_kg / (self.kg_par_menage_jour * jours)
        total = reels_ab + reels_non
        if total <= 0:
            return
        max_agents = self.h("simulation", "max_agents_menages")
        n = int(min(max_agents, max(1, round(total))))
        self.echelle = total / n
        n_ab = int(round(n * reels_ab / total))
        poids = [p["demand_kg"] for p in self.points]
        disp = self.h("simulation", "dispersion_menages_m") / METRES_PAR_DEGRE
        for i in range(n):
            point = self.random.choices(self.points, weights=poids)[0]
            lat = point["lat"] + self.random.gauss(0, disp)
            lon = point["lon"] + self.random.gauss(0, disp / max(math.cos(math.radians(point["lat"])), 0.1))
            self.menages.append(Menage(self, point, i < n_ab, lat, lon))

    def deposer(self, menage: Menage, kg: float) -> None:
        """Dépôt sauvage simulé : un dépotoir par point de regroupement voisin."""
        did = f"sim_{menage.point['id']}"
        d = self.depotoirs.setdefault(did, {"id": did, "lat": menage.point["lat"], "lon": menage.point["lon"],
                                            "kg": 0.0, "signale": False, "source": "sim", "origine": "simulation"})
        d["kg"] += kg
        self.jour_courant["depose_kg"] += kg

    def step(self) -> None:
        self.jour_courant = {"jour": self.jour + 1, "produit_kg": 0.0, "precollecte_kg": 0.0, "collecte_kg": 0.0,
                             "depose_kg": 0.0, "cout_fcfa": 0.0}
        for groupe in (self.menages, self.tricycles, self.patrouilles, [self.mairie] if self.mairie else []):
            ordre = list(groupe)
            self.random.shuffle(ordre)
            for agent in ordre:
                agent.step()
        seuil = self.h("mairie", "seuil_depotoir_kg")
        self.series.append({**{k: round(v, 1) if isinstance(v, float) else v for k, v in self.jour_courant.items()},
                            "depotoirs": sum(1 for d in self.depotoirs.values() if d["kg"] >= seuil)})
        self.jour += 1


def _hypotheses_utilisees(cfg: dict[str, Any]) -> dict[str, Any]:
    """Copie des hypothèses de la configuration, pour l'étiquetage dans la sortie."""
    out = {}
    for groupe, valeurs in section(cfg, "hypotheses").items():
        if isinstance(valeurs, dict):
            out[groupe] = {k: v for k, v in valeurs.items() if not k.startswith("_")}
    return out


def run_scenario(params: dict[str, Any] | None, plan: dict[str, Any] | None, days: Any = 7,
                 actors_enabled: dict[str, bool] | None = None, seed: Any = 0,
                 sim_dumpsites: list[dict[str, Any]] | None = None, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Simule `days` jours du plan ; ne lève jamais : {"error": ...} si l'entrée est inutilisable."""
    try:
        cfg = cfg or get_config()
        if not isinstance(plan, dict) or not isinstance(plan.get("collection_points"), list):
            return {"error": "Plan absent ou mal formé : calculer d'abord un plan."}
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
            return {"error": "days doit être un entier entre 1 et 365."}
        warnings: list[str] = []
        base = dict(plan.get("params_used") or {})
        base.update({k: v for k, v in (params or {}).items() if k in section(cfg, "params")})
        base = clamp_params(base, cfg, warnings)
        actifs = {a: True for a in ACTEURS}
        if isinstance(actors_enabled, dict):
            actifs.update({k: bool(v) for k, v in actors_enabled.items() if k in actifs})
        graine = int(seed) if isinstance(seed, int) and not isinstance(seed, bool) else 0
        modele = ModeleOuaga(plan, base, cfg, graine, actifs, list(sim_dumpsites or []))
        for _ in range(days):
            modele.step()
        produit = sum(j["produit_kg"] for j in modele.series)
        collecte = sum(j["collecte_kg"] for j in modele.series)
        cout = sum(j["cout_fcfa"] for j in modele.series)
        seuil = modele.h("mairie", "seuil_depotoir_kg")
        restants = [d for d in modele.depotoirs.values() if d["kg"] >= seuil]
        part = round(collecte / produit, 4) if produit > 0 else None
        mairie, tricycles = modele.mairie, modele.tricycles
        return {
            "scenario_id": f"s_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}{uuid.uuid4().hex[:6]}",
            "plan_id": plan.get("plan_id"), "data_tag": "simulated", "source": "sim", "moteur": MOTEUR,
            "graine": graine, "jours": days, "params_used": base, "actors_enabled": actifs,
            "part_ramassee": part,
            "message_dechet": None if produit > 0 else "Aucun déchet produit (population nulle ou aucun ménage actif).",
            "cout_fcfa": round(cout), "cout_m_fcfa": round(cout / 1e6, 3),
            "depotoirs_restants": len(restants),
            "kg_produits": round(produit, 1), "kg_ramasses": round(collecte, 1),
            "menages_agents": len(modele.menages), "menages_par_agent": round(modele.echelle, 2),
            "series": modele.series,
            "depotoirs": [{"id": d["id"], "lat": d["lat"], "lon": d["lon"], "kg": round(d["kg"], 1),
                           "signale": d["signale"], "source": "sim", "origine": d["origine"]} for d in restants],
            "indicateurs": {
                "menages": {"abonnes": sum(1 for a in modele.menages if a.abonne),
                            "non_desservis": sum(1 for a in modele.menages if not a.desservi),
                            "sensibilises": sum(1 for a in modele.menages if a.sensibilise_jusqua >= modele.jour)},
                "pre_collecteurs": {"tricycles": len(tricycles), "en_panne_dernier_jour": sum(t.en_panne for t in tricycles),
                                    "kg_precollectes": round(sum(t.ramasse_kg for t in tricycles), 1)},
                "brigade": {"patrouilles": len(modele.patrouilles),
                            "depotoirs_signales": sum(b.patrouilles for b in modele.patrouilles),
                            "menages_sensibilises": sum(b.sensibilises for b in modele.patrouilles)},
                "mairie": {"camions_en_service": modele.camions_en_service, "jours_de_collecte": mairie.jours_collecte if mairie else 0,
                           "kg_collectes_points": round(mairie.collecte_kg, 1) if mairie else 0,
                           "kg_nettoyes_depotoirs": round(mairie.nettoye_kg, 1) if mairie else 0,
                           "budget_par_passage_fcfa": modele.budget_passage}},
            "agents": [{"cle": k, "nom": NOMS_ACTEURS[k], "actif": actifs[k]} for k in ACTEURS],
            "hypotheses": _hypotheses_utilisees(cfg),
            "assumptions": ["Simulation : chiffres issus d'hypothèses non mesurées (configuration, section hypotheses) ; "
                            "jamais un constat de terrain.",
                            f"{len(modele.menages)} agents ménages, chacun pour {modele.echelle:.1f} ménages réels."],
            "warnings": warnings,
        }
    except KeyError as exc:  # hypothèse manquante dans la configuration
        return {"error": str(exc.args[0] if exc.args else exc)}
    except Exception as exc:  # jamais d'exception vers l'API
        return {"error": f"Simulation impossible : {type(exc).__name__}: {exc}"}
