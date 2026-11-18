// Sélection spatiale : lancer de rayon sur véhicules, signalements, points, coupures, quartiers ; sol pour ajouter
// un dépotoir simulé ; routes pour une coupure. Un glissé (rotation de caméra) n'est jamais pris pour un clic.
import * as THREE from "three";

export class Picker {
  constructor(scene3d, { layers, fleet, city }) {
    this.s = scene3d;
    this.layers = layers;
    this.fleet = fleet;
    this.city = city;
    this.mode = "selection"; // selection | ajout-depotoir | coupure-route
    this.ray = new THREE.Raycaster();
    this.ndc = new THREE.Vector2();
    this.handlers = { select: () => {}, ground: () => {}, road: () => {}, hover: () => {} };
    const el = scene3d.renderer.domElement;
    let down = null;
    el.addEventListener("pointerdown", (e) => { down = { x: e.clientX, y: e.clientY, t: performance.now() }; });
    el.addEventListener("pointerup", (e) => {
      if (!down || e.button !== 0) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      down = null;
      if (moved < 6) this.click(e);
    });
    let pending = false;
    el.addEventListener("pointermove", (e) => {
      if (pending || down) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; this.hover(e); });
    });
    el.addEventListener("pointerleave", () => this.handlers.hover(null));
  }

  on(name, fn) { this.handlers[name] = fn; }

  setMode(mode) {
    this.mode = mode;
    this.s.renderer.domElement.style.cursor = mode === "selection" ? "" : "crosshair";
  }

  _ray(e) {
    const r = this.s.renderer.domElement.getBoundingClientRect();
    this.ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.ray.setFromCamera(this.ndc, this.s.camera);
  }

  /** Premier objet métier sous le pointeur (véhicule > signalement > point > coupure > quartier). */
  pickObject() {
    const roots = [...this.fleet.pickables(), ...this.layers.pickables()];
    for (const root of roots) {
      const hits = this.ray.intersectObject(root, true);
      for (const h of hits) {
        let o = h.object;
        while (o && !o.userData?.kind) o = o.parent;
        if (o && o.userData.kind !== "selection") return o;
      }
    }
    return null;
  }

  pickTerritory() {
    const p = this.groundPoint();
    if (!p) return null;
    return this.city.territories.find((t) => !t.secteur && t.contains(p.x, p.z))
      || this.city.territories.find((t) => t.contains(p.x, p.z)) || null;
  }

  groundPoint() {
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const p = new THREE.Vector3();
    return this.ray.ray.intersectPlane(plane, p) ? p : null;
  }

  pickRoad() {
    const hits = this.ray.intersectObjects(this.city.roadMeshes, false);
    if (!hits.length) return null;
    const h = hits[0];
    const idx = h.object.userData.faceToRoad[h.faceIndex];
    return this.city.roads[idx] || null;
  }

  click(e) {
    this._ray(e);
    if (this.mode === "ajout-depotoir") {
      const p = this.groundPoint();
      if (p) this.handlers.ground(p);
      return;
    }
    if (this.mode === "coupure-route") {
      const road = this.pickRoad();
      this.handlers.road(road);
      return;
    }
    const obj = this.pickObject();
    if (obj) return this.handlers.select(obj.userData, obj);
    const terr = this.pickTerritory();
    this.handlers.select(terr ? { kind: "quartier", territory: terr } : null, null);
  }

  hover(e) {
    this._ray(e);
    if (this.mode === "coupure-route") {
      const road = this.pickRoad();
      return this.handlers.hover(road ? { kind: "route", road } : null, e);
    }
    const obj = this.pickObject();
    this.handlers.hover(obj ? obj.userData : null, e);
  }
}
