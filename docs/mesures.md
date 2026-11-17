# Mesures du membre A

Générées le 2026-11-16 20:40 UTC par `python -m scripts.bench` (relançable, une commande).
Machine : 11th Gen Intel(R) Core(TM) i7-1165G7 @ 2.80GHz, 8 cœurs logiques, Linux 7.0.0-43-generic, Python 3.12.3.
Temps médian sur 5 essais sauf mention ; réseau chargé une fois avant les mesures (premier calcul complet, chargement compris : 7.8 s). Zone pilote, configuration du dépôt.
Signalements : synthétiques (`scripts/make_synthetic.py`, graine fixe), statut accepted. Valeurs `observed` sur cette machine.

| Mesure | Variante | Médiane | Résultat | Ce que ça montre |
|---|---|---|---|---|
| 1. Dijkstra 60 sources | NetworkX, une source à la fois | 8.43 s | graphe NetworkX construit à part en 0.47 s |  |
|  | SciPy, un appel | 0.56 s | écart max des distances 0.000 m | Même vue, mêmes sources : SciPy prend 15.1 fois moins de temps que NetworkX sur cette machine. |
| 2. Placement, k = 46 | KMeans sur 26285 bâtiments | 0.11 s | 100.0% de la demande à moins de 1500 m |  |
|  | KMeans sur 1740 cellules de 100 m | 0.02 s | 100.0% de la demande à moins de 1500 m | Même zone et même k : les cellules prennent 4.7 fois moins de temps, couverture mesurée dans la colonne Résultat. |
| 3. Matrice 46 × 46 | à froid (cache vide) | 0.450 s | 1 appel Dijkstra |  |
|  | cache rempli | 0.001 s | 0 appel Dijkstra | Avec le cache, la matrice est relue sans Dijkstra ; il reste le temps de lecture des lignes. |
| 4. Panne de truck2 | calcul complet | 0.64 s | optimized, 46/46 points servis |  |
|  | recalcul partiel | 0.72 s | optimized, 46/46 points servis | Le mode et le nombre de points servis sont ceux du plan gardé (le partiel lance aussi le complet s'il laisse des points non servis). |
| 5. +20 signalements | calcul complet | 1.90 s | optimized, 57/66 points servis |  |
|  | recalcul partiel | 2.10 s | partial, 57/66 points servis | Partiel 2.10 s contre complet 1.90 s ; le partiel lance aussi le complet s'il laisse des points non servis, d'où un temps qui peut dépasser celui du complet. |
| 6. 100 signalements | compute_plan sans présélection (avant) | 4.21 s | 54 arrêts dépotoirs ; optimized, 62/100 points servis |  |
|  | compute_plan avec présélection et remplissage (après, matrice sur k) | 1.34 s | 100 signalements -> 54 arrêts dépotoirs ; optimized, 62/100 points servis ; camions nécessaires (estimation) : 18 | Avant / après présélection et remplissage : 4.21 s -> 1.34 s. |
|  | matrice sur n = 100 signalements | 0.99 s | 5 essai(s) |  |
| 6. 1000 signalements | compute_plan sans présélection (avant) | 5.25 s | 261 arrêts dépotoirs ; optimized, 48/307 points servis |  |
|  | compute_plan avec présélection et remplissage (après, matrice sur k) | 1.07 s | 1000 signalements -> 261 arrêts dépotoirs ; optimized, 48/307 points servis ; camions nécessaires (estimation) : 92 | Avant / après présélection et remplissage : 5.25 s -> 1.07 s. |
|  | matrice sur n = 1000 signalements | 9.85 s | 1 essai(s) (limité : durée) |  |
| 6. 10000 signalements | compute_plan sans présélection (avant) | 7.81 s | 2516 arrêts dépotoirs ; optimized, 49/2562 points servis |  |
|  | compute_plan avec présélection et remplissage (après, matrice sur k) | 1.36 s | 10000 signalements -> 2516 arrêts dépotoirs ; optimized, 48/2562 points servis ; camions nécessaires (estimation) : 844 | Avant / après présélection et remplissage : 7.81 s -> 1.36 s. |
|  | matrice sur n = 10000 signalements | non mesuré | limité : 10000 sources Dijkstra, trop long pour ce banc | compute_plan ne calcule la matrice que sur les arrêts (k), regroupés au-delà de solver.max_dumpsite_stops ; la matrice sur n est mesurée à part pour comparer. |
| 6. population 0 | compute_plan, 100 signalements | 1.05 s | optimized, 44/54 points servis ; 0 centre(s) ; contrôles au vert | Population 0 sur le vrai réseau : seuls les dépotoirs sont servis. |
| 6. 46 points imposés | compute_plan | 0.46 s | optimized, 46/46 points servis |  |
| 6. 120 points imposés | compute_plan | 2.01 s | optimized, 120/120 points servis | Même zone, k imposé ; médiane qui inclut le premier essai à cache froid. |
