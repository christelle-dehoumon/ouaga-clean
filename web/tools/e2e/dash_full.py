"""Test de bout en bout dans Chromium (Playwright). Serveur requis : BASE (défaut http://localhost:9446),
lancé sur des bases de test (REEL_DB, SIM_DB, PHOTO_DIR temporaires). Captures dans SHOTS."""
import os
BASE = os.environ.get('BASE', 'http://localhost:9446')
SHOTS = os.environ.get('SHOTS', '/tmp/ouaga-shots/')
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')) + '/'
os.makedirs(SHOTS, exist_ok=True)
import base64, json, sys, time, urllib.request
from playwright.sync_api import sync_playwright

B = BASE
SH = SHOTS + ""
RESULTS = []


def ok(name, cond, info=""):
    RESULTS.append((name, bool(cond)))
    print(f"[{'OK ' if cond else 'KO '}] {name} {info}")


def api(method, path, body=None, code="mairie-demo"):
    req = urllib.request.Request(B + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Role-Code": code, "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        return {"http": e.code}


# Données réelles : un cas rejeté, un confirmé, un écarté.
photo = base64.b64encode(open(ROOT + "tests/data/blur/street1.jpg", "rb").read()).decode()
import random
for k in range(2):
    api("POST", "/api/reports", {"lat": 12.36 + random.random() * 0.02, "lon": -1.54 + random.random() * 0.02, "photo_b64": photo})
api("POST", "/api/reports", {"lat": 12.37, "lon": -1.53, "photo_b64": photo, "reported_at": "2099-01-01T00:00:00Z"})
cases = api("GET", "/api/reports", code="brigade-demo")
api("POST", f"/api/reports/{cases[0]['id']}/decision", {"action": "confirmer"}, code="brigade-demo")
api("POST", f"/api/reports/{cases[1]['id']}/decision", {"action": "rejeter"}, code="brigade-demo")

PROJ = """(lat, lon) => { const v = window.__ouaga.view; const p = v.proj.toLocal(lat, lon);
  const THREE_V = v.scene.camera.position.clone(); const w = THREE_V.set(p.x, 2, p.z).project(v.scene.camera);
  const r = document.querySelector('#scene').getBoundingClientRect();
  return [r.left + (w.x + 1) / 2 * r.width, r.top + (1 - w.y) / 2 * r.height]; }"""

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("sessionStorage.setItem('ouaga.code.mairie','mairie-demo'); localStorage.setItem('ouaga.aide.vue','1');")
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(f"PAGE {e}"))
    pg.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and errs.append(f"CONSOLE {m.text}"))
    t0 = time.time()
    pg.goto(B + "/dashboard/ville/")
    pg.wait_for_function("document.getElementById('chargement').hidden === true", timeout=120000)
    ok("chargement 3D", pg.evaluate("window.__ouaga.view.kind") == "3d", f"{time.time() - t0:.1f} s (rendu logiciel SwiftShader)")

    # --- Réel -----------------------------------------------------------------------------------
    pg.wait_for_timeout(1500)
    n_pins = pg.evaluate("window.__ouaga.view.layers.groups.signalements.children.length")
    ok("réel : signalements dans la ville", n_pins == pg.evaluate("window.__ouaga.reports.length") and n_pins > 0, f"{n_pins} épingles")
    pg.locator("#panneau-gauche .liste li", has_text="Dépotoir confirmé").first.click()
    pg.wait_for_selector("#onglet-selection h2")
    pg.wait_for_function("document.querySelector('#onglet-selection img') && document.querySelector('#onglet-selection img').src.startsWith('blob:')", timeout=15000)
    ok("réel : fiche + photo floutée + historique", "Dépotoir confirmé" in pg.text_content("#onglet-selection h2"),
       pg.locator("#onglet-selection .histo li").first.text_content())
    pg.click("text=Marquer nettoyé"); pg.click(".modal .btn-primary"); pg.wait_for_selector(".toast-ok", timeout=15000)
    ok("réel : marquer nettoyé", "Nettoyage à vérifier" in pg.text_content(".toast-ok"), pg.text_content(".toast-ok"))
    pg.locator("#panneau-gauche .filtre", has_text="Rejetés").click() if not pg.locator("#panneau-gauche .liste li", has_text="Signalement rejeté").count() else None
    pg.locator("#panneau-gauche .liste li", has_text="Signalement rejeté").first.click()
    pg.click("#onglet-selection >> text=Remettre à vérifier"); pg.click(".modal .btn-primary")
    pg.wait_for_function("[...document.querySelectorAll('.toast-ok')].some(t => t.textContent.includes('Dépotoir à vérifier'))", timeout=15000)
    ok("réel : remettre à vérifier (rejeté)", True)
    n_ec = len(api("GET", "/api/ecartes"))
    pg.click("#panneau-gauche >> text=Remettre"); pg.click(".modal .btn-primary"); pg.wait_for_timeout(1500)
    ok("réel : écarté remis à vérifier", len(api("GET", "/api/ecartes")) == n_ec - 1, f"{n_ec} -> {len(api('GET', '/api/ecartes'))}")
    pg.click("text=Calculer le plan réel")
    pg.wait_for_function("window.__ouaga.plan.reel", timeout=60000)
    ok("réel : plan réel calculé", "Plan" in pg.text_content("#statut-plan"), pg.text_content("#statut-plan"))
    pg.screenshot(path=SH + "full_reel.png")

    # --- Simulation --------------------------------------------------------------------------------
    pg.click("#mode-sim")
    pg.wait_for_function("window.__ouaga.sim.sim && !window.__ouaga.busy", timeout=120000)
    ok("sim : bandeau", "SIMULATION — DONNÉES FICTIVES" in pg.text_content("#bandeau-mode"))
    ok("sim : réel non affiché", pg.evaluate("window.__ouaga.view.layers.groups.signalements.children.every(o => o.userData.data.source === 'sim')"))
    plan0 = pg.evaluate("window.__ouaga.plan.sim.plan_id")
    pg.click("#onglet-comparer") if False else None
    pg.click(".onglets >> text=Comparer A/B"); pg.click("text=Fixer le plan affiché comme A")
    # Curseur : 5 camions
    pg.evaluate("""() => { const i = [...document.querySelectorAll('#panneau-gauche input[type=range]')].find(x => x.getAttribute('aria-label').startsWith('Camions'));
      i.value = 6; i.dispatchEvent(new Event('input', { bubbles: true })); }""")
    pg.wait_for_function(f"window.__ouaga.plan.sim.plan_id !== '{plan0}' && !window.__ouaga.busy", timeout=60000)
    ok("sim : curseur -> recalcul (différé)", pg.evaluate("window.__ouaga.plan.sim.params_used.trucks") == 6, pg.text_content("#statut-plan"))
    # Panne d'un camion du plan
    truck = pg.evaluate("window.__ouaga.plan.sim.vehicles.find(v => v.trips.length).id")
    pg.select_option("#panneau-gauche select >> nth=0", truck)
    plan1 = pg.evaluate("window.__ouaga.plan.sim.plan_id")
    t1 = time.time()
    pg.click("text=Déclarer la panne")
    pg.wait_for_function(f"window.__ouaga.plan.sim.plan_id !== '{plan1}' && !window.__ouaga.busy", timeout=60000)
    st = pg.evaluate("[window.__ouaga.plan.sim.mode, window.__ouaga.plan.sim.compute_ms, window.__ouaga.plan.sim.postponed.length, window.__ouaga.plan.sim.vehicles.find(v => v.id === '%s').status]" % truck)
    ok("sim : panne -> recalcul partiel < 5 s", st[0] == "partiel" and st[1] < 5000 and st[3] == "en panne",
       f"mode {st[0]}, serveur {st[1]} ms, mur {time.time() - t1:.1f} s, reportés {st[2]} | {pg.text_content('#statut-plan')}")
    beacon = pg.evaluate("(() => { const t = window.__ouaga.view.fleet.trucks.get('%s'); return [t.broken, t.object.userData.beacon !== undefined]; })()" % truck)
    ok("sim : camion en panne immobilisé (feux)", beacon[0] and beacon[1])
    # Pluie
    plan2 = pg.evaluate("window.__ouaga.plan.sim.plan_id")
    pg.click("text=Déclencher la saison des pluies")
    pg.wait_for_function(f"window.__ouaga.plan.sim.plan_id !== '{plan2}' && !window.__ouaga.busy", timeout=60000)
    ok("sim : pluie", pg.evaluate("window.__ouaga.plan.sim.params_used.rainy_season") is True
       and pg.evaluate("window.__ouaga.view.scene.scene.children.some(c => c.type === 'LineSegments' && c.visible)"), pg.text_content("#statut-plan"))
    pg.click(".onglets >> text=Comparer A/B"); pg.click("text=Fixer le plan affiché comme B")
    pg.click("text=Comparer A et B"); pg.wait_for_selector("#onglet-comparer table", timeout=20000)
    ok("A/B : tableau et explication", pg.locator("#onglet-comparer tbody tr").count() >= 4, pg.text_content("#onglet-comparer .texte-comparaison")[:220])
    pg.screenshot(path=SH + "full_ab.png")
    # Nouveau quartier
    pts_before = pg.evaluate("window.__ouaga.plan.sim.consolidation_points.length")
    pg.select_option("#panneau-gauche select >> nth=1", "kalgodin")
    plan3 = pg.evaluate("window.__ouaga.plan.sim.plan_id")
    pg.click("text=Ajouter au scénario")
    pg.wait_for_function(f"window.__ouaga.plan.sim.plan_id !== '{plan3}' && !window.__ouaga.busy", timeout=60000)
    pts_after = pg.evaluate("window.__ouaga.plan.sim.consolidation_points.length")
    ok("sim : nouveau quartier (Kalgodin)", pts_after > pts_before, f"{pts_before} -> {pts_after} points")
    pg.wait_for_timeout(1800)
    pg.screenshot(path=SH + "full_quartier.png")
    # Ajout d'un dépotoir par clic au sol
    pg.click("text=Ajouter un dépotoir")
    pg.mouse.click(860, 470)
    pg.wait_for_function("window.__ouaga.simDumps.length >= 1 && !window.__ouaga.busy", timeout=60000)
    pg.wait_for_function("window.__ouaga.plan.sim.consolidation_points.some(p => p.type === 'dumpsite')", timeout=60000)
    ok("sim : dépotoir ajouté au clic -> dans le plan", True, str(pg.evaluate("window.__ouaga.simDumps[0].id")))
    # Coupure de route : cliquer sur une route proche de la cible.
    xy = pg.evaluate("""() => { const v = window.__ouaga.view; const t = v.rig.controls.target;
      const r = v.city.roads.filter(r => r.truck).map(r => [r, Math.hypot(r.pts[0][0]-t.x, r.pts[0][1]-t.z)]).sort((a,b)=>a[1]-b[1])[0][0];
      const m = r.pts[Math.floor(r.pts.length/2)], n = r.pts[Math.floor(r.pts.length/2) - 1] || r.pts[0];
      const x = (m[0]+n[0])/2, z = (m[1]+n[1])/2; const w = v.scene.camera.position.clone().set(x, 0.1, z).project(v.scene.camera);
      const b = document.querySelector('#scene').getBoundingClientRect(); window.__road = r.id;
      return [b.left + (w.x+1)/2*b.width, b.top + (1-w.y)/2*b.height]; }""")
    pg.click("text=Couper une route")
    pg.mouse.click(xy[0], xy[1])
    pg.wait_for_selector("#onglet-selection >> text=Couper cette route", timeout=10000)
    plan4 = pg.evaluate("window.__ouaga.plan.sim.plan_id")
    pg.click("#onglet-selection >> text=Couper cette route")
    pg.wait_for_function(f"window.__ouaga.plan.sim.plan_id !== '{plan4}' && !window.__ouaga.busy", timeout=60000)
    cuts = pg.evaluate("window.__ouaga.plan.sim.cut_roads.map(c => c.edge_id)")
    ok("sim : route coupée (clic sur la route) -> plan", len(cuts) >= 1, f"{cuts[:2]} | barrière dans la scène : {pg.evaluate('window.__ouaga.view.layers.groups.coupures.children.length')}")
    # Clic sur un camion en service : jusqu'à trois camions, point visé contrôlé (dans la ville, sur le canevas).
    pg.evaluate("window.__ouaga.view.setPlaying(false); window.__ouaga.view.rig.flight = null")
    picked = None
    for k in range(3):
        pg.evaluate("""(k) => { const v = window.__ouaga.view; const b = v.city.bounds;
          const ts = [...v.fleet.trucks.values()].filter(t => !t.broken && t.pts.length > 1 && t.object.position.x > b.minX + 200
            && t.object.position.x < b.maxX - 200 && t.object.position.z > b.minZ + 200 && t.object.position.z < b.maxZ - 200);
          const t = ts[k % ts.length]; v.rig.controls.target.set(t.object.position.x, 0, t.object.position.z);
          v.scene.camera.position.set(t.object.position.x + 50, 60, t.object.position.z + 50); window.__truck = t.object.userData.id; }""", k)
        pg.wait_for_timeout(800)
        xy = pg.evaluate("""() => { const v = window.__ouaga.view; const o = v.fleet.get(window.__truck); const w = o.position.clone(); w.y = 2 * o.scale.y; w.project(v.scene.camera);
          const b = document.querySelector('#scene').getBoundingClientRect(); return [b.left + (w.x+1)/2*b.width, b.top + (1-w.y)/2*b.height]; }""")
        pg.evaluate("document.getElementById('toasts')?.remove()")
        top = pg.evaluate(f"(document.elementFromPoint({xy[0]}, {xy[1]}) || {{}}).tagName")
        if top != "CANVAS":
            continue
        pg.mouse.click(xy[0], xy[1])
        pg.wait_for_timeout(500)
        if "Camion" in (pg.text_content("#onglet-selection h2") or ""):
            picked = window_truck = pg.evaluate("window.__truck")
            break
    ok("3D : clic sur un camion -> fiche", picked is not None, pg.text_content("#onglet-selection .sous"))
    pg.screenshot(path=SH + "full_camion.png")
    # Clic sur un quartier
    pg.evaluate("window.__ouaga.view.focusTerritory('paglayiri')")
    pg.wait_for_timeout(1800)
    xy = pg.evaluate("""() => { const v = window.__ouaga.view; const t = v.city.territories.find(t => t.id === 'paglayiri');
      const w = v.scene.camera.position.clone().set(t.center.x, 0, t.center.z).project(v.scene.camera); const b = document.querySelector('#scene').getBoundingClientRect();
      return [b.left + (w.x+1)/2*b.width, b.top + (1-w.y)/2*b.height]; }""")
    pg.mouse.click(xy[0], xy[1])
    pg.wait_for_timeout(500)
    ok("3D : clic sur un quartier -> fiche", "Paglayiri" in pg.text_content("#onglet-selection h2"), pg.text_content("#onglet-selection dl")[:120])
    # Historique
    pg.click(".onglets >> text=Historique"); pg.wait_for_selector("#onglet-historique .bloc", timeout=15000)
    ok("historique : liste des calculs", pg.locator("#onglet-historique .bloc").count() >= 5, f"{pg.locator('#onglet-historique .bloc').count()} entrées")
    # Échec du recalcul : réseau coupé pour /api/plans
    good = pg.evaluate("window.__ouaga.plan.sim.plan_id")
    pg.route("**/api/plans", lambda route: route.abort())
    pg.click("#panneau-gauche >> text=Recalculer")
    pg.wait_for_selector("#bandeau-perime:not([hidden])", timeout=20000)
    ok("échec réseau : plan précédent gardé, marqué périmé", pg.evaluate("window.__ouaga.plan.sim.plan_id") == good,
       pg.text_content("#statut-plan") + " | " + pg.text_content("#bandeau-perime")[:80])
    pg.unroute("**/api/plans")
    pg.route("**/api/plans", lambda route: route.fulfill(status=200, content_type="application/json", body="{}"))
    pg.click("#panneau-gauche >> text=Recalculer"); pg.wait_for_timeout(1500)
    ok("réponse vide : refusée, plan gardé", pg.evaluate("window.__ouaga.plan.sim.plan_id") == good, pg.text_content("#bandeau-perime")[:90])
    pg.unroute("**/api/plans")
    pg.click("#panneau-gauche >> text=Recalculer")
    pg.wait_for_function("document.querySelector('#bandeau-perime').hidden", timeout=60000)
    ok("retour à la normale après un échec", True, pg.text_content("#statut-plan"))
    perf = pg.evaluate("window.__ouaga.view.frameMs()")
    print(f"temps CPU par image (rendu logiciel) : {perf:.1f} ms")
    ok("aucune erreur JavaScript", not errs, str(errs[:5]))
    b.close()
print(f"\n{sum(r for _, r in RESULTS)}/{len(RESULTS)} vérifications OK")
sys.exit(0 if all(r for _, r in RESULTS) else 1)
