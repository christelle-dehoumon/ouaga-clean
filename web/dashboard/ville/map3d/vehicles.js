// Camions du plan : un objet par véhicule réel (plan.vehicles), qui enchaîne ses trajets (truckN_trip1, trip2…)
// en suivant la géométrie des tournées calculées (plan.routes[].path). Camion en panne : immobile, feux de détresse.
import * as THREE from "three";

const SPEED = 55; // m/s dans la scène : animation accélérée (indiquée à l'écran)

function truckModel(color) {
  const g = new THREE.Group();
  const dark = new THREE.MeshLambertMaterial({ color: 0x2b2b2b });
  const cab = new THREE.MeshLambertMaterial({ color: 0xf4f1ea });
  const body = new THREE.MeshLambertMaterial({ color });
  const chassis = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.8, 7.4), dark);
  chassis.position.y = 0.9;
  const c = new THREE.Mesh(new THREE.BoxGeometry(2.4, 2.1, 1.9), cab);
  c.position.set(0, 2.25, 2.6);
  const b = new THREE.Mesh(new THREE.BoxGeometry(2.6, 2.4, 4.9), body);
  b.position.set(0, 2.5, -0.9);
  const wheelGeo = new THREE.CylinderGeometry(0.55, 0.55, 0.4, 10).rotateZ(Math.PI / 2);
  for (const [x, z] of [[-1.2, 2.4], [1.2, 2.4], [-1.2, -2.4], [1.2, -2.4]]) {
    const w = new THREE.Mesh(wheelGeo, dark);
    w.position.set(x, 0.55, z);
    g.add(w);
  }
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.5, 8, 6), new THREE.MeshBasicMaterial({ color: 0xfcd116 }));
  beacon.position.set(0, 3.6, 2.6);
  beacon.visible = false;
  g.add(chassis, c, b, beacon);
  g.userData.beacon = beacon;
  for (const m of [chassis, c, b]) m.castShadow = true;
  return g;
}

export class Fleet {
  constructor(scene3d, proj) {
    this.s = scene3d;
    this.proj = proj;
    this.group = new THREE.Group();
    this.group.name = "vehicules";
    scene3d.scene.add(this.group);
    this.trucks = new Map();
    this.playing = true;
    this.speedFactor = 1;
    scene3d.onFrame((dt) => this.update(dt));
  }

  /** Remplace la flotte par celle du plan ; un camion déjà présent garde sa position (panne : il s'arrête là). */
  setPlan(plan, colors) {
    const previous = new Map([...this.trucks].map(([id, t]) => [id, t.object.position.clone()]));
    for (const t of this.trucks.values()) this.group.remove(t.object);
    this.trucks.clear();
    if (!plan) return;
    const routes = new Map((plan.routes || []).map((r) => [r.vehicle_id || r.vehicle, r]));
    const depotPath = (plan.routes || []).find((r) => (r.path || []).length)?.path;
    const depot = depotPath ? this.proj.toLocal(depotPath[0][0], depotPath[0][1]) : { x: 0, z: 0 };
    (plan.vehicles || []).forEach((v, i) => {
      // Couleur de sa tournée ; gris si le camion n'a aucun trajet dans ce plan (au dépôt).
      const color = (v.trips || []).length ? (colors?.get(v.id) ?? 0x1f6fb2) : 0x9a9a92;
      const object = truckModel(color);
      const pts = [];
      const legs = [];
      for (const trip of v.trips || []) {
        const r = routes.get(trip);
        if (!r || !(r.path || []).length) continue;
        const start = pts.length;
        for (const [lat, lon] of r.path) {
          const p = this.proj.toLocal(lat, lon);
          pts.push([p.x, p.z]);
        }
        legs.push({ trip, start, end: pts.length - 1, stops: r.stops || [], km: r.distance_km, load: r.load_kg });
      }
      const cum = [0];
      for (let k = 1; k < pts.length; k++) cum.push(cum[k - 1] + Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]));
      const broken = v.status === "en panne";
      const prev = previous.get(v.id);
      const home = prev && broken ? prev : new THREE.Vector3(depot.x + (i % 4) * 4, 0, depot.z + Math.floor(i / 4) * 9);
      object.position.copy(home);
      const beacon = object.userData.beacon;
      object.userData = { kind: "vehicule", id: v.id, status: v.status, legs, length: cum.at(-1) || 0, color, beacon };
      object.userData.beacon.visible = broken;
      this.group.add(object);
      this.trucks.set(v.id, { object, pts, cum, d: (i * 137) % Math.max(cum.at(-1) || 1, 1), broken, idle: pts.length < 2 });
    });
  }

  setPlaying(on) { this.playing = on; }

  update(dt) {
    const cam = this.s.camera.position;
    this._t = (this._t || 0) + dt;
    for (const t of this.trucks.values()) {
      const o = t.object;
      const k = Math.max(1, Math.min(6, cam.distanceTo(o.position) / 260));
      o.scale.setScalar(k);
      if (t.broken) {
        o.userData.beacon.visible = Math.sin(this._t * 8) > 0;
        continue;
      }
      if (t.idle || !this.playing) continue;
      t.d = (t.d + SPEED * this.speedFactor * dt) % t.cum.at(-1);
      let lo = 0;
      let hi = t.cum.length - 1;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (t.cum[mid] <= t.d) lo = mid; else hi = mid; }
      const seg = t.cum[hi] - t.cum[lo] || 1;
      const f = (t.d - t.cum[lo]) / seg;
      const [x1, z1] = t.pts[lo];
      const [x2, z2] = t.pts[hi];
      o.position.set(x1 + (x2 - x1) * f, 0, z1 + (z2 - z1) * f);
      if (Math.hypot(x2 - x1, z2 - z1) > 0.5) o.rotation.y = Math.atan2(x2 - x1, z2 - z1);
      o.userData.leg = o.userData.legs.find((l) => lo >= l.start && lo < l.end)?.trip || null;
    }
  }

  get(id) { return this.trucks.get(id)?.object || null; }

  pickables() { return [this.group]; }
}

export const ANIMATION_NOTE = "Animation accélérée : la vitesse à l'écran n'est pas la vitesse réelle des camions.";
