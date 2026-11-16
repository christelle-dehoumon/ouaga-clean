"""
Simulation multi-agents — Mesa, 4 acteurs : ménages, pré-collecteurs, brigade Laabal, mairie.
Le plan entre, 3 chiffres sortent : part ramassée, coût, dépotoirs restants.
"""
import random

def simuler(plan, parametres, config, jours=7, seed=0):
    """
    Version légère sans dépendance Mesa obligatoire (fallback pur Python).
    Si Mesa est installé, on l'utilise ; sinon on émule les mêmes règles.
    Retourne {"part_ramassee":0.82, "cout_m_fcfa":..., "depotoirs_restants":...}
    """
    random.seed(seed)
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
                    if random.random() > h_menage.get("proba_depot_sauvage_si_desservi_mais_plein",0.35):
                        self.a_depose=False
                    else:
                        self.a_depose=True
                else:
                    self.a_depose = random.random() < h_menage.get("proba_depot_sauvage_si_non_desservi",0.78)
        class PreCollecteur(Agent):
            def __init__(self, uid, model):
                super().__init__(model); self.unique_id=uid
            def step(self):
                if random.random() < h_pre.get("proba_panne_tricycle_jour",0.04):
                    return
                for a in self.model.agents:
                    if isinstance(a, Menage) and a.a_depose:
                        if random.random() < h_pre.get("proba_passage_si_freq_respectee",0.88):
                            a.a_depose=False
        class Brigade(Agent):
            def __init__(self, uid, model):
                super().__init__(model); self.unique_id=uid
            def step(self):
                for a in self.model.agents:
                    if isinstance(a, Menage) and a.a_depose:
                        if random.random() < h_brigade.get("proba_sensibilisation_reussie",0.22):
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
                    desservi = random.random() < (parametres.get("taux_abonnement_pct",35)/100 * 0.9 + 0.2)
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
        desservis=int(n * (parametres.get("taux_abonnement_pct",35)/100*0.8+0.2))
        non_desservis=n-desservis
        # dépôts sauvages initiaux
        sauvages = int(non_desservis * h_menage.get("proba_depot_sauvage_si_non_desservi",0.78) + desservis * h_menage.get("proba_depot_sauvage_si_desservi_mais_plein",0.35))
        # pré-collecte ramasse
        ramasses_pre=int(sauvages * h_pre.get("proba_passage_si_freq_respectee",0.88) * 0.6)
        sauvages-=ramasses_pre
        # brigade
        ramenes_brigade=int(sauvages * h_brigade.get("proba_sensibilisation_reussie",0.22))
        sauvages=max(0, sauvages-ramenes_brigade)
        part=round(1 - sauvages/max(1,n),2)
        cout=plan.get("coherence", {}).get("cout_annuel_m_fcfa", 990) if plan else 990
        return {"part_ramassee": part, "cout_m_fcfa": cout, "depotoirs_restants": sauvages, "jours": jours, "moteur": "fallback (Mesa non installé)"}
