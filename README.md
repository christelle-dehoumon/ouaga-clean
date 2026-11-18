# Ouaga Clean

Outil libre d'aide à la décision pour l'assainissement de Ouagadougou (Hackathon des Universités 2026, sujet 01) :
du signalement des dépotoirs sauvages au plan de gestion, avec une simulation des ménages, pré-collecteurs,
brigade Laabal et mairie. Licence Apache-2.0 (voir [LICENSE](LICENSE)).

## Démarrer en une commande

```bash
./scripts/run.sh
```

Le script crée `.venv` (Python 3.12), installe `requirements.txt`, génère un certificat HTTPS auto-signé dans
`data/certs/`, crée `data/reel.db` et `data/sim.db`, puis lance l'API en HTTPS sur `0.0.0.0:8443`.
HTTPS est indispensable : sans lui, le téléphone refuse le GPS et la caméra. Le certificat étant auto-signé, le
navigateur affiche un avertissement à accepter une fois. Avec ce certificat, GPS, caméra, envoi et file hors connexion
fonctionnent (vérifié), mais les navigateurs refusent le service worker : la page citoyen ne se ROUVRE pas sans réseau.
Pour cela, fournir un certificat reconnu : `SSL_CERTFILE=… SSL_KEYFILE=… ./scripts/run.sh` (Let's Encrypt), ou
installer `mkcert` (le script l'utilise) et son autorité racine sur les téléphones de démonstration.

- Page citoyen (téléphone, sans compte) : `https://<ip-du-poste>:8443/citizen/`
- Brigade Laabal (téléphone, code brigade) : `https://<ip-du-poste>:8443/brigade/`
- Mairie, ville 3D (ordinateur, code mairie) : `https://<ip-du-poste>:8443/dashboard/`
- Mode démonstration à données FICTIVES : ajouter `?mock=1` (bandeau permanent). Détails du front : [web/README.md](web/README.md)
- Documentation interactive de l'API : `https://localhost:8443/docs` ; contrat : [docs/api.md](docs/api.md)

Avec Docker : `docker compose up --build`. Port HTTP de débogage en plus : `HTTP_DEBUG_PORT=8000 ./scripts/run.sh`.

Codes de démonstration (en-tête `X-Role-Code`) : `brigade-demo` et `mairie-demo`. Ils sont publics : en vrai
déploiement, définir `BRIGADE_CODE` et `MAIRIE_CODE`.

Tests : `.venv/bin/python -m pytest -q` (serveur et contrat du front). Vérification complète, serveur + trois
interfaces dans Chromium : `./scripts/verifier_tout.sh` (Playwright requis, voir le script).

## Ce que fait l'outil

| Acteur | Ce qu'il fait |
|---|---|
| Citoyen | Envoie une photo et sa position, sans compte. Réponse toujours `{"ok": true}`, sans verdict. |
| Tri automatique | Écarte d'office les envois impossibles (forme, position, hors ville, date, photo), avec un motif visible de la mairie. Sinon transmet le cas avec des alertes. Il ne décide jamais. |
| Brigade Laabal | Ne voit que les cas à vérifier (dépotoir ou nettoyage), confirme ou rejette sur place. |
| Mairie | Voit tout, marque « nettoyé », remet un rejet ou un écarté à vérifier, calcule le plan, simule, compare des scénarios. |

Cycle d'un cas (`core/lifecycle.py`) : à vérifier, puis confirmé ou rejeté ; confirmé, puis nettoyage à vérifier,
puis nettoyé ou rejeté ; rejeté, puis à vérifier (mairie seule). Chaque transition est écrite dans la table
`historique` (qui, quand). Toute autre transition est refusée (409).

Doublon : moins de 30 m et moins de 48 h d'un cas actif. Aucun nouveau point n'est créé : le cas existant passe à
« signalé N fois », avec l'alerte `DOUBLON_PROBABLE`. La recherche passe par une grille spatiale indexée en base
(9 cellules voisines), jamais par toutes les paires.

Photos : visages et plaques floutés côté serveur, avant tout stockage, avec OpenCV (`core/privacy.py`). L'original
n'est jamais écrit sur disque, et le réencodage supprime les métadonnées EXIF. Si la détection échoue, toute la photo
est floutée et le cas reçoit l'alerte `FLOUTAGE_NON_VERIFIE`.

Réel et simulé : deux bases séparées, `data/reel.db` et `data/sim.db`, sans jointure possible. Les cas factices,
dépotoirs fictifs et routes coupées de la simulation ne vont que dans `sim.db`. Ils n'apparaissent jamais dans un
export réel ni dans un fichier OSM.

## Plan de gestion et épreuve en direct

`POST /api/plans` calcule les points de regroupement (KMeans pondéré sur les bâtiments) et les tournées des camions
(OR-Tools, limite de 5 s lue dans la configuration). Il accepte des événements :

| Événement | Effet |
|---|---|
| `truck_down` (`vehicle_id`) | Recalcul partiel à partir du plan précédent : seuls les arrêts du camion perdu sont redistribués ; ceux qui ne trouvent pas de place sont listés dans `postponed`, à part de `unserved`. |
| `rain` | Vue « pluie » du réseau : voies non revêtues ×2,5, voies près des cours d'eau OSM coupées. |
| `new_district` (`territory_id`) | Ajoute un quartier de `data/territories.geojson` : bâtiments, demande, points. |
| `cut_roads` | Arêtes retirées d'une copie du réseau, pour ce calcul seulement. Les points devenus inaccessibles sont listés. |

Contrôles après chaque calcul : capacité, budget, véhicules, durée, réseau, et chaque point servi ou listé avec sa
raison. `checks.ok` est faux si plus de 10 % des points ne sont pas desservis : un plan largement non servi n'est
jamais « vert ». Replis : glouton si OR-Tools échoue, vol d'oiseau ×1,4 si une distance manque, plan vide valide en
dernier recours. Les plans et scénarios sont enregistrés en base et survivent au redémarrage.

La simulation (`core/sim/model.py`, Mesa 3.5.2) fait agir 4 acteurs, avec 2 ou 3 règles chacun. Elle produit trois
chiffres : la part des déchets ramassée, le coût et les dépotoirs restants. Tous ses coefficients sont dans la
section `hypotheses` de la configuration, étiquetés « hypothèse non mesurée ».

## Paramètres et réglages par commune

Toutes les valeurs sont dans [config/commune_config.json](config/commune_config.json) : paramètres et leurs bornes
(`params`, `bounds` ; hors bornes = ramené à la borne avec un avertissement), modèle, réseau, solveur, tri, floutage,
hypothèses de simulation, chemins des données et des bases. Chaque section porte une note `_note`.

Changer de commune sans toucher au code :

```bash
COMMUNE_CONFIG=config/commune_config.koudougou.json ./scripts/run.sh
```

Le centre, les paramètres, la limite de la ville, le secteur et les bases changent. Les routes de Koudougou ne sont
pas téléchargées : le plan passe en mode « secours », `checks.ok` est faux, et un message demande de lancer une fois
`COMMUNE_CONFIG=config/commune_config.koudougou.json python -m core.geo.download --pilot`.

## Données et licences

| Données | Source | Licence | Fichier |
|---|---|---|---|
| Routes, bâtiments du secteur et de deux quartiers | OpenStreetMap (Overpass) | ODbL-1.0 | `data/processed/` |
| Plans d'eau, cours d'eau | OpenStreetMap | ODbL-1.0 | `data/water_bodies.geojson`, `data/processed/waterways.geojson` |
| Limite communale | OpenStreetMap | ODbL-1.0 | `data/raw/boundary.geojson` |
| Quartiers ajoutables | Nœuds OSM `place=suburb`, emprise approximative (cellule de Voronoï) | ODbL-1.0 | `data/territories.geojson` |
| Signalements vérifiés (export) | Ce projet | ODbL-1.0 | `GET /api/export/reports.geojson`, `data/export/` |
| Jeux fictifs | `scripts/make_synthetic.py`, étiquetés `synthetic` | ODbL-1.0 | `data/mock/*.geojson` |

Toutes ces données sont versionnées : un clone neuf a un plan complet sans téléchargement. Pour les reproduire,
lancer `python -m core.geo.download --pilot`, `python -m scripts.extend_districts`, `python -m scripts.build_water`
et `python -m scripts.make_secteur`.

Les signalements de démonstration sont SIMULÉS et étiquetés comme tels. Ils ne sont jamais versés dans OpenStreetMap.
L'export OSM est un fichier à relire dans JOSM ; le logiciel n'envoie jamais rien à OpenStreetMap.

## Limites assumées

- **Bâtiments OSM, pas Open Buildings.** Les bâtiments OSM de Ouagadougou sont denses, se téléchargent avec la même
  chaîne que les routes et ont une licence claire (ODbL). Open Buildings n'a pas été intégré faute de temps ; ses
  conditions d'utilisation restent à vérifier.
- **Population répartie à la surface.** Seuls le secteur et deux quartiers ont leurs bâtiments. La population d'un
  territoire vaut donc la population de la commune multipliée par sa part de surface (densité supposée uniforme,
  `model.territory_population_method`). C'est une hypothèse non mesurée.
- **Quartiers approximatifs.** OSM n'a pas de limites de quartier à Ouagadougou. Le troisième quartier (Tampouy) n'a
  pas pu être téléchargé, le serveur Overpass public étant saturé : il reste proposé, mais sans bâtiments, et le plan
  le signale par un avertissement.
- **Tricycles non optimisés.** Le réseau des tricycles est construit, mais seules les tournées des camions sont
  calculées. Un point accessible seulement en tricycle est déclaré non desservi, avec la raison.
- **Floutage de fiabilité limitée.** Cascades Haar et détecteur de zones de plaque. Les résultats chiffrés sur 7 images
  sont dans [docs/mesures.md](docs/mesures.md) ; aucun taux général n'est annoncé.
- **Ville 3D partielle.** Emprises des bâtiments et routes OSM du secteur pilote et des quartiers téléchargés ; hauteurs
  estimées (27 seulement balisées dans OSM), arbres illustratifs. Une autre commune s'affiche en carte 2D tant que sa
  ville 3D n'a pas été préparée (`web/tools/build_city_data.py`).
- **Fond de carte en ligne pour la 2D.** La ville 3D est locale ; la vue 2D de secours affiche les tuiles OpenStreetMap
  en ligne (« © OpenStreetMap contributors »). Sans réseau, cette carte 2D est blanche ; l'API, les calculs et la page
  citoyen (service worker, file locale) continuent.
- **Doublon par renvoi.** `POST /api/reports` n'a pas de clé d'idempotence : si une réponse se perd, le renvoi
  automatique ajoute un signalement au même dépotoir (« signalé N + 1 fois ») au lieu d'en créer un autre.
- **Mesures.** Les temps de [docs/mesures.md](docs/mesures.md) sont mesurés par `python -m scripts.bench`. Aucun
  pourcentage n'est publié sans cette mesure.

## Organisation du code

| Dossier | Rôle |
|---|---|
| `api/` | FastAPI : `main.py` (erreurs, config), `reports.py` (cycle de vie, tri, exports), `plans.py` (plans, simulation, scénarios), `roles.py` |
| `core/lifecycle.py` | Machine à états et historique |
| `core/db.py` | `get_db("reel" \| "sim")`, schéma commun |
| `core/validation/` | Tri automatique et grille anti-doublon |
| `core/privacy.py` | Floutage des visages et des plaques |
| `core/geo/`, `core/optim/` | Réseau, points de regroupement, tournées, événements |
| `core/sim/` | Simulation Mesa |
| `core/config.py` | Seul lecteur de la configuration (`COMMUNE_CONFIG`) |
| `scripts/` | Lancement, préparation des données, mesures, exports, matrice de contribution |

Contributions et briques réutilisées : [docs/contribution.md](docs/contribution.md).
