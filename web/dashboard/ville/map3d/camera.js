// Navigation : orbite / déplacement / zoom amortis, vues prédéfinies, vols animés, vue « rue » à hauteur d'homme.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const EASE = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export class CameraRig {
  constructor(scene3d, bounds) {
    this.s = scene3d;
    this.camera = scene3d.camera;
    this.bounds = bounds; // {minX, maxX, minZ, maxZ}
    this.controls = new OrbitControls(this.camera, scene3d.renderer.domElement);
    Object.assign(this.controls, {
      enableDamping: true, dampingFactor: 0.08, screenSpacePanning: false, minDistance: 18, maxDistance: 5200,
      maxPolarAngle: Math.PI * 0.47, zoomSpeed: 0.9, rotateSpeed: 0.6, panSpeed: 0.9,
    });
    this.controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
    this.controls.target.set(0, 0, 0);
    this.flight = null;
    this.street = null;
    this.keys = new Set();
    this._onKey = (e) => this._key(e);
    window.addEventListener("keydown", this._onKey);
    window.addEventListener("keyup", this._onKey);
    scene3d.onFrame((dt) => this.update(dt));
  }

  /** Vol animé vers une cible : distance, angle polaire (0 = vue du dessus) et azimut. */
  flyTo({ x, z, distance = 600, polar = 0.95, azimuth = null, duration = 1.4 }) {
    this.exitStreet();
    const from = { pos: this.camera.position.clone(), target: this.controls.target.clone() };
    const az = azimuth ?? this.controls.getAzimuthalAngle();
    const target = new THREE.Vector3(x, 0, z);
    const pos = new THREE.Vector3(
      x + distance * Math.sin(polar) * Math.sin(az),
      Math.max(distance * Math.cos(polar), 12),
      z + distance * Math.sin(polar) * Math.cos(az),
    );
    this.flight = { from, to: { pos, target }, t: 0, duration };
    return new Promise((resolve) => { this.flight.done = resolve; });
  }

  overview() {
    const b = this.bounds;
    const span = Math.max(b.maxX - b.minX, b.maxZ - b.minZ);
    return this.flyTo({ x: (b.minX + b.maxX) / 2, z: (b.minZ + b.maxZ) / 2, distance: span * 0.85, polar: 0.02, azimuth: 0 });
  }

  immersive(x = this.controls.target.x, z = this.controls.target.z) {
    return this.flyTo({ x, z, distance: 420, polar: 1.18 });
  }

  focus(x, z, distance = 160) {
    return this.flyTo({ x, z, distance, polar: 1.0 });
  }

  /** Vue « rue » : caméra à 1,7 m, flèches ou ZQSD/WASD pour avancer, glisser pour regarder. */
  enterStreet(x = this.controls.target.x, z = this.controls.target.z) {
    this.flight = null;
    this.controls.enabled = false;
    const yaw = Math.atan2(this.camera.position.x - x, this.camera.position.z - z) + Math.PI;
    this.street = { yaw, pitch: -0.05, x, z };
    const el = this.s.renderer.domElement;
    let drag = null;
    this._down = (e) => { drag = { x: e.clientX, y: e.clientY }; };
    this._move = (e) => {
      if (!drag || !this.street) return;
      this.street.yaw -= (e.clientX - drag.x) * 0.004;
      this.street.pitch = Math.max(-1.2, Math.min(0.9, this.street.pitch - (e.clientY - drag.y) * 0.004));
      drag = { x: e.clientX, y: e.clientY };
    };
    this._up = () => { drag = null; };
    el.addEventListener("pointerdown", this._down);
    window.addEventListener("pointermove", this._move);
    window.addEventListener("pointerup", this._up);
    this.onModeChange?.("rue");
  }

  exitStreet() {
    if (!this.street) return;
    const el = this.s.renderer.domElement;
    el.removeEventListener("pointerdown", this._down);
    window.removeEventListener("pointermove", this._move);
    window.removeEventListener("pointerup", this._up);
    const { x, z } = this.street;
    this.street = null;
    this.controls.enabled = true;
    this.controls.target.set(x, 0, z);
    this.camera.position.set(x + 120, 140, z + 120);
    this.onModeChange?.("orbite");
  }

  _key(e) {
    const tag = e.target?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (e.type === "keydown") this.keys.add(e.key.toLowerCase());
    else this.keys.delete(e.key.toLowerCase());
  }

  update(dt) {
    if (this.flight) {
      const f = this.flight;
      f.t = Math.min(1, f.t + dt / f.duration);
      const k = EASE(f.t);
      this.camera.position.lerpVectors(f.from.pos, f.to.pos, k);
      this.controls.target.lerpVectors(f.from.target, f.to.target, k);
      if (f.t >= 1) {
        this.flight = null;
        f.done?.();
      }
    }
    if (this.street) {
      const st = this.street;
      const fast = this.keys.has("shift") ? 3 : 1;
      const v = 9 * fast * dt;
      const fwd = (this.keys.has("arrowup") || this.keys.has("z") || this.keys.has("w") ? 1 : 0)
        - (this.keys.has("arrowdown") || this.keys.has("s") ? 1 : 0);
      const side = (this.keys.has("arrowright") || this.keys.has("d") ? 1 : 0)
        - (this.keys.has("arrowleft") || this.keys.has("q") || this.keys.has("a") ? 1 : 0);
      // avant = (sin yaw, cos yaw) ; droite = avant × haut = (-cos yaw, sin yaw)
      st.x += (Math.sin(st.yaw) * fwd - Math.cos(st.yaw) * side) * v;
      st.z += (Math.cos(st.yaw) * fwd + Math.sin(st.yaw) * side) * v;
      const b = this.bounds;
      st.x = Math.max(b.minX, Math.min(b.maxX, st.x));
      st.z = Math.max(b.minZ, Math.min(b.maxZ, st.z));
      this.camera.position.set(st.x, 1.7, st.z);
      const dir = new THREE.Vector3(Math.sin(st.yaw) * Math.cos(st.pitch), Math.sin(st.pitch), Math.cos(st.yaw) * Math.cos(st.pitch));
      this.camera.lookAt(this.camera.position.clone().add(dir));
      this.s.followShadow(this.camera.position, 140);
      this.s.scene.fog.near = 60;
      this.s.scene.fog.far = 900;
      return;
    }
    // Garder la cible dans la zone modélisée.
    const b = this.bounds;
    const t = this.controls.target;
    const cx = Math.max(b.minX, Math.min(b.maxX, t.x)) - t.x;
    const cz = Math.max(b.minZ, Math.min(b.maxZ, t.z)) - t.z;
    if (cx || cz) {
      t.x += cx; t.z += cz;
      this.camera.position.x += cx; this.camera.position.z += cz;
    }
    this.controls.update();
    // Brume proportionnelle à la distance : profondeur en vue rasante, lisibilité en vue du dessus.
    const d = this.camera.position.distanceTo(t);
    this.s.followShadow(t, d);
    this.s.scene.fog.near = d * 1.1 + 200;
    this.s.scene.fog.far = d * 3.2 + 1600;
  }
}
