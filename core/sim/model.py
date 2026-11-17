"""Simulation multi-agents — 4 acteurs : ménages, pré-collecteurs, brigade Laabal, mairie.

Le plan entre, 3 chiffres sortent : part ramassée, coût, dépotoirs restants.
Mesa 3.x est utilisé quand il est disponible. À défaut, un shim local expose la
même API (Agent, Model, agents.shuffle_do) : une seule implémentation des règles,
donc le même résultat pour une même graine, quel que soit le moteur.
"""
from __future__ import annotations

import json
import math
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Moteur : Mesa 3.x si disponible, shim compatible sinon.
# ---------------------------------------------------------------------------
try:  # Mesa >= 3
    from mesa import Agent, Model  # type: ignore

    MOTEUR = "mesa 3.x"
except Exception:  # pragma: no cover - environnement sans Mesa
    MOTEUR = "fallback local (sans Mesa)"

    class Agent:  # type: ignore[no-redef]
        def __init__(self, model: "Model"):
            self.model = model
            model._agents.append(self)

    class _AgentSet:  # type: ignore[no-redef]
        """Vue live sur les agents, comme l'AgentSet de Mesa."""

        def __init__(self, model: "Model"):
            self.model = model

        def __iter__(self):
            return iter(self.model._agents)

        def __len__(self) -> int:
            return len(self.model._agents)

        def shuffle_do(self, method: str) -> None:
            ordre = list(self.model._agents)
            self.model.random.shuffle(ordre)
            for agent in ordre:
                getattr(agent, method)()

    class Model:  # type: ignore[no-redef]
        def __init__(self, seed: int | None = None):
            self.random = random.Random(seed)
            self._agents: list[Agent] = []
            self.agents = _AgentSet(self)


RACINE = Path(__file__).resolve().parents[2]


def _charger_json(chemin: Path) -> dict[str, Any]:
    try:
        with chemin.open(encoding="utf-8") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except Exception:  # un fichier absent ne doit jamais casser la simulation
        return {}


def _config_defaut() -> dict[str, Any]:
    return _charger_json(RACINE / "config" / "commune_config.json")


def _plan_reference() -> dict[str, Any]:
    """Plan de démonstration utilisé par run_simulation quand aucun plan n'est fourni."""
    return _charger_json(RACINE / "data" / "mock" / "plan_real.json")


# ---------------------------------------------------------------------------
# Aide : bornes et lecture tolérante des paramètres
# ---------------------------------------------------------------------------
def _born(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _nombre(parametres: dict[str, Any], cle: str, defaut: float) -> float:
    try:
        return float(parametres.get(cle, defaut))
    except (TypeError, ValueError):
        return defaut


def _crises(parametres: dict[str, Any]) -> set[str]:
    brut = parametres.get("crises_actives") or []
    if isinstance(brut, str):
        brut = [brut]
    return {str(c) for c in brut if c}


def _cout_plan(plan: Any) -> float:
    """Le plan de A porte un coût en FCFA dans totals.cost : on le convertit en M FCFA."""
    if not isinstance(plan, dict):
        return 0.0
    for cle in ("cout_annuel_m_fcfa", "cout_m_fcfa"):
        if cle in plan:
            return round(float(plan[cle]), 3)
    coher = plan.get("coherence") if isinstance(plan.get("coherence"), dict) else {}
    for cle in ("cout_annuel_m_fcfa", "cout_m_fcfa"):
        if cle in coher:
            return round(float(coher[cle]), 3)
    totaux = plan.get("totals") if isinstance(plan.get("totals"), dict) else {}
    if "cost" in totaux:
        return round(float(totaux["cost"]) / 1_000_000, 3)
    return 0.0


def _regles(parametres: dict[str, Any], config: dict[str, Any]):
    """Coefficients d'une journée, dérivés des curseurs, de la config et des crises."""
    hypo = config.get("hypotheses_simulation", {}) if isinstance(config, dict) else {}
    h_menage = hypo.get("menage", {}) if isinstance(hypo, dict) else {}
    h_pre = hypo.get("pre_collecteur", {}) if isinstance(hypo, dict) else {}
    h_brigade = hypo.get("brigade_laabal", {}) if isinstance(hypo, dict) else {}
    actives = _crises(parametres)

    population = _nombre(parametres, "population", 1_200_000)
    # 500 ménages synthétiques = proxy de démonstration, pas un recensement.
    # Aucun ménage => aucun déchet : on ne fabrique pas de proxy dans ce cas.
    n_menages = 0 if population <= 0 else int(_born(population / 2400.0, 150, 900))

    abonnement = _born(_nombre(parametres, "taux_abonnement_pct", 35) / 100.0, 0.0, 1.0)
    desserte = _born(0.2 + abonnement * 0.8, 0.0, 0.98)

    camions = _nombre(parametres, "nb_camions", 12)
    freq_camions = _nombre(parametres, "freq_camions_par_semaine", 3)
    tricycles = _nombre(parametres, "nb_tricycles", 40)
    freq_tricycles = _nombre(parametres, "freq_tricycles_par_semaine", 6)
    budget_m = _nombre(parametres, "budget_annuel_m_fcfa", 1200)

    coeff_camion = _born(0.60 + camions / 12.0 * 0.25 + freq_camions / 7.0 * 0.15, 0.2, 1.0)
    coeff_tricycle = _born(
        0.50 + tricycles / 40.0 * 0.30 + freq_tricycles / 6.0 * 0.20, 0.2, 1.0
    )
    coeff_budget = _born(budget_m / 1200.0, 0.4, 1.1)

    if "panne_camions" in actives:
        coeff_camion *= 0.70
    if "saison_pluies" in actives:
        coeff_tricycle *= 0.80
        coeff_camion *= 0.90
    if "nouveau_quartier" in actives:
        # Le nouveau quartier n'est pas encore desservi par les points de regroupement.
        desserte *= 0.85
        n_menages = int(n_menages * 1.10)

    return {
        "n_menages": n_menages,
        "nb_pre": max(1, int(tricycles / 10)),
        "desserte": desserte,
        "coeff_camion": coeff_camion,
        "coeff_tricycle": coeff_tricycle,
        "coeff_budget": coeff_budget,
        "proba_depot_desservi": float(
            h_menage.get("proba_depot_sauvage_si_desservi_mais_plein", 0.35)
        ),
        "proba_depot_non_desservi": float(
            h_menage.get("proba_depot_sauvage_si_non_desservi", 0.78)
        ),
        "proba_panne_tricycle": float(h_pre.get("proba_panne_tricycle_jour", 0.04)),
        "proba_passage": float(h_pre.get("proba_passage_si_freq_respectee", 0.88)),
        "proba_sensibilisation": float(h_brigade.get("proba_sensibilisation_reussie", 0.22)),
        "crises": sorted(actives),
    }


# ---------------------------------------------------------------------------
# Pont explicite avec le plan de A (aucune hypothèse inventée)
# ---------------------------------------------------------------------------
def _taux_non_servis(plan: Any) -> float:
    """Part des points du plan réellement laissés sans tournée.

    `unserved` et `totals.points_unserved` sont au contrat §5 ; quand les deux
    sont présents on préfère la liste, qui porte les raisons. Le dénominateur
    est `points_served + points_unserved` du plan, jamais un nombre synthétique.
    """
    if not isinstance(plan, dict):
        return 0.0
    totaux = plan.get("totals") if isinstance(plan.get("totals"), dict) else {}
    servi = totaux.get("points_served")
    non_servi = totaux.get("points_unserved")
    if isinstance(non_servi, (int, float)) and not isinstance(non_servi, bool):
        if isinstance(servi, (int, float)) and not isinstance(servi, bool):
            total = float(servi) + float(non_servi)
            if total > 0:
                return _born(float(non_servi) / total, 0.0, 1.0)
    liste = plan.get("unserved")
    points = plan.get("collection_points")
    if isinstance(liste, list) and isinstance(points, list) and points:
        return _born(len(liste) / len(points), 0.0, 1.0)
    return 0.0


def _raison_non_servis(plan: Any) -> list[str]:
    """Raisons déclarées par A dans `unserved` (jamais devinées)."""
    if not isinstance(plan, dict) or not isinstance(plan.get("unserved"), list):
        return []
    raisons = {
        str(p["reason"])
        for p in plan["unserved"]
        if isinstance(p, dict) and p.get("reason")
    }
    return sorted(raisons)


def _masse_collectee(plan: Any) -> float | None:
    """`totals.collected_kg` du contrat §5, en kg ; None si le plan ne le porte pas."""
    if not isinstance(plan, dict):
        return None
    totaux = plan.get("totals") if isinstance(plan.get("totals"), dict) else {}
    valeur = totaux.get("collected_kg")
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not math.isfinite(valeur):
        return None
    return max(0.0, float(valeur))


def _regles_plan(plan: Any, r: dict[str, Any]) -> dict[str, Any]:
    """Décline les chiffres du plan dans les règles des agents C.

    Deux leviers seulement, tous deux lus dans le plan :
    * un point `unserved` n'est pas vidé par la mairie : moins il y en a, plus
      la saturation des centres est forte, donc plus le dépôt sauvage augmente ;
    * `totals.collected_kg` fixe l'échelle de la charge traitée par les
      pré-collecteurs, rapportée à la taille du proxy (ménages synthétiques).
    """
    taux = _taux_non_servis(plan)
    collecte = _masse_collectee(plan)
    quotient = None if collecte is None else collecte / max(1, r["n_menages"])
    return {
        "taux_points_non_servis": round(taux, 4),
        "raisons_non_servis": _raison_non_servis(plan),
        "kg_collectes_plan": collecte,
        "kg_collectes_par_menage": None if quotient is None else round(quotient, 3),
        # Saturation des points de regroupement : 0 si tout le plan est servi,
        # 1 si tous ses points sont en `unserved`.
        "saturation_plan": round(taux, 4),
        # La collecte du plan module la probabilité de passage des tricycles.
        "facteur_collecte": (
            1.0 if quotient is None else _born(0.6 + quotient / 250.0, 0.6, 1.0)
        ),
    }


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
class Menage(Agent):
    def __init__(self, uid: int, model: "Model", desservi: bool, r: dict[str, Any]):
        super().__init__(model)
        self.unique_id = uid
        self.desservi = desservi
        self.r = r
        self.a_depose = False

    def step(self):
        r = self.r
        if self.desservi:
            # Un ménage desservi peut encore jeter si le service est saturé.
            saturation = 1.0 - 0.5 * r["coeff_camion"] * r["coeff_budget"]
            saturation = max(saturation, r["saturation_plan"])
            proba = r["proba_depot_desservi"] * _born(saturation, 0.3, 1.0)
        else:
            proba = r["proba_depot_non_desservi"]
        self.a_depose = self.model.random.random() < proba  # type: ignore[attr-defined]


class PreCollecteur(Agent):
    def __init__(self, uid: int, model: "Model", r: dict[str, Any]):
        super().__init__(model)
        self.unique_id = uid
        self.r = r

    def step(self):
        r = self.r
        panne = r["proba_panne_tricycle"] + (0.12 if "saison_pluies" in r["crises"] else 0.0)
        if self.model.random.random() < panne:  # type: ignore[attr-defined]
            return
        proba = r["proba_passage"] * r["coeff_tricycle"] * 0.25 * r["facteur_collecte"]
        # Chaque pré-collecteur ne couvre qu'une part des ménages : la flotte compte.
        tournee = self.unique_id - 10_000
        for agent in self.model.agents:  # type: ignore[attr-defined]
            if isinstance(agent, Menage) and agent.a_depose and agent.unique_id % self.r["nb_pre"] == tournee:
                if self.model.random.random() < proba:  # type: ignore[attr-defined]
                    agent.a_depose = False


class Brigade(Agent):
    def __init__(self, uid: int, model: "Model", r: dict[str, Any]):
        super().__init__(model)
        self.unique_id = uid
        self.r = r

    def step(self):
        r = self.r
        proba = r["proba_sensibilisation"]
        if "saison_pluies" in r["crises"]:
            proba *= 0.8
        for agent in self.model.agents:  # type: ignore[attr-defined]
            if isinstance(agent, Menage) and agent.a_depose:
                if self.model.random.random() < proba:  # type: ignore[attr-defined]
                    agent.a_depose = False


class Mairie(Agent):
    def __init__(self, uid: int, model: "Model", r: dict[str, Any]):
        super().__init__(model)
        self.unique_id = uid
        self.r = r

    def step(self):
        r = self.r
        # La mairie envoie la brigade mécanisée selon les camions, la fréquence et le budget.
        # Un point en `unserved` n'est pas vidé : la charge restante augmente.
        proba = 0.12 * r["coeff_camion"] * r["coeff_budget"] * (1.0 - r["saturation_plan"])
        for agent in self.model.agents:  # type: ignore[attr-defined]
            if isinstance(agent, Menage) and agent.a_depose:
                if self.model.random.random() < proba:  # type: ignore[attr-defined]
                    agent.a_depose = False


# Noms exigés par le guide final (les alias gardent les anciens imports valides).
Menages = Menage
PreCollecteurs = PreCollecteur
BrigadeLaabal = Brigade
Municipalite = Mairie

AGENTS = (
    {"nom": "Ménages", "classe": "Menage", "regle": "déposent ou non selon la desserte et la saturation"},
    {"nom": "Précollecteurs", "classe": "PreCollecteur", "regle": "ramassent une part des dépôts, panne possible"},
    {"nom": "Brigade Laabal", "classe": "Brigade", "regle": "sensibilise et évite certains dépôts sauvages"},
    {"nom": "Municipalité", "classe": "Mairie", "regle": "envoie la brigade mécanisée selon camions, fréquence et budget"},
)


class OuagaModel(Model):
    def __init__(self, parametres: dict[str, Any], config: dict[str, Any], r: dict[str, Any], seed: int):
        super().__init__(seed=seed)
        self.regles = r
        for i in range(r["n_menages"]):
            desservi = self.random.random() < r["desserte"]  # type: ignore[attr-defined]
            Menage(i, self, desservi, r)
        for i in range(r["nb_pre"]):
            PreCollecteur(10_000 + i, self, r)
        for i in range(3):
            Brigade(20_000 + i, self, r)
        Mairie(30_000, self, r)

    def step(self):
        self.agents.shuffle_do("step")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# API publique — conserve exactement les clés historiques du contrat
# ---------------------------------------------------------------------------
def simuler(
    plan: Any,
    parametres: dict[str, Any] | None,
    config: dict[str, Any] | None,
    jours: int = 7,
    seed: int = 0,
) -> dict[str, Any]:
    parametres = parametres if isinstance(parametres, dict) else {}
    config = config if isinstance(config, dict) else {}
    try:
        jours = max(1, int(jours))
    except (TypeError, ValueError):
        jours = 7
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        seed = 0

    r = _regles(parametres, config)
    r.update(_regles_plan(plan, r))
    modele = OuagaModel(parametres, config, r, seed)
    for _ in range(jours):
        modele.step()

    restants = sum(
        1 for a in modele.agents if isinstance(a, Menage) and a.a_depose  # type: ignore[attr-defined]
    )
    total = r["n_menages"]
    sans_dechet = total <= 0
    # Sans déchet, « 100 % ramassé » serait faux : on affiche 0 et un message.
    part = 0.0 if sans_dechet else round(1.0 - restants / max(1, total), 3)

    return {
        "part_ramassee": part,
        "cout_m_fcfa": _cout_plan(plan),
        "depotoirs_restants": 0 if sans_dechet else restants,
        "sans_dechet": sans_dechet,
        "message_dechet": "Aucun déchet généré" if sans_dechet else None,
        "jours": jours,
        "moteur": MOTEUR,
        # Métadonnées d'honnêteté : le compteur est un proxy, pas un relevé terrain.
        "unite_depotoirs_restants": "ménages synthétiques (proxy)",
        "menages_synthetiques": total,
        "crises_actives": r["crises"],
        "graine": seed,
        "agents": [dict(a) for a in AGENTS],
        "hypotheses": "paramètres de démonstration à valider avec la mairie",
        # Traçabilité du plan : chaque nombre vient du plan, rien n'est inventé.
        "plan": {
            "taux_points_non_servis": r["taux_points_non_servis"],
            "points_non_servis": (
                plan.get("totals", {}).get("points_unserved")
                if isinstance(plan, dict) and isinstance(plan.get("totals"), dict) else None
            ),
            "raisons_non_servis": r["raisons_non_servis"],
            "kg_collectes": r["kg_collectes_plan"],
            "kg_collectes_par_menage": r["kg_collectes_par_menage"],
        },
    }


# ---------------------------------------------------------------------------
# Fonctions partagées du contrat (docs/contracts.md §6)
# ---------------------------------------------------------------------------
def _scenario_id() -> str:
    return "s_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + uuid.uuid4().hex[:6]


def _repli(exc: Exception | None = None) -> dict[str, Any]:
    """Dernier état valide connu, toujours marqué « simulé » et jamais d'exception."""
    sortie: dict[str, Any] = {
        "part_ramassee": 0.0,
        "cout_m_fcfa": 0.0,
        "depotoirs_restants": 0,
        "jours": 1,
        "days": 1,
        "moteur": MOTEUR,
        "unite_depotoirs_restants": "ménages synthétiques (proxy)",
        "menages_synthetiques": 0,
        "crises_actives": [],
        "graine": 0,
        "agents": [dict(a) for a in AGENTS],
        "fonction": "run_scenario",
        "source_plan": "indisponible",
        "data_tag": "simulated",
        "series": [],
        "agent_states": [],
        "events": [],
    }
    if exc is not None:
        sortie["warnings"] = [f"Simulation de repli : {type(exc).__name__} — {exc}"]
    return sortie


# ---------------------------------------------------------------------------
# Validation Backend (contrat §6) — renvoie {"error": ...}, jamais d'exception.
# ---------------------------------------------------------------------------
def _valider_entree(
    params: Any, plan: Any, days: Any
) -> tuple[dict[str, Any], dict[str, Any], int, str | None]:
    if not isinstance(params, dict):
        return {}, {}, 0, "Les paramètres doivent être un objet."
    if not isinstance(plan, dict) or not isinstance(plan.get("totals"), dict):
        return {}, {}, 0, "Un plan calculé avec ses totaux est obligatoire."
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        return {}, {}, 0, "Le nombre de jours doit être un entier positif."

    total = plan["totals"]
    cout = total.get("cost")
    if isinstance(cout, bool) or not isinstance(cout, (int, float)) or not math.isfinite(cout) or cout < 0:
        return {}, {}, 0, "Le coût du plan est absent ou invalide."

    # Les tests C historiques appellent run_scenario avec les curseurs du
    # membre C (taux_abonnement_pct en pourcentage, nb_tricycles). Le contrat
    # Backend utilise subscription_rate (0..1) et tricycles ; les deux formes
    # sont acceptées, sans jamais fabriquer de valeur pour un champ manquant.
    if "subscription_rate" in params and "taux_abonnement_pct" not in params:
        subscription = params["subscription_rate"]
        if (isinstance(subscription, bool) or not isinstance(subscription, (int, float))
                or not math.isfinite(subscription) or not 0 <= subscription <= 1):
            return {}, {}, 0, "subscription_rate doit être compris entre 0 et 1."
    elif "taux_abonnement_pct" in params:
        if ("subscription_rate" in params
                and (isinstance(params["subscription_rate"], bool)
                     or not isinstance(params["subscription_rate"], (int, float))
                     or not math.isfinite(params["subscription_rate"])
                     or not 0 <= params["subscription_rate"] <= 1)):
            return {}, {}, 0, "subscription_rate doit être compris entre 0 et 1."
    else:
        return {}, {}, 0, "subscription_rate doit être compris entre 0 et 1."

    if "tricycles" in params and "nb_tricycles" not in params:
        tricycles = params["tricycles"]
        if isinstance(tricycles, bool) or not isinstance(tricycles, int) or tricycles < 0:
            return {}, {}, 0, "tricycles doit être un entier positif ou nul."
    elif "nb_tricycles" in params:
        if ("tricycles" in params
                and (isinstance(params["tricycles"], bool)
                     or not isinstance(params["tricycles"], int)
                     or params["tricycles"] < 0)):
            return {}, {}, 0, "tricycles doit être un entier positif ou nul."
    else:
        return {}, {}, 0, "tricycles doit être un entier positif ou nul."

    for cle in ("collected_kg", "uncollected_kg", "points_unserved", "points_served"):
        valeur = total.get(cle)
        if valeur is not None and (isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not math.isfinite(valeur)):
            return {}, {}, 0, f"totals.{cle} est invalide dans le plan."

    # Un plan conforme porte `unserved` (liste) ; sa présence est vérifiée sans
    # l'exiger quand le champ n'existe pas dans une version antérieure du contrat.
    if "unserved" in plan and not isinstance(plan["unserved"], list):
        return {}, {}, 0, "Le champ unserved du plan doit être une liste."

    return params, plan, days, None


def _parametres_simulation(params: dict[str, Any]) -> dict[str, Any]:
    """Convertit les noms du contrat §6 vers les curseurs historiques du membre C."""
    if "taux_abonnement_pct" in params:
        abonnement_pct = float(params["taux_abonnement_pct"])
    else:
        abonnement_pct = float(params["subscription_rate"]) * 100.0
    tricycles = params["nb_tricycles"] if "nb_tricycles" in params else params["tricycles"]
    return {
        "taux_abonnement_pct": abonnement_pct,
        "nb_tricycles": int(tricycles),
        "nb_camions": params.get("trucks", 12),
        "population": params.get("population", 1_200_000),
        "crises_actives": (
            (["panne_camions"] if params.get("broken_trucks") else [])
            + (["saison_pluies"] if params.get("rainy_season") else [])
            + (["nouveau_quartier"] if params.get("extra_territories") else [])
        ),
        "graine": params.get("graine", params.get("seed", 0)),
    }


def run_scenario(
    params: dict[str, Any] | None = None,
    plan: dict[str, Any] | int | None = None,
    days: int | dict[str, bool] | None = None,
    actors_enabled: dict[str, bool] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Lance un scénario et ne lève jamais d'exception vers l'appelant.

    Deux signatures sont acceptées :
    * historique (contrat §6) : ``run_scenario(params, plan, days)`` ;
    * étendue (démo acteurs)  : ``run_scenario(params, days, actors_enabled)``.

    La détection repose sur le type du 2ᵉ argument positionnel : un dictionnaire
    est un plan (ancienne signature), un nombre est le nombre de jours (nouvelle).
    """
    try:
        nouveaux_acteurs = (
            actors_enabled is not None
            or isinstance(days, dict)
            or (plan is not None and not isinstance(plan, dict))
        )

        if nouveaux_acteurs:
            # --- Nouvelle signature : jours + drapeaux d'acteurs -------------
            if isinstance(days, dict):
                acteurs = days
                jours_bruts = plan
            else:
                acteurs = actors_enabled
                jours_bruts = plan if (plan is not None and not isinstance(plan, dict)) else days
            plan_acteurs = params.get("plan") if isinstance(params, dict) else None
            if isinstance(plan_acteurs, dict):
                # Le contrat §6 s'applique aussi ici quand un plan valide est fourni.
                valides, _, duree_valide, erreur = _valider_entree(params, plan_acteurs, jours_bruts)
                if erreur is not None:
                    return {"error": erreur}
                jours_bruts = duree_valide
            if "actors_enabled" in kwargs and isinstance(kwargs["actors_enabled"], dict):
                acteurs = kwargs["actors_enabled"]
            try:
                duree = max(1, int(jours_bruts))
            except (TypeError, ValueError):
                duree = 7
            try:
                graine = int(params.get("graine", params.get("seed", 42))) if isinstance(params, dict) else 42
            except (TypeError, ValueError):
                graine = 42

            from .actors import executer  # import différé : évite tout cycle

            resultat = executer(params or {}, duree, acteurs, graine)
            if resultat.get("sans_dechet"):
                resultat.setdefault("assumptions", []).insert(
                    0, "Aucun déchet généré : aucun pourcentage de collecte n'est affiché."
                )
            resultat.update({
                "scenario_id": _scenario_id(),
                "plan_id": (plan_acteurs or {}).get("plan_id")
                if isinstance(plan_acteurs, dict) else None,
            })
            return resultat

        # --- Signature historique : plan + jours ---------------------------
        valides, plan_valide, duree, erreur = _valider_entree(params, plan, days)
        if erreur is not None:
            return {"error": erreur}

        try:
            graine = int(valides.get("graine", valides.get("seed", 0)))
        except (TypeError, ValueError):
            graine = 0
        resultat = simuler(
            plan_valide,
            _parametres_simulation(valides),
            _config_defaut(),
            jours=duree,
            seed=graine,
        )
        resultat.update({
            "fonction": "run_scenario",
            "scenario_id": _scenario_id(),
            "plan_id": plan_valide.get("id") or plan_valide.get("plan_id"),
            "params_used": valides,
            "days": duree,
            "source_plan": "plan fourni par A",
            "data_tag": "simulated",
            "assumptions": ([
                "Aucun déchet généré : aucun pourcentage de collecte n'est affiché."
            ] if resultat.get("sans_dechet") else []) + [
                "Simulation multi-agents sur {} ménages synthétiques (proxy).".format(
                    resultat["menages_synthetiques"]
                ),
                "Le résultat dépend du plan : taux de points non servis et kg collectés "
                "sont lus dans unserved et totals.collected_kg (contrat §5).",
                "Probabilités par défaut faute de configuration : dépôt sauvage 0,78 (non desservi), "
                "0,35 (desservi), passage de pré-collecte 0,88, panne de tricycle 0,04, "
                "sensibilisation 0,22.",
            ],
        })
        return resultat
    except Exception as exc:  # règle commune : jamais d'exception vers l'appelant
        return _repli(exc)


def run_simulation(
    params: dict[str, Any] | None = None,
    days: int = 7,
    actors_enabled: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Signature du message d'équipe, avec support optionnel des acteurs.

    Sans ``actors_enabled``, le comportement historique est conservé (le même
    calcul que ``run_scenario(params, plan, days)`` avec le plan de référence),
    ce qui garantit l'égalité attendue par les tests du contrat.
    """
    parametres = params if isinstance(params, dict) else {}
    plan = parametres.get("plan")
    source = "plan fourni dans params"
    if not isinstance(plan, dict):
        plan = _plan_reference()
        source = "plan de référence simulé (mock local)"
    if actors_enabled is None:
        resultat = run_scenario(parametres, plan, days)
    else:
        avec_plan = dict(parametres)
        avec_plan["plan"] = plan
        resultat = run_scenario(avec_plan, days, actors_enabled)
        resultat["source_plan"] = source
    resultat["fonction"] = "run_simulation"
    resultat["source_plan"] = source
    return resultat
