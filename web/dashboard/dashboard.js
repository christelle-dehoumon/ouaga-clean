const API = window.location.origin;
const $ = (id) => document.getElementById(id);
let crisesActives = new Set();
let dernierPlan = null;
let planA = null;
let planB = null;
let couches = null;

const map = window.L ? L.map("map").setView([12.3615, -1.5283], 12) : null;
if (map) {
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution: "© OSM"}).addTo(map);
  couches = L.layerGroup().addTo(map);
} else {
  $("map").textContent = "La bibliothèque cartographique Leaflet n’a pas pu être chargée.";
}

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = body && typeof body === "object" ? body.error || response.statusText : response.statusText;
    throw new Error(message || `HTTP ${response.status}`);
  }
  return body;
}

function showError(error) {
  const banner = $("bandeau");
  banner.style.display = "block";
  banner.textContent = `Erreur : ${error.message}`;
}

function updateSliderLabels() {
  $("v-pop").textContent = Number($("pop").value).toLocaleString("fr-FR");
  $("v-abo").textContent = `${$("abo").value}%`;
  $("v-cam").textContent = $("cam").value;
  $("v-fc").textContent = `${$("fc").value}/sem`;
  $("v-bud").textContent = `${$("bud").value} M`;
}

for (const id of ["pop", "abo", "cam", "fc", "bud"]) {
  $(id).addEventListener("input", updateSliderLabels);
}

function paramsActuels() {
  const trucks = Number($("cam").value);
  const panne = crisesActives.has("panne_camions");
  return {
    population: Number($("pop").value),
    subscription_rate: Number($("abo").value) / 100,
    trucks,
    truck_capacity_kg: 5000,
    tricycles: 40,
    tricycle_capacity_kg: 400,
    frequency_per_week: Number($("fc").value),
    budget: Number($("bud").value) * 1_000_000,
    rainy_season: crisesActives.has("saison_pluies"),
    broken_trucks: panne ? Array.from({length: Math.min(3, trucks)}, (_, i) => `truck${i + 1}`) : [],
    extra_territories: crisesActives.has("nouveau_quartier") ? ["saaba"] : [],
  };
}

async function recalculer() {
  $("chrono").textContent = "Calcul du plan…";
  try {
    const plan = await api("/api/plans", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({params: paramsActuels()}),
    });
    dernierPlan = plan;
    $("chrono").textContent = `Calculé en ${plan.compute_ms} ms — mode ${plan.mode}`;
    $("bandeau").style.display = "none";
    majBandeau(plan);
    majCarte(plan);
    majKpi(plan);
    majChangements(plan);
    majAB();
  } catch (error) {
    $("chrono").textContent = "Le calcul a échoué.";
    showError(error);
  }
}

function majBandeau(plan) {
  const messages = [...(plan.checks?.messages || []), ...(plan.warnings || [])];
  if (messages.length) {
    const banner = $("bandeau");
    banner.style.display = "block";
    banner.textContent = messages.join(" ");
  }
  $("modePlan").textContent = plan.mode;
  $("modePlan").className = `pill ${plan.mode === "fallback" ? "pill-rouge" : "pill-vert"}`;
}

async function chargerSignalements() {
  try {
    const reports = await api("/api/reports?limit=5000");
    if (dernierPlan) majCarte(dernierPlan, reports);
    const counts = {accepte: 0, rejete: 0, a_verifier: 0};
    for (const report of reports) counts[report.status] = (counts[report.status] || 0) + 1;
    const output = $("statsSig");
    output.replaceChildren();
    const summary = document.createElement("p");
    summary.textContent = `${counts.accepte} acceptés · ${counts.rejete} rejetés · ${counts.a_verifier} à vérifier`;
    output.append(summary);
    const latest = document.createElement("p");
    latest.className = "muted";
    latest.textContent = reports.slice(0, 3).map((report) => `${report.id}: ${report.status} — ${report.reason || report.reason_code}`).join(" | ");
    output.append(latest);
  } catch (error) {
    showError(error);
  }
}

function majCarte(plan, reports = []) {
  if (!couches) return;
  couches.clearLayers();
  const pointsById = new Map();
  for (const point of plan.collection_points || []) {
    pointsById.set(point.id, point);
    const color = point.type === "dumpsite" ? "#009E49" : "#333";
    L.circleMarker([point.lat, point.lon], {radius: 7, color, weight: 1, fillColor: "#fff", fillOpacity: 1})
      .addTo(couches).bindPopup(`<b>${point.id}</b><br>${point.demand_kg} kg`);
  }
  for (const route of plan.routes || []) {
    const geometry = route.geometry;
    if (geometry?.type === "LineString" && Array.isArray(geometry.coordinates)) {
      const positions = geometry.coordinates.map(([lon, lat]) => [lat, lon]);
      L.polyline(positions, {color: route.type === "truck" ? "#EF2B2D" : "#009E49", weight: 4, opacity: 0.85})
        .addTo(couches).bindPopup(`${route.vehicle} · ${route.distance_km} km`);
    }
    for (const id of route.stops || []) {
      const point = pointsById.get(id);
      if (point) L.circleMarker([point.lat, point.lon], {radius: 4, fillColor: "#EF2B2D", color: "#fff", weight: 1}).addTo(couches);
    }
  }
  const reportColors = {accepte: "#009E49", rejete: "#EF2B2D", a_verifier: "#FCD116"};
  for (const report of reports) {
    const color = reportColors[report.status];
    if (color && Number.isFinite(report.lat) && Number.isFinite(report.lon)) {
      L.circleMarker([report.lat, report.lon], {radius: 5, fillColor: color, color: "#fff", weight: 1, fillOpacity: 1})
        .addTo(couches).bindPopup(`${report.id} · ${report.status}`);
    }
  }
}

function majKpi(plan) {
  const totals = plan.totals || {};
  $("k-tonnes").textContent = `${(Number(totals.uncollected_kg || 0) / 1000).toFixed(2)} t`;
  $("k-budget").textContent = `${(Number(totals.budget_remaining || 0) / 1_000_000).toFixed(2)} M`;
  $("k-depots").textContent = String(totals.points_unserved ?? "—");

  const canvas = $("courbes");
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  const collected = Math.max(0, Number(totals.collected_kg || 0));
  const uncollected = Math.max(0, Number(totals.uncollected_kg || 0));
  const max = Math.max(collected, uncollected, 1);
  const scale = 90 / max;
  context.fillStyle = "#009E49";
  context.fillRect(60, 15, Math.max(1, collected * scale), 30);
  context.fillStyle = "#EF2B2D";
  context.fillRect(60, 65, Math.max(1, uncollected * scale), 30);
  context.fillStyle = "#1a1a1a";
  context.font = "12px system-ui";
  context.fillText(`Collectés : ${collected.toFixed(0)} kg`, 5, 35);
  context.fillText(`Non collectés : ${uncollected.toFixed(0)} kg`, 5, 85);
}

function majChangements(plan) {
  const el = $("changements");
  const messages = [...(plan.assumptions || []), ...(plan.warnings || [])];
  el.textContent = messages.length ? messages.join(" ") : "Aucune hypothèse ni alerte pour ce plan.";
}

async function crise(id) {
  crisesActives.add(id);
  await recalculer();
}

async function resetCrises() {
  crisesActives.clear();
  await recalculer();
}

async function injecterPieges() {
  const now = new Date().toISOString();
  const reports = [
    {lat: 12.60, lon: -1.55, size: "moyen"},
    {lat: 12.3615, lon: -1.5283, size: "petit"},
    {lat: 12.403, lon: -1.559, size: "moyen"},
    {lat: 13.0, lon: -1.5, size: "grand"},
  ].map((item) => ({
    ...item, id: crypto.randomUUID(), reported_at: now, source: "simule",
  }));
  try {
    const result = await api("/api/reports/bulk", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(reports),
    });
    const counts = result.stats.par_statut;
    alert(`Traitement réel : ${counts.accepte || 0} acceptés, ${counts.rejete || 0} rejetés, ${counts.a_verifier || 0} à vérifier.`);
    await chargerSignalements();
  } catch (error) {
    showError(error);
  }
}

async function simulerPlan() {
  if (!dernierPlan) return showError(new Error("Calculez d’abord un plan."));
  try {
    const result = await api(`/api/plans/${encodeURIComponent(dernierPlan.plan_id)}/simulation`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({days: 7}),
    });
    $("simOut").textContent = `Simulation ${result.days} jours (${result.moteur}) — part ramassée ${Math.round(result.part_ramassee * 100)}% — ménages synthétiques avec dépôt sauvage ${result.depotoirs_restants} — coût du plan ${result.cout_m_fcfa} M FCFA. ${result.assumptions.join(" ")}`;
    $("k-part").textContent = `${Math.round(result.part_ramassee * 100)}%`;
  } catch (error) {
    showError(error);
  }
}

function figer(which) {
  if (!dernierPlan) return showError(new Error("Calculez d’abord un plan."));
  if (which === "A") planA = dernierPlan;
  else planB = dernierPlan;
  majAB();
}

function majAB() {
  const el = $("ab");
  el.replaceChildren();
  for (const [label, plan] of [["A", planA], ["B", planB]]) {
    const card = document.createElement("div");
    card.className = "card";
    card.textContent = plan
      ? `${label} · ${plan.plan_id} · ${(plan.totals.cost / 1_000_000).toFixed(2)} M FCFA · ${plan.totals.uncollected_kg} kg non collectés`
      : `${label} · non figé`;
    el.append(card);
  }
  if (planA && planB) {
    $("diff").textContent = `B − A : ${((planB.totals.cost - planA.totals.cost) / 1_000_000).toFixed(2)} M FCFA · ${(planB.totals.uncollected_kg - planA.totals.uncollected_kg).toFixed(1)} kg non collectés`;
  }
}

async function exportOsm() {
  if (!dernierPlan) return showError(new Error("Calculez d’abord un plan."));
  try {
    const response = await fetch(`${API}/api/plans/${encodeURIComponent(dernierPlan.plan_id)}/export`);
    if (!response.ok) throw new Error(`Export impossible (HTTP ${response.status}).`);
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `plan-${dernierPlan.plan_id}.geojson`;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    showError(error);
  }
}

function validerPlan() {
  if (!dernierPlan) return showError(new Error("Aucun plan calculé."));
  const failed = Object.entries(dernierPlan.checks || {}).filter(([key, value]) => key !== "messages" && value !== true);
  if (failed.length) {
    alert(`Plan non cohérent : ${(dernierPlan.checks.messages || []).join(" ") || failed.map(([key]) => key).join(", ")}`);
    return;
  }
  alert(`Contrôles du plan ${dernierPlan.plan_id} validés. Cette vérification n’enregistre pas une décision municipale.`);
}

updateSliderLabels();
chargerSignalements();
recalculer();
