// Brigade Laabal : cas « à vérifier » (dépotoir ou nettoyage), photo floutée, alertes du tri, confirmer / rejeter.
// Décisions hors connexion : file IndexedDB (opId), synchronisées ensuite ; un 409 est montré comme un conflit,
// jamais comme un succès. Le code de rôle n'est pas une sécurité : le serveur vérifie chaque appel.
import { ApiError, createApi, isMockMode, once, roleCode } from "/dashboard/shared/api.js";
import { opId, queue } from "/dashboard/shared/store.js";
import { $, askCode, confirmDialog, el, fmt, mockBanner, toast } from "/dashboard/shared/ui.js";

const STORE = "decisions";
const POLL_MS = 10000;
const TYPE = { depotoir: "Dépotoir à vérifier", nettoyage: "Nettoyage à vérifier" };
const ACTION = { confirmer: "confirmé", rejeter: "rejeté" };
const state = { api: null, mode: "reel", cases: [], seen: new Set(), pending: new Map(), me: null, current: null, photos: new Map() };

function distance(a, b) {
  const R = 6371000;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

async function ensureCode(force = false) {
  if (!force && roleCode.get("brigade")) return;
  // Une seule demande à la fois, même si plusieurs appels reçoivent un 401 en même temps.
  state.asking ??= askCode({ role: "brigade", title: "Code de la brigade", hint: "Saisissez le code d'accès de la brigade Laabal." })
    .then((code) => { roleCode.set("brigade", code); })
    .finally(() => { state.asking = null; });
  await state.asking;
}

async function handleAuth(err) {
  if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
    roleCode.clear("brigade");
    if (!state.asking) toast(err.message, "erreur");
    await ensureCode(true);
    return true;
  }
  return false;
}

// --- Liste ----------------------------------------------------------------------------------------------------
async function load({ silent = false } = {}) {
  if (!navigator.onLine) { render(); return; }
  try {
    const cases = await state.api.reports({ mode: state.mode });
    const fresh = cases.filter((c) => !state.seen.has(c.id));
    if (state.seen.size && fresh.length) {
      $("#nouveaux").textContent = `${fresh.length} nouveau${fresh.length > 1 ? "x" : ""}`;
      $("#nouveaux").hidden = false;
      if (navigator.vibrate && document.visibilityState === "visible") navigator.vibrate(150);
    }
    for (const c of cases) state.seen.add(c.id);
    state.cases = cases;
    $("#etat").className = "etat";
    $("#etat").textContent = cases.length ? `${cases.length} cas à vérifier — mis à jour à ${new Date().toLocaleTimeString("fr-FR")}`
      : "Aucun cas à vérifier pour l'instant.";
  } catch (err) {
    if (await handleAuth(err)) return load();
    $("#etat").className = "etat erreur";
    $("#etat").textContent = `${err.message} La liste affichée peut être ancienne.`;
    if (!silent) toast(err.message, "erreur");
  }
  render();
}

function render() {
  const list = $("#liste");
  const pendingIds = new Set([...state.pending.values()].map((d) => d.caseId));
  list.replaceChildren(...state.cases.map((c) => {
    const pending = pendingIds.has(c.id);
    const d = state.me ? distance(state.me, c) : null;
    const thumb = state.photos.get(c.id);
    return el("li", {}, [el("button", { class: `carte${pending ? " en-attente" : ""}`, type: "button", onclick: () => openCase(c) }, [
      thumb ? el("img", { src: thumb, alt: "" }) : el("div", { class: "vignette", "aria-hidden": "true" }),
      el("div", {}, [
        el("span", { class: `type type-${c.type}` }, [TYPE[c.type] || c.type]),
        el("div", { class: "ligne" }, [`Signalé le ${fmt.date(c.reported_at)}`]),
        el("div", { class: "ligne" }, [
          el("span", { class: "compteur" }, [`Signalé ${c.nb_signalements} fois`]),
          d !== null ? ` · à ${d < 1000 ? `${Math.round(d)} m` : `${fmt.n(d / 1000)} km`}` : "",
        ]),
        el("div", { class: "pills" }, [
          ...(c.alertes || []).map((a, i) => el("span", { class: "pill pill-alerte", title: c.alertes_libelles?.[i] || a }, [alerteCourte(a)])),
          pending ? el("span", { class: "pill" }, ["Décision en attente de synchronisation"]) : null,
        ]),
      ]),
    ]), el("button", { class: "lien-carte", type: "button", onclick: () => ouvrirCarte(c) }, ["Voir sur la carte"])]);
  }));
  if (carte.ouverte) majCarte();
  for (const c of state.cases.slice(0, 12)) loadThumb(c);
  const waiting = [...state.pending.values()];
  $("#attente").hidden = !waiting.length;
  $("#attente").textContent = waiting.length
    ? `${waiting.length} décision(s) enregistrée(s) sur le téléphone, pas encore reçue(s) par le serveur : envoi automatique au retour du réseau.` : "";
}

const ALERTES_COURTES = { DOUBLON_PROBABLE: "Doublon probable", PHOTO_DEJA_VUE: "Photo déjà vue", PRES_PLAN_EAU: "Près d'un plan d'eau",
  HORS_SECTEUR: "Hors secteur", GPS_IMPRECIS: "GPS imprécis", FLOUTAGE_NON_VERIFIE: "Floutage non vérifié", ECARTE_REMIS: "Remis par la mairie",
  CAS_SIMULE: "Cas simulé" };
const alerteCourte = (a) => ALERTES_COURTES[a] || a;

async function loadThumb(c) {
  if (!c.photo || state.photos.has(c.id) || !navigator.onLine) return;
  state.photos.set(c.id, null);
  try {
    const blob = await state.api.photo(c.id, state.mode);
    state.photos.set(c.id, URL.createObjectURL(blob));
    render();
  } catch {
    state.photos.delete(c.id);
  }
}

// --- Détail et décision --------------------------------------------------------------------------------------
async function openCase(c) {
  state.current = c;
  $("#detail").hidden = false;
  $("#detail-titre").textContent = TYPE[c.type] || "Cas";
  const img = $("#detail-photo");
  img.removeAttribute("src");
  $("#photo-etat").textContent = c.photo ? "Chargement de la photo floutée…" : "Pas de photo pour ce cas.";
  const infos = [
    ["Type", TYPE[c.type] || c.type], ["Signalé le", fmt.date(c.reported_at)], ["Signalements", `${c.nb_signalements}`],
    ["Position", `${Number(c.lat).toFixed(5)}, ${Number(c.lon).toFixed(5)}`],
  ];
  if (state.me) infos.push(["Distance", `${Math.round(distance(state.me, c))} m`]);
  $("#detail-infos").replaceChildren(...infos.flatMap(([k, v]) => [el("dt", {}, [k]), el("dd", {}, [v])]),
    el("dt", {}, ["Y aller"]), el("dd", {}, [el("button", { type: "button", class: "lien-carte lien-carte-fiche", onclick: () => { closeCase(); ouvrirCarte(c); } }, ["Voir sur la carte de la brigade"])]));
  $("#detail-alertes").replaceChildren(...(c.alertes || []).map((a, i) => el("div", { class: "alerte" }, [
    el("b", {}, [alerteCourte(a)]), " — ", c.alertes_libelles?.[i] || ""])));
  $("#detail-histo").replaceChildren(el("li", {}, ["Chargement…"]));
  const pending = [...state.pending.values()].some((d) => d.caseId === c.id);
  $("#confirmer").disabled = pending;
  $("#rejeter").disabled = pending;
  if (c.photo) {
    try {
      const url = state.photos.get(c.id) || URL.createObjectURL(await state.api.photo(c.id, state.mode));
      state.photos.set(c.id, url);
      if (state.current === c) { img.src = url; $("#photo-etat").textContent = "Photo floutée par le serveur (visages et plaques)."; }
    } catch (err) {
      $("#photo-etat").textContent = `Photo indisponible : ${err.message}`;
    }
  }
  try {
    const h = await state.api.history(c.id, state.mode);
    if (state.current === c) {
      $("#detail-histo").replaceChildren(...h.map((x) => el("li", {}, [
        `${fmt.date(x.quand)} — ${x.qui} : ${x.action}${x.vers?.statut ? ` → ${x.vers.type} / ${x.vers.statut}` : ""}`])));
    }
  } catch (err) {
    $("#detail-histo").replaceChildren(el("li", {}, [`Historique indisponible : ${err.message}`]));
  }
}

function closeCase() {
  $("#detail").hidden = true;
  state.current = null;
}

async function decide(action) {
  const c = state.current;
  if (!c) return;
  const ok = await confirmDialog({
    title: action === "confirmer" ? "Confirmer ce cas ?" : "Rejeter ce cas ?",
    message: action === "confirmer"
      ? (c.type === "nettoyage" ? "Le lieu est bien nettoyé : le cas sera clos." : "Le dépotoir est bien présent : la mairie le recevra.")
      : (c.type === "nettoyage" ? "Le lieu n'est pas nettoyé : la mairie verra le rejet." : "Pas de dépotoir à cet endroit : le cas sera rejeté."),
    confirm: action === "confirmer" ? "Oui, confirmer" : "Oui, rejeter",
    danger: action === "rejeter",
  });
  if (!ok) return;
  const item = { opId: opId(), caseId: c.id, action, mode: state.mode, at: new Date().toISOString(), statut: "attente" };
  await once($(action === "confirmer" ? "#confirmer" : "#rejeter"), async () => {
    const result = await sendDecision(item);
    if (result === "ok") {
      toast(`Cas ${ACTION[action]} : décision reçue par le serveur.`, "ok");
      state.cases = state.cases.filter((x) => x.id !== c.id);
      closeCase();
    } else if (result === "attente") {
      toast("Pas de réseau : décision enregistrée sur le téléphone, envoi automatique plus tard.", "info", 6000);
      closeCase();
    }
    render();
  });
}

/** Envoie une décision ; ok | attente (réseau) | conflit | erreur. */
async function sendDecision(item) {
  try {
    if (!navigator.onLine) throw new ApiError("Hors ligne", { kind: "reseau" });
    await state.api.decision(item.caseId, item.action, item.mode);
    state.pending.delete(item.opId);
    await queue.remove(STORE, item.opId).catch(() => {});
    return "ok";
  } catch (err) {
    if (err.kind === "reseau" || err.kind === "delai") {
      state.pending.set(item.opId, item);
      await queue.put(STORE, item).catch(() => toast("Stockage local indisponible : décision non gardée.", "erreur"));
      return "attente";
    }
    if (await handleAuth(err)) return sendDecision(item);
    state.pending.delete(item.opId);
    await queue.remove(STORE, item.opId).catch(() => {});
    if (err.status === 409) toast(`Conflit : ${err.message} Le cas a déjà été traité, la liste est rechargée.`, "erreur", 7000);
    else toast(`Décision refusée : ${err.message}`, "erreur", 7000);
    load({ silent: true });
    return err.status === 409 ? "conflit" : "erreur";
  }
}

async function syncDecisions() {
  if (!navigator.onLine || state.syncing) return;
  state.syncing = true;
  try {
    for (const item of [...state.pending.values()].sort((a, b) => a.at.localeCompare(b.at))) {
      const r = await sendDecision(item);
      if (r === "ok") toast("Décision hors ligne envoyée et reçue par le serveur.", "ok");
      if (r === "attente") break;
    }
  } finally {
    state.syncing = false;
  }
  await load({ silent: true });
}

function network() {
  const on = navigator.onLine;
  $("#reseau").textContent = on ? "En ligne" : "Hors ligne";
  $("#reseau").classList.toggle("hors-ligne", !on);
  if (on) syncDecisions();
  else render();
}

function setMode(mode) {
  state.mode = mode;
  state.seen.clear();
  state.photos.clear();
  for (const b of document.querySelectorAll(".seg")) {
    b.classList.toggle("actif", b.dataset.mode === mode);
    b.setAttribute("aria-pressed", String(b.dataset.mode === mode));
  }
  $("#bandeau-sim").hidden = mode !== "sim";
  $("#sous-titre").textContent = mode === "sim" ? "Cas simulés (exercice)" : "Cas à vérifier sur place";
  load();
}

// --- Carte des cas à vérifier : ouverte seulement sur clic, Leaflet local chargé à la première ouverture ----------------
const carte = { map: null, L: null, couche: null, moi: null, ouverte: false, defil: 0 };
const COULEURS_CAS = { depotoir: "#b25d00", nettoyage: "#3d6373" };

function chargerLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = "/dashboard/vendor/leaflet/leaflet.css";
  document.head.append(css);
  return new Promise((ok, ko) => {
    const sc = document.createElement("script");
    sc.src = "/dashboard/vendor/leaflet/leaflet.js";
    sc.onload = () => ok(window.L);
    sc.onerror = () => ko(new Error("Leaflet introuvable"));
    document.head.append(sc);
  });
}

/** Cas encore à vérifier seulement (les cas décidés ne s'affichent jamais sur la carte). */
const casAVerifier = () => state.cases.filter((c) => !c.statut || c.statut === "a_verifier");

function majCarte({ ajuster = false, focus = null } = {}) {
  const L = carte.L;
  if (!L || !carte.map) return;
  carte.couche.clearLayers();
  const pts = [];
  for (const c of casAVerifier()) {
    if (!Number.isFinite(Number(c.lat))) continue;
    const ll = [Number(c.lat), Number(c.lon)];
    pts.push(ll);
    const sel = focus && focus.id === c.id;
    const icone = L.divIcon({ className: "", iconSize: [34, 34], iconAnchor: [17, 17],
      html: `<span class="marqueur-cas marqueur-${c.type === "nettoyage" ? "nettoyage" : "depotoir"}${sel ? " marqueur-sel" : ""}" data-cas="${encodeURIComponent(String(c.id))}" role="button" aria-label="${TYPE[c.type] || "Cas"}"></span>` });
    L.marker(ll, { icon: icone, title: `${TYPE[c.type] || c.type} — toucher pour ouvrir la fiche`, keyboard: true }).addTo(carte.couche);
  }
  if (state.me) L.circleMarker([state.me.lat, state.me.lon], { radius: 8, color: "#ffffff", weight: 3, fillColor: "#1f6fb2", fillOpacity: 1 })
    .bindTooltip("Ma position").addTo(carte.couche);
  if (focus && Number.isFinite(Number(focus.lat))) carte.map.setView([Number(focus.lat), Number(focus.lon)], 17);
  else if (ajuster && pts.length) carte.map.fitBounds(pts, { padding: [40, 40], maxZoom: 17 });
  $("#carte-compte").textContent = `${pts.length} cas à vérifier`;
}

async function ouvrirCarte(focus = null) {
  carte.defil = window.scrollY;
  $("#panneau-carte").hidden = false;
  carte.ouverte = true;
  if (!carte.map) {
    try {
      carte.L = await chargerLeaflet();
    } catch (err) {
      $("#carte-message").hidden = false;
      $("#carte-message").textContent = `Carte indisponible : ${err.message}`;
      return;
    }
    const L = carte.L;
    carte.map = L.map("brigade-map", { zoomControl: true }).setView([12.3672, -1.5337], 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors" }).on("tileerror", () => { $("#carte-message").hidden = false; })
      .on("tileload", () => { $("#carte-message").hidden = true; }).addTo(carte.map);
    carte.couche = L.layerGroup().addTo(carte.map);
    // Toucher un point ouvre la même fiche que dans la liste (délégation : fiable au doigt comme à la souris).
    carte.map.getContainer().addEventListener("click", (e) => {
      const m = e.target.closest?.("[data-cas]");
      if (!m) return;
      const id = decodeURIComponent(m.dataset.cas);
      const c = state.cases.find((x) => String(x.id) === id);
      if (c) openCase(c);
    });
  }
  setTimeout(() => { carte.map.invalidateSize(); majCarte({ ajuster: !focus, focus }); }, 30);
}

function fermerCarte() {
  $("#panneau-carte").hidden = true;
  carte.ouverte = false;
  window.scrollTo(0, carte.defil);
}

async function init() {
  state.api = await createApi({ role: "brigade" });
  if (isMockMode()) { mockBanner(); roleCode.set("brigade", roleCode.get("brigade") || "demo"); }
  await ensureCode();
  for (const it of await queue.all(STORE).catch(() => [])) state.pending.set(it.opId, it);
  $("#retour").addEventListener("click", closeCase);
  $("#confirmer").addEventListener("click", () => decide("confirmer"));
  $("#rejeter").addEventListener("click", () => decide("rejeter"));
  $("#actualiser").addEventListener("click", () => { $("#nouveaux").hidden = true; load(); });
  $("#ouvrir-carte").addEventListener("click", () => ouvrirCarte());
  $("#fermer-carte").addEventListener("click", fermerCarte);
  for (const b of document.querySelectorAll(".seg")) b.addEventListener("click", () => setMode(b.dataset.mode));
  window.addEventListener("online", network);
  window.addEventListener("offline", network);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#detail").hidden) closeCase(); });
  if ("geolocation" in navigator) {
    navigator.geolocation.watchPosition((p) => { state.me = { lat: p.coords.latitude, lon: p.coords.longitude }; render(); },
      () => {}, { enableHighAccuracy: true, maximumAge: 20000 });
  }
  setInterval(() => { if (document.visibilityState === "visible") { syncDecisions(); } }, POLL_MS);
  network();
  await load();
}

init();
