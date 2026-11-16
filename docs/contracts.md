# Contrat de données — version 2

Version 2 (2026-11-16, membre A, autorisation donnée) : `totals.uncollected_kg`, `ignored_reports`, véhicules `truckN_tripM`,
`collection_points[].type`, `checks.network_ok`, clés de configuration renommées (section 3).

À valider à trois. Après validation, tout changement passe par `docs/DEMANDES.md`.
Tous les échanges sont en JSON, coordonnées en WGS84 (`lat`, `lon` en degrés décimaux),
dates en ISO 8601 UTC, masses en kilogrammes, distances en kilomètres, durées en minutes.

Étiquette de provenance (`source` ou `data_tag`) :
`observed` (vu sur place), `provided` (fourni par la mairie ou le jury), `documented` (source publique citée),
`estimated` (calculé à partir d'hypothèses), `synthetic` (fabriqué pour les tests), `simulated` (sortie de la simulation).

## 1. Signalement (B produit, A et C lisent)
```json
{
  "id": "r001",
  "lat": 12.37,
  "lon": -1.52,
  "size": "small|medium|large",
  "photo_url": null,
  "photo_hash": null,
  "timestamp": "2026-11-17T10:00:00Z",
  "source": "synthetic",
  "status": "pending|accepted|rejected|to_review",
  "trust": 0.0,
  "reason": null,
  "dumpsite_id": null,
  "validated_by": null,
  "validated_at": null
}
```
- `status` n'a que ces quatre valeurs. Un doublon n'est pas un statut : c'est `status: "accepted"`,
  `reason: "duplicate_merged"` et `dumpsite_id` renseigné.
- A ne consomme que les signalements `accepted`, regroupés par `dumpsite_id`.

## 2. Dépotoir validé (B produit, A et C lisent)
```json
{"id": "d001", "lat": 12.37, "lon": -1.52, "size": "medium", "estimated_kg": 800,
 "report_count": 3, "trust": 0.8, "source": "synthetic", "status": "active|cleaned"}
```

## 3. Paramètres (`config/commune_config.json`, modifiables par l'API : `POST /params`)
Voir le fichier. Les clés du bloc `params` sont celles que le jury peut changer en direct :
`population`, `subscription_rate`, `trucks`, `truck_capacity_kg`, `tricycles`, `tricycle_capacity_kg`,
`frequency_per_week`, `budget`, `rainy_season`, `broken_trucks`, `extra_territories`.
- `broken_trucks` contient des camions (`"truck2"`) : toutes leurs tournées du jour sont perdues.
- `extra_territories` : identifiants de `paths.territories` ou Features GeoJSON (section 4).
- Clés du modèle renommées ou ajoutées en version 2 (hypothèses) : `model.max_walk_m` → `model.precollect_radius_m` ;
  `network.rain_waterway_types` → `network.flood_waterway_types` ; nouvelles : `model.truck_trips_per_day`, `model.cell_size_m`,
  `model.pilot_territory_ids`, `model.pilot_square_m`, `model.resnap_max_m`, `solver.max_dumpsite_stops`.

## 4. Territoire / nouveau quartier (jury ou mairie fournit, B reçoit, A intègre)
GeoJSON `Feature` de type `Polygon` ou `MultiPolygon`, propriétés :
```json
{"id": "q_new_1", "name": "Nouveau quartier", "population": 12000, "source": "provided"}
```
Si `population` est absent, A l'estime à partir des bâtiments et marque `estimated`.

## 5. Plan (A produit avec `compute_plan`, B expose par `GET /plan`, C affiche et simule)
```json
{
  "plan_id": "p_20261117T101500Z",
  "computed_at": "2026-11-17T10:15:00Z",
  "mode": "optimized|partial|fallback",
  "compute_ms": 0,
  "params_used": {},
  "collection_points": [
    {"id": "p1", "lat": 12.37, "lon": -1.52, "demand_kg": 0, "access": "truck|tricycle",
     "territory_id": null, "type": "center|dumpsite", "data_tag": "estimated"}
  ],
  "routes": [
    {"vehicle": "truck1_trip1", "type": "truck|tricycle", "stops": ["p1", "p2"],
     "distance_km": 0, "duration_min": 0, "load_kg": 0, "capacity_kg": 0, "cost": 0,
     "geometry": null}
  ],
  "unserved": [
    {"point_id": "p9", "reason": "capacity|budget|access|time|no_route", "detail": "texte en français"}
  ],
  "ignored_reports": [
    {"report_id": "r042", "reason": "Hors de la commune."}
  ],
  "checks": {
    "capacity_ok": true, "budget_ok": true, "vehicles_ok": true, "network_ok": true,
    "every_point_served_or_reported": true, "messages": []
  },
  "totals": {"distance_km": 0, "cost": 0, "collected_kg": 0, "budget_remaining": 0,
             "points_served": 0, "points_unserved": 0, "uncollected_kg": 0},
  "assumptions": ["texte en français"],
  "warnings": []
}
```
- `mode` : `optimized` = solveur complet ; `partial` = recalcul limité aux arrêts touchés ;
  `fallback` = méthode de secours. L'écran affiche toujours le mode.
- `geometry` : `LineString` GeoJSON du trajet sur les routes, ou `null` si indisponible.
- `vehicle` : `truckN_tripM` = M-ième tournée du jour du camion N (chaque tournée part du dépôt et y revient).
- `collection_points[].type` : `center` = point de regroupement (les pré-collecteurs y déposent, les camions le vident) ;
  `dumpsite` = dépotoir validé, arrêt ponctuel (id `d_<id du dépotoir>`).
- `ignored_reports` : tout signalement ou dépotoir non pris en compte, avec sa raison en français (rien ne disparaît en silence).
- `totals.uncollected_kg` : déchets des non-abonnés des territoires actifs, par passage (`estimated`), non collectés ; pour la simulation.
- `checks.network_ok` : aucun trajet n'emprunte une voie absente du réseau utilisé (coupée par la pluie).
- Tout point de regroupement est soit dans une `route`, soit dans `unserved`. Jamais ailleurs.

## 6. Fonctions partagées
```python
# A — core/optim/plan.py
compute_plan(params: dict, reports: list[dict], previous_plan: dict | None = None,
             changed: dict | None = None) -> dict          # renvoie un Plan, ne lève jamais

# A — core/geo/export.py
export_geojson(dumpsites: list[dict]) -> dict              # FeatureCollection, sources non réelles exclues

# C — core/sim/
run_scenario(params: dict, plan: dict, days: int) -> dict  # le plan est obligatoire
```
Avec `previous_plan` sans `changed`, A déduit le changement en comparant `previous_plan.params_used` et les signalements.
`changed` décrit ce qui a changé depuis `previous_plan`, par exemple
`{"broken_trucks": ["truck2"]}`, `{"rainy_season": true}` ou `{"extra_territories": ["q_new_1"]}`.
Sans `previous_plan`, calcul complet.

## 7. Erreurs
Aucune fonction partagée ne lève d'exception vers l'appelant. En cas de problème :
plan en mode `fallback`, `warnings` renseigné, et l'explication dans `checks.messages`.
