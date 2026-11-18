// Page citoyen : position GPS automatique, photo réduite (1024 px, JPEG 0,8), envoi ; file IndexedDB hors connexion
// et synchronisation automatique (au chargement, au retour du réseau, toutes les 30 s). Aucun verdict du tri affiché.
import { ApiError, createApi, isMockMode } from "/dashboard/shared/api.js";
import { opId, queue } from "/dashboard/shared/store.js";
import { $, el, fmt, mockBanner } from "/dashboard/shared/ui.js";
import { installerCamera } from "/citizen/camera.js";

let camera = null;   // caméra directe (repli sur le champ natif si elle est inaccessible)

const STORE = "signalements";
const MAX_SIDE = 1024;
const QUALITY = 0.8;
const SYNC_EVERY_MS = 30000;
const STATUTS = {
  local: ["Enregistré sur le téléphone", "p-local"],
  attente: ["En attente de réseau", "p-attente"],
  envoi: ["Envoi en cours…", "p-attente"],
  recu: ["Bien reçu, Barka, Anitche, Fofo", "p-recu"],
  echec: ["Échec de l'envoi : nouvel essai automatique", "p-echec"],
};

const state = { pos: null, photo: null, api: null, syncing: false, urls: [] };

// --- Position --------------------------------------------------------------------------------------------------
function askPosition() {
  const etat = $("#pos-etat");
  $("#pos-btn").hidden = true;
  if (!("geolocation" in navigator)) {
    etat.textContent = "Ce téléphone ne donne pas sa position : le signalement est impossible sans elle.";
    etat.className = "etat erreur";
    return;
  }
  etat.textContent = "Recherche de la position…";
  etat.className = "etat";
  // Suivi continu : chaque envoi part avec la position du moment, pas celle du chargement de la page.
  if (state.watch !== undefined) navigator.geolocation.clearWatch(state.watch);
  state.watch = navigator.geolocation.watchPosition(
    (p) => {
      state.pos = { lat: p.coords.latitude, lon: p.coords.longitude, accuracy_m: p.coords.accuracy };
      etat.textContent = `Position trouvée (précision environ ${Math.round(p.coords.accuracy)} m).`;
      etat.className = "etat ok";
      refreshButton();
    },
    (err) => {
      state.pos = null;
      etat.textContent = err.code === 1
        ? "Position refusée. Autorisez la localisation pour ce site dans le navigateur (la page doit être en https), puis réessayez."
        : "Position introuvable. Sortez à découvert puis réessayez.";
      etat.className = "etat erreur";
      $("#pos-btn").hidden = false;
      refreshButton();
    },
    { enableHighAccuracy: true, timeout: 20000, maximumAge: 5000 },
  );
}

// --- Photo -----------------------------------------------------------------------------------------------------
async function compress(file) {
  const bitmap = await createImageBitmap(file).catch(() => null);
  const src = bitmap || await new Promise((ok, ko) => {
    const img = new Image();
    img.onload = () => ok(img);
    img.onerror = () => ko(new Error("photo"));
    img.src = URL.createObjectURL(file);
  });
  const w = src.width;
  const h = src.height;
  const k = Math.min(1, MAX_SIDE / Math.max(w, h));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w * k);
  canvas.height = Math.round(h * k);
  canvas.getContext("2d").drawImage(src, 0, 0, canvas.width, canvas.height);
  bitmap?.close?.();
  const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", QUALITY));
  if (!blob) throw new Error("photo");
  return blob;
}

async function onPhoto(e) {
  await accepterPhoto(e.target.files?.[0]);
}

/** Photo venant de la caméra directe (Blob) ou du repli natif (File) : même réduction, même file d'envoi. */
async function accepterPhoto(file) {
  const etat = $("#photo-etat");
  if (!file) return;
  etat.textContent = "Préparation de la photo…";
  etat.className = "etat";
  try {
    state.photo = await compress(file);
    const url = URL.createObjectURL(state.photo);
    state.urls.push(url);
    $("#apercu").src = url;
    $("#apercu").hidden = false;
    etat.textContent = `Photo prête (${Math.round(state.photo.size / 1024)} Ko).`;
    etat.className = "etat ok";
  } catch {
    state.photo = null;
    $("#apercu").hidden = true;
    etat.textContent = "Cette photo est illisible. Reprenez-la.";
    etat.className = "etat erreur";
  }
  refreshButton();
}

function refreshButton() {
  const ready = Boolean(state.pos && state.photo);
  $("#envoyer").disabled = !ready;
  $("#envoi-aide").textContent = ready ? "Tout est prêt." : !state.pos
    ? "En attente de la position." : "En attente de la photo.";
}

// --- File d'attente et envoi --------------------------------------------------------------------------------------
const toBase64 = (blob) => new Promise((ok, ko) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result));
  r.onerror = () => ko(r.error);
  r.readAsDataURL(blob);
});

async function sendOne(item) {
  item.statut = "envoi";
  await queue.put(STORE, item);
  render();
  try {
    await state.api.postReport({
      photo_b64: await toBase64(item.photo), lat: item.lat, lon: item.lon,
      accuracy_m: item.accuracy_m, reported_at: item.createdAt,
    });
    item.statut = "recu";
    item.recuAt = new Date().toISOString();
    item.photo = null;            // reçu : la photo n'a plus à rester sur le téléphone
  } catch (err) {
    item.essais = (item.essais || 0) + 1;
    item.statut = err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 408 && err.status !== 429
      ? "echec" : "attente";
    item.erreur = err.message;
  }
  await queue.put(STORE, item);
  return item.statut === "recu";
}

/** Synchronise la file : un seul passage à la fois, éléments dans l'ordre de création. */
async function sync() {
  if (state.syncing || !navigator.onLine) return;
  state.syncing = true;
  try {
    const items = (await queue.all(STORE)).filter((i) => i.statut !== "recu").sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    for (const item of items) {
      const ok = await sendOne(item);
      if (!ok && item.statut === "attente") break;  // réseau perdu : on réessaiera plus tard
    }
  } catch {
    /* stockage local inaccessible : signalé par render() */
  } finally {
    state.syncing = false;
    render();
  }
}

async function submit() {
  if (!state.pos || !state.photo) return;
  const btn = $("#envoyer");
  btn.disabled = true;
  const item = { opId: opId(), lat: state.pos.lat, lon: state.pos.lon, accuracy_m: state.pos.accuracy_m,
    createdAt: new Date().toISOString(), photo: state.photo, statut: "local", essais: 0 };
  const box = $("#confirmation");
  box.hidden = false;
  try {
    await queue.put(STORE, item);
  } catch {
    box.className = "confirmation local";
    box.replaceChildren(el("b", {}, ["Impossible d'enregistrer sur ce téléphone."]),
      "Le stockage local est indisponible (navigation privée ?). Réessayez avec une connexion.");
    btn.disabled = false;
    return;
  }
  state.photo = null;
  $("#photo").value = "";
  $("#apercu").hidden = true;
  $("#photo-etat").textContent = "";
  refreshButton();
  camera?.apresEnvoi();
  const ok = navigator.onLine ? await sendOne(item) : false;
  if (ok) {
    box.className = "confirmation";
    box.replaceChildren(el("b", {}, ["Bien reçu, Barka, Anitche, Fofo"]));
  } else {
    box.className = "confirmation local";
    box.replaceChildren(el("b", {}, ["Enregistré sur votre téléphone."]),
      "Il n'est pas encore arrivé : il partira automatiquement dès le retour du réseau. Gardez cette page ou rouvrez-la plus tard.");
  }
  render();
}

// --- Affichage de la file ------------------------------------------------------------------------------------
async function render() {
  let items = [];
  try {
    items = (await queue.all(STORE)).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  } catch {
    $("#aucun").textContent = "Stockage local indisponible : les envois hors connexion ne peuvent pas être gardés.";
  }
  for (const u of state.urls.splice(0)) if (u !== $("#apercu").src) URL.revokeObjectURL(u);
  const list = $("#liste-envois");
  list.replaceChildren(...items.slice(0, 20).map((i) => {
    const [label, cls] = STATUTS[i.statut] || STATUTS.attente;
    let thumb = el("img", { alt: "" });
    if (i.photo instanceof Blob) {
      const u = URL.createObjectURL(i.photo);
      state.urls.push(u);
      thumb = el("img", { alt: "Photo du signalement", src: u });
    }
    return el("li", {}, [thumb, el("div", {}, [
      el("div", { class: "quand" }, [fmt.date(i.createdAt)]),
      el("span", { class: `pastille ${cls}` }, [label]),
      i.statut === "attente" && i.essais ? el("div", { class: "quand" }, [`${i.essais} essai(s) : ${i.erreur || ""}`]) : null,
    ])]);
  }));
  $("#aucun").hidden = items.length > 0;
  $("#sync").hidden = !items.some((i) => i.statut !== "recu");
}

function network() {
  const on = navigator.onLine;
  $("#reseau").textContent = on ? "En ligne" : "Hors ligne";
  $("#reseau").classList.toggle("hors-ligne", !on);
  if (on) sync();
}

async function cleanup() {
  // Les envois reçus depuis plus de 7 jours disparaissent de la liste locale.
  const limit = Date.now() - 7 * 86400e3;
  for (const i of await queue.all(STORE).catch(() => [])) {
    if (i.statut === "recu" && Date.parse(i.recuAt || i.createdAt) < limit) await queue.remove(STORE, i.opId);
  }
}

async function init() {
  state.api = await createApi();
  if (isMockMode()) mockBanner();
  $("#photo").addEventListener("change", onPhoto);
  camera = installerCamera({
    surPhoto: accepterPhoto,
    surReprendre: () => { state.photo = null; $("#apercu").hidden = true; $("#photo-etat").textContent = ""; refreshButton(); },
  });
  $("#pos-btn").addEventListener("click", askPosition);
  $("#envoyer").addEventListener("click", submit);
  $("#sync").addEventListener("click", sync);
  window.addEventListener("online", network);
  window.addEventListener("offline", network);
  setInterval(sync, SYNC_EVERY_MS);
  if ("serviceWorker" in navigator && !isMockMode()) {
    navigator.serviceWorker.register("/citizen/sw.js", { scope: "/citizen/" }).catch(() => {});
  }
  askPosition();
  await cleanup();
  network();
  render();
}

init();
