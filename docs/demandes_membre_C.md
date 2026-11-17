# Demandes du membre C (hors périmètre strict)

Périmètre autorisé pour cette tâche : `core/sim/` et `web/dashboard/` uniquement.
Tout ce qui suit **n'a pas été modifié** et doit être traité par le membre
responsable. Aucune valeur manquante n'a été inventée dans la configuration :
les valeurs C sont déclarées dans `core/sim/hypotheses.py` et étiquetées
« à valider » dans la sortie de `run_scenario`.

| Date | De | Pour | Demande | Pourquoi | État |
|---|---|---|---|---|---|
| 2026-11-17 | C | A (configuration) | Ajouter `model.brigade_radius_m` (mètres) à `config/commune_config.json` | Le rayon de patrouille doit venir de la configuration, pas d'un défaut code. Valeur C temporaire : 500 m, marquée « défaut membre C (clé absente de la configuration) ». | ouverte |
| 2026-11-17 | C | A (configuration) | Ajouter `model.brigade_patrols_per_day`, `model.brigade_success_rate`, `model.menage_dump_rate_served`, `model.menage_dump_rate_unserved`, `model.precollect_pass_rate`, `model.precollect_breakdown_rate` | Ces 7 règles simples pilotent les 4 acteurs. Valeurs C temporaires dans `core/sim/hypotheses.py::DEFAUTS_C`, toutes étiquetées « à valider ». | ouverte |
| 2026-11-17 | C | A (données) | Fournir `data/mock/batiments.geojson` (points ou polygones avec `lat`/`lon`) | Les distances « point de regroupement à N m » sont aujourd'hui synthétiques, bornées par `model.precollect_radius_m`. Des bâtiments réels rendraient la carte et les distances vérifiables. | ouverte |
| 2026-11-17 | C | A (données) | Fournir `data/mock/routes.geojson` (LineString) | Le fond de carte utilise aujourd'hui `plan_real.json.routes[].geometry` (données réelles du plan) et `zones.geojson` (placeholder). Un GeoJSON de routes dédié améliorerait le fond sans dépendre du plan optimisé. | ouverte |
| 2026-11-17 | C | Tous (contrat) | Documenter dans `docs/contracts.md` la signature étendue `run_scenario(params, days, actors_enabled)` en plus de `run_scenario(params, plan, days)`, ainsi que les champs `series`, `agent_states`, `events`, `hypotheses` et `data_tag` | Le contrat v2 ne décrit que l'ancienne signature ; la démo acteurs doit rester compatible. | ouverte |
| 2026-11-17 | C | Backend | Servir `/dashboard/` depuis `api.main:app` et exposer les routes `/api/plan/calculer`, `/api/simulation`, `/api/scenarios` en production | L'API canonique locale ne sert pas le tableau de bord ; seul `scripts/serve_integration.py` fait le pont, en mode test. La démo locale contourne ce point avec `web/dashboard/serve_mock.py`, sans API externe. | ouverte |
| 2026-11-17 | C | Tous (front) | Mutualiser Leaflet dans `web/vendor/leaflet/` | Le périmètre interdit d'écrire hors de `web/dashboard/` : Leaflet 1.9.4 a donc été copié dans `web/dashboard/vendor/leaflet/`. Si la page citoyenne doit l'utiliser aussi, déplacer le dossier et mettre à jour les deux chemins. | ouverte |

## Ce qui a été fait sans toucher au périmètre interdit

- `run_scenario(params, days, actors_enabled)` et l'ancienne signature coexistent dans `core/sim/model.py`.
- Les valeurs absentes de la configuration sont lues depuis `core/sim/hypotheses.py::DEFAUTS_C` et renvoyées dans `hypotheses` avec leur source exacte.
- Le centre de la carte, la commune, la population, les camions, tricycles et le budget viennent de `config/commune_config.json` via `/api/bootstrap` ; aucune coordonnée ni nom de commune n'est écrit en dur dans le tableau de bord.
- Aucun appel réseau sortant : Leaflet est local, le fond est dessiné depuis `data/mock/` et aucune tuile n'est chargée.
