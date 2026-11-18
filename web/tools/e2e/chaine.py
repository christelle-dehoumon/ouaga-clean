"""Chaîne complète à travers les trois interfaces, sur le vrai serveur (BASE, bases de test) :
citoyen (téléphone) -> brigade confirme -> plan réel de la mairie -> mairie « nettoyé » -> brigade confirme le
nettoyage -> le cas disparaît de la carte (jamais supprimé), historique complet, export ouvert, absent de la simulation."""
import json
import os
import random
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://localhost:9446")
SHOTS = os.environ.get("SHOTS", "/tmp/ouaga-shots/")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.makedirs(SHOTS, exist_ok=True)
MAIRIE, BRIGADE = os.environ.get("MAIRIE_CODE", "mairie-demo"), os.environ.get("BRIGADE_CODE", "brigade-demo")
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
res = []


def ok(nom, cond, info=""):
    res.append(bool(cond))
    print(f"[{'OK ' if cond else 'KO '}] {nom} {info}")


def api(path, code=MAIRIE):
    req = urllib.request.Request(BASE + path, headers={"X-Role-Code": code})
    return json.load(urllib.request.urlopen(req))


# Un lieu neuf dans le secteur pilote (aucun cas existant à moins de 30 m).
random.seed()
lat, lon = 12.350 + random.random() * 0.035, -1.552 + random.random() * 0.035

with sync_playwright() as p:
    b = p.chromium.launch(args=GL)
    errs = []
    # 1. Citoyen
    tel = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, permissions=["geolocation"],
                        geolocation={"latitude": lat, "longitude": lon, "accuracy": 9})
    cit = tel.new_page()
    cit.on("pageerror", lambda e: errs.append(f"citoyen {e}"))
    cit.goto(BASE + "/citizen/")
    cit.wait_for_selector("#pos-etat.ok", timeout=20000)
    cit.set_input_files("#photo", os.path.join(ROOT, "tests/data/blur/car_504.jpg"))
    cit.wait_for_selector("#photo-etat.ok")
    cit.click("#envoyer")
    cit.wait_for_selector(".pastille.p-recu", timeout=30000)
    cases = [c for c in api("/api/reports?mode=reel") if abs(c["lat"] - lat) < 1e-6 and abs(c["lon"] - lon) < 1e-6]
    ok("1. citoyen : reçu par le serveur, cas à vérifier créé", len(cases) == 1 and cases[0]["statut"] == "a_verifier",
       cit.text_content("#confirmation b"))
    rid = cases[0]["id"]

    # 2. Brigade : le cas apparaît, photo floutée, confirmation.
    bri_ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    bri_ctx.add_init_script(f"sessionStorage.setItem('ouaga.code.brigade', '{BRIGADE}');")
    bri = bri_ctx.new_page()
    bri.on("pageerror", lambda e: errs.append(f"brigade {e}"))

    def brigade_open():
        bri.goto(BASE + "/brigade/")
        bri.wait_for_selector(".carte", timeout=20000)
        for i in range(bri.locator(".carte").count()):
            bri.locator(".carte").nth(i).click()
            bri.wait_for_selector("#detail:not([hidden])")
            if f"{lat:.5f}, {lon:.5f}" in bri.text_content("#detail-infos"):
                return True
            bri.click("#retour")
        return False

    found = brigade_open()
    bri.wait_for_function("document.querySelector('#detail-photo').src.startsWith('blob:')", timeout=20000)
    ok("2. brigade : cas reçu avec sa photo floutée", found, bri.text_content("#detail-titre"))
    bri.click("#confirmer")
    bri.click(".modal .btn-primary")
    bri.wait_for_selector(".toast-ok", timeout=15000)
    ok("   brigade : confirmé", any(c["id"] == rid and c["statut"] == "confirme" for c in api("/api/reports?mode=reel")))

    # 3. Mairie : épingle rouge dans la ville, plan réel qui inclut ce dépotoir, « nettoyé ».
    pc = b.new_context(viewport={"width": 1440, "height": 900})
    pc.add_init_script(f"sessionStorage.setItem('ouaga.code.mairie', '{MAIRIE}'); localStorage.setItem('ouaga.aide.vue', '1');")
    mai = pc.new_page()
    mai.on("pageerror", lambda e: errs.append(f"mairie {e}"))
    mai.goto(BASE + "/dashboard/?vue=ville3d")   # ville Three.js (la redirection garde les paramètres)
    mai.wait_for_function("document.getElementById('chargement').hidden === true", timeout=120000)
    mai.wait_for_function(f"window.__ouaga.reports.some(r => r.id === '{rid}')", timeout=30000)
    mai.click("text=Calculer le plan réel")
    mai.wait_for_function("window.__ouaga.plan.reel && !window.__ouaga.busy", timeout=60000)
    in_plan = mai.evaluate(f"window.__ouaga.plan.reel.consolidation_points.some(p => p.id === 'd_{rid}')")
    ok("3. mairie : le dépotoir confirmé entre dans le plan réel", in_plan, mai.text_content("#statut-plan"))
    mai.evaluate("window.__ouaga.view.setPlaying(false)")   # un camion animé ne doit pas passer devant l'épingle
    mai.evaluate(f"""() => {{ const v = window.__ouaga.view; const pin = v.layers.groups.signalements.children.find(o => o.userData.data.id === '{rid}');
      v.rig.controls.target.set(pin.position.x, 0, pin.position.z); v.scene.camera.position.set(pin.position.x + 80, 100, pin.position.z + 80); window.__pin = pin; }}""")
    mai.wait_for_timeout(2500)   # rendu logiciel lent : laisser la caméra et le rendu se stabiliser avant de viser l'épingle
    xy = mai.evaluate("""() => { const v = window.__ouaga.view, pin = window.__pin; const w = pin.position.clone(); w.y = 12 * pin.scale.y;
      w.project(v.scene.camera); const r = document.querySelector('#scene').getBoundingClientRect();
      return [r.left + (w.x + 1) / 2 * r.width, r.top + (1 - w.y) / 2 * r.height]; }""")
    mai.evaluate("document.getElementById('toasts')?.remove()")
    mai.mouse.click(xy[0], xy[1])
    try:
        mai.wait_for_selector("#onglet-selection >> text=Marquer nettoyé", timeout=10000)
    except Exception:
        print("fiche obtenue :", mai.text_content("#onglet-selection")[:200])
        raise
    ok("   mairie : clic sur l'épingle -> fiche « Dépotoir confirmé »", rid in mai.text_content("#onglet-selection .sous"))
    mai.click("#onglet-selection >> text=Marquer nettoyé")
    mai.click(".modal .btn-primary")
    mai.wait_for_selector(".toast-ok", timeout=15000)
    mai.screenshot(path=SHOTS + "chaine_mairie.png", timeout=120000)   # camions déjà en pause ; rendu logiciel lent

    # 4. Brigade : vérifie le nettoyage et confirme.
    found = brigade_open()
    ok("4. brigade : « Nettoyage à vérifier » reçu", found and "Nettoyage" in bri.text_content("#detail-titre"), bri.text_content("#detail-titre"))
    bri.click("#confirmer")
    bri.click(".modal .btn-primary")
    bri.wait_for_selector(".toast-ok", timeout=15000)

    # 5. Mairie : disparu de la carte, jamais supprimé, historique complet.
    mai.reload()
    mai.wait_for_function("document.getElementById('chargement').hidden === true", timeout=120000)
    mai.wait_for_function("window.__ouaga.reports.length > 0", timeout=30000)
    gone = mai.evaluate(f"!window.__ouaga.reports.some(r => r.id === '{rid}') && !window.__ouaga.view.layers.groups.signalements.children.some(o => o.userData.data.id === '{rid}')")
    kept = [c for c in api("/api/reports?mode=reel&inclure_nettoyes=1") if c["id"] == rid]
    ok("5. nettoyé : absent de la carte, toujours en base", gone and kept and kept[0]["statut"] == "nettoye")
    hist = api(f"/api/reports/{rid}/history")
    ok("   historique : une ligne par transition (qui, quand)",
       [(h["qui"], h["action"]) for h in hist] == [("citoyen", "creation"), ("brigade", "confirmer"), ("mairie", "marquer_nettoye"), ("brigade", "confirmer")],
       str([(h["qui"], h["action"]) for h in hist]))
    fc = api("/api/export/reports.geojson")
    ok("   export ouvert : présent, sans photo, licence", any(f["properties"]["id"] == rid for f in fc["features"]) and fc["license"].startswith("ODbL"))
    ok("   simulation : le cas réel n'y apparaît jamais", not any(c["id"] == rid for c in api("/api/reports?mode=sim")))
    ok("aucune erreur JavaScript", not errs, str(errs[:3]))
    b.close()
print(f"{sum(res)}/{len(res)} vérifications OK")
sys.exit(0 if all(res) else 1)
