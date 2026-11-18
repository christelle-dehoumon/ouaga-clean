// « Aller à » : lieux emblématiques de Ouagadougou et visite guidée de la ville.
// Noms et positions repris tels quels de l'index OSM des tuiles (recherche.json) : aucun lieu n'est inventé.
// Chaque lieu ouvre aussi l'état de la propreté alentour (données de l'API, jamais inventées).
import { el } from "/dashboard/shared/ui.js";

export const REPERES = [
  { n: "Grand Marché", t: "Marché", c: [-1.5235, 12.368299] },
  { n: "Place des Cinéastes", t: "Monument", c: [-1.527529, 12.368535] },
  { n: "Mairie centrale de Ouagadougou", t: "Institution", c: [-1.526965, 12.367979] },
  { n: "BCEAO", t: "Architecture", c: [-1.528907, 12.367277] },
  { n: "Cathédrale de l'Immaculée-Conception", t: "Lieu de culte", c: [-1.527008, 12.361964] },
  { n: "Grande Mosquée", t: "Lieu de culte", c: [-1.521392, 12.366219] },
  { n: "Place Naaba Koom", t: "Place", c: [-1.526279, 12.372973] },
  { n: "Stade du 4-Août", t: "Stade", c: [-1.553482, 12.368671] },
  { n: "CHU Yalgado Ouédraogo", t: "Santé", c: [-1.506457, 12.383562] },
  { n: "Université Joseph Ki-Zerbo", t: "Campus", c: [-1.499049, 12.379439] },
  { n: "Musée National", t: "Culture", c: [-1.471959, 12.379695] },
  { n: "SIAO", t: "Salon international", c: [-1.490327, 12.350498] },
  { n: "Monument aux héros nationaux", t: "Monument", c: [-1.502616, 12.312189] },
  { n: "Palais de Kosyam", t: "Institution", c: [-1.502729, 12.292613] },
];

const VOL = { zoom: 16.6, pitch: 62, duration: 2600 };

/** Installe le bouton « Aller à » dans la barre de caméra et son panneau ; choisir(repere) ouvre la fiche. */
export function installerReperes(view, choisir) {
  const barre = document.querySelector(".commandes-camera");
  if (!barre || document.getElementById("aller-a")) return null;
  const map = view.map;
  let visite = null;

  const panneau = el("div", { id: "panneau-reperes", class: "panneau-reperes", role: "dialog", "aria-label": "Aller à un lieu", hidden: true });
  const fermer = () => { panneau.hidden = true; bouton.setAttribute("aria-expanded", "false"); };
  const aller = (r, i) => {
    const bearing = ((i * 47) % 120) - 60;   // angle varié d'un lieu à l'autre, déterministe
    map.flyTo({ center: r.c, zoom: VOL.zoom, pitch: VOL.pitch, bearing, duration: VOL.duration, essential: true });
    choisir(r);
  };
  const arreterVisite = () => {
    if (!visite) return;
    clearTimeout(visite.t);
    visite = null;
    boutonVisite.textContent = "Visite guidée";
    boutonVisite.setAttribute("aria-pressed", "false");
  };
  const etape = (i) => {
    if (!visite) return;
    aller(REPERES[i % REPERES.length], i);
    visite.t = setTimeout(() => etape(i + 1), VOL.duration + 4500);
  };
  const boutonVisite = el("button", { type: "button", class: "btn btn-primaire btn-large", "aria-pressed": "false", onclick: () => {
    if (visite) return arreterVisite();
    fermer();
    visite = { t: 0 };
    boutonVisite.textContent = "Arrêter la visite";
    boutonVisite.setAttribute("aria-pressed", "true");
    etape(0);
  } }, ["Visite guidée"]);
  panneau.append(
    el("div", { class: "reperes-entete" }, [el("b", {}, ["Aller à"]), el("button", { type: "button", class: "bouton-icone", "aria-label": "Fermer", onclick: fermer }, ["×"])]),
    el("p", { class: "reperes-note" }, ["Lieux d'OpenStreetMap. Chaque fiche donne la propreté alentour."]),
    el("ul", { class: "reperes-liste" }, REPERES.map((r, i) => el("li", {}, [el("button", { type: "button", onclick: () => { arreterVisite(); fermer(); aller(r, i); } },
      [el("b", {}, [r.n]), el("span", {}, [r.t])])]))),
    boutonVisite,
  );
  document.querySelector("#scene").append(panneau);
  const bouton = el("button", { type: "button", id: "aller-a", "aria-expanded": "false", "aria-controls": "panneau-reperes",
    title: "Aller à un lieu emblématique ou lancer la visite guidée", onclick: () => {
      panneau.hidden = !panneau.hidden;
      bouton.setAttribute("aria-expanded", String(!panneau.hidden));
    } }, ["Aller à"]);
  barre.prepend(bouton);
  // Toute action de l'utilisateur sur la carte reprend la main : la visite s'arrête.
  for (const ev of ["mousedown", "touchstart", "wheel"]) map.getCanvas().addEventListener(ev, arreterVisite, { passive: true });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { arreterVisite(); fermer(); } });
  return { arreterVisite };
}

/** Propreté autour d'un point : signalements à moins de `rayon` m, par statut, et point du plan le plus proche. */
export function proprete(lat, lon, reports, plan, rayon = 600) {
  const d = (a, b) => {
    const k = Math.cos((lat * Math.PI) / 180) * 111320;
    return Math.hypot((b.lon - a.lon) * k, (b.lat - a.lat) * 111320);
  };
  const ici = { lat, lon };
  const proches = reports.filter((r) => Number.isFinite(Number(r.lat)) && d(ici, { lat: Number(r.lat), lon: Number(r.lon) }) <= rayon);
  let point = null;
  for (const p of plan?.consolidation_points || []) {
    const m = d(ici, { lat: Number(p.lat), lon: Number(p.lon) });
    if (!point || m < point.m) point = { p, m };
  }
  return { proches, point };
}
