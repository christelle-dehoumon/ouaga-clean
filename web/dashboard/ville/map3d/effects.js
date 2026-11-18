// Effets de scénario : pluie (traits qui tombent autour du point regardé, lumière plus grise, routes plus sombres).
// La pluie reste discrète pour ne pas gêner la lecture de la carte.
import * as THREE from "three";

export class Weather {
  constructor(scene3d) {
    this.s = scene3d;
    this.raining = false;
    const n = 5000;
    const pos = new Float32Array(n * 6);
    this.seed = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      this.seed[i * 3] = Math.random() * 2 - 1;
      this.seed[i * 3 + 1] = Math.random();
      this.seed[i * 3 + 2] = Math.random() * 2 - 1;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.drops = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x9fb2c2, transparent: true, opacity: 0.45 }));
    this.drops.frustumCulled = false;
    this.drops.visible = false;
    scene3d.scene.add(this.drops);
    this.base = { sun: scene3d.sun.intensity, hemi: scene3d.hemi.intensity, fog: scene3d.scene.fog.color.clone() };
    scene3d.onFrame((dt) => this.update(dt));
  }

  set(raining) {
    this.raining = raining;
    this.drops.visible = raining;
    this.s.sun.intensity = raining ? this.base.sun * 0.35 : this.base.sun;
    this.s.hemi.intensity = raining ? this.base.hemi * 0.8 : this.base.hemi;
    this.s.scene.fog.color.copy(raining ? new THREE.Color(0xb7bcbd) : this.base.fog);
    this.s.sky.material.color = raining ? new THREE.Color(0x9aa2a6) : new THREE.Color(0xffffff);
  }

  update(dt) {
    if (!this.raining) return;
    this._t = (this._t || 0) + dt;
    const cam = this.s.camera.position;
    const spread = Math.max(120, Math.min(900, cam.y * 1.6));
    const height = Math.max(60, Math.min(500, cam.y * 1.2));
    const arr = this.drops.geometry.attributes.position.array;
    const n = this.seed.length / 3;
    for (let i = 0; i < n; i++) {
      const x = cam.x + this.seed[i * 3] * spread;
      const z = cam.z + this.seed[i * 3 + 2] * spread;
      const y = (((this.seed[i * 3 + 1] - this._t * 0.9) % 1) + 1) % 1 * height;
      arr.set([x, y, z, x + 0.6, y + Math.max(2.5, height * 0.02), z], i * 6);
    }
    this.drops.geometry.attributes.position.needsUpdate = true;
  }
}
