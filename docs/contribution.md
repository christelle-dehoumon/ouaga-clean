# Matrice de contribution

Générée par `python -m scripts.contribution_matrix` à partir de git (toutes branches, sans fusions). Lignes ajoutées, hors données, bibliothèques copiées et images.

| Membre | Rôle | Commits | Instantanés automatiques | API | Géo | Optimisation | Simulation | Tri | Cœur (cycle de vie, config, bases, floutage) | Page citoyen | Tableau de bord | Tests | Scripts | Docs | Configuration | Autres |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jonathan-onjd | B (API, tri, mobile) | 12 | 29 | 1090 | 241 | 277 | 424 | 821 | 507 | 310 | 314 | 1093 | 752 | 336 | 713 | 688 |
| TaniaW777 | A (géo, optimisation) | 7 | 0 |  | 988 | 1274 |  |  | 183 |  |  | 912 | 576 | 204 | 80 | 71 |
| Christelle Dehoumon | C (simulation, tableau de bord) | 10 | 0 |  |  |  | 1286 |  |  |  | 1635 | 208 | 254 | 163 |  |  |

Les instantanés automatiques (« Agent host session ») ne sont pas comptés dans les lignes : ils recopient l'état de travail, y compris des fichiers d'autres membres.

Note : les commits du 2026-11-18 (refonte back-end) sont signés jonathan-onjd avec l'assistance de Claude (mention Co-Authored-By dans chaque message de commit).

## Briques réutilisées

| Brique | Licence | Usage |
|---|---|---|
| FastAPI | MIT | API web |
| Uvicorn | BSD-3-Clause | serveur HTTPS |
| OR-Tools | Apache-2.0 | tournées |
| OSMnx | MIT | préparation du réseau OSM |
| NetworkX | BSD-3-Clause | graphe |
| SciPy | BSD-3-Clause | plus courts chemins |
| scikit-learn | BSD-3-Clause | KMeans des points de regroupement |
| Shapely / GeoPandas / pyproj | BSD-3-Clause / BSD-3-Clause / MIT | géométrie |
| NumPy | BSD-3-Clause | calcul |
| pyosmium | BSD-2-Clause | lecture OSM |
| Mesa | Apache-2.0 | simulation multi-agents |
| OpenCV (opencv-python-headless) et ses cascades Haar | Apache-2.0 (cascades : licence Intel de type BSD) | floutage |
| Requests | Apache-2.0 | scripts de préparation |
| pytest / httpx | MIT / BSD-3-Clause | tests |
| Leaflet 1.9.4 | BSD-2-Clause | carte (front) |
| Données OpenStreetMap (routes, bâtiments, eau, quartiers) | ODbL-1.0, © contributeurs OpenStreetMap | données |
| Tuiles OpenStreetMap (front, en ligne) | CC BY-SA 2.0 (tuiles) ; politique d'usage des tuiles OSMF | fond de carte |
| Images de test (Wikimedia Commons) | Domaine public / CC0 | mesure du floutage |

Toutes ces licences sont compatibles avec la licence Apache-2.0 du projet. Les données dérivées d'OpenStreetMap restent sous ODbL et doivent être attribuées « © contributeurs OpenStreetMap ».
