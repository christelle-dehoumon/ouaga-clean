# Scénarios et plan de gestion de la zone pilote

Générés le 2026-11-18 08:23 UTC par `python -m scripts.scenarios_rapport` (x86_64, Python 3.12.3, simulation mesa 3.5.2).
Configuration : `commune_config.json` (Ouagadougou). Paramètres : 10 camions de 5 000 kg, 3 passages par semaine, population 3 000 000, abonnement 40 %, budget 10 000 000 FCFA par jour de collecte.
Les chiffres de la simulation reposent sur des hypothèses non mesurées (configuration, section hypotheses).

| Scénario | Mode | Points servis | Non desservis | Reportés | Camions utilisés | Distance (km) | Coût d'un passage (FCFA) | Collecté par passage (t) | Calcul (ms) | Part ramassée, 7 j (simulée) | Dépotoirs restants (simulés) | Coût 7 j (simulé, FCFA) | checks.ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Défaut (configuration) | complet | 29/29 | 0 | 0 | 6 | 127,9 | 191 827 | 79,3 | 290 | 34,7 % | 27 | 575 481 | oui |
| Panne de truck1 (recalcul partiel) | partiel | 29/29 | 0 | 0 | 6 | 127,9 | 191 826 | 79,3 | 40 | 31,6 % | 27 | 575 478 | oui |
| Flotte réduite : 6 camions | complet | 29/29 | 0 | 0 | 6 | 127,1 | 190 635 | 79,3 | 258 | 24,9 % | 28 | 571 905 | oui |
| 6 camions + panne de truck1 | partiel | 25/29 | 0 | 4 | 5 | 109,5 | 164 191 | 66,9 | 43 | 22,7 % | 29 | 492 573 | oui |
| Saison des pluies | complet | 28/29 | 1 | 0 | 7 | 152,3 | 228 481 | 77,7 | 263 | 29,3 % | 27 | 685 443 | oui |
| Pluie + nouveau quartier Kalgodin | complet | 37/37 | 0 | 0 | 8 | 192,9 | 289 382 | 92,9 | 386 | 25,1 % | 35 | 868 146 | oui |
| Nouveau quartier Paglayiri | complet | 37/37 | 0 | 0 | 8 | 160,0 | 239 944 | 96,8 | 391 | 27,5 % | 35 | 719 832 | oui |

## Plan de gestion par défaut de la zone pilote

29 points de regroupement, 18 tournées (trajets de camions), 127,9 km, coût d'un passage 191 827 FCFA, 79,3 t collectées par passage ; masse non collectée (ménages non abonnés) 118,9 t par passage.

| Trajet | Arrêts | Distance (km) | Durée (min) | Charge (kg) |
|---|---|---|---|---|
| truck1_trip1 | 2 | 7,8 | 39 | 4 816 |
| truck1_trip2 | 2 | 6,0 | 34 | 4 936 |
| truck1_trip3 | 1 | 4,8 | 22 | 3 708 |
| truck2_trip1 | 1 | 3,9 | 20 | 3 918 |
| truck2_trip2 | 1 | 5,2 | 23 | 3 696 |
| truck2_trip3 | 1 | 3,7 | 19 | 4 293 |
| truck3_trip1 | 2 | 9,5 | 43 | 4 981 |
| truck3_trip2 | 2 | 7,7 | 38 | 4 930 |
| truck3_trip3 | 2 | 7,8 | 39 | 4 386 |
| truck4_trip1 | 2 | 3,7 | 29 | 3 930 |
| truck4_trip2 | 2 | 10,1 | 44 | 4 116 |
| truck4_trip3 | 2 | 9,0 | 42 | 4 960 |
| truck5_trip1 | 2 | 8,7 | 41 | 4 519 |
| truck5_trip2 | 1 | 7,4 | 28 | 4 492 |
| truck5_trip3 | 1 | 9,6 | 33 | 4 218 |
| truck6_trip1 | 1 | 8,6 | 31 | 4 567 |
| truck6_trip2 | 2 | 7,8 | 39 | 4 227 |
| truck6_trip3 | 2 | 6,4 | 35 | 4 561 |
