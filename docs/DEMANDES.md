# Demandes entre membres

Une ligne par demande : date, de qui, pour qui, ce qui est demandé, pourquoi.

| Date | De | Pour | Demande | Pourquoi | État |
|---|---|---|---|---|---|
| 2026-11-16 | A | Tous | Ajouter à la racine un `pytest.ini` contenant `[pytest]` puis `pythonpath = .` | Sans lui, `pytest tests/ -q` ne trouve pas le paquet `core` (en attendant : `python -m pytest tests/ -q`) | ouverte |
| 2026-11-16 | A | Tous | Ajouter `data/processed/*.pkl` et `data/processed/*.npz` au `.gitignore` | Fichiers générés lourds (54 Mo pour le graphe) : régénérés par `python -m core.geo.download` | ouverte |
| 2026-11-16 | A | Tous | Contrat, section 5 : ajouter `totals.uncollected_kg` (part des non-abonnés des territoires actifs, kg par passage, `estimated`) | Demandé pour la simulation de C | faite (contrat v2) |
| 2026-11-16 | A | Tous | Contrat, section 5 : `routes[].vehicle` vaut `truckN_tripM` (une tournée par rotation, `model.truck_trips_per_day`) ; `broken_trucks` reste `truckN` | Plusieurs tournées par camion et par jour | faite (contrat v2) |
| 2026-11-16 | A | Tous | Configuration : `model.max_walk_m` remplacé par `model.precollect_radius_m` ; `network.rain_waterway_types` renommé `network.flood_waterway_types` ; ajout de `model.truck_trips_per_day`, `cell_size_m`, `pilot_territory_ids`, `pilot_square_m` (hypothèses) | Corrections du modèle | faite (contrat v2) |
| 2026-11-16 | A | B | `compute_plan` ne calcule la demande que pour les territoires actifs (zone pilote + `params.extra_territories`) ; un quartier ajouté doit être écrit dans `paths.territories` avec un `id` (ou passé comme Feature dans `extra_territories`) | Zone d'étude | ouverte |
| 2026-11-16 | A | B, C | Contrat v2 : lire `ignored_reports`, `collection_points[].type` (center/dumpsite) et `checks.network_ok` ; `solver.max_collection_points` passe à 120 | Dépotoirs = arrêts ponctuels, rien ne disparaît en silence | ouverte |
