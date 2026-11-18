// Réglages de la carte MapLibre de Ouagadougou : sources locales (aucun service en ligne), emprise, caméra, hauteurs.

export const CARTE = {
  // Tuiles vectorielles auto-hébergées, fabriquées par scripts/fabriquer_tuiles.sh depuis l'extrait OSM Geofabrik.
  tuiles: "/dashboard/ville/carte/data/ouagadougou.pmtiles",
  polices: "/dashboard/ville/carte/polices/{fontstack}/{range}.pbf",
  // Emprise des tuiles (lon/lat) : la caméra ne sort pas de la zone fabriquée.
  emprise: [[-1.72, 12.2], [-1.36, 12.53]],
  centre: [-1.5197, 12.3714],   // Ouagadougou, centre-ville
  vueVille: { zoom: 11.6, pitch: 0, bearing: 0 },
  vueDepart: { zoom: 14.6, pitch: 55, bearing: -17 },
  zoomMin: 9.5,
  zoomMax: 19.5,
  attribution: "© contributeurs OpenStreetMap (ODbL) · tuiles Yilgré (Planetiler) · MapLibre",
};

// Hauteur affichée d'un bâtiment, en mètres (expression MapLibre).
// 1. hauteur OSM (height) ; 2. étages OSM (building:levels) × 3,2 m ; 3. sinon ESTIMATION selon le type OSM, variée de
// façon déterministe par l'identifiant OSM pour éviter un bloc uniforme. La fiche du bâtiment dit laquelle s'applique.
export const NIVEAU_M = 3.2;
export const HAUTEUR_ESTIMEE = {
  apartments: 10, commercial: 7, retail: 6, office: 9, hotel: 10, hospital: 8, school: 5, university: 7, public: 7,
  government: 8, civic: 7, church: 9, mosque: 8, cathedral: 14, industrial: 6, warehouse: 6, hangar: 6, stadium: 12,
  house: 3.2, detached: 3.2, residential: 3.4, hut: 2.6, shed: 2.4, garage: 2.6, roof: 3, kiosk: 2.6, yes: 3.2,
};

export const exprHauteur = [
  "case",
  ["has", "hauteur"], ["to-number", ["get", "hauteur"]],
  ["has", "niveaux"], ["*", ["to-number", ["get", "niveaux"]], NIVEAU_M],
  ["+",
    ["match", ["get", "type"], ...Object.entries(HAUTEUR_ESTIMEE).flat(), 3.2],
    ["*", ["%", ["to-number", ["get", "osm_id"], 0], 3], 0.9]],
];

export const exprBase = [
  "case",
  ["has", "hauteur_min"], ["to-number", ["get", "hauteur_min"]],
  ["has", "niveaux_min"], ["*", ["to-number", ["get", "niveaux_min"]], NIVEAU_M],
  0,
];

/** Origine de la hauteur affichée, pour la fiche (jamais une estimation présentée comme une mesure). */
export function sourceHauteur(p) {
  if (p.hauteur !== undefined) return { m: Number(p.hauteur), source: "hauteur cartographiée dans OpenStreetMap" };
  if (p.niveaux !== undefined) return { m: Number(p.niveaux) * NIVEAU_M, source: `${p.niveaux} niveau(x) dans OpenStreetMap × ${NIVEAU_M} m` };
  const base = HAUTEUR_ESTIMEE[p.type] ?? 3.2;
  return { m: base + (Number(p.osm_id || 0) % 3) * 0.9, source: "estimée (pas de hauteur ni d'étages dans OpenStreetMap)" };
}
