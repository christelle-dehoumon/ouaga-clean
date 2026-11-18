"""Réglages par commune, côté interface : serveur lancé avec COMMUNE_CONFIG=config/commune_config.koudougou.json (BASE).
La ville 3D (préparée pour Ouagadougou) n'est pas réutilisée à tort : carte 2D centrée sur la commune configurée,
bandeau explicite, plan en mode secours annoncé comme irréalisable (routes de Koudougou non préparées)."""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://localhost:9447")
MAIRIE = os.environ.get("MAIRIE_CODE", "mairie-demo")
res = []


def ok(nom, cond, info=""):
    res.append(bool(cond))
    print(f"[{'OK ' if cond else 'KO '}] {nom} {info}")


with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(f"sessionStorage.setItem('ouaga.code.mairie', '{MAIRIE}'); localStorage.setItem('ouaga.aide.vue', '1');")
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/dashboard/")
    pg.wait_for_function("document.getElementById('chargement').hidden === true", timeout=120000)
    commune = pg.evaluate("window.__ouaga.config.commune")
    ok("configuration lue : commune et centre", commune == "Koudougou" and pg.evaluate("window.__ouaga.config.center[1]") < -2.3, commune)
    ok("ville 3D d'une autre commune non réutilisée : carte 2D", pg.evaluate("window.__ouaga.view.kind") == "2d",
       pg.text_content("#bandeau-perime"))
    pg.click("#mode-sim")
    pg.wait_for_function("window.__ouaga.plan.sim && !window.__ouaga.busy", timeout=60000)
    ok("plan sans routes préparées : annoncé irréalisable (secours)", "irréalisable" in pg.text_content("#statut-plan"),
       pg.text_content("#statut-plan"))
    ok("paramètres de la commune dans les curseurs", pg.evaluate("window.__ouaga.scenario.params.population") == 160000)
    ok("aucune erreur JavaScript", not errs, str(errs[:3]))
    b.close()
print(f"{sum(res)}/{len(res)} vérifications OK")
sys.exit(0 if all(res) else 1)
