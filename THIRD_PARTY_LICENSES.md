# Licences Tierces de Yilgré

Yilgré est distribué sous licence **Apache-2.0** ([LICENSE](LICENSE)). Il réutilise les briques et les données
ci-dessous, chacune sous sa propre licence. Les licences des paquets Python ont été relues le 2026-11-18 dans les
métadonnées des paquets installés (`importlib.metadata`), et celles des bibliothèques web dans leurs fichiers `LICENSE`.

---

## 1. Dépendances Python Directes (`requirements.txt`)

| Paquet | Version | Licence | Usage |
|---|---|---|---|
| **fastapi** | `0.163.1` | MIT | API web |
| **uvicorn** | `0.54.0` | BSD-3-Clause | serveur HTTP/HTTPS |
| **httpx** | `0.28.1` | BSD-3-Clause | client de test |
| **requests** | `2.34.2` | Apache-2.0 | scripts de préparation des données |
| **mesa** | `3.5.2` | Apache-2.0 | simulation multi-agents |
| **opencv-python-headless** | `4.12.0.88` | Apache-2.0 (voir section 2) | floutage des visages et plaques |
| **osmnx** | `2.1.2` | MIT | préparation du réseau routier OSM |
| **networkx** | `3.7` | BSD-3-Clause | graphe routier |
| **shapely** | `2.2.0` | BSD-3-Clause | géométrie |
| **geopandas** | `1.2.0` | BSD-3-Clause | géométrie tabulaire |
| **pyproj** | `3.8.0` | MIT | projections |
| **numpy** | `2.2.6` | BSD-3-Clause | calcul |
| **scipy** | `1.18.1` | BSD-3-Clause | plus courts chemins |
| **scikit-learn** | `1.9.1` | BSD-3-Clause | points de regroupement (KMeans) |
| **ortools** | `9.15.6755` | Apache-2.0 | tournées des camions |
| **osmium** (pyosmium) | `4.3.2` | BSD-2-Clause | lecture des fichiers OSM |
| **pytest** | `9.2.0` | MIT | tests |

Dépendances indirectes notables : pandas (BSD-3-Clause), tqdm (MPL-2.0 et MIT), protobuf (BSD-3-Clause),
absl-py (Apache-2.0), starlette (BSD-3-Clause), pydantic (MIT), anyio (MIT), pyogrio (MIT), typing_extensions (PSF-2.0).

---

## 2. Composants Embarqués par OpenCV

La roue `opencv-python-headless` embarque des bibliothèques tierces décrites dans son fichier
`LICENSE-3RD-PARTY.txt`, notamment **FFmpeg** (LGPL-2.1), libpng, libjpeg-turbo (licences de type BSD et IJG), libwebp
et OpenJPEG. Yilgré n'utilise pas les fonctions vidéo et ne modifie pas ces bibliothèques ; elles sont liées
dynamiquement dans la roue officielle, ce que la LGPL-2.1 permet.

Les **cascades Haar** de détection (visages, plaques) livrées avec OpenCV sont sous l'« Intel License Agreement For Open
Source Computer Vision Library », une licence de type BSD (en-tête de chaque fichier `.xml`).

---

## 3. Bibliothèques Web Copiées dans le Dépôt

| Bibliothèque | Version | Licence | Emplacement |
|---|---|---|---|
| **Three.js** | `r170` | MIT, © three.js authors | `web/dashboard/vendor/three/` (avec `LICENSE`) |
| **Leaflet** | `1.9.4` | BSD-2-Clause, © Volodymyr Agafonkin, CloudMade | `web/dashboard/vendor/leaflet/` (avec `LICENSE`) |
| **MapLibre GL JS** | `6.16.0` | BSD-3-Clause, © MapLibre contributors | `web/dashboard/vendor/maplibre/` (`maplibre-gl.mjs`, `maplibre-gl-worker.mjs`, `maplibre-gl.css`, avec `LICENSE.txt`) |
| **pmtiles** (JavaScript) | `4.5.0` (build IIFE `dist/pmtiles.js`) | BSD-3-Clause | `web/dashboard/vendor/pmtiles/` (avec `LICENSE`) |
| **Noto Sans** (glyphes des étiquettes de la carte) | regular, bold, italic ; plages 0-255, 256-511, 512-767, 768-1023, 8192-8447 | SIL Open Font License 1.1 | `web/dashboard/ville/carte/polices/` ; glyphes téléchargés depuis le service de polices d'OpenFreeMap, générés à partir du projet openmaptiles/fonts ; texte de la licence : `polices/OFL.txt` |
| **Textures Poly Haven** (Clay Plaster, Clay Block Wall, Concrete Wall 008, Corrugated Iron 02, Red Plaster Weathered) | 5 images 128 × 128 px réduites en niveaux de gris | CC0 1.0 (domaine public) | `web/dashboard/ville/carte/textures/` ; auteurs et pages sources dans `CREDITS.txt` ; habillage stylistique, le matériau réel des bâtiments n'est pas connu |

Ces fichiers sont livrés avec l'application : ils sont servis par l'API et chargés par le navigateur.

---

## 4. Données

| Données | Source | Licence | Fichiers |
|---|---|---|---|
| **Routes, bâtiments, plans d'eau, cours d'eau, limite communale, nœuds de quartiers** | OpenStreetMap | **ODbL-1.0**, « © OpenStreetMap contributors » | `data/processed/`, `data/raw/boundary.geojson`, `data/water_bodies.geojson`, `data/territories.geojson`, `web/dashboard/ville/data/city.json` |
| **Tuiles vectorielles et index de recherche de la carte de la mairie** | extrait OpenStreetMap du Burkina Faso (Geofabrik, daté du 2026-11-17), découpé par Yilgré | **ODbL-1.0**, « © contributeurs OpenStreetMap » ; attribution affichée en permanence | `web/dashboard/ville/carte/data/ouagadougou.pmtiles`, `web/dashboard/ville/carte/data/recherche.json` (fabriqués par `scripts/fabriquer_tuiles.sh`, hors de Git : voir `docs/carte.md`) |
| **Tuiles de la carte 2D de secours** | serveur de tuiles OpenStreetMap, chargées en ligne | CC BY-SA 2.0 et politique d'usage des tuiles de l'OSMF ; attribution affichée | aucune copie locale |
| **Images de test du floutage** | Wikimedia Commons | domaine public ou CC0 | `tests/data/blur/` (détail dans `LICENSES.md`) |
| **Jeu de signalements exporté** | Yilgré (cas confirmés par la brigade) | ODbL-1.0 | `GET /api/export/reports.geojson`, `data/export/` |

Les hauteurs des bâtiments de la ville 3D et de la carte sont estimées par Yilgré quand OpenStreetMap ne les donne pas,
et les arbres de la ville 3D sont illustratifs : ces éléments ne viennent d'aucune source de données (règles dans
`docs/carte.md`).

---

## 5. Outils de Fabrication et de Test (Non Livrés)

Ces outils servent à préparer les données ou à tester. Ils ne sont pas copiés dans le dépôt ni livrés avec
l'application.

| Outil | Version | Licence | Usage |
|---|---|---|---|
| **Planetiler** | `0.10.2` | Apache-2.0 | fabrication des tuiles vectorielles (`scripts/fabriquer_tuiles.sh`, téléchargé dans `~/.cache/yilgre`) |
| **pmtiles** (Python) | `3.8.1` | BSD-3-Clause | lecture de l'archive pour l'index de recherche (`scripts/tuiles/requirements.txt`) |
| **mapbox-vector-tile** | `2.2.0` | MIT | décodage des tuiles pour l'index de recherche (`scripts/tuiles/requirements.txt`) |
| **Playwright** (Python) et Chromium | non épinglée | Apache-2.0 ; Chromium sous licences BSD et associées | tests de bout en bout (`web/tools/e2e/`), installés à part par `scripts/verifier_tout.sh` |
