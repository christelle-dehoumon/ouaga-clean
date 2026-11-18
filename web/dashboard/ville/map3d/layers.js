// Couches opérationnelles reliées aux données de l'API : signalements, dépotoirs simulés, points de regroupement,
// tournées, points non desservis ou reportés, routes coupées. Symboles agrandis à l'écran pour rester lisibles.
import * as THREE from "three";
import { disposeObject } from "./scene.js";

export const STATUTS = {
  "depotoir:a_verifier": { couleur: 0xfcd116, libelle: "Dépotoir à vérifier (brigade)" },
  "depotoir:confirme": { couleur: 0xef2b2d, libelle: "Dépotoir confirmé" },
  "depotoir:rejete": { couleur: 0x8c8c8c, libelle: "Signalement rejeté" },
  "nettoyage:a_verifier": { couleur: 0x2d8fa0, libelle: "Nettoyage à vérifier" },
  "nettoyage:rejete": { couleur: 0x5a5a5a, libelle: "Nettoyage rejeté" },
  "nettoyage:nettoye": { couleur: 0x009e49, libelle: "Nettoyé" },
  simule: { couleur: 0x8e44ad, libelle: "Dépotoir simulé (fictif)" },
};
export const VEHICLE_COLORS = [0xef2b2d, 0x1f6fb2, 0x009e49, 0xe67e22, 0x8e44ad, 0x16a085, 0xc0392b, 0x2c3e50,
  0xd35400, 0x27ae60, 0x7f8c8d, 0xb7950b];

const ROUTE_Y = 0.6;

function pinGeometry() {
  const head = new THREE.SphereGeometry(3.2, 16, 12).translate(0, 13, 0);
  const cone = new THREE.ConeGeometry(3.2, 9, 16, 1, true).rotateX(Math.PI).translate(0, 7.6, 0);
  const g = mergeGeometries([head, cone]);
  return g;
}

function mergeGeometries(list) {
  const pos = [];
  const norm = [];
  for (const g of list) {
    const ng = g.index ? g.toNonIndexed() : g;
    pos.push(...ng.attributes.position.array);
    norm.push(...ng.attributes.normal.array);
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  out.setAttribute("normal", new THREE.Float32BufferAttribute(norm, 3));
  return out;
}

/** Ruban posé au-dessus des routes le long d'une polyligne [[x, z], ...]. */
export function ribbon(points, width, y = ROUTE_Y) {
  const pos = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [x1, z1] = points[i];
    const [x2, z2] = points[i + 1];
    const len = Math.hypot(x2 - x1, z2 - z1);
    if (len < 0.01) continue;
    const nx = (-(z2 - z1) / len) * (width / 2);
    const nz = ((x2 - x1) / len) * (width / 2);
    pos.push(x1 + nx, y, z1 + nz, x2 + nx, y, z2 + nz, x2 - nx, y, z2 - nz, x1 + nx, y, z1 + nz, x2 - nx, y, z2 - nz, x1 - nx, y, z1 - nz);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  return g;
}

export class Layers {
  constructor(scene3d, proj) {
    this.s = scene3d;
    this.proj = proj;
    this.root = new THREE.Group();
    this.root.name = "couches";
    this.groups = {};
    for (const name of ["signalements", "simules", "points", "tournees", "alertes", "coupures", "selection"]) {
      this.groups[name] = new THREE.Group();
      this.groups[name].name = name;
      this.root.add(this.groups[name]);
    }
    scene3d.scene.add(this.root);
    this.pinGeo = pinGeometry();
    this.ringGeo = new THREE.TorusGeometry(9, 1.1, 8, 40).rotateX(Math.PI / 2);
    this.materials = new Map();
    this.scaled = []; // objets dont la taille suit la distance de la caméra
    this.pulse = [];
    this.vehicleColor = new Map();
    scene3d.onFrame((dt) => this.update(dt));
  }

  mat(color, opts = {}) {
    const key = `${color}:${JSON.stringify(opts)}`;
    if (!this.materials.has(key)) this.materials.set(key, new THREE.MeshLambertMaterial({ color, ...opts }));
    return this.materials.get(key);
  }

  local(lat, lon) {
    return this.proj.toLocal(Number(lat), Number(lon));
  }

  clear(name) {
    const g = this.groups[name];
    for (const child of [...g.children]) {
      child.traverse((o) => { if (o.geometry && o.geometry !== this.pinGeo && o.geometry !== this.ringGeo) o.geometry.dispose(); });
      g.remove(child);
    }
    this.scaled = this.scaled.filter((o) => o.parent);
    this.pulse = this.pulse.filter((o) => o.parent);
  }

  /** Signalements de l'API (type, statut, lat, lon). */
  setReports(reports) {
    this.clear("signalements");
    for (const r of reports) {
      if (!Number.isFinite(Number(r.lat)) || !Number.isFinite(Number(r.lon))) continue;
      const st = STATUTS[`${r.type}:${r.statut}`] || STATUTS["depotoir:a_verifier"];
      const { x, z } = this.local(r.lat, r.lon);
      const pin = new THREE.Mesh(this.pinGeo, this.mat(st.couleur));
      pin.position.set(x, 0, z);
      pin.castShadow = true;
      pin.userData = { kind: "signalement", data: r, label: st.libelle };
      this.groups.signalements.add(pin);
      this.scaled.push(pin);
    }
  }

  /** Dépotoirs simulés (sim.db) : violets, marqués « simulé ». */
  setSimDumps(list) {
    this.clear("simules");
    for (const d of list) {
      const { x, z } = this.local(d.lat, d.lon);
      const pin = new THREE.Mesh(this.pinGeo, this.mat(STATUTS.simule.couleur));
      pin.position.set(x, 0, z);
      pin.userData = { kind: "simule", data: d, label: STATUTS.simule.libelle };
      this.groups.simules.add(pin);
      this.scaled.push(pin);
    }
  }

  /** Plan : points de regroupement, tournées, non desservis, reportés, coupures. */
  setPlan(plan) {
    for (const name of ["points", "tournees", "alertes", "coupures"]) this.clear(name);
    if (!plan) return;
    const unserved = new Map((plan.unserved || []).map((u) => [u.point_id, u]));
    const postponed = new Map((plan.postponed || []).map((p) => [p.id, p]));
    const binGeo = new THREE.CylinderGeometry(2.6, 3.2, 1, 10).translate(0, 0.5, 0);
    for (const p of plan.consolidation_points || plan.collection_points || []) {
      if (!Number.isFinite(Number(p.lat))) continue;
      const { x, z } = this.local(p.lat, p.lon);
      const dump = p.type === "dumpsite";
      const status = unserved.has(p.id) ? "non_desservi" : postponed.has(p.id) ? "reporte" : "desservi";
      const color = status === "non_desservi" ? 0xef2b2d : status === "reporte" ? 0xe67e22 : dump ? 0x9a6b3c : 0x009e49;
      const h = Math.max(3, Math.min(26, Math.sqrt(Number(p.demand_kg) || 0) / 4));
      const bin = new THREE.Mesh(binGeo, this.mat(color));
      bin.scale.set(1, h, 1);
      bin.position.set(x, 0, z);
      bin.castShadow = true;
      bin.userData = { kind: "point", data: p, status, raison: unserved.get(p.id) || postponed.get(p.id) || null, h };
      this.groups.points.add(bin);
      this.scaled.push(bin);
      if (status !== "desservi") {
        const ring = new THREE.Mesh(this.ringGeo, this.mat(color, { emissive: color, emissiveIntensity: 0.6 }));
        ring.position.set(x, 1, z);
        ring.userData = { kind: "point", data: p, status, raison: unserved.get(p.id) || postponed.get(p.id) };
        this.groups.alertes.add(ring);
        this.pulse.push(ring);
      }
    }
    // Tournées : un ruban par trajet, couleur du camion.
    const trucks = [...new Set((plan.routes || []).map((r) => String(r.vehicle_id || r.vehicle).split("_trip")[0]))].sort(
      (a, b) => Number(a.replace(/\D/g, "")) - Number(b.replace(/\D/g, "")));
    trucks.forEach((t, i) => this.vehicleColor.set(t, VEHICLE_COLORS[i % VEHICLE_COLORS.length]));
    for (const r of plan.routes || []) {
      const path = (r.path || []).map(([lat, lon]) => { const p = this.local(lat, lon); return [p.x, p.z]; });
      if (path.length < 2) continue;
      const truck = String(r.vehicle_id || r.vehicle).split("_trip")[0];
      const color = this.vehicleColor.get(truck) ?? 0xef2b2d;
      const mesh = new THREE.Mesh(ribbon(path, this.routeWidth || 4), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9, side: THREE.DoubleSide, depthWrite: false }));
      mesh.renderOrder = 4;
      mesh.userData = { kind: "tournee", data: r, truck, path };
      this.groups.tournees.add(mesh);
    }
    for (const c of plan.cut_roads || []) this.addCut(c);
  }

  /** Route coupée : barrière rouge et blanche à son milieu. */
  addCut(cut, road = null) {
    const g = new THREE.Group();
    let x;
    let z;
    if (road) {
      const mid = road.pts[Math.floor(road.pts.length / 2)];
      [x, z] = mid;
      g.add(new THREE.Mesh(ribbon(road.pts, 9, 0.35), new THREE.MeshBasicMaterial({ color: 0xef2b2d, transparent: true, opacity: 0.75, side: THREE.DoubleSide, depthWrite: false })));
    } else {
      ({ x, z } = this.local(cut.lat, cut.lon));
    }
    const bar = new THREE.Mesh(new THREE.BoxGeometry(14, 1.6, 1.2), this.mat(0xef2b2d));
    bar.position.set(x, 2.6, z);
    const legs = new THREE.Mesh(new THREE.BoxGeometry(12, 2.4, 0.6), this.mat(0xffffff));
    legs.position.set(x, 1.2, z);
    g.add(bar, legs);
    g.userData = { kind: "coupure", data: cut };
    this.groups.coupures.add(g);
    this.scaled.push(bar);
    return g;
  }

  /** Anneau de sélection animé autour d'un objet. */
  select(obj) {
    this.clear("selection");
    if (!obj) return;
    const pos = new THREE.Vector3();
    obj.getWorldPosition(pos);
    const ring = new THREE.Mesh(this.ringGeo, new THREE.MeshBasicMaterial({ color: 0xfcd116 }));
    ring.position.set(pos.x, 0.8, pos.z);
    ring.scale.setScalar(1.6);
    ring.userData.kind = "selection";
    this.groups.selection.add(ring);
    this.pulse.push(ring);
    this.scaled.push(ring);
  }

  /** Surbrillance d'une polyligne (route sélectionnée, tournée d'un camion). */
  highlightPath(points, color = 0xfcd116, width = 6) {
    const m = new THREE.Mesh(ribbon(points, width, 0.9), new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, depthWrite: false }));
    m.renderOrder = 5;
    m.userData.kind = "selection";
    this.groups.selection.add(m);
    return m;
  }

  /** Largeur des tournées proportionnelle à l'altitude de la caméra : lisibles de près comme de loin. */
  _routeWidth() {
    const w = Math.max(3, Math.min(22, Math.round(this.s.camera.position.y / 70)));
    if (w === this.routeWidth) return;
    this.routeWidth = w;
    for (const m of this.groups.tournees.children) {
      m.geometry.dispose();
      m.geometry = ribbon(m.userData.path, w);
    }
  }

  update(dt) {
    this._routeWidth();
    const cam = this.s.camera.position;
    for (const o of this.scaled) {
      const d = cam.distanceTo(o.position);
      const k = Math.max(0.35, Math.min(4.5, d / 520));
      if (o.userData.kind === "selection") o.scale.setScalar(1.6 * k);
      else if (o.userData.h) o.scale.set(k, o.userData.h * Math.max(1, k * 0.7), k);
      else o.scale.set(k, k, k);
    }
    this._t = (this._t || 0) + dt;
    for (const r of this.pulse) {
      const k = 1 + 0.18 * Math.sin(this._t * 4);
      if (r.userData.kind !== "selection") r.scale.setScalar(k * Math.max(0.6, Math.min(4, cam.distanceTo(r.position) / 520)));
      r.rotation.y += dt * 0.8;
    }
  }

  /** Objets cliquables (dans l'ordre de priorité). */
  pickables() {
    return [this.groups.signalements, this.groups.simules, this.groups.points, this.groups.alertes, this.groups.coupures];
  }
}

export { disposeObject };
