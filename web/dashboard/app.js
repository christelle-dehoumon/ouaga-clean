/* Tableau de bord local — aucune ressource externe, aucun chiffre pré-calculé.
 * Toutes les données affichées viennent de /api/bootstrap (data/mock + config)
 * ou de /api/simulation (core.sim.run_scenario), étiquetées « simulé ».
 */
'use strict';

const NOMS_ICONS = ['tricycle', 'camion-benne', 'brigade', 'menage', 'point-regroupement', 'ctvd'];

const ETAT = {
  bootstrap: null,
  resultat: null,
  actifs: {},
  icons: {},
  map: null,
  couches: null,
  couchesFond: null,
  filtre: 'tous',
  occupe: false,
};

const CARTES_ACTEURS = [
  {
    cle: 'menages', nom: 'Ménages', icone: 'menage', role: 'Produisent les déchets et choisissent où les déposer.',
    chiffres: r => [
      ['Abonnés', (r.indicateurs?.menages?.abonnes_pct ?? '—') + ' %'],
      ['Dépôts créés', r.indicateurs?.menages?.depotoirs_crees ?? '—'],
    ],
  },
  {
    cle: 'pre_collecteurs', nom: 'Pré-collecteurs', icone: 'tricycle', role: 'Ramassent les dépôts en tricycle vers les points de regroupement.',
    chiffres: r => [
      ['Ramassé', (r.indicateurs?.pre_collecteurs?.tonnes_ramassees ?? '—') + ' t'],
      ['Remplissage', (r.indicateurs?.pre_collecteurs?.remplissage_moyen ?? '—')],
    ],
  },
  {
    cle: 'brigade', nom: 'Brigade Laabal', icone: 'brigade', role: 'Patrouille et sensibilise les ménages dans son rayon.',
    chiffres: r => [
      ['Patrouilles', r.indicateurs?.brigade?.patrouilles_actives ?? '—'],
      ['Dépôts évités', r.indicateurs?.brigade?.depots_evites ?? '—'],
    ],
  },
  {
    cle: 'mairie', nom: 'Mairie', icone: 'camion-benne', role: 'Organise les camions, paie la collecte et suit le budget.',
    chiffres: r => [
      ['Budget restant', (r.indicateurs?.mairie?.budget_restant_m_fcfa ?? '—') + ' M'],
      ['Camions actifs', (r.indicateurs?.mairie?.camions_en_service ?? '—') + ' / ' + (r.indicateurs?.mairie?.camions_total ?? '—')],
    ],
  },
];

const NOMS_ACTEURS_FR = {
  menages: 'Ménages',
  pre_collecteurs: 'Pré-collecteurs',
  brigade: 'Brigade',
  mairie: 'Mairie',
};

function $(id) { return document.getElementById(id); }

function texte(valeur) {
  return String(valeur ?? '—').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

function nombreFr(valeur, digits = 1) {
  if (valeur === null || valeur === undefined || valeur === '—') return '—';
  return Number(valeur).toLocaleString('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function bandeau(message, estAncien) {
  const el = $('bandeau');
  if (!message) { el.hidden = true; el.textContent = ''; return; }
  el.hidden = false;
  el.textContent = (estAncien ? 'Donnée ancienne — ' : '') + message;
}

/* ---------- Icônes SVG locales ---------- */
async function chargerIcones() {
  await Promise.all(NOMS_ICONS.map(async nom => {
    try {
      const reponse = await fetch('icons/' + nom + '.svg');
      if (!reponse.ok) throw new Error('svg ' + reponse.status);
      const texteSvg = await reponse.text();
      const doc = new DOMParser().parseFromString(texteSvg, 'image/svg+xml');
      ETAT.icons[nom] = Array.from(doc.documentElement.children)
        .map(n => new XMLSerializer().serializeToString(n)).join('');
    } catch (e) {
      ETAT.icons[nom] = '';
    }
  }));
  document.querySelectorAll('[data-icon]').forEach(el => {
    const nom = el.getAttribute('data-icon');
    if (ETAT.icons[nom]) {
      el.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + ETAT.icons[nom] + '</svg>';
    }
  });
}

function iconeHtml(nom) {
  return '<span class="ic" aria-hidden="true"><svg viewBox="0 0 24 24">' + (ETAT.icons[nom] || '') + '</svg></span>';
}

function iconeDiv(nom, couleur) {
  return L.divIcon({
    className: 'icone-carte',
    html: '<div style="color:' + couleur + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + (ETAT.icons[nom] || '') + '</svg></div>',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -12],
  });
}

/* ---------- Paramètres ---------- */
function initialiserParametres(config, defauts) {
  const p = config && typeof config === 'object' ? config : {};
  const d = defauts && typeof defauts === 'object' ? defauts : {};
  const bornes = {
    'p-population': [500000, 5000000], 'p-abonnement': [10, 90],
    'p-trucks': [0, 30], 'p-tricycles': [0, 60], 'p-budget': [1000000, 50000000],
  };
  const valeurs = {
    'p-population': p.population, 'p-abonnement': p.subscription_rate !== undefined ? p.subscription_rate * 100 : undefined,
    'p-trucks': p.trucks, 'p-tricycles': p.tricycles, 'p-budget': p.budget,
  };
  for (const [id, [mini, maxi]] of Object.entries(bornes)) {
    const input = $(id);
    const brut = valeurs[id];
    const nombre = Number(brut);
    input.value = Number.isFinite(nombre) ? Math.min(maxi, Math.max(mini, nombre)) : mini;
  }
  $('p-jours').value = Number.isFinite(Number(d.days)) ? d.days : 7;
  $('p-graine').value = Number.isFinite(Number(d.seed)) ? d.seed : 42;
  $('p-pluie').checked = Boolean(p.rainy_season);
  majLabels();
}

function majLabels() {
  $('v-jours').textContent = $('p-jours').value;
  $('v-population').textContent = Number($('p-population').value).toLocaleString('fr-FR');
  $('v-abonnement').textContent = $('p-abonnement').value + ' %';
  $('v-trucks').textContent = $('p-trucks').value;
  $('v-tricycles').textContent = $('p-tricycles').value;
  $('v-budget').textContent = nombreFr(Number($('p-budget').value) / 1e6, 1) + ' M';
}

function paramsActuels() {
  return {
    population: Number($('p-population').value),
    subscription_rate: Number($('p-abonnement').value) / 100,
    trucks: Number($('p-trucks').value),
    tricycles: Number($('p-tricycles').value),
    budget: Number($('p-budget').value),
    rainy_season: $('p-pluie').checked,
    seed: Number($('p-graine').value),
  };
}

/* ---------- Simulation ---------- */
async function simuler() {
  if (ETAT.occupe) return;
  ETAT.occupe = true;
  $('btn-recalculer').disabled = true;
  try {
    const reponse = await fetch('api/simulation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        params: paramsActuels(),
        days: Number($('p-jours').value),
        actors_enabled: ETAT.actifs,
      }),
    });
    const donnees = await reponse.json();
    if (!reponse.ok && !donnees.series) throw new Error(donnees.erreur || ('HTTP ' + reponse.status));
    ETAT.resultat = donnees;
    if (donnees.data_status === 'ancien' || donnees.erreur) {
      bandeau(donnees.erreur || 'Serveur de simulation indisponible.', true);
      $('etat-reseau').textContent = 'état ancien affiché';
    } else {
      bandeau('');
      $('etat-reseau').textContent = 'hors ligne · données mock';
    }
    afficherResultat(donnees);
  } catch (e) {
    // Aucun chiffre inventé : on conserve le dernier état valide, marqué « ancien ».
    bandeau(e.message || 'Serveur indisponible : dernier état valide conservé.', true);
    $('etat-reseau').textContent = 'état ancien affiché';
    if (ETAT.resultat) afficherResultat(ETAT.resultat);
  } finally {
    ETAT.occupe = false;
    $('btn-recalculer').disabled = false;
  }
}

function afficherResultat(r) {
  $('k-part').textContent = r.part_ramassee === null || r.part_ramassee === undefined
    ? '—' : nombreFr(r.part_ramassee * 100, 1) + ' %';
  $('k-cout').textContent = r.cout_m_fcfa === null || r.cout_m_fcfa === undefined
    ? '—' : nombreFr(r.cout_m_fcfa, 2) + ' M FCFA';
  $('k-depots').textContent = r.depotoirs_restants === null || r.depotoirs_restants === undefined
    ? '—' : String(r.depotoirs_restants);
  $('k-depots').title = r.unite_depotoirs_restants || 'proxy : ménages synthétiques';
  rendreActeurs(r);
  rendreJournal(r);
  rendreSeries(r);
  rendreHypotheses(r);
  majCarteActeurs(r);
}

/* ---------- Panneau des acteurs ---------- */
function rendreActeurs(r) {
  const conteneur = $('acteurs');
  conteneur.innerHTML = CARTES_ACTEURS.map(carte => {
    const actif = ETAT.actifs[carte.cle] !== false;
    const chiffres = carte.chiffres(r).map(([label, valeur]) =>
      '<div class="acteur-chiffre"><span>' + texte(label) + '</span><b>' + texte(valeur) + '</b></div>').join('');
    return '<article class="acteur' + (actif ? '' : ' desactive') + '">' +
      '<div class="acteur-entete"><span class="acteur-ic">' + iconeHtml(carte.icone) + '</span>' +
      '<div><div class="acteur-nom">' + texte(carte.nom) + '</div>' +
      '<div class="acteur-etat">' + (actif ? 'actif' : 'retiré du scénario') + '</div></div></div>' +
      '<p class="aide" style="margin:8px 0 0">' + texte(carte.role) + '</p>' +
      '<div class="acteur-chiffres">' + chiffres + '</div>' +
      '<button type="button" class="btn ' + (actif ? 'btn-retirer' : 'btn-restaurer') + '" ' +
      'data-acteur="' + carte.cle + '" aria-label="' + (actif ? 'Retirer ' : 'Rétablir ') + texte(carte.nom) + '">' +
      (actif ? 'Retirer cet acteur' : 'Rétablir cet acteur') + '</button></article>';
  }).join('');
  conteneur.querySelectorAll('button[data-acteur]').forEach(btn => {
    btn.addEventListener('click', () => {
      const cle = btn.getAttribute('data-acteur');
      ETAT.actifs[cle] = ETAT.actifs[cle] === false;
      simuler();
    });
  });
}

/* ---------- Journal ---------- */
function rendreJournal(r) {
  const evenements = Array.isArray(r.events) ? r.events : [];
  const visibles = ETAT.filtre === 'tous' ? evenements : evenements.filter(e => e.acteur === ETAT.filtre);
  $('journal').innerHTML = visibles.length
    ? visibles.map(e => '<li data-acteur="' + texte(e.acteur) + '">' +
        '<span class="jour">J ' + texte(e.jour) + '</span><span><span class="qui">' +
        texte(NOMS_ACTEURS_FR[e.acteur] || e.acteur) + '</span><br>' + texte(e.texte) + '</span></li>').join('')
    : '<li class="vide">Aucun événement pour ce filtre.</li>';
}

/* ---------- Séries (dessinées à partir des vraies valeurs) ---------- */
function rendreSeries(r) {
  const canvas = $('series');
  const ctx = canvas.getContext('2d');
  const largeur = canvas.width, hauteur = canvas.height;
  ctx.clearRect(0, 0, largeur, hauteur);
  const series = Array.isArray(r.series) ? r.series : [];
  if (!series.length) return;
  const marge = 34;
  const courbes = [
    { cle: 'part_ramassee', couleur: '#2f6b4f', max: 1 },
    { cle: 'cout_m_fcfa', couleur: '#a4302a' },
    { cle: 'depotoirs_restants', couleur: '#1d6c8c' },
  ];
  for (const courbe of courbes) {
    const valeurs = series.map(s => Number(s[courbe.cle]));
    const max = courbe.max ?? Math.max(...valeurs, 1);
    ctx.strokeStyle = courbe.couleur;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    valeurs.forEach((v, i) => {
      const x = marge + i * (largeur - marge - 12) / Math.max(1, valeurs.length - 1);
      const y = hauteur - 22 - (v / max) * (hauteur - 40);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
  ctx.font = '12px system-ui, sans-serif';
  ctx.fillStyle = '#52606d';
  ctx.fillText('J1', 4, hauteur - 6);
  ctx.fillText('J' + series.length, largeur - 34, hauteur - 6);
  let x = marge;
  for (const courbe of courbes) {
    ctx.fillStyle = courbe.couleur;
    ctx.fillRect(x, 10, 12, 4);
    ctx.fillStyle = '#1f2933';
    ctx.fillText(courbe.cle.replace('_', ' '), x + 17, 15);
    x += 165;
  }
}

/* ---------- Hypothèses ---------- */
function rendreHypotheses(r) {
  const liste = Array.isArray(r.hypotheses) ? r.hypotheses : [];
  $('hypotheses').innerHTML = liste.length
    ? liste.map(h => '<div class="hypothese"><b>' + texte(h.cle) + ' = ' + texte(h.valeur) + '</b>' +
        '<div class="source">source : ' + texte(h.source) + '</div>' +
        '<div class="note">' + texte(h.note) + '</div></div>').join('')
    : '<p class="aide">Aucune hypothèse déclarée.</p>';
}

/* ---------- Carte locale (fond GeoJSON, aucune tuile) ---------- */
function initialiserCarte(bootstrap) {
  try {
    const centre = bootstrap.centre;
    if (!Array.isArray(centre)) throw new Error('emprise indisponible dans la configuration');
    ETAT.map = L.map('map', { zoomControl: true, attributionControl: false });
    ETAT.map.setView(centre, 11);
    ETAT.couchesFond = L.layerGroup().addTo(ETAT.map);
    ETAT.couches = L.layerGroup().addTo(ETAT.map);
    dessinerFond(bootstrap);
  } catch (e) {
    $('map').innerHTML = '<p class="aide" style="padding:14px">Carte indisponible : ' + texte(e.message) +
      '. Les chiffres, le journal et les séries restent utilisables.</p>';
  }
}

function dessinerFond(bootstrap) {
  if (!ETAT.couchesFond) return;
  const geojson = bootstrap.zones;
  if (geojson && Array.isArray(geojson.features)) {
    L.geoJSON(geojson, {
      style: { color: '#2f6b4f', weight: 2, fillColor: '#e7f1ea', fillOpacity: .45 },
    }).addTo(ETAT.couchesFond);
  }
  const eau = bootstrap.water;
  if (eau && Array.isArray(eau.features) && eau.features.length) {
    L.geoJSON(eau, { style: { color: '#1d6c8c', weight: 1, fillColor: '#dcecf5', fillOpacity: .6 } }).addTo(ETAT.couchesFond);
  }
  const plan = bootstrap.plan || {};
  const routes = Array.isArray(plan.routes) ? plan.routes : [];
  for (const route of routes) {
    const geom = route.geometry;
    if (!geom || !Array.isArray(geom.coordinates) || geom.coordinates.length < 2) continue;
    const latlngs = geom.coordinates.map(c => [c[1], c[0]]);
    const camion = route.type === 'truck';
    L.polyline(latlngs, {
      color: camion ? '#a4302a' : '#2f6b4f',
      weight: camion ? 3.5 : 2.5,
      opacity: .75,
      dashArray: camion ? undefined : '6,6',
    }).addTo(ETAT.couchesFond);
  }
  // Ajuste la vue sur les géométries réellement présentes dans data/mock/.
  const limites = [];
  for (const route of routes) {
    if (route.geometry && Array.isArray(route.geometry.coordinates)) {
      for (const c of route.geometry.coordinates) limites.push([c[1], c[0]]);
    }
  }
  if (limites.length && ETAT.map) ETAT.map.fitBounds(L.latLngBounds(limites), { padding: [16, 16] });
  dessinerLegende(bootstrap);
}

function dessinerLegende(bootstrap) {
  const plan = bootstrap.plan || {};
  const rayon = ETAT.resultat?.agent_states?.at(-1)?.brigade?.rayon_m;
  $('legende').innerHTML = [
    '<span><i class="tache tache-propre"></i> Ménage propre</span>',
    '<span><i class="tache tache-pleine"></i> Poubelle pleine / dépôt</span>',
    '<span><i class="tache tache-depotoir"></i> Dépotoir sauvage</span>',
    '<span class="ic-legende">' + iconeHtml('point-regroupement') + ' Point de regroupement</span>',
    '<span class="ic-legende">' + iconeHtml('tricycle') + ' Tricycle (pointillés)</span>',
    '<span class="ic-legende">' + iconeHtml('camion-benne') + ' Camion (trait plein)</span>',
    '<span><i class="zone-brigade"></i> Brigade ' + (rayon ? '— rayon ' + nombreFr(rayon, 0) + ' m (config)' : '') + '</span>',
    '<span class="ic-legende">' + iconeHtml('ctvd') + ' Centre de traitement</span>',
    '<span><i class="trait"></i> Tournée camion</span>',
    '<span><i class="trait trait-tri"></i> Tournée tricycle</span>',
  ].join('');
}

function milieu(route) {
  const coords = route.geometry && route.geometry.coordinates;
  if (!Array.isArray(coords) || !coords.length) return null;
  const c = coords[Math.floor(coords.length / 2)];
  return [c[1], c[0]];
}

function majCarteActeurs(r) {
  if (!ETAT.couches) return;
  ETAT.couches.clearLayers();
  const bootstrap = ETAT.bootstrap || {};
  const plan = bootstrap.plan || {};
  const etat = Array.isArray(r.agent_states) ? r.agent_states.at(-1) : null;
  const points = Array.isArray(plan.collection_points) ? plan.collection_points : [];

  // Points de regroupement (SVG local).
  for (const p of points.filter(p => p.type === 'center')) {
    if (!Number.isFinite(p.lat) || !Number.isFinite(p.lon)) continue;
    L.marker([p.lat, p.lon], { icon: iconeDiv('point-regroupement', '#2f6b4f') })
      .addTo(ETAT.couches).bindPopup('<b>Point de regroupement</b><br>' + texte(p.id));
  }
  // Dépotoirs sauvages.
  for (const p of points.filter(p => p.type === 'dumpsite')) {
    if (!Number.isFinite(p.lat) || !Number.isFinite(p.lon)) continue;
    L.circleMarker([p.lat, p.lon], { radius: 6, color: '#6d1f1a', weight: 1, fillColor: '#a4302a', fillOpacity: .95 })
      .addTo(ETAT.couches).bindPopup('<b>Dépotoir sauvage</b><br>' + texte(p.id));
  }
  // Ménages synthétiques : gris propres, jaune poubelle pleine (jamais en texte).
  for (const foyer of etat?.menages?.positions || []) {
    const plein = foyer.propre === false;
    L.circleMarker([foyer.lat, foyer.lon], {
      radius: 4.5,
      color: plein ? '#6b5210' : '#33404c',
      weight: 1,
      fillColor: plein ? '#e1b12c' : '#9aa3ab',
      fillOpacity: 1,
    }).addTo(ETAT.couches).bindPopup('<b>' + texte(foyer.id) + '</b><br>' + (plein ? 'dépôt sauvage' : 'dépôt au point de regroupement'));
  }
  // Véhicules aux milieux des tournées du plan (aucune coordonnée inventée).
  const routes = Array.isArray(plan.routes) ? plan.routes : [];
  const camions = routes.filter(x => x.type === 'truck').slice(0, etat?.mairie?.camions_en_service ?? 0);
  const tricycles = routes.filter(x => x.type === 'tricycle').slice(0, etat?.pre_collecteurs?.en_service ?? 0);
  for (const route of camions) {
    const pos = milieu(route);
    if (pos) L.marker(pos, { icon: iconeDiv('camion-benne', '#a4302a') })
      .addTo(ETAT.couches).bindPopup('<b>Camion</b><br>' + texte(route.vehicle));
  }
  for (const route of tricycles) {
    const pos = milieu(route);
    if (pos) L.marker(pos, { icon: iconeDiv('tricycle', '#2f6b4f') })
      .addTo(ETAT.couches).bindPopup('<b>Tricycle</b><br>' + texte(route.vehicle));
  }
  // Rayon de patrouille de la brigade : valeur lue dans la configuration.
  const rayon = etat?.brigade?.rayon_m;
  const centre = bootstrap.centre;
  if (Number.isFinite(rayon) && rayon > 0 && Array.isArray(centre)) {
    L.circle(centre, {
      radius: rayon,
      color: '#2f6b4f', weight: 1.5, fillColor: '#2f6b4f', fillOpacity: .12,
    }).addTo(ETAT.couches).bindPopup('<b>Brigade Laabal</b><br>rayon ' + nombreFr(rayon, 0) + ' m — hypothèse à valider');
  }
  // Centre de traitement : à l'origine de la première tournée du plan.
  if (routes.length && Array.isArray(routes[0].geometry?.coordinates) && routes[0].geometry.coordinates.length) {
    const c = routes[0].geometry.coordinates[0];
    L.marker([c[1], c[0]], { icon: iconeDiv('ctvd', '#1f2933') })
      .addTo(ETAT.couches).bindPopup('<b>Centre de traitement (dépot du plan)</b>');
  }
  dessinerLegende(bootstrap);
}

/* ---------- Initialisation ---------- */
function brancherEvenements() {
  ['p-jours', 'p-population', 'p-abonnement', 'p-trucks', 'p-tricycles', 'p-budget'].forEach(id => {
    $(id).addEventListener('input', majLabels);
  });
  $('btn-recalculer').addEventListener('click', simuler);
  document.querySelectorAll('.filtre').forEach(btn => {
    btn.addEventListener('click', () => {
      ETAT.filtre = btn.getAttribute('data-filtre');
      document.querySelectorAll('.filtre').forEach(b => b.classList.toggle('actif', b === btn));
      if (ETAT.resultat) rendreJournal(ETAT.resultat);
    });
  });
}

async function init() {
  brancherEvenements();
  await chargerIcones();
  try {
    const reponse = await fetch('api/bootstrap');
    if (!reponse.ok) throw new Error('HTTP ' + reponse.status);
    ETAT.bootstrap = await reponse.json();
    ETAT.actifs = Object.assign({}, ETAT.bootstrap.actifs_par_defaut || {});
    $('commune').textContent = ETAT.bootstrap.commune || '—';
    initialiserParametres(ETAT.bootstrap.parametres_config, ETAT.bootstrap.simulation_defauts);
    initialiserCarte(ETAT.bootstrap);
    $('source-donnees').textContent = 'Sources : ' + Object.values(ETAT.bootstrap.sources || {}).join(' · ');
  } catch (e) {
    bandeau('Données de démonstration indisponibles : ' + e.message + '.', true);
    ETAT.actifs = { menages: true, pre_collecteurs: true, brigade: true, mairie: true };
  }
  await simuler();
}

init();
