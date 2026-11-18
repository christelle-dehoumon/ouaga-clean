// Style cartographique de VIELA pour les tuiles du schéma scripts/tuiles/schema_yilgre.yml.
import { CARTE, exprBase, exprHauteur } from "./config.js";
import { exprMateriau, exprMotif } from "./materiaux.js";

// Quatre ambiances (jour, doré, soir, nuit) : couleurs, lumière, ciel et ombres stylisées changent, jamais la géographie.
// murs : teintes des façades (motifs de materiaux.js en haute qualité, couleurs pleines en mode léger) ; toits : dalle
// de toiture posée sur chaque bâtiment ; ombre : ombres portées simulées (MapLibre n'en calcule pas pour les extrusions),
// orientées comme la lumière (azimut en degrés depuis le nord, longueur = facteur de la hauteur affichée).
export const AMBIANCES = {
  jour: {
    fond: "#efe7da", residentiel: "#ebe2d3", vert: "#d2e0b6", eau: "#9fcbe0", eauTexte: "#2f6a86", sable: "#eadbbd",
    equipement: "#ece2d4", commerce: "#f0ddd0", industrie: "#e3ddd5", route: "#ffffff", routeBord: "#d8ccb8",
    principale: "#fde3a7", principaleBord: "#d6ae60", chemin: "#c9bba2", rail: "#a39c92", plats: "#dccfbc",
    murs: { enduit: "#f4e4ca", enduit2: "#efd2ae", banco: "#dcb28a", beton: "#ebe7df", tole: "#c8ced1", public: "#e6b190" },
    toits: { enduit: ["#d8ccbb", "#cbb8a2", "#bfae9c"], banco: "#bd9874", beton: "#efebe4", tole: "#b5bcc0", public: "#cf9a80" },
    texte: "#3c3a35", halo: "rgba(255,255,255,.92)", lieu: "#2e2b26", limite: "#a7998a", fenetres: 0,
    lumiere: { anchor: "map", color: "#fff4e2", intensity: 0.4, position: [1.15, 235, 42] },
    ombre: { couleur: "#4a3b2a", azimut: 235, longueur: 0.9, opacite: 0.2 },
    ciel: { "sky-color": "#b9d7ee", "horizon-color": "#efe4cf", "fog-color": "#ede4d3", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.75, "fog-ground-blend": 0.92 },
  },
  dore: {
    fond: "#efd8b2", residentiel: "#ecd2a8", vert: "#cbcf8f", eau: "#86b5bb", eauTexte: "#24565e", sable: "#ebcd99",
    equipement: "#ecd4b0", commerce: "#f0cdac", industrie: "#e0ccae", route: "#fff3d8", routeBord: "#d9b480",
    principale: "#ffcf73", principaleBord: "#c4862f", chemin: "#c7a573", rail: "#9c8466", plats: "#e3c393",
    murs: { enduit: "#fbdcaa", enduit2: "#f6c68a", banco: "#e3a56e", beton: "#f6e0bc", tole: "#d3c0a2", public: "#eea776" },
    toits: { enduit: ["#d4b088", "#c69c72", "#b68a66"], banco: "#bd8455", beton: "#f2ddb8", tole: "#baa587", public: "#cd7f5a" },
    texte: "#3b2a18", halo: "rgba(255,246,226,.93)", lieu: "#2f1f10", limite: "#a8875e", fenetres: 0,
    lumiere: { anchor: "map", color: "#ffc27a", intensity: 0.55, position: [1.15, 262, 66] },
    ombre: { couleur: "#5b3214", azimut: 262, longueur: 1.9, opacite: 0.2 },
    ciel: { "sky-color": "#9fbcd4", "horizon-color": "#f8c886", "fog-color": "#f3d3a0", "sky-horizon-blend": 0.75, "horizon-fog-blend": 0.7, "fog-ground-blend": 0.85 },
  },
  soir: {
    fond: "#d6cbc6", residentiel: "#d0c3bc", vert: "#b2bc9f", eau: "#7896b4", eauTexte: "#2b4762", sable: "#d6c3b0",
    equipement: "#d4c6bf", commerce: "#dac1ba", industrie: "#c9c0bc", route: "#efe4df", routeBord: "#b6a39f",
    principale: "#f0c08c", principaleBord: "#b07c52", chemin: "#ab9a92", rail: "#887d7f", plats: "#c4b4ad",
    murs: { enduit: "#cbb4ab", enduit2: "#c2a294", banco: "#a78273", beton: "#c6beba", tole: "#a0a2ab", public: "#bb8a7d" },
    toits: { enduit: ["#a79a98", "#9a8a86", "#8d7d7a"], banco: "#8d6c60", beton: "#cdc5c2", tole: "#8d939e", public: "#9e746a" },
    texte: "#33272a", halo: "rgba(250,241,240,.92)", lieu: "#2a1f22", limite: "#9a8288", fenetres: 0.05,
    lumiere: { anchor: "map", color: "#f4c2ae", intensity: 0.3, position: [1.15, 285, 76] },
    ombre: { couleur: "#3a2c40", azimut: 285, longueur: 2.2, opacite: 0.11 },
    ciel: { "sky-color": "#6c7ca6", "horizon-color": "#efa57e", "fog-color": "#d8b4a8", "sky-horizon-blend": 0.8, "horizon-fog-blend": 0.75, "fog-ground-blend": 0.88 },
  },
  nuit: {
    fond: "#171b21", residentiel: "#1d2228", vert: "#1c2620", eau: "#0f2133", eauTexte: "#7fa8c4", sable: "#232427",
    equipement: "#20252c", commerce: "#272225", industrie: "#212328", route: "#353b43", routeBord: "#14171b",
    principale: "#9a7436", principaleBord: "#3d2f18", chemin: "#2e333a", rail: "#4a4f55", plats: "#2c323a",
    murs: { enduit: "#535a66", enduit2: "#5a5e68", banco: "#5c5249", beton: "#5e6570", tole: "#4a525d", public: "#64554f" },
    toits: { enduit: ["#3b414b", "#41464f", "#373c45"], banco: "#433d37", beton: "#4a5059", tole: "#363c44", public: "#4a3f3c" },
    texte: "#d9d6cf", halo: "rgba(15,17,20,.9)", lieu: "#f1ede4", limite: "#5b636d", fenetres: 0.16,
    lumiere: { anchor: "map", color: "#e2e8f5", intensity: 0.34, position: [1.15, 200, 35] },
    ombre: null,
    ciel: { "sky-color": "#0b111c", "horizon-color": "#1d2838", "fog-color": "#141a23", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.8, "fog-ground-blend": 0.9 },
  },
};

// Épaisseur de la dalle de toiture (mètres, prise dans la hauteur affichée : la hauteur totale ne change pas).
const EPAISSEUR_TOIT = ["min", 0.45, ["*", 0.15, exprHauteur]];
const HAUT_MUR = ["max", exprBase, ["-", exprHauteur, EPAISSEUR_TOIT]];
// Pixels par mètre à la latitude de Ouagadougou (12,37° N), au zoom 14 et 20 (tuiles de 512 px).
const PX_M = (z) => (2 ** z * 512) / (40075016.686 * Math.cos((12.37 * Math.PI) / 180));
const CLASSES_OMBRE = [
  ["bas", ["<", exprHauteur, 6], 3.6, [0.5, 1]],
  ["haut", ["all", [">=", exprHauteur, 6], ["<", exprHauteur, 14]], 9, [0.35, 0.7, 1]],
  ["tres-haut", [">=", exprHauteur, 14], 20, [0.35, 0.7, 1]],
];

/** Ombres portées simulées : empreintes décalées à l'opposé de la lumière, plusieurs pas superposés (adoucies). */
export function couchesOmbres(a) {
  const o = a.ombre || { couleur: "#000000", azimut: 0, longueur: 0, opacite: 0 };
  const rad = (o.azimut * Math.PI) / 180;
  const out = [];
  for (const [nom, filtre, hRef, pas] of CLASSES_OMBRE) {
    pas.forEach((f, i) => {
      const m = hRef * o.longueur * f;
      const v = (z) => [-Math.sin(rad) * m * PX_M(z), Math.cos(rad) * m * PX_M(z)];
      out.push({ id: `ombre-${nom}-${i + 1}`, type: "fill", source: "osm", "source-layer": "batiments", minzoom: 14.6, filter: filtre,
        paint: { "fill-color": o.couleur, "fill-antialias": true, "fill-translate-anchor": "map",
          "fill-translate": { base: 2, stops: [[14, v(14)], [20, v(20)]] },
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 14.6, 0, 15.4, o.opacite] } });
    });
  }
  return out;
}

/** Peinture des bâtiments extrudés et de leurs toits selon l'ambiance et la qualité (motifs ou couleurs pleines). */
export function peintureBatiments(a, motifs) {
  return {
    murs: {
      "fill-extrusion-color": exprMateriau(a.murs),
      "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 14, 0, 15, motifs ? HAUT_MUR : exprHauteur],
      "fill-extrusion-base": exprBase,
      "fill-extrusion-opacity": 1,
      "fill-extrusion-vertical-gradient": true,
      ...(motifs ? { "fill-extrusion-pattern": exprMotif() } : {}),
    },
    toits: {
      "fill-extrusion-color": exprMateriau({ ...a.toits,
        enduit: ["match", ["%", ["to-number", ["get", "osm_id"], 0], 3], 0, a.toits.enduit[0], 1, a.toits.enduit[1], a.toits.enduit[2]],
        enduit2: ["match", ["%", ["to-number", ["get", "osm_id"], 0], 3], 0, a.toits.enduit[1], 1, a.toits.enduit[2], a.toits.enduit[0]] }),
      "fill-extrusion-height": exprHauteur,
      "fill-extrusion-base": HAUT_MUR,
      "fill-extrusion-opacity": 1,
      "fill-extrusion-vertical-gradient": false,
    },
  };
}

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

export function construireStyle(nomAmbiance = "jour", { motifs = false } = {}) {
  const a = AMBIANCES[nomAmbiance] || AMBIANCES.jour;
  const bat = peintureBatiments(a, motifs);
  const url = `pmtiles://${location.origin}${CARTE.tuiles}`;
  return {
    version: 8,
    name: `VIELA — ${nomAmbiance}`,
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
      ...couchesOmbres(a),
      { id: "batiments-plats", type: "fill", source: "osm", "source-layer": "batiments", minzoom: 13, maxzoom: 14.6,
        paint: { "fill-color": a.plats, "fill-opacity": ["interpolate", ["linear"], ["zoom"], 13, 0, 13.6, 0.85] } },
      { id: "batiments-3d", type: "fill-extrusion", source: "osm", "source-layer": "batiments", minzoom: 14, paint: bat.murs },
      // Dalle de toiture : distingue toits et murs (un motif MapLibre habille sinon les deux faces de la même façon).
      { id: "batiments-toits", type: "fill-extrusion", source: "osm", "source-layer": "batiments", minzoom: 15, paint: bat.toits },
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
