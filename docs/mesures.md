# Mesures reproductibles

Générées le 2026-11-18 01:12 UTC par `python -m scripts.bench` (relançable, une commande).
Machine : 11th Gen Intel(R) Core(TM) i3-1115G4 @ 3.00GHz, 4 cœurs logiques, Linux 7.0.0-30-generic, Python 3.12.3.
Temps médian sur 5 essais sauf mention ; réseau chargé une fois avant les mesures (premier calcul complet, chargement compris : 1.2 s). Secteur pilote, configuration du dépôt.
Signalements : synthétiques (`scripts/make_synthetic.py`, graine fixe), statut accepted. Valeurs `observed` sur cette machine.

| Mesure | Variante | Médiane | Résultat | Ce que ça montre |
|---|---|---|---|---|
| 0. Plan par défaut | compute_plan(config.params, []) | 0.31 s | optimized, 29/29 points servis (100.0%) ; checks.ok = True ; unserved_ratio = 0.0 | Critère de cohérence : au moins 90 % des points servis et checks.ok vrai. |
| 1. Dijkstra 60 sources | NetworkX, une source à la fois | 0.89 s | graphe NetworkX construit à part en 0.03 s |  |
|  | SciPy, un appel | 0.06 s | écart max des distances 0.000 m | Même vue, mêmes sources : SciPy prend 16.0 fois moins de temps que NetworkX sur cette machine. |
| 2. Placement, k = 46 | KMeans sur 26397 bâtiments | 0.13 s | 100.0% de la demande à moins de 1500 m |  |
|  | KMeans sur 1741 cellules de 100 m | 0.03 s | 100.0% de la demande à moins de 1500 m | Même zone et même k : les cellules prennent 3.9 fois moins de temps, couverture mesurée dans la colonne Résultat. |
| 3. Matrice 29 × 29 | à froid (cache vide) | 0.027 s | 1 appel Dijkstra |  |
|  | cache rempli | 0.000 s | 0 appel Dijkstra | Avec le cache, la matrice est relue sans Dijkstra ; il reste le temps de lecture des lignes. |
| 4. Panne de truck2 | calcul complet | 0.31 s | optimized, 29/29 points servis |  |
|  | recalcul partiel | 0.05 s | partial, 29/29 points servis | Le mode et le nombre de points servis sont ceux du plan gardé (le partiel lance aussi le complet s'il laisse des points non servis). |
| 5. +20 signalements | calcul complet | 0.63 s | optimized, 49/49 points servis |  |
|  | recalcul partiel | 0.08 s | partial, 49/49 points servis | Partiel 0.08 s contre complet 0.63 s ; le partiel lance aussi le complet s'il laisse des points non servis, d'où un temps qui peut dépasser celui du complet. |
| 6. 100 signalements | compute_plan sans présélection (avant) | 4.77 s | 63 arrêts dépotoirs ; optimized, 70/92 points servis |  |
|  | compute_plan avec présélection et remplissage (après, matrice sur k) | 1.38 s | 100 signalements -> 63 arrêts dépotoirs ; optimized, 67/92 points servis ; camions nécessaires (estimation) : 15 | Avant / après présélection et remplissage : 4.77 s -> 1.38 s. |
|  | matrice sur n = 100 signalements | 0.09 s | 5 essai(s) |  |
| 6. 1000 signalements | compute_plan sans présélection (avant) | 5.28 s | 289 arrêts dépotoirs ; optimized, 34/318 points servis |  |
|  | compute_plan avec présélection et remplissage (après, matrice sur k) | 1.03 s | 1000 signalements -> 289 arrêts dépotoirs ; optimized, 41/318 points servis ; camions nécessaires (estimation) : 97 | Avant / après présélection et remplissage : 5.28 s -> 1.03 s. |
|  | matrice sur n = 1000 signalements | 0.94 s | 1 essai(s) (limité : durée) |  |
| 6. 10000 signalements | compute_plan sans présélection (avant) | 8.80 s | 2718 arrêts dépotoirs ; optimized, 34/2747 points servis |  |
|  | compute_plan avec présélection et remplissage (après, matrice sur k) | 1.46 s | 10000 signalements -> 2718 arrêts dépotoirs ; optimized, 40/2747 points servis ; camions nécessaires (estimation) : 907 | Avant / après présélection et remplissage : 8.80 s -> 1.46 s. |
|  | matrice sur n = 10000 signalements | non mesuré | limité : 10000 sources Dijkstra, trop long pour ce banc | compute_plan ne calcule la matrice que sur les arrêts (k), regroupés au-delà de solver.max_dumpsite_stops ; la matrice sur n est mesurée à part pour comparer. |
| 6. population 0 | compute_plan, 100 signalements | 1.13 s | optimized, 60/63 points servis ; 0 centre(s) ; contrôles en échec | Population 0 sur le vrai réseau : seuls les dépotoirs sont servis. |
| 6. 46 points imposés | compute_plan | 0.49 s | optimized, 46/46 points servis |  |
| 6. 120 points imposés | compute_plan | 1.85 s | optimized, 120/120 points servis | Même zone, k imposé ; médiane qui inclut le premier essai à cache froid. |

## Floutage des visages et des plaques (core/privacy.py)

Mesuré par `python -m scripts.bench_blur` sur 7 images libres de droits (tests/data/blur, licences dans LICENSES.md), vérité terrain relevée à l'œil. Couvert = zone de 9 × 9 px autour du centre modifiée de plus de 8 niveaux de gris.

| Image | Scène | Visages couverts | Plaques couvertes | Zones floutées | Part de l'image floutée | Durée |
|---|---|---|---|---|---|---|
| group.jpg | photo de groupe, 7 visages de face | 7/7 | 0/0 | 11 | 15.4% | 1150 ms |
| face1.jpg | portrait, 1 visage | 1/1 | 0/0 | 2 | 5.9% | 903 ms |
| car_504.jpg | voiture vue de l'arrière dans la rue, 1 plaque lisible, passants lointains non identifiables | 0/0 | 1/1 | 2 | 14.5% | 845 ms |
| car_lada.jpg | voiture vue de l'arrière, 2 plaques lisibles (une troisième, lointaine, illisible) | 0/0 | 2/2 | 4 | 6.0% | 991 ms |
| street1.jpg | rue de Ouagadougou, mur, aucune personne ni véhicule | 0/0 | 0/0 | 1 | 0.2% | 929 ms |
| street3.jpg | rue de Ouagadougou vue d'en haut, personnes et véhicules trop lointains pour être identifiés | 0/0 | 0/0 | 1 | 2.3% | 652 ms |
| plate_swiss.jpg | gros plan d'une plaque seule (cas limite : la plaque remplit l'image) | 0/0 | 0/1 | 0 | 0.0% | 55 ms |

Total sur ce petit jeu : visages couverts 8/8, plaques couvertes 3/4. Sept images ne suffisent pas à estimer un taux de détection général : aucun pourcentage n'est annoncé au-delà de ces comptes. Les zones floutées en trop (panneaux, écussons) sont acceptées : la règle est de flouter trop plutôt que pas assez.
