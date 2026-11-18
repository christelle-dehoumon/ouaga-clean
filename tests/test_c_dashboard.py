"""Contrat UI du membre C : architecture séparée, assets locaux, routes réelles.

Les tests statiques verrouillent les points qui ont déjà causé une confusion
entre proxy de ménages synthétiques et dépotoirs réels, sans dépendre d'un
navigateur. La nouvelle structure (index.html + dashboard.css + dashboard.js)
remplace l'ancien tableau de bord mono-fichier ; les intentions des tests sont
conservées et étendues au vrai Backend.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
DASH = RACINE / "web" / "dashboard"
INDEX = (DASH / "index.html").read_text(encoding="utf-8")
CSS = (DASH / "dashboard.css").read_text(encoding="utf-8")
JS = (DASH / "dashboard.js").read_text(encoding="utf-8")
TOUS = "\n".join((INDEX, CSS, JS))


class DashboardContratTest(unittest.TestCase):
    # --- Structure séparée et assets locaux --------------------------------
    def test_structure_separee_avec_un_seul_script_applicatif(self):
        scripts = re.findall(r"<script[^>]*src=\"([^\"]+)\"", INDEX)
        applicatifs = [s for s in scripts if "dashboard.js" in s or "app.js" in s]
        self.assertEqual(applicatifs, ["/dashboard/dashboard.js"])
        self.assertNotIn("app.js", INDEX)
        self.assertNotIn("app.css", INDEX)
        self.assertEqual(INDEX.count("<header"), 1, "Un seul en-tête autorisé")

    def test_assets_locaux_avec_chemins_absolus(self):
        for chemin in (
            "/dashboard/dashboard.css",
            "/dashboard/dashboard.js",
            "/dashboard/vendor/leaflet/leaflet.css",
            "/dashboard/vendor/leaflet/leaflet.js",
        ):
            with self.subTest(chemin=chemin):
                self.assertIn(chemin, INDEX)
        for relatif in ('href="app.css"', 'src="app.js"', 'href="vendor/', 'src="vendor/'):
            with self.subTest(relatif=relatif):
                self.assertNotIn(relatif, INDEX)

    def test_lien_citoyen_conforme_au_mount_et_lien_docs_absent_de_l_ui(self):
        self.assertIn('href="/citizen/"', INDEX)
        self.assertNotIn('href="/docs"', INDEX)

    # --- KPI : proxy, pas des dépotoirs réels -------------------------------
    def test_unite_proxy_affichee_sur_le_kpi(self):
        self.assertIn("Dépôts non collectés (proxy)", INDEX)
        self.assertIn("ménages synthétiques", INDEX)
        self.assertNotIn(">Dépotoirs restants<", INDEX)

    def test_compteur_initial_ne_reutilise_pas_les_points_de_regroupement(self):
        self.assertIn('<b id="k-depots" class="kpi-valeur">—</b>', INDEX)
        self.assertIn("totaux.points_unserved", JS)  # champ réel du plan (contrat §5)
        self.assertNotIn("points_regroupement", TOUS)
        self.assertNotIn("points_non_desservis", TOUS)

    def test_sortie_simulation_porte_l_unite_du_modele(self):
        self.assertIn("resultat.unite_depotoirs_restants", JS)
        self.assertIn("$(\"k-depots\").title = resultat.unite_depotoirs_restants", JS)

    def test_zero_dechet_affiche_un_message_jamais_cent_pourcent(self):
        self.assertIn("Aucun déchet généré", JS)
        self.assertIn("resultat.sans_dechet", JS)
        self.assertNotIn("part_ramassee * 100) + \" %\"\n  }", JS)  # garde-fou de l'ancien calcul

    # --- Couleurs, icônes, ressources externes ------------------------------
    def test_couleurs_contrat_et_iconographie_locale(self):
        self.assertIn("#EF2B2D", JS)  # camions
        self.assertIn("#009E49", JS)  # tricycles
        self.assertIn("/dashboard/icons/${nom}.svg", JS)
        self.assertIn('NOMS_ICONS = ["brigade"', JS)
        for nom in ("menage", "camion-benne", "ctvd", "point-regroupement"):
            with self.subTest(icone=nom):
                self.assertTrue((DASH / "icons" / f"{nom}.svg").exists())

    def test_aucune_ressource_externe_hors_vendor(self):
        motifs = [
            r"https?://",
            r"tile\.openstreetmap\.org",
            r"unpkg\.com",
            r"cdn\.jsdelivr\.net",
            r"fonts\.googleapis\.com",
            r"UPDATE\?nodes=",
            r"api\.openstreetmap\.org",
        ]
        for motif in motifs:
            with self.subTest(motif=motif):
                self.assertIsNone(re.search(motif, TOUS), f"Ressource externe : {motif}")
        self.assertIn("aucune tuile", INDEX.lower())

    def test_geometries_et_fond_neutre_locaux(self):
        for geo in ("zones.geojson", "water.geojson"):
            with self.subTest(geo=geo):
                self.assertIn(f"/dashboard/geo/{geo}", JS)
                self.assertTrue((DASH / "geo" / geo).exists())
        self.assertIn("#eef2ee", CSS)  # fond neutre, pas de tuile

    def test_aucun_emoji_dans_le_dashboard(self):
        emojis = [
            ch for ch in TOUS
            if 0x1F300 <= ord(ch) <= 0x1FAFF
            or 0x2600 <= ord(ch) <= 0x27BF
            or ord(ch) == 0xFE0F
        ]
        self.assertEqual(emojis, [], "Emojis résiduels dans le tableau de bord")

    # --- Routes du vrai Backend --------------------------------------------
    def test_routes_du_pont_sont_cellles_du_vrai_backend(self):
        for route in (
            '"/api/plans"',
            "/api/plans/${encodeURIComponent(ETAT.plan.plan_id)}/simulation",
            "/api/reports?limit=5000",
            "/api/reports/${encodeURIComponent(id)}/validate",
            "/api/reports/bulk",
        ):
            with self.subTest(route=route):
                self.assertIn(route, JS)
        # Anciennes routes de serveur mock : plus présentes.
        for obsolete in ("/api/plan/calculer", "/api/signalements", "/api/scenarios"):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, TOUS)

    # --- Signalements et resilience ---------------------------------------
    def test_polling_5s_avec_pause_onglet_masque(self):
        self.assertIn("5000", JS)
        self.assertIn("document.hidden", JS)
        self.assertIn("visibilitychange", JS)
        self.assertIn("ETAT.couchesSignalements", JS)

    def test_validation_brigade_avec_motif_obligatoire(self):
        self.assertIn('by: "brigade"', JS)
        self.assertIn("accept: Boolean(accept)", JS)
        self.assertIn("Le motif du rejet est obligatoire.", JS)
        self.assertIn("note: note.trim()", JS)
        self.assertIn("data-accept=\"false\"", JS)

    def test_resilience_etiquette_ancien_sans_vider_la_carte(self):
        self.assertIn("données anciennes", JS)
        self.assertIn("ancien", CSS)
        self.assertIn("showError(error, true)", JS)
        self.assertIn("ETAT.resultat) majSimulation(ETAT.resultat, true)", JS)

    # --- Accessibilité -----------------------------------------------------
    def test_tailles_et_variables_css_accessibles(self):
        self.assertIn("html { font-size: 16px; }", CSS)
        self.assertIn("font-size: 28px", CSS)
        self.assertIn("min-height: 44px", CSS)
        self.assertIn("width: 36px; height: 36px", CSS)
        self.assertIn("width: 24px; height: 24px", CSS)
        self.assertIn(":root {", CSS)
        for variable in ("--vert", "--rouge", "--jaune", "--fond", "--texte"):
            with self.subTest(variable=variable):
                self.assertIn(variable + ":", CSS)


if __name__ == "__main__":
    unittest.main()
