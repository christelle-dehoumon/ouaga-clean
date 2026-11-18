// Vue 3D (Three.js) derrière l'interface commune des vues : la ville, les données de l'API et la sélection.
import * as THREE from "three";
import { CameraRig } from "./map3d/camera.js";
import { buildCity } from "./map3d/city.js";
import { Weather } from "./map3d/effects.js";
import { Projection } from "./map3d/geo.js";
import { Picker } from "./map3d/interactions.js";
import { Layers, STATUTS } from "./map3d/layers.js";
import { Scene3D } from "./map3d/scene.js";
import { Fleet } from "./map3d/vehicles.js";

export async function createView3D(container, cityData) {
  const s = new Scene3D(container);
  const city = buildCity(s, cityData);
  const proj = new Projection(...cityData.meta.origin);
  const rig = new CameraRig(s, city.bounds);
  const layers = new Layers(s, proj);
  const fleet = new Fleet(s, proj);
  const picker = new Picker(s, { layers, fleet, city });
  const weather = new Weather(s);
  const roadById = new Map();
  for (const r of city.roads) {
    roadById.set(r.id, r);
    const [u, v] = r.id.split("-");
    roadById.set(`${v}-${u}`, r);
  }
  const handlers = { select: () => {}, ground: () => {}, road: () => {}, hover: () => {} };

  // Étiquettes des quartiers (HTML, repositionnées à chaque image).
  const labelHost = document.createElement("div");
  labelHost.className = "etiquettes";
  container.append(labelHost);
  const labels = city.territories.map((t) => {
    const d = document.createElement("div");
    d.className = `etiquette${t.secteur ? " etiquette-secteur" : ""}`;
    d.textContent = t.secteur ? `${t.nom}` : `${t.nom}${t.approximate ? " (emprise approx.)" : ""}`;
    labelHost.append(d);
    return { t, d };
  });
  const v = new THREE.Vector3();
  s.onFrame(() => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    for (const { t, d } of labels) {
      v.set(t.center.x, 30, t.center.z).project(s.camera);
      const visible = v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1 && !rig.street;
      d.style.display = visible ? "" : "none";
      if (visible) d.style.transform = `translate(${((v.x + 1) / 2) * w}px, ${((1 - v.y) / 2) * h}px) translate(-50%, -50%)`;
    }
  });

  let selectedTerritory = null;
  const view = {
    kind: "3d",
    proj,
    city,
    rig,
    scene: s,
    fleet,
    layers,
    roadById,
    on(name, fn) { handlers[name] = fn; },
    setReports(list) { layers.setReports(list); },
    setSimDumps(list) { layers.setSimDumps(list); },
    setPlan(plan) {
      layers.setPlan(plan ? { ...plan, cut_roads: [] } : null);
      fleet.setPlan(plan, layers.vehicleColor);
      for (const c of plan?.cut_roads || []) layers.addCut(c, roadById.get(c.edge_id) || null);
    },
    vehicleColor(id) { return `#${(layers.vehicleColor.get(id) ?? 0x9a9a92).toString(16).padStart(6, "0")}`; },
    setRain(on) { weather.set(on); },
    setPlaying(on) { fleet.setPlaying(on); },
    setInteraction(mode) { picker.setMode(mode); },
    highlightTerritory(id) {
      for (const t of city.territories) t.fillMat.opacity = t.id === id ? 0.22 : 0;
      selectedTerritory = id;
    },
    select(info, object) {
      layers.select(null);
      if (!info) return;
      if (object) layers.select(object);
      if (info.kind === "vehicule") {
        for (const leg of info.legs || []) {
          const r = layers.groups.tournees.children.find((m) => (m.userData.data?.vehicle_id || m.userData.data?.vehicle) === leg.trip);
          if (r) layers.highlightPath(r.userData.path, 0xfcd116, 6);
        }
      }
      if (info.kind === "route" && info.road) layers.highlightPath(info.road.pts, 0xfcd116, 10);
    },
    focusLatLon(lat, lon, distance = 220) {
      const p = proj.toLocal(lat, lon);
      return rig.focus(p.x, p.z, distance);
    },
    focusTerritory(id) {
      const t = city.territories.find((x) => x.id === id);
      if (!t) return null;
      let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
      for (const [x, z] of t.rings.flat()) { minX = Math.min(minX, x); maxX = Math.max(maxX, x); minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z); }
      return rig.flyTo({ x: (minX + maxX) / 2, z: (minZ + maxZ) / 2, distance: Math.max(maxX - minX, maxZ - minZ) * 1.25, polar: 0.85 });
    },
    overview() { return rig.overview(); },
    immersive() { return rig.immersive(); },
    street() { rig.enterStreet(); },
    exitStreet() { rig.exitStreet(); },
    reset() { return rig.flyTo({ x: 0, z: 0, distance: 1100, polar: 1.02, azimuth: 0.6 }); },
    territoryAt(lat, lon) {
      const p = proj.toLocal(lat, lon);
      return city.territories.find((t) => !t.secteur && t.contains(p.x, p.z)) || city.territories.find((t) => t.contains(p.x, p.z)) || null;
    },
    frameMs() { return s.frameMs; },
    statutsLegend: STATUTS,
    get selectedTerritory() { return selectedTerritory; },
  };
  picker.on("select", (info, object) => handlers.select(info, object));
  picker.on("ground", (p) => {
    const [lat, lon] = proj.toLatLon(p.x, p.z);
    handlers.ground({ lat, lon });
  });
  picker.on("road", (road) => handlers.road(road));
  picker.on("hover", (info, e) => handlers.hover(info, e));
  rig.onModeChange = (m) => handlers.camera?.(m);
  view.onCamera = (fn) => { handlers.camera = fn; };
  s.start();
  await rig.flyTo({ x: 0, z: 0, distance: 1100, polar: 1.02, azimuth: 0.6, duration: 0.01 });
  return view;
}
