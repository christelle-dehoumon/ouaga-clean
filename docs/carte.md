# Carte de Ouagadougou (vue « carte » de la mairie)

La vue par défaut de la mairie (`/dashboard/ville/`) est une carte de toute l'agglomération de Ouagadougou. Elle est
dessinée par MapLibre GL JS à partir de tuiles vectorielles fabriquées depuis OpenStreetMap et servies par Yilgré
lui-même. Aucune ressource n'est chargée sur Internet à l'affichage.

Ce document décrit l'architecture, la fabrication des tuiles, leur schéma, l'estimation des hauteurs, les limites et
les licences.

---

## 1. Architecture

```text
Extrait OSM Burkina Faso (Geofabrik, .osm.pbf)
        │  scripts/fabriquer_tuiles.sh (une fois, avec réseau)
        ▼
Planetiler + scripts/tuiles/schema_yilgre.yml  ──►  web/dashboard/ville/carte/data/ouagadougou.pmtiles
                                                          │  scripts/tuiles/index_recherche.py
                                                          ▼
                                                    web/dashboard/ville/carte/data/recherche.json
        │  servis par l'API comme fichiers statiques (sans réseau)
        ▼
MapLibre GL JS + protocole pmtiles (navigateur)  ──►  vue « carte »
```

### Trois vues, une seule interface

`createView` (`web/dashboard/ville/app.js`) choisit la vue au démarrage. Les trois vues exposent les mêmes méthodes
(`setReports`, `setPlan`, `select`, `focusLatLon`…) : la logique métier de `app.js` ne change pas.

| Vue | Adresse | Contenu | Rendu |
|---|---|---|---|
| **Carte** (par défaut) | `/dashboard/ville/` | toute l'agglomération, bâtiments extrudés | MapLibre GL JS, tuiles locales |
| **Ville 3D** | `/dashboard/ville/?vue=ville3d` | secteur pilote et quartiers téléchargés | Three.js (`view3d.js`, `map3d/`) |
| **2D de secours** | `/dashboard/ville/?vue=2d` | même données, sans relief | Leaflet (`view2d.js`), tuiles OSM en ligne |

Replis automatiques :
- tuiles absentes (clone neuf, `./scripts/fabriquer_tuiles.sh` pas lancé) : ville 3D du secteur pilote, sous un bandeau
  permanent (`#bandeau-couverture`) : carte de toute la ville indisponible, commande à lancer, affichage limité au secteur
  pilote et aux quartiers téléchargés ;
- erreur au démarrage de la carte : même repli, même bandeau permanent, avec le motif de l'erreur ;
- pas de WebGL : vue 2D de secours ;
- autre commune que celle de `city.json` : vue 2D de secours.

### Modules de `web/dashboard/ville/carte/`

| Fichier | Rôle |
|---|---|
| `config.js` | adresses locales des tuiles et des polices, emprise, caméra, attribution, règles de hauteur des bâtiments |
| `style.js` | style MapLibre du schéma Yilgré ; trois ambiances (jour, soir, nuit) qui ne changent que les couleurs et la lumière |
| `vue.js` | crée la carte, vérifie la présence des tuiles (`tuilesDisponibles`), gère clics, survol, caméra (Dessus, Immersive, Rue), bascule 2D / 3D |
| `operationnel.js` | couches venant de l'API : signalements, dépotoirs simulés, points du plan, tournées, coupures, quartiers du plan, surbrillance |
| `camions.js` | camions du plan dans une couche Three.js insérée dans MapLibre ; réutilise la flotte de la ville 3D (`map3d/vehicles.js`) |
| `recherche.js` | recherche locale dans `recherche.json` (lieux, rues, points d'intérêt), insensible aux accents et à la casse |
| `polices/` | glyphes Noto Sans (regular, bold, italic) pour les étiquettes |
| `data/` | `ouagadougou.pmtiles` et `recherche.json`, fabriqués, non versionnés (voir section 5) |

`app.js` branche la recherche, le bouton 2D / 3D et le choix d'ambiance dans `bindCarte`. Les fiches d'un bâtiment ou
d'un point d'intérêt OSM y sont construites (`ficheBatiment`, `fichePoi`).

Bibliothèques copiées dans le dépôt : `web/dashboard/vendor/maplibre/` (MapLibre GL JS) et
`web/dashboard/vendor/pmtiles/` (lecture des archives PMTiles dans le navigateur).

---

## 2. Fabriquer (ou refaire) les tuiles

```bash
./scripts/fabriquer_tuiles.sh
```

**Obligatoire une fois après chaque clonage** : le fichier de tuiles n'est pas dans Git (section 5). Sans cette étape,
la mairie affiche la ville 3D du secteur pilote sous un bandeau permanent.

Le script peut être relancé sans risque :
- **rien à refaire** si les tuiles et l'index existent, sont valides et ont été fabriqués avec le même schéma, la même
  emprise, la même version de Planetiler et le même extrait OSM (somme MD5). Cette empreinte est gardée dans
  `web/dashboard/ville/carte/data/.fabrication.json` (hors de Git) ;
- `./scripts/fabriquer_tuiles.sh --force` refabrique dans tous les cas.

Mesuré le 2026-11-18 sur la machine de fabrication : 0,5 s quand il n'y a rien à refaire ; 36 s (temps écoulé) pour
refabriquer avec l'extrait OSM et Planetiler déjà en cache.

Prérequis :
- **Java 21 ou plus** (Planetiler) ;
- `curl`, `md5sum`, `sha256sum`, `unzip`, `python3` avec le module `venv` ;
- une connexion Internet pendant la fabrication seulement.

Ce que fait le script :
0. vérifie Java : absent ou plus ancien que 21, il s'arrête avec un message clair (code de sortie 2) ;
1. télécharge l'extrait Geofabrik du Burkina Faso et vérifie sa somme MD5 ; le fichier est gardé en cache et n'est
   téléchargé de nouveau que s'il manque ou si la somme ne correspond pas ;
2. télécharge Planetiler (version `0.10.2` par défaut, variable `PLANETILER_VERSION`) si le fichier en cache n'est pas
   de cette version ;
3. lance Planetiler avec le schéma `scripts/tuiles/schema_yilgre.yml` sur l'emprise choisie, dans un fichier temporaire ;
4. valide ce fichier avec `scripts/tuiles/valider_tuiles.py` : en-tête PMTiles lisible, zooms 0 à 14, emprise couverte,
   couches attendues déclarées, tuile du centre-ville au zoom 14 non vide. Si la validation échoue, le fichier temporaire
   est supprimé, l'ancien fichier est gardé et le script s'arrête en erreur. Sinon le fichier remplace
   `web/dashboard/ville/carte/data/ouagadougou.pmtiles` ;
5. écrit `recherche.json` avec `scripts/tuiles/index_recherche.py`, puis l'empreinte `.fabrication.json`.

La validation et l'index tournent dans un environnement Python de fabrication à part (`venv-tuiles` dans le cache), avec
`scripts/tuiles/requirements.txt`. Il n'est jamais nécessaire à l'application.

Variables :

| Variable | Défaut | Rôle |
|---|---|---|
| `YILGRE_CACHE` | `~/.cache/yilgre` | cache de l'extrait OSM, de Planetiler et de l'environnement de fabrication |
| `BOUNDS` | `-1.72,12.20,-1.36,12.53` | emprise (lon min, lat min, lon max, lat max) : Ouagadougou et communes contiguës |
| `PLANETILER_VERSION` | `0.10.2` | version de Planetiler téléchargée |

Si `BOUNDS` change, il faut aussi changer `emprise` dans `web/dashboard/ville/carte/config.js` : la caméra est bornée
à cette zone.

Pour suivre les mises à jour d'OpenStreetMap, supprimer `~/.cache/yilgre/burkina-faso-latest.osm.pbf*` puis relancer
le script : le nouvel extrait change l'empreinte, donc les tuiles sont refabriquées.

### Alternative Docker (non testée)

Sans Java installé, Planetiler existe en image Docker. La commande ci-dessous est un point de départ à adapter, elle n'a
pas été essayée sur ce projet. Elle suppose l'extrait OSM déjà téléchargé dans le cache :

```bash
docker run --rm -v "$PWD":/data -v "$HOME/.cache/yilgre":/cache ghcr.io/onthegomap/planetiler:0.10.2 \
  generate-custom --schema=/data/scripts/tuiles/schema_yilgre.yml \
  --osm_path=/cache/burkina-faso-latest.osm.pbf --bounds=-1.72,12.20,-1.36,12.53 \
  --output=/data/web/dashboard/ville/carte/data/ouagadougou.pmtiles --force
```

La validation et l'index de recherche se font ensuite à part :

```bash
python3 -m venv /tmp/venv-tuiles && /tmp/venv-tuiles/bin/pip install -r scripts/tuiles/requirements.txt
/tmp/venv-tuiles/bin/python scripts/tuiles/valider_tuiles.py \
  web/dashboard/ville/carte/data/ouagadougou.pmtiles -1.72,12.20,-1.36,12.53
/tmp/venv-tuiles/bin/python scripts/tuiles/index_recherche.py \
  web/dashboard/ville/carte/data/ouagadougou.pmtiles web/dashboard/ville/carte/data/recherche.json
```

### Mesures de la fabrication

Mesurées le 2026-11-18 sur la machine de fabrication (Intel i7-1165G7, relevé par `lscpu` ; ce n'est pas la machine de `docs/mesures.md`) :

| Mesure | Valeur |
|---|---|
| Extrait Geofabrik (daté du 2026-11-17, en-tête `Last-Modified`) | 85 136 281 octets |
| Durée de Planetiler (première fabrication) | 2 min 40 s |
| Refabrication complète (extrait et Planetiler déjà en cache, après correction du zoom des points d'intérêt) | 1 min 7 s (`time ./scripts/fabriquer_tuiles.sh`) |
| Archive `ouagadougou.pmtiles` | 16 293 582 octets, 424 tuiles, 727 537 objets (comptés en décodant toutes les tuiles), zooms 0 à 14 |
| `recherche.json` | 5 352 entrées |
| Index de recherche | 189 lieux, 1 166 rues, 3 997 points d'intérêt nommés |

Ces valeurs dépendent de l'extrait du jour et de la machine.

---

## 3. Schéma des tuiles

Défini dans `scripts/tuiles/schema_yilgre.yml`. Les attributs reprennent les balises OSM, sans invention : une valeur
absente d'OSM reste absente. Le nom (`nom`) prend `name:fr`, sinon `name`. Zoom maximal des tuiles : 14 (MapLibre agrandit
au-delà).

| Couche | Géométrie | Zoom min | Attributs |
|---|---|---|---|
| `batiments` | polygone | 13 | `osm_id`, `type` (`building` ou `building:part`), `partie`, `niveaux`, `niveaux_min`, `hauteur`, `hauteur_min` (en mètres, seulement si la balise OSM est un nombre), `toit` (`roof:shape`), `amenite`, `nom` |
| `routes` | ligne | 6 à 14 selon la classe | `osm_id`, `classe` (`highway` sans `_link`), `bretelle`, `nom`, `ref`, `sens_unique`, `sens_unique_inverse`, `vitesse_max`, `pont`, `tunnel`, `revetement` (`surface`), `giratoire`, `niveau` (`layer`) |
| `rail` | ligne | 10 | `classe`, `nom` |
| `eau` | polygone | 8 | `classe`, `nom` (barrages, bassins, `natural=water`) |
| `cours_eau` | ligne | 11 | `classe` (rivière, ruisseau, canal, drain, fossé), `nom`, `tunnel` |
| `occupation` | polygone | 10 | `classe` (amenity, leisure, aeroway, landuse ou natural), `nom` |
| `lieux` | point | 4 à 13 selon la classe | `osm_id`, `classe` (`place`), `nom`, `population` |
| `limites` | ligne | 8 | `niveau_admin` (`admin_level`) |
| `poi` | point | 12 à 14 selon la classe | `osm_id`, `classe`, `famille` (commerce, santé, éducation, culte, transport, administration, loisirs, autre), `nom` |

Les bâtiments `building=no` et `building=roof` sont exclus. Pour les points d'intérêt, une surface est réduite à un point
sur sa surface.

---

## 4. Hauteur des bâtiments

Règle de `web/dashboard/ville/carte/config.js` (`exprHauteur`, `sourceHauteur`), dans cet ordre :

1. balise OSM `height` : hauteur cartographiée ;
2. balise OSM `building:levels` : niveaux × 3,2 m ;
3. sinon, **hauteur estimée** selon le type OSM du bâtiment, plus 0 ; 0,9 ou 1,8 m selon l'identifiant OSM (reste de la
   division par 3). Cette variation est déterministe : la même ville s'affiche à chaque chargement, sans bloc uniforme.

| Type OSM | Hauteur estimée (m) |
|---|---|
| `cathedral` | 14 |
| `stadium` | 12 |
| `apartments`, `hotel` | 10 |
| `office`, `church` | 9 |
| `hospital`, `government`, `mosque` | 8 |
| `commercial`, `university`, `public`, `civic` | 7 |
| `retail`, `industrial`, `warehouse`, `hangar` | 6 |
| `school` | 5 |
| `residential` | 3,4 |
| `house`, `detached`, `yes`, type absent ou autre | 3,2 |
| `roof` | 3 |
| `hut`, `garage`, `kiosk` | 2,6 |
| `shed` | 2,4 |

La base d'un bâtiment vient de `min_height`, sinon de `building:min_level` × 3,2 m, sinon 0.

La fiche d'un bâtiment (clic) affiche la hauteur et son origine : hauteur cartographiée dans OpenStreetMap, nombre de
niveaux OSM multiplié par 3,2 m, ou « estimée (pas de hauteur ni d'étages dans OpenStreetMap) ». Une estimation n'est
jamais présentée comme une mesure.

Pourquoi estimer : au zoom 14, sur 385 359 bâtiments distincts, 12 ont une hauteur OSM, 241 un nombre de niveaux, 57 une
forme de toit et 430 un nom. Moins de 0,1 % ont donc une hauteur ou des niveaux réels.

---

## 5. Auto-hébergement et fonctionnement hors ligne

- Les tuiles, l'index de recherche, les polices, MapLibre et pmtiles sont des fichiers du dépôt ou fabriqués en local.
  L'API les sert comme les autres fichiers de `/dashboard`. Le navigateur lit l'archive PMTiles par requêtes partielles
  (`Range`), sans serveur de tuiles.
- Le réseau n'est nécessaire que pendant `./scripts/fabriquer_tuiles.sh`. Ensuite la carte fonctionne sans Internet.
- Le test `test_aucune_ressource_externe_hors_fond_2d_de_secours` (`tests/test_c_dashboard.py`) refuse toute adresse
  `http(s)://` dans le code de la page de la mairie, y compris `carte/`. Seule la vue 2D de secours (`view2d.js`) charge
  des tuiles OpenStreetMap en ligne.
- `ouagadougou.pmtiles` (16 293 582 octets) dépasse la limite de 10 Mo par fichier du dépôt. **Décision : ce fichier
  reste hors de Git**, comme `recherche.json` (`.gitignore`). Après un clonage, il faut lancer
  `./scripts/fabriquer_tuiles.sh` (Java 21 ou plus). Distribuer un fichier déjà fabriqué par les « Releases » GitHub
  pourra être envisagé plus tard ; ce n'est pas fait.
- Fichier absent, ou carte en échec : la page ne tombe pas en panne. Elle affiche la ville 3D du secteur pilote sous un
  bandeau permanent explicite : carte de toute la ville indisponible, couverture limitée au secteur pilote et aux
  quartiers téléchargés.
- L'image Docker (`docker compose up --build`) copie le dépôt local (`COPY . .`) : elle contient les tuiles seulement si
  elles ont été fabriquées avant la construction de l'image.

### Pourquoi pas un service de tuiles public

- **Démonstration hors ligne :** la finale peut se dérouler sans réseau fiable ; une carte en ligne serait blanche.
- **Pas de dépendance à un service :** un service gratuit n'a pas d'engagement de disponibilité.
- **Règle du projet :** aucune ressource externe dans les pages (voir le test ci-dessus).
- **Données utiles à la mairie :** le schéma Yilgré garde par bâtiment l'identifiant OSM, le type et les niveaux.

### Comparaison : A (OpenFreeMap en ligne) et B (tuiles auto-hébergées)

| Critère | A. OpenFreeMap | B. Auto-hébergé (retenu) |
|---|---|---|
| Couverture | toute la ville | agglomération (emprise `BOUNDS`) |
| Bâtiments | fusionnés en multipolygones, seulement `render_height` et `render_min_height` | un objet par bâtiment OSM : `osm_id`, `type`, `niveaux`, `hauteur`, `toit`, `nom` |
| Fiche d'un bâtiment, origine de la hauteur | impossible (ni type, ni niveaux, ni identifiant) | possible |
| Sans réseau | non | oui |
| Fraîcheur des données | mise à jour par le service | celle de l'extrait téléchargé ; refaire les tuiles pour suivre OSM |
| Coût de mise en place | aucun | Java 21+, extrait OSM de 85 136 281 octets à télécharger, fabrication à lancer |
| Taille dans le projet | aucune | archive de 16 293 582 octets, fabriquée en local, hors de Git |

Valhalla (calcul d'itinéraires) n'a pas été ajouté. Les tournées suivent déjà les rues OSM réelles grâce au graphe
existant (`data/processed/roads_graph.pkl`) et à OR-Tools. Valhalla serait une dépendance lourde de plus et remplacerait
la logique de planification des tournées.

---

## 6. Limites et données manquantes

- **Couverture OSM inégale.** Bâtiments mesurés par tuile du zoom 14 : 5 462 (centre), 7 457 (Saaba), 1 255 (Ouaga 2000),
  1 229 (Karpala), 455 (Tampouy). Un quartier vide sur la carte peut être un quartier peu cartographié, pas un quartier
  vide.
- **Hauteurs estimées** pour presque tous les bâtiments (section 4). Ce n'est pas une maquette exacte de la ville.
- **Calcul des tournées limité, pour l'instant, au secteur pilote et aux quartiers téléchargés.** La carte montre toute
  l'agglomération, mais le graphe routier utilisé par OR-Tools ne couvre aujourd'hui que ces zones. Une route ne peut être
  coupée (simulation) que sur ce réseau. L'extension du graphe à toute l'agglomération est en cours ; elle n'est pas
  encore validée.
- **Camions simulés.** Les camions de la carte sont une animation ACCÉLÉRÉE le long des tournées calculées. Ce n'est
  jamais une position GPS : aucune donnée GPS de camion n'existe dans Yilgré.
- **Pas de temps réel poussé par le serveur.** En données réelles, la page interroge l'API toutes les 15 s (`POLL_MS`
  dans `app.js`).
- **Données absentes du serveur :** pas de bacs ou conteneurs à déchets, pas de positions GPS des camions, pas d'état
  « assigné » ou « en cours » pour un signalement.
- **Zones inondables :** `data/processed/flood_zones.geojson` est étiqueté `"source": "estimated"` ; ce sont des
  hypothèses, pas des relevés.
- **Points d'intérêt :** seuls ceux qui ont une balise reconnue par le schéma (`amenity`, `shop`, `tourism`, quelques `leisure`,
  `healthcare`, `office=government`, `historic`, quelques `man_made`) sont gardés, et seuls ceux qui ont un nom entrent dans
  la recherche. Un lieu absent d'OSM ou sans nom n'est pas trouvable.
- **Glyphes :** seules cinq plages Unicode sont fournies (U+0000 à U+03FF : latin, latin étendu, diacritiques, grec ; et
  U+2000 à U+20FF : ponctuation générale) ; un caractère hors de ces plages n'est pas affiché.
- **Données figées :** les tuiles reflètent l'extrait OSM du jour de fabrication.

---

## 7. Licences et attributions

| Élément | Licence | Livré avec l'application |
|---|---|---|
| Données OpenStreetMap (extrait Geofabrik) | ODbL 1.0, « © contributeurs OpenStreetMap » | oui (dans les tuiles et l'index) |
| MapLibre GL JS `6.16.0` | BSD-3-Clause | oui, `web/dashboard/vendor/maplibre/` avec `LICENSE.txt` |
| pmtiles (JS) `4.5.0` | BSD-3-Clause | oui, `web/dashboard/vendor/pmtiles/` avec `LICENSE` |
| Noto Sans (glyphes) | SIL Open Font License 1.1 | oui, `web/dashboard/ville/carte/polices/` |
| Planetiler `0.10.2` | Apache-2.0 | non, outil de fabrication |
| pmtiles (Python) `3.8.1` | BSD-3-Clause | non, outil de fabrication |
| mapbox-vector-tile `2.2.0` | MIT | non, outil de fabrication |

Les glyphes ont été téléchargés depuis le service de polices d'OpenFreeMap ; ils sont générés à partir du projet
openmaptiles/fonts.

L'attribution « © contributeurs OpenStreetMap (ODbL) » est affichée en permanence dans le bandeau de crédit de la page.
Les tuiles et l'index de recherche sont une base de données dérivée d'OpenStreetMap : ils restent sous ODbL.

Inventaire complet du projet : [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md).

---

## 8. Phase « Adopter, Adapter, Améliorer » (référence : Kutɔnu Vibes)

Observé sur Kutɔnu Vibes (navigateur, 2026-11-18) : moteur Three.js r180, panneau « Aller à » vers 37 lieux,
ambiances Jour, Doré, Soir, Nuit, réglage Haute qualité / Mode léger, écran de chargement avec progression et
astuces, modèles `.glb` avec variantes simplifiées, crédits par ressource. Le rendu de leur scène n'a pas pu être
observé ici (rendu logiciel trop lent).

Adopté et adapté dans Yilgré (sans copier de ressource) :

- **Bâtiments texturés** : cinq textures CC0 de Poly Haven (`carte/textures/`, `CREDITS.txt`) choisies selon le type
  OSM du bâtiment (`carte/materiaux.js`), murs et toits différenciés. Habillage stylistique : le matériau réel n'est
  pas connu.
- **Ombres portées simulées** : copies décalées des emprises au sol, direction et longueur propres à chaque ambiance
  (MapLibre ne calcule pas d'ombre pour les extrusions) ; aucune ombre la nuit.
- **Quatre ambiances** : jour, doré, soir, nuit (couleurs, lumière, ciel ; jamais la géographie).
- **Qualité** : HQ ou Léger (sans textures ni ombres, inclinaison limitée) ; choix gardé dans le navigateur, Léger par
  défaut sur écran tactile ou étroit.
- **« Aller à »** (`carte/reperes.js`) : 14 lieux emblématiques dont le nom et la position viennent de l'index OSM, vol
  de caméra et **visite guidée** qui s'arrête dès que l'utilisateur touche la carte.
- **Astuces au chargement** : fonctions réelles de l'application uniquement.

Amélioré pour Yilgré : **zones prioritaires** (« où intervenir ? ») : densité des signalements à traiter (confirmé 1,
à vérifier 0,7, nettoyage à vérifier 0,3, rejeté et nettoyé 0), réelle ou simulée selon le mode, visible à l'échelle de la
ville et effacée en s'approchant au profit des épingles ; c'est une densité de signalements, pas une mesure de tonnage.
Et la fiche d'un lieu (repère ou recherche) donne la **propreté à moins de 600 m** : signalements
par statut (réels, ou simulés en mode Simulation) et point du plan le plus proche avec son état (desservi ou non).

Mesures (2026-11-18, poste faible simulé : rendu logiciel SwiftShader, processeur ralenti ×4 par l'émulation de
Chromium, 1366 × 768) : chargement de la carte 4,6 s ; temps médian par image en HQ 28, 35 et 21 ms sur trois vues ;
en Léger 26 et 20 ms sur les deux dernières (la première mesure Léger inclut la reconstruction du style et n'est pas
comparable). Script : mesure par 20 images forcées après chargement complet des tuiles.

Non fait, faute de temps : modèles 3D des monuments, bâtiments Google Open Buildings pour les zones peu cartographiées,
routage des tournées sur toute l'agglomération, module de simulation animée (pré-collecteurs, ménages, journal).
