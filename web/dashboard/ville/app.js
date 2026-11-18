// Tableau de bord mairie : ville 3D reliée aux données réelles (mode Réel) ou à un scénario (mode Simulation).
// Contrat d'API : docs/api.md. Rien n'est inventé : chaque chiffre affiché vient d'une réponse du serveur ou d'un
// calcul documenté à côté de lui.
import { ApiError, createApi, isMockMode, once, roleCode } from "/dashboard/shared/api.js";
import { $, askCode, confirmDialog, el, fmt, mockBanner, toast } from "/dashboard/shared/ui.js";
import { renderCompare, renderHistory } from "./compare.js";
import { planStatus } from "./status.js";

const DEBOUNCE_MS = 700;
const POLL_MS = 15000;
const SIM_DAYS = 7;
const PARAM_ORDER = ["trucks", "truck_capacity_kg", "tricycles", "population", "subscription_rate", "frequency_per_week", "budget"];

export const S = {
  api: null, view: null, config: null, territories: [], mode: "reel",
  reports: [], simReports: [], simDumps: [], ecartes: [], filtres: new Set(["a_verifier", "confirme", "rejete", "nettoyage"]),
  inclureNettoyes: false,
  plan: { reel: null, sim: null }, sim: { reel: null, sim: null }, stale: { reel: null, sim: null },
  scenario: { params: {}, broken: new Set(), rain: false, districts: new Set(), cuts: new Map() },
  busy: false, pending: null, selection: null, interaction: "selection", timings: {}, A: null, B: null,
};

// --- Démarrage ------------------------------------------------------------------------------------------------
async function ensureCode(force = false) {
  if (!force && roleCode.get("mairie")) return;
  S.asking ??= askCode({ role: "mairie", title: "Code de la mairie", hint: "Saisissez le code d'accès de la mairie." })
    .then((c) => roleCode.set("mairie", c)).finally(() => { S.asking = null; });
  await S.asking;
}

/** Appel API avec gestion du code : 401/403 -> nouvelle saisie et un seul nouvel essai. */
async function call(fn) {
  try {
    return await fn();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401 && !isMockMode()) {
      roleCode.clear("mairie");
      if (!S.asking) toast("Code de la mairie incorrect ou absent.", "erreur");
      await ensureCode(true);
      return fn();
    }
    throw err;
  }
}

function progress(step, pct) {
  $("#chargement-etape").textContent = step;
  $("#progression").style.width = `${pct}%`;
}

async function init() {
  S.api = await createApi({ role: "mairie" });
  if (isMockMode()) { mockBanner(); roleCode.set("mairie", roleCode.get("mairie") || "demo"); }
  await ensureCode();
  progress("Lecture de la configuration de la commune…", 10);
  try {
    S.config = await call(() => S.api.config());
    S.territories = S.config.territories || await S.api.territories();
  } catch (err) {
    progress(`Configuration indisponible : ${err.message}`, 10);
    toast(err.message, "erreur", 8000);
    return;
  }
  for (const k of PARAM_ORDER) if (S.config.params?.[k]) S.scenario.params[k] = S.config.params[k].default;
  progress("Téléchargement des bâtiments et des routes (OpenStreetMap)…", 25);
  const cityResp = await fetch("/dashboard/ville/data/city.json");
  if (!cityResp.ok) { progress("Données de la ville introuvables.", 25); return; }
  let cityData = await cityResp.json();
  // Réglages par commune : la ville 3D n'existe que pour la commune où elle a été préparée (web/tools/build_city_data.py).
  let other = null;
  if (S.config.commune && cityData.meta.commune && cityData.meta.commune !== S.config.commune) {
    other = `La ville 3D n'est préparée que pour ${cityData.meta.commune} : carte 2D pour ${S.config.commune} (configuration de la commune).`;
    cityData = { meta: { origin: S.config.center, commune: S.config.commune, counts: { buildings: 0 }, sources: [] }, buildings: [], roads: [], water: [], territories: [] };
  }
  progress(`Construction de ${fmt.int(cityData.meta.counts.buildings)} bâtiments en 3D…`, 55);
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 30)));
  S.view = await createView(cityData, other);
  if (isMockMode()) S.api.attachCity?.(S.view.city.roads, S.view.proj);
  bindView();
  bindChrome();
  progress("Chargement des signalements…", 85);
  $("#credit").textContent = S.view.kind === "carte"
    ? "Carte © contributeurs OpenStreetMap (ODbL) · MapLibre · hauteurs des bâtiments estimées sauf mention OSM"
    : S.view.kind === "3d"
      ? "Bâtiments et routes © contributeurs OpenStreetMap (ODbL) · hauteurs estimées · arbres illustratifs"
      : "Vue 2D de secours";
  document.body.classList.toggle("vue-carte", S.view.kind === "carte");
  renderLegend();
  await setMode("reel");
  $("#chargement").hidden = true;
  try { if (!localStorage.getItem("ouaga.aide.vue")) { $("#aide").hidden = false; localStorage.setItem("ouaga.aide.vue", "1"); } } catch { /* ignoré */ }
  setInterval(() => { if (S.mode === "reel" && document.visibilityState === "visible") loadReal({ silent: true }); }, POLL_MS);
  window.__ouaga = S;   // inspection et tests
}

async function createView(cityData, other = null) {
  const host = $("#scene");
  const { detectWebGL } = await import("./map3d/scene.js");
  const demande = new URLSearchParams(location.search).get("vue");
  const forced2d = demande === "2d";
  // Vue par défaut : la carte de toute l'agglomération (MapLibre, tuiles OSM locales). ?vue=ville3d garde la ville
  // Three.js du secteur pilote ; repli automatique sur elle si les tuiles n'ont pas été fabriquées (clone neuf).
  if (!forced2d && !other && demande !== "ville3d" && detectWebGL()) {
    const { createViewCarte, tuilesDisponibles } = await import("./carte/vue.js");
    if (await tuilesDisponibles()) {
      try {
        progress("Chargement de la carte de Ouagadougou (OpenStreetMap)…", 60);
        return await createViewCarte(host, cityData);
      } catch (err) {
        console.error(err);
        toast(`La carte n'a pas pu démarrer (${err.message}) : ville 3D du secteur pilote.`, "erreur", 8000);
        host.querySelectorAll(".maplibregl-canvas-container, .maplibregl-control-container").forEach((n) => n.remove());
      }
    } else {
      toast("Tuiles de la carte absentes (./scripts/fabriquer_tuiles.sh) : ville 3D du secteur pilote.", "info", 8000);
    }
  }
  if (!forced2d && !other && detectWebGL()) {
    try {
      const { createView3D } = await import("./view3d.js");
      return await createView3D(host, cityData);
    } catch (err) {
      console.error(err);
      toast(`La 3D n'a pas pu démarrer (${err.message}) : vue 2D de secours.`, "erreur", 8000);
    }
  }
  const { createView2D } = await import("./view2d.js");
  const box = el("div", { class: "carte-2d", style: "position:absolute;inset:0" });
  host.prepend(box);
  document.body.classList.add("vue-2d");
  $("#bandeau-perime").hidden = false;
  $("#bandeau-perime").textContent = other || (forced2d
    ? "Vue 2D de secours (demandée par ?vue=2d). Les données et les actions sont les mêmes, sans la ville en 3D."
    : "Vue 2D de secours : la 3D (WebGL) n'est pas disponible sur ce poste. Les données et les actions sont les mêmes, sans la ville en 3D.");
  for (const b of document.querySelectorAll("[data-cam=immersive],[data-cam=rue],[data-cam=animation]")) b.disabled = true;
  return createView2D(box, cityData);
}

// --- Modes ----------------------------------------------------------------------------------------------------
async function setMode(mode) {
  S.mode = mode;
  document.body.classList.toggle("mode-sim", mode === "sim");
  document.body.classList.toggle("mode-reel", mode === "reel");
  for (const [id, m] of [["#mode-reel", "reel"], ["#mode-sim", "sim"]]) {
    $(id).classList.toggle("actif", m === mode);
    $(id).setAttribute("aria-pressed", String(m === mode));
  }
  const b = $("#bandeau-mode");
  b.className = `bandeau-mode ${mode === "sim" ? "bandeau-sim" : "bandeau-reel"}`;
  b.textContent = mode === "sim" ? "SIMULATION — DONNÉES FICTIVES ET SCÉNARIOS DE TEST"
    : "DONNÉES RÉELLES — signalements des citoyens vérifiés par la brigade Laabal";
  setInteraction("selection");
  select(null);
  S.view.setRain(mode === "sim" && S.scenario.rain);
  S.view.setReports([]);
  S.view.setSimDumps([]);
  S.view.setPlan(S.plan[mode]);
  renderLeft();
  renderKpis();
  renderStatus();
  if (mode === "reel") await loadReal();
  else {
    await loadSim();
    if (!S.plan.sim) await recalc("Plan initial du scénario");
  }
}

async function loadReal({ silent = false } = {}) {
  try {
    const [reports, ecartes] = await Promise.all([
      call(() => S.api.reports({ mode: "reel", inclureNettoyes: S.inclureNettoyes })), call(() => S.api.ecartes("reel"))]);
    if (S.mode !== "reel") return;
    S.reports = reports;
    S.ecartes = ecartes;
    drawReports();
    renderLeft();
    renderKpis();
  } catch (err) {
    if (!silent) toast(`Signalements indisponibles : ${err.message}`, "erreur", 7000);
  }
}

async function loadSim() {
  try {
    S.simReports = await call(() => S.api.reports({ mode: "sim" }));
  } catch (err) {
    toast(`Cas simulés indisponibles : ${err.message}`, "erreur");
  }
  drawReports();
  renderLeft();
}

function drawReports() {
  if (S.mode === "reel") {
    S.view.setReports(S.reports.filter((r) => S.filtres.has(r.type === "nettoyage" && r.statut !== "rejete" ? "nettoyage" : r.statut)));
    S.view.setSimDumps([]);
  } else {
    S.view.setReports(S.simReports.map((r) => ({ ...r, simule: true })));
    S.view.setSimDumps(S.simDumps);
  }
}

// --- Recalcul du plan -------------------------------------------------------------------------------------------
function scenarioParams() {
  const sc = S.scenario;
  return { ...sc.params, rainy_season: sc.rain, broken_trucks: [...sc.broken], extra_territories: [...sc.districts] };
}

/** Recalcule le plan (une requête à la fois ; la dernière demande en attente passe ensuite). */
async function recalc(reason, { events = null, previous = false } = {}) {
  const mode = S.mode;
  const request = { reason, mode, events, previous };
  if (S.busy) { S.pending = request; return; }
  S.busy = true;
  renderStatus(`Recalcul : ${reason}…`);
  const body = { mode, params: mode === "sim" ? scenarioParams() : {}, label: reason };
  if (events) body.events = events;
  if (previous && S.plan[mode]) body.previous_plan_id = S.plan[mode].plan_id;
  const t0 = performance.now();
  try {
    const plan = await call(() => S.api.plan(body));
    const requestMs = performance.now() - t0;
    if (!plan || !Array.isArray(plan.consolidation_points) || !Array.isArray(plan.routes)) {
      throw new ApiError("Réponse de plan incomplète : le plan précédent est conservé.", { kind: "format" });
    }
    S.plan[mode] = plan;
    S.stale[mode] = null;
    S.sim[mode] = null;
    const r0 = performance.now();
    if (S.mode === mode) S.view.setPlan(plan);
    S.timings = { server: plan.compute_ms, request: requestMs, render: performance.now() - r0, sim: null };
    if (mode === "sim") {
      for (const c of plan.cut_roads || []) S.scenario.cuts.set(c.edge_id, c);
      const s0 = performance.now();
      try {
        S.sim[mode] = await call(() => S.api.simulate(plan.plan_id, { days: SIM_DAYS }));
        S.timings.sim = performance.now() - s0;
      } catch (err) {
        toast(`Simulation multi-agents indisponible : ${err.message}`, "erreur");
      }
    }
  } catch (err) {
    S.stale[mode] = { message: err.message, at: new Date() };
    toast(`Recalcul échoué : ${err.message}`, "erreur", 8000);
  } finally {
    S.busy = false;
    if (S.mode === mode) { renderStatus(); renderKpis(); renderLeft(); refreshSelection(); }
    const next = S.pending;
    S.pending = null;
    if (next && next.mode === S.mode) recalc(next.reason, next);
  }
}

let debounce = null;
function scheduleRecalc(reason) {
  clearTimeout(debounce);
  renderStatus("Paramètres modifiés : recalcul imminent…");
  debounce = setTimeout(() => recalc(reason), DEBOUNCE_MS);
}

// --- Actions de scénario ---------------------------------------------------------------------------------------
async function truckDown(id) {
  if (!S.plan.sim) return;
  S.scenario.broken.add(id);
  await recalc(`Panne de ${id}`, { events: [{ type: "truck_down", vehicle_id: id }], previous: true });
}
async function truckRepair(id) {
  S.scenario.broken.delete(id);
  await recalc(`${id} remis en service`);
}
async function toggleRain(on) {
  S.scenario.rain = on;
  S.view.setRain(on);
  await recalc(on ? "Saison des pluies" : "Fin de la saison des pluies");
}
async function toggleDistrict(id, on) {
  if (on) S.scenario.districts.add(id); else S.scenario.districts.delete(id);
  S.view.focusTerritory(id);
  S.view.highlightTerritory(on ? id : null);
  await recalc(on ? `Nouveau quartier : ${territoryName(id)}` : `Retrait de ${territoryName(id)}`);
}
async function addDump({ lat, lon }) {
  try {
    const d = await call(() => S.api.addSimDump(lat, lon));
    S.simDumps.push({ ...d, type: "depotoir", statut: "a_verifier" });
    S.view.setSimDumps(S.simDumps);
    toast("Dépotoir simulé ajouté (sim.db) : recalcul du plan.", "ok");
    await recalc("Dépotoir simulé ajouté");
  } catch (err) {
    toast(`Ajout impossible : ${err.message}`, "erreur");
  }
}
async function cutRoad(road, cut = true) {
  try {
    const r = await call(() => S.api.cutRoad(road.id, cut));
    S.scenario.cuts = new Map((r.active_cuts || []).map((c) => [c.edge_id, c]));
    toast(cut ? `Route coupée : ${road.name || road.kind}. Recalcul…` : "Route rouverte. Recalcul…", "ok");
    await recalc(cut ? `Route coupée (${road.name || road.kind})` : "Route rouverte");
  } catch (err) {
    toast(`Coupure impossible : ${err.message}`, "erreur");
  }
}
async function resetScenario() {
  const ok = await confirmDialog({ title: "Réinitialiser le scénario ?", message: "Paramètres par défaut, aucune panne, pas de pluie, aucun quartier ajouté. Les routes coupées et dépotoirs simulés déjà enregistrés en simulation restent dans sim.db.", confirm: "Réinitialiser" });
  if (!ok) return;
  for (const k of PARAM_ORDER) if (S.config.params?.[k]) S.scenario.params[k] = S.config.params[k].default;
  S.scenario.broken.clear();
  S.scenario.districts.clear();
  S.scenario.rain = false;
  S.view.setRain(false);
  S.view.highlightTerritory(null);
  await recalc("Scénario réinitialisé");
}

function setInteraction(mode) {
  S.interaction = mode;
  S.view?.setInteraction(mode);
  const box = $("#mode-interaction");
  box.hidden = mode === "selection";
  if (mode !== "selection") {
    box.replaceChildren(mode === "ajout-depotoir" ? "Cliquez sur le sol pour placer un dépotoir simulé" : "Cliquez sur une route à couper ou à rouvrir",
      el("button", { type: "button", onclick: () => setInteraction("selection") }, ["Annuler"]));
  }
  renderLeft();
}

// --- Sélection --------------------------------------------------------------------------------------------------
function select(info, object = null) {
  S.selection = info;
  S.view?.select(info, object);
  if (info?.kind === "quartier") S.view.highlightTerritory(info.territory.id);
  else if (S.view && !(S.mode === "sim" && S.scenario.districts.size)) S.view.highlightTerritory(null);
  showTab("selection");
  renderSelection();
}
function refreshSelection() {
  if (!S.selection) return renderSelection();
  if (S.selection.kind === "vehicule") {
    const v = (S.plan[S.mode]?.vehicles || []).find((x) => x.id === S.selection.id);
    if (v) S.selection = { ...S.selection, status: v.status, legs: S.view.fleet?.get(v.id)?.userData.legs || S.selection.legs };
  }
  renderSelection();
}

function territoryName(id) {
  return (S.territories.find((t) => t.id === id) || {}).nom || id;
}

const LIBELLES = {
  "depotoir:a_verifier": "Dépotoir à vérifier", "depotoir:confirme": "Dépotoir confirmé", "depotoir:rejete": "Signalement rejeté",
  "nettoyage:a_verifier": "Nettoyage à vérifier", "nettoyage:rejete": "Nettoyage rejeté", "nettoyage:nettoye": "Nettoyé",
};

function renderSelection() {
  const host = $("#onglet-selection");
  const s = S.selection;
  if (!s) {
    host.replaceChildren(el("div", { class: "fiche" }, [
      el("h2", {}, ["Rien de sélectionné"]),
      el("p", { class: "sous" }, ["Cliquez dans la ville sur un signalement, un camion, un point de collecte ou un quartier."]),
      S.mode === "sim" ? el("p", { class: "sous" }, ["En simulation : choisissez « Ajouter un dépotoir » ou « Couper une route » à gauche, puis cliquez dans la ville."]) : null,
    ]));
    return;
  }
  const builders = { signalement: ficheSignalement, simule: ficheSimule, point: fichePoint, vehicule: ficheVehicule, quartier: ficheQuartier, route: ficheRoute, coupure: ficheRoute,
    batiment: ficheBatiment, poi: fichePoi, lieu: fichePoi, tournee: ficheTournee };
  host.replaceChildren(...[].concat((builders[s.kind] || (() => el("p", {}, ["Objet sans fiche."])))(s)));
}

// --- Fiches des objets de la carte OpenStreetMap (vue « carte ») -------------------------------------------------
const TYPES_BATIMENT = { yes: "bâtiment (type non précisé dans OSM)", house: "maison", residential: "habitation", apartments: "immeuble d'habitation",
  school: "école", mosque: "mosquée", church: "église", chapel: "chapelle", hospital: "hôpital", commercial: "commerce", retail: "commerce",
  industrial: "industrie", warehouse: "entrepôt", hangar: "hangar", garage: "garage", construction: "en construction", office: "bureaux",
  public: "bâtiment public", government: "administration", university: "université", hotel: "hôtel", hut: "case", shed: "abri" };

function ficheBatiment({ props: p, lat, lon }) {
  const h = S.view.sourceHauteur(p);
  return el("div", { class: "fiche" }, [
    el("h2", {}, [p.nom || "Bâtiment"]),
    el("p", { class: "sous" }, [`OpenStreetMap · way ${p.osm_id}`]),
    dl([["Type", TYPES_BATIMENT[p.type] || p.type || "—"],
      ["Hauteur affichée", `${fmt.n(h.m)} m`], ["Origine de la hauteur", h.source],
      p.niveaux !== undefined ? ["Niveaux (OSM)", `${p.niveaux}`] : null,
      p.toit ? ["Toit (OSM)", p.toit] : null,
      p.amenite ? ["Usage (OSM)", p.amenite] : null,
      ["Quartier du plan", S.view.territoryAt(lat, lon)?.nom || "hors des quartiers modélisés"]]),
    el("button", { class: "btn", type: "button", onclick: () => S.view.focusLatLon(lat, lon, 120) }, ["Centrer la caméra"]),
    el("p", { class: "vide" }, ["Emprise exacte d'OpenStreetMap. Corriger ou compléter : openstreetmap.org (données ouvertes, ODbL)."]),
  ]);
}

function fichePoi({ props: p }) {
  return el("div", { class: "fiche" }, [
    el("h2", {}, [p.nom || "Lieu sans nom"]),
    el("p", { class: "sous" }, [`OpenStreetMap · ${p.classe || "lieu"}`]),
    dl([["Catégorie", p.famille || p.classe || "—"], p.osm_id ? ["Identifiant OSM", `${p.osm_id}`] : null]),
    el("p", { class: "vide" }, ["Information cartographique : pas une donnée de la mairie."]),
  ]);
}

function ficheTournee({ data: r }) {
  const v = (S.plan[S.mode]?.vehicles || []).find((x) => x.id === String(r.vehicle_id || r.vehicle).split("_trip")[0]);
  if (v) return ficheVehicule(v);
  return el("div", { class: "fiche" }, [el("h2", {}, [`Tournée ${r.vehicle_id || r.vehicle}`]),
    dl([["Arrêts", `${(r.stops || []).length}`], ["Distance", `${fmt.n(r.distance_km)} km`], ["Charge", fmt.t(r.load_kg)]])]);
}

function dl(pairs) {
  return el("dl", {}, pairs.filter(Boolean).flatMap(([k, v]) => [el("dt", {}, [k]), el("dd", {}, [v ?? "—"])]));
}

function ficheSignalement({ data: r }) {
  const isSim = S.mode === "sim";
  const img = el("img", { alt: "Photo floutée du signalement" });
  const histo = el("ol", { class: "histo" }, [el("li", {}, ["Chargement…"])]);
  const actions = el("div", { class: "rangee" });
  if (r.type === "depotoir" && r.statut === "confirme") {
    actions.append(el("button", { class: "btn btn-vert", type: "button", onclick: (e) => transition(e.currentTarget, r, "markClean") }, ["Marquer nettoyé"]));
  }
  if (r.statut === "rejete") {
    actions.append(el("button", { class: "btn btn-jaune", type: "button", onclick: (e) => transition(e.currentTarget, r, "resetCase") }, ["Remettre à vérifier"]));
  }
  actions.append(el("button", { class: "btn", type: "button", onclick: () => S.view.focusLatLon(r.lat, r.lon, 140) }, ["Centrer la caméra"]));
  if (r.photo) {
    call(() => S.api.photo(r.id, isSim ? "sim" : "reel")).then((b) => { img.src = URL.createObjectURL(b); }).catch(() => { img.alt = "Photo indisponible"; });
  }
  call(() => S.api.history(r.id, isSim ? "sim" : "reel")).then((h) => histo.replaceChildren(...h.map((x) => el("li", {}, [
    `${fmt.date(x.quand)} — ${x.qui} : ${x.action}${x.vers?.statut ? ` → ${LIBELLES[`${x.vers.type}:${x.vers.statut}`] || x.vers.statut}` : ""}`]))))
    .catch((err) => histo.replaceChildren(el("li", {}, [`Historique indisponible : ${err.message}`])));
  return el("div", { class: "fiche" }, [
    el("h2", {}, [LIBELLES[`${r.type}:${r.statut}`] || r.statut, isSim ? " " : "", isSim ? el("span", { class: "etiquette-fictive" }, ["fictif"]) : ""]),
    el("p", { class: "sous" }, [`Cas ${r.id}`]),
    r.photo ? img : el("p", { class: "vide" }, ["Pas de photo pour ce cas."]),
    dl([["Signalé le", fmt.date(r.reported_at)], ["Signalé", `${r.nb_signalements} fois`], ["Mis à jour", fmt.date(r.updated_at)],
      ["Position", `${Number(r.lat).toFixed(5)}, ${Number(r.lon).toFixed(5)}`], ["Quartier", S.view.territoryAt(r.lat, r.lon)?.nom || "hors zone modélisée"]]),
    (r.alertes || []).length ? el("div", { class: "alertes-liste" }, r.alertes.map((a, i) => el("div", { class: "alerte-ligne" }, [el("b", {}, [a]), ` — ${r.alertes_libelles?.[i] || ""}`]))) : null,
    actions,
    el("h3", {}, ["Historique"]), histo,
  ]);
}

async function transition(button, r, method) {
  const verbs = { markClean: ["Marquer ce dépotoir comme nettoyé ?", "La brigade devra vérifier le nettoyage sur place."],
    resetCase: ["Remettre ce cas à vérifier ?", "Il reviendra dans la liste de la brigade, sans note."] };
  if (!(await confirmDialog({ title: verbs[method][0], message: verbs[method][1] }))) return;
  await once(button, async () => {
    try {
      const res = await call(() => S.api[method](r.id, S.mode === "sim" ? "sim" : "reel"));
      toast(`Fait : le cas est maintenant « ${LIBELLES[`${res.type}:${res.statut}`] || res.statut} ».`, "ok");
      S.selection = { kind: "signalement", data: res.cas || { ...r, type: res.type, statut: res.statut } };
      await (S.mode === "reel" ? loadReal() : loadSim());
      renderSelection();
    } catch (err) {
      toast(err.status === 409 ? `Refusé : ${err.message}` : `Échec : ${err.message}`, "erreur", 7000);
    }
  });
}

function ficheSimule({ data: d }) {
  return el("div", { class: "fiche" }, [
    el("h2", {}, ["Dépotoir simulé ", el("span", { class: "etiquette-fictive" }, ["fictif"])]),
    el("p", { class: "sous" }, ["Ajouté pour ce scénario (sim.db). Jamais exporté ni versé dans OpenStreetMap."]),
    dl([["Identifiant", d.id], ["Position", `${Number(d.lat).toFixed(5)}, ${Number(d.lon).toFixed(5)}`], ["Masse supposée", d.kg ? `${fmt.int(d.kg)} kg` : "—"]]),
  ]);
}

function fichePoint({ data: p, status, raison }) {
  const plan = S.plan[S.mode];
  const route = (plan?.routes || []).find((r) => (r.stops || []).includes(p.id));
  const labels = { desservi: "Desservi", non_desservi: "Non desservi", reporte: "Reporté (camion en panne)" };
  return el("div", { class: "fiche" }, [
    el("h2", {}, [p.type === "dumpsite" ? "Dépotoir à collecter" : "Point de regroupement"]),
    el("p", { class: "sous" }, [`${p.id}${p.split_of ? ` (partie ${p.part}/${p.parts} de ${p.split_of})` : ""}`]),
    dl([["État", labels[status] || status], ["Demande par passage", `${fmt.int(p.demand_kg)} kg`],
      ["Desservi par", route ? `${route.vehicle_id} (${fmt.n(route.distance_km)} km)` : "aucune tournée"],
      raison ? ["Raison", raison.detail || raison.reason] : null, ["Quartier", S.view.territoryAt(p.lat, p.lon)?.nom || "—"]]),
    el("button", { class: "btn", type: "button", onclick: () => S.view.focusLatLon(p.lat, p.lon, 160) }, ["Centrer la caméra"]),
  ]);
}

function ficheVehicule(v) {
  const plan = S.plan[S.mode];
  const routes = (plan?.routes || []).filter((r) => (r.vehicle_id || "").split("_trip")[0] === v.id);
  const km = routes.reduce((s, r) => s + (r.distance_km || 0), 0);
  const load = routes.reduce((s, r) => s + (r.load_kg || 0), 0);
  const stops = routes.reduce((s, r) => s + (r.stops || []).length, 0);
  const broken = v.status === "en panne";
  const actions = el("div", { class: "rangee" });
  if (S.mode === "sim" && !broken) {
    actions.append(el("button", { class: "btn btn-rouge", type: "button", onclick: async (e) => {
      if (await confirmDialog({ title: `Déclarer ${v.id} en panne ?`, message: "Recalcul partiel : seuls ses arrêts sont redistribués ; ceux qui ne trouvent pas de place seront reportés.", confirm: "Déclarer la panne", danger: true })) {
        await once(e.currentTarget, () => truckDown(v.id));
      }
    } }, ["Déclarer en panne"]));
  }
  if (S.mode === "sim" && broken) {
    actions.append(el("button", { class: "btn btn-vert", type: "button", onclick: (e) => once(e.currentTarget, () => truckRepair(v.id)) }, ["Remettre en service"]));
  }
  if (S.mode === "reel") actions.append(el("p", { class: "vide" }, ["Les pannes se simulent en mode Simulation."]));
  return el("div", { class: "fiche" }, [
    el("h2", {}, [`Camion ${v.id.replace("truck", "n° ")}`]),
    el("p", { class: "sous" }, [broken ? "En panne : immobilisé, feux de détresse" : routes.length ? "En service : animation le long de ses tournées calculées" : "En service, sans tournée dans ce plan (au dépôt)"]),
    dl([["Identifiant", v.id], ["État", v.status], ["Trajets", `${routes.length}`], ["Arrêts", `${stops}`],
      ["Distance", `${fmt.n(km)} km`], ["Charge", fmt.t(load)], ["Trajet en cours", v.leg || (routes[0]?.vehicle_id ?? "—")]]),
    actions,
    el("p", { class: "vide" }, ["La vitesse à l'écran est accélérée ; les distances et charges sont celles du plan."]),
  ]);
}

function ficheQuartier({ territory: t }) {
  const inside = (o) => S.view.territoryAt(o.lat, o.lon)?.id === t.id;
  const reports = (S.mode === "reel" ? S.reports : S.simReports).filter(inside);
  const plan = S.plan[S.mode];
  const pts = (plan?.consolidation_points || []).filter(inside);
  const unserved = new Set((plan?.unserved || []).map((u) => u.point_id));
  const postponed = new Set((plan?.postponed || []).map((u) => u.id));
  const counts = {};
  for (const r of reports) counts[LIBELLES[`${r.type}:${r.statut}`] || r.statut] = (counts[LIBELLES[`${r.type}:${r.statut}`] || r.statut] || 0) + 1;
  const inScenario = S.scenario.districts.has(t.id);
  return el("div", { class: "fiche" }, [
    el("h2", {}, [t.nom]),
    el("p", { class: "sous" }, [t.secteur ? "Secteur de l'équipe (zone pilote)." : t.approximate
      ? "Emprise approximative (cellule autour du nœud OSM du quartier) : pas une limite officielle." : "Quartier."]),
    dl([[S.mode === "reel" ? "Signalements" : "Cas simulés", `${reports.length}`],
      ...Object.entries(counts).map(([k, n]) => [`· ${k}`, `${n}`]),
      ["Points du plan", plan ? `${pts.length}` : "aucun plan"],
      plan ? ["· non desservis", `${pts.filter((p) => unserved.has(p.id)).length}`] : null,
      plan ? ["· reportés", `${pts.filter((p) => postponed.has(p.id)).length}`] : null]),
    S.mode === "sim" && !t.secteur ? el("button", { class: `btn ${inScenario ? "" : "btn-jaune"}`, type: "button",
      onclick: (e) => once(e.currentTarget, () => toggleDistrict(t.id, !inScenario)) }, [inScenario ? "Retirer ce quartier du scénario" : "Ajouter ce quartier au scénario"]) : null,
    el("button", { class: "btn", type: "button", onclick: () => S.view.focusTerritory(t.id) }, ["Centrer la caméra"]),
  ]);
}

function ficheRoute(info) {
  const road = info.road || (info.data && S.view.roadById.get(info.data.edge_id));
  if (!road) return el("div", { class: "fiche" }, [el("h2", {}, ["Route coupée"]), dl([["Arête", info.data?.edge_id]])]);
  const cut = S.scenario.cuts.has(road.id) || [...S.scenario.cuts.keys()].some((k) => S.view.roadById.get(k) === road);
  return el("div", { class: "fiche" }, [
    el("h2", {}, [road.name || "Voie sans nom"]),
    el("p", { class: "sous" }, [`${road.kind} · ${road.paved ? "revêtue" : "non revêtue (latérite)"} · ${road.truck ? "praticable aux camions" : "hors réseau camion"}`]),
    dl([["Identifiant", road.id], ["État", cut ? "Coupée (simulation)" : "Ouverte"]]),
    S.mode === "sim" ? el("button", { class: `btn ${cut ? "btn-vert" : "btn-rouge"}`, type: "button",
      onclick: (e) => once(e.currentTarget, () => cutRoad(road, !cut)) }, [cut ? "Rouvrir la route" : "Couper cette route"]) : null,
  ]);
}

/** Téléchargement d'un fichier produit par l'API (le contenu vient du serveur, rien n'est recalculé ici). */
function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([typeof content === "string" ? content : JSON.stringify(content, null, 1)], { type }));
  const a = el("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

async function exporter(button, kind) {
  await once(button, async () => {
    try {
      if (kind === "geojson") {
        const fc = await call(() => S.api.exportReports());
        download("signalements-verifies.geojson", fc, "application/geo+json");
        toast(`${fc.features.length} signalement(s) vérifié(s) exporté(s), licence ${fc.license}.`, "ok");
      } else if (kind === "osm") {
        download("depotoirs.osm", await call(() => S.api.exportOsm()), "application/xml");
        toast("Fichier OSM téléchargé : à relire dans JOSM, rien n'est envoyé à OpenStreetMap.", "ok", 6000);
      } else {
        const plan = S.plan[S.mode];
        download(`plan-${plan.plan_id}.geojson`, await call(() => S.api.exportPlan(plan.plan_id)), "application/geo+json");
        toast("Plan exporté en GeoJSON.", "ok");
      }
    } catch (err) {
      toast(`Export impossible : ${err.message}`, "erreur");
    }
  });
}

// --- Panneau gauche --------------------------------------------------------------------------------------------
function renderLeft() {
  const host = $("#panneau-gauche");
  host.replaceChildren(...(S.mode === "reel" ? leftReal() : leftSim()));
}

function leftReal() {
  const groups = [["a_verifier", "À vérifier", 0xfcd116], ["confirme", "Confirmés", 0xef2b2d], ["rejete", "Rejetés", 0x8c8c8c], ["nettoyage", "Nettoyage", 0x2d8fa0]];
  const count = (k) => S.reports.filter((r) => (r.type === "nettoyage" && r.statut !== "rejete" ? "nettoyage" : r.statut) === k).length;
  const filtres = el("div", { class: "filtres" }, groups.map(([k, label, c]) => el("button", {
    type: "button", class: `filtre${S.filtres.has(k) ? " actif" : ""}`, "aria-pressed": String(S.filtres.has(k)),
    onclick: () => { if (S.filtres.has(k)) S.filtres.delete(k); else S.filtres.add(k); drawReports(); renderLeft(); },
  }, [el("span", { class: "puce", style: `background:#${c.toString(16).padStart(6, "0")}` }), `${label} (${count(k)})`])));
  const list = el("ul", { class: "liste" }, S.reports.filter((r) => S.filtres.has(r.type === "nettoyage" && r.statut !== "rejete" ? "nettoyage" : r.statut))
    .slice(0, 200).map((r) => el("li", { onclick: () => { select({ kind: "signalement", data: r }); S.view.focusLatLon(r.lat, r.lon, 180); } }, [
      el("span", { class: "puce", style: `background:#${(S.view.statutsLegend?.[`${r.type}:${r.statut}`]?.couleur ?? 0xfcd116).toString(16).padStart(6, "0")}` }),
      el("div", {}, [LIBELLES[`${r.type}:${r.statut}`] || r.statut, el("div", { class: "meta" }, [`${fmt.date(r.reported_at)} · signalé ${r.nb_signalements} fois`])]),
    ])));
  const ecartes = el("ul", { class: "liste" }, S.ecartes.slice(0, 100).map((e) => el("li", {}, [
    el("div", { style: "flex:1" }, [e.motif, el("div", { class: "meta" }, [`${fmt.date(e.quand)} · ${e.motif_code}`])]),
    e.remettable ? el("button", { class: "btn", type: "button", onclick: async (ev) => {
      ev.stopPropagation();
      if (!(await confirmDialog({ title: "Remettre cet envoi à vérifier ?", message: "Un nouveau cas à vérifier sera créé pour la brigade (sans photo)." }))) return;
      await once(ev.currentTarget, async () => {
        try { await call(() => S.api.resetEcarte(e.id, "reel")); toast("Remis à vérifier.", "ok"); await loadReal(); }
        catch (err) { toast(`Échec : ${err.message}`, "erreur"); }
      });
    } }, ["Remettre"]) : el("span", { class: "meta" }, ["sans position"]),
  ])));
  const planReel = S.plan.reel;
  return [
    el("section", { class: "bloc" }, [
      el("h3", {}, ["Signalements réels", el("label", { class: "meta" }, [el("input", { type: "checkbox", checked: S.inclureNettoyes || null,
        onchange: (e) => { S.inclureNettoyes = e.target.checked; loadReal(); } }), " nettoyés"])]),
      filtres,
      S.reports.length ? list : el("p", { class: "vide" }, ["Aucun signalement réel pour l'instant."]),
    ]),
    el("section", { class: "bloc" }, [
      el("h3", {}, [`Écartés d'office (${S.ecartes.length})`]),
      el("p", {}, ["Envois écartés par le tri (forme, position, date, photo), avec leur motif."]),
      S.ecartes.length ? ecartes : el("p", { class: "vide" }, ["Aucun envoi écarté."]),
    ]),
    el("section", { class: "bloc" }, [
      el("h3", {}, ["Plan de collecte réel"]),
      el("p", {}, ["Calculé avec les paramètres de la commune et les seuls dépotoirs confirmés par la brigade."]),
      el("button", { class: "btn btn-primaire btn-large", type: "button", onclick: (e) => once(e.currentTarget, () => recalc("Plan réel")) },
        [planReel ? "Recalculer le plan réel" : "Calculer le plan réel"]),
      planReel ? el("button", { class: "btn btn-large", type: "button", style: "margin-top:.4rem", onclick: (e) => exporter(e.currentTarget, "plan") }, ["Exporter le plan (GeoJSON)"]) : null,
    ]),
    el("section", { class: "bloc" }, [
      el("h3", {}, ["Données ouvertes"]),
      el("p", {}, ["Signalements réels confirmés ou nettoyés, sans photo ni donnée personnelle (ODbL). Jamais de cas simulé."]),
      el("div", { class: "rangee" }, [
        el("button", { class: "btn", type: "button", onclick: (e) => exporter(e.currentTarget, "geojson") }, ["GeoJSON"]),
        el("button", { class: "btn", type: "button", onclick: (e) => exporter(e.currentTarget, "osm") }, ["Fichier OSM (JOSM)"]),
      ]),
    ]),
  ];
}

function slider(key) {
  const spec = S.config.params[key];
  if (!spec) return null;
  const isRate = key === "subscription_rate";
  const step = isRate ? 0.01 : key === "budget" ? 100000 : key === "population" ? 10000 : key.endsWith("_kg") ? 50 : 1;
  const val = S.scenario.params[key];
  const show = (v) => (isRate ? fmt.pct(v) : key === "budget" ? fmt.fcfa(v) : fmt.int(v));
  const out = el("output", {}, [show(val)]);
  const input = el("input", { type: "range", min: spec.min, max: spec.max, step, value: val, "aria-label": spec.label,
    oninput: (e) => { const v = Number(e.target.value); S.scenario.params[key] = v; out.textContent = show(v); scheduleRecalc(`${spec.label} : ${show(v)}`); } });
  return el("div", { class: "ligne-param" }, [el("label", {}, [spec.label.replace("a la", "à la").replace("Capacite", "Capacité").replace("Frequence", "Fréquence"), out]), input]);
}

function leftSim() {
  const plan = S.plan.sim;
  const vehicles = plan?.vehicles || [];
  const select = el("select", { class: "champ", "aria-label": "Camion du plan" }, [
    el("option", { value: "" }, ["Choisir un camion du plan…"]),
    ...vehicles.filter((v) => v.status !== "en panne").map((v) => el("option", { value: v.id }, [`${v.id} — ${(v.trips || []).length} trajet(s)`]))]);
  const terrSelect = el("select", { class: "champ", "aria-label": "Quartier à ajouter" }, [
    el("option", { value: "" }, ["Choisir un quartier…"]),
    ...S.territories.filter((t) => !S.scenario.districts.has(t.id)).map((t) => el("option", { value: t.id }, [`${t.nom}${t.approximate ? " (emprise approx.)" : ""}`]))]);
  const broken = [...S.scenario.broken];
  return [
    el("section", { class: "bloc" }, [
      el("h3", {}, ["Paramètres du scénario"]),
      el("p", {}, ["Valeurs et bornes lues dans la configuration de la commune. Le plan se recalcule après chaque réglage."]),
      ...PARAM_ORDER.map(slider),
    ]),
    el("section", { class: "bloc" }, [
      el("h3", {}, ["Événements"]),
      el("div", { class: "ligne-param" }, [el("label", {}, ["Panne d'un camion"]), select,
        el("button", { class: "btn btn-rouge btn-large", type: "button", style: "margin-top:.35rem", onclick: async (e) => {
          if (!select.value) return toast("Choisissez d'abord un camion (liste ou clic dans la ville).", "info");
          await once(e.currentTarget, () => truckDown(select.value));
        } }, ["Déclarer la panne"]),
        broken.length ? el("p", {}, [`En panne : ${broken.join(", ")}`]) : null]),
      el("div", { class: "ligne-param" }, [el("label", {}, ["Saison des pluies", el("output", {}, [S.scenario.rain ? "active" : "non"])]),
        el("button", { class: `btn btn-large ${S.scenario.rain ? "actif" : ""}`, type: "button", onclick: (e) => once(e.currentTarget, () => toggleRain(!S.scenario.rain)) },
          [S.scenario.rain ? "Arrêter la pluie" : "Déclencher la saison des pluies"])]),
      el("div", { class: "ligne-param" }, [el("label", {}, ["Nouveau quartier"]), terrSelect,
        el("button", { class: "btn btn-jaune btn-large", type: "button", style: "margin-top:.35rem", onclick: async (e) => {
          if (!terrSelect.value) return toast("Choisissez un quartier.", "info");
          await once(e.currentTarget, () => toggleDistrict(terrSelect.value, true));
        } }, ["Ajouter au scénario"]),
        S.scenario.districts.size ? el("p", {}, [`Ajoutés : ${[...S.scenario.districts].map(territoryName).join(", ")}`]) : null]),
      el("div", { class: "rangee" }, [
        el("button", { class: `btn ${S.interaction === "ajout-depotoir" ? "actif" : ""}`, type: "button",
          onclick: () => setInteraction(S.interaction === "ajout-depotoir" ? "selection" : "ajout-depotoir") }, ["Ajouter un dépotoir"]),
        el("button", { class: `btn ${S.interaction === "coupure-route" ? "actif" : ""}`, type: "button",
          onclick: () => setInteraction(S.interaction === "coupure-route" ? "selection" : "coupure-route") }, ["Couper une route"]),
      ]),
      S.scenario.cuts.size ? el("p", {}, [`${S.scenario.cuts.size} route(s) coupée(s) en simulation.`]) : null,
    ]),
    el("section", { class: "bloc" }, [
      el("h3", {}, ["Scénario"]),
      el("div", { class: "rangee" }, [
        el("button", { class: "btn btn-primaire", type: "button", onclick: (e) => once(e.currentTarget, () => recalc("Recalcul demandé")) }, ["Recalculer"]),
        el("button", { class: "btn", type: "button", onclick: resetScenario }, ["Réinitialiser"]),
        plan ? el("button", { class: "btn", type: "button", onclick: (e) => exporter(e.currentTarget, "plan") }, ["Exporter le plan"]) : null,
      ]),
      el("p", {}, [`Cas simulés affichés : ${S.simReports.length}. Dépotoirs ajoutés : ${S.simDumps.length}.`]),
    ]),
  ];
}

// --- Statut, indicateurs, légende ------------------------------------------------------------------------------
function renderStatus(computing = null) {
  const box = $("#statut-plan");
  const stale = S.stale[S.mode];
  const plan = S.plan[S.mode];
  if (computing || S.busy) {
    box.className = "statut statut-calcul";
    box.textContent = computing || "Recalcul en cours…";
  } else {
    const st = planStatus(plan, stale);
    box.className = `statut statut-${st.niveau}`;
    box.textContent = st.titre;
    box.title = st.details.join(" ");
  }
  const per = $("#bandeau-perime");
  if (S.view?.kind === "2d") return;
  per.hidden = !stale;
  if (stale) per.textContent = `Plan précédent affiché — recalcul impossible (${stale.message}). Les chiffres et la carte ne reflètent pas le dernier réglage.`;
  const t = S.timings;
  $("#chrono").textContent = plan && t.server !== undefined
    ? `Serveur ${fmt.ms(t.server)} · requête ${fmt.ms(t.request)} · rendu ${fmt.ms(t.render)}${t.sim ? ` · simulation ${fmt.ms(t.sim)}` : ""}` : "";
}

function kpi(label, value, note = "", cls = "") {
  return el("div", { class: `kpi ${cls}` }, [el("span", {}, [label]), el("b", {}, [value]), note ? el("small", {}, [note]) : null]);
}

function renderKpis() {
  const host = $("#indicateurs");
  const plan = S.plan[S.mode];
  const sim = S.sim[S.mode];
  const items = [];
  if (S.mode === "reel") {
    const c = (st) => S.reports.filter((r) => r.statut === st).length;
    items.push(kpi("À vérifier", fmt.int(c("a_verifier")), "brigade"), kpi("Confirmés", fmt.int(c("confirme"))), kpi("Rejetés", fmt.int(c("rejete"))),
      kpi("Écartés d'office", fmt.int(S.ecartes.length), "tri automatique"));
  }
  if (plan) {
    const n = plan.consolidation_points.length;
    const ch = plan.checks || {};
    const served = n - (ch.unserved_count ?? plan.unserved.length) - (ch.postponed_count ?? plan.postponed?.length ?? 0);
    const active = (plan.vehicles || []).filter((v) => v.status !== "en panne").length;
    const unservedTerr = new Set((plan.unserved || []).map((u) => plan.consolidation_points.find((p) => p.id === u.point_id))
      .filter(Boolean).map((p) => S.view.territoryAt(p.lat, p.lon)?.id).filter(Boolean));
    items.push(
      kpi("Points desservis", `${fmt.int(served)} / ${fmt.int(n)}`, "plan"),
      kpi("Non desservis", fmt.int(ch.unserved_count), ch.unserved_ratio !== undefined ? fmt.pct(ch.unserved_ratio) : "", ch.unserved_count ? "alerte" : "ok"),
      kpi("Reportés", fmt.int(ch.postponed_count ?? 0), "panne", ch.postponed_count ? "alerte" : ""),
      kpi("Camions en service", `${active} / ${(plan.vehicles || []).length}`),
      kpi("Coût du passage", fmt.fcfa(plan.totals?.cost), "carburant estimé"),
      kpi("Collecté (plan)", fmt.t(plan.totals?.collected_kg), "par passage"),
      kpi("Quartiers touchés", fmt.int(unservedTerr.size), "avec point non desservi"),
    );
  }
  if (sim) {
    items.push(
      kpi("Part ramassée", sim.part_ramassee === null ? "—" : fmt.pct(sim.part_ramassee, 1), `${sim.jours} jours`, "fictif"),
      kpi("Dépotoirs restants", fmt.int(sim.depotoirs_restants), "fin de simulation", "fictif"),
      kpi("Coût simulé", fmt.fcfa(sim.cout_fcfa), `${sim.jours} jours`, "fictif"),
    );
  }
  if (!items.length) items.push(kpi("Plan", "—", S.mode === "reel" ? "calculer le plan réel à gauche" : "calcul en cours"));
  host.replaceChildren(...items);
}

function renderLegend() {
  const L = S.view.statutsLegend;
  const sw = (c) => el("span", { class: "puce", style: `background:#${c.toString(16).padStart(6, "0")}` });
  const box = $("#legende");
  box.classList.toggle("repliee", S.view.kind === "carte");
  box.replaceChildren(
    // Carte : légende repliée au départ (la carte reste dégagée) ; un clic l'ouvre.
    el("button", { class: "legende-titre", type: "button", "aria-expanded": String(S.view.kind !== "carte"), onclick: (e) => {
      const folded = box.classList.toggle("repliee");
      e.currentTarget.setAttribute("aria-expanded", String(!folded));
      e.currentTarget.textContent = folded ? "Légende ▸" : "Légende ▾";
    } }, [S.view.kind === "carte" ? "Légende ▸" : "Légende ▾"]),
    el("h4", {}, ["Signalements"]),
    el("ul", {}, Object.values(L).map((s) => el("li", {}, [sw(s.couleur), s.libelle]))),
    el("h4", {}, ["Plan"]),
    el("ul", {}, [
      el("li", {}, [sw(0x009e49), "Point desservi"]), el("li", {}, [sw(0xef2b2d), "Non desservi"]),
      el("li", {}, [sw(0xe67e22), "Reporté"]), el("li", {}, [el("span", { class: "trait", style: "background:linear-gradient(90deg,#1f6fb2 0 33%,#0f8b8d 33% 66%,#7a5195 66%)" }), "Tournée (couleur du camion)"]),
      el("li", {}, [sw(0x9a9a92), "Camion au dépôt"]), el("li", {}, [el("span", { class: "trait", style: "background:#ef2b2d;height:8px" }), "Route coupée"]),
    ]),
  );
}

// --- Onglets, caméra, survol -----------------------------------------------------------------------------------
function showTab(name) {
  for (const b of document.querySelectorAll(".onglets button")) {
    const on = b.dataset.onglet === name;
    b.classList.toggle("actif", on);
    b.setAttribute("aria-selected", String(on));
  }
  for (const n of ["selection", "comparer", "historique"]) $(`#onglet-${n}`).hidden = n !== name;
  if (name === "comparer") renderCompare(S, ctx);
  if (name === "historique") renderHistory(S, ctx);
}

const ctx = { call, showTab, toast, openPlan, select };

/** Rouvre un plan enregistré (historique) : affiché comme plan historique, pas comme le plan actif. */
async function openPlan(planId) {
  try {
    const plan = await call(() => S.api.getPlan(planId));
    const mode = plan.data_mode === "sim" ? "sim" : "reel";
    if (S.mode !== mode) await setMode(mode);
    S.plan[mode] = plan;
    S.sim[mode] = null;
    S.view.setPlan(plan);
    S.timings = { server: plan.compute_ms };
    renderKpis();
    renderStatus();
    toast(`Plan historique ${planId} affiché (pas le scénario en cours de réglage).`, "info", 6000);
  } catch (err) {
    toast(`Plan introuvable : ${err.message}`, "erreur");
  }
}

function bindView() {
  const v = S.view;
  v.on("select", (info, object) => select(info, object));
  v.on("ground", (p) => {
    if (S.mode !== "sim") return;
    setInteraction("selection");
    addDump(p);
  });
  v.on("road", (road) => {
    if (!road) return toast("Aucune route à cet endroit : cliquez sur une rue.", "info");
    setInteraction("selection");
    select({ kind: "route", road });
  });
  const tip = $("#infobulle");
  v.on("hover", (info, e) => {
    if (!info || !e) { tip.hidden = true; return; }
    const r = $("#scene").getBoundingClientRect();
    const text = info.kind === "signalement" ? `${info.label} — ${fmt.date(info.data.reported_at)}`
      : info.kind === "vehicule" ? `Camion ${info.id} — ${info.status}`
        : info.kind === "point" ? `${info.data.type === "dumpsite" ? "Dépotoir" : "Point de regroupement"} — ${fmt.int(info.data.demand_kg)} kg — ${info.status.replace("_", " ")}`
          : info.kind === "route" ? `${info.road.name || info.road.kind} — cliquer pour ${S.scenario.cuts.has(info.road.id) ? "rouvrir" : "couper"}`
            : info.kind === "simule" ? "Dépotoir simulé (fictif)" : info.kind === "coupure" ? "Route coupée" : "";
    if (!text) { tip.hidden = true; return; }
    tip.textContent = text;
    tip.hidden = false;
    tip.style.left = `${e.clientX - r.left + 14}px`;
    tip.style.top = `${e.clientY - r.top + 14}px`;
  });
  v.onCamera((m) => { for (const b of document.querySelectorAll("[data-cam=rue]")) b.classList.toggle("actif", m === "rue"); });
}

function bindChrome() {
  $("#mode-reel").addEventListener("click", () => S.mode !== "reel" && setMode("reel"));
  $("#mode-sim").addEventListener("click", () => S.mode !== "sim" && setMode("sim"));
  $("#aide-btn").addEventListener("click", () => { $("#aide").hidden = false; });
  $("#aide-fermer").addEventListener("click", () => { $("#aide").hidden = true; });
  if (S.view.kind === "carte") bindCarte();
  // Panneaux repliables : la ville reste en plein cadre, seule la surcouche se masque.
  for (const [id, cls] of [["#replier-gauche", "gauche-replie"], ["#replier-droit", "droit-replie"]]) {
    $(id).addEventListener("click", (e) => {
      const replie = document.body.classList.toggle(cls);
      e.currentTarget.setAttribute("aria-expanded", String(!replie));
    });
  }
  for (const b of document.querySelectorAll(".onglets button")) b.addEventListener("click", () => showTab(b.dataset.onglet));
  let playing = true;
  for (const b of document.querySelectorAll("[data-cam]")) {
    b.addEventListener("click", () => {
      const a = b.dataset.cam;
      if (a !== "rue") S.view.exitStreet?.();
      if (a === "dessus") S.view.overview();
      if (a === "immersive") S.view.immersive();
      if (a === "recentrer") S.view.reset();
      if (a === "rue") { if (b.classList.contains("actif")) S.view.exitStreet(); else S.view.street(); }
      if (a === "animation") {
        playing = !playing;
        S.view.setPlaying(playing);
        b.textContent = playing ? "Pause" : "Lecture";
        b.setAttribute("aria-pressed", String(playing));
      }
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { if (!$("#aide").hidden) $("#aide").hidden = true; else if (S.interaction !== "selection") setInteraction("selection"); else select(null); }
  });
}

// --- Carte : recherche, relief, ambiance ------------------------------------------------------------------------------
function bindCarte() {
  const v = S.view;
  const champ = $("#recherche");
  const liste = $("#recherche-resultats");
  let resultats = [];
  let actif = -1;
  import("./carte/recherche.js").then(({ chargerIndex, chercher }) => {
    chargerIndex().catch((err) => toast(`Recherche limitée : ${err.message}`, "info", 6000));
    const extras = () => [
      ...S.territories.map((t) => ({ n: t.nom, t: "Quartier du plan", extra: true, territoire: t.id })),
      ...(S.plan[S.mode]?.vehicles || []).map((c) => ({ n: `Camion ${c.id.replace("truck", "n° ")}`, t: S.mode === "sim" ? "Camion (simulé)" : "Camion du plan", extra: true, camion: c.id })),
    ];
    const afficher = () => {
      liste.replaceChildren(...resultats.map((r, i) => el("li", { role: "option", id: `rr-${i}`, "aria-selected": String(i === actif),
        class: i === actif ? "actif" : "", onmousedown: (e) => { e.preventDefault(); choisir(r); } }, [el("b", {}, [r.n]), el("span", {}, [r.t])])));
      liste.hidden = !resultats.length;
      champ.setAttribute("aria-expanded", String(!liste.hidden));
    };
    const choisir = async (r) => {
      champ.value = r.n;
      resultats = [];
      afficher();
      champ.blur();
      if (r.camion) {
        const o = v.fleet.get(r.camion);
        if (o) {
          const [lat, lon] = v.proj.toLatLon(o.position.x, o.position.z);
          await v.focusLatLon(lat, lon, 160);
          select({ ...o.userData }, o);
        }
      } else if (r.territoire && v.city.territories.some((t) => t.id === r.territoire)) {
        await v.focusTerritory(r.territoire);
        select({ kind: "quartier", territory: v.city.territories.find((t) => t.id === r.territoire) });
      } else if (r.b) {
        await v.focusLngLatBounds([[r.b[0], r.b[1]], [r.b[2], r.b[3]]]);
        select({ kind: "lieu", props: { nom: r.n, classe: r.t.toLowerCase(), famille: r.t } });
      } else if (r.c) {
        v.focusLatLon(r.c[1], r.c[0], r.z >= 17 ? 140 : 900);
        select({ kind: "lieu", props: { nom: r.n, classe: r.t.toLowerCase(), famille: r.t } }, { lonlat: r.c });
      }
    };
    champ.addEventListener("input", () => { resultats = chercher(champ.value, extras()); actif = resultats.length ? 0 : -1; afficher(); });
    champ.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!resultats.length) return;
        actif = (actif + (e.key === "ArrowDown" ? 1 : -1) + resultats.length) % resultats.length;
        afficher();
        champ.setAttribute("aria-activedescendant", `rr-${actif}`);
      } else if (e.key === "Enter" && resultats[actif]) {
        e.preventDefault();
        choisir(resultats[actif]);
      } else if (e.key === "Escape") {
        resultats = [];
        afficher();
        e.stopPropagation();
      }
    });
    champ.addEventListener("blur", () => setTimeout(() => { resultats = []; afficher(); }, 120));
  });
  const relief = $("#vue-2d3d");
  relief.addEventListener("click", () => {
    const oui = relief.getAttribute("aria-pressed") !== "true";
    relief.setAttribute("aria-pressed", String(oui));
    relief.textContent = oui ? "3D" : "2D";
    v.setVue3D(oui);
  });
  const amb = $("#ambiance");
  amb.value = v.ambiance;
  amb.addEventListener("change", () => v.setAmbiance(amb.value));
}

init().catch((err) => {
  console.error(err);
  $("#chargement-etape").textContent = `Erreur au démarrage : ${err.message}`;
});
