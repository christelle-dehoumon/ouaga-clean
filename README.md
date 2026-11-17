# Ouaga Propre

Outil libre d'aide à la décision pour l'assainissement de Ouagadougou (Hackathon des Universités 2026, challenge 1).

## Installation (partie A : géographie et optimisation)

Python 3.12 (environnement de dev : 3.12.3). Les versions sont épinglées dans `requirements.txt` ; ce sont celles de
l'environnement où les tests A passent :

| Paquet | Version épinglée | Minimum vérifié | Pourquoi |
|---|---|---|---|
| ortools | 9.15.6755 | 9.12 | `routing_enums_pb2.RoutingSearchStatus` absent en 9.11.4210 |
| osmnx | 2.1.2 | 2.0 | `simplify_graph(node_attrs_include=...)` absent en 1.9.4 |
| numpy | 2.5.5 | | |
| osmium (pyosmium) | 4.3.2 | | lecture du fichier `.osm.pbf` (cours d'eau, bâtiments) |
| scipy, networkx, shapely, geopandas, pyproj, scikit-learn, pytest | voir `requirements.txt` | | |

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests/test_a_*.py -q
```

Avec `uv` : `uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt`.

Une version d'OR-Tools trop ancienne arrête l'application dès l'import de `core.optim.tournees` avec le message
« Version d'OR-Tools incompatible … attendu >= 9.12 », au lieu de basculer en secours sans le dire. Même chose pour OSMnx
(« attendu >= 2.0 ») au lancement de `python -m core.geo.download` ; OSMnx ne sert qu'à cette préparation unique des données.

### osmium (pyosmium)

`pip install osmium==4.3.2` installe une roue précompilée sur Linux x86_64, macOS et Windows pour Python 3.12 : rien d'autre
à faire. S'il n'y a pas de roue pour la machine (autre architecture, autre version de Python), pip compile libosmium, ce
qui demande des paquets système, par exemple sous Debian ou Ubuntu :

```bash
sudo apt install build-essential cmake libboost-dev libexpat1-dev zlib1g-dev libbz2-dev liblz4-dev
```

Vérifier : `.venv/bin/python -c "import osmium; print(osmium.__version__)"`.

## Démarrage rapide

Ouaga Propre aide à planifier la collecte et à visualiser des scénarios d'assainissement pour Ouagadougou.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Lancer l'application :

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Les pages sont disponibles sur `/citizen/` et `/dashboard/`.

Lancer les tests :

```bash
PYTHONPATH=. pytest -q
```

## Organisation

- `api/` : API de l'application
- `core/geo/` : données et traitements géographiques
- `core/optim/` : optimisation des tournées et des points de collecte
- `core/validation/` : validation des signalements
- `core/sim/` : simulation
- `web/citizen/` : interface citoyenne
- `web/dashboard/` : tableau de bord
- `config/` : configuration de la commune
- `data/` : données et exemples

Pour changer de commune, utilisez la configuration `config/commune_config.koudougou.json`.

## Données et licence

Les données OpenStreetMap sont soumises à l'ODbL. Les conditions d'utilisation des données Open Buildings sont à vérifier
auprès de leur fournisseur avant toute réutilisation.

Le projet est distribué sous licence Apache-2.0 (voir [LICENSE](LICENSE)).

Les signalements et paramètres présentés pour la démonstration sont **SIMULÉS** ou des **HYPOTHÈSES**. Ils ne sont jamais
versés dans OpenStreetMap.
