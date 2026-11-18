# Matrice de Contribution de VIELA

Générée par `python -m scripts.contribution_matrix` à partir de git (toutes branches, sans fusions). Lignes ajoutées par couche, hors données, bibliothèques copiées et images (comptées en fichiers).

## Commits

| Membre (auteur git) | Rôle | Commits | Instantanés automatiques (non attribués) | Fichiers de données touchés |
|---|---|---|---|---|
| jonathan-onjd | API, tri, interfaces citoyen et brigade | 29 | 0 | 36 |
| Christelle Dehoumon | simulation, tableau de bord de la mairie, carte 3D | 19 | 0 | 61 |
| TaniaW777 | géographie, optimisation des tournées | 7 | 0 | 6 |

## Lignes ajoutées par couche

| Couche | jonathan-onjd | Christelle Dehoumon | TaniaW777 |
|---|---|---|---|
| API | 963 |  |  |
| Tri | 540 |  |  |
| Moteur (géo, optimisation) | 518 |  | 2262 |
| Simulation | 424 | 1286 |  |
| Cycle de vie, bases, floutage | 509 |  | 183 |
| Citoyen | 525 | 224 |  |
| Brigade | 384 | 263 |  |
| Mairie 3D | 3424 | 2280 |  |
| Ancien tableau de bord | 325 | 1589 |  |
| Tests | 1779 | 449 | 912 |
| Scripts, déploiement | 1279 | 915 | 576 |
| Documentation | 1605 | 647 | 244 |
| Configuration | 699 |  | 80 |
| Autres | 84 | 125 | 31 |

Lecture et limites :

- Les commits « Agent host session » sont des instantanés automatiques d'un outil : ils recopient l'état de travail,
  y compris des fichiers d'autres membres. Leurs lignes ne sont attribuées à personne ; les statistiques brutes de
  `git shortlog` les comptent et faussent donc la répartition.

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
| Three.js | r170 | MIT | camions 3D, ville 3D du secteur pilote |
| Leaflet | 1.9.4 | BSD-2-Clause | carte 2D de secours, carte de la brigade |
| MapLibre GL JS | 6.16.0 | BSD-3-Clause | carte 3D de l'agglomération |
| PMTiles (JavaScript) | 4.5.0 | BSD-3-Clause | lecture des tuiles auto-hébergées |
| Polices Noto Sans | — | SIL OFL-1.1 | étiquettes de la carte |
| Textures Poly Haven | — | CC0-1.0 | façades des bâtiments (stylistique) |
| Planetiler (outil de fabrication, non livré) | 0.10.2 | Apache-2.0 | fabrication des tuiles |
| pmtiles / mapbox-vector-tile (Python, fabrication, non livrés) | 3.8.1 / 2.2.0 | BSD-3-Clause / MIT | validation des tuiles, index de recherche |
| Playwright (outil de test, non livré) | — | Apache-2.0 | tests de bout en bout |
| Données OpenStreetMap | — | ODbL-1.0, « © OpenStreetMap contributors » | routes, bâtiments, eau, quartiers |
| Images de test (Wikimedia Commons) | — | domaine public / CC0 | mesure du floutage |

Toutes ces licences sont compatibles avec la licence Apache-2.0 du projet. Les données dérivées d'OpenStreetMap
restent sous ODbL. Inventaire détaillé : [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md).
