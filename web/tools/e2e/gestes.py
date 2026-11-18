"""Gestes du jury non couverts par dash_full.py : /dashboard/ redirige vers la ville 3D, clic sur une épingle de
signalement DANS la ville (pas dans la liste), bouton « Rouvrir » de l'historique. Serveur : BASE (bases de test)."""
import os

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://localhost:9446")
SHOTS = os.environ.get("SHOTS", "/tmp/ouaga-shots/")
os.makedirs(SHOTS, exist_ok=True)
INIT = "sessionStorage.setItem('ouaga.code.mairie','mairie-demo'); localStorage.setItem('ouaga.aide.vue','1');"
res = []


def ok(nom, cond, info=""):
    res.append(bool(cond))
    print(f"[{'OK ' if cond else 'KO '}] {nom} {info}")


with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(INIT)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/dashboard/")
    pg.wait_for_url("**/dashboard/ville/**", timeout=15000)
    ok("/dashboard/ redirige vers la ville 3D", "/dashboard/ville/" in pg.url, pg.url)
    pg.wait_for_function("document.getElementById('chargement').hidden === true", timeout=120000)
    pg.wait_for_function("window.__ouaga.reports.length > 0", timeout=30000)
    # Caméra au-dessus d'une épingle, puis clic sur l'épingle dans la scène 3D.
    rid = pg.evaluate("""() => { const v = window.__ouaga.view; const pin = v.layers.groups.signalements.children[0];
      v.rig.controls.target.set(pin.position.x, 0, pin.position.z);
      v.scene.camera.position.set(pin.position.x + 90, 110, pin.position.z + 90); window.__pin = pin; return pin.userData.data.id; }""")
    pg.wait_for_timeout(900)
    xy = pg.evaluate("""() => { const v = window.__ouaga.view, pin = window.__pin; const w = pin.position.clone();
      w.y = 12 * pin.scale.y; w.project(v.scene.camera); const r = document.querySelector('#scene').getBoundingClientRect();
      return [r.left + (w.x + 1) / 2 * r.width, r.top + (1 - w.y) / 2 * r.height]; }""")
    pg.evaluate("document.getElementById('toasts')?.remove()")
    pg.mouse.click(xy[0], xy[1])
    pg.wait_for_timeout(600)
    sous = pg.text_content("#onglet-selection .sous") or ""
    ok("clic sur une épingle dans la ville -> fiche du signalement", rid in sous, sous)
    pg.screenshot(path=SHOTS + "geste_epingle.png")
    # Historique : rouvrir un plan enregistré.
    pg.click("#mode-sim")
    pg.wait_for_function("window.__ouaga.sim.sim && !window.__ouaga.busy", timeout=120000)
    courant = pg.evaluate("window.__ouaga.plan.sim.plan_id")
    pg.click(".onglets >> text=Historique")
    pg.wait_for_selector("#onglet-historique .bloc", timeout=15000)
    blocs = pg.locator("#onglet-historique .bloc")
    cible = None
    for i in range(blocs.count()):
        if "en cours" not in blocs.nth(i).text_content() and "simulation" in blocs.nth(i).text_content():
            cible = blocs.nth(i)
            break
    cible.locator("text=Rouvrir").click()
    pg.wait_for_function(f"window.__ouaga.plan.sim.plan_id !== '{courant}'", timeout=20000)
    ok("historique : « Rouvrir » affiche le plan enregistré", True,
       pg.evaluate("window.__ouaga.plan.sim.plan_id") + " | " + pg.locator(".toast").last.text_content())
    ok("aucune erreur JavaScript", not errs, str(errs[:3]))
    b.close()
print(f"{sum(res)}/{len(res)} vérifications OK")
