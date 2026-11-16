# Mesures du membre A

Générées le 2026-11-16 18:58 UTC par `python -m scripts.bench` (relançable, une commande).
Machine : 11th Gen Intel(R) Core(TM) i7-1165G7 @ 2.80GHz, 8 cœurs logiques, Linux 7.0.0-43-generic, Python 3.12.3.
Temps médian sur 5 essais sauf mention ; réseau chargé une fois avant les mesures (premier calcul complet, chargement compris : 10.9 s). Zone pilote, configuration du dépôt.
Signalements : synthétiques (`scripts/make_synthetic.py`, graine fixe), statut accepted. Valeurs `observed` sur cette machine.

| Mesure | Variante | Médiane | Résultat | Ce que ça montre |
|---|---|---|---|---|
| 1. Dijkstra 60 sources | NetworkX, une source à la fois | 11.62 s | graphe NetworkX construit à part en 0.63 s |  |
|  | SciPy, un appel | 0.74 s | écart max des distances 0.000 m | Même vue, mêmes sources : SciPy prend 15.6 fois moins de temps que NetworkX sur cette machine. |
| 2. Placement, k = 46 | KMeans sur 26285 bâtiments | 0.11 s | 100.0% de la demande à moins de 1500 m |  |
|  | KMeans sur 1740 cellules de 100 m | 0.03 s | 100.0% de la demande à moins de 1500 m | Même zone et même k : les cellules prennent 4.0 fois moins de temps, couverture mesurée dans la colonne Résultat. |
| 3. Matrice 46 × 46 | à froid (cache vide) | 0.607 s | 1 appel Dijkstra |  |
|  | cache rempli | 0.001 s | 0 appel Dijkstra | Avec le cache, la matrice est relue sans Dijkstra ; il reste le temps de lecture des lignes. |
| 4. Panne de truck2 | calcul complet | 0.82 s | optimized, 46/46 points servis |  |
|  | recalcul partiel | 0.91 s | optimized, 46/46 points servis | Le mode et le nombre de points servis sont ceux du plan gardé (le partiel lance aussi le complet s'il laisse des points non servis). |
| 5. +20 signalements | calcul complet | 2.36 s | optimized, 57/66 points servis |  |
|  | recalcul partiel | 2.50 s | partial, 57/66 points servis | Partiel 2.50 s contre complet 2.36 s ; le partiel lance aussi le complet s'il laisse des points non servis, d'où un temps qui peut dépasser celui du complet. |
| 6. 100 signalements | compute_plan (matrice sur k) | 3.37 s | 100 signalements -> 41 arrêts dépotoirs ; optimized, 62/87 points servis |  |
|  | matrice sur n = 100 signalements | 1.23 s | 5 essai(s) |  |
| 6. 1000 signalements | compute_plan (matrice sur k) | 0.63 s | 1000 signalements -> 17 arrêts dépotoirs ; optimized, 46/63 points servis |  |
|  | matrice sur n = 1000 signalements | 12.40 s | 1 essai(s) (limité : durée) |  |
| 6. 10000 signalements | compute_plan (matrice sur k) | 0.89 s | 10000 signalements -> 19 arrêts dépotoirs ; optimized, 48/65 points servis |  |
|  | matrice sur n = 10000 signalements | non mesuré | limité : 10000 sources Dijkstra, trop long pour ce banc | compute_plan ne calcule la matrice que sur les arrêts (k), regroupés au-delà de solver.max_dumpsite_stops ; la matrice sur n est mesurée à part pour comparer. |
| 6. 46 points imposés | compute_plan | 0.55 s | optimized, 46/46 points servis |  |
| 6. 120 points imposés | compute_plan | 2.33 s | optimized, 120/120 points servis | Même zone, k imposé ; médiane qui inclut le premier essai à cache froid. |
