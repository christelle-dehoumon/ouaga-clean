"""Tests du membre C — simulation Mesa 3.x / shim compatible.

Ces tests utilisent unittest (aucune dépendance pytest nécessaire) et sont
également collectés par pytest si celui-ci est installé plus tard.
"""
from __future__ import annotations

import importlib
import json
import statistics
import sys
import unittest
from pathlib import Path

from core.sim import model as sim
from core.sim import scenarios

RACINE = Path(__file__).resolve().parents[1]
PLAN = json.loads((RACINE / "data" / "mock" / "plan_real.json").read_text(encoding="utf-8"))

BASE = {
    "population": 2_450_000,
    "taux_abonnement_pct": 35,
    "nb_camions": 12,
    "freq_camions_par_semaine": 3,
    "budget_annuel_m_fcfa": 1200,
    "nb_tricycles": 40,
    "freq_tricycles_par_semaine": 6,
    "crises_actives": [],
}


class SimulationTest(unittest.TestCase):
    def test_contrat_sortie(self):
        r = sim.simuler(PLAN, BASE, {}, jours=7, seed=42)
        for cle in (
            "part_ramassee", "cout_m_fcfa", "depotoirs_restants", "jours", "moteur",
            "unite_depotoirs_restants", "menages_synthetiques", "crises_actives", "graine",
        ):
            self.assertIn(cle, r)
        self.assertIsInstance(r["part_ramassee"], float)
        self.assertGreaterEqual(r["part_ramassee"], 0.0)
        self.assertLessEqual(r["part_ramassee"], 1.0)
        self.assertGreater(r["depotoirs_restants"], 0)
        self.assertIn("proxy", r["unite_depotoirs_restants"])

    def test_reproductibilite(self):
        self.assertEqual(
            sim.simuler(PLAN, BASE, {}, 7, 42),
            sim.simuler(PLAN, BASE, {}, 7, 42),
        )

    def test_cout_vient_du_plan_en_millions_fcfa(self):
        r = sim.simuler(PLAN, BASE, {}, 7, 42)
        self.assertAlmostEqual(r["cout_m_fcfa"], PLAN["totals"]["cost"] / 1_000_000, places=3)
        self.assertEqual(sim.simuler({}, BASE, {}, 7, 42)["cout_m_fcfa"], 0.0)

    def test_parametres_bornes(self):
        r = sim.simuler(None, {}, {}, jours=0, seed="x")
        self.assertEqual(r["jours"], 1)
        self.assertEqual(r["graine"], 0)

    def _moyenne(self, params: dict) -> float:
        return statistics.mean(sim.simuler(PLAN, params, {}, 7, graine)["part_ramassee"] for graine in range(12))

    def test_abonnement_ameliorose_la_collecte(self):
        self.assertGreater(
            self._moyenne({**BASE, "taux_abonnement_pct": 70}),
            self._moyenne(BASE),
        )

    def test_chacune_des_crises_degrade_la_collecte(self):
        reference = self._moyenne(BASE)
        for crise in ("panne_camions", "saison_pluies", "nouveau_quartier"):
            with self.subTest(crise=crise):
                self.assertLess(self._moyenne({**BASE, "crises_actives": [crise]}), reference)

    def test_shim_sans_mesa_donne_le_meme_resultat(self):
        attendu = sim.simuler(PLAN, BASE, {}, 7, 42)
        attendu_sans_moteur = {k: v for k, v in attendu.items() if k != "moteur"}
        sauvegarde = sys.modules.get("mesa")
        sys.modules["mesa"] = None  # force l'except ImportError
        try:
            importlib.reload(sim)
            self.assertIn("fallback", sim.MOTEUR)
            obtenu = sim.simuler(PLAN, BASE, {}, 7, 42)
            self.assertEqual({k: v for k, v in obtenu.items() if k != "moteur"}, attendu_sans_moteur)
        finally:
            if sauvegarde is None:
                sys.modules.pop("mesa", None)
            else:
                sys.modules["mesa"] = sauvegarde
            importlib.reload(sim)

    def test_quatre_agents_du_guide(self):
        self.assertEqual([a["nom"] for a in sim.AGENTS],
                         ["Ménages", "Précollecteurs", "Brigade Laabal", "Municipalité"])
        regles = sim._regles(BASE, {})
        modele = sim.OuagaModel(BASE, {}, regles, 0)
        classes = {type(a) for a in modele.agents}
        self.assertTrue({sim.Menages, sim.PreCollecteurs, sim.BrigadeLaabal, sim.Municipalite} <= classes)

    def test_run_scenario_depends_on_plan(self):
        """Deux plans différents, mêmes paramètres et graine : résultat différent."""
        params = {"subscription_rate": 0.4, "tricycles": 8, "seed": 42}
        plan_a = {
            "plan_id": "pA",
            "totals": {"cost": 1_000_000, "collected_kg": 120_000,
                       "uncollected_kg": 0, "points_served": 10, "points_unserved": 0},
            "unserved": [],
        }
        plan_b = {
            "plan_id": "pB",
            "totals": {"cost": 1_000_000, "collected_kg": 20_000,
                       "uncollected_kg": 100_000, "points_served": 3, "points_unserved": 7},
            "unserved": [{"point_id": "p4", "reason": "capacity", "detail": "test"}],
        }
        a = sim.run_scenario(params, plan_a, 7)
        b = sim.run_scenario(params, plan_b, 7)
        self.assertNotIn("error", a)
        self.assertNotIn("error", b)
        self.assertNotEqual(a["part_ramassee"], b["part_ramassee"])
        self.assertNotEqual(a["depotoirs_restants"], b["depotoirs_restants"])
        self.assertEqual(a["cout_m_fcfa"], b["cout_m_fcfa"])
        self.assertEqual(a["graine"], b["graine"])

    def test_run_scenario_contrat(self):
        r = sim.run_scenario(BASE, PLAN, 7)
        for cle in ("part_ramassee", "cout_m_fcfa", "depotoirs_restants", "days", "fonction", "params_used"):
            self.assertIn(cle, r)
        self.assertEqual(r["fonction"], "run_scenario")
        self.assertEqual(r["days"], 7)
        self.assertEqual(r["plan_id"], PLAN.get("plan_id"))

    def test_run_simulation_signature_equipe(self):
        r = sim.run_simulation(BASE, 7)
        self.assertEqual(r["fonction"], "run_simulation")
        self.assertIn("plan de référence", r["source_plan"])
        self.assertAlmostEqual(r["part_ramassee"], sim.run_scenario(BASE, PLAN, 7)["part_ramassee"])

    def test_fonctions_partagees_ne_levent_jamais(self):
        for appellable, args in (
            (sim.run_scenario, (None, None, "bizarre")),
            (sim.run_simulation, (None, None)),
            (scenarios.comparer, ({}, {})),
        ):
            with self.subTest(fonction=appellable.__name__):
                self.assertIsInstance(appellable(*args), dict)

    def test_historique_et_comparaison(self):
        hist = scenarios.HistoriqueScenarios(limite=3)
        a = hist.ajouter({
            "plan_id": "pA",
            "params": {"nb_camions": 12},
            "plan": {"cout_annuel_m_fcfa": 0.405, "tonnes_rue_par_jour": 180.9},
            "simulation": {"part_ramassee": 0.70, "depotoirs_restants": 274},
        })
        b = hist.ajouter({
            "plan_id": "pB",
            "params": {"nb_camions": 9},
            "plan": {"cout_annuel_m_fcfa": 0.396, "tonnes_rue_par_jour": 186.6},
            "simulation": {"part_ramassee": 0.66, "depotoirs_restants": 308},
        })
        self.assertEqual(len(hist.liste()), 2)
        d = hist.comparer_ids(a["id"], b["id"])
        self.assertAlmostEqual(d["diff_cout"], -0.009)
        self.assertAlmostEqual(d["diff_tonnes"], 5.7)
        self.assertAlmostEqual(d["diff_part_ramassee"], -0.04)
        self.assertEqual(d["diff_depotoirs"], 34)

    def test_zero_dechet_sans_faux_pourcent(self):
        """Aucun ménage/déchet : message explicite, jamais 100 % de collecte."""
        plan_vide = {
            "plan_id": "p_zero",
            "totals": {"cost": 0, "collected_kg": 0, "uncollected_kg": 0,
                       "points_served": 0, "points_unserved": 0},
            "unserved": [], "collection_points": [], "routes": [],
        }
        historique = sim.run_scenario(
            {"subscription_rate": 0, "tricycles": 0, "population": 0}, plan_vide, 2)
        self.assertNotIn("error", historique)
        self.assertTrue(historique["sans_dechet"])
        self.assertEqual(historique["message_dechet"], "Aucun déchet généré")
        self.assertEqual(historique["part_ramassee"], 0.0)
        self.assertEqual(historique["depotoirs_restants"], 0)

        params_acteurs = {
            "subscription_rate": 0, "tricycles": 0, "population": 0, "seed": 4,
            "plan": plan_vide,
        }
        acteurs = sim.run_scenario(
            params_acteurs, 2, {nom: True for nom in ("menages", "pre_collecteurs", "brigade", "mairie")})
        self.assertNotIn("error", acteurs)
        self.assertTrue(acteurs["sans_dechet"])
        self.assertEqual(acteurs["message_dechet"], "Aucun déchet généré")
        self.assertNotEqual(acteurs["part_ramassee"], 1.0)
        self.assertEqual(acteurs["points_etat"], [])

    def test_acteurs_retirables_avec_effet_reproductible(self):
        tous = {nom: True for nom in ("menages", "pre_collecteurs", "brigade", "mairie")}
        sans_brigade = {**tous, "brigade": False}
        params = {**PLAN["params_used"], "plan": PLAN, "seed": 11}
        avec = sim.run_scenario(params, 3, tous)
        sans = sim.run_scenario(params, 3, sans_brigade)
        self.assertNotIn("error", avec)
        self.assertNotIn("error", sans)
        self.assertNotEqual(avec["indicateurs"]["brigade"], sans["indicateurs"]["brigade"])
        self.assertEqual(
            sim.run_scenario(params, 3, sans_brigade)["indicateurs"],
            sans["indicateurs"],
            "Retirer un acteur doit rester reproductible pour une même graine",
        )

    def test_simulation_acteurs_depends_on_plan(self):
        """Le chemin à quatre acteurs lit aussi unserved et totals du plan."""
        tous = {nom: True for nom in ("menages", "pre_collecteurs", "brigade", "mairie")}
        points = [{"id": "c1", "lat": 12.3, "lon": -1.5, "type": "center", "demand_kg": 100}]
        plan_a = {
            "plan_id": "pA_acteurs", "collection_points": points, "routes": [], "unserved": [],
            "totals": {"cost": 1_000_000, "collected_kg": 120_000,
                       "points_served": 1, "points_unserved": 0},
        }
        plan_b = {
            "plan_id": "pB_acteurs", "collection_points": points, "routes": [],
            "unserved": [{"point_id": "c1", "reason": "capacity"}],
            "totals": {"cost": 5_000_000, "collected_kg": 20_000,
                       "points_served": 0, "points_unserved": 1},
        }
        a = sim.run_scenario(
            {"subscription_rate": 0.4, "tricycles": 8, "population": 100_000,
             "seed": 42, "plan": plan_a}, 3, tous)
        b = sim.run_scenario(
            {"subscription_rate": 0.4, "tricycles": 8, "population": 100_000,
             "seed": 42, "plan": plan_b}, 3, tous)
        self.assertNotIn("error", a)
        self.assertNotIn("error", b)
        self.assertNotEqual(a["cout_m_fcfa"], b["cout_m_fcfa"])
        self.assertEqual(a["cout_m_fcfa"], 1.0)
        self.assertEqual(b["cout_m_fcfa"], 5.0)
        self.assertEqual(
            [p["raison"] for p in b["points_etat"] if p["etat"] == "non_desservi"],
            ["capacity"],
        )

    def test_mairie_budget_et_flotte_modifient_le_service(self):
        tous = {nom: True for nom in ("menages", "pre_collecteurs", "brigade", "mairie")}
        base = {**PLAN["params_used"], "plan": PLAN, "seed": 5}
        pauvre = sim.run_scenario({**base, "budget": 0}, 2, tous)
        riche = sim.run_scenario({**base, "budget": 100_000_000}, 2, tous)
        self.assertNotIn("error", pauvre)
        self.assertNotIn("error", riche)
        self.assertLess(
            pauvre["indicateurs"]["mairie"]["camions_en_service"],
            riche["indicateurs"]["mairie"]["camions_en_service"],
        )


if __name__ == "__main__":
    unittest.main()
