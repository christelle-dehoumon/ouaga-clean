#!/usr/bin/env bash
# reset_db.sh — supprime la base locale et réinitialise via l'API si elle tourne.
set -euo pipefail

DB="${REPORTS_DB:-data/reports.db}"
API_URL="${API_URL:-http://localhost:8000}"

echo "Suppression de ${DB}…"
rm -f "${DB}"
echo "  → fichier supprimé (ou absent)."

if curl -sf "${API_URL}/api/health" > /dev/null 2>&1; then
  echo "API détectée sur ${API_URL} — appel de POST /api/admin/reset…"
  curl -s -X POST "${API_URL}/api/admin/reset" | python3 -m json.tool
  echo "  → reset API effectué."
else
  echo "API non joignable sur ${API_URL} — reset fichier uniquement."
fi
