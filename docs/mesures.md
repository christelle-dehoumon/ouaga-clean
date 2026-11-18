# Mesures du membre A

Générées le 2026-11-18 00:37 UTC par `python -m scripts.bench` (relançable, une commande).
Machine : 11th Gen Intel(R) Core(TM) i3-1115G4 @ 3.00GHz, 4 cœurs logiques, Linux 7.0.0-30-generic, Python 3.12.3.
Temps médian sur 5 essais sauf mention ; réseau chargé une fois avant les mesures (premier calcul complet, chargement compris : 0.8 s). Zone pilote, configuration du dépôt.
Signalements : synthétiques (`scripts/make_synthetic.py`, graine fixe), statut accepted. Valeurs `observed` sur cette machine.

| Mesure | Variante | Médiane | Résultat | Ce que ça montre |
|---|---|---|---|---|
| 1. Dijkstra 60 sources | NetworkX, une source à la fois | 0.42 s | graphe NetworkX construit à part en 0.02 s |  |
|  | SciPy, un appel | 0.03 s | écart max des distances 0.000 m | Même vue, mêmes sources : SciPy prend 15.4 fois moins de temps que NetworkX sur cette machine. |
| 2. Placement, k = 46 | KMeans sur 26318 bâtiments | 0.10 s | 100.0% de la demande à moins de 1500 m |  |
|  | KMeans sur 1739 cellules de 100 m | 0.03 s | 100.0% de la demande à moins de 1500 m | Même zone et même k : les cellules prennent 3.2 fois moins de temps, couverture mesurée dans la colonne Résultat. |
| 3. Matrice 37 × 37 | à froid (cache vide) | 0.019 s | 1 appel Dijkstra |  |
|  | cache rempli | 0.001 s | 0 appel Dijkstra | Avec le cache, la matrice est relue sans Dijkstra ; il reste le temps de lecture des lignes. |
| 4. Panne de truck2 | calcul complet | 0.38 s | optimized, 37/37 points servis |  |
|  | recalcul partiel | 0.05 s | partial, 37/37 points servis | Le mode et le nombre de points servis sont ceux du plan gardé (le partiel lance aussi le complet s'il laisse des points non servis). |
| 5. +20 signalements | calcul complet | 0.78 s | optimized, 57/57 points servis |  |
|  | recalcul partiel | 0.09 s | partial, 57/57 points servis | Partiel 0.09 s contre complet 0.78 s ; le partiel lance aussi le complet s'il laisse des points non servis, d'où un temps qui peut dépasser celui du complet. |
| 6. 100 signalements | compute_plan sans présélection (avant) | 5.01 s | 52 arrêts dépotoirs ; optimized, 62/89 points servis |  |
|  | compute_plan avec présélection et remplissage (après, matrice sur k) | 1.61 s | 100 signalements -> 52 arrêts dépotoirs ; optimized, 63/89 points servis ; camions nécessaires (estimation) : 16 | Avant / après présélection et remplissage : 5.01 s -> 1.61 s. |
|  | matrice sur n = 100 signalements | 0.05 s | 5 essai(s) |  |
| 6. 1000 signalements | compute_plan sans présélection (avant) | 5.24 s | 277 arrêts dépotoirs ; optimized, 36/314 points servis |  |
|  | compute_plan avec présélection et remplissage (après, matrice sur k) | 1.28 s | 1000 signalements -> 277 arrêts dépotoirs ; optimized, 47/314 points servis ; camions nécessaires (estimation) : 95 | Avant / après présélection et remplissage : 5.24 s -> 1.28 s. |
|  | matrice sur n = 1000 signalements | 0.47 s | 1 essai(s) (limité : durée) |  |
| 6. 10000 signalements | compute_plan sans présélection (avant) | 8.90 s | 2690 arrêts dépotoirs ; optimized, 32/2727 points servis |  |
|  | compute_plan avec présélection et remplissage (après, matrice sur k) | 2.40 s | 10000 signalements -> 2690 arrêts dépotoirs ; optimized, 43/2727 points servis ; camions nécessaires (estimation) : 900 | Avant / après présélection et remplissage : 8.90 s -> 2.40 s. |
|  | matrice sur n = 10000 signalements | non mesuré | limité : 10000 sources Dijkstra, trop long pour ce banc | compute_plan ne calcule la matrice que sur les arrêts (k), regroupés au-delà de solver.max_dumpsite_stops ; la matrice sur n est mesurée à part pour comparer. |
| 6. population 0 | compute_plan, 100 signalements | 1.24 s | optimized, 44/52 points servis ; 0 centre(s) ; contrôles en échec | Population 0 sur le vrai réseau : seuls les dépotoirs sont servis. |
| 6. 46 points imposés | compute_plan | 0.41 s | optimized, 46/46 points servis |  |
| 6. 120 points imposés | compute_plan | 1.77 s | optimized, 120/120 points servis | Même zone, k imposé ; médiane qui inclut le premier essai à cache froid. |
