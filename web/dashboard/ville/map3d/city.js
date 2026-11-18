// Ville : sol, bâtiments OSM extrudés (par tuiles, hauteur estimée sauf balise OSM), routes (latérite / bitume),
// plans d'eau, quartiers. Géométries fusionnées par tuile pour limiter les appels de dessin.
import * as THREE from "three";
import { decodeDeltas, hash01, pointInRing } from "./geo.js";

const TILE = 450; // m
const WALLS = [0xd9b98c, 0xc99a6b, 0xe3cfae, 0xb97a55, 0xd8a77d, 0xece0c8, 0xc58f71, 0xdcc3a1];
const ROOFS = [0x8b8f92, 0x9a6d55, 0xb7a58a, 0x7d8489, 0xa8907a, 0xc9bca5, 0x6f7a80];
const ROAD = { paved: 0x6e6a63, laterite: 0xbb7650, major: 0x5d5a55 };

function tileKey(x, z) {
  return `${Math.floor(x / TILE)}:${Math.floor(z / TILE)}`;
}

function colorArr(hex, f = 1) {
  const c = new THREE.Color(hex); // déjà converti en espace linéaire par la gestion des couleurs de three
  return [c.r * f, c.g * f, c.b * f];
}

/** Charge et décode city.json. */
export async function loadCity(url, onProgress) {
  onProgress?.("Téléchargement des données de la ville…");
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Données de la ville introuvables (HTTP ${r.status}).`);
  const data = await r.json();
  onProgress?.("Décodage des bâtiments et des routes…");
  return data;
}

export function buildCity(scene3d, data) {
  const group = new THREE.Group();
  group.name = "ville";
  const out = { group, roadMeshes: [], territories: [], bounds: null, roads: [], stats: {} };

  // --- Bâtiments --------------------------------------------------------------
  const tiles = new Map();
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  data.buildings.forEach((b, idx) => {
    const h = b[0] / 10;
    const ring = decodeDeltas(b, 2);
    if (ring.length < 3) return;
    let cx = 0, cz = 0;
    for (const [x, z] of ring) { cx += x; cz += z; minX = Math.min(minX, x); maxX = Math.max(maxX, x); minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z); }
    cx /= ring.length; cz /= ring.length;
    const key = tileKey(cx, cz);
    if (!tiles.has(key)) tiles.set(key, { pos: [], col: [] });
    const t = tiles.get(key);
    const r = hash01(idx + 17);
    const wall = WALLS[Math.floor(r * WALLS.length)];
    const roof = ROOFS[Math.floor(hash01(idx * 7 + 3) * ROOFS.length)];
    const wallTop = colorArr(wall, 1.0);
    const wallBot = colorArr(wall, 0.62);
    const roofC = colorArr(roof, 1.0);
    // Toit : triangulation de l'emprise.
    const contour = ring.map(([x, z]) => new THREE.Vector2(x, z));
    if (THREE.ShapeUtils.isClockWise(contour)) contour.reverse();
    const tris = THREE.ShapeUtils.triangulateShape(contour, []);
    for (const tri of tris) {
      for (const k of [tri[0], tri[2], tri[1]]) {
        t.pos.push(contour[k].x, h, contour[k].y);
        t.col.push(...roofC);
      }
    }
    // Murs : un quad par arête, plus sombre en bas (occlusion simulée).
    for (let i = 0; i < contour.length; i++) {
      const a = contour[i];
      const c = contour[(i + 1) % contour.length];
      t.pos.push(a.x, 0, a.y, c.x, 0, c.y, c.x, h, c.y, a.x, 0, a.y, c.x, h, c.y, a.x, h, a.y);
      t.col.push(...wallBot, ...wallBot, ...wallTop, ...wallBot, ...wallTop, ...wallTop);
    }
  });
  const bMat = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true, side: THREE.DoubleSide });
  bMat.shadowSide = THREE.FrontSide; // évite les stries d'auto-ombrage des matériaux double face
  for (const t of tiles.values()) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(t.pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(t.col, 3));
    g.computeVertexNormals();
    g.computeBoundingSphere();
    const m = new THREE.Mesh(g, bMat);
    m.castShadow = true;
    m.receiveShadow = true;
    m.userData.kind = "batiments";
    group.add(m);
  }
  out.stats.buildingTiles = tiles.size;

  // --- Routes ---------------------------------------------------------------
  const roadTiles = new Map();
  data.roads.forEach((road, ri) => {
    const pts = decodeDeltas(road.c);
    if (pts.length < 2) return;
    out.roads.push({ id: road.e, kind: road.k, name: road.n, paved: Boolean(road.p), truck: Boolean(road.t), pts });
    const key = tileKey(pts[0][0], pts[0][1]);
    if (!roadTiles.has(key)) roadTiles.set(key, { pos: [], col: [], face: [] });
    const t = roadTiles.get(key);
    const w = road.w / 2;
    const major = ["motorway", "trunk", "primary", "secondary"].includes(road.k);
    const col = colorArr(major ? ROAD.major : road.p ? ROAD.paved : ROAD.laterite);
    const y = major ? 0.09 : road.p ? 0.07 : 0.06;
    const idx = out.roads.length - 1;
    for (let i = 0; i < pts.length - 1; i++) {
      const [x1, z1] = pts[i];
      const [x2, z2] = pts[i + 1];
      const len = Math.hypot(x2 - x1, z2 - z1) || 1;
      const nx = (-(z2 - z1) / len) * w;
      const nz = ((x2 - x1) / len) * w;
      t.pos.push(x1 + nx, y, z1 + nz, x2 + nx, y, z2 + nz, x2 - nx, y, z2 - nz, x1 + nx, y, z1 + nz, x2 - nx, y, z2 - nz, x1 - nx, y, z1 - nz);
      for (let k = 0; k < 6; k++) t.col.push(...col);
      t.face.push(idx, idx);
      // Jonction : octogone au nœud pour des virages et carrefours sans trou ni dent de scie.
      for (let k = 0; k < 8; k++) {
        const a1 = (k / 8) * Math.PI * 2;
        const a2 = ((k + 1) / 8) * Math.PI * 2;
        t.pos.push(x2, y, z2, x2 + Math.cos(a1) * w, y, z2 + Math.sin(a1) * w, x2 + Math.cos(a2) * w, y, z2 + Math.sin(a2) * w);
        for (let q = 0; q < 3; q++) t.col.push(...col);
        t.face.push(idx);
      }
    }
    void ri;
  });
  const rMat = new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  for (const t of roadTiles.values()) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(t.pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(t.col, 3));
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, rMat);
    m.receiveShadow = true;
    m.userData = { kind: "routes", faceToRoad: Int32Array.from(t.face) };
    group.add(m);
    out.roadMeshes.push(m);
  }

  // --- Arbres ILLUSTRATIFS (non issus d'OSM) le long des rues résidentielles -------------------
  out.trees = trees(out.roads);
  group.add(out.trees);

  // --- Sol ------------------------------------------------------------------
  const pad = 2500;
  out.bounds = { minX, maxX, minZ, maxZ };
  const gw = maxX - minX + pad * 2;
  const gh = maxZ - minZ + pad * 2;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(gw, gh), new THREE.MeshLambertMaterial({ color: 0xf2e6d2, map: sandTexture() }));
  ground.material.map.repeat.set(gw / 60, gh / 60);
  ground.rotation.x = -Math.PI / 2;
  ground.position.set((minX + maxX) / 2, 0, (minZ + maxZ) / 2);
  ground.receiveShadow = true;
  ground.userData.kind = "sol";
  group.add(ground);
  out.ground = ground;

  // --- Eau -------------------------------------------------------------------
  const waterMat = new THREE.MeshLambertMaterial({ color: 0x3f7f8f, transparent: true, opacity: 0.92 });
  for (const w of data.water) {
    for (const r of w.r) {
      const pts = decodeDeltas(r).map(([x, z]) => new THREE.Vector2(x, -z));
      if (pts.length < 3) continue;
      const geo = new THREE.ShapeGeometry(new THREE.Shape(pts));
      geo.rotateX(-Math.PI / 2);
      const mesh = new THREE.Mesh(geo, waterMat);
      mesh.position.y = 0.04;
      mesh.receiveShadow = true;
      mesh.userData = { kind: "eau", name: w.n };
      group.add(mesh);
    }
  }

  // --- Quartiers (surfaces de sélection + liserés) ----------------------------
  for (const t of data.territories) {
    const rings = t.r.map((r) => decodeDeltas(r));
    const tGroup = new THREE.Group();
    const color = t.secteur ? 0x009e49 : 0xfcd116;
    const fillMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0, depthWrite: false });
    for (const ring of rings) {
      const geo = new THREE.ShapeGeometry(new THREE.Shape(ring.map(([x, z]) => new THREE.Vector2(x, -z))));
      geo.rotateX(-Math.PI / 2);
      const fill = new THREE.Mesh(geo, fillMat);
      fill.position.y = 0.12;
      fill.renderOrder = 2;
      fill.userData = { kind: "quartier", territory: t };
      tGroup.add(fill);
      tGroup.add(border(ring, color, t.secteur ? 7 : 5));
    }
    let cx = 0, cz = 0, n = 0;
    for (const [x, z] of rings[0]) { cx += x; cz += z; n += 1; }
    const info = { ...t, rings, center: { x: cx / n, z: cz / n }, group: tGroup, fillMat,
      contains: (x, z) => rings.some((ring) => pointInRing(x, z, ring)) };
    tGroup.userData.territory = info;
    group.add(tGroup);
    out.territories.push(info);
  }
  scene3d.scene.add(group);
  return out;
}

/** Arbres illustratifs : instances (tronc + houppier) espacées le long des rues, positions déterministes. */
function trees(roads) {
  const spots = [];
  roads.forEach((r, ri) => {
    if (!["residential", "unclassified", "tertiary", "living_street"].includes(r.kind)) return;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x1, z1] = r.pts[i];
      const [x2, z2] = r.pts[i + 1];
      const len = Math.hypot(x2 - x1, z2 - z1);
      for (let d = 12; d < len - 6; d += 26) {
        const h = hash01(ri * 131 + i * 17 + Math.floor(d));
        if (h > 0.55) continue;
        const side = h > 0.27 ? 1 : -1;
        const off = 5.5 + h * 3;
        const ux = (x2 - x1) / len, uz = (z2 - z1) / len;
        spots.push([x1 + ux * d - uz * off * side, z1 + uz * d + ux * off * side, 0.7 + hash01(ri + i + d) * 0.7]);
      }
    }
  });
  const g = new THREE.Group();
  g.name = "arbres-illustratifs";
  const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.25, 0.35, 3, 5).translate(0, 1.5, 0),
    new THREE.MeshLambertMaterial({ color: 0x6b4a32 }), spots.length);
  const crown = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(2.6, 0).translate(0, 4.4, 0),
    new THREE.MeshLambertMaterial({ color: 0x5f7d3a, flatShading: true }), spots.length);
  const m = new THREE.Matrix4();
  const c = new THREE.Color();
  spots.forEach(([x, z, k], i) => {
    m.makeScale(k, k, k).setPosition(x, 0, z);
    trunk.setMatrixAt(i, m);
    crown.setMatrixAt(i, m);
    crown.setColorAt(i, c.setHSL(0.22 + hash01(i) * 0.06, 0.38, 0.28 + hash01(i + 5) * 0.1));
  });
  crown.castShadow = true;
  trunk.castShadow = true;
  g.add(trunk, crown);
  g.userData = { kind: "arbres", count: spots.length, illustratif: true };
  return g;
}

/** Liseré de quartier : ruban posé au sol, en pointillés. */
function border(ring, color, width) {
  const pos = [];
  const closed = [...ring, ring[0]];
  for (let i = 0; i < closed.length - 1; i++) {
    const [x1, z1] = closed[i];
    const [x2, z2] = closed[i + 1];
    const len = Math.hypot(x2 - x1, z2 - z1) || 1;
    const steps = Math.max(1, Math.floor(len / 30));
    for (let s = 0; s < steps; s += 1) {
      if (s % 2) continue;
      const a = s / steps;
      const b = Math.min(1, (s + 1) / steps);
      const ax = x1 + (x2 - x1) * a, az = z1 + (z2 - z1) * a;
      const bx = x1 + (x2 - x1) * b, bz = z1 + (z2 - z1) * b;
      const nx = (-(bz - az) / (len / steps)) * width / 2;
      const nz = ((bx - ax) / (len / steps)) * width / 2;
      pos.push(ax + nx, 0.3, az + nz, bx + nx, 0.3, bz + nz, bx - nx, 0.3, bz - nz, ax + nx, 0.3, az + nz, bx - nx, 0.3, bz - nz, ax - nx, 0.3, az - nz);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, transparent: true, opacity: 0.85 }));
  m.renderOrder = 3;
  m.userData.kind = "lisere";
  return m;
}

/** Texture de sol procédurale (sable, latérite, petites variations) : aucune image externe. */
function sandTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#d4bc95";
  ctx.fillRect(0, 0, 128, 128);
  for (let i = 0; i < 1400; i++) {
    const r = hash01(i * 3 + 1);
    const g = hash01(i * 5 + 2);
    ctx.fillStyle = r > 0.5 ? `rgba(160,100,60,${0.05 + g * 0.08})` : `rgba(240,225,195,${0.05 + g * 0.1})`;
    ctx.fillRect(hash01(i) * 128, hash01(i + 999) * 128, 1 + r * 3, 1 + g * 3);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
