"""Test de bout en bout dans Chromium (Playwright). Serveur requis : BASE (défaut http://localhost:9446),
lancé sur des bases de test (REEL_DB, SIM_DB, PHOTO_DIR temporaires). Captures dans SHOTS."""
import os
BASE = os.environ.get('BASE', 'http://localhost:9446')
SHOTS = os.environ.get('SHOTS', '/tmp/ouaga-shots/')
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')) + '/'
os.makedirs(SHOTS, exist_ok=True)
from playwright.sync_api import sync_playwright
SH = SHOTS + ""
INIT = "sessionStorage.setItem('ouaga.code.mairie','mairie-demo'); localStorage.setItem('ouaga.aide.vue','1');"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-webgl", "--disable-3d-apis"])
    ctx = b.new_context(viewport={"width": 1280, "height": 720}); ctx.add_init_script(INIT)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/dashboard/ville/")
    pg.wait_for_function("document.getElementById('chargement').hidden === true", timeout=120000)
    print("sans WebGL :", pg.evaluate("window.__ouaga.view.kind"), "|", pg.text_content("#bandeau-perime")[:75], "| erreurs :", errs)
    assert pg.evaluate("window.__ouaga.view.kind") == "2d" and not errs
    b.close()
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    ctx = b.new_context(viewport={"width": 1280, "height": 720}); ctx.add_init_script(INIT)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/api/scenarios", lambda r: r.fulfill(status=404, content_type="application/json", body='{"detail":"Ressource introuvable."}'))
    pg.goto(BASE + "/dashboard/ville/")
    pg.wait_for_function("document.getElementById('chargement').hidden === true", timeout=120000)
    pg.click(".onglets >> text=Historique"); pg.wait_for_selector("#onglet-historique .erreur", timeout=10000)
    print("route manquante :", pg.text_content("#onglet-historique .erreur"))
    pg.click(".onglets >> text=Sélection"); pg.click("#mode-sim"); pg.wait_for_function("window.__ouaga.sim.sim && !window.__ouaga.busy", timeout=60000)
    # Camions en pause pendant la capture : le rendu logiciel (SwiftShader) est lent sous charge.
    pg.wait_for_timeout(1500); pg.evaluate("window.__ouaga.view.setPlaying(false)"); pg.screenshot(path=SH + "qa_1280.png", timeout=120000)
    over = pg.evaluate("document.querySelector('.barre-haut').scrollHeight > 60 || document.body.scrollWidth > innerWidth")
    print("1280×720 : débordement =", over, "| erreurs :", errs)
    assert not over and not errs
    b.close()
