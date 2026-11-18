// Vue « carte » : Ouagadougou entière depuis OpenStreetMap (tuiles vectorielles locales), bâtiments extrudés en 3D,
// rendue par MapLibre GL JS ; même interface que les vues 3D (Three.js) et 2D (Leaflet), donc même logique métier.
import * as maplibregl from "/dashboard/vendor/maplibre/maplibre-gl.mjs";
import { decodeDeltas, pointInRing, Projection } from "../map3d/geo.js";
import { STATUTS } from "../map3d/layers.js";
import { coucheCamions } from "./camions.js";
import { CARTE, sourceHauteur } from "./config.js";
import { Operationnel } from "./operationnel.js";
import { Materiaux, MOTIF_SELECTION } from "./materiaux.js";
import { AMBIANCES, construireStyle } from "./style.js";

let protocoleAjoute = false;

function chargerScript(src, globalName) {
  if (window[globalName]) return Promise.resolve(window[globalName]);
  return new Promise((ok, ko) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => ok(window[globalName]);
    s.onerror = () => ko(new Error(`${src} introuvable`));
    document.head.append(s);
  });
}

function chargerCss(href) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = href;
  document.head.append(l);
}

/** Les tuiles existent-elles ? (fichier fabriqué par scripts/fabriquer_tuiles.sh, absent d'un clone neuf). */
export async function tuilesDisponibles() {
  try {
    const r = await fetch(CARTE.tuiles, { method: "GET", headers: { Range: "bytes=0-126" } });
    return r.ok || r.status === 206;
  } catch {
    return false;
  }
}

export async function createViewCarte(container, cityData) {
  chargerCss("/dashboard/vendor/maplibre/maplibre-gl.css");
  const pmtiles = await chargerScript("/dashboard/vendor/pmtiles/pmtiles.js", "pmtiles");
  if (!protocoleAjoute) {
    maplibregl.addProtocol("pmtiles", new pmtiles.Protocol({ metadata: true }).tile);
    protocoleAjoute = true;
  }
  const proj = new Projection(...cityData.meta.origin);
  const versLatLon = (x, z) => proj.toLatLon(x, z);

  // Données de la ville 3D réutilisées pour le métier : quartiers du plan et réseau de calcul des tournées.
  const roads = (cityData.roads || []).map((r) => ({ id: r.e, kind: r.k, name: r.n, paved: Boolean(r.p), truck: Boolean(r.t), pts: decodeDeltas(r.c) }));
  const roadById = new Map();
  for (const r of roads) {
    roadById.set(r.id, r);
    const [u, v] = r.id.split("-");
    roadById.set(`${v}-${u}`, r);
  }
  const territories = (cityData.territories || []).map((t) => {
    const rings = t.r.map((r) => decodeDeltas(r));
    const flat = rings.flat();
    const center = { x: flat.reduce((s, p) => s + p[0], 0) / flat.length, z: flat.reduce((s, p) => s + p[1], 0) / flat.length };
    return { ...t, rings, center, contains: (x, z) => rings.some((ring) => pointInRing(x, z, ring)) };
  });

  let ambiance = "jour";
  try { ambiance = localStorage.getItem("yilgre.ambiance") || "jour"; } catch { /* ignoré */ }
  if (!AMBIANCES[ambiance]) ambiance = "jour";
  // Qualité : « haute » (motifs de façade, toits, ombres simulées) par défaut sur ordinateur, « leger » sinon.
  let qualite = "haute";
  try {
    qualite = localStorage.getItem("yilgre.qualite") || (matchMedia("(pointer: coarse)").matches || innerWidth < 900 ? "leger" : "haute");
  } catch { /* ignoré */ }
  if (qualite !== "leger") qualite = "haute";
  let motifsPrets = false;
  let vue3D = true;
  const optionsStyle = () => ({ motifs: motifsPrets && qualite === "haute" });
  const map = new maplibregl.Map({
    container,
    style: construireStyle(ambiance),
    center: CARTE.centre,
    zoom: CARTE.vueDepart.zoom,
    pitch: CARTE.vueDepart.pitch,
    bearing: CARTE.vueDepart.bearing,
    minZoom: CARTE.zoomMin,
    maxZoom: CARTE.zoomMax,
    maxPitch: qualite === "leger" ? 60 : 78,
    ...(qualite === "leger" ? { pixelRatio: 1 } : {}),
    maxBounds: [[CARTE.emprise[0][0] - 0.08, CARTE.emprise[0][1] - 0.08], [CARTE.emprise[1][0] + 0.08, CARTE.emprise[1][1] + 0.08]],
    attributionControl: false,   // attribution OSM affichée en permanence par #credit (app.js)
    canvasContextAttributes: { antialias: true },
    fadeDuration: 200,
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true, showCompass: true, showZoom: true }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 110 }), "bottom-right");
  map.addControl(new maplibregl.FullscreenControl({ container: document.body }), "top-right");
  // Les glyphes hors des plages fournies (caractères rares) ne sont pas une panne : on les tait.
  // Requêtes de tuiles annulées quand la caméra bouge (ERR_ABORTED) : comportement normal, pas une panne.
  map.on("error", (e) => {
    const msg = String(e?.error?.message || e?.error?.name || "");
    if (/glyph|\.pbf|abort|Failed to fetch/i.test(msg)) return;
    console.warn("Carte :", msg || e);
  });

  await new Promise((ok, ko) => {
    const t = setTimeout(() => ko(new Error("la carte n'a pas pu se charger (tuiles ou WebGL)")), 45000);
    map.once("load", () => { clearTimeout(t); ok(); });
  });

  const op = new Operationnel(map, { territoires: territories, versLatLon });
  op.setReseau(roads);
  const { couche, flotte, camionEn } = coucheCamions(maplibregl, proj);
  map.addLayer(couche);

  // Sélection d'un bâtiment OSM : surbrillance par identifiant OSM (attribut des tuiles), sur les murs (couleur ou motif)
  // et sur la dalle de toiture.
  let batSel = null;
  const sel = (expr, valeur) => (batSel === null ? expr : ["case", ["==", ["get", "osm_id"], batSel], valeur, expr]);
  const peintureDe = (id) => construireStyle(ambiance, optionsStyle()).layers.find((l) => l.id === id).paint;
  const surlignerBatiment = (props) => {
    batSel = props ? props.osm_id : null;
    if (map.getLayer("batiments-3d")) {
      const p = peintureDe("batiments-3d");
      map.setPaintProperty("batiments-3d", "fill-extrusion-color", sel(p["fill-extrusion-color"], "#f2c200"));
      map.setPaintProperty("batiments-3d", "fill-extrusion-pattern", p["fill-extrusion-pattern"] ? sel(p["fill-extrusion-pattern"], MOTIF_SELECTION) : undefined);
    }
    if (map.getLayer("batiments-toits")) map.setPaintProperty("batiments-toits", "fill-extrusion-color", sel(peintureDe("batiments-toits")["fill-extrusion-color"], "#e0b300"));
  };
  /** Couches visibles selon le relief, la qualité et l'ambiance (pas d'ombres simulées de nuit ni en mode léger). */
  const appliquerVisibilites = () => {
    const vis = (id, oui) => { if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", oui ? "visible" : "none"); };
    vis("batiments-3d", vue3D);
    vis("batiments-toits", vue3D && qualite === "haute");
    const ombres = vue3D && qualite === "haute" && Boolean(AMBIANCES[ambiance].ombre);
    for (const l of map.getStyle().layers) if (l.id.startsWith("ombre-")) vis(l.id, ombres);
    if (map.getLayer("batiments-plats")) map.setLayerZoomRange("batiments-plats", 13, vue3D ? 14.6 : 24);
  };
  const peindreBatiments = () => {
    const p = peintureDe("batiments-3d");
    for (const k of ["fill-extrusion-height", "fill-extrusion-base"]) map.setPaintProperty("batiments-3d", k, p[k]);
    surlignerBatiment(batSel === null ? null : { osm_id: batSel });
  };
  // Motifs de façade chargés en arrière-plan : la carte s'affiche d'abord en couleurs pleines.
  const materiaux = new Materiaux(map);
  materiaux.charger().then(() => {
    materiaux.appliquer(AMBIANCES[ambiance]);
    motifsPrets = true;
    peindreBatiments();
  }).catch(() => { /* motifs indisponibles : couleurs pleines, comme en mode léger */ });
  appliquerVisibilites();

  const handlers = { select: () => {}, ground: () => {}, road: () => {}, hover: () => {}, camera: () => {} };
  let mode = "selection";
  let selectedTerritory = null;
  let rue = false;
  let frameMs = 16;
  let t0 = performance.now();
  map.on("render", () => { const t = performance.now(); frameMs = frameMs * 0.9 + (t - t0) * 0.1; t0 = t; });

  const toLocal = (lngLat) => proj.toLocal(lngLat.lat, lngLat.lng);
  const territoryAt = (lat, lon) => {
    const p = proj.toLocal(lat, lon);
    return territories.find((t) => !t.secteur && t.contains(p.x, p.z)) || territories.find((t) => t.contains(p.x, p.z)) || null;
  };
  const coucheExiste = (ids) => ids.filter((id) => map.getLayer(id));
  const boite = (p, r = 6) => [[p.x - r, p.y - r], [p.x + r, p.y + r]];

  /** Objet opérationnel sous le pointeur : signalements, puis camion (modèle 3D touché ou repère), puis points du
   *  plan, coupures et tournées, enfin camion le plus proche (petits modèles au loin). Sert au clic et au survol. */
  function operationnelEn(point) {
    const trouver = (couches) => {
      for (const f of map.queryRenderedFeatures(boite(point), { layers: coucheExiste(couches) })) {
        const objet = op.objet(f.source, f.properties.i);
        if (objet) return { info: objet, lonlat: f.geometry.type === "Point" ? f.geometry.coordinates : null };
      }
      return null;
    };
    const camionTrouve = (c) => (c ? { info: { ...c.userData }, objet: c } : null);
    const repere = () => {
      const f = map.queryRenderedFeatures(boite(point, 3), { layers: coucheExiste(["op-camions"]) })[0];
      return f ? flotte.get(f.properties.id) : null;
    };
    return trouver(["op-signalements", "op-simules"])
      || camionTrouve(camionEn(point, false) || repere())
      || trouver(["op-points", "op-coupures", "op-tournees"])
      || camionTrouve(camionEn(point, true));
  }

  /** Objet sous le pointeur : opérationnel d'abord, puis la ville (bâtiment, lieu, quartier). */
  function objetEn(point, lngLat) {
    const ops = operationnelEn(point);
    if (ops) return ops;
    const poi = map.queryRenderedFeatures(boite(point, 5), { layers: coucheExiste(["poi-points", "poi-noms"]) });
    if (poi.length) return { info: { kind: "poi", props: poi[0].properties }, lonlat: poi[0].geometry.coordinates };
    const bat = map.queryRenderedFeatures(boite(point, 1), { layers: coucheExiste(["batiments-toits", "batiments-3d", "batiments-plats"]) });
    if (bat.length) return { info: { kind: "batiment", props: bat[0].properties, lat: lngLat.lat, lon: lngLat.lng } };
    const t = territoryAt(lngLat.lat, lngLat.lng);
    if (t) return { info: { kind: "quartier", territory: t } };
    return null;
  }

  map.on("click", (e) => {
    if (mode === "ajout-depotoir") return handlers.ground({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    if (mode === "coupure-route") {
      const f = map.queryRenderedFeatures(boite(e.point, 10), { layers: ["op-reseau"] })[0];
      return handlers.road(f ? op.objet("op-reseau", f.properties.i) : null);
    }
    const hit = objetEn(e.point, e.lngLat);
    handlers.select(hit ? hit.info : null, hit?.objet || (hit?.lonlat ? { lonlat: hit.lonlat } : null));
  });
  let survol = 0;
  map.on("mousemove", (e) => {
    if (performance.now() - survol < 60) return;
    survol = performance.now();
    if (mode === "coupure-route") {
      const f = map.queryRenderedFeatures(boite(e.point, 10), { layers: ["op-reseau"] })[0];
      const road = f ? op.objet("op-reseau", f.properties.i) : null;
      map.getCanvas().style.cursor = road ? "pointer" : "crosshair";
      return handlers.hover(road ? { kind: "route", road } : null, e.originalEvent);
    }
    const info = operationnelEn(e.point)?.info || null;
    map.getCanvas().style.cursor = info ? "pointer" : mode === "selection" ? "" : "crosshair";
    handlers.hover(info, e.originalEvent);
  });
  map.on("mouseout", () => handlers.hover(null, null));

  // Avancement des camions (animation SIMULÉE) : une mise à jour de la source op-avancement au plus deux fois par
  // seconde, et seulement si un camion roule ; immédiate après un nouveau plan, une pause ou une sélection.
  let camionSel = null;
  const majAvancement = () => op.majAvancement(flotte, camionSel);
  setInterval(() => {
    if (document.hidden || !flotte.playing) return;
    for (const t of flotte.trucks.values()) if (!t.idle && !t.broken) { majAvancement(); return; }
  }, 500);

  const fin = () => new Promise((ok) => map.once("moveend", ok));
  const voler = (opts) => { const p = fin(); map.flyTo({ ...opts, essential: true, duration: opts.duration ?? 1600 }); return p; };
  const zoomPourDistance = (d) => Math.max(14, Math.min(19, 17.6 - Math.log2(Math.max(40, d) / 160)));

  const view = {
    kind: "carte",
    map,
    proj,
    city: { roads, territories },
    roadById,
    fleet: flotte,
    layers: op,
    statutsLegend: STATUTS,
    /** Abonne fn à l'évènement name ; renvoie le gestionnaire précédent (pour le compléter sans le perdre). */
    on(name, fn) { const avant = handlers[name]; handlers[name] = fn; return avant; },
    onCamera(fn) { handlers.camera = fn; },
    setReports(list) { op.setReports(list); },
    setSimDumps(list) { op.setSimDumps(list); },
    setPlan(plan) {
      op.setPlan(plan);
      flotte.setPlan(plan, op.couleurCamion);
      op.setCoupures(plan?.cut_roads || [], roadById);
      majAvancement();
      map.triggerRepaint();
    },
    vehicleColor(id) { return `#${(op.couleurCamion.get(id) ?? 0x9a9a92).toString(16).padStart(6, "0")}`; },
    setRain(on) { container.classList.toggle("pluie-carte", Boolean(on)); },
    setPlaying(on) { flotte.setPlaying(on); majAvancement(); map.triggerRepaint(); },
    setInteraction(m) {
      mode = m;
      op.afficherReseau(m === "coupure-route");
      map.getCanvas().style.cursor = m === "selection" ? "" : "crosshair";
    },
    highlightTerritory(id) { selectedTerritory = id; op.surlignerQuartier(id); },
    select(info, objet) {
      op.marquer(null);
      op.surligner([]);
      surlignerBatiment(null);
      const sel = info?.kind === "vehicule" ? info.id
        : info?.kind === "tournee" ? String(info.data.vehicle_id || info.data.vehicle).split("_trip")[0] : null;
      if (sel !== camionSel) { camionSel = sel; majAvancement(); }
      if (!info) return;
      if (objet?.lonlat) op.marquer(objet.lonlat);
      else if (info.data && Number.isFinite(Number(info.data.lat))) op.marquer([Number(info.data.lon), Number(info.data.lat)]);
      if (info.kind === "vehicule") {
        const plan = (info.legs || []).map((l) => l.trip);
        const routes = (map.getSource("op-tournees") && op.donnees.get("op-tournees")) || [];
        op.surligner(routes.filter((r) => plan.includes(r.data.vehicle_id || r.data.vehicle)).map((r) => r.data.path.map(([la, lo]) => [lo, la])));
      }
      if (info.kind === "tournee") op.surligner([info.data.path.map(([la, lo]) => [lo, la])]);
      if (info.kind === "route" && info.road) op.surligner([info.road.pts.map(([x, z]) => { const [la, lo] = versLatLon(x, z); return [lo, la]; })]);
      if (info.kind === "batiment") surlignerBatiment(info.props);
    },
    focusLatLon(lat, lon, distance = 220) {
      return voler({ center: [lon, lat], zoom: zoomPourDistance(distance), pitch: Math.max(map.getPitch(), 50) });
    },
    focusTerritory(id) {
      const t = territories.find((x) => x.id === id);
      if (!t) return null;
      const pts = t.rings.flat().map(([x, z]) => versLatLon(x, z));
      const lats = pts.map((p) => p[0]);
      const lons = pts.map((p) => p[1]);
      const p = fin();
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
        { padding: { top: 90, bottom: 60, left: 360, right: 380 }, pitch: 45, bearing: map.getBearing(), duration: 1600, maxZoom: 16.5 });
      return p;
    },
    focusLngLatBounds(bounds) {
      const p = fin();
      map.fitBounds(bounds, { padding: { top: 90, bottom: 60, left: 360, right: 380 }, maxZoom: 17.5, duration: 1500 });
      return p;
    },
    overview() { rue = false; handlers.camera("dessus"); return voler({ center: CARTE.centre, zoom: CARTE.vueVille.zoom, pitch: 0, bearing: 0 }); },
    immersive() { rue = false; handlers.camera("immersive"); return voler({ zoom: Math.max(map.getZoom(), 15.4), pitch: 62, bearing: map.getBearing() || -17 }); },
    street() { rue = true; handlers.camera("rue"); return voler({ zoom: 18.3, pitch: 76, bearing: map.getBearing() }); },
    exitStreet() { if (rue) { rue = false; handlers.camera("immersive"); } },
    reset() { rue = false; return voler({ center: CARTE.centre, ...CARTE.vueDepart }); },
    territoryAt,
    frameMs() { return frameMs; },
    setAmbiance(nom) {
      if (!AMBIANCES[nom]) return;
      ambiance = nom;
      try { localStorage.setItem("yilgre.ambiance", nom); } catch { /* ignoré */ }
      const style = construireStyle(nom, optionsStyle());
      map.setSky(style.sky);
      map.setLight(style.light);
      for (const l of style.layers) {
        if (!map.getLayer(l.id) || l.id === "batiments-3d" || l.id === "batiments-toits") continue;
        for (const [k, v] of Object.entries(l.paint || {})) map.setPaintProperty(l.id, k, v);
      }
      if (motifsPrets) materiaux.appliquer(AMBIANCES[nom]);
      peindreBatiments();
      appliquerVisibilites();
      op.setAmbiance(nom);
      container.dataset.ambiance = nom;
    },
    get ambiance() { return ambiance; },
    /** « haute » : motifs de façade, toits et ombres simulées ; « leger » : couleurs pleines, sans ombres ni toits,
     *  inclinaison maximale réduite et résolution d'écran simple (moins de calcul par image). */
    setQualite(nom) {
      qualite = nom === "leger" ? "leger" : "haute";
      try { localStorage.setItem("yilgre.qualite", qualite); } catch { /* ignoré */ }
      map.setMaxPitch(qualite === "leger" ? 60 : 78);
      map.setPixelRatio(qualite === "leger" ? 1 : (window.devicePixelRatio || 1));
      peindreBatiments();
      appliquerVisibilites();
      container.dataset.qualite = qualite;
    },
    get qualite() { return qualite; },
    setVue3D(oui) {
      vue3D = Boolean(oui);
      appliquerVisibilites();
      return voler({ pitch: oui ? Math.max(50, map.getPitch()) : 0, bearing: oui ? map.getBearing() : 0, duration: 900 });
    },
    sourceHauteur,
    get selectedTerritory() { return selectedTerritory; },
    toLocal,
  };
  op.setAmbiance(ambiance);
  container.dataset.ambiance = ambiance;
  container.dataset.qualite = qualite;
  return view;
}
