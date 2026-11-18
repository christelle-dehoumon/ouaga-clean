// Vue 2D de SECOURS (Leaflet) quand WebGL est indisponible ou que la 3D échoue : mêmes données et mêmes actions,
// sans relief ni animation. Fond de carte : tuiles OpenStreetMap en ligne (attribution obligatoire affichée).
import { Projection, decodeDeltas } from "./map3d/geo.js";
import { STATUTS, VEHICLE_COLORS } from "./map3d/layers.js";

const hex = (n) => `#${n.toString(16).padStart(6, "0")}`;

function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  return new Promise((resolve, reject) => {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "/dashboard/vendor/leaflet/leaflet.css";
    document.head.append(css);
    const s = document.createElement("script");
    s.src = "/dashboard/vendor/leaflet/leaflet.js";
    s.onload = () => resolve(window.L);
    s.onerror = () => reject(new Error("Leaflet introuvable."));
    document.head.append(s);
  });
}

export async function createView2D(container, cityData) {
  const L = await loadLeaflet();
  const proj = new Projection(...cityData.meta.origin);
  const map = L.map(container, { preferCanvas: true, zoomControl: true }).setView(cityData.meta.origin, 14);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
  }).addTo(map);
  const roads = cityData.roads.map((r) => ({ id: r.e, kind: r.k, name: r.n, paved: Boolean(r.p), truck: Boolean(r.t), pts: decodeDeltas(r.c) }));
  const territories = cityData.territories.map((t) => {
    const rings = t.r.map((r) => decodeDeltas(r));
    const poly = L.polygon(rings.map((ring) => ring.map(([x, z]) => proj.toLatLon(x, z))), {
      color: t.secteur ? "#009e49" : "#b8960c", weight: 2, dashArray: "6 6", fillOpacity: 0, interactive: false }).addTo(map);
    return { ...t, rings, poly };
  });
  const groups = { signalements: L.layerGroup().addTo(map), simules: L.layerGroup().addTo(map), plan: L.layerGroup().addTo(map),
    selection: L.layerGroup().addTo(map) };
  const handlers = { select: () => {}, ground: () => {}, road: () => {}, hover: () => {} };
  const colors = new Map();
  let mode = "selection";

  function marker(lat, lon, color, info, radius = 7) {
    const m = L.circleMarker([lat, lon], { radius, color: "#1d1f1e", weight: 1, fillColor: color, fillOpacity: 1 });
    m.on("click", (e) => { L.DomEvent.stopPropagation(e); if (mode === "selection") handlers.select(info, m); });
    return m;
  }

  function nearestRoad(lat, lon, maxM = 35) {
    const p = proj.toLocal(lat, lon);
    let best = null;
    let bd = maxM;
    for (const r of roads) {
      for (let i = 0; i < r.pts.length - 1; i++) {
        const [x1, z1] = r.pts[i];
        const [x2, z2] = r.pts[i + 1];
        const dx = x2 - x1, dz = z2 - z1;
        const t = Math.max(0, Math.min(1, ((p.x - x1) * dx + (p.z - z1) * dz) / (dx * dx + dz * dz || 1)));
        const d = Math.hypot(p.x - (x1 + t * dx), p.z - (z1 + t * dz));
        if (d < bd) { bd = d; best = r; }
      }
    }
    return best;
  }

  map.on("click", (e) => {
    const { lat, lng } = e.latlng;
    if (mode === "ajout-depotoir") return handlers.ground({ lat, lon: lng });
    if (mode === "coupure-route") return handlers.road(nearestRoad(lat, lng));
    const t = view.territoryAt(lat, lng);
    handlers.select(t ? { kind: "quartier", territory: t } : null, null);
  });

  const view = {
    kind: "2d",
    proj,
    city: { territories, roads },
    roadById: new Map(roads.flatMap((r) => { const [u, v] = r.id.split("-"); return [[r.id, r], [`${v}-${u}`, r]]; })),
    on(name, fn) { handlers[name] = fn; },
    setReports(list) {
      groups.signalements.clearLayers();
      for (const r of list) {
        const st = STATUTS[`${r.type}:${r.statut}`] || STATUTS["depotoir:a_verifier"];
        marker(r.lat, r.lon, hex(st.couleur), { kind: "signalement", data: r, label: st.libelle }).addTo(groups.signalements);
      }
    },
    setSimDumps(list) {
      groups.simules.clearLayers();
      for (const d of list) marker(d.lat, d.lon, hex(STATUTS.simule.couleur), { kind: "simule", data: d, label: STATUTS.simule.libelle }).addTo(groups.simules);
    },
    setPlan(plan) {
      groups.plan.clearLayers();
      if (!plan) return;
      const trucks = [...new Set((plan.routes || []).map((r) => String(r.vehicle_id || r.vehicle).split("_trip")[0]))].sort();
      trucks.forEach((t, i) => colors.set(t, VEHICLE_COLORS[i % VEHICLE_COLORS.length]));
      for (const r of plan.routes || []) {
        const truck = String(r.vehicle_id).split("_trip")[0];
        L.polyline(r.path || [], { color: hex(colors.get(truck) ?? 0xef2b2d), weight: 4, opacity: 0.85 }).addTo(groups.plan);
      }
      const unserved = new Map((plan.unserved || []).map((u) => [u.point_id, u]));
      const postponed = new Map((plan.postponed || []).map((p) => [p.id, p]));
      for (const p of plan.consolidation_points || []) {
        const status = unserved.has(p.id) ? "non_desservi" : postponed.has(p.id) ? "reporte" : "desservi";
        const color = status === "non_desservi" ? "#ef2b2d" : status === "reporte" ? "#e67e22" : "#009e49";
        marker(p.lat, p.lon, color, { kind: "point", data: p, status, raison: unserved.get(p.id) || postponed.get(p.id) || null }, 6).addTo(groups.plan);
      }
      const routes = new Map((plan.routes || []).map((r) => [r.vehicle_id, r]));
      for (const v of plan.vehicles || []) {
        const first = routes.get((v.trips || [])[0]);
        const at = first?.path?.[Math.floor(first.path.length / 2)] || first?.path?.[0];
        if (!at) continue;
        const legs = (v.trips || []).map((trip) => ({ trip, stops: routes.get(trip)?.stops || [], km: routes.get(trip)?.distance_km, load: routes.get(trip)?.load_kg }));
        marker(at[0], at[1], v.status === "en panne" ? "#1d1f1e" : hex(colors.get(v.id) ?? 0x9a9a92),
          { kind: "vehicule", id: v.id, status: v.status, legs }, 9).addTo(groups.plan);
      }
      for (const c of plan.cut_roads || []) {
        const road = view.roadById.get(c.edge_id);
        if (road) L.polyline(road.pts.map(([x, z]) => proj.toLatLon(x, z)), { color: "#ef2b2d", weight: 9, opacity: 0.8 }).addTo(groups.plan);
      }
    },
    vehicleColor(id) { return hex(colors.get(id) ?? 0x9a9a92); },
    setRain(on) { container.classList.toggle("pluie-2d", on); },
    setPlaying() {},
    setInteraction(m) { mode = m; container.style.cursor = m === "selection" ? "" : "crosshair"; },
    highlightTerritory(id) {
      for (const t of territories) t.poly.setStyle({ fillOpacity: t.id === id ? 0.2 : 0, fillColor: t.secteur ? "#009e49" : "#fcd116" });
    },
    select(info) {
      groups.selection.clearLayers();
      if (info?.kind === "route" && info.road) {
        L.polyline(info.road.pts.map(([x, z]) => proj.toLatLon(x, z)), { color: "#fcd116", weight: 10 }).addTo(groups.selection);
      }
    },
    focusLatLon(lat, lon) { map.setView([lat, lon], 17); return Promise.resolve(); },
    focusTerritory(id) { const t = territories.find((x) => x.id === id); if (t) map.fitBounds(t.poly.getBounds()); return Promise.resolve(); },
    overview() { map.setView(cityData.meta.origin, 13); return Promise.resolve(); },
    immersive() { return Promise.resolve(); },
    street() {},
    exitStreet() {},
    reset() { map.setView(cityData.meta.origin, 14); return Promise.resolve(); },
    territoryAt(lat, lon) {
      const p = proj.toLocal(lat, lon);
      const inside = (t) => t.rings.some((ring) => {
        let ins = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          const [xi, zi] = ring[i]; const [xj, zj] = ring[j];
          if ((zi > p.z) !== (zj > p.z) && p.x < ((xj - xi) * (p.z - zi)) / (zj - zi) + xi) ins = !ins;
        }
        return ins;
      });
      return territories.find((t) => !t.secteur && inside(t)) || territories.find(inside) || null;
    },
    frameMs() { return 0; },
    onCamera() {},
    statutsLegend: STATUTS,
  };
  return view;
}
