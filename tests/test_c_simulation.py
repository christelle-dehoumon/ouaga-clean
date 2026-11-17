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


if __name__ == "__main__":
    unittest.main()
