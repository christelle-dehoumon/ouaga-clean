// Projection locale lat/lon <-> mètres de la scène (x vers l'est, z vers le sud), identique à web/tools/build_city_data.py.
const M_PER_DEG = 111320;

export class Projection {
  constructor(lat0, lon0) {
    this.lat0 = lat0;
    this.lon0 = lon0;
    this.k = Math.cos((lat0 * Math.PI) / 180);
  }
  /** [lat, lon] -> {x, z} en mètres. */
  toLocal(lat, lon) {
    return { x: (lon - this.lon0) * this.k * M_PER_DEG, z: -(lat - this.lat0) * M_PER_DEG };
  }
  /** {x, z} en mètres -> [lat, lon]. */
  toLatLon(x, z) {
    return [this.lat0 - z / M_PER_DEG, this.lon0 + x / (this.k * M_PER_DEG)];
  }
}

/** Décode [x0, z0, dx1, dz1, ...] (décimètres) en [[x, z], ...] (mètres). */
export function decodeDeltas(arr, start = 0) {
  const pts = [];
  let x = 0;
  let z = 0;
  for (let i = start; i + 1 < arr.length; i += 2) {
    x += arr[i];
    z += arr[i + 1];
    pts.push([x / 10, z / 10]);
  }
  return pts;
}

/** Point dans un polygone (anneau [[x, z], ...]). */
export function pointInRing(x, z, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, zi] = ring[i];
    const [xj, zj] = ring[j];
    if ((zi > z) !== (zj > z) && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}

/** Hachage déterministe 0..1 d'un entier (variations visuelles stables). */
export function hash01(n) {
  let h = Math.imul(n ^ 0x9e3779b9, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967295;
}
