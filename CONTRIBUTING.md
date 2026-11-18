# Contribuer à Yilgré

Yilgré est un logiciel libre (Apache-2.0). Toute contribution est la bienvenue : correction, nouvelle commune, données,
documentation, traduction des interfaces.

---

## 1. Installation de Développement

```bash
git clone https://github.com/christelle-dehoumon/yilgre.git
cd yilgre
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m scripts.init_db        # data/reel.db et data/sim.db
.venv/bin/python -m uvicorn api.main:app --reload --port 8000
```
En HTTP sur `localhost`, le navigateur autorise le GPS et le service worker : pratique pour développer. Pour un
téléphone, utiliser `./scripts/run.sh` (HTTPS).

## 2. Tests

```bash
.venv/bin/python -m pytest -q tests    # serveur et contrat du front (rapide)
./scripts/verifier_tout.sh             # tout : pytest + parcours dans Chromium sur des bases temporaires
```
Une contribution ne doit faire échouer aucun test, ni en affaiblir un. Tout nouveau comportement vient avec son test.

## 3. Conventions

- **Commits :** un sujet court au présent, préfixé par le type : `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- **Langue :** interfaces et documentation en français clair.
- **Valeurs :** aucune valeur métier écrite dans le code ; tout passe par `config/commune_config.json`
  (lu uniquement par `core/config.py`).
- **Honnêteté des données :** ce qui est simulé reste dans `sim.db`, étiqueté « simulé » ; aucun chiffre publié sans
  mesure reproductible (`python -m scripts.bench`).
- **Licences :** toute nouvelle dépendance doit avoir une licence libre compatible avec Apache-2.0 et être ajoutée à
  [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
- **Front :** HTML, CSS et JavaScript natifs, sans étape de construction ; rendu du DOM par `textContent`.

## 4. Ajouter une Commune

1. Copier `config/commune_config.json` vers `config/commune_config.<commune>.json` et adapter : nom, emprise (`bbox`),
   chemins des données (`paths`), paramètres, bornes, secteur.
2. Préparer les données une fois (réseau requis) :
   ```bash
   COMMUNE_CONFIG=config/commune_config.<commune>.json .venv/bin/python -m core.geo.download --pilot
   COMMUNE_CONFIG=config/commune_config.<commune>.json .venv/bin/python -m scripts.build_water
   COMMUNE_CONFIG=config/commune_config.<commune>.json .venv/bin/python -m scripts.make_secteur
   ```
3. Lancer : `COMMUNE_CONFIG=config/commune_config.<commune>.json ./scripts/run.sh`.
4. La ville 3D est préparée par `web/tools/build_city_data.py` ; tant qu'elle ne l'est pas pour la commune, l'interface
   mairie affiche une carte 2D (comportement testé avec Koudougou).

## 5. Proposer une Amélioration

Ouvrir une *issue* décrivant le problème, le comportement attendu et, si possible, une mesure. Pour une demande de
fusion : une branche par sujet, tests à jour, `./scripts/verifier_tout.sh` vert, documentation mise à jour.
