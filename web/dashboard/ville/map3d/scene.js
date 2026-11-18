// Moteur de rendu : scène, lumière de fin d'après-midi, brume sèche (harmattan), ombres, boucle d'animation.
import * as THREE from "three";

export const PALETTE = {
  ciel: 0xe9d9bf,       // brume chaude
  sol: 0xd6c09a,        // latérite claire, sable
  brume: 0xe4d2b4,
};

export function detectWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(window.WebGL2RenderingContext && canvas.getContext("webgl2"))
      || Boolean(window.WebGLRenderingContext && canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export class Scene3D {
  constructor(container, { shadows = true } = {}) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = shadows;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(PALETTE.ciel);
    this.sky = skyDome();
    this.scene.add(this.sky);
    this.scene.fog = new THREE.Fog(PALETTE.brume, 900, 4200);

    this.camera = new THREE.PerspectiveCamera(45, 1, 1, 9000);
    this.camera.position.set(-600, 520, 700);

    this.hemi = new THREE.HemisphereLight(0xfff3dc, 0x8a6a48, 1.25);
    this.scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight(0xffe2b8, 2.1);
    this.sun.position.set(-500, 700, 300);
    this.sun.castShadow = shadows;
    this.sun.shadow.mapSize.set(2048, 2048);
    const s = this.sun.shadow.camera;
    s.left = -700; s.right = 700; s.top = 700; s.bottom = -700; s.near = 10; s.far = 2500;
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.9;
    this.scene.add(this.sun, this.sun.target);

    this.clock = new THREE.Clock();
    this.updaters = new Set();
    this.frameMs = 16;
    this._resize = () => this.resize();
    window.addEventListener("resize", this._resize);
    this.resize();
  }

  resize() {
    const w = this.container.clientWidth || 1;
    const h = this.container.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  /** Les ombres suivent le point regardé (carte d'ombre nette autour de la zone utile). */
  followShadow(target, distance = 600) {
    // Cadre d'ombre proportionnel à la distance de vue : ombres nettes de près, sans stries.
    const half = Math.max(120, Math.min(900, distance * 0.9));
    const c = this.sun.shadow.camera;
    if (Math.abs(c.right - half) > 20) {
      c.left = -half; c.right = half; c.top = half; c.bottom = -half;
      c.updateProjectionMatrix();
    }
    this.sun.position.set(target.x - 500, 700, target.z + 300);
    this.sun.target.position.set(target.x, 0, target.z);
    this.sky.position.set(target.x, 0, target.z);
  }

  onFrame(fn) {
    this.updaters.add(fn);
    return () => this.updaters.delete(fn);
  }

  start() {
    const loop = () => {
      this._raf = requestAnimationFrame(loop);
      const dt = Math.min(this.clock.getDelta(), 0.1);
      const t0 = performance.now();
      for (const fn of this.updaters) fn(dt);
      this.renderer.render(this.scene, this.camera);
      this.frameMs = this.frameMs * 0.9 + (performance.now() - t0) * 0.1;
    };
    loop();
  }

  dispose() {
    cancelAnimationFrame(this._raf);
    window.removeEventListener("resize", this._resize);
    this.scene.traverse((o) => {
      o.geometry?.dispose?.();
      if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose());
      else o.material?.dispose?.();
    });
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

/** Dôme de ciel : bleu pâle en haut, horizon chaud et brumeux (harmattan). Ne reçoit pas la brume. */
function skyDome() {
  const geo = new THREE.SphereGeometry(8000, 32, 16);
  const top = new THREE.Color(0x9fbad0);
  const horizon = new THREE.Color(0xeedcc0);
  const cols = [];
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const t = Math.max(0, pos.getY(i) / 8000);
    const c = horizon.clone().lerp(top, Math.pow(t, 0.55));
    cols.push(c.r, c.g, c.b);
  }
  geo.setAttribute("color", new THREE.Float32BufferAttribute(cols, 3));
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide, fog: false, depthWrite: false }));
  mesh.renderOrder = -1;
  return mesh;
}

/** Libère la géométrie et les matériaux d'un objet retiré de la scène. */
export function disposeObject(obj) {
  obj.traverse((o) => {
    o.geometry?.dispose?.();
    if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose());
    else o.material?.dispose?.();
  });
  obj.parent?.remove(obj);
}
