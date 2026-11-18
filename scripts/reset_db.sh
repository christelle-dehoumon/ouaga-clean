#!/usr/bin/env bash
# Remise à zéro de la démonstration : vide sim.db et recharge le jeu factice. reel.db seulement avec --reel.
# Usage : ./scripts/reset_db.sh [--reel]
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON_BIN:-.venv/bin/python}"
"$PY" - "$@" <<'PYEOF'
import sys
from core.db import reset
modes = ["sim"] + (["reel"] if "--reel" in sys.argv[1:] else [])
for mode in modes:
    reset(mode)
    print(f"[reset] base {mode} vidée")
PYEOF
"$PY" -m scripts.init_db
