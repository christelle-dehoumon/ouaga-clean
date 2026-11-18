// Matériaux de façade : textures CC0 (Poly Haven, voir textures/CREDITS.txt) réduites en cartes de détail en niveaux de
// gris de 128 px, teintées dans le navigateur selon l'ambiance puis données à MapLibre (fill-extrusion-pattern).
// Purement stylistique : le matériau réel des bâtiments n'est pas connu ; seul le type OSM choisit la famille.
// Fenêtres éclairées du soir et de la nuit : effet de style, ne représente aucune occupation réelle.

export const TYPES_MATERIAU = {
  beton: ["apartments", "commercial", "retail", "office", "hotel", "supermarket", "bank", "dormitory"],
  tole: ["industrial", "warehouse", "hangar", "garage", "garages", "service", "manufacture", "factory"],
  public: ["school", "university", "college", "kindergarten", "hospital", "clinic", "public", "government", "civic",
    "church", "mosque", "cathedral", "chapel", "temple", "religious", "stadium", "train_station", "transportation"],
  banco: ["hut", "shed", "kiosk", "roof", "cabin", "barn", "farm_auxiliary", "stable", "ruins"],
};
const FICHIERS = ["enduit", "banco", "beton", "tole", "public"];
// Motifs donnés à MapLibre : deux teintes d'enduit pour éviter un bloc uniforme, plus la sélection.
const MOTIFS = { enduit: "enduit", enduit2: "enduit", banco: "banco", beton: "beton", tole: "tole", public: "public" };

/** Expression : famille de matériau selon le type OSM (les maisons alternent deux teintes d'enduit par identifiant). */
export function exprMateriau(valeurs) {
  const branches = [];
  for (const [m, types] of Object.entries(TYPES_MATERIAU)) branches.push(types, valeurs[m]);
  return ["match", ["get", "type"], ...branches,
    ["case", ["==", ["%", ["to-number", ["get", "osm_id"], 0], 2], 0], valeurs.enduit, valeurs.enduit2]];
}
export const exprMotif = () => exprMateriau(Object.fromEntries(Object.keys(MOTIFS).map((m) => [m, `yl-${m}`])));
export const MOTIF_SELECTION = "yl-selection";

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const hache = (x, y, s) => { let h = (x * 374761393 + y * 668265263 + s * 2147483647) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };

export class Materiaux {
  constructor(map) { this.map = map; this.details = new Map(); }

  async charger() {
    await Promise.all(FICHIERS.map(async (nom) => {
      const { data } = await this.map.loadImage(new URL(`./textures/${nom}.png`, import.meta.url).href);
      const c = document.createElement("canvas");
      c.width = data.width; c.height = data.height;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(data, 0, 0);
      const px = ctx.getImageData(0, 0, c.width, c.height).data;
      const l = new Uint8Array(c.width * c.height);
      for (let i = 0; i < l.length; i++) l[i] = px[i * 4];
      this.details.set(nom, { l, w: c.width, h: c.height });
    }));
  }

  /** Teinte chaque carte de détail selon l'ambiance a (murs, fenêtres) ; updateImage évite de recharger les tuiles. */
  appliquer(a) {
    const motifs = { ...MOTIFS, selection: "enduit" };
    for (const [nom, src] of Object.entries(motifs)) {
      const d = this.details.get(src);
      if (!d) continue;
      const teinte = rgb(nom === "selection" ? "#f2c200" : a.murs[nom]);
      const out = new Uint8Array(d.w * d.h * 4);
      const densite = nom === "selection" || nom === "tole" ? 0 : a.fenetres || 0;
      const lum = rgb("#f6c873");
      for (let y = 0; y < d.h; y++) {
        for (let x = 0; x < d.w; x++) {
          const i = y * d.w + x;
          const k = 1 + ((d.l[i] - 128) / 128) * 0.6;   // contraste adouci : grain visible, teinte respectée
          let c = teinte.map((v) => v * k);
          if (densite) {
            // Grille de baies 16 × 16 px, ouverture 4 × 5 px ; quelques-unes seulement sont « allumées ».
            const cx = x >> 4, cy = y >> 4, lx = x & 15, ly = y & 15;
            if (lx >= 6 && lx < 10 && ly >= 5 && ly < 10 && hache(cx, cy, src.length) < densite) {
              const bord = lx === 6 || lx === 9 || ly === 5 || ly === 9 ? 0.7 : 1;
              c = lum.map((v) => v * bord);
            }
          }
          out.set([Math.min(255, c[0]), Math.min(255, c[1]), Math.min(255, c[2]), 255], i * 4);
        }
      }
      const id = `yl-${nom}`;
      const image = { width: d.w, height: d.h, data: out };
      if (this.map.hasImage(id)) this.map.updateImage(id, image);
      else this.map.addImage(id, image, { pixelRatio: 2 });   // grain plus fin (64 px à l'écran)
    }
  }
}
