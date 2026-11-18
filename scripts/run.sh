#!/usr/bin/env bash
# Déploiement en UNE commande depuis un clone neuf :   ./scripts/run.sh
# Crée .venv (Python 3.12), installe requirements.txt (seulement s'il a changé), puis lance scripts/start.sh
# (certificat HTTPS auto-signé dans data/certs/, reel.db et sim.db, uvicorn en HTTPS sur 0.0.0.0:8443).
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3.12}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3
if [ ! -x .venv/bin/python ]; then
  echo "[venv] création avec $PYTHON ($("$PYTHON" --version))"
  "$PYTHON" -m venv .venv
fi
STAMP=".venv/.requirements.sha256"
SUM="$(sha256sum requirements.txt | cut -d' ' -f1)"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$SUM" ]; then
  echo "[pip] installation de requirements.txt (une seule fois, quelques minutes)"
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt
  echo "$SUM" > "$STAMP"
fi
exec ./scripts/start.sh
