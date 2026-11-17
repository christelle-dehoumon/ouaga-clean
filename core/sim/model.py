"""
Simulation multi-agents — 4 acteurs : ménages, pré-collecteurs, brigade Laabal, mairie.

Le plan entre, 3 chiffres sortent : part ramassée, coût, dépotoirs restants.
Mesa 3.x est utilisé quand il est disponible. À défaut, un shim local expose la
même API (Agent, Model, agents.shuffle_do) : une seule implémentation des règles,
donc le même résultat pour une même graine, quel que soit le moteur.
"""
from __future__ import annotations

import random
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
    n_menages = int(_born(population / 2400.0, 150, 900))

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
        proba = r["proba_passage"] * r["coeff_tricycle"] * 0.25
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
        proba = 0.12 * r["coeff_camion"] * r["coeff_budget"]
        for agent in self.model.agents:  # type: ignore[attr-defined]
            if isinstance(agent, Menage) and agent.a_depose:
                if self.model.random.random() < proba:  # type: ignore[attr-defined]
                    agent.a_depose = False


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
    modele = OuagaModel(parametres, config, r, seed)
    for _ in range(jours):
        modele.step()

    restants = sum(
        1 for a in modele.agents if isinstance(a, Menage) and a.a_depose  # type: ignore[attr-defined]
    )
    total = r["n_menages"]
    part = round(1.0 - restants / max(1, total), 3)

    return {
        "part_ramassee": part,
        "cout_m_fcfa": _cout_plan(plan),
        "depotoirs_restants": restants,
        "jours": jours,
        "moteur": MOTEUR,
        # Métadonnées d'honnêteté : le compteur est un proxy, pas un relevé terrain.
        "unite_depotoirs_restants": "ménages synthétiques (proxy)",
        "menages_synthetiques": total,
        "crises_actives": r["crises"],
        "graine": seed,
        "hypotheses": "paramètres de démonstration à valider avec la mairie",
    }
