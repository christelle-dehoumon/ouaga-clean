"""Test de bout en bout dans Chromium (Playwright). Serveur requis : BASE (défaut http://localhost:9446),
lancé sur des bases de test (REEL_DB, SIM_DB, PHOTO_DIR temporaires). Captures dans SHOTS."""
import os
BASE = os.environ.get('BASE', 'http://localhost:9446')
SHOTS = os.environ.get('SHOTS', '/tmp/ouaga-shots/')
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')) + '/'
os.makedirs(SHOTS, exist_ok=True)
import json, urllib.request
from playwright.sync_api import sync_playwright
B = BASE
PHOTO = ROOT + "tests/data/blur/street1.jpg"
def cases():
    req = urllib.request.Request(B + "/api/reports?mode=reel", headers={"X-Role-Code": "mairie-demo"})
    return json.load(urllib.request.urlopen(req))
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, geolocation={"latitude": 12.3655, "longitude": -1.5312, "accuracy": 12},
                        permissions=["geolocation"], is_mobile=True, has_touch=True)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
    n0 = len(cases())
    pg.goto(B + "/citizen/"); pg.wait_for_selector("#pos-etat.ok", timeout=15000)
    print("1 position :", pg.text_content("#pos-etat"))
    pg.set_input_files("#photo", PHOTO); pg.wait_for_selector("#photo-etat.ok")
    print("2 photo    :", pg.text_content("#photo-etat"), "| bouton actif :", pg.is_enabled("#envoyer"))
    pg.click("#envoyer"); pg.wait_for_selector(".pastille.p-recu", timeout=20000)
    print("3 en ligne :", pg.text_content("#confirmation b"), "| serveur :", len(cases()) - n0, "nouveau cas")
    pg.wait_for_timeout(1500)  # le service worker met la coquille en cache
    ctx.set_offline(True); pg.wait_for_timeout(300)
    print("4 réseau   :", pg.text_content("#reseau"))
    ctx.set_geolocation({"latitude": 12.3700, "longitude": -1.5250, "accuracy": 10})
    pg.wait_for_timeout(1500)
    pg.set_input_files("#photo", ROOT + "tests/data/blur/street3.jpg"); pg.wait_for_selector("#photo-etat.ok")
    pg.click("#envoyer"); pg.wait_for_selector("#confirmation.local")
    print("5 hors ligne:", pg.text_content("#confirmation b"), "|", [t for t in pg.locator(".pastille").all_text_contents()][:2])
    pg.reload(); pg.wait_for_selector("#etape-photo")
    print("6 rechargement hors ligne : page ouverte =", pg.is_visible("#envoyer"), "| file :", pg.locator(".pastille").all_text_contents()[:2])
    ctx.set_offline(False); pg.wait_for_function("document.querySelectorAll('.pastille.p-recu').length >= 2", timeout=30000)
    print("7 retour réseau :", pg.locator(".pastille").all_text_contents()[:2], "| serveur :", len(cases()) - n0, "nouveaux cas")
    pg.screenshot(path=SHOTS + "citizen.png", full_page=True)
    ctx2 = b.new_context(viewport={"width": 390, "height": 844}); pg2 = ctx2.new_page()
    pg2.goto(B + "/citizen/"); pg2.wait_for_selector("#pos-etat.erreur", timeout=25000)
    print("8 GPS refusé :", pg2.text_content("#pos-etat"), "| bouton :", pg2.is_enabled("#envoyer"))
    print("erreurs JS :", errs)
    b.close()
