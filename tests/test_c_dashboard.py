"""Contrat du tableau de bord de la mairie (web/dashboard/ville/) et des pages citoyen et brigade.

Tests statiques, sans navigateur : ressources locales, routes réellement servies par l'API, étiquetage des données
fictives, rendu sûr du DOM. Les parcours dans un navigateur sont dans web/tools/e2e/ (Playwright).
Remplace l'ancien test qui figeait le tableau de bord mono-page retiré le 2026-11-18.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
WEB = RACINE / "web"
VILLE = WEB / "dashboard" / "ville"
SHARED = WEB / "dashboard" / "shared"
JS_APP = sorted([*VILLE.rglob("*.js"), *SHARED.glob("*.js"), *(WEB / "citizen").glob("*.js"), *(WEB / "brigade").glob("*.js")])


def lire(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_par_defaut_redirige_vers_la_ville_3d() -> None:
    index = lire(WEB / "dashboard" / "index.html")
    assert 'url=/dashboard/ville/' in index and 'location.replace("/dashboard/ville/"' in index


def test_page_ville_charge_un_seul_module_et_three_en_local() -> None:
    index = lire(VILLE / "index.html")
    assert re.findall(r'<script[^>]*src="([^"]+)"', index) == ["/dashboard/ville/app.js"]
    carte = json.loads(re.search(r'<script type="importmap">(.*?)</script>', index, re.S).group(1))["imports"]
    assert carte == {"three": "/dashboard/vendor/three/three.module.js", "three/addons/": "/dashboard/vendor/three/addons/"}
    for f in ("three.module.js", "addons/controls/OrbitControls.js", "LICENSE"):
        assert (WEB / "dashboard" / "vendor" / "three" / f).exists()
    assert (WEB / "dashboard" / "vendor" / "leaflet" / "leaflet.js").exists()


def test_aucune_ressource_externe_hors_fond_2d_de_secours() -> None:
    """La ville 3D ne dépend d'aucun service en ligne ; seule la vue 2D de secours charge des tuiles OSM."""
    for path in [*JS_APP, *VILLE.glob("*.html"), *VILLE.glob("*.css"), WEB / "citizen" / "index.html", WEB / "brigade" / "index.html"]:
        texte = lire(path)
        externes = re.findall(r"https?://[^\s\"'`)]+", texte)
        if path.name == "view2d.js":
            assert externes and all("openstreetmap.org" in u for u in externes)
            assert "OpenStreetMap contributors" in texte
        else:
            assert not externes, f"Ressource externe dans {path.relative_to(RACINE)} : {externes}"


def test_routes_appelees_existent_dans_l_api() -> None:
    """Chaque chemin /… appelé par shared/api.js correspond à une route réellement servie par l'API."""
    from api.main import app

    servies = [re.sub(r"\{[^}]+\}", "X", p) for p in app.openapi()["paths"] if p.startswith("/api")]
    appels = set(re.findall(r'this\.request\("(?:GET|POST)", `?"?(/[^`"?]+)', lire(SHARED / "api.js")))
    assert len(appels) >= 15
    for chemin in appels:
        normal = "/api" + re.sub(r"\$\{[^}]+\}", "X", chemin)
        assert normal in servies, f"{normal} appelé par le front mais absent de l'API"


def test_donnees_fictives_toujours_etiquetees() -> None:
    assert "SIMULATION — DONNÉES FICTIVES ET SCÉNARIOS DE TEST" in lire(VILLE / "app.js")
    assert "MODE DÉMONSTRATION — DONNÉES FICTIVES" in lire(SHARED / "ui.js")
    assert 'get("mock") === "1"' in lire(SHARED / "api.js")          # jamais de bascule automatique
    assert "isMockMode()" in lire(SHARED / "api.js")


def test_rendu_sur_et_sans_identifiant_en_dur() -> None:
    for path in JS_APP:
        texte = lire(path)
        assert ".innerHTML" not in texte, f"innerHTML dans {path.relative_to(RACINE)}"
        assert not re.search(r"""["'](truck1|saaba)["']""", texte), f"identifiant en dur dans {path.relative_to(RACINE)}"


def test_aucun_emoji_dans_les_interfaces() -> None:
    for path in [*JS_APP, *WEB.rglob("*.html"), *WEB.rglob("*.css")]:
        if "vendor" in path.parts:
            continue
        emojis = [c for c in lire(path) if 0x1F300 <= ord(c) <= 0x1FAFF or 0x2600 <= ord(c) <= 0x27BF or ord(c) == 0xFE0F]
        assert not emojis, f"emoji dans {path.relative_to(RACINE)}"


def test_donnees_de_la_ville_sourcees() -> None:
    meta = json.loads(lire(VILLE / "data" / "city.json"))["meta"]
    assert meta["counts"]["buildings"] > 1000 and meta["counts"]["roads"] > 1000
    licences = {s["license"] for s in meta["sources"]}
    assert "ODbL-1.0" in licences
    assert any("estimation" in s["source"] for s in meta["sources"])          # hauteurs estimées déclarées
    assert "OpenStreetMap" in lire(VILLE / "app.js")                           # crédit affiché


@pytest.mark.parametrize("page", ["citizen", "brigade"])
def test_pages_mobiles_partagent_la_couche_api(page: str) -> None:
    js = lire(WEB / page / f"{page}.js")
    assert 'from "/dashboard/shared/api.js"' in js and "queue" in js
