// Couches opérationnelles de Yilgré sur la carte : signalements, dépotoirs simulés, points du plan, tournées,
// coupures, quartiers et surbrillance. Données venant de l'API uniquement (aucune donnée inventée ici).
import { STATUTS, VEHICLE_COLORS } from "../map3d/layers.js";

const hex = (n) => `#${Number(n).toString(16).padStart(6, "0")}`;
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
    // Tournées : bordure claire puis couleur du camion ; trajet sélectionné en jaune.
    add({ id: "op-tournees-bord", type: "line", source: "op-tournees", layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2.5, 16, 7, 19, 14], "line-opacity": 0.85 } });
    add({ id: "op-tournees", type: "line", source: "op-tournees", layout: { "line-cap": "round", "line-join": "round" },
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
      return point(Number(r.lon), Number(r.lat), { i, couleur: hex(st.couleur), fictif: r.source === "sim" });
    }), ok.map((r) => ({ kind: "signalement", data: r, label: (STATUTS[`${r.type}:${r.statut}`] || {}).libelle })));
  }

  setSimDumps(list) {
    this.poser("op-simules", list.map((d, i) => point(Number(d.lon), Number(d.lat), { i, couleur: hex(STATUTS.simule.couleur), fictif: true })),
      list.map((d) => ({ kind: "simule", data: d, label: STATUTS.simule.libelle })));
  }

  setPlan(plan) {
    if (!plan) {
      for (const id of ["op-points", "op-tournees", "op-coupures"]) this.poser(id, [], []);
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
    this.poser("op-tournees", routes.map((r, i) => {
      const camion = String(r.vehicle_id || r.vehicle).split("_trip")[0];
      return ligne(r.path.map(([la, lo]) => [lo, la]), { i, camion, couleur: hex(this.couleurCamion.get(camion) ?? VEHICLE_COLORS[0]) });
    }), routes.map((r) => ({ kind: "tournee", data: r })));
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

  /** Couches cliquables, de la plus haute à la plus basse. */
  static COUCHES_CLIC = ["op-signalements", "op-simules", "op-points", "op-coupures", "op-tournees"];
}
