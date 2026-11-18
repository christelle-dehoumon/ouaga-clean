# Vidéo de Démonstration de Yilgré (3 minutes)

Du signalement à la tournée, puis un changement de paramètres et le plan recalculé. Tout ce qui est filmé est réel et
reproductible ; les scènes de simulation portent le bandeau jaune « SIMULATION — DONNÉES FICTIVES ».

---

## 1. Préparatifs (la veille et 15 minutes avant)

1. **Remise à zéro :** `./scripts/reset_db.sh` (vide `sim.db` et recharge le jeu fictif ; `reel.db` reste intacte).
2. **Lancement :** `./scripts/run.sh`, noter l'adresse affichée `réseau local : https://<ip>:8443/`.
3. **Connexion :** ordinateur et téléphone sur le même Wi-Fi. Sur le téléphone, ouvrir `https://<ip>:8443/citizen/` et
   accepter le certificat une fois ; autoriser la position et la caméra.
4. **Brigade :** un deuxième téléphone (ou un onglet mobile de l'ordinateur) sur `https://<ip>:8443/brigade/`, code `brigade-demo`.
5. **Mairie :** sur l'ordinateur, `https://<ip>:8443/dashboard/`, code `mairie-demo`, fermer l'aide ; écran en 1920 × 1080.
6. **Réseau :** une connexion Internet n'est pas nécessaire (la ville 3D est locale). Ne pas couper le Wi-Fi local.
7. **Répétition :** jouer le parcours une fois en entier, puis `./scripts/reset_db.sh` à nouveau.
8. **Certificat :** avec le certificat auto-signé, la page citoyen ne se rouvre pas sans réseau ; garder la page
   ouverte pendant la scène hors connexion.

---

## 2. Conducteur

| Temps | Écran | Voix |
|---|---|---|
| **0:00 – 0:15** | Logo Yilgré, puis la ville 3D qui tourne (vue Immersive). | « Yilgré est un outil libre d'aide à la décision pour l'assainissement de Ouagadougou, du signalement d'un dépotoir jusqu'au plan de collecte. » |
| **0:15 – 0:40** | Téléphone citoyen : position trouvée, photo, « Envoyer », « reçu ». Mode avion, second envoi « enregistré sur le téléphone », réseau rétabli, « reçu ». | « Le citoyen n'a pas de compte : une photo, sa position, c'est tout. Sans réseau, le signalement attend sur le téléphone et part tout seul. » |
| **0:40 – 1:00** | Téléphone brigade : nouveau cas, photo floutée, alertes, « Confirmer ». | « Le serveur floute les visages et les plaques avant tout stockage. La brigade Laabal vérifie sur place et confirme. » |
| **1:00 – 1:25** | Mairie, Données réelles : épingle rouge, fiche, historique ; « Calculer le plan réel » ; statut vert. | « La mairie voit chaque cas dans la ville et son historique. Le plan de collecte n'utilise que les dépotoirs confirmés. » |
| **1:25 – 1:50** | Bascule Simulation (bandeau jaune) : tournées colorées, camions qui roulent ; « Fixer le plan affiché comme A ». | « En simulation, données fictives, la mairie teste ses décisions. Chaque camion suit sa tournée calculée par OR-Tools sur les vraies rues. » |
| **1:50 – 2:15** | Clic sur un camion, « Déclarer en panne » : il s'arrête, feux allumés ; statut « partiellement réalisable », arrêts reportés, temps serveur affiché. | « Un camion tombe en panne : seuls ses arrêts sont redistribués, en une fraction de seconde. Ce qui ne peut pas être collecté est dit, pas caché. » |
| **2:15 – 2:35** | « Déclencher la saison des pluies » (pluie à l'écran), puis ajout du quartier Kalgodin : la caméra y vole, nouveaux points. | « Pluie : les pistes en latérite ralentissent, certaines routes sont coupées. Un nouveau quartier : le plan s'agrandit. » |
| **2:35 – 2:55** | « Fixer le plan affiché comme B », « Comparer A et B » : tableau des écarts et compromis. | « La comparaison montre ce que l'on gagne et ce que l'on perd : couverture, coût, points non desservis. L'outil éclaire, la mairie décide. » |
| **2:55 – 3:00** | Logo, « Apache-2.0 · données OpenStreetMap (ODbL) · github.com/christelle-dehoumon/yilgre ». | « Yilgré est libre, ses données sont ouvertes, et une autre commune peut l'adopter en changeant sa configuration. » |

---

## 3. Points d'Attention

- Montrer le bandeau jaune à chaque scène de simulation ; ne jamais présenter un chiffre simulé comme un constat.
- Ne pas dire « bâtiments réels » : dire « emprises OpenStreetMap, hauteurs estimées ».
- Si un recalcul échoue en direct, le dernier plan reste affiché et marqué « plan précédent » : le montrer plutôt que le cacher.
