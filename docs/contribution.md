# Matrice de contribution

Générée par `python -m scripts.contribution_matrix` à partir de git (toutes branches, sans fusions). Lignes ajoutées par couche, hors données, bibliothèques copiées et images (comptées en fichiers).

## Commits

| Membre (auteur git) | Rôle | Commits | dont assistés par IA | Instantanés automatiques (non attribués) | Fichiers de données touchés |
|---|---|---|---|---|---|
| jonathan-onjd | API, tri, interfaces (à confirmer) | 25 | 18 | 29 | 36 |
| TaniaW777 | géo, optimisation (à confirmer) | 7 | 0 | 0 | 6 |
| Christelle Dehoumon | simulation, tableau de bord (à confirmer) | 10 | 0 | 0 | 17 |

## Lignes ajoutées par couche

| Couche | jonathan-onjd | TaniaW777 | Christelle Dehoumon |
|---|---|---|---|
| API | 1092 |  |  |
| Tri | 821 |  |  |
| Moteur (géo, optimisation) | 518 | 2262 |  |
| Simulation | 424 |  | 1286 |
| Cycle de vie, bases, floutage | 507 | 183 |  |
| Citoyen | 680 |  |  |
| Brigade | 384 |  |  |
| Mairie 3D | 3424 |  |  |
| Ancien tableau de bord | 325 |  | 1588 |
| Tests | 1895 | 912 | 208 |
| Scripts, déploiement | 1153 | 576 | 254 |
| Documentation | 1165 | 244 | 163 |
| Configuration | 713 | 80 |  |
| Autres | 126 | 31 |  |

Lecture et limites :

- Les commits « Agent host session » sont des instantanés automatiques d'un outil : ils recopient l'état de travail,
  y compris des fichiers d'autres membres. Leurs lignes ne sont attribuées à personne ; les statistiques brutes de
  `git shortlog` les comptent et faussent donc la répartition.
- Les commits « assistés par IA » portent la mention `Co-Authored-By: Claude` : ils ont été produits avec un
  assistant de code, sous le compte git indiqué.
- Les rôles sont déduits des dossiers modifiés et restent à confirmer par l'équipe.

## Briques réutilisées

| Brique | Version | Licence | Usage |
|---|---|---|---|
| FastAPI | 0.163.1 | MIT | API web |
| Uvicorn | 0.54.0 | BSD-3-Clause | serveur HTTPS |
| OR-Tools | 9.15.6755 | Apache-2.0 | tournées des camions |
| OSMnx | 2.1.2 | MIT | préparation du réseau OSM |
| NetworkX | 3.7 | BSD-3-Clause | graphe routier |
| SciPy | 1.18.1 | BSD-3-Clause | plus courts chemins |
| NumPy | 2.2.6 | BSD-3-Clause | calcul |
| scikit-learn | 1.9.1 | BSD-3-Clause | points de regroupement (KMeans) |
| Shapely / GeoPandas / pyproj | 2.2.0 / 1.2.0 / 3.8.0 | BSD-3-Clause / BSD-3-Clause / MIT | géométrie |
| pyosmium | 4.3.2 | BSD-2-Clause | lecture des fichiers OSM |
| Mesa | 3.5.2 | Apache-2.0 | simulation multi-agents |
| OpenCV (opencv-python-headless) | 4.12.0.88 | Apache-2.0 (roue avec FFmpeg LGPL-2.1, voir THIRD_PARTY_LICENSES.md) | floutage |
| Requests | 2.34.2 | Apache-2.0 | scripts de préparation |
| pytest / httpx | 9.2.0 / 0.28.1 | MIT / BSD-3-Clause | tests |
| Three.js | r170 | MIT | ville 3D |
| Leaflet | 1.9.4 | BSD-2-Clause | carte 2D de secours |
| Playwright (outil de test, non livré) | — | Apache-2.0 | tests de bout en bout |
| Données OpenStreetMap | — | ODbL-1.0, « © OpenStreetMap contributors » | routes, bâtiments, eau, quartiers |
| Images de test (Wikimedia Commons) | — | domaine public / CC0 | mesure du floutage |

Toutes ces licences sont compatibles avec la licence Apache-2.0 du projet. Les données dérivées d'OpenStreetMap
restent sous ODbL. Inventaire détaillé : [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md).
