#!/usr/bin/env bash
# VIELA en UNE commande, depuis un clone neuf :   ./scripts/lancer.sh
# 1. fabrique les tuiles de la carte si elles manquent (Java 21+ ; sinon la mairie affiche la ville 3D du secteur pilote) ;
# 2. démarre l'application (scripts/run.sh : environnement Python, certificat HTTPS, bases, serveur sur le port 8443) ;
# 3. attend que le serveur réponde, puis ouvre les trois écrans dans le navigateur : mairie, brigade, citoyen.
# Ctrl+C arrête le serveur. Variables : HTTPS_PORT (8443), NO_OPEN=1 (ne pas ouvrir le navigateur).
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${HTTPS_PORT:-8443}"
URL="https://localhost:${PORT}"
IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"

# 1. Tuiles de la carte (une seule fois ; le script ne refait rien si elles sont déjà valides).
if ! ./scripts/fabriquer_tuiles.sh; then
  echo "[carte] tuiles non fabriquées (voir le message ci-dessus) : la mairie affichera la ville 3D du secteur pilote."
fi

# 2. Serveur : réutilise celui qui tourne déjà sur ce port, sinon le démarre.
PID=""
if curl -sk --max-time 3 "$URL/api/health" >/dev/null; then
  echo "[serveur] déjà en marche sur $URL"
else
  HTTPS_PORT="$PORT" ./scripts/run.sh &
  PID=$!
  trap '[ -n "$PID" ] && kill "$PID" 2>/dev/null; exit 0' INT TERM
  echo "[serveur] démarrage…"
  for _ in $(seq 180); do
    curl -sk --max-time 2 "$URL/api/health" >/dev/null && break
    kill -0 "$PID" 2>/dev/null || { echo "ERREUR : le serveur s'est arrêté (voir les messages ci-dessus)." >&2; exit 1; }
    sleep 1
  done
  curl -sk --max-time 3 "$URL/api/health" >/dev/null || { echo "ERREUR : le serveur ne répond pas sur $URL." >&2; exit 1; }
fi

# 3. Les trois écrans.
ECRANS=("$URL/dashboard/ville/" "$URL/brigade/" "$URL/citizen/")
cat <<EOF

  VIELA est prêt.
    Mairie  : $URL/dashboard/ville/   (code : ${MAIRIE_CODE:-mairie-demo})
    Brigade : $URL/brigade/           (code : ${BRIGADE_CODE:-brigade-demo})
    Citoyen : $URL/citizen/           (aucun code)
  Téléphone sur le même Wi-Fi : https://${IP:-<ip-du-poste>}:${PORT}/citizen/
  Certificat auto-signé : accepter l'avertissement du navigateur une fois.
  La carte 3D demande WebGL (Firefox ou Chrome ; pas le navigateur intégré de VS Code).

EOF
if [ "${NO_OPEN:-0}" != 1 ]; then
  OUVRIR=""
  command -v xdg-open >/dev/null 2>&1 && OUVRIR=xdg-open
  command -v open >/dev/null 2>&1 && [ -z "$OUVRIR" ] && OUVRIR=open
  if [ -n "$OUVRIR" ]; then
    for u in "${ECRANS[@]}"; do "$OUVRIR" "$u" >/dev/null 2>&1 || true; sleep 1; done
  else
    echo "Ouvrez les adresses ci-dessus dans le navigateur."
  fi
fi

# Garde le serveur au premier plan (Ctrl+C pour arrêter) s'il a été démarré par ce script.
[ -n "$PID" ] && wait "$PID" || true
