"""
Simulation multi-agents — Mesa, 4 acteurs : ménages, pré-collecteurs, brigade Laabal, mairie.
Le plan entre, 3 chiffres sortent : part ramassée, coût, dépotoirs restants.
"""
import math
import random

def simuler(plan, parametres, config, jours=7, seed=0):
    """
    Version légère sans dépendance Mesa obligatoire (fallback pur Python).
    Si Mesa est installé, on l'utilise ; sinon on émule les mêmes règles.
    Retourne {"part_ramassee":0.82, "cout_m_fcfa":..., "depotoirs_restants":...}
    """
    rng = random.Random(seed)
    hypo = config.get("hypotheses_simulation", {})
    h_menage = hypo.get("menage", {})
    h_pre = hypo.get("pre_collecteur", {})
    h_brigade = hypo.get("brigade_laabal", {})

    # --- Essayons Mesa si dispo ---
    try:
        from mesa import Agent, Model
        from mesa.time import RandomActivation
        # Modèle Mesa minimal (2-3 règles par acteur)
        class Menage(Agent):
            def __init__(self, uid, model, desservi):
                super().__init__(model)
                self.desservi=desservi
                self.a_depose=False
                self.unique_id=uid
            def step(self):
                if self.desservi:
                    if rng.random() > h_menage.get("proba_depot_sauvage_si_desservi_mais_plein",0.35):
                        self.a_depose=False
                    else:
                        self.a_depose=True
                else:
                    self.a_depose = rng.random() < h_menage.get("proba_depot_sauvage_si_non_desservi",0.78)
        class PreCollecteur(Agent):
            def __init__(self, uid, model):
                super().__init__(model); self.unique_id=uid
            def step(self):
                if rng.random() < h_pre.get("proba_panne_tricycle_jour",0.04):
                    return
                for a in self.model.agents:
                    if isinstance(a, Menage) and a.a_depose:
                        if rng.random() < h_pre.get("proba_passage_si_freq_respectee",0.88):
                            a.a_depose=False
        class Brigade(Agent):
            def __init__(self, uid, model):
                super().__init__(model); self.unique_id=uid
            def step(self):
                for a in self.model.agents:
                    if isinstance(a, Menage) and a.a_depose:
                        if rng.random() < h_brigade.get("proba_sensibilisation_reussie",0.22):
                            a.a_depose=False
        class Mairie(Agent):
            def __init__(self, uid, model): super().__init__(model); self.unique_id=uid
            def step(self): pass

        class OuagaModel(Model):
            def __init__(self, n_menages=500):
                super().__init__()
                self.schedule=RandomActivation(self)
                # desservi = 1 si proche d'un PR
                for i in range(n_menages):
                    desservi = rng.random() < (parametres.get("taux_abonnement_pct",35)/100 * 0.9 + 0.2)
                    self.schedule.add(Menage(i, self, desservi))
                for i in range(parametres.get("nb_tricycles",12)//4):
                    self.schedule.add(PreCollecteur(1000+i, self))
                for i in range(3):
                    self.schedule.add(Brigade(2000+i, self))
                self.schedule.add(Mairie(3000, self))
            def step(self): self.schedule.step()

        m=OuagaModel()
        for _ in range(jours): m.step()
        restants=sum(1 for a in m.schedule.agents if isinstance(a, Menage) and a.a_depose)
        total=sum(1 for a in m.schedule.agents if isinstance(a, Menage))
        part=round(1 - restants/max(1,total), 2)
        # coût issu du plan
        cout=plan.get("coherence", {}).get("cout_annuel_m_fcfa", 990) if plan else 990
        return {"part_ramassee": part, "cout_m_fcfa": cout, "depotoirs_restants": restants, "jours": jours, "moteur": "mesa"}

    except ImportError:
        # Fallback sans Mesa — mêmes probas
        n=500
        p_abonnement = parametres.get("taux_abonnement_pct", 35) / 100
        households = [{"served": rng.random() < p_abonnement * 0.9 + 0.2, "dumped": False} for _ in range(n)]
        collectors = max(0, parametres.get("nb_tricycles", 12) // 4)
        p_served = h_menage.get("proba_depot_sauvage_si_desservi_mais_plein", 0.35)
        p_unserved = h_menage.get("proba_depot_sauvage_si_non_desservi", 0.78)
        p_collection = h_pre.get("proba_passage_si_freq_respectee", 0.88)
        p_breakdown = h_pre.get("proba_panne_tricycle_jour", 0.04)
        p_sensitization = h_brigade.get("proba_sensibilisation_reussie", 0.22)
        for _ in range(jours):
            for household in households:
                household["dumped"] = rng.random() < (p_served if household["served"] else p_unserved)
            for _ in range(collectors):
                if rng.random() < p_breakdown:
                    continue
                for household in households:
                    if household["dumped"] and rng.random() < p_collection:
                        household["dumped"] = False
            for _ in range(3):
                for household in households:
                    if household["dumped"] and rng.random() < p_sensitization:
                        household["dumped"] = False
        sauvages = sum(household["dumped"] for household in households)
        part = round(1 - sauvages / max(1, n), 2)
        cout=plan.get("coherence", {}).get("cout_annuel_m_fcfa", 990) if plan else 990
        return {"part_ramassee": part, "cout_m_fcfa": cout, "depotoirs_restants": sauvages, "jours": jours, "moteur": "fallback (Mesa non installé)"}


def run_scenario(params: dict, plan: dict, days: int) -> dict:
    """Exécute le scénario du contrat à partir des paramètres et du plan calculé."""
    if not isinstance(params, dict):
        return {"error": "Les paramètres doivent être un objet."}
    if not isinstance(plan, dict) or not isinstance(plan.get("totals"), dict):
        return {"error": "Un plan calculé avec ses totaux est obligatoire."}
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        return {"error": "Le nombre de jours doit être un entier positif."}

    cost = plan["totals"].get("cost")
    subscription_rate = params.get("subscription_rate")
    tricycles = params.get("tricycles")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
        return {"error": "Le coût du plan est absent ou invalide."}
    if (isinstance(subscription_rate, bool) or not isinstance(subscription_rate, (int, float))
            or not math.isfinite(subscription_rate) or not 0 <= subscription_rate <= 1):
        return {"error": "subscription_rate doit être compris entre 0 et 1."}
    if isinstance(tricycles, bool) or not isinstance(tricycles, int) or tricycles < 0:
        return {"error": "tricycles doit être un entier positif ou nul."}

    try:
        result = simuler(
            {"coherence": {"cout_annuel_m_fcfa": cost / 1_000_000}},
            {"taux_abonnement_pct": subscription_rate * 100, "nb_tricycles": tricycles},
            {},
            jours=days,
            seed=0,
        )
    except Exception as exc:
        return {"error": f"Échec de la simulation : {type(exc).__name__}: {exc}"}

    result.update({
        "plan_id": plan.get("plan_id"),
        "days": days,
        "data_tag": "simulated",
        "assumptions": [
            "Simulation multi-agents sur 500 ménages synthétiques.",
            "Probabilités par défaut faute de configuration : dépôt sauvage 0,78 (non desservi), 0,35 (desservi), "
            "passage de pré-collecte 0,88, panne de tricycle 0,04, sensibilisation 0,22.",
        ],
    })
    return result
