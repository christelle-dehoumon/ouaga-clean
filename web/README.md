# Front VIELA (web/)

HTML, CSS et JavaScript natifs (modules ES), sans framework ni étape de construction. Contrat d'API : `docs/api.md`.

| Page | Adresse | Public |
|---|---|---|
| Signalement citoyen | `/citizen/` | téléphone, sans compte |
| Brigade Laabal | `/brigade/` | téléphone, code brigade |
| Mairie, carte de la ville | `/dashboard/ville/` (`?vue=ville3d`, `?vue=2d`) | ordinateur (1280 px et plus), code mairie |
| Raccourci | `/dashboard/` | redirige vers `/dashboard/ville/` |

Démarrage : `./scripts/fabriquer_tuiles.sh` une fois après le clonage (obligatoire, Java 21+ ; voir `docs/carte.md`), puis
`./scripts/run.sh` et `https://<ip>:8443/dashboard/` (redirige vers `/dashboard/ville/`). Codes de démonstration : `mairie-demo`,
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
    shared/         api.js (appels, délais, erreurs, code de rôle), mock.js (?mock=1), store.js (IndexedDB), ui.js,
                    design.css (jetons : couleurs, espacements, typographie, mode sombre), shared.css (composants communs),
                    icones/ (SVG locaux), logo-final-viela.png (copie telle quelle de assets/logo-final-viela.png)
    ville/          index.html, ville.css, app.js (état, modes, panneaux), status.js, compare.js (A/B, historique),
                    view3d.js (vue 3D), view2d.js (vue 2D de secours), data/city.json
      carte/        config.js (sources locales, emprise, hauteurs), style.js (style MapLibre, ambiances), vue.js (vue « carte »),
                    operationnel.js (couches de l'API), camions.js (camions Three.js dans MapLibre), recherche.js,
                    polices/ (glyphes Noto Sans, OFL-1.1), data/ (ouagadougou.pmtiles, recherche.json : fabriqués, non versionnés)
      map3d/        scene.js, camera.js, city.js, layers.js, vehicles.js, interactions.js, effects.js, geo.js
    vendor/         leaflet/ (BSD-2), three/ (Three.js r170 + OrbitControls, MIT), maplibre/ (MapLibre GL JS 6.16.0, BSD-3),
                    pmtiles/ (pmtiles 4.5.0, BSD-3)
  tools/            build_city_data.py (données de la ville 3D), e2e/ (tests de bout en bout Playwright)
```

`web/shared/` n'est pas servi par l'API (seuls `/citizen`, `/brigade` et `/dashboard` sont montés) : le code commun vit
donc dans `/dashboard/shared/` et les trois pages l'importent par chemin absolu.

Mise en page de la mairie : la ville occupe tout l'écran ; commandes à gauche et détails à droite (Sélection, Comparer
A/B, Historique) dans deux panneaux flottants que les boutons aux deux bouts de la barre du haut masquent ; statut du
plan et chronomètre en haut de la scène ; légende en bas à gauche, caméra en bas à droite, indicateurs en pied de page.
Couleurs : vert = identité et actions positives, jaune = accent rare, rouge = erreurs et danger, violet = simulation.

## La carte de la ville (vue par défaut)

- Toute l'agglomération de Ouagadougou depuis OpenStreetMap (© contributeurs OpenStreetMap, ODbL) : tuiles vectorielles
  fabriquées par `./scripts/fabriquer_tuiles.sh` (Planetiler) et servies en local, rendues par MapLibre GL JS. Aucune
  ressource en ligne à l'affichage. Architecture, schéma des tuiles, limites : `docs/carte.md`.
- Bâtiments OSM extrudés en s'approchant ; hauteur OSM, sinon niveaux OSM × 3,2 m, sinon ESTIMÉE selon le type OSM. La
  fiche du bâtiment dit laquelle s'applique.
- Recherche locale (lieux, rues, points d'intérêt, quartiers du plan, camions), bouton 2D / 3D, ambiances jour, soir, nuit.
- Mêmes couches opérationnelles que la ville 3D, venant de l'API. Camions : animation ACCÉLÉRÉE et SIMULÉE le long des
  tournées calculées, jamais une position GPS. Le calcul des tournées ne couvre pour l'instant que le secteur pilote et
  les quartiers téléchargés.
- Tuiles absentes (clone neuf : le fichier reste hors de Git) ou carte en échec : ville 3D du secteur pilote sous un
  bandeau permanent (`#bandeau-couverture`) : carte de toute la ville indisponible, couverture limitée au secteur pilote
  et aux quartiers téléchargés. `?vue=ville3d` demande directement la ville 3D.

## La ville 3D (`?vue=ville3d`)

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
   bâtiment, un quartier puis un signalement (fiche, photo floutée, historique).
2. **Plan initial (0:35–1:05)** : passer en Simulation (bandeau violet hachuré) ; le plan se calcule ; points verts, tournées
   colorées, camions qui roulent ; « Comparer A/B » → « Fixer le plan affiché comme A ».
3. **Panne (1:05–1:40)** : cliquer un camion → « Déclarer en panne » ; le camion s'arrête, feux allumés ; statut
   « Plan partiellement réalisable — N arrêt(s) reporté(s) », recalcul partiel, temps serveur affiché en haut de la scène.
4. **Pluie (1:40–2:10)** : « Déclencher la saison des pluies » ; pluie dans la ville ; points non desservis en rouge.
5. **Nouveau quartier (2:10–2:40)** : choisir Kalgodin → « Ajouter au scénario » ; la caméra y vole, nouveaux points.
6. **Décider (2:40–3:00)** : « Fixer le plan affiché comme B » → « Comparer A et B » : écarts et compromis.

Avant la démonstration : vérifier que les tuiles existent (`web/dashboard/ville/carte/data/ouagadougou.pmtiles`, sinon
`./scripts/fabriquer_tuiles.sh`), puis `./scripts/reset_db.sh` (vide sim.db, recharge le jeu factice) et ouvrir la page une fois.

## Tests

- `pytest` (racine) : 128 tests, dont `tests/test_c_dashboard.py` (contrat du front : ressources locales, routes appelées
  présentes dans l'API, données fictives étiquetées, pas d'innerHTML).
- `web/tools/e2e/*.py` : parcours dans Chromium (Playwright, à installer à part), sur un serveur lancé avec des bases
  temporaires (`REEL_DB`, `SIM_DB`, `PHOTO_DIR`) : citoyen (en ligne, hors ligne, synchronisation, GPS refusé),
  brigade (code, décision, hors ligne, conflit 409), mairie (24 vérifications), vue 2D, mode démonstration, couche API,
  gestes (`gestes.py` : redirection, clic sur une épingle dans la ville, « Rouvrir » de l'historique).

## Dépendances côté serveur

1. Pas de `GET` des dépotoirs simulés ni des routes coupées : la liste est reconstruite à partir des réponses
   (`active_cuts`, `plan.cut_roads`, points `dumpsite` du plan).
2. `POST /api/reports` n'a pas de clé d'idempotence : si une réponse se perd (délai dépassé), un nouvel envoi
   automatique peut renforcer le même dépotoir (signalé N + 1 fois) au lieu de créer un doublon.
3. Les bâtiments, routes et limites de quartiers ne sont pas exposés par l'API : `city.json` est généré depuis
   `data/` et doit être régénéré si ces données changent. Les tuiles de la carte sont fabriquées à part depuis l'extrait
   OSM (`./scripts/fabriquer_tuiles.sh`).
4. Pas de position des camions côté serveur : un camion en panne s'arrête là où l'animation le montrait.
