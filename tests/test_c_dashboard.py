"""Contrat UI du membre C : unités du KPI, couleurs et icônes locales.

Test statique du tableau de bord mono-fichier : il verrouille les points qui
ont déjà causé une confusion entre proxy de ménages synthétiques et dépotoirs
réels, sans dépendre d'un navigateur.
"""
from __future__ import annotations

import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
INDEX = (RACINE / "web" / "dashboard" / "index.html").read_text(encoding="utf-8")


class DashboardContratTest(unittest.TestCase):
    def test_unite_proxy_affichee_sur_le_kpi(self):
        self.assertIn("Dépôts non collectés (proxy)", INDEX)
        self.assertIn("ménages synthétiques", INDEX)
        self.assertNotIn(">Dépotoirs restants<", INDEX)

    def test_compteur_initial_ne_reutilise_pas_les_points_de_regroupement(self):
        self.assertIn("document.getElementById('k-depots').textContent='—';", INDEX)
        self.assertNotIn("k-depots').textContent=c.points_non_desservis", INDEX)
        self.assertNotIn("k-depots').textContent=plan.points_regroupement", INDEX)

    def test_sortie_simulation_porte_l_unite_du_modele(self):
        self.assertIn("s.unite_depotoirs_restants", INDEX)
        self.assertIn("document.getElementById('k-depots').title=unite;", INDEX)

    def test_couleurs_contrat_et_iconographie_locale(self):
        self.assertIn("#EF2B2D", INDEX)  # camions
        self.assertIn("#009E49", INDEX)  # tricycles
        self.assertIn('<symbol id="i-truck"', INDEX)
        self.assertIn('<symbol id="i-bike"', INDEX)
        self.assertNotIn("unpkg.com/feather", INDEX)
        self.assertNotIn("cdn.jsdelivr.net/npm/@fortawesome", INDEX)

    def test_aucun_emoji_dans_le_dashboard(self):
        emojis = [
            ch for ch in INDEX
            if 0x1F300 <= ord(ch) <= 0x1FAFF
            or 0x2600 <= ord(ch) <= 0x27BF
            or 0xFE0F == ord(ch)
        ]
        self.assertEqual(emojis, [], "Emojis résiduels dans index.html")

    def test_routes_du_pont_sont_cellles_attendues(self):
        for route in (
            "/api/plan/calculer", "/api/signalements", "/api/signalements/bulk",
            "/api/plans/", "/api/scenarios/compare", "/api/scenarios",
            "/api/exports/osm",
        ):
            with self.subTest(route=route):
                self.assertIn(route, INDEX)


if __name__ == "__main__":
    unittest.main()
