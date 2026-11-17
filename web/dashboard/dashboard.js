/* Tableau de bord mairie — Backend + apports membre C.
 * Toutes les données viennent du vrai Backend (/api/...). Carte, icônes et
 * géométries sont locales : aucune tuile, police, CDN ou ressource externe.
 * Les valeurs simulées sont étiquetées ; les règles sont des hypothèses à valider.
 */

const API = window.location.origin;
const $ = (id) => document.getElementById(id);

const NOMS_ACTEURS_FR = {
  menages: "Ménages",
  pre_collecteurs: "Pré-collecteurs",
  brigade: "Brigade Laabal",
  mairie: "Mairie",
};
const CLASSES_STATUT = {
  accepte: "signal-accepte",
  rejete: "signal-rejete",
  a_verifier: "signal-a_verifier",
};
const NOMS_ICONS = ["brigade", "camion-benne", "ctvd", "menage", "point-regroupement", "tricycle"];
const COULEURS = {truck: "#EF2B2D", tricycle: "#009E49", depotoir: "#009E49", neutre: "#333333"};

const ETAT = {
  plan: null,
  resultat: null,
  actifs: {menages: true, pre_collecteurs: true, brigade: true, mairie: true},
  crises: new Set(),
  planA: null,
  planB: null,
  carte: null,
  couchesFond: null,
  couchesPlan: null,
  couchesActeurs: null,
  couchesSignalements: null,
  fond: {zones: null, eau: null},
  icons: {},
  signalements: [],
  idsSignalements: new Set(),
  filtreJournal: "tous",
  polling: null,
  alerteSignalements: null,
  enCoursSimulation: false,
};

const CARTES_ACTEURS = [
  {
    cle: "menages", nom: "Ménages", icone: "menage",
    role: "Produisent les déchets et choisissent le dépôt selon la desserte et la saturation du plan.",
    chiffres: (r) => [
      ["Abonnés", (r.indicateurs?.menages?.abonnes_pct ?? "—") + " %"],
      ["Dépôts créés", r.indicateurs?.menages?.depotoirs_crees ?? "—"],
    ],
  },
  {
    cle: "pre_collecteurs", nom: "Pré-collecteurs", icone: "tricycle",
    role: "Ramassent les dépôts vers les points de regroupement ; leur passage dépend des masses collectées du plan.",
    chiffres: (r) => [
      ["Ramassé", (r.indicateurs?.pre_collecteurs?.tonnes_ramassees ?? "—") + " t"],
      ["Remplissage", r.indicateurs?.pre_collecteurs?.remplissage_moyen ?? "—"],
    ],
  },
  {
    cle: "brigade", nom: "Brigade Laabal", icone: "brigade",
    role: "Patrouille et sensibilise les ménages dans le rayon déclaré dans les hypothèses.",
    chiffres: (r) => [
      ["Patrouilles", r.indicateurs?.brigade?.patrouilles_actives ?? "—"],
      ["Dépôts évités", r.indicateurs?.brigade?.depots_evites ?? "—"],
    ],
  },
  {
    cle: "mairie", nom: "Mairie", icone: "camion-benne",
    role: "Mobilise les camions selon la flotte et le budget, vide les centres et paie le coût du plan.",
    chiffres: (r) => [
      ["Budget restant", (r.indicateurs?.mairie?.budget_restant_m_fcfa ?? "—") + " M"],
      ["Camions actifs", (r.indicateurs?.mairie?.camions_en_service ?? "—") + " / " +
        (r.indicateurs?.mairie?.camions_total ?? "—")],
    ],
  },
];

function texte(valeur) {
  return String(valeur ?? "—").replace(/[&<>"']/g, (car) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[car]);
}

function nombreFr(valeur, digits = 1) {
  if (valeur === null || valeur === undefined || valeur === "—") return "—";
  const nombre = Number(valeur);
  return Number.isFinite(nombre)
    ? nombre.toLocaleString("fr-FR", {minimumFractionDigits: digits, maximumFractionDigits: digits})
    : "—";
}

function marquerAncien(estAncien) {
  const badge = $("etat-donnees");
  badge.textContent = estAncien ? "données anciennes" : "données à jour";
  badge.classList.toggle("ancien", Boolean(estAncien));
}

function showError(error, estAncien = false) {
  const bandeau = $("bandeau");
  bandeau.hidden = false;
  bandeau.textContent = (estAncien ? "Donnée ancienne — " : "") +
    "Erreur : " + (error && error.message ? error.message : String(error));
  if (estAncien) marquerAncien(true);
}

function masquerErreur() {
  const bandeau = $("bandeau");
  bandeau.hidden = true;
  bandeau.textContent = "";
  marquerAncien(false);
}

async function api(chemin, options = {}) {
  const reponse = await fetch(API + chemin, options);
  const type = reponse.headers.get("content-type") || "";
  const corps = type.includes("json") ? await reponse.json() : await reponse.text();
  if (!reponse.ok) {
    const message = corps && typeof corps === "object"
      ? corps.error || corps.detail || reponse.statusText
      : reponse.statusText;
    throw new Error(message || "HTTP " + reponse.status);
  }
  return corps;
}

function majLabels() {
  $("v-pop").textContent = Number($("pop").value).toLocaleString("fr-FR");
  $("v-abo").textContent = $("abo").value + " %";
  $("v-cam").textContent = $("cam").value;
  $("v-tri").textContent = $("tri").value;
  $("v-fc").textContent = $("fc").value + "/sem";
  $("v-bud").textContent = nombreFr(Number($("bud").value) / 1e6, 1) + " M";
}

function mettreValeur(id, brut, facteur = 1) {
  const input = $(id);
  if (!input || brut === null || brut === undefined) return;
  const nombre = Number(brut) * facteur;
  if (!Number.isFinite(nombre)) return;
  const mini = Number(input.min);
  const maxi = Number(input.max);
  input.value = String(Math.min(Number.isFinite(maxi) ? maxi : nombre,
                                Math.max(Number.isFinite(mini) ? mini : nombre, nombre)));
}

function initialiserControles(parametres) {
  const p = parametres && typeof parametres === "object" ? parametres : {};
  mettreValeur("pop", p.population ?? p.pop);
  mettreValeur("abo", p.subscription_rate ?? p.abonnement, 100);
  mettreValeur("cam", p.trucks ?? p.nb_camions);
  mettreValeur("tri", p.tricycles ?? p.nb_tricycles);
  mettreValeur("fc", p.frequency_per_week ?? p.freq_camions_par_semaine);
  mettreValeur("bud", p.budget ?? p.budget_annuel_m_fcfa, 1e6 ? 1 / 1e6 : 1);
  if (p.seed !== undefined && p.seed !== null && Number.isFinite(Number(p.seed))) {
    $("graine").value = String(p.seed);
  }
  majLabels();
}

function paramsActuels() {
  const config = ETAT.plan?.params_used || {};
  const trucks = Number($("cam").value);
  const panne = ETAT.crises.has("panne_camions");
  const params = {
    population: Number($("pop").value),
    subscription_rate: Number($("abo").value) / 100,
    trucks,
    tricycles: Number($("tri").value),
    frequency_per_week: Number($("fc").value),
    budget: Number($("bud").value) * 1e6,
    rainy_season: ETAT.crises.has("saison_pluies"),
    broken_trucks: panne ? ["truck1"] : Array.isArray(config.broken_trucks) ? config.broken_trucks : [],
    extra_territories: ETAT.crises.has("nouveau_quartier")
      ? Array.from(new Set([...(Array.isArray(config.extra_territories) ? config.extra_territories : []), "saaba"]))
      : Array.isArray(config.extra_territories) ? config.extra_territories : [],
  };
  for (const cle of ["truck_capacity_kg", "tricycle_capacity_kg", "truck_trips_per_day"]) {
    if (config[cle] !== undefined) params[cle] = config[cle];
  }
  return params;
}

async function recalculer(options = {}) {
  const initial = Boolean(options.initial);
  $("chrono").textContent = "Calcul du plan…";
  try {
    const corps = initial ? {params: {}} : {params: paramsActuels()};
    const plan = await api("/api/plans", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(corps),
    });
    ETAT.plan = plan;
    if (initial) initialiserControles(plan.params_used || {});
    $("chrono").textContent = `Calculé en ${plan.compute_ms} ms — mode ${plan.mode}`;
    masquerErreur();
    majBandeau(plan);
    majCartePlan(plan);
    majKpi(plan);
    majChangements(plan);
    majAB();
    majStatsSignalements();
    await simulerPlan();
  } catch (error) {
    $("chrono").textContent = "Le calcul a échoué (dernier état conservé).";
    showError(error, true);
  }
}

function majBandeau(plan) {
  const messages = [...(plan.checks?.messages || []), ...(plan.warnings || [])];
  if (messages.length) {
    const bandeau = $("bandeau");
    bandeau.hidden = false;
    bandeau.textContent = messages.join(" ");
  }
  $("modePlan").textContent = plan.mode;
  $("modePlan").className = "pill kpi-valeur " +
    (plan.mode === "fallback" ? "pill-rouge" : "pill-vert");
}

function majKpi(plan) {
  const totaux = plan.totals || {};
  const collecte = Number(totaux.collected_kg || 0);
  const nonCollecte = Number(totaux.uncollected_kg || 0);
  $("k-tonnes").textContent = collecte === 0 && nonCollecte === 0
    ? "Aucun déchet généré"
    : (nonCollecte / 1000).toFixed(2) + " t";
  $("k-budget").textContent = nombreFr(Number(totaux.budget_remaining || 0) / 1e6, 2) + " M";
  $("k-depots").textContent = String(totaux.points_unserved ?? "—");
  $("k-depots").title = "Points du plan non desservis (contrat §5) — aucun relevé terrain";
  dessinerCourbesPlan(collecte, nonCollecte);
}

function dessinerCourbesPlan(collecte, nonCollecte) {
  const canvas = $("courbes");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const maximum = Math.max(collecte, nonCollecte, 1);
  const echelle = 90 / maximum;
  ctx.fillStyle = COULEURS.tricycle;
  ctx.fillRect(60, 15, Math.max(1, collecte * echelle), 30);
  ctx.fillStyle = COULEURS.truck;
  ctx.fillRect(60, 65, Math.max(1, nonCollecte * echelle), 30);
  ctx.fillStyle = "#1a1a1a";
  ctx.font = "14px system-ui, sans-serif";
  ctx.fillText(`Collectés : ${collecte.toFixed(0)} kg`, 5, 35);
  ctx.fillText(`Non collectés : ${nonCollecte.toFixed(0)} kg`, 5, 85);
}

function majChangements(plan) {
  const messages = [...(plan.assumptions || []), ...(plan.warnings || [])];
  $("changements").textContent = messages.length
    ? messages.join(" ")
    : "Aucune hypothèse ni alerte pour ce plan.";
}

async function simulerPlan() {
  if (!ETAT.plan) return showError(new Error("Calculez d'abord un plan."));
  if (ETAT.enCoursSimulation) return;
  ETAT.enCoursSimulation = true;
  $("simOut").textContent = "Simulation en cours…";
  try {
    const corps = {days: 7, actors_enabled: ETAT.actifs};
    const graine = $("graine").value === ""
      ? ETAT.resultat?.graine
      : Number($("graine").value);
    if (Number.isFinite(graine)) corps.seed = graine;
    const resultat = await api(
      `/api/plans/${encodeURIComponent(ETAT.plan.plan_id)}/simulation`,
      {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(corps)});
    if (resultat.error) throw new Error(resultat.error);
    ETAT.resultat = resultat;
    masquerErreur();
    majSimulation(resultat);
  } catch (error) {
    showError(error, true);
    if (ETAT.resultat) majSimulation(ETAT.resultat, true);
    else $("simOut").textContent = "Simulation indisponible : aucun résultat valide à afficher.";
  } finally {
    ETAT.enCoursSimulation = false;
  }
}

function majSimulation(resultat, estAncien = false) {
  const sansDechet = Boolean(resultat.sans_dechet);
  $("k-part").textContent = sansDechet
    ? "Aucun déchet généré"
    : (Number.isFinite(Number(resultat.part_ramassee))
        ? Math.round(Number(resultat.part_ramassee) * 100) + " %"
        : "—");
  $("k-part").title = sansDechet
    ? "Aucun déchet généré : aucun pourcentage n'est affiché"
    : "Part ramassée simulée (proxy, pas un relevé terrain)";
  $("k-depots").textContent = String(resultat.depotoirs_restants ?? "—");
  $("k-depots").title = resultat.unite_depotoirs_restants ||
    "ménages synthétiques et dépotoirs du plan (proxy)";

  const resumeDechet = sansDechet
    ? "Aucun déchet généré"
    : `part ramassée ${Math.round(Number(resultat.part_ramassee || 0) * 100)} %`;
  const hypotheses = Array.isArray(resultat.assumptions) ? resultat.assumptions.join(" ") : "";
  $("simOut").textContent = (estAncien ? "Donnée ancienne — " : "") +
    `Simulation (simulé) — ${resultat.days} jours (${resultat.moteur}) — ${resumeDechet} — ` +
    `dépôts restants ${resultat.depotoirs_restants} (${resultat.unite_depotoirs_restants}) — ` +
    `coût ${resultat.cout_m_fcfa} M FCFA. ${hypotheses}`;

  rendreActeurs(resultat);
  rendreFiltresJournal();
  rendreJournal(resultat);
  rendreEtatsPoints(resultat);
  rendreSeries(resultat);
  rendreHypotheses(resultat);
  majCarteActeurs(resultat);
}

/* ---------- Icônes SVG locales ---------- */
async function chargerIcones() {
  await Promise.all(NOMS_ICONS.map(async (nom) => {
    try {
      const reponse = await fetch(`${API}/dashboard/icons/${nom}.svg`);
      if (!reponse.ok) throw new Error("icône " + reponse.status);
      const source = await reponse.text();
      const doc = new DOMParser().parseFromString(source, "image/svg+xml");
      ETAT.icons[nom] = Array.from(doc.documentElement.children)
        .map((enfant) => new XMLSerializer().serializeToString(enfant)).join("");
    } catch (error) {
      ETAT.icons[nom] = "";
    }
  }));
}

function iconeHtml(nom) {
  return '<span class="ic" aria-hidden="true"><svg viewBox="0 0 24 24">' +
    (ETAT.icons[nom] || "") + "</svg></span>";
}

function iconeDiv(nom, couleur) {
  return L.divIcon({
    className: "icone-carte",
    html: '<div style="color:' + couleur + '"><svg viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' +
      (ETAT.icons[nom] || "") + "</svg></div>",
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    popupAnchor: [0, -14],
  });
}

/* ---------- Cartes d'acteurs ---------- */
function rendreActeurs(resultat) {
  const conteneur = $("acteurs");
  conteneur.innerHTML = CARTES_ACTEURS.map((carte) => {
    const actif = ETAT.actifs[carte.cle] !== false;
    const chiffres = carte.chiffres(resultat).map(([label, valeur]) =>
      '<div class="acteur-chiffre"><span>' + texte(label) + "</span><b>" + texte(valeur) + "</b></div>").join("");
    return '<article class="acteur' + (actif ? "" : " desactive") + '">' +
      '<div class="acteur-entete"><span class="acteur-ic">' + iconeHtml(carte.icone) + "</span>" +
      "<div><div class=\"acteur-nom\">" + texte(carte.nom) + "</div>" +
      '<div class="acteur-etat">' + (actif ? "actif (simulé)" : "retiré du scénario") + "</div></div></div>" +
      '<p class="aide">' + texte(carte.role) + "</p>" +
      '<div class="acteur-chiffres">' + chiffres + "</div>" +
      '<button type="button" class="btn ' + (actif ? "btn-retirer" : "btn-restaurer") + '" ' +
      'data-acteur="' + carte.cle + '" aria-label="' + (actif ? "Retirer " : "Rétablir ") +
      texte(carte.nom) + '">' + (actif ? "Retirer cet acteur" : "Rétablir cet acteur") + "</button></article>";
  }).join("");
  conteneur.querySelectorAll("button[data-acteur]").forEach((bouton) => {
    bouton.addEventListener("click", () => {
      const cle = bouton.getAttribute("data-acteur");
      ETAT.actifs[cle] = ETAT.actifs[cle] === false;
      simulerPlan();
    });
  });
}

/* ---------- Journal, états des points, séries, hypothèses ---------- */
function rendreFiltresJournal() {
  const conteneur = $("filtresJournal");
  const filtres = [["tous", "Tous"], ...Object.entries(NOMS_ACTEURS_FR)];
  conteneur.innerHTML = filtres.map(([cle, nom]) =>
    '<button type="button" class="filtre' + (ETAT.filtreJournal === cle ? " actif" : "") +
    '" data-filtre="' + cle + '">' + texte(nom) + "</button>").join("");
  conteneur.querySelectorAll("button[data-filtre]").forEach((bouton) => {
    bouton.addEventListener("click", () => {
      ETAT.filtreJournal = bouton.getAttribute("data-filtre");
      conteneur.querySelectorAll("button[data-filtre]").forEach((autre) =>
        autre.classList.toggle("actif", autre === bouton));
      if (ETAT.resultat) rendreJournal(ETAT.resultat);
    });
  });
}

function rendreJournal(resultat) {
  const evenements = Array.isArray(resultat.events) ? resultat.events : [];
  const visibles = ETAT.filtreJournal === "tous"
    ? evenements
    : evenements.filter((evenement) => evenement.acteur === ETAT.filtreJournal);
  $("journal").innerHTML = visibles.length
    ? visibles.map((evenement) =>
        '<li data-acteur="' + texte(evenement.acteur) + '">' +
        '<span class="jour">J ' + texte(evenement.jour) + "</span><span>" +
        '<span class="qui">' + texte(NOMS_ACTEURS_FR[evenement.acteur] || evenement.acteur) + "</span><br>" +
        texte(evenement.texte) + " <span class=\"tag-sim\">" +
        (evenement.data_tag === "plan" ? "lu dans le plan" : "simulé") + "</span></span></li>").join("")
    : '<li class="vide">Aucun événement simulé pour ce filtre.</li>';
}

function rendreEtatsPoints(resultat) {
  const etats = Array.isArray(resultat.points_etat) ? resultat.points_etat : [];
  $("etatsPoints").innerHTML = etats.length
    ? etats.map((point) => {
        let details = "";
        if (point.raison) details += " — motif : " + texte(point.raison);
        if (point.jour !== undefined) details += " — J" + texte(point.jour);
        if (point.tournee) details += " — tournée " + texte(point.tournee);
        return '<li data-etat="' + texte(point.etat) + '">' +
          '<span class="jour">' + texte(point.id) + "</span><span>" +
          '<span class="qui">' + texte(point.etat) + "</span>" + details + " <span class=\"tag-sim\">" +
          (point.source === "plan" ? "lu dans le plan" : "simulé") + "</span></span></li>";
      }).join("")
    : '<li class="vide">Aucun état de point fourni par cette simulation.</li>';
}

function rendreSeries(resultat) {
  const canvas = $("series");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const series = Array.isArray(resultat.series) ? resultat.series : [];
  if (!series.length) {
    ctx.fillStyle = "#4b5563";
    ctx.font = "14px system-ui, sans-serif";
    ctx.fillText("Aucune série simulée disponible.", 10, 24);
    return;
  }
  const courbes = [
    {cle: "part_ramassee", couleur: COULEURS.tricycle, max: 1},
    {cle: "cout_m_fcfa", couleur: COULEURS.truck},
    {cle: "depotoirs_restants", couleur: "#155e75"},
  ];
  const marge = 40;
  for (const courbe of courbes) {
    const valeurs = series.map((point) => Number(point[courbe.cle]));
    const maximum = courbe.max ?? Math.max(...valeurs, 1);
    ctx.strokeStyle = courbe.couleur;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    valeurs.forEach((valeur, index) => {
      const x = marge + index * (canvas.width - marge - 16) / Math.max(1, valeurs.length - 1);
      const y = canvas.height - 28 - (valeur / maximum) * (canvas.height - 52);
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
  ctx.font = "14px system-ui, sans-serif";
  ctx.fillStyle = "#4b5563";
  ctx.fillText("J1", 4, canvas.height - 8);
  ctx.fillText("J" + series.length, canvas.width - 44, canvas.height - 8);
  let x = marge;
  for (const courbe of courbes) {
    ctx.fillStyle = courbe.couleur;
    ctx.fillRect(x, 12, 14, 5);
    ctx.fillStyle = "#1a1a1a";
    ctx.fillText(courbe.cle.replaceAll("_", " "), x + 20, 18);
    x += 190;
  }
}

function rendreHypotheses(resultat) {
  const liste = Array.isArray(resultat.hypotheses) ? resultat.hypotheses : [];
  $("hypotheses").innerHTML = liste.length
    ? liste.map((hypothese) =>
        '<div class="hypothese"><b>' + texte(hypothese.cle) + " = " + texte(hypothese.valeur) + "</b>" +
        '<div class="source">source : ' + texte(hypothese.source) + "</div>" +
        '<div class="note">' + texte(hypothese.note || "hypothèse à valider") + "</div></div>").join("")
    : '<p class="aide">Aucune hypothèse déclarée par la simulation.</p>';
}

/* ---------- Carte locale : fond neutre, géométries locales, aucun tuile ---------- */
async function chargerGeo(chemin) {
  try {
    const reponse = await fetch(API + chemin);
    if (!reponse.ok) return null;
    return await reponse.json();
  } catch (error) {
    return null;
  }
}

async function chargerFonds() {
  ETAT.fond.zones = await chargerGeo("/dashboard/geo/zones.geojson");
  ETAT.fond.eau = await chargerGeo("/dashboard/geo/water.geojson");
}

function initialiserCarte() {
  if (!window.L || !L.map) {
    $("map").textContent = "Carte locale indisponible : les chiffres et le journal restent utilisables.";
    return;
  }
  ETAT.carte = L.map("map", {attributionControl: false, zoomControl: true});
  ETAT.carte.setView([0, 0], 2);
  ETAT.couchesFond = L.layerGroup().addTo(ETAT.carte);
  ETAT.couchesPlan = L.layerGroup().addTo(ETAT.carte);
  ETAT.couchesActeurs = L.layerGroup().addTo(ETAT.carte);
  ETAT.couchesSignalements = L.layerGroup().addTo(ETAT.carte);
  if (ETAT.fond.zones && Array.isArray(ETAT.fond.zones.features)) {
    L.geoJSON(ETAT.fond.zones, {
      style: {color: "#007a38", weight: 2, fillColor: "#e6f4eb", fillOpacity: 0.45},
    }).addTo(ETAT.couchesFond);
  }
  if (ETAT.fond.eau && Array.isArray(ETAT.fond.eau.features) && ETAT.fond.eau.features.length) {
    L.geoJSON(ETAT.fond.eau, {
      style: {color: "#155e75", weight: 1, fillColor: "#dcecf5", fillOpacity: 0.6},
    }).addTo(ETAT.couchesFond);
  }
}

function centrePlan(plan) {
  const points = (plan?.collection_points || []).filter((point) =>
    Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lon)));
  if (!points.length) return null;
  return [
    points.reduce((total, point) => total + Number(point.lat), 0) / points.length,
    points.reduce((total, point) => total + Number(point.lon), 0) / points.length,
  ];
}

function majCartePlan(plan) {
  if (!ETAT.couchesPlan) return;
  ETAT.couchesPlan.clearLayers();
  const pointsById = new Map();
  const limites = [];
  for (const point of plan.collection_points || []) {
    if (!Number.isFinite(Number(point.lat)) || !Number.isFinite(Number(point.lon))) continue;
    pointsById.set(String(point.id), point);
    limites.push([Number(point.lat), Number(point.lon)]);
    const depotoir = point.type === "dumpsite";
    L.circleMarker([Number(point.lat), Number(point.lon)], {
      radius: depotoir ? 6 : 8,
      color: depotoir ? "#701519" : "#064e2b",
      weight: 1,
      fillColor: depotoir ? COULEURS.depotoir : COULEURS.tricycle,
      fillOpacity: 1,
    }).addTo(ETAT.couchesPlan).bindPopup(
      "<b>" + texte(point.id) + "</b><br>" +
      (depotoir ? "Dépotoir du plan" : "Point de regroupement") + "<br>" +
      texte(point.demand_kg) + " kg — données du plan");
  }
  for (const route of plan.routes || []) {
    const geometry = route.geometry;
    if (geometry?.type === "LineString" && Array.isArray(geometry.coordinates)) {
      const positions = geometry.coordinates
        .filter((coordonnee) => Array.isArray(coordonnee) && coordonnee.length >= 2)
        .map(([lon, lat]) => [Number(lat), Number(lon)]);
      if (positions.length) {
        positions.forEach((position) => limites.push(position));
        L.polyline(positions, {
          color: route.type === "truck" ? COULEURS.truck : COULEURS.tricycle,
          weight: route.type === "truck" ? 4 : 3,
          opacity: 0.85,
        }).addTo(ETAT.couchesPlan).bindPopup(
          texte(route.vehicle) + " · " + texte(route.distance_km) + " km — tournée du plan");
      }
    }
    for (const identifiant of route.stops || []) {
      const point = pointsById.get(String(identifiant));
      if (point && Number.isFinite(Number(point.lat))) {
        L.circleMarker([Number(point.lat), Number(point.lon)], {
          radius: 4, fillColor: COULEURS.truck, color: "#fff", weight: 1,
        }).addTo(ETAT.couchesPlan);
      }
    }
  }
  if (limites.length && ETAT.carte) {
    ETAT.carte.fitBounds(L.latLngBounds(limites), {padding: [16, 16]});
  } else if (ETAT.carte) {
    ETAT.carte.setView([0, 0], 2);
  }
  dessinerLegende(ETAT.resultat);
}

function majCarteActeurs(resultat) {
  if (!ETAT.couchesActeurs) return;
  ETAT.couchesActeurs.clearLayers();
  const etat = Array.isArray(resultat.agent_states) ? resultat.agent_states.at(-1) : null;
  const plan = ETAT.plan || {};
  const routes = Array.isArray(plan.routes) ? plan.routes : [];
  for (const foyer of etat?.menages?.positions || []) {
    if (!Number.isFinite(Number(foyer.lat)) || !Number.isFinite(Number(foyer.lon))) continue;
    const plein = foyer.propre === false;
    L.circleMarker([Number(foyer.lat), Number(foyer.lon)], {
      radius: plein ? 6 : 5,
      color: plein ? "#5c4700" : "#33404c",
      weight: 1,
      fillColor: plein ? "#fcd116" : "#9aa3ab",
      fillOpacity: 1,
    }).addTo(ETAT.couchesActeurs).bindPopup(
      "<b>" + texte(foyer.id) + "</b><br>" +
      (plein ? "dépôt sauvage simulé" : "dépôt au point de regroupement simulé"));
  }
  const camions = routes.filter((route) => route.type === "truck")
    .slice(0, etat?.mairie?.camions_en_service ?? 0);
  const tricycles = routes.filter((route) => route.type === "tricycle")
    .slice(0, etat?.pre_collecteurs?.en_service ?? 0);
  for (const route of camions) {
    const pos = milieuRoute(route);
    if (pos) L.marker(pos, {icon: iconeDiv("camion-benne", COULEURS.truck)})
      .addTo(ETAT.couchesActeurs).bindPopup("<b>Camion simulé</b><br>" + texte(route.vehicle));
  }
  for (const route of tricycles) {
    const pos = milieuRoute(route);
    if (pos) L.marker(pos, {icon: iconeDiv("tricycle", COULEURS.tricycle)})
      .addTo(ETAT.couchesActeurs).bindPopup("<b>Tricycle simulé</b><br>" + texte(route.vehicle));
  }
  const rayon = Number(etat?.brigade?.rayon_m);
  const centre = centrePlan(plan);
  if (Number.isFinite(rayon) && rayon > 0 && centre) {
    L.circle(centre, {
      radius: rayon, color: COULEURS.tricycle, weight: 1.5,
      fillColor: COULEURS.tricycle, fillOpacity: 0.12,
    }).addTo(ETAT.couchesActeurs).bindPopup(
      "<b>Brigade Laabal</b><br>rayon " + nombreFr(rayon, 0) + " m — hypothèse à valider");
  }
  if (routes.length) {
    const premiere = routes[0].geometry?.coordinates;
    if (Array.isArray(premiere) && premiere.length) {
      L.marker([Number(premiere[0][1]), Number(premiere[0][0])],
        {icon: iconeDiv("ctvd", "#1f2933")})
        .addTo(ETAT.couchesActeurs)
        .bindPopup("<b>Dépot du plan</b><br>premier point de la première tournée");
    }
  }
  dessinerLegende(resultat);
}

function milieuRoute(route) {
  const coordonnees = route.geometry?.coordinates;
  if (!Array.isArray(coordonnees) || !coordonnees.length) return null;
  const point = coordonnees[Math.floor(coordonnees.length / 2)];
  if (!Array.isArray(point) || point.length < 2) return null;
  return [Number(point[1]), Number(point[0])];
}

function dessinerLegende(resultat) {
  const rayon = Number(resultat?.agent_states?.at(-1)?.brigade?.rayon_m);
  $("legende").innerHTML = [
    '<span><i class="tache tache-propre"></i> Ménage propre (simulé)</span>',
    '<span><i class="tache tache-pleine"></i> Dépôt sauvage (simulé)</span>',
    '<span><i class="legende-point"></i> Point de regroupement</span>',
    '<span><i class="legende-depotoir"></i> Dépotoir du plan</span>',
    '<span class="ic-legende">' + iconeHtml("tricycle") + " Tricycle simulé</span>",
    '<span class="ic-legende">' + iconeHtml("camion-benne") + " Camion simulé</span>",
    '<span><i class="trait"></i> Tournée camion du plan</span>',
    '<span><i class="trait trait-tri"></i> Tournée tricycle du plan</span>',
    '<span><i class="zone-brigade"></i> Brigade' +
      (Number.isFinite(rayon) && rayon > 0 ? " — rayon " + nombreFr(rayon, 0) + " m (hypothèse)" : "") + "</span>",
    '<span><i class="marqueur-signal signal-accepte"><i class="forme"></i></i> Signalement accepté</span>',
    '<span><i class="marqueur-signal signal-rejete"><i class="forme"></i></i> Signalement rejeté</span>',
    '<span><i class="marqueur-signal signal-a_verifier"><i class="forme"></i></i> À vérifier (brigade)</span>',
  ].join("");
}

/* ---------- Signalements : polling 5 s, couche séparée, validation brigade ---------- */
function demarrerPolling() {
  if (ETAT.polling) return;
  ETAT.polling = window.setInterval(() => {
    if (!document.hidden) chargerSignalements({silencieux: true});
  }, 5000);
}

function arreterPolling() {
  if (ETAT.polling) {
    window.clearInterval(ETAT.polling);
    ETAT.polling = null;
  }
}

async function chargerSignalements(options = {}) {
  const initial = Boolean(options.initial);
  const silencieux = Boolean(options.silencieux);
  try {
    const signalements = await api("/api/reports?limit=5000");
    const nouveaux = initial ? []
      : signalements.filter((signalement) => !ETAT.idsSignalements.has(String(signalement.id)));
    ETAT.signalements = Array.isArray(signalements) ? signalements : [];
    ETAT.idsSignalements = new Set(ETAT.signalements.map((signalement) => String(signalement.id)));
    majCarteSignalements();
    majStatsSignalements();
    if (!silencieux && nouveaux.length) annoncerNouveaux(nouveaux.length);
  } catch (error) {
    showError(error, true);
  }
}

function annoncerNouveaux(nombre) {
  const element = $("nouveauxSignalements");
  element.hidden = false;
  element.textContent = nombre + " nouveau(x) signalement(s) détecté(s).";
  if (ETAT.alerteSignalements) window.clearTimeout(ETAT.alerteSignalements);
  ETAT.alerteSignalements = window.setTimeout(() => { element.hidden = true; }, 3000);
}

function majCarteSignalements() {
  if (!ETAT.couchesSignalements) return;
  ETAT.couchesSignalements.clearLayers();
  for (const signalement of ETAT.signalements) {
    const lat = Number(signalement.lat);
    const lon = Number(signalement.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    const statut = CLASSES_STATUT[signalement.status] ? signalement.status : "a_verifier";
    const source = signalement.source === "simule" ? "signal-simule" : "signal-reel";
    const icon = L.divIcon({
      className: "marqueur-signal " + CLASSES_STATUT[statut] + " " + source,
      html: '<span class="forme"></span>',
      iconSize: [36, 36],
      iconAnchor: [18, 18],
      popupAnchor: [0, -14],
    });
    L.marker([lat, lon], {icon}).addTo(ETAT.couchesSignalements)
      .bindPopup(contenuPopupSignalement(signalement));
  }
}

function contenuPopupSignalement(signalement) {
  const conteneur = document.createElement("div");
  conteneur.className = "popup-signal";
  const titre = document.createElement("b");
  titre.textContent = String(signalement.id);
  const details = document.createElement("div");
  details.textContent = "Statut : " + String(signalement.status) +
    " — motif : " + String(signalement.reason || "non précisé") +
    " — source : " + (signalement.source === "simule" ? "simulée" : "réelle");
  conteneur.append(titre, details);
  if (signalement.status === "a_verifier") {
    const rangee = document.createElement("div");
    rangee.className = "rangee";
    for (const accept of [true, false]) {
      const bouton = document.createElement("button");
      bouton.type = "button";
      bouton.className = "btn " + (accept ? "btn-vert" : "btn-rouge");
      bouton.textContent = accept ? "Valider" : "Rejeter";
      bouton.addEventListener("click", () => validerSignalement(signalement.id, accept));
      rangee.append(bouton);
    }
    conteneur.append(rangee);
  }
  return conteneur;
}

function majStatsSignalements() {
  const comptes = {accepte: 0, rejete: 0, a_verifier: 0};
  for (const signalement of ETAT.signalements) {
    if (comptes[signalement.status] !== undefined) comptes[signalement.status] += 1;
  }
  const aVerifier = ETAT.signalements.filter((signalement) => signalement.status === "a_verifier");
  const lignes = aVerifier.slice(0, 8).map((signalement) =>
    '<div class="ligne-signalement"><span>' + texte(signalement.id) + " — " +
    texte(signalement.reason || "à vérifier") + "</span><span>" +
    '<button type="button" class="btn btn-vert" data-signal-id="' + texte(signalement.id) +
    '" data-accept="true">Valider</button> ' +
    '<button type="button" class="btn btn-rouge" data-signal-id="' + texte(signalement.id) +
    '" data-accept="false">Rejeter</button></span></div>').join("");
  $("statsSig").innerHTML =
    "<p>" + comptes.accepte + " acceptés · " + comptes.rejete + " rejetés · " +
    comptes.a_verifier + " à vérifier</p>" +
    (lignes || '<p class="muted">Aucun signalement à vérifier.</p>');
  $("statsSig").querySelectorAll("button[data-signal-id]").forEach((bouton) => {
    bouton.addEventListener("click", () =>
      validerSignalement(bouton.getAttribute("data-signal-id"), bouton.getAttribute("data-accept") === "true"));
  });

  const datePlan = ETAT.plan?.computed_at ? Date.parse(ETAT.plan.computed_at) : NaN;
  const tardifs = Number.isFinite(datePlan)
    ? ETAT.signalements.filter((signalement) => signalement.status === "accepte" &&
        signalement.received_at && Date.parse(signalement.received_at) > datePlan)
    : [];
  $("propositionRecalcul").hidden = tardifs.length === 0;
}

async function validerSignalement(id, accept) {
  const note = accept ? "" : window.prompt("Motif du rejet (obligatoire) :", "");
  if (!accept && (!note || !note.trim())) {
    showError(new Error("Le motif du rejet est obligatoire."));
    return;
  }
  try {
    const resultat = await api(`/api/reports/${encodeURIComponent(id)}/validate`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({by: "brigade", accept: Boolean(accept), note: note.trim()}),
    });
    if (!resultat.updated) throw new Error("Signalement introuvable ou déjà traité.");
    const bandeau = $("bandeau");
    bandeau.hidden = false;
    bandeau.textContent = accept
      ? "Signalement validé par la brigade (décision enregistrée)."
      : "Signalement rejeté par la brigade (motif enregistré).";
    await chargerSignalements({silencieux: true});
  } catch (error) {
    showError(error, true);
  }
}

async function injecterPieges() {
  const points = (ETAT.plan?.collection_points || []).filter((point) =>
    Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lon)));
  if (!points.length) return showError(new Error("Calculez d'abord un plan pour injecter des cas de test."));
  const maintenant = new Date().toISOString();
  const rapports = points.slice(0, 4).map((point, index) => ({
    id: "test-" + Date.now() + "-" + index,
    lat: Number(point.lat),
    lon: Number(point.lon),
    size: "moyen",
    reported_at: maintenant,
    source: "simule",
  }));
  try {
    const resultat = await api("/api/reports/bulk", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(rapports),
    });
    const comptes = resultat.stats.par_statut || {};
    alert("Traitement réel : " + (comptes.accepte || 0) + " acceptés, " +
      (comptes.rejete || 0) + " rejetés, " + (comptes.a_verifier || 0) + " à vérifier.");
    await chargerSignalements({silencieux: true});
  } catch (error) {
    showError(error, true);
  }
}

/* ---------- Actions Backend conservées ---------- */
async function crise(id) {
  ETAT.crises.add(id);
  await recalculer();
}

async function resetCrises() {
  ETAT.crises.clear();
  await recalculer();
}

function figer(lettre) {
  if (!ETAT.plan) return showError(new Error("Calculez d'abord un plan."));
  if (lettre === "A") ETAT.planA = ETAT.plan; else ETAT.planB = ETAT.plan;
  majAB();
}

function majAB() {
  const element = $("ab");
  element.replaceChildren();
  for (const [lettre, plan] of [["A", ETAT.planA], ["B", ETAT.planB]]) {
    const carte = document.createElement("div");
    carte.className = "card";
    carte.textContent = plan
      ? lettre + " · " + plan.plan_id + " · " +
        nombreFr(Number(plan.totals.cost || 0) / 1e6, 2) + " M FCFA · " +
        texte(plan.totals.uncollected_kg) + " kg non collectés"
      : lettre + " · non figé";
    element.append(carte);
  }
  if (ETAT.planA && ETAT.planB) {
    $("diff").textContent = "B − A : " +
      nombreFr((ETAT.planB.totals.cost - ETAT.planA.totals.cost) / 1e6, 2) + " M FCFA · " +
      nombreFr(ETAT.planB.totals.uncollected_kg - ETAT.planA.totals.uncollected_kg, 1) +
      " kg non collectés";
  }
}

async function exportOsm() {
  if (!ETAT.plan) return showError(new Error("Calculez d'abord un plan."));
  try {
    const reponse = await fetch(`${API}/api/plans/${encodeURIComponent(ETAT.plan.plan_id)}/export`);
    if (!reponse.ok) throw new Error("Export impossible (HTTP " + reponse.status + ").");
    const blob = await reponse.blob();
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(blob);
    lien.download = "plan-" + ETAT.plan.plan_id + ".geojson";
    lien.click();
    URL.revokeObjectURL(lien.href);
  } catch (error) {
    showError(error, true);
  }
}

function validerPlan() {
  if (!ETAT.plan) return showError(new Error("Aucun plan calculé."));
  const echoues = Object.entries(ETAT.plan.checks || {})
    .filter(([cle, valeur]) => cle !== "messages" && valeur !== true);
  if (echoues.length) {
    alert("Plan non cohérent : " +
      ((ETAT.plan.checks.messages || []).join(" ") || echoues.map(([cle]) => cle).join(", ")));
    return;
  }
  alert("Contrôles du plan " + ETAT.plan.plan_id +
    " validés. Cette vérification n'enregistre pas une décision municipale.");
}

/* ---------- Initialisation ---------- */
function brancherEvenements() {
  for (const id of ["pop", "abo", "cam", "tri", "fc", "bud"]) {
    $(id).addEventListener("input", majLabels);
  }
  $("recalculerPropose").addEventListener("click", () => recalculer());
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) arreterPolling();
    else {
      demarrerPolling();
      chargerSignalements({silencieux: true});
    }
  });
}

async function initialiser() {
  brancherEvenements();
  rendreFiltresJournal();
  await chargerIcones();
  await chargerFonds();
  initialiserCarte();
  demarrerPolling();
  await recalculer({initial: true});
  await chargerSignalements({initial: true});
}

initialiser();
