#!/usr/bin/env bash
# Fabrique les tuiles vectorielles de l'agglomération de Ouagadougou depuis OpenStreetMap :
#   ./scripts/fabriquer_tuiles.sh
# 1. télécharge (une seule fois, contrôle MD5) l'extrait Burkina Faso de Geofabrik (~85 Mo) et Planetiler (Apache-2.0) ;
# 2. découpe l'agglomération (emprise ci-dessous) et écrit web/dashboard/ville/carte/data/ouagadougou.pmtiles ;
# 3. tire des tuiles l'index de recherche recherche.json (lieux, rues, points d'intérêt nommés).
# Réseau requis seulement pendant la fabrication ; la carte fonctionne ensuite sans internet.
# Cache des téléchargements : ~/.cache/yilgre (YILGRE_CACHE pour le changer). Java 21+ requis (ou Docker, voir docs/carte.md).
set -euo pipefail
cd "$(dirname "$0")/.."
CACHE="${YILGRE_CACHE:-$HOME/.cache/yilgre}"
PBF="$CACHE/burkina-faso-latest.osm.pbf"
JAR="$CACHE/planetiler.jar"
PLANETILER_VERSION="${PLANETILER_VERSION:-0.10.2}"
# Emprise de l'agglomération (lon/lat) : Ouagadougou et communes contiguës (Saaba, Komsilga, Tanghin-Dassouri en partie).
BOUNDS="${BOUNDS:--1.72,12.20,-1.36,12.53}"
SORTIE="web/dashboard/ville/carte/data/ouagadougou.pmtiles"
UA="yilgre-tiles/1.0"
mkdir -p "$CACHE" "$(dirname "$SORTIE")"

if [ ! -s "$PBF" ] || ! (cd "$CACHE" && md5sum -c --status burkina-faso-latest.osm.pbf.md5 2>/dev/null); then
  echo "[osm] téléchargement de l'extrait Geofabrik du Burkina Faso…"
  curl -fL -A "$UA" -o "$PBF" https://download.geofabrik.de/africa/burkina-faso-latest.osm.pbf
  curl -fsL -A "$UA" -o "$PBF.md5" https://download.geofabrik.de/africa/burkina-faso-latest.osm.pbf.md5
  (cd "$CACHE" && md5sum -c burkina-faso-latest.osm.pbf.md5)
fi
if [ ! -s "$JAR" ]; then
  echo "[planetiler] téléchargement de Planetiler $PLANETILER_VERSION…"
  curl -fL -o "$JAR" "https://github.com/onthegomap/planetiler/releases/download/v$PLANETILER_VERSION/planetiler.jar"
fi

echo "[tuiles] emprise $BOUNDS -> $SORTIE"
java -Xmx2g -jar "$JAR" generate-custom --schema=scripts/tuiles/schema_yilgre.yml \
  --osm_path="$PBF" --bounds="$BOUNDS" --output="$SORTIE" --force \
  --tmpdir="$CACHE/tmp" --nodemap_type=sparsearray --nodemap_storage=ram
# Index de recherche (lieux, rues, points d'intérêt nommés) tiré des tuiles, dans un environnement de fabrication à part.
if [ ! -x "$CACHE/venv-tuiles/bin/python" ]; then python3 -m venv "$CACHE/venv-tuiles"; fi
"$CACHE/venv-tuiles/bin/pip" install -q -r scripts/tuiles/requirements.txt
"$CACHE/venv-tuiles/bin/python" scripts/tuiles/index_recherche.py "$SORTIE" "$(dirname "$SORTIE")/recherche.json"
ls -la "$(dirname "$SORTIE")"
