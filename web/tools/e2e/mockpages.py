"""Test de bout en bout dans Chromium (Playwright). Serveur requis : BASE (défaut http://localhost:9446),
lancé sur des bases de test (REEL_DB, SIM_DB, PHOTO_DIR temporaires). Captures dans SHOTS."""
import os
BASE = os.environ.get('BASE', 'http://localhost:9446')
SHOTS = os.environ.get('SHOTS', '/tmp/ouaga-shots/')
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')) + '/'
os.makedirs(SHOTS, exist_ok=True)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, geolocation={"latitude": 12.36, "longitude": -1.53, "accuracy": 8}, permissions=["geolocation"])
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/citizen/?mock=1"); pg.wait_for_selector("#pos-etat.ok")
    pg.set_input_files("#photo", ROOT + "tests/data/blur/street1.jpg"); pg.wait_for_selector("#photo-etat.ok")
    pg.click("#envoyer"); pg.wait_for_selector("#confirmation:not([hidden])")
    print("citoyen démo :", pg.text_content("#bandeau-demo"), "|", pg.text_content("#confirmation b"), "| erreurs :", errs)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/brigade/?mock=1"); pg.wait_for_selector(".carte", timeout=15000)
    print("brigade démo :", pg.text_content("#bandeau-demo"), "|", pg.locator(".carte").count(), "cas | erreurs :", errs)
    b.close()
