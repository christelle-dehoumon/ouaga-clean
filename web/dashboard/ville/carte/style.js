// Style cartographique de Yilgré pour les tuiles du schéma scripts/tuiles/schema_yilgre.yml.
// Trois ambiances (jour, soir, nuit) : seules les couleurs et la lumière changent, jamais la géographie.
import { CARTE, exprBase, exprHauteur } from "./config.js";

export const AMBIANCES = {
  jour: {
    fond: "#eee8dd", residentiel: "#e8e0d2", vert: "#d3e3bd", eau: "#a7cfe2", eauTexte: "#3f7590", sable: "#e9dcc2",
    equipement: "#ece2d6", commerce: "#efdcd2", industrie: "#e2dcd6", route: "#ffffff", routeBord: "#d6cbb9",
    principale: "#fde6b2", principaleBord: "#d9b46a", chemin: "#cbbfa9", rail: "#a39c92",
    bat: ["#ebe3d6", "#dccfbc", "#cbb99f"], batHaut: "#bda88a", texte: "#3c3a35", halo: "rgba(255,255,255,.92)",
    lieu: "#2e2b26", limite: "#a7998a", lumiere: { anchor: "viewport", color: "#fff6e8", intensity: 0.32, position: [1.2, 200, 35] },
    ciel: { "sky-color": "#cfe3f0", "horizon-color": "#efe3cd", "fog-color": "#efe6d6", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.75, "fog-ground-blend": 0.92 },
  },
  soir: {
    fond: "#e6d3bd", residentiel: "#dfc9b0", vert: "#c4cf9f", eau: "#8fb3c9", eauTexte: "#335c73", sable: "#e0c9a4",
    equipement: "#e2cbb3", commerce: "#e6c8b4", industrie: "#d6c6b6", route: "#fff3e0", routeBord: "#cfb293",
    principale: "#ffd28a", principaleBord: "#c98f45", chemin: "#bfa587", rail: "#94867a",
    bat: ["#ead2b8", "#ddbd9b", "#c9a47f"], batHaut: "#b98f68", texte: "#3a2e24", halo: "rgba(255,244,228,.92)",
    lieu: "#2e231a", limite: "#a08670", lumiere: { anchor: "viewport", color: "#ffd7a8", intensity: 0.42, position: [1.2, 250, 18] },
    ciel: { "sky-color": "#f2b98a", "horizon-color": "#f6d2a6", "fog-color": "#efd2b2", "sky-horizon-blend": 0.7, "horizon-fog-blend": 0.8, "fog-ground-blend": 0.9 },
  },
  nuit: {
    fond: "#1b1f24", residentiel: "#20252b", vert: "#1f2a22", eau: "#14283a", eauTexte: "#7fa8c4", sable: "#25272a",
    equipement: "#232830", commerce: "#2a2527", industrie: "#24262a", route: "#3a4048", routeBord: "#1a1d21",
    principale: "#8a6a35", principaleBord: "#3d2f18", chemin: "#33383f", rail: "#4a4f55",
    bat: ["#2c323a", "#343b44", "#3e4650"], batHaut: "#4a535e", texte: "#d9d6cf", halo: "rgba(15,17,20,.9)",
    lieu: "#f1ede4", limite: "#5b636d", lumiere: { anchor: "viewport", color: "#b8c8ff", intensity: 0.2, position: [1.2, 210, 40] },
    ciel: { "sky-color": "#0d1420", "horizon-color": "#1d2838", "fog-color": "#151b24", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.8, "fog-ground-blend": 0.9 },
  },
};

const NOM = ["coalesce", ["get", "nom"], ""];
const POLICE = ["noto-regular"];
const POLICE_GRAS = ["noto-bold"];
const ITALIQUE = ["noto-italic"];

/** Largeur d'une route selon sa classe et le zoom (pixels). */
function largeur(classe, facteur = 1) {
  const w = {
    motorway: [1.2, 3.2, 14], trunk: [1.1, 3, 13], primary: [0.9, 2.6, 12], secondary: [0.6, 2.1, 10],
    tertiary: [0.4, 1.7, 9], unclassified: [0.2, 1, 7], residential: [0.2, 1, 7], living_street: [0.2, 0.9, 6],
    service: [0.1, 0.6, 4.5], pedestrian: [0.1, 0.7, 5], track: [0.1, 0.5, 3], footway: [0.1, 0.4, 2], path: [0.1, 0.4, 2],
    cycleway: [0.1, 0.4, 2], steps: [0.1, 0.4, 2],
  }[classe];
  return ["interpolate", ["exponential", 1.6], ["zoom"], 10, w[0] * facteur, 14, w[1] * facteur, 18, w[2] * facteur];
}
const CLASSES_PRINCIPALES = ["motorway", "trunk", "primary"];
const CLASSES_SECONDAIRES = ["secondary", "tertiary"];
const CLASSES_LOCALES = ["unclassified", "residential", "living_street", "service", "pedestrian"];
const CLASSES_CHEMINS = ["track", "footway", "path", "cycleway", "steps"];

/** Couches de routes : bordure puis remplissage, une couche par classe (une interpolation de zoom ne peut pas être
 *  imbriquée dans un « match »), dans l'ordre chemins, locales, secondaires, principales (les grandes dessus). */
function couchesRoutes(a) {
  const out = [];
  const groupes = [
    [CLASSES_CHEMINS, a.chemin, null, 13],
    [CLASSES_LOCALES, a.route, a.routeBord, 12],
    [CLASSES_SECONDAIRES, a.route, a.routeBord, 10],
    [CLASSES_PRINCIPALES, a.principale, a.principaleBord, 6],
  ];
  for (const [classes, couleur, bord, minzoom] of groupes) {
    for (const classe of classes) {
      const filtre = ["all", ["==", ["get", "classe"], classe], ["!", ["has", "tunnel"]]];
      if (bord) {
        out.push({ id: `route-bord-${classe}`, type: "line", source: "osm", "source-layer": "routes", minzoom, filter: filtre,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": bord, "line-width": largeur(classe, 1.35), "line-opacity": ["interpolate", ["linear"], ["zoom"], minzoom, 0, minzoom + 1, 1] } });
      }
      out.push({ id: `route-${classe}`, type: "line", source: "osm", "source-layer": "routes", minzoom, filter: filtre,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": couleur, "line-width": largeur(classe),
          ...(CLASSES_CHEMINS.includes(classe) ? { "line-dasharray": [1.5, 1.2] } : {}),
          "line-opacity": ["interpolate", ["linear"], ["zoom"], minzoom, 0, minzoom + 1, 1] } });
    }
  }
  return out;
}

export function construireStyle(nomAmbiance = "jour") {
  const a = AMBIANCES[nomAmbiance] || AMBIANCES.jour;
  const url = `pmtiles://${location.origin}${CARTE.tuiles}`;
  return {
    version: 8,
    name: `Yilgré — ${nomAmbiance}`,
    glyphs: `${location.origin}${CARTE.polices}`,
    sources: { osm: { type: "vector", url, attribution: CARTE.attribution } },
    sky: a.ciel,
    light: a.lumiere,
    layers: [
      { id: "fond", type: "background", paint: { "background-color": a.fond } },
      { id: "occupation", type: "fill", source: "osm", "source-layer": "occupation",
        paint: {
          "fill-color": ["match", ["get", "classe"],
            ["park", "garden", "grass", "forest", "wood", "scrub", "grassland", "meadow", "recreation_ground", "nature_reserve", "golf_course", "orchard", "allotments", "farmland", "heath", "wetland"], a.vert,
            ["pitch", "stadium", "sports_centre", "playground"], a.vert,
            ["sand", "bare_rock", "construction", "brownfield", "greenfield"], a.sable,
            ["commercial", "retail", "marketplace"], a.commerce,
            ["industrial", "military", "prison"], a.industrie,
            ["residential"], a.residentiel,
            a.equipement],
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 10, 0.55, 14, 0.9],
        } },
      { id: "eau", type: "fill", source: "osm", "source-layer": "eau", paint: { "fill-color": a.eau } },
      { id: "cours-eau", type: "line", source: "osm", "source-layer": "cours_eau", filter: ["!", ["has", "tunnel"]],
        paint: { "line-color": a.eau, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 16, ["match", ["get", "classe"], ["river", "canal"], 6, 2.5]] } },
      { id: "limites", type: "line", source: "osm", "source-layer": "limites", filter: ["<=", ["to-number", ["get", "niveau_admin"], 99], 8],
        paint: { "line-color": a.limite, "line-width": 1, "line-dasharray": [3, 2], "line-opacity": 0.6 } },
      ...couchesRoutes(a),
      { id: "rail", type: "line", source: "osm", "source-layer": "rail", minzoom: 10,
        paint: { "line-color": a.rail, "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.8, 16, 2.4], "line-dasharray": [3, 2] } },
      // Bâtiments : emprises OSM en 2D au loin, extrudées en 3D en s'approchant.
      { id: "batiments-plats", type: "fill", source: "osm", "source-layer": "batiments", minzoom: 13, maxzoom: 14.6,
        paint: { "fill-color": a.bat[1], "fill-opacity": ["interpolate", ["linear"], ["zoom"], 13, 0, 13.6, 0.85] } },
      { id: "batiments-3d", type: "fill-extrusion", source: "osm", "source-layer": "batiments", minzoom: 14,
        paint: {
          "fill-extrusion-color": ["interpolate", ["linear"], exprHauteur, 2, a.bat[0], 5, a.bat[1], 10, a.bat[2], 24, a.batHaut],
          "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 14, 0, 15, exprHauteur],
          "fill-extrusion-base": exprBase,
          "fill-extrusion-opacity": 0.96,
          "fill-extrusion-vertical-gradient": true,
        } },
      // Étiquettes : noms de rues, eau, points d'intérêt, quartiers, ville.
      { id: "noms-rues", type: "symbol", source: "osm", "source-layer": "routes", minzoom: 14.5,
        filter: ["all", ["has", "nom"], ["!", ["in", ["get", "classe"], ["literal", CLASSES_CHEMINS]]]],
        layout: { "symbol-placement": "line", "text-field": NOM, "text-font": POLICE, "text-size": ["interpolate", ["linear"], ["zoom"], 14.5, 10, 18, 13],
          "text-max-angle": 30, "text-padding": 4 },
        paint: { "text-color": a.texte, "text-halo-color": a.halo, "text-halo-width": 1.4 } },
      { id: "noms-eau", type: "symbol", source: "osm", "source-layer": "eau", minzoom: 12, filter: ["has", "nom"],
        layout: { "text-field": NOM, "text-font": ITALIQUE, "text-size": 12 },
        paint: { "text-color": a.eauTexte, "text-halo-color": a.halo, "text-halo-width": 1 } },
      // Points d'intérêt OSM : petits losanges de couleur sourde, pour ne jamais se confondre avec les signalements.
      { id: "poi-points", type: "circle", source: "osm", "source-layer": "poi", minzoom: 15.5,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 15.5, 2, 18, 3.5],
          "circle-color": ["match", ["get", "famille"], "sante", "#c94f5d", "education", "#4f78b5", "commerce", "#c98a2b",
            "culte", "#7f6aa8", "administration", "#4b6b5f", "transport", "#5f6f80", "loisirs", "#3f8f5a", "#8a8378"],
          "circle-stroke-color": a.halo, "circle-stroke-width": 1.2,
          "circle-opacity": ["interpolate", ["linear"], ["zoom"], 15.5, 0, 16, 0.6],
          "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 15.5, 0, 16, 0.8],
        } },
      { id: "poi-noms", type: "symbol", source: "osm", "source-layer": "poi", minzoom: 16, filter: ["has", "nom"],
        layout: { "text-field": NOM, "text-font": POLICE, "text-size": 11, "text-offset": [0, 0.9], "text-anchor": "top",
          "text-max-width": 9, "text-optional": true },
        paint: { "text-color": a.texte, "text-halo-color": a.halo, "text-halo-width": 1.3, "text-opacity": 0.85 } },
      { id: "noms-quartiers", type: "symbol", source: "osm", "source-layer": "lieux", minzoom: 11,
        filter: ["in", ["get", "classe"], ["literal", ["suburb", "quarter", "neighbourhood", "village", "borough", "hamlet"]]],
        layout: { "text-field": NOM, "text-font": POLICE_GRAS, "text-transform": "uppercase", "text-letter-spacing": 0.12,
          "text-size": ["interpolate", ["linear"], ["zoom"], 11, 10, 15, 13], "text-max-width": 8, "text-padding": 8 },
        paint: { "text-color": a.lieu, "text-halo-color": a.halo, "text-halo-width": 1.6,
          "text-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.75, 16.5, 0.85, 17.5, 0] } },
      { id: "noms-villes", type: "symbol", source: "osm", "source-layer": "lieux", maxzoom: 13,
        filter: ["in", ["get", "classe"], ["literal", ["city", "town"]]],
        layout: { "text-field": NOM, "text-font": POLICE_GRAS, "text-size": ["match", ["get", "classe"], "city", 18, 13], "text-letter-spacing": 0.04 },
        paint: { "text-color": a.lieu, "text-halo-color": a.halo, "text-halo-width": 2 } },
    ],
  };
}
