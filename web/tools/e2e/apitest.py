"""Test de bout en bout dans Chromium (Playwright). Serveur requis : BASE (défaut http://localhost:9446),
lancé sur des bases de test (REEL_DB, SIM_DB, PHOTO_DIR temporaires). Captures dans SHOTS."""
import os
BASE = os.environ.get('BASE', 'http://localhost:9446')
SHOTS = os.environ.get('SHOTS', '/tmp/ouaga-shots/')
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')) + '/'
os.makedirs(SHOTS, exist_ok=True)
from playwright.sync_api import sync_playwright
JS = """async () => {
  const m = await import('/dashboard/shared/api.js');
  const out = {};
  const api = new m.HttpApi({ role: 'mairie' });
  try { await api.reports(); } catch (e) { out.sans_code = [e.status, e.message]; }
  m.roleCode.set('mairie', 'mairie-demo');
  out.reports = (await api.reports()).length;
  try { await api.getPlan('inexistant'); } catch (e) { out.plan_404 = [e.status, e.message]; }
  m.roleCode.set('brigade', 'brigade-demo');
  try { await new m.HttpApi({ role: 'brigade' }).plan({}); } catch (e) { out.brigade_plan = [e.status, e.message]; }
  try { await api.request('GET', '/health', { timeout: 1 }); } catch (e) { out.delai = [e.kind, e.message]; }
  try { await new m.HttpApi({ base: 'http://127.0.0.1:1/api' }).health(); } catch (e) { out.reseau = [e.kind, e.message]; }
  let n = 0; const orig = window.fetch; window.fetch = (...a) => { n++; return orig(...a); };
  await Promise.all([api.config(), api.config(), api.config()]); window.fetch = orig; out.get_dedoublonne = n;
  const plan = await api.plan({});
  out.plan = [plan.mode, plan.routes.length, plan.checks.ok];
  const { MockApi } = await import('/dashboard/shared/mock.js');
  const mock = new MockApi({ role: 'brigade' });
  const cas = (await mock.reports())[0];
  await mock.decision(cas.id, 'confirmer');
  try { await mock.decision(cas.id, 'confirmer'); } catch (e) { out.mock_409 = [e.status, e.message]; }
  return out; }"""
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(); pg.goto(BASE + "/citizen/")
    out = pg.evaluate(JS)
    for k, v in out.items(): print(f"{k:16s} {v}")
    assert out["sans_code"][0] == 401 and out["plan_404"][0] == 404 and out["brigade_plan"][0] == 403
    assert out["delai"][0] == "delai" and out["reseau"][0] == "reseau" and out["get_dedoublonne"] == 1
    assert out["plan"][0] == "complet" and out["mock_409"][0] == 409
    b.close()
