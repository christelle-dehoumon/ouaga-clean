# Contrat d'API (v1.0)

Base : `https://<hôte>:8443/api`. Réponses JSON ; erreurs `{"detail": "..."}` en français, jamais de trace Python
(400, 401, 403, 404, 409, 422, 500). Documentation interactive : `/docs`.

## Rôles

Pas de compte. Brigade et mairie envoient leur code dans l'en-tête `X-Role-Code`.
Codes : variables `BRIGADE_CODE` et `MAIRIE_CODE` ; sans elles, codes de démonstration de la configuration
(`brigade-demo`, `mairie-demo`, publics). Code absent ou faux : 401. Rôle sans droit : 403. Le citoyen n'a rien.

## Signalements et cycle de vie

| Méthode | Chemin | Rôle | Effet |
|---|---|---|---|
| POST | `/reports` | public | `{photo_b64, lat, lon, reported_at}` (champs en plus ignorés) ; toujours 200 `{"ok": true}` |
| POST | `/reports?mode=sim` | mairie | « Simuler un cas » : même tri, écrit dans sim.db seulement |
| GET | `/reports?mode=reel\|sim&statut=&type=&inclure_nettoyes=1&depuis=<iso>` | brigade, mairie | brigade : forcé à `a_verifier` ; mairie : tout sauf `nettoye` par défaut ; `depuis` pour le sondage des nouveaux cas |
| POST | `/reports/{id}/decision` `{action: "confirmer"\|"rejeter"}` | brigade | à vérifier -> confirmé / rejeté (ou nettoyé / rejeté pour un nettoyage) |
| POST | `/reports/{id}/mark-clean` | mairie | confirmé -> type nettoyage, à vérifier |
| POST | `/reports/{id}/reset` | mairie | rejeté -> à vérifier (même type), sans note |
| GET | `/reports/{id}/history` | brigade, mairie | `[{qui, quand, action, de, vers}]`, une ligne par transition |
| GET | `/reports/{id}/photo?code=` | brigade, mairie | photo floutée (JPEG) ; `code` accepté en paramètre pour une balise `<img>` |
| GET | `/ecartes?mode=` | mairie | envois écartés d'office avec motif |
| POST | `/ecartes/{id}/reset` | mairie | écarté -> nouveau cas à vérifier (alerte `ECARTE_REMIS`) |

Tout cas porte : `id, type (depotoir|nettoyage), statut (a_verifier|confirme|rejete|nettoye), lat, lon, reported_at,
alertes, alertes_libelles, nb_signalements, source (reel|sim), photo_url`. Ajouter `?mode=sim` aux routes pour la base simulée.

Transitions (core/lifecycle.py) : toute autre transition donne 409 ; rejouer une décision donne 409.

Alertes du tri : `DOUBLON_PROBABLE, PHOTO_DEJA_VUE, PRES_PLAN_EAU, HORS_SECTEUR, GPS_IMPRECIS, FLOUTAGE_NON_VERIFIE,
ECARTE_REMIS, CAS_SIMULE, MIGRE_SANS_PHOTO`. Motifs d'écart : `TROP_VOLUMINEUX, FORMAT_INVALIDE, POSITION_INVALIDE,
HORS_VILLE, DATE_INVALIDE, DATE_FUTURE, DATE_TROP_ANCIENNE, PHOTO_ABSENTE, PHOTO_INVALIDE, PHOTO_TROP_LOURDE, ERREUR_INTERNE`.

## Plan, simulation, scénarios (mairie)

`POST /plans`
```json
{"mode": "reel", "params": {"trucks": 8, "budget": 5000000},
 "events": [{"type": "truck_down", "vehicle_id": "truck3"}, {"type": "rain"},
            {"type": "new_district", "territory_id": "kalgodin"}],
 "cut_roads": [{"edge_id": "1234-5678"}, {"lat": 12.36, "lon": -1.53}],
 "previous_plan_id": "p_20261118T010000Z"}
```
Réponse : `plan_id, mode (complet|partiel|secours), engine_mode, compute_ms, params_used, vehicles[{id, status, trips}],
routes[{vehicle_id, stops, path: [[lat, lon], ...], distance_km, load_kg, duration_min}], consolidation_points,
unserved[{point_id, reason, detail}], postponed[{id, reason}], cut_roads, inaccessible_due_to_cuts,
checks{ok, unserved_count, unserved_ratio, postponed_count, capacity_ok, budget_ok, vehicles_ok, network_ok, messages},
totals, assumptions, warnings`.
`checks.ok` est faux dès que plus de `solver.max_unserved_ratio` (10 %) des points ne sont pas desservis.

| Méthode | Chemin | Effet |
|---|---|---|
| GET | `/plans/{id}` | plan enregistré (survit au redémarrage) |
| POST | `/plans/{id}/simulation` `{days, seed, actors_enabled}` | simulation Mesa : `part_ramassee, cout_fcfa, depotoirs_restants, series, indicateurs, hypotheses` |
| GET | `/plans/{id}/export` | GeoJSON du plan (fichier) |
| GET | `/scenarios` | historique de chaque calcul (paramètres, événements, résultats, durée, mode, horodatage) |
| POST | `/scenarios` | plan + simulation en un appel (même corps que `/plans`, plus `days`, `label`) |
| GET | `/scenarios/compare?a=&b=` | écarts B − A : part ramassée, coût, non servis, reportés, dépotoirs restants, durée |
| POST | `/sim/dumpsites` `{lat, lon, kg?}` | dépotoir fictif (sim.db) |
| POST | `/sim/roads/cut` `{edge_id \| lat, lon, cut}` | coupe ou rouvre une route en simulation (sim.db) |

## Divers

| Méthode | Chemin | Rôle | Effet |
|---|---|---|---|
| GET | `/health` | public | état, commune, moteur de simulation, taille du réseau |
| GET | `/config` | public | `{commune, center: [lat, lon], zoom, params: {nom: {min, max, default, unit, label}}, territories}` |
| GET | `/territories` | public | quartiers ajoutables `[{id, nom, approximate}]` |
| GET | `/export/reports.geojson` | mairie | cas réels confirmés ou nettoyés, sans photo, licence ODbL |
| GET | `/export/reports.osm` | mairie | fichier OSM à relire dans JOSM (jamais envoyé à OSM) |
| POST | `/admin/reset` | mairie | vide sim.db ; reel.db seulement avec `?confirm=reel` |
