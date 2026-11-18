# Assainissement de Ouaga : guide final de l'équipe

Nov 16, 2026 · @Wedtoin

## La décision

On suit la proposition 2 (le guide d'équipe), on y greffe cinq éléments de la proposition 1 (Yilgré) et on ajoute trois choses nouvelles. Ce document remplace les deux propositions : c'est la seule route.

| What                                      | Why                                                                                   | How                                                                                                  |
|-------------------------------------------|---------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| Base : proposition 2                      | Elle tient dans le temps restant et met en premier ce que le jury teste.              | FastAPI, SQLite, page web pour téléphone, Mesa dès ce soir.                                          |
| Greffe 1 : contrôles de cohérence         | Le sujet exige un plan qui « reste cohérent ».                                        | Après chaque calcul : capacité, budget, points non desservis avec la raison.                         |
| Greffe 2 : historique des scénarios       | Sans lui, on ne peut pas comparer deux plans.                                         | Chaque calcul est enregistré avec ses paramètres.                                                    |
| Greffe 3 : quartiers et zones             | Il faut savoir si un signalement est dans la zone, et accueillir un nouveau quartier. | Polygones stockés en GeoJSON, chargés depuis la configuration.                                       |
| Greffe 4 : qui a validé, quand            | Le sujet parle de « signalements vérifiés ».                                          | Trois champs sur le signalement : validé par, validé le, motif.                                      |
| Greffe 5 : règles d'OpenStreetMap         | Le thème est l'open source ; le jury peut vérifier.                                   | Export en fichier, jamais d'envoi de données simulées dans OSM.                                      |
| Ajout 1 : amélioration chiffrée (les 3 A) | C'est le critère sur lequel les organisateurs ont insisté.                            | Grille pour les doublons, distances gardées en mémoire, recalcul partiel, temps mesurés avant/après. |
| Ajout 2 : solutions de repli              | L'épreuve est « impossible à préparer » : quelque chose cassera.                      | Limite de temps, plan de secours, dernier plan valide gardé à l'écran.                               |
| Ajout 3 : fusion du code dès ce soir      | Assembler tard, c'est découvrir les problèmes quand il n'y a plus de temps.           | Premier parcours complet ce soir à 23 h, même avec de fausses données.                               |

## Ce qu'on construit

Un site avec une carte de Ouaga qui trie les signalements, propose un plan de collecte, simule les acteurs, et refait le plan en quelques secondes quand la situation change. L'outil éclaire, la mairie décide.

| Brique                    | What                                                                          | Why                                                                                                        | How                                                                                                                                                                                                                                                                |
|---------------------------|-------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1\. Signalements vérifiés | Recevoir les signalements et écarter automatiquement les faux.                | Premier test du jury : il injecte des signalements piégés.                                                 | Trois statuts : accepté, rejeté, à vérifier. Règles : dans la zone, hors plan d'eau, pas de doublon (moins de 30 m et moins de 48 h), photo déjà vue, date possible. Un doublon renforce le dépotoir existant. Chaque rejet affiche son motif. Jamais de plantage. |
| 2\. Plan de gestion       | Placer les points de regroupement et tracer les tournées.                     | C'est le cœur de l'aide à la décision, et le deuxième test : le plan doit se recalculer.                   | Routes d'OpenStreetMap avec osmnx, deux réseaux (camions, tricycles). Points de regroupement placés selon les bâtiments et les dépotoirs validés, puis déplacés sur le carrefour le plus proche. Tournées avec OR-Tools, limitées à 5 secondes.                    |
| 3\. Simulation            | Faire vivre les 4 acteurs : ménages, pré-collecteurs, brigade Laabal, mairie. | Fonction exigée par le sujet. Elle montre si le plan tient dans un monde où les gens ne sont pas parfaits. | Mesa, 2 ou 3 règles par acteur. Le plan entre dans la simulation, qui renvoie trois chiffres : part des déchets ramassés, coût, dépotoirs restants.                                                                                                                |

Les deux écrans :

- **Tableau de bord de la mairie** (ordinateur) : carte, plan, cinq curseurs (population, abonnements, camions, fréquences, budget), trois boutons de crise, comparaison de deux scénarios, bouton « Valider ce plan ». C'est 80 % de l'effort.

- **Page de signalement** (téléphone) : photo, position, taille, envoi même sans réseau. C'est 20 % de l'effort.

Les 3 A :

- **Adopter** : osmnx, OR-Tools, Mesa, Leaflet, sans les modifier.

- **Adapter** : camions sur le goudron et tricycles sur les pistes, routes coupées par la pluie, acteurs propres à Ouaga, réglages par commune.

- **Améliorer** : doublons cherchés avec une grille au lieu de comparer toutes les paires ; distances calculées entre les points de regroupement seulement et gardées en mémoire ; en cas de panne, on ne redistribue que les arrêts du camion perdu. Les temps sont mesurés avant et après.

## Qui fait quoi

Chacun possède ses dossiers et ne modifie pas ceux des autres : c'est ce qui évite les conflits dans git.

| Membre | What                                                                      | Why                                                                                    | How (dossiers)                       |
|--------|---------------------------------------------------------------------------|----------------------------------------------------------------------------------------|--------------------------------------|
| A      | Données géographiques, points de regroupement, tournées, recalcul         | C'est la partie que le jury bouscule avec les pannes, la pluie et le nouveau quartier. | core/geo/, core/optim/, data/        |
| B      | API, tri automatique des signalements, page de signalement pour téléphone | C'est le premier test du jury, et l'étiquette « Mobile » du sujet.                     | api/, core/validation/, web/citizen/ |
| C      | Simulation, scénarios, tableau de bord                                    | C'est l'écran que le jury manipule.                                                    | core/sim/, web/dashboard/            |

Deux règles d'équipe :

- Le contrat de données (docs/contracts.md) est écrit à trois et ne change plus sans prévenir les autres.

- B aide C sur le tableau de bord mardi après-midi, une fois la page de signalement terminée.

## La route, étape par étape

Huit étapes, de maintenant au rendu. Les heures supposent un rendu mercredi à 10 h, à confirmer auprès des organisateurs.

| Quand                       | Qui     | What                                                                             | Why                                                                                                                  | How                                                                                                                                                                                                                                                                                                                |
|-----------------------------|---------|----------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Lundi, maintenant → 16 h    | Tous    | Dépôt public, licence, contrat de données                                        | Sans contrat commun, les trois parties ne s'assembleront pas. La licence libre est une règle du sujet.               | Créer le dépôt, choisir une licence, écrire le format d'un signalement, des paramètres et d'un plan. Mettre des fichiers d'exemple dans data/mock/. Toutes les valeurs vont dans config/commune_config.json, aucune dans le code.                                                                                  |
| Lundi 16 h → 23 h           | A       | Routes et bâtiments de toute la ville, points de regroupement                    | Un nouveau quartier hors du secteur serait hors carte. Les données doivent être locales : aucune dépendance externe. | Télécharger les routes avec osmnx et les bâtiments d'Open Buildings, en garder une copie. Construire les deux réseaux (camions, tricycles). Placer les points de regroupement.                                                                                                                                     |
| Lundi 16 h → 23 h           | B       | API et tri automatique des signalements                                          | C'est ce que le jury teste en premier.                                                                               | Les routes de l'API, les règles de vérification, la grille pour les doublons. Toute entrée mal formée renvoie un rejet avec motif.                                                                                                                                                                                 |
| Lundi 16 h → 23 h           | C       | Simulation des 4 acteurs, squelette du tableau de bord                           | La simulation est une fonction exigée ; le tableau de bord est ce que le jury voit.                                  | Modèle Mesa avec des règles simples. Les chiffres du modèle vont dans la configuration, étiquetés « hypothèses ». Tableau de bord branché sur les fichiers d'exemple.                                                                                                                                              |
| Lundi 23 h                  | Tous    | Première fusion                                                                  | Voir très tôt si les parties se parlent.                                                                             | Un signalement entre, un plan s'affiche, même avec de fausses données.                                                                                                                                                                                                                                             |
| Mardi 8 h → 12 h            | A, B, C | A : tournées et recalcul. B : page de signalement. C : comparaison de scénarios. | Ce sont les trois fonctions encore manquantes.                                                                       | A : OR-Tools limité à 5 secondes, plan de secours, recalcul partiel en cas de panne. B : photo, position, envoi différé sans réseau. C : deux scénarios côte à côte, historique gardé.                                                                                                                             |
| Mardi 12 h → 20 h           | Tous    | Intégration, trois boutons de crise, contrôles de cohérence                      | C'est exactement le déroulé de l'épreuve en direct.                                                                  | Camion en panne, saison des pluies, nouveau quartier : chaque bouton change les paramètres, relance le plan et la simulation. Afficher capacité, budget et points non desservis. Marquer une version stable dans git à 20 h.                                                                                       |
| Mardi 20 h → mercredi matin | Tous    | Crash-test, mesures, finitions, sommeil                                          | Une épreuve impossible à préparer se prépare en essayant de tout casser.                                             | A joue le jury avec 50 signalements absurdes. Test sans Internet et sur un vrai téléphone. Mesure des temps avant/après. Essai sur une autre commune en changeant seulement la configuration. Vidéo de secours. README. Gel du code 1 h 30 avant le rendu, puis répétition du pitch. Dormir au moins 4 à 5 heures. |

## Ce qu'on ne coupe jamais, et ce qu'on coupe

Sept règles tiennent jusqu'au bout, quel que soit le retard.

| What                                              | Why                                                                           | How                                                                                                                                                                                                                                           |
|---------------------------------------------------|-------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Le tri automatique des signalements               | Premier test du jury.                                                         | Fini lundi soir.                                                                                                                                                                                                                              |
| Le recalcul en direct                             | Deuxième test du jury.                                                        | Limite de 5 secondes et chronomètre à l'écran.                                                                                                                                                                                                |
| Un plan cohérent                                  | Exigé par le sujet.                                                           | Capacité, budget, points non desservis affichés après chaque calcul.                                                                                                                                                                          |
| Les solutions de repli                            | L'outil doit toujours répondre.                                               | Plan de secours (chaque camion va au point le plus proche), distance à vol d'oiseau si la route manque, dernier plan valide gardé à l'écran et marqué « ancien », script de remise à zéro de la base. L'écran dit toujours quel mode a servi. |
| Tout en local                                     | Règle : aucune dépendance à des données indisponibles.                        | Aucun service extérieur. Fond de carte dessiné avec ses propres routes. Sur téléphone, la page doit être en connexion sécurisée, sinon le GPS et l'appareil photo sont refusés.                                                               |
| L'honnêteté sur les données                       | Un chiffre inventé présenté comme réel coûte plus cher qu'une limite assumée. | Signalements générés étiquetés « simulé » partout, jamais versés dans OpenStreetMap. Aucun pourcentage dans le pitch sans mesure.                                                                                                             |
| Licence, README, export OSM, réglages par commune | Ce sont les livrables « bien commun » du sujet.                               | Licence choisie à l'étape 1. Export en fichier. Une deuxième commune démontrée.                                                                                                                                                               |

En cas de retard, on coupe dans cet ordre :

1.  Les tournées des tricycles (on garde les camions).

2.  La finesse de la simulation (on garde 4 acteurs avec une règle chacun).

3.  L'envoi différé sans réseau sur la page de signalement.

On ne commence pas : reconnaissance d'images, guidage vocal, code USSD, comptes utilisateurs, application à installer.

## La démo et les points à confirmer

La démo suit l'ordre de l'épreuve, en cinq temps :

1.  Le jury injecte ses signalements : l'écran montre combien sont acceptés et rejetés, et pourquoi.

2.  Le plan s'affiche : points de regroupement, tournées, contrôles de cohérence au vert.

3.  Un camion tombe en panne : recalcul en direct, chronomètre visible, points reportés listés.

4.  Saison des pluies, puis nouveau quartier : deux scénarios comparés côte à côte.

5.  Dernière diapo : tout est libre, tout tourne sans Internet, une autre commune le réutilise en changeant un fichier.

Trois phrases pour le pitch :

- « L'outil éclaire, la mairie décide. »

- « Nous n'avons rien réinventé : nous avons adopté des logiciels libres, nous les avons adaptés à Ouaga, et nous avons amélioré le recalcul, mesures à l'appui. »

- « Une mairie ne peut pas se permettre un outil qui s'arrête : le nôtre donne toujours une réponse, et dit quand elle est dégradée. »

À confirmer auprès des organisateurs, dès maintenant :

- [ ] L'heure exacte du rendu et le format attendu (dépôt, démo, diapos, durée du pitch).

- [ ] Des signalements simulés sont-ils acceptés, ou un jeu de données est-il fourni ? Le sujet écrit « collectés par chaque équipe dans son secteur ».

- [ ] Les paramètres de départ « fixés avec la mairie » : sont-ils fournis ?

- [ ] Le rôle exact de la brigade Laabal, pour la simulation.

- [ ] Les conditions d'utilisation d'Open Buildings, à lire sur la page du jeu de données.