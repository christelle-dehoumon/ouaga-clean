#!/usr/bin/env bash
# Vérification complète, back + front ensemble, en une commande :   ./scripts/verifier_tout.sh
# 1. pytest (serveur et contrat du front) ;
# 2. deux serveurs de test sur des bases TEMPORAIRES (Ouagadougou, et Koudougou via COMMUNE_CONFIG) ;
# 3. les parcours dans Chromium (web/tools/e2e) : citoyen, brigade, chaîne complète citoyen -> brigade -> mairie,
#    carte MapLibre de l'agglomération (vue par défaut, ignorée sans tuiles), ville 3D (?vue=ville3d : réel, simulation,
#    panne, pluie, quartier, coupure, A/B, historique, échecs), gestes,
#    2D sans WebGL, mode démonstration, couche API, réglages par commune.
# Playwright est un outil de test, installé à part dans .venv-e2e (réseau requis la première fois, ~150 Mo).
# Les bases du dépôt (data/reel.db, data/sim.db) ne sont jamais touchées.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
E2E="${E2E_VENV:-.venv-e2e}"
PORT="${PORT:-9460}"
PORT2=$((PORT + 1))
TMP="$(mktemp -d)"
export BRIGADE_CODE="${BRIGADE_CODE:-brigade-demo}" MAIRIE_CODE="${MAIRIE_CODE:-mairie-demo}" PYTHONDONTWRITEBYTECODE=1
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done; }
trap cleanup EXIT

if [ ! -x "$E2E/bin/python" ] || ! "$E2E/bin/python" -c "import playwright" 2>/dev/null; then
  echo "[e2e] installation de Playwright et Chromium dans $E2E…"
  python3 -m venv "$E2E" && "$E2E/bin/pip" install -q playwright && "$E2E/bin/python" -m playwright install chromium || {
    echo "Playwright impossible à installer : seuls les tests pytest seront lancés."; E2E=""; }
fi

serve() {  # serve PORT PREFIXE [COMMUNE_CONFIG]
  REEL_DB="$TMP/$2reel.db" SIM_DB="$TMP/$2sim.db" PHOTO_DIR="$TMP/$2photos" COMMUNE_CONFIG="${3:-config/commune_config.json}" \
    "$PY" -m scripts.init_db >/dev/null
  REEL_DB="$TMP/$2reel.db" SIM_DB="$TMP/$2sim.db" PHOTO_DIR="$TMP/$2photos" COMMUNE_CONFIG="${3:-config/commune_config.json}" \
    "$PY" -m uvicorn api.main:app --port "$1" >"$TMP/serveur-$1.log" 2>&1 &
  PIDS+=($!)
  for _ in $(seq 60); do curl -s "localhost:$1/api/health" >/dev/null && return 0; sleep 1; done
  echo "Serveur $1 injoignable (voir $TMP/serveur-$1.log)"; return 1
}

declare -a NOMS=() ETATS=()
run() {  # run NOM commande...
  local nom="$1"; shift
  echo; echo "=== $nom"
  if "$@" >"$TMP/$nom.log" 2>&1; then ETATS+=("OK"); else ETATS+=("ÉCHEC"); fi
  NOMS+=("$nom")
  grep -E "^\[(OK |KO |SKIP)\]|passed|failed|vérifications|Error|assert" "$TMP/$nom.log" | tail -30
}

run pytest "$PY" -m pytest -q -p no:cacheprovider tests
if [ -n "$E2E" ]; then
  serve "$PORT" "" && serve "$PORT2" "k_" config/commune_config.koudougou.json
  for s in apitest citizen_test brigade_test chaine dash_full carte gestes qa mockpages; do
    run "e2e-$s" env BASE="http://localhost:$PORT" SHOTS="$TMP/captures/" "$E2E/bin/python" "web/tools/e2e/$s.py"
  done
  run e2e-commune env BASE="http://localhost:$PORT2" "$E2E/bin/python" web/tools/e2e/commune.py
fi

echo; echo "================ BILAN ================"
FAIL=0
for i in "${!NOMS[@]}"; do printf "%-22s %s\n" "${NOMS[$i]}" "${ETATS[$i]}"; [ "${ETATS[$i]}" = OK ] || FAIL=1; done
echo "Journaux et captures : $TMP"
exit $FAIL
