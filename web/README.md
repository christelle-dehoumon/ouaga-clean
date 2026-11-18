# Front Ouaga Clean (web/)

HTML, CSS et JavaScript natifs (modules ES), sans framework ni étape de construction. Contrat d'API : `docs/api.md`.

| Page | Adresse | Public |
|---|---|---|
| Signalement citoyen | `/citizen/` | téléphone, sans compte |
| Brigade Laabal | `/brigade/` | téléphone, code brigade |
| Mairie, ville 3D | `/dashboard/ville/` | ordinateur (1280 px et plus), code mairie |
| Ancien tableau de bord | `/dashboard/` | conservé tel quel (voir « Dépendances côté serveur ») |

Démarrage : `./scripts/run.sh`, puis `https://<ip>:8443/dashboard/ville/`. Codes de démonstration : `mairie-demo`,
`brigade-demo` (définir `MAIRIE_CODE` et `BRIGADE_CODE` en vrai déploiement). Le code est gardé pour la session de
l'onglet ; ce n'est pas une sécurité : le serveur vérifie chaque appel.

Mode démonstration : ajouter `?mock=1` à n'importe quelle page. Les données sont FICTIVES et un bandeau permanent
l'indique. Ce mode ne s'active jamais tout seul : une route absente ou en erreur affiche une erreur visible.

## Organisation

```text
web/
  citizen/          index.html, citizen.css, citizen.js, sw.js (service worker : la page s'ouvre sans réseau)
  brigade/          index.html, brigade.css, brigade.js
  dashboard/
    shared/         api.js (appels, délais, erreurs, code de rôle), mock.js (?mock=1), store.js (IndexedDB), ui.js, shared.css
    ville/          index.html, ville.css, app.js (état, modes, panneaux), status.js, compare.js (A/B, historique),
                    view3d.js (vue 3D), view2d.js (vue 2D de secours), data/city.json
      map3d/        scene.js, camera.js, city.js, layers.js, vehicles.js, interactions.js, effects.js, geo.js
    vendor/         leaflet/ (BSD-2), three/ (Three.js r170 + OrbitControls, MIT)
  tools/            build_city_data.py (données de la ville 3D), e2e/ (tests de bout en bout Playwright)
```

`web/shared/` n'est pas servi par l'API (seuls `/citizen`, `/brigade` et `/dashboard` sont montés) : le code commun vit
donc dans `/dashboard/shared/` et les trois pages l'importent par chemin absolu.

## La ville 3D

- Emprises des 49 738 bâtiments, tracés et revêtement des 12 408 tronçons de route, plans d'eau : OpenStreetMap
  (© contributeurs OpenStreetMap, ODbL), lus dans les données déjà préparées du dépôt par
  `.venv/bin/python web/tools/build_city_data.py [--cache-dir …]` (rien n'est téléchargé à l'affichage).
- Hauteurs : balise OSM quand elle existe (27 bâtiments), sinon ESTIMÉES (1 à 3 niveaux, déterministe). Arbres :
  ILLUSTRATIFS, pas des données. Quartiers : emprises approximatives. Le bandeau de crédit et l'aide le disent.
- Couverture : le secteur pilote (5 km) et les quartiers téléchargés ; le reste de Ouagadougou n'est pas modélisé.
- Tout ce qui est opérationnel vient de l'API : signalements à leurs coordonnées, points et tournées du plan calculé,
  camions de `plan.vehicles` animés le long de `plan.routes[].path` (vitesse accélérée, indiquée), points non
  desservis et reportés, routes coupées par leur identifiant d'arête.
- Navigation : orbite (glisser), déplacement (clic droit), zoom (molette), vues Dessus / Immersive / Rue / Recentrer,
  vol vers un quartier ou un incident. La vue Rue se pilote aux flèches ou Z Q S D.
- Sans WebGL (ou avec `?vue=2d`) : vue 2D de secours Leaflet, annoncée par un bandeau, tuiles OpenStreetMap en ligne
  avec attribution.

## Démonstration (3 minutes)

1. **Découvrir la ville (0:00–0:35)** : ouvrir `/dashboard/ville/`, Immersive, faire tourner la ville, cliquer un
   quartier puis un signalement (fiche, photo floutée, historique).
2. **Plan initial (0:35–1:05)** : passer en Simulation (bandeau jaune) ; le plan se calcule ; points verts, tournées
   colorées, camions qui roulent ; « Comparer A/B » → « Fixer le plan affiché comme A ».
3. **Panne (1:05–1:40)** : cliquer un camion → « Déclarer en panne » ; le camion s'arrête, feux allumés ; statut
   « Plan partiellement réalisable — N arrêt(s) reporté(s) », recalcul partiel, temps serveur affiché en haut.
4. **Pluie (1:40–2:10)** : « Déclencher la saison des pluies » ; pluie dans la ville ; points non desservis en rouge.
5. **Nouveau quartier (2:10–2:40)** : choisir Kalgodin → « Ajouter au scénario » ; la caméra y vole, nouveaux points.
6. **Décider (2:40–3:00)** : « Fixer le plan affiché comme B » → « Comparer A et B » : écarts et compromis.

Avant la démonstration : `./scripts/reset_db.sh` (vide sim.db, recharge le jeu factice) puis ouvrir la page une fois.

## Tests

- `pytest` (racine) : 134 tests du serveur, dont `tests/test_c_dashboard.py` qui fige l'ancien tableau de bord.
- `web/tools/e2e/*.py` : parcours dans Chromium (Playwright, à installer à part), sur un serveur lancé avec des bases
  temporaires (`REEL_DB`, `SIM_DB`, `PHOTO_DIR`) : citoyen (en ligne, hors ligne, synchronisation, GPS refusé),
  brigade (code, décision, hors ligne, conflit 409), mairie (24 vérifications), vue 2D, mode démonstration, couche API.

## Dépendances côté serveur (non modifié : seul web/ était ouvert)

1. `tests/test_c_dashboard.py` fige l'ancien `/dashboard/` (routes `/validate` et `/bulk` supprimées de l'API, motif de
   rejet obligatoire, aucune URL externe) : la nouvelle interface est donc servie sous `/dashboard/ville/`. Pour en
   faire la page par défaut, il faut mettre à jour ce test (ou monter `/mairie`).
2. Pas de `GET` des dépotoirs simulés ni des routes coupées : la liste est reconstruite à partir des réponses
   (`active_cuts`, `plan.cut_roads`, points `dumpsite` du plan).
3. `POST /api/reports` n'a pas de clé d'idempotence : si une réponse se perd (délai dépassé), un nouvel envoi
   automatique peut renforcer le même dépotoir (signalé N + 1 fois) au lieu de créer un doublon.
4. Les bâtiments, routes et limites de quartiers ne sont pas exposés par l'API : `city.json` est généré depuis
   `data/` et doit être régénéré si ces données changent.
5. Pas de position des camions côté serveur : un camion en panne s'arrête là où l'animation le montrait.
6. `README.md` et `docs/` (hors web/) citent encore `/dashboard/` comme tableau de bord.
