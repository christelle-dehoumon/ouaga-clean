// Camions du plan dans la carte MapLibre : couche personnalisée Three.js, géoréférencée sur l'origine de la projection
// locale (x est, z sud, en mètres), qui réutilise la flotte de la ville 3D (map3d/vehicles.js) : mêmes trajets le long
// des tournées calculées, même panne (immobile, feux), même animation ACCÉLÉRÉE et SIMULÉE (jamais présentée comme GPS).
import * as THREE from "three";
import { Fleet } from "../map3d/vehicles.js";

export function coucheCamions(maplibregl, proj) {
  const origine = maplibregl.MercatorCoordinate.fromLngLat([proj.lon0, proj.lat0], 0);
  const echelle = origine.meterInMercatorCoordinateUnits();
  const scene = new THREE.Scene();
  const camera = new THREE.Camera();
  scene.add(new THREE.HemisphereLight(0xfff3dc, 0x6b5a48, 2.2));
  const soleil = new THREE.DirectionalLight(0xffffff, 1.6);
  soleil.position.set(-80, 140, 60);
  scene.add(soleil);
  const abonnes = new Set();
  // Adaptateur minimal de Scene3D pour réutiliser Fleet.
  const hote = { scene, camera: { position: new THREE.Vector3(0, 1e9, 0) }, onFrame: (fn) => abonnes.add(fn) };
  const flotte = new Fleet(hote, proj);
  let renderer = null;
  let map = null;
  let precedent = performance.now();
  let clignote = 0;
  const rotX = new THREE.Matrix4().makeRotationAxis(new THREE.Vector3(1, 0, 0), Math.PI / 2);
  const base = new THREE.Matrix4().makeTranslation(origine.x, origine.y, origine.z)
    .scale(new THREE.Vector3(echelle, -echelle, echelle)).multiply(rotX);

  const couche = {
    id: "camions-3d",
    type: "custom",
    renderingMode: "3d",
    onAdd(m, gl) {
      map = m;
      renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl, antialias: true });
      renderer.autoClear = false;
    },
    render(gl, args) {
      const now = performance.now();
      const dt = Math.min(0.1, (now - precedent) / 1000);
      precedent = now;
      for (const fn of abonnes) fn(dt);
      // Taille lisible quel que soit le zoom : réelle (7,4 m) de près, agrandie au loin.
      const k = Math.max(1, Math.min(14, 2 ** (17.2 - map.getZoom())));
      for (const t of flotte.trucks.values()) t.object.scale.setScalar(k);
      const mat = args?.defaultProjectionData?.mainMatrix || args?.modelViewProjectionMatrix || args;
      camera.projectionMatrix = new THREE.Matrix4().fromArray(mat).multiply(base);
      renderer.resetState();
      renderer.render(scene, camera);
      // Repeindre seulement si quelque chose bouge : camions en route à chaque image ; feux de détresse d'un camion
      // en panne à faible cadence (4 Hz) ; rien quand l'animation est en pause ou que tous les camions sont arrêtés.
      if (!flotte.playing || !flotte.trucks.size) return;
      let roule = false;
      let panne = false;
      for (const t of flotte.trucks.values()) { if (t.broken) panne = true; else if (!t.idle) { roule = true; break; } }
      if (roule) map.triggerRepaint();
      else if (panne && !clignote) clignote = setTimeout(() => { clignote = 0; map?.triggerRepaint(); }, 250);
    },
    onRemove() { clearTimeout(clignote); renderer?.dispose(); },
  };

  /** Camion sous un point écran (lancer de rayon dans la scène des camions) ; avec proche, repli sur le camion le
   *  plus proche à moins de 18 px. */
  function camionEn(point, proche = true) {
    if (!map || !flotte.trucks.size) return null;
    const w = map.getCanvas().clientWidth;
    const h = map.getCanvas().clientHeight;
    const ndc = new THREE.Vector2((point.x / w) * 2 - 1, 1 - (point.y / h) * 2);
    const inv = camera.projectionMatrix.clone().invert();
    const a = new THREE.Vector3(ndc.x, ndc.y, -1).applyMatrix4(inv);
    const b = new THREE.Vector3(ndc.x, ndc.y, 1).applyMatrix4(inv);
    const ray = new THREE.Raycaster(a, b.sub(a).normalize());
    const hits = ray.intersectObjects([flotte.group], true);
    let o = hits[0]?.object;
    while (o && !o.userData?.kind) o = o.parent;
    if (o || !proche) return o || null;
    // Repli : camion le plus proche à moins de 18 px (petits objets au loin).
    let best = null;
    let bd = 18;
    for (const t of flotte.trucks.values()) {
      const [lat, lon] = proj.toLatLon(t.object.position.x, t.object.position.z);
      const p = map.project([lon, lat]);
      const d = Math.hypot(p.x - point.x, p.y - point.y);
      if (d < bd) { bd = d; best = t.object; }
    }
    return best;
  }

  return { couche, flotte, camionEn };
}
