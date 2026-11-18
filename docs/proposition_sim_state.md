# Proposition de forme de données — `run_scenario` avec état des agents

Document de travail du membre C. Rien ici n'est déjà dans `docs/contracts.md` :
ce sont les champs **proposés** pour rendre la simulation inspectable et
démontrable. La compatibilité ascendante est conservée :
`run_scenario(params, plan, days)` garde exactement sa sortie historique.

## Signature proposée

```python
run_scenario(
    params: dict | None = None,
    days: int = 7,
    actors_enabled: dict[str, bool] | None = None,
) -> dict
```

L'ancien appel `run_scenario(params, plan, days)` reste accepté : la fonction
détecte le type du deuxième argument (dictionnaire = plan, nombre = jours).

`actors_enabled` : `{"menages": bool, "pre_collecteurs": bool,
"brigade": bool, "mairie": bool}`. Une clé absente vaut `True`.
Retirer un acteur désactive ses règles et déclenche un recalcul immédiat.

## Champs de sortie proposés

```jsonc
{
  "fonction": "run_scenario",
  "data_tag": "simulated",              // toute donnée générée
  "moteur": "mesa 3.x | fallback local (sans Mesa)",
  "graine": 42,
  "days": 7,
  "scenario_id": "s_20261117T...",
  "plan_id": "p_...",                   // si un plan a été fourni
  "source_plan": "plan fourni dans params | plan de démonstration plan_real.json",

  // Les 3 chiffres historiques, inchangés :
  "part_ramassee": 0.893,
  "cout_m_fcfa": 2.837,
  "depotoirs_restants": 6,
  "unite_depotoirs_restants": "foyers synthétiques et dépotoirs du plan (proxy)",

  "actors_enabled": { "menages": true, "pre_collecteurs": true,
                      "brigade": true, "mairie": true },
  "menages_synthetiques": 46,
  "params_used": { /* paramètres réellement utilisés */ },

  "series": [                           // un point par jour
    {
      "jour": 1,
      "part_ramassee": 0.61,
      "cout_m_fcfa": 0.405,
      "depotoirs_restants": 18,
      "budget_restant_m_fcfa": 9.595,
      "kg_ramasses": 812.4,
      "data_tag": "simulated"
    }
  ],

  "agent_states": [                     // un état par jour et par acteur
    {
      "jour": 1,
      "menages": {
        "abonnes": 18, "total": 46, "avec_depot": 9,
        "positions": [                  // pour la carte locale
          {"id": "menage_1", "lat": 12.34, "lon": -1.53, "propre": false}
        ]
      },
      "pre_collecteurs": {
        "en_service": 20, "total": 20, "kg_ramasses": 812.4,
        "remplissage_moyen": 0.31
      },
      "brigade": {
        "patrouilles_actives": 2, "depots_evites": 1,
        "rayon_m": 500.0                // valeur de config, pas un chiffre en dur
      },
      "mairie": {
        "camions_en_service": 10, "camions_total": 10,
        "budget_restant": 9595000,
        "remplissage_centres": [0.2, 0.35]
      }
    }
  ],

  "events": [                           // journal lisible par décision
    {"jour": 1, "acteur": "menages",
     "texte": "Ménage 214 a jeté dans la rue : point de regroupement à 410 m",
     "data_tag": "simulated"},
    {"jour": 2, "acteur": "mairie",
     "texte": "Camion en panne : 6 tournée(s) reportée(s)",
     "data_tag": "simulated"}
  ],

  "indicateurs": {                      // 2 chiffres par acteur pour le panneau UI
    "menages": {"abonnes_pct": 39.1, "depotoirs_crees": 6},
    "pre_collecteurs": {"tonnes_ramassees": 0.812, "remplissage_moyen": 0.31},
    "brigade": {"patrouilles_actives": 2, "depots_evites": 1},
    "mairie": {"budget_restant_m_fcfa": 9.595,
               "camions_en_service": 10, "camions_total": 10}
  },

  "hypotheses": [                       // traçabilité de chaque nombre
    {"cle": "brigade_radius_m", "valeur": 500,
     "source": "défaut membre C (clé absente de la configuration)",
     "note": "hypothèse à valider avec la mairie — demander l'ajout de model.brigade_radius_m"}
  ],

  "agents": [                           // libellés stables pour l'UI
    {"nom": "Ménages", "cle": "menages"},
    {"nom": "Pré-collecteurs", "cle": "pre_collecteurs"},
    {"nom": "Brigade Laabal", "cle": "brigade"},
    {"nom": "Mairie", "cle": "mairie"}
  ]
}
```

## Règles garanties par l'implémentation

- Un point de `series` et un point d'`agent_states` par jour simulé, sans trou.
- Aucune valeur pré-calculée : tout est produit par `core/sim/actors.py`.
- `data_tag = "simulated"` sur chaque donnée générée, y compris dans le journal.
- Si un champ manque ou si le moteur échoue, le dernier état valide est renvoyé
  avec `data_status = "ancien"` et un message clair (côté `serve_mock.py`) ;
  aucun chiffre n'est remplacé par une valeur inventée.

## Mesure de retrait des acteurs (graine 42, 7 jours, données mock)

| Acteur retiré | `part_ramassee` | `cout_m_fcfa` | `depotoirs_restants` |
|---|---|---|---|
| Aucun (référence) | 0.893 | 2.837 | 6 |
| Ménages | 1.000 | 2.837 | 0 |
| Pré-collecteurs | 0.679 | 2.837 | 18 |
| Brigade Laabal | 0.804 | 2.837 | 11 |
| Mairie | 0.482 | 0.000 | 29 |

Chaque retrait modifie au moins un des trois chiffres. Le coût ne bouge que
quand la mairie est retirée : c'est la seule règle qui finance les tournées.
