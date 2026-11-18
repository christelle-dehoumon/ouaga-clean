#!/usr/bin/env bash
# Fabrique les tuiles vectorielles de l'agglomération de Ouagadougou depuis OpenStreetMap (à lancer après un clone :
# le fichier généré n'est jamais versionné) :
#   ./scripts/fabriquer_tuiles.sh            # ne refait rien si des tuiles valides et à jour existent déjà
#   ./scripts/fabriquer_tuiles.sh --force    # refabrique dans tous les cas
# 1. télécharge (une seule fois, contrôle MD5) l'extrait Burkina Faso de Geofabrik (~85 Mo) et Planetiler (Apache-2.0) ;
# 2. découpe l'agglomération (emprise ci-dessous) et écrit web/dashboard/ville/carte/data/ouagadougou.pmtiles ;
# 3. valide le résultat (scripts/tuiles/valider_tuiles.py) avant de remplacer l'ancien fichier ;
# 4. tire des tuiles l'index de recherche recherche.json (lieux, rues, points d'intérêt nommés).
# Réseau requis seulement pendant la fabrication ; la carte fonctionne ensuite sans internet.
# Prérequis : Java 21 ou plus récent, python3 (venv). Cache : ~/.cache/yilgre (YILGRE_CACHE pour le changer).
set -euo pipefail
cd "$(dirname "$0")/.."
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1
CACHE="${YILGRE_CACHE:-$HOME/.cache/yilgre}"
PBF="$CACHE/burkina-faso-latest.osm.pbf"
JAR="$CACHE/planetiler.jar"
PLANETILER_VERSION="${PLANETILER_VERSION:-0.10.2}"
# Emprise de l'agglomération (lon/lat) : Ouagadougou et communes contiguës (Saaba, Komsilga, Tanghin-Dassouri en partie).
BOUNDS="${BOUNDS:--1.72,12.20,-1.36,12.53}"
DOSSIER="web/dashboard/ville/carte/data"
SORTIE="$DOSSIER/ouagadougou.pmtiles"
INDEX="$DOSSIER/recherche.json"
TAMPON="$DOSSIER/.fabrication.json"   # empreinte de ce qui a servi à fabriquer les tuiles (non versionnée)
UA="yilgre-tiles/1.0"
mkdir -p "$CACHE" "$DOSSIER"

# Environnement Python de fabrication (validation, index) : séparé de .venv, jamais requis par l'application.
venv_tuiles() {
  if [ ! -x "$CACHE/venv-tuiles/bin/python" ]; then python3 -m venv "$CACHE/venv-tuiles"; fi
  "$CACHE/venv-tuiles/bin/pip" install -q -r scripts/tuiles/requirements.txt
}
empreinte() {  # schéma + emprise + version de Planetiler + extrait OSM utilisés
  local osm="absent"
  [ -s "$PBF.md5" ] && osm="$(cut -d' ' -f1 "$PBF.md5")"
  printf '{"schema":"%s","bornes":"%s","planetiler":"%s","osm_md5":"%s"}' \
    "$(sha256sum scripts/tuiles/schema_yilgre.yml | cut -d' ' -f1)" "$BOUNDS" "$PLANETILER_VERSION" "$osm"
}

# 0. Déjà fait ? Tuiles présentes, valides, fabriquées avec le même schéma et la même emprise : rien à refaire.
if [ "$FORCE" = 0 ] && [ -s "$SORTIE" ] && [ -s "$INDEX" ] && [ -s "$TAMPON" ] && [ "$(cat "$TAMPON")" = "$(empreinte)" ]; then
  venv_tuiles
  if "$CACHE/venv-tuiles/bin/python" scripts/tuiles/valider_tuiles.py "$SORTIE" "$BOUNDS" >/dev/null; then
    echo "[tuiles] déjà présentes et valides ($SORTIE) : rien à refaire (--force pour refabriquer)."
    exit 0
  fi
  echo "[tuiles] fichier présent mais invalide : nouvelle fabrication."
fi

# 1. Prérequis : Java 21+.
if ! command -v java >/dev/null 2>&1; then
  echo "ERREUR : Java est introuvable. Installez Java 21 ou plus récent (par exemple : sudo apt install openjdk-21-jre-headless), puis relancez." >&2
  exit 2
fi
JAVA_MAJEUR="$(java -version 2>&1 | sed -nE '1s/.*version "([0-9]+).*/\1/p')"
if [ -z "$JAVA_MAJEUR" ] || [ "$JAVA_MAJEUR" -lt 21 ]; then
  echo "ERREUR : Java ${JAVA_MAJEUR:-?} détecté ; Planetiler demande Java 21 ou plus récent." >&2
  exit 2
fi

# 2. Téléchargements (une seule fois).
if [ ! -s "$PBF" ] || ! (cd "$CACHE" && md5sum -c --status burkina-faso-latest.osm.pbf.md5 2>/dev/null); then
  echo "[osm] téléchargement de l'extrait Geofabrik du Burkina Faso…"
  curl -fL -A "$UA" -o "$PBF" https://download.geofabrik.de/africa/burkina-faso-latest.osm.pbf
  curl -fsL -A "$UA" -o "$PBF.md5" https://download.geofabrik.de/africa/burkina-faso-latest.osm.pbf.md5
  (cd "$CACHE" && md5sum -c burkina-faso-latest.osm.pbf.md5)
fi
if [ ! -s "$JAR" ] || [ "$(unzip -p "$JAR" buildinfo.properties 2>/dev/null | sed -n 's/^version=//p')" != "$PLANETILER_VERSION" ]; then
  echo "[planetiler] téléchargement de Planetiler $PLANETILER_VERSION…"
  curl -fL -o "$JAR" "https://github.com/onthegomap/planetiler/releases/download/v$PLANETILER_VERSION/planetiler.jar"
fi

# 3. Fabrication dans un fichier temporaire, validation, puis remplacement (jamais de fichier à moitié écrit en place).
TEMP="$DOSSIER/.ouagadougou.en-cours.pmtiles"
rm -f "$TEMP"
echo "[tuiles] emprise $BOUNDS -> $SORTIE"
java -Xmx2g -jar "$JAR" generate-custom --schema=scripts/tuiles/schema_yilgre.yml \
  --osm_path="$PBF" --bounds="$BOUNDS" --output="$TEMP" --force \
  --tmpdir="$CACHE/tmp" --nodemap_type=sparsearray --nodemap_storage=ram
venv_tuiles
if ! "$CACHE/venv-tuiles/bin/python" scripts/tuiles/valider_tuiles.py "$TEMP" "$BOUNDS"; then
  rm -f "$TEMP"
  echo "ERREUR : tuiles fabriquées invalides ; l'ancien fichier (s'il existe) est conservé." >&2
  exit 1
fi
mv -f "$TEMP" "$SORTIE"

# 4. Index de recherche (lieux, rues, points d'intérêt nommés) tiré des tuiles.
"$CACHE/venv-tuiles/bin/python" scripts/tuiles/index_recherche.py "$SORTIE" "$INDEX.tmp" && mv -f "$INDEX.tmp" "$INDEX"
empreinte > "$TAMPON"
ls -la "$DOSSIER"
