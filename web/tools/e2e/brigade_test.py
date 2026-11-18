"""Test de bout en bout dans Chromium (Playwright). Serveur requis : BASE (défaut http://localhost:9446),
lancé sur des bases de test (REEL_DB, SIM_DB, PHOTO_DIR temporaires). Captures dans SHOTS."""
import os
BASE = os.environ.get('BASE', 'http://localhost:9446')
SHOTS = os.environ.get('SHOTS', '/tmp/ouaga-shots/')
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')) + '/'
os.makedirs(SHOTS, exist_ok=True)
import base64, json, random, urllib.request, urllib.error
from playwright.sync_api import sync_playwright
B = BASE
SHOT = SHOTS + "brigade_detail.png"


def api(method, path, body=None, code="mairie-demo"):
    req = urllib.request.Request(B + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Role-Code": code, "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        return {"http": e.code}


photo = base64.b64encode(open(ROOT + "tests/data/blur/car_lada.jpg", "rb").read()).decode()
random.seed()
for i in range(4):  # cas frais, éloignés les uns des autres
    api("POST", "/api/reports", {"lat": 12.35 + random.random() * 0.03, "lon": -1.55 + random.random() * 0.03, "photo_b64": photo})

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/brigade/")
    pg.fill(".modal input", "faux-code")
    pg.click(".modal button[type=submit]")
    pg.wait_for_selector(".toast-erreur", timeout=10000)
    pg.wait_for_selector(".modal input", timeout=10000)
    print("1 code faux     :", pg.text_content(".toast-erreur"), "-> code redemandé")
    pg.fill(".modal input", "brigade-demo")
    pg.click(".modal button[type=submit]")
    pg.wait_for_selector(".carte", timeout=15000)
    print("2 liste         :", pg.locator(".carte").count(), "cas |", pg.text_content("#etat"))
    pg.locator(".carte").first.click()
    pg.wait_for_function("document.querySelector('#detail-photo').src.startsWith('blob:')", timeout=15000)
    print("3 détail        :", pg.text_content("#detail-titre"), "| photo :", pg.text_content("#photo-etat"))
    pg.wait_for_timeout(500)
    pg.screenshot(path=SHOT)
    before = pg.locator(".carte").count()
    pg.click("#confirmer")
    pg.click(".modal .btn-primary")
    pg.wait_for_selector(".toast-ok", timeout=10000)
    print("4 confirmation  :", pg.text_content(".toast-ok"), "| cartes :", before, "->", pg.locator(".carte").count())
    ctx.set_offline(True)
    pg.wait_for_timeout(300)
    pg.locator(".carte").first.click()
    pg.wait_for_selector("#detail:not([hidden])")
    pg.click("#rejeter")
    pg.click(".modal .btn-danger")
    pg.wait_for_selector("#attente:not([hidden])", timeout=10000)
    print("5 hors ligne    :", pg.text_content("#attente"))
    ctx.set_offline(False)
    pg.wait_for_function("document.querySelector('#attente').hidden", timeout=20000)
    print("6 synchronisé   :", pg.locator(".toast").last.text_content(), "| cartes :", pg.locator(".carte").count())
    first = api("GET", "/api/reports?mode=reel", code="brigade-demo")[0]["id"]
    pg.locator(f".carte").first.click()
    pg.wait_for_selector("#detail:not([hidden])")
    shown = pg.evaluate("() => document.querySelector('#detail-titre').textContent")
    other = api("POST", f"/api/reports/{first}/decision", {"action": "confirmer"}, code="brigade-demo")
    print("   traité ailleurs entre-temps :", other.get("statut"))
    pg.click("#confirmer")
    pg.click(".modal .btn-primary")
    pg.wait_for_selector(".toast-erreur", timeout=10000)
    print("7 conflit       :", pg.locator(".toast-erreur").last.text_content())
    print("erreurs JS      :", errs)
    b.close()
