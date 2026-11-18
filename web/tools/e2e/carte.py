"""Vue par défaut du tableau de bord : la carte MapLibre de toute l'agglomération (tuiles vectorielles OSM
auto-hébergées). Serveur requis : BASE (bases de test). Captures dans SHOTS.
Parcours : signalements sur la carte, fiche depuis la liste et depuis la carte, plan réel, simulation (camions,
tournées, clic sur un camion, panne, pluie, vue immersive), coupure d'une route, recherche d'un lieu, fiche d'un
bâtiment OSM, ambiance de nuit. Sans tuiles (clone neuf, ./scripts/fabriquer_tuiles.sh non lancé) : ignoré."""
import base64
import json
import os
import random
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://localhost:9446")
SHOTS = os.environ.get("SHOTS", "/tmp/ouaga-shots/")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")) + "/"
os.makedirs(SHOTS, exist_ok=True)
MAIRIE, BRIGADE = os.environ.get("MAIRIE_CODE", "mairie-demo"), os.environ.get("BRIGADE_CODE", "brigade-demo")
TUILES = "/dashboard/ville/carte/data/ouagadougou.pmtiles"
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
res = []


def ok(nom, cond, info=""):
    res.append(bool(cond))
    print(f"[{'OK ' if cond else 'KO '}] {nom} {info}")


def api(methode, chemin, corps=None, code=MAIRIE):
    req = urllib.request.Request(BASE + chemin, method=methode, data=json.dumps(corps).encode() if corps is not None else None,
                                 headers={"X-Role-Code": code, "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        return {"http": e.code}


def tuiles_servies():
    """Le fichier de tuiles est-il servi ? (même requête que l'application : les 127 premiers octets)"""
    req = urllib.request.Request(BASE + TUILES, headers={"Range": "bytes=0-126"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status in (200, 206)
    except (urllib.error.HTTPError, urllib.error.URLError):
        return False


def shot(pg, nom):
    """Capture : tuiles chargées, camions en pause pendant la capture (rendu logiciel lent), état de lecture rétabli."""
    pg.wait_for_function("window.__ouaga.view.map.areTilesLoaded()", timeout=60000)
    pg.wait_for_timeout(700)
    lecture = pg.evaluate("(() => { const v = window.__ouaga.view; const l = v.fleet.playing; v.setPlaying(false); return l; })()")
    pg.screenshot(path=SHOTS + f"carte_{nom}.png", timeout=120000)
    pg.evaluate(f"window.__ouaga.view.setPlaying({'true' if lecture else 'false'})")


# Données réelles : quatre cas, dont un confirmé et un rejeté.
photo = base64.b64encode(open(ROOT + "tests/data/blur/street1.jpg", "rb").read()).decode()
for _ in range(4):
    api("POST", "/api/reports", {"lat": 12.36 + random.random() * 0.02, "lon": -1.54 + random.random() * 0.02, "photo_b64": photo})
cs = api("GET", "/api/reports", code=BRIGADE)
api("POST", f"/api/reports/{cs[0]['id']}/decision", {"action": "confirmer"}, code=BRIGADE)
api("POST", f"/api/reports/{cs[1]['id']}/decision", {"action": "rejeter"}, code=BRIGADE)

errs = []
with sync_playwright() as p:
    b = p.chromium.launch(args=GL)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(f"sessionStorage.setItem('ouaga.code.mairie', '{MAIRIE}'); localStorage.setItem('ouaga.aide.vue', '1');")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(f"PAGE {e}"))
    pg.on("console", lambda m: m.type in ("error", "warning") and errs.append(f"{m.type} {m.text[:200]}"))
    pg.goto(BASE + "/dashboard/ville/")
    pg.wait_for_function("document.getElementById('chargement').hidden === true", timeout=180000)
    genre = pg.evaluate("window.__ouaga.view.kind")
    if genre != "carte" and not tuiles_servies():
        # Couverture réduite : le tableau de bord doit le dire par un bandeau permanent.
        ok("tuiles absentes : bandeau de couverture affiché", pg.is_visible("#bandeau-couverture"),
           (pg.text_content("#bandeau-couverture") or "")[:120])
        b.close()
        if all(res):
            print(f"[SKIP] tuiles absentes ({TUILES} non servi, vue « {genre} ») : lancer ./scripts/fabriquer_tuiles.sh")
        print(f"{sum(res)}/{len(res)} vérifications OK")
        sys.exit(0 if all(res) else 1)
    ok("vue carte par défaut", genre == "carte", genre)
    if genre != "carte":   # tuiles présentes mais carte non démarrée : rien d'autre à vérifier
        b.close()
        print(f"{sum(res)}/{len(res)} vérifications OK")
        sys.exit(1)
    n = pg.evaluate("window.__ouaga.view.layers.donnees.get('op-signalements').length")
    ok("signalements réels sur la carte", n == pg.evaluate("window.__ouaga.reports.length") and n > 0, f"{n}")

    # Clic sur un signalement dans la liste -> fiche + vol de la caméra.
    pg.locator("#panneau-gauche .liste li", has_text="Dépotoir confirmé").first.click()
    pg.wait_for_selector("#onglet-selection h2")
    pg.wait_for_timeout(1800)
    ok("fiche signalement", "Dépotoir confirmé" in pg.text_content("#onglet-selection h2"))
    shot(pg, "a_signalement")

    # Clic dans la carte sur l'épingle d'un cas à vérifier.
    rid = pg.evaluate("window.__ouaga.reports.find(r => r.statut === 'a_verifier').id")
    pg.evaluate(f"(() => {{ const r = window.__ouaga.reports.find(r => r.id === '{rid}'); return window.__ouaga.view.focusLatLon(r.lat, r.lon, 300); }})()")
    pg.wait_for_timeout(2000)
    xy = pg.evaluate(f"""() => {{ const v = window.__ouaga.view, r = window.__ouaga.reports.find(r => r.id === '{rid}'); const p = v.map.project([r.lon, r.lat]);
      const b = document.querySelector('#scene').getBoundingClientRect(); return [b.left + p.x, b.top + p.y, r.id]; }}""")
    pg.mouse.click(xy[0], xy[1])
    pg.wait_for_timeout(600)
    ok("clic sur une épingle -> fiche", xy[2] in (pg.text_content("#onglet-selection .sous") or ""), pg.text_content("#onglet-selection h2"))
    pg.click("text=Calculer le plan réel")
    pg.wait_for_function("window.__ouaga.plan.reel", timeout=90000)
    ok("plan réel", "Plan" in pg.text_content("#statut-plan"), pg.text_content("#statut-plan"))

    # Simulation : camions et tournées.
    pg.click("#mode-sim")
    pg.wait_for_function("window.__ouaga.sim.sim && !window.__ouaga.busy", timeout=180000)
    nt = pg.evaluate("window.__ouaga.view.fleet.trucks.size")
    nr = pg.evaluate("window.__ouaga.view.layers.donnees.get('op-tournees').length")
    ok("sim : camions et tournées", nt > 0 and nr > 0, f"{nt} camions, {nr} tournées")
    pg.evaluate("window.__ouaga.view.overview()")
    pg.wait_for_timeout(2200)
    pg.evaluate("window.__ouaga.view.focusTerritory('pilot')")
    pg.wait_for_timeout(2200)
    shot(pg, "b_sim_secteur")

    # Clic sur un camion (animation en pause pour viser juste).
    pg.evaluate("window.__ouaga.view.setPlaying(false)")
    pos = pg.evaluate("""() => { const v = window.__ouaga.view; const t = [...v.fleet.trucks.values()].find(t => !t.idle);
      const [lat, lon] = v.proj.toLatLon(t.object.position.x, t.object.position.z); return [lat, lon, t.object.userData.id]; }""")
    pg.evaluate(f"window.__ouaga.view.focusLatLon({pos[0]}, {pos[1]}, 180)")
    pg.wait_for_timeout(2200)
    xy = pg.evaluate(f"""() => {{ const v = window.__ouaga.view; const p = v.map.project([{pos[1]}, {pos[0]}]);
      const b = document.querySelector('#scene').getBoundingClientRect(); return [b.left + p.x, b.top + p.y]; }}""")
    pg.mouse.click(xy[0], xy[1])
    pg.wait_for_timeout(600)
    ok("clic sur un camion -> fiche", "Camion" in (pg.text_content("#onglet-selection h2") or ""), pg.text_content("#onglet-selection h2"))
    shot(pg, "c_camion")

    # Panne puis saison des pluies.
    pg.click("#onglet-selection >> text=Déclarer en panne")
    pg.click(".modal .btn-danger")
    pg.wait_for_function(f"window.__ouaga.plan.sim.vehicles.find(v => v.id === '{pos[2]}').status === 'en panne' && !window.__ouaga.busy", timeout=90000)
    ok("panne -> recalcul (camion immobilisé)", pg.evaluate("window.__ouaga.view.fleet.trucks.get('%s').broken" % pos[2]),
       "mode " + str(pg.evaluate("window.__ouaga.plan.sim.mode")) + " | " + pg.text_content("#statut-plan"))
    pg.click("text=Déclencher la saison des pluies")
    pg.wait_for_function("window.__ouaga.plan.sim.params_used.rainy_season === true && !window.__ouaga.busy", timeout=90000)
    ok("pluie", pg.evaluate("document.querySelector('#scene').classList.contains('pluie-carte')"), pg.text_content("#statut-plan"))
    pg.evaluate("window.__ouaga.view.setPlaying(true)")
    pg.evaluate("window.__ouaga.view.immersive()")
    pg.wait_for_timeout(2400)
    shot(pg, "d_pluie_immersif")

    # Couper une route : mode coupure, clic sur une route du réseau camion la plus proche du centre.
    pg.evaluate("window.__ouaga.view.focusTerritory('pilot')")
    pg.wait_for_timeout(2200)
    pg.click("#panneau-gauche >> text=Couper une route")
    try:
        pg.wait_for_function("window.__ouaga.view.map.queryRenderedFeatures({ layers: ['op-reseau'] }).length > 0", timeout=15000)
    except Exception:
        print("réseau non rendu :", pg.evaluate("[window.__ouaga.interaction, window.__ouaga.view.map.getLayoutProperty('op-reseau','visibility'), window.__ouaga.view.map.getZoom()]"))
    xy = pg.evaluate("""() => { const v = window.__ouaga.view; const fs = v.map.queryRenderedFeatures({ layers: ['op-reseau'] });
      const b = document.querySelector('#scene').getBoundingClientRect(); const cx = b.width / 2, cy = b.height / 2;
      let best = null, bd = 1e9; for (const f of fs) for (const c of f.geometry.coordinates) { const p = v.map.project(c); const d = Math.hypot(p.x - cx, p.y - cy); if (d < bd) { bd = d; best = p; } }
      return best ? [b.left + best.x, b.top + best.y] : null; }""")
    if xy:
        pg.mouse.click(xy[0], xy[1])
        pg.wait_for_timeout(600)
        has = pg.locator("#onglet-selection >> text=Couper cette route").count()
        ok("coupure : clic sur une route -> fiche", has > 0, pg.text_content("#onglet-selection h2"))
        if has:
            p0 = pg.evaluate("window.__ouaga.plan.sim.plan_id")
            pg.click("#onglet-selection >> text=Couper cette route")
            pg.wait_for_function(f"window.__ouaga.plan.sim.plan_id !== '{p0}' && !window.__ouaga.busy", timeout=90000)
            ok("route coupée dans le plan", len(pg.evaluate("window.__ouaga.plan.sim.cut_roads")) >= 1,
               "tracés : " + str(pg.evaluate("window.__ouaga.view.layers.donnees.get('op-coupures').length")))
    else:
        ok("coupure : réseau visible", False)

    # Recherche d'un lieu.
    pg.fill("#recherche", "grand marche")
    pg.wait_for_timeout(400)
    items = pg.locator("#recherche-resultats li").all_text_contents()
    ok("recherche : résultats", any("Grand Marché" in t for t in items), str(items[:3]))
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(2500)
    ok("recherche : fiche du lieu", "Grand Marché" in (pg.text_content("#onglet-selection h2") or ""))
    shot(pg, "e_grand_marche")

    # Bâtiment : clic sur le bâtiment OSM le plus proche du centre de l'écran.
    pg.click("#mode-reel")
    pg.wait_for_timeout(2500)
    pg.evaluate("window.__ouaga.view.focusLatLon(12.3686, -1.5275, 140)")
    pg.wait_for_timeout(2400)
    pg.wait_for_function("window.__ouaga.view.map.areTilesLoaded()", timeout=60000)
    xy = pg.evaluate("""() => { const v = window.__ouaga.view; const fs = v.map.queryRenderedFeatures({ layers: ['batiments-3d'] });
      const b = document.querySelector('#scene').getBoundingClientRect(); const cx = b.width / 2, cy = b.height / 2;
      let best = null, bd = 1e9; for (const f of fs) { if (!f.properties.osm_id) continue; const c = f.geometry.type === 'Polygon' ? f.geometry.coordinates[0] : f.geometry.coordinates[0][0];
        const m = c.reduce((a, p) => [a[0] + p[0] / c.length, a[1] + p[1] / c.length], [0, 0]); const p = v.map.project(m); const d = Math.hypot(p.x - cx, p.y - cy);
        if (d < bd) { bd = d; best = p; } } return best ? [b.left + best.x, b.top + best.y] : null; }""")
    if xy:
        pg.mouse.click(xy[0], xy[1])
        pg.wait_for_timeout(600)
        ok("clic sur un bâtiment -> fiche OSM", "Origine de la hauteur" in (pg.text_content("#onglet-selection") or ""),
           (pg.text_content("#onglet-selection") or "")[:200])
    else:
        ok("clic sur un bâtiment -> fiche OSM", False, "aucun bâtiment OSM rendu au centre")

    # Ambiance de nuit.
    pg.select_option("#ambiance", "nuit")
    pg.wait_for_timeout(1500)
    shot(pg, "f_nuit")
    pg.select_option("#ambiance", "jour")
    print("image (ms, moyenne glissante) :", round(pg.evaluate("window.__ouaga.view.frameMs()"), 1))
    ok("aucune erreur JavaScript", not errs, str(errs[:6]))
    b.close()
print(f"{sum(res)}/{len(res)} vérifications OK")
sys.exit(0 if all(res) else 1)
