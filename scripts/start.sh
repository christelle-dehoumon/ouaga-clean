#!/usr/bin/env bash
# Démarre l'API (déjà installée) : certificat HTTPS auto-signé si absent, bases initialisées, uvicorn en HTTPS.
# Variables : HTTPS_PORT (8443), HTTP_DEBUG_PORT (vide = pas de port HTTP ; 8000 conseillé derrière un proxy),
#             PYTHON_BIN (python de l'environnement), COMMUNE_CONFIG, BRIGADE_CODE, MAIRIE_CODE.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON_BIN:-.venv/bin/python}"
HTTPS_PORT="${HTTPS_PORT:-8443}"
CERT_DIR="data/certs"
mkdir -p "$CERT_DIR"
# Certificat reconnu (recommandé : sans lui, les navigateurs refusent le service worker, donc la réouverture de la
# page citoyen sans réseau) : SSL_CERTFILE / SSL_KEYFILE (ex. Let's Encrypt), sinon mkcert s'il est installé,
# sinon certificat auto-signé (GPS, caméra et file hors ligne fonctionnent ; réouverture hors ligne non).
if [ -n "${SSL_CERTFILE:-}" ] && [ -n "${SSL_KEYFILE:-}" ]; then
  cp "$SSL_CERTFILE" "$CERT_DIR/cert.pem" && cp "$SSL_KEYFILE" "$CERT_DIR/key.pem"
  echo "[https] certificat fourni : $SSL_CERTFILE"
elif [ ! -f "$CERT_DIR/cert.pem" ] && command -v mkcert >/dev/null 2>&1; then
  IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  mkcert -cert-file "$CERT_DIR/cert.pem" -key-file "$CERT_DIR/key.pem" localhost 127.0.0.1 ${IP:+"$IP"} >/dev/null 2>&1 \
    && echo "[https] certificat mkcert (installer $(mkcert -CAROOT)/rootCA.pem sur les téléphones de démonstration)"
fi
if [ ! -f "$CERT_DIR/cert.pem" ] || [ ! -f "$CERT_DIR/key.pem" ]; then
  IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  SAN="DNS:localhost,IP:127.0.0.1${IP:+,IP:$IP}"
  echo "[https] certificat auto-signé pour $SAN (le téléphone affichera un avertissement à accepter une fois)"
  openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=yilgre" \
    -addext "subjectAltName=$SAN" -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" >/dev/null 2>&1
fi
"$PY" -m scripts.init_db
if [ -n "${HTTP_DEBUG_PORT:-}" ]; then
  echo "[http] débogage sur http://0.0.0.0:${HTTP_DEBUG_PORT} (GPS et caméra refusés hors HTTPS sur téléphone)"
  "$PY" -m uvicorn api.main:app --host 0.0.0.0 --port "$HTTP_DEBUG_PORT" &
fi
IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
echo "[https] https://localhost:${HTTPS_PORT}/  (réseau local : https://${IP:-<ip>}:${HTTPS_PORT}/citizen/)"
exec "$PY" -m uvicorn api.main:app --host 0.0.0.0 --port "$HTTPS_PORT" \
  --ssl-keyfile "$CERT_DIR/key.pem" --ssl-certfile "$CERT_DIR/cert.pem"
