// Couches opérationnelles de VIELA sur la carte : signalements, dépotoirs simulés, points du plan, tournées,
// coupures, quartiers et surbrillance. Données venant de l'API uniquement (aucune donnée inventée ici).
import { STATUTS, VEHICLE_COLORS } from "../map3d/layers.js";

const hex = (n) => `#${Number(n).toString(16).padStart(6, "0")}`;
// Anneau d'un repère de camion : jaune si sélectionné, rouge si en panne, sinon sombre (de jour) ou clair (de nuit),
// pour ne pas se confondre avec les points du plan cerclés de blanc.
const anneauCamion = (couleur) => ["case", ["get", "sel"], "#fcd116", ["get", "panne"], "#d32f2f", couleur];
const vide = () => ({ type: "FeatureCollection", features: [] });
const point = (lon, lat, props) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: props });
const ligne = (coords, props) => ({ type: "Feature", geometry: { type: "LineString", coordinates: coords }, properties: props });

export const COULEURS_PLAN = { desservi: "#0a7a42", non_desservi: "#d32f2f", reporte: "#e67e22", depotoir: "#9a6b3c" };

export class Operationnel {
  constructor(map, { territoires, versLatLon }) {
    this.map = map;
    this.versLatLon = versLatLon;          // (x, z) locaux -> [lat, lon]
    this.territoires = territoires;
    this.donnees = new Map();              // id de source -> tableau d'objets d'origine (index = id de l'entité)
    this.couleurCamion = new Map();
    this.ajouterSources();
    this.ajouterCouches();
    this.setTerritoires(territoires);
  }

  source(id) { return this.map.getSource(id); }

  ajouterSources() {
    for (const id of ["op-quartiers", "op-tournees", "op-points", "op-signalements", "op-simules", "op-coupures", "op-surbrillance", "op-selection", "op-reseau"]) {
      if (!this.map.getSource(id)) this.map.addSource(id, { type: "geojson", data: vide(), promoteId: "i" });
    }
    if (!this.map.getSource("op-avancement")) this.map.addSource("op-avancement", { type: "geojson", data: vide() });
  }

  ajouterCouches() {
    const m = this.map;
    const add = (c, avant) => { if (!m.getLayer(c.id)) m.addLayer(c, avant); };
    const avantEtiquettes = m.getLayer("noms-rues") ? "noms-rues" : undefined;
    // Quartiers du plan (emprises approximatives : traits pointillés, jamais présentés comme officiels).
    add({ id: "op-quartiers-fond", type: "fill", source: "op-quartiers",
      paint: { "fill-color": ["case", ["boolean", ["feature-state", "actif"], false], "#fcd116", "#0a7a42"],
        "fill-opacity": ["case", ["boolean", ["feature-state", "actif"], false], 0.16, 0] } }, avantEtiquettes);
    add({ id: "op-quartiers-trait", type: "line", source: "op-quartiers",
      paint: { "line-color": ["case", ["get", "secteur"], "#0a7a42", "#6b5a3e"], "line-width": ["case", ["get", "secteur"], 2.2, 1.4],
        "line-dasharray": ["case", ["get", "approximatif"], ["literal", [2, 2]], ["literal", [1, 0]]], "line-opacity": 0.7 } }, avantEtiquettes);
    // Réseau routier du plan (graphe de calcul des tournées) : visible seulement en mode « couper une route ».
    add({ id: "op-reseau", type: "line", source: "op-reseau", layout: { visibility: "none", "line-cap": "round" },
      paint: { "line-color": "#d32f2f", "line-width": ["interpolate", ["linear"], ["zoom"], 13, 2, 18, 9], "line-opacity": 0.25 } });
    // Tournées : tracé complet en gris fin (partie déjà parcourue par l'animation SIMULÉE), puis par-dessus la partie
    // restante à la couleur du camion (source op-avancement, mise à jour au plus deux fois par seconde) ; trajet
    // sélectionné en jaune.
    add({ id: "op-tournees-bord", type: "line", source: "op-tournees", layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2, 16, 4.5, 19, 9], "line-opacity": 0.55 } });
    add({ id: "op-tournees", type: "line", source: "op-tournees", layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#8c8981", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1, 16, 2.5, 19, 5.5], "line-opacity": 0.9 } });
    add({ id: "op-restant-bord", type: "line", source: "op-avancement", filter: ["==", ["geometry-type"], "LineString"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2.5, 16, 7, 19, 14], "line-opacity": 0.85 } });
    add({ id: "op-restant", type: "line", source: "op-avancement", filter: ["==", ["geometry-type"], "LineString"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": ["get", "couleur"], "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1.5, 16, 4.5, 19, 10] } });
    add({ id: "op-surbrillance", type: "line", source: "op-surbrillance", layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#fcd116", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 3, 16, 9, 19, 16], "line-opacity": 0.95 } });
    add({ id: "op-coupures", type: "line", source: "op-coupures",
      paint: { "line-color": "#d32f2f", "line-width": ["interpolate", ["linear"], ["zoom"], 12, 3, 18, 12], "line-dasharray": [1, 0.6] } });
    // Points du plan : couleur du statut (desservi, non desservi, reporté), taille selon la demande.
    add({ id: "op-points-halo", type: "circle", source: "op-points", filter: ["!=", ["get", "statut"], "desservi"],
      paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 7, 17, 18], "circle-color": ["get", "couleur"], "circle-opacity": 0.22,
        "circle-stroke-color": ["get", "couleur"], "circle-stroke-width": 1.5, "circle-stroke-opacity": 0.8 } });
    add({ id: "op-points", type: "circle", source: "op-points",
      paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, ["*", 0.5, ["get", "r"]], 17, ["*", 1.4, ["get", "r"]]],
        "circle-color": ["get", "couleur"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.6, "circle-pitch-alignment": "map" } });
    // Repères des camions (même source) : lisibles et cliquables au loin, où le modèle 3D est minuscule ; ils
    // s'effacent de près, où le modèle 3D prend le relais. Gris cerclé de rouge et mention « en panne » si immobilisé.
    const camionsFiltre = ["==", ["geometry-type"], "Point"];
    const fondu = ["interpolate", ["linear"], ["zoom"], 15.6, 1, 16.8, 0];
    add({ id: "op-camions", type: "circle", source: "op-avancement", filter: camionsFiltre, maxzoom: 17,
      paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 4.5, 13, 6, 15, 7.5, 16.5, 9],
        "circle-color": ["case", ["get", "panne"], "#8a8a84", ["get", "couleur"]],
        "circle-stroke-color": anneauCamion("#1e2320"),
        "circle-stroke-width": ["case", ["get", "sel"], 3.2, ["get", "panne"], 2.6, 2.2],
        "circle-opacity": fondu, "circle-stroke-opacity": fondu, "circle-pitch-alignment": "viewport" } });
    add({ id: "op-camions-panne", type: "symbol", source: "op-avancement", filter: ["all", camionsFiltre, ["get", "panne"]],
      layout: { "text-field": "en panne", "text-font": ["noto-bold"], "text-size": 11, "text-anchor": "top", "text-offset": [0, 0.9],
        "text-allow-overlap": true, "text-ignore-placement": true },
      paint: { "text-color": "#b3261e", "text-halo-color": "rgba(255,255,255,.95)", "text-halo-width": 1.6 } });
    // Zones prioritaires (« où intervenir ? ») : densité des signalements à traiter, visible à l'échelle de la ville et
    // effacée en s'approchant (les épingles prennent le relais). Poids : confirmé 1, à vérifier 0,7, nettoyage à
    // vérifier 0,3 ; rejeté et nettoyé 0. Données de l'API seulement (réelles, ou simulées en mode Simulation).
    add({ id: "op-priorite", type: "heatmap", source: "op-signalements", maxzoom: 15.5,
      paint: {
        "heatmap-weight": ["match", ["get", "etat"], "depotoir:confirme", 1, "depotoir:a_verifier", 0.7, "nettoyage:a_verifier", 0.3, 0],
        "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 10, 1.2, 15, 2.2],
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 10, 22, 13, 55, 15, 90],
        "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(252,209,22,0)", 0.2, "rgba(252,209,22,0.35)",
          0.5, "rgba(240,140,30,0.55)", 0.8, "rgba(214,60,40,0.7)", 1, "rgba(170,20,30,0.8)"],
        "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 13.5, 0.85, 15.5, 0],
      } }, avantEtiquettes);
    // Signalements et dépotoirs simulés : épingles rondes au statut lisible.
    for (const [src, id] of [["op-simules", "op-simules"], ["op-signalements", "op-signalements"]]) {
      add({ id: `${id}-ombre`, type: "circle", source: src,
        paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 5, 17, 13], "circle-color": "#000", "circle-opacity": 0.18, "circle-blur": 0.8,
          "circle-translate": [0, 2] } });
      add({ id, type: "circle", source: src,
        paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 4, 17, 10], "circle-color": ["get", "couleur"],
          "circle-stroke-color": ["case", ["get", "fictif"], "#e8ddff", "#ffffff"], "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 11, 1.5, 17, 3] } });
    }
    add({ id: "op-selection", type: "circle", source: "op-selection",
      paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 10, 17, 22], "circle-color": "rgba(0,0,0,0)",
        "circle-stroke-color": "#fcd116", "circle-stroke-width": 3.5 } });
  }

  poser(id, features, objets) {
    this.donnees.set(id, objets);
    this.source(id)?.setData({ type: "FeatureCollection", features });
  }

  objet(sourceId, i) { return this.donnees.get(sourceId)?.[i]; }

  setTerritoires(territoires) {
    const feats = territoires.map((t, i) => ({ type: "Feature", id: i, properties: { i, nom: t.nom, secteur: Boolean(t.secteur), approximatif: Boolean(t.approximate) },
      geometry: { type: "Polygon", coordinates: t.rings.map((r) => { const c = r.map(([x, z]) => { const [la, lo] = this.versLatLon(x, z); return [lo, la]; }); c.push(c[0]); return c; }) } }));
    this.poser("op-quartiers", feats, territoires);
  }

  surlignerQuartier(id) {
    this.territoires.forEach((t, i) => this.map.setFeatureState({ source: "op-quartiers", id: i }, { actif: t.id === id }));
  }

  setReseau(roads) {
    const feats = roads.filter((r) => r.truck).map((r, i) => ligne(r.pts.map(([x, z]) => { const [la, lo] = this.versLatLon(x, z); return [lo, la]; }), { i }));
    this.poser("op-reseau", feats, roads.filter((r) => r.truck));
  }

  setReports(list) {
    const ok = list.filter((r) => Number.isFinite(Number(r.lat)) && Number.isFinite(Number(r.lon)));
    this.poser("op-signalements", ok.map((r, i) => {
      const st = STATUTS[`${r.type}:${r.statut}`] || STATUTS["depotoir:a_verifier"];
      return point(Number(r.lon), Number(r.lat), { i, couleur: hex(st.couleur), fictif: r.source === "sim", etat: `${r.type}:${r.statut}` });
    }), ok.map((r) => ({ kind: "signalement", data: r, label: (STATUTS[`${r.type}:${r.statut}`] || {}).libelle })));
  }

  setSimDumps(list) {
    this.poser("op-simules", list.map((d, i) => point(Number(d.lon), Number(d.lat), { i, couleur: hex(STATUTS.simule.couleur), fictif: true })),
      list.map((d) => ({ kind: "simule", data: d, label: STATUTS.simule.libelle })));
  }

  setPlan(plan) {
    if (!plan) {
      for (const id of ["op-points", "op-tournees", "op-coupures"]) this.poser(id, [], []);
      this.traces = [];
      return;
    }
    const unserved = new Map((plan.unserved || []).map((u) => [u.point_id, u]));
    const postponed = new Map((plan.postponed || []).map((p) => [p.id, p]));
    const pts = (plan.consolidation_points || plan.collection_points || []).filter((p) => Number.isFinite(Number(p.lat)));
    const infos = pts.map((p) => {
      const status = unserved.has(p.id) ? "non_desservi" : postponed.has(p.id) ? "reporte" : "desservi";
      return { kind: "point", data: p, status, raison: unserved.get(p.id) || postponed.get(p.id) || null };
    });
    this.poser("op-points", pts.map((p, i) => {
      const st = infos[i].status;
      const couleur = st === "desservi" ? (p.type === "dumpsite" ? COULEURS_PLAN.depotoir : COULEURS_PLAN.desservi) : COULEURS_PLAN[st];
      return point(Number(p.lon), Number(p.lat), { i, statut: st, couleur, r: Math.max(4, Math.min(11, 3 + Math.sqrt(Number(p.demand_kg) || 0) / 9)) });
    }), infos);
    // Couleur stable par camion (même ordre que la vue 3D).
    const camions = [...new Set((plan.routes || []).map((r) => String(r.vehicle_id || r.vehicle).split("_trip")[0]))]
      .sort((a, b) => Number(a.replace(/\D/g, "")) - Number(b.replace(/\D/g, "")));
    this.couleurCamion.clear();
    camions.forEach((t, i) => this.couleurCamion.set(t, VEHICLE_COLORS[i % VEHICLE_COLORS.length]));
    const routes = (plan.routes || []).filter((r) => (r.path || []).length >= 2);
    const feats = routes.map((r, i) => {
      const camion = String(r.vehicle_id || r.vehicle).split("_trip")[0];
      return ligne(r.path.map(([la, lo]) => [lo, la]), { i, camion, couleur: hex(this.couleurCamion.get(camion) ?? VEHICLE_COLORS[0]) });
    });
    this.poser("op-tournees", feats, routes.map((r) => ({ kind: "tournee", data: r })));
    this.traces = feats.map((f, i) => ({ trajet: routes[i].vehicle_id || routes[i].vehicle, coords: f.geometry.coordinates, props: f.properties }));
  }

  /** Avancement de l'animation SIMULÉE des camions (jamais une position GPS) : partie restante de chaque tournée et
   *  repère de chaque camion, en une seule mise à jour de la source op-avancement. Lu dans l'état de la flotte :
   *  t.d (distance parcourue le long de t.pts, cumulée dans t.cum). */
  majAvancement(flotte, camionSel = null) {
    const parTrajet = new Map();
    const curseurs = new Map();
    for (const t of flotte.trucks.values()) {
      for (const leg of t.object.userData.legs || []) parTrajet.set(leg.trip, { t, leg });
      if (t.idle || t.broken || t.cum.length < 2) continue;
      let lo = 0;
      let hi = t.cum.length - 1;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (t.cum[mid] <= t.d) lo = mid; else hi = mid; }
      const f = Math.min(1, Math.max(0, (t.d - t.cum[lo]) / (t.cum[hi] - t.cum[lo] || 1)));
      const [x1, z1] = t.pts[lo];
      const [x2, z2] = t.pts[hi];
      const [la, lo2] = this.versLatLon(x1 + (x2 - x1) * f, z1 + (z2 - z1) * f);
      curseurs.set(t, { lo, ici: [lo2, la] });
    }
    const feats = [];
    for (const tr of this.traces || []) {
      const lien = parTrajet.get(tr.trajet);
      const c = lien && curseurs.get(lien.t);
      let reste = tr.coords;
      if (c) {
        const { start, end } = lien.leg;
        if (c.lo >= end) reste = null;                                   // trajet terminé dans l'animation
        else if (c.lo >= start) reste = [c.ici, ...tr.coords.slice(c.lo - start + 1)];
      }
      if (reste && reste.length >= 2) feats.push(ligne(reste, tr.props));
    }
    for (const t of flotte.trucks.values()) {
      const u = t.object.userData;
      const [la, lo] = this.versLatLon(t.object.position.x, t.object.position.z);
      feats.push(point(lo, la, { id: u.id, couleur: hex(u.color ?? 0x9a9a92), panne: Boolean(t.broken), sel: u.id === camionSel }));
    }
    this.avancement = { type: "FeatureCollection", features: feats };   // dernier état publié (inspection, tests)
    this.source("op-avancement")?.setData(this.avancement);
  }

  /** Couleurs des couches opérationnelles adaptées à l'ambiance (contraste de nuit). */
  setAmbiance(nom) {
    const nuit = nom === "nuit";
    const m = this.map;
    const peindre = (id, k, v) => { if (m.getLayer(id)) m.setPaintProperty(id, k, v); };
    const bord = nuit ? "#0f1216" : "#ffffff";
    peindre("op-tournees-bord", "line-color", bord);
    peindre("op-tournees", "line-color", nuit ? "#7d8590" : "#8c8981");
    // De nuit, la partie restante garde une bordure claire atténuée : les couleurs des camions ressortent sur le fond sombre.
    peindre("op-restant-bord", "line-color", nuit ? "#e9e4d8" : "#ffffff");
    peindre("op-restant-bord", "line-opacity", nuit ? 0.55 : 0.85);
    peindre("op-camions", "circle-stroke-color", anneauCamion(nuit ? "#f4f1ea" : "#1e2320"));
    peindre("op-camions-panne", "text-color", nuit ? "#ff8a80" : "#b3261e");
    peindre("op-camions-panne", "text-halo-color", nuit ? "rgba(15,17,20,.92)" : "rgba(255,255,255,.95)");
    peindre("op-quartiers-trait", "line-color", nuit ? ["case", ["get", "secteur"], "#3fbf7f", "#a8977a"] : ["case", ["get", "secteur"], "#0a7a42", "#6b5a3e"]);
  }

  setCoupures(coupures, roadById) {
    const feats = [];
    const objets = [];
    for (const c of coupures || []) {
      const road = roadById.get(c.edge_id);
      if (road) feats.push(ligne(road.pts.map(([x, z]) => { const [la, lo] = this.versLatLon(x, z); return [lo, la]; }), { i: objets.length }));
      else if (Number.isFinite(Number(c.lat))) feats.push(point(Number(c.lon), Number(c.lat), { i: objets.length }));
      else continue;
      objets.push({ kind: "coupure", data: c });
    }
    this.poser("op-coupures", feats, objets);
  }

  surligner(chemins) {
    this.source("op-surbrillance")?.setData({ type: "FeatureCollection", features: chemins.filter((c) => c.length > 1).map((c) => ligne(c, {})) });
  }

  marquer(lonlat) {
    this.source("op-selection")?.setData({ type: "FeatureCollection", features: lonlat ? [point(lonlat[0], lonlat[1], {})] : [] });
  }

  afficherReseau(oui) {
    if (this.map.getLayer("op-reseau")) this.map.setLayoutProperty("op-reseau", "visibility", oui ? "visible" : "none");
  }
}
