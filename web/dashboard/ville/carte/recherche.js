// Recherche locale dans la ville : index tiré des tuiles OSM (lieux, rues, points d'intérêt nommés), sans géocodeur en
// ligne. Insensible aux accents et à la casse ; les débuts de mots passent devant.
const URL_INDEX = "/dashboard/ville/carte/data/recherche.json";
let index = null;

export const normaliser = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[’'`-]/g, " ").replace(/\s+/g, " ").trim();

export async function chargerIndex() {
  if (index) return index;
  const r = await fetch(URL_INDEX);
  if (!r.ok) throw new Error("index de recherche absent (./scripts/fabriquer_tuiles.sh)");
  const d = await r.json();
  index = d.entrees.map((e) => ({ ...e, cle: normaliser(e.n) }));
  return index;
}

const PRIORITE = { "Arrondissement / secteur": 0, Quartier: 0, Ville: 0, Commune: 1, Village: 2, Rue: 3, Santé: 4, "Commerce, marché": 4, Administration: 4 };

/** Résultats pour une saisie ; `extras` : entrées supplémentaires (camions, quartiers du plan) au même format. */
export function chercher(texte, extras = [], limite = 8) {
  const q = normaliser(texte);
  if (q.length < 2) return [];
  const mots = q.split(" ");
  const tout = [...extras.map((e) => ({ ...e, cle: normaliser(e.n) })), ...(index || [])];
  const scores = [];
  for (const e of tout) {
    if (!mots.every((m) => e.cle.includes(m))) continue;
    const debut = e.cle.startsWith(q) ? 0 : e.cle.split(" ").some((w) => w.startsWith(mots[0])) ? 1 : 2;
    scores.push([debut, e.extra ? -1 : PRIORITE[e.t] ?? 5, e.n.length, e]);
  }
  scores.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  const vus = new Set();
  const out = [];
  for (const [, , , e] of scores) {
    const k = `${e.n}|${e.t}`;
    if (vus.has(k)) continue;
    vus.add(k);
    out.push(e);
    if (out.length >= limite) break;
  }
  return out;
}
