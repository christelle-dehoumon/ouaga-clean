// Backend de DÉMONSTRATION (?mock=1 uniquement) : mêmes méthodes que HttpApi, données FICTIVES en mémoire.
// Les tournées suivent le vrai réseau routier de la ville 3D (Dijkstra) quand il est fourni (attachCity) ;
// sinon des segments droits. Rien de ce module n'est jamais présenté comme une donnée municipale.
import { ApiError } from "./api.js";

const CENTER = [12.3672, -1.5337];
const TERRITORIES = [
  { id: "tampouy", nom: "Tampouy", approximate: true },
  { id: "kalgodin", nom: "Kalgodin", approximate: true },
  { id: "paglayiri", nom: "Paglayiri", approximate: true },
];
const TRANSITIONS = {
  "brigade:confirmer:depotoir:a_verifier": ["depotoir", "confirme"],
  "brigade:rejeter:depotoir:a_verifier": ["depotoir", "rejete"],
  "mairie:marquer_nettoye:depotoir:confirme": ["nettoyage", "a_verifier"],
  "brigade:confirmer:nettoyage:a_verifier": ["nettoyage", "nettoye"],
  "brigade:rejeter:nettoyage:a_verifier": ["nettoyage", "rejete"],
  "mairie:remettre_a_verifier:depotoir:rejete": ["depotoir", "a_verifier"],
  "mairie:remettre_a_verifier:nettoyage:rejete": ["nettoyage", "a_verifier"],
};
const ALERTES = {
  DOUBLON_PROBABLE: "Signalé plusieurs fois au même endroit en peu de temps.",
  PHOTO_DEJA_VUE: "Photo identique à un envoi précédent.",
  HORS_SECTEUR: "Dans la ville mais hors du secteur de l'équipe.",
  GPS_IMPRECIS: "Position GPS imprécise.",
};

function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const nowIso = () => new Date().toISOString();

class MinHeap {
  constructor() { this.a = []; }
  push(k, v) { const a = this.a; a.push([k, v]); let i = a.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (a[p][0] <= a[i][0]) break; [a[p], a[i]] = [a[i], a[p]]; i = p; } }
  pop() {
    const a = this.a; const top = a[0]; const last = a.pop();
    if (a.length) { a[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < a.length && a[l][0] < a[m][0]) m = l; if (r < a.length && a[r][0] < a[m][0]) m = r; if (m === i) break; [a[m], a[i]] = [a[i], a[m]]; i = m; } }
    return top;
  }
  get size() { return this.a.length; }
}

export class MockApi {
  constructor({ role = null } = {}) {
    this.role = role;
    this.mock = true;
    const r = rng(42);
    this.cases = [];
    const statuts = [["depotoir", "a_verifier"], ["depotoir", "a_verifier"], ["depotoir", "confirme"], ["depotoir", "rejete"],
      ["nettoyage", "a_verifier"], ["depotoir", "confirme"]];
    for (let i = 0; i < 26; i++) {
      const [type, statut] = statuts[i % statuts.length];
      const alertes = Object.keys(ALERTES).filter(() => r() < 0.12);
      this.cases.push({
        id: `demo${String(i + 1).padStart(3, "0")}`, type, statut,
        lat: CENTER[0] + (r() - 0.5) * 0.04, lon: CENTER[1] + (r() - 0.5) * 0.04,
        reported_at: new Date(Date.now() - r() * 5 * 86400e3).toISOString(),
        created_at: nowIso(), updated_at: new Date(Date.now() - r() * 3600e3).toISOString(),
        alertes, alertes_libelles: alertes.map((a) => ALERTES[a]), nb_signalements: 1 + Math.floor(r() * 3),
        source: "reel", photo: true, photo_url: "#demo", history: [],
      });
    }
    this.ecartesList = [
      { id: 1, quand: nowIso(), motif_code: "HORS_VILLE", motif: "Position hors de la commune.", payload_resume: "{\"lat\": 11.18, \"lon\": -4.29}", lat: 11.18, lon: -4.29, resolu: false, remettable: true },
      { id: 2, quand: nowIso(), motif_code: "DATE_FUTURE", motif: "Date dans le futur.", payload_resume: "{\"reported_at\": \"2099-01-01\"}", lat: 12.37, lon: -1.52, resolu: false, remettable: true },
      { id: 3, quand: nowIso(), motif_code: "FORMAT_INVALIDE", motif: "Données mal formées (JSON illisible ou pas un objet).", payload_resume: "{casse", lat: null, lon: null, resolu: false, remettable: false },
    ];
    this.plans = new Map();
    this.scenarioList = [];
    this.simDumps = [];
    this.cuts = new Set();
    this.graph = null;
  }

  /** Réseau routier de la ville 3D (city.roads, projection) pour des tournées le long des rues. */
  attachCity(roads, proj) {
    const nodes = new Map();
    const adj = new Map();
    roads.forEach((road) => {
      if (!road.truck) return;
      const [u, v] = road.id.split("-");
      const len = road.pts.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - road.pts[i][0], p[1] - road.pts[i][1]), 0);
      nodes.set(u, road.pts[0]);
      nodes.set(v, road.pts.at(-1));
      for (const [a, b, pts] of [[u, v, road.pts], [v, u, [...road.pts].reverse()]]) {
        if (!adj.has(a)) adj.set(a, []);
        adj.get(a).push({ to: b, len, pts, id: road.id, paved: road.paved });
      }
    });
    this.graph = { nodes, adj, proj };
  }

  async _delay() { await wait(150 + Math.random() * 250); }

  _check(roles) {
    if (!this.role) throw new ApiError("Code d'accès manquant ou incorrect.", { status: 401 });
    if (!roles.includes(this.role)) throw new ApiError(`Action réservée à : ${roles.join(", ")}.`, { status: 403 });
  }

  async health() { await this._delay(); return { ok: true, commune: "Ouagadougou (démonstration)", simulation: "démonstration", network_nodes: this.graph?.nodes.size || 0 }; }
  async config() {
    await this._delay();
    const p = (min, max, def, unit, label) => ({ min, max, default: def, unit, label });
    return { commune: "Ouagadougou (démonstration)", center: CENTER, zoom: 14, modes: ["reel", "sim"], territories: TERRITORIES,
      params: { population: p(0, 6000000, 3000000, "habitants", "Population de la commune"),
        subscription_rate: p(0, 1, 0.4, "part (0 a 1)", "Taux d'abonnement a la pre-collecte"),
        trucks: p(0, 60, 10, "camions", "Camions de la mairie"), truck_capacity_kg: p(500, 20000, 5000, "kg", "Capacite d'un camion"),
        tricycles: p(0, 300, 20, "tricycles", "Tricycles des pre-collecteurs"), tricycle_capacity_kg: p(50, 1500, 400, "kg", "Capacite d'un tricycle"),
        frequency_per_week: p(1, 7, 3, "passages par semaine", "Frequence de collecte"),
        budget: p(0, 500000000, 10000000, "FCFA par jour de collecte", "Budget de collecte") } };
  }
  async territories() { await this._delay(); return TERRITORIES; }
  async postReport(payload) {
    await this._delay();
    if (payload && Number.isFinite(payload.lat) && payload.photo_b64) {
      const alertes = payload.accuracy_m > 100 ? ["GPS_IMPRECIS"] : [];
      this.cases.unshift({ id: `demo${Date.now()}`, type: "depotoir", statut: "a_verifier", lat: payload.lat, lon: payload.lon,
        reported_at: payload.reported_at || nowIso(), created_at: nowIso(), updated_at: nowIso(), alertes,
        alertes_libelles: alertes.map((a) => ALERTES[a]), nb_signalements: 1, source: "reel", photo: true, photo_url: "#demo", history: [] });
    }
    return { ok: true };
  }

  async reports({ mode = "reel", statut, type, inclureNettoyes = false } = {}) {
    await this._delay();
    this._check(["brigade", "mairie"]);
    if (mode === "sim") return this.simDumps.map((d) => ({ ...d }));
    return this.cases.filter((c) => (this.role === "brigade" ? c.statut === "a_verifier"
      : (statut ? c.statut === statut : inclureNettoyes || c.statut !== "nettoye")) && (!type || c.type === type)).map((c) => ({ ...c }));
  }
  async _transition(id, action) {
    await this._delay();
    this._check(["brigade", "mairie"]);
    const c = this.cases.find((x) => x.id === id);
    if (!c) throw new ApiError(`Cas « ${id} » introuvable.`, { status: 404 });
    const allowed = Object.keys(TRANSITIONS).some((k) => k.split(":")[1] === action && k.startsWith(`${this.role}:`));
    if (!allowed) throw new ApiError(`Le rôle « ${this.role} » ne peut pas « ${action} ».`, { status: 403 });
    const to = TRANSITIONS[`${this.role}:${action}:${c.type}:${c.statut}`];
    if (!to) throw new ApiError(`Transition impossible : un cas « ${c.type} » au statut « ${c.statut} » ne peut pas recevoir « ${action} ».`, { status: 409 });
    c.history.push({ qui: this.role, quand: nowIso(), action, de: { type: c.type, statut: c.statut }, vers: { type: to[0], statut: to[1] } });
    [c.type, c.statut] = to;
    c.updated_at = nowIso();
    return { id, type: c.type, statut: c.statut, cas: { ...c } };
  }
  decision(id, action) { return this._transition(id, action); }
  markClean(id) { return this._transition(id, "marquer_nettoye"); }
  resetCase(id) { return this._transition(id, "remettre_a_verifier"); }
  async history(id) {
    await this._delay();
    const c = this.cases.find((x) => x.id === id);
    if (!c) throw new ApiError("Cas introuvable.", { status: 404 });
    return [{ qui: "citoyen", quand: c.created_at, action: "creation", de: { type: null, statut: null }, vers: { type: "depotoir", statut: "a_verifier" } }, ...c.history];
  }
  async photo() {
    await this._delay();
    const c = document.createElement("canvas");
    c.width = 480; c.height = 320;
    const g = c.getContext("2d");
    g.fillStyle = "#b9a17d"; g.fillRect(0, 0, 480, 320);
    g.fillStyle = "#6b5236"; for (let i = 0; i < 40; i++) g.fillRect(Math.random() * 480, 160 + Math.random() * 160, 20 + Math.random() * 40, 8 + Math.random() * 20);
    g.fillStyle = "#1d1f1e"; g.font = "bold 22px system-ui"; g.fillText("PHOTO FICTIVE — DÉMONSTRATION", 40, 60);
    return new Promise((res) => c.toBlob(res, "image/jpeg", 0.8));
  }
  async ecartes() { await this._delay(); this._check(["mairie"]); return this.ecartesList.filter((e) => !e.resolu); }
  async resetEcarte(id) {
    await this._delay();
    this._check(["mairie"]);
    const e = this.ecartesList.find((x) => x.id === Number(id));
    if (!e) throw new ApiError("Écarté introuvable.", { status: 404 });
    if (e.lat === null) throw new ApiError("Impossible de remettre à vérifier : l'envoi n'avait pas de position valide.", { status: 409 });
    e.resolu = true;
    const cas = { id: `demo${Date.now()}`, type: "depotoir", statut: "a_verifier", lat: e.lat, lon: e.lon, reported_at: nowIso(), created_at: nowIso(),
      updated_at: nowIso(), alertes: ["ECARTE_REMIS"], alertes_libelles: ["Écarté puis remis à vérifier."], nb_signalements: 1, source: "reel", photo: false, history: [] };
    this.cases.unshift(cas);
    return { ecarte_id: e.id, cas };
  }

  // --- Plan fictif -----------------------------------------------------------------------------------------------
  _nearestNode(x, z) {
    let best = null;
    let bd = Infinity;
    for (const [id, [nx, nz]] of this.graph.nodes) {
      const d = (nx - x) ** 2 + (nz - z) ** 2;
      if (d < bd && this.graph.adj.has(id)) { bd = d; best = id; }
    }
    return best;
  }
  _path(a, b, rain) {
    const dist = new Map([[a, 0]]);
    const prev = new Map();
    const h = new MinHeap();
    h.push(0, a);
    while (h.size) {
      const [d, u] = h.pop();
      if (u === b) break;
      if (d > (dist.get(u) ?? Infinity)) continue;
      for (const e of this.graph.adj.get(u) || []) {
        if (this.cuts.has(e.id)) continue;
        const nd = d + e.len * (rain && !e.paved ? 2.5 : 1);
        if (nd < (dist.get(e.to) ?? Infinity)) { dist.set(e.to, nd); prev.set(e.to, [u, e]); h.push(nd, e.to); }
      }
    }
    if (!prev.has(b) && a !== b) return null;
    const pts = [];
    let cur = b;
    while (cur !== a) { const [p, e] = prev.get(cur); pts.unshift(...e.pts.slice(1)); cur = p; }
    pts.unshift(this.graph.nodes.get(a));
    return { pts, km: pts.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0) / 1000 };
  }

  async plan(body = {}) {
    this._check(["mairie"]);
    const t0 = performance.now();
    await this._delay();
    const cfg = await this.config();
    const params = Object.fromEntries(Object.entries(cfg.params).map(([k, v]) => [k, v.default]));
    Object.assign(params, body.params || {});
    params.broken_trucks = [...(body.params?.broken_trucks || [])];
    params.extra_territories = [...(body.params?.extra_territories || [])];
    for (const ev of body.events || []) {
      if (ev.type === "truck_down") params.broken_trucks.push(String(ev.vehicle_id).split("_trip")[0]);
      else if (ev.type === "rain") params.rainy_season = true;
      else if (ev.type === "new_district") {
        if (!TERRITORIES.some((t) => t.id === ev.territory_id)) throw new ApiError(`Quartier « ${ev.territory_id} » inconnu.`, { status: 422 });
        params.extra_territories.push(ev.territory_id);
      } else throw new ApiError(`Événement « ${ev.type} » inconnu.`, { status: 422 });
    }
    for (const c of body.cut_roads || []) if (c.edge_id) this.cuts.add(c.edge_id);
    const r = rng(7);
    const proj = this.graph?.proj;
    const pts = [];
    const n = 24 + params.extra_territories.length * 6;
    for (let i = 0; i < n; i++) {
      const ang = r() * Math.PI * 2;
      const rad = 300 + r() * 2100;
      const x = Math.cos(ang) * rad;
      const z = Math.sin(ang) * rad;
      const ll = proj ? proj.toLatLon(x, z) : [CENTER[0] - z / 111320, CENTER[1] + x / 108700];
      pts.push({ id: `demo_c${i}`, type: "center", lat: ll[0], lon: ll[1], demand_kg: Math.round((1500 + r() * 2500) * (params.population / 3e6) * (params.subscription_rate / 0.4)), x, z, data_tag: "fictif" });
    }
    for (const d of this.simDumps) {
      const p = proj ? proj.toLocal(d.lat, d.lon) : { x: 0, z: 0 };
      pts.push({ id: d.id, type: "dumpsite", lat: d.lat, lon: d.lon, demand_kg: 800, x: p.x, z: p.z, data_tag: "fictif" });
    }
    const trucks = [];
    for (let i = 1; i <= params.trucks; i++) if (!params.broken_trucks.includes(`truck${i}`)) trucks.push(`truck${i}`);
    const capacity = params.truck_capacity_kg * 3 * (params.rainy_season ? 0.85 : 1);
    pts.sort((a, b) => Math.atan2(a.z, a.x) - Math.atan2(b.z, b.x));
    const routes = [];
    const unserved = [];
    let ti = 0;
    let load = 0;
    let stops = [];
    const depotNode = this.graph ? this._nearestNode(0, 0) : null;
    const flush = () => {
      if (!stops.length) return;
      const truck = trucks[ti];
      let path = [];
      let km = 0;
      if (this.graph) {
        let cur = depotNode;
        for (const s of [...stops, null]) {
          const target = s ? this._nearestNode(s.x, s.z) : depotNode;
          const leg = this._path(cur, target, params.rainy_season);
          if (!leg) { if (s) unserved.push({ point_id: s.id, reason: "access", detail: "Route coupée : point inaccessible." }); continue; }
          path.push(...leg.pts); km += leg.km; cur = target;
        }
        path = path.map(([x, z]) => proj.toLatLon(x, z));
      } else {
        path = [CENTER, ...stops.map((s) => [s.lat, s.lon]), CENTER];
        km = stops.length * 1.5;
      }
      routes.push({ vehicle: `${truck}_trip1`, vehicle_id: `${truck}_trip1`, type: "truck", stops: stops.map((s) => s.id),
        distance_km: Math.round(km * 10) / 10, load_kg: load, duration_min: Math.round(km * 2.4 + stops.length * 10), cost: Math.round(km * 1500), path });
      stops = []; load = 0; ti += 1;
    };
    for (const p of pts) {
      if (ti >= trucks.length) { unserved.push({ point_id: p.id, reason: "capacity", detail: "Aucun camion disponible." }); continue; }
      if (load + p.demand_kg > capacity) flush();
      if (ti >= trucks.length) { unserved.push({ point_id: p.id, reason: "capacity", detail: "Aucun camion disponible." }); continue; }
      stops.push(p); load += p.demand_kg;
    }
    flush();
    const prev = body.previous_plan_id ? this.plans.get(body.previous_plan_id) : null;
    const down = (body.events || []).filter((e) => e.type === "truck_down").map((e) => String(e.vehicle_id).split("_trip")[0]);
    const lost = new Set((prev?.routes || []).filter((r0) => down.includes(r0.vehicle_id.split("_trip")[0])).flatMap((r0) => r0.stops));
    const postponed = unserved.filter((u) => lost.has(u.point_id)).map((u) => ({ id: u.point_id, reason: "Camion en panne : arrêt reporté au prochain passage." }));
    const unservedOnly = unserved.filter((u) => !lost.has(u.point_id));
    const cost = routes.reduce((s, x) => s + x.cost, 0);
    const ratio = pts.length ? unservedOnly.length / pts.length : 0;
    const id = `demo_p${Date.now()}`;
    const plan = {
      plan_id: id, mode: down.length && prev ? "partiel" : "complet", data_mode: body.mode || "reel", data_tag: "fictif",
      compute_ms: Math.round(performance.now() - t0), params_used: params, consolidation_points: pts.map(({ x, z, ...p }) => p),
      collection_points: pts.map(({ x, z, ...p }) => p), routes, unserved: unservedOnly, postponed,
      vehicles: Array.from({ length: params.trucks }, (_, i) => ({ id: `truck${i + 1}`, type: "truck",
        status: params.broken_trucks.includes(`truck${i + 1}`) ? "en panne" : "en service",
        trips: routes.filter((x) => x.vehicle_id.startsWith(`truck${i + 1}_`)).map((x) => x.vehicle_id) })),
      cut_roads: [...this.cuts].map((e) => ({ edge_id: e })), inaccessible_due_to_cuts: [],
      checks: { ok: ratio <= 0.1 && routes.length > 0, capacity_ok: true, budget_ok: cost <= params.budget, vehicles_ok: true, network_ok: true,
        unserved_count: unservedOnly.length, unserved_ratio: Math.round(ratio * 1e4) / 1e4, postponed_count: postponed.length, max_unserved_ratio: 0.1,
        messages: ratio > 0.1 ? [`${unservedOnly.length} point(s) non desservis (${Math.round(ratio * 100)} %).`] : [] },
      totals: { cost, collected_kg: routes.reduce((s, x) => s + x.load_kg, 0), distance_km: routes.reduce((s, x) => s + x.distance_km, 0),
        uncollected_kg: Math.round(params.population * 0.6 * (1 - params.subscription_rate) * 7 / params.frequency_per_week / 20) },
      warnings: ["DONNÉES FICTIVES : plan de démonstration, sans valeur opérationnelle."], assumptions: [], events: body.events || [],
    };
    this.plans.set(id, plan);
    this.scenarioList.unshift({ id: `s_${id}`, created_at: nowIso(), plan_id: id, label: body.label || null, params, events: body.events || [], mode: body.mode || "reel",
      compute_ms: plan.compute_ms, results: { cout_fcfa: cost, non_servis: unservedOnly.length, reportes: postponed.length, points: pts.length,
        unserved_ratio: plan.checks.unserved_ratio, checks_ok: plan.checks.ok, compute_ms: plan.compute_ms } });
    return plan;
  }
  async getPlan(id) { await this._delay(); const p = this.plans.get(id); if (!p) throw new ApiError("Plan introuvable.", { status: 404 }); return p; }
  async simulate(planId, { days = 7 } = {}) {
    await this._delay();
    const p = this.plans.get(planId);
    if (!p) throw new ApiError("Plan introuvable.", { status: 404 });
    const served = 1 - (p.checks.unserved_ratio + (p.checks.postponed_count || 0) / Math.max(1, p.consolidation_points.length));
    const rain = p.params_used.rainy_season ? 0.9 : 1;
    const part = Math.max(0, Math.min(1, served * p.params_used.subscription_rate * 0.95 * rain + 0.05));
    const cost = Math.round(p.totals.cost * days * p.params_used.frequency_per_week / 7);
    const result = { scenario_id: `s_${planId}`, plan_id: planId, data_tag: "fictif", moteur: "démonstration", jours: days,
      part_ramassee: Math.round(part * 1000) / 1000, cout_fcfa: cost, cout_m_fcfa: Math.round(cost / 1e3) / 1e3,
      depotoirs_restants: Math.round(40 * (1 - part) + this.simDumps.length), kg_produits: 0, kg_ramasses: 0,
      series: Array.from({ length: days }, (_, i) => ({ jour: i + 1, collecte_kg: Math.round(p.totals.collected_kg / 3), depotoirs: Math.round(40 * (1 - part)) })),
      depotoirs: [], indicateurs: {}, hypotheses: {}, assumptions: ["DONNÉES FICTIVES"], warnings: [] };
    const s = this.scenarioList.find((x) => x.plan_id === planId);
    if (s) Object.assign(s.results, { part_ramassee: result.part_ramassee, cout_sim_fcfa: cost, depotoirs_restants: result.depotoirs_restants, jours_simules: days });
    return result;
  }
  async scenarios() { await this._delay(); return this.scenarioList.map((s) => ({ ...s })); }
  async createScenario(body) {
    const plan = await this.plan(body);
    const simulation = await this.simulate(plan.plan_id, { days: body.days || 7 });
    const s = this.scenarioList.find((x) => x.plan_id === plan.plan_id);
    s.label = body.label || s.label;
    return { ...s, plan, simulation };
  }
  async compare(a, b) {
    await this._delay();
    const A = this.scenarioList.find((s) => s.id === a);
    const B = this.scenarioList.find((s) => s.id === b);
    if (!A || !B) throw new ApiError("Scénario introuvable.", { status: 404 });
    const keys = ["part_ramassee", "cout_fcfa", "non_servis", "reportes", "depotoirs_restants", "compute_ms"];
    return { a: A, b: B, ecarts: keys.map((k) => ({ indicateur: k, a: A.results[k] ?? null, b: B.results[k] ?? null,
      ecart: Number.isFinite(A.results[k]) && Number.isFinite(B.results[k]) ? B.results[k] - A.results[k] : null })) };
  }
  async addSimDump(lat, lon) {
    await this._delay();
    this._check(["mairie"]);
    const d = { id: `sim_demo${Date.now()}`, lat, lon, kg: 800, created_at: nowIso(), source: "sim", type: "depotoir", statut: "a_verifier" };
    this.simDumps.push(d);
    return d;
  }
  async cutRoad(edgeId, cut = true) {
    await this._delay();
    this._check(["mairie"]);
    if (cut) this.cuts.add(edgeId); else this.cuts.delete(edgeId);
    return { edge: { edge_id: edgeId }, cut, active_cuts: [...this.cuts].map((e) => ({ edge_id: e })) };
  }
  async exportReports() { await this._delay(); return { type: "FeatureCollection", features: [], license: "fictif" }; }
}
