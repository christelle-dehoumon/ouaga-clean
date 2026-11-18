// Couche API commune (citoyen, brigade, mairie). Contrat : docs/api.md. Un seul endroit pour les délais, les
// erreurs en français, le code de rôle (en-tête X-Role-Code) et le mode démonstration (?mock=1, jamais automatique).

export const TIMEOUT_MS = 8000;
export const LONG_TIMEOUT_MS = 30000; // calcul de plan et scénarios

export class ApiError extends Error {
  constructor(message, { status = 0, detail = null, kind = "http" } = {}) {
    super(message);
    this.status = status;
    this.detail = detail;
    this.kind = kind; // http | reseau | delai | format
  }
}

export function isMockMode() {
  try {
    return new URLSearchParams(window.location.search).get("mock") === "1";
  } catch {
    return false;
  }
}

const CODE_KEY = (role) => `ouaga.code.${role}`;

/** Code de rôle gardé pour la session de l'onglet. Ce n'est PAS une sécurité : le serveur vérifie chaque appel. */
export const roleCode = {
  get(role) { try { return sessionStorage.getItem(CODE_KEY(role)) || ""; } catch { return ""; } },
  set(role, code) { try { sessionStorage.setItem(CODE_KEY(role), code); } catch { /* stockage indisponible */ } },
  clear(role) { try { sessionStorage.removeItem(CODE_KEY(role)); } catch { /* idem */ } },
};

const MESSAGES = {
  400: "Requête invalide.",
  401: "Code d'accès manquant ou incorrect.",
  403: "Action non autorisée pour ce rôle.",
  404: "Ressource introuvable sur le serveur.",
  409: "Conflit : l'élément a déjà changé d'état.",
  413: "Envoi trop volumineux.",
  422: "Données refusées par le serveur.",
  500: "Erreur interne du serveur.",
};

/** Client HTTP réel. */
export class HttpApi {
  constructor({ role = null, base = "/api" } = {}) {
    this.role = role;
    this.base = base;
    this.inflight = new Map();
    this.mock = false;
  }

  headers(extra = {}) {
    const h = { Accept: "application/json", ...extra };
    const code = this.role ? roleCode.get(this.role) : "";
    if (code) h["X-Role-Code"] = code;
    return h;
  }

  async request(method, path, { body, timeout = TIMEOUT_MS, raw = false } = {}) {
    const key = method === "GET" ? `${method} ${path}` : null;
    if (key && this.inflight.has(key)) return this.inflight.get(key);   // pas de requête GET en double
    const run = this._request(method, path, { body, timeout, raw });
    if (key) {
      this.inflight.set(key, run);
      run.finally(() => this.inflight.delete(key)).catch(() => {});
    }
    return run;
  }

  async _request(method, path, { body, timeout, raw }) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    let resp;
    try {
      resp = await fetch(this.base + path, {
        method,
        headers: this.headers(body !== undefined ? { "Content-Type": "application/json" } : {}),
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
        cache: "no-store",
      });
    } catch (err) {
      clearTimeout(timer);
      if (err?.name === "AbortError") {
        throw new ApiError(`Le serveur n'a pas répondu en ${Math.max(1, Math.round(timeout / 1000))} s.`, { kind: "delai" });
      }
      throw new ApiError("Serveur injoignable : vérifiez la connexion.", { kind: "reseau" });
    }
    clearTimeout(timer);
    if (!resp.ok) {
      let detail = null;
      try { detail = (await resp.json())?.detail ?? null; } catch { /* corps non JSON */ }
      const msg = typeof detail === "string" && detail ? detail : MESSAGES[resp.status] || `Erreur HTTP ${resp.status}.`;
      throw new ApiError(msg, { status: resp.status, detail });
    }
    if (raw) return resp;
    try {
      return await resp.json();
    } catch {
      throw new ApiError("Réponse illisible du serveur.", { kind: "format", status: resp.status });
    }
  }

  // --- Public ----------------------------------------------------------------
  health() { return this.request("GET", "/health"); }
  config() { return this.request("GET", "/config"); }
  territories() { return this.request("GET", "/territories"); }
  /** Envoi citoyen : {photo_b64, lat, lon, reported_at, accuracy_m} -> {ok: true} (aucun verdict renvoyé). */
  postReport(payload) { return this.request("POST", "/reports", { body: payload, timeout: 20000 }); }

  // --- Brigade et mairie -------------------------------------------------------
  reports({ mode = "reel", statut, type, inclureNettoyes = false, depuis } = {}) {
    const q = new URLSearchParams({ mode, limit: "5000" });
    if (statut) q.set("statut", statut);
    if (type) q.set("type", type);
    if (inclureNettoyes) q.set("inclure_nettoyes", "1");
    if (depuis) q.set("depuis", depuis);
    return this.request("GET", `/reports?${q}`);
  }
  decision(id, action, mode = "reel") {
    return this.request("POST", `/reports/${encodeURIComponent(id)}/decision?mode=${mode}`, { body: { action } });
  }
  markClean(id, mode = "reel") { return this.request("POST", `/reports/${encodeURIComponent(id)}/mark-clean?mode=${mode}`); }
  resetCase(id, mode = "reel") { return this.request("POST", `/reports/${encodeURIComponent(id)}/reset?mode=${mode}`); }
  history(id, mode = "reel") { return this.request("GET", `/reports/${encodeURIComponent(id)}/history?mode=${mode}`); }
  /** Photo floutée en Blob (en-tête de rôle, jamais le code dans l'URL). */
  async photo(id, mode = "reel") {
    const r = await this.request("GET", `/reports/${encodeURIComponent(id)}/photo?mode=${mode}`, { raw: true, timeout: 15000 });
    return r.blob();
  }
  ecartes(mode = "reel") { return this.request("GET", `/ecartes?mode=${mode}`); }
  resetEcarte(id, mode = "reel") { return this.request("POST", `/ecartes/${encodeURIComponent(id)}/reset?mode=${mode}`); }

  // --- Plan, simulation, scénarios (mairie) ------------------------------------
  plan(body) { return this.request("POST", "/plans", { body, timeout: LONG_TIMEOUT_MS }); }
  getPlan(id) { return this.request("GET", `/plans/${encodeURIComponent(id)}`); }
  simulate(planId, body) {
    return this.request("POST", `/plans/${encodeURIComponent(planId)}/simulation`, { body, timeout: LONG_TIMEOUT_MS });
  }
  scenarios() { return this.request("GET", "/scenarios"); }
  createScenario(body) { return this.request("POST", "/scenarios", { body, timeout: LONG_TIMEOUT_MS * 2 }); }
  compare(a, b) { return this.request("GET", `/scenarios/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`); }
  addSimDump(lat, lon) { return this.request("POST", "/sim/dumpsites", { body: { lat, lon } }); }
  cutRoad(edgeId, cut = true) { return this.request("POST", "/sim/roads/cut", { body: { edge_id: edgeId, cut } }); }
  exportReports() { return this.request("GET", "/export/reports.geojson"); }
  /** Fichier OSM (texte XML) des dépotoirs réels confirmés : à relire dans JOSM, jamais envoyé à OpenStreetMap. */
  async exportOsm() { return (await this.request("GET", "/export/reports.osm", { raw: true })).text(); }
  exportPlan(planId) { return this.request("GET", `/plans/${encodeURIComponent(planId)}/export`); }
}

/** Fabrique : client réel, ou client de démonstration si ?mock=1 (et seulement dans ce cas). */
export async function createApi(opts = {}) {
  if (isMockMode()) {
    const { MockApi } = await import("./mock.js");
    return new MockApi(opts);
  }
  return new HttpApi(opts);
}

/** Empêche un double envoi : le bouton est désactivé pendant l'action et réactivé ensuite. */
export async function once(button, fn) {
  if (button?.dataset.busy === "1") return undefined;
  if (button) { button.dataset.busy = "1"; button.disabled = true; button.setAttribute("aria-busy", "true"); }
  try {
    return await fn();
  } finally {
    if (button) { delete button.dataset.busy; button.disabled = false; button.removeAttribute("aria-busy"); }
  }
}
