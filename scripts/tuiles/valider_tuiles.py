"""Valide le fichier de tuiles de la carte avant de l'utiliser ; code de sortie 0 si valide, 1 sinon (message en clair).

    python scripts/tuiles/valider_tuiles.py web/dashboard/ville/carte/data/ouagadougou.pmtiles -1.72,12.20,-1.36,12.53

Contrôles : en-tête PMTiles v3 lisible, zooms 0 à 14, emprise couvrant celle demandée, couches attendues déclarées,
et une tuile du centre-ville au zoom 14 qui contient réellement des bâtiments, des routes et des lieux.
Dépendances de fabrication seulement (scripts/tuiles/requirements.txt).
"""
from __future__ import annotations

import gzip
import json
import math
import sys

import mapbox_vector_tile as mvt
from pmtiles.reader import MmapSource, Reader

COUCHES = {"batiments", "routes", "eau", "occupation", "lieux", "poi"}
CENTRE = (12.3686, -1.5275)   # centre-ville de Ouagadougou (avenue Kwamé N'Krumah)


def tuile(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def valider(chemin: str, bornes: str) -> list[str]:
    erreurs: list[str] = []
    try:
        f = open(chemin, "rb")
    except OSError as e:
        return [f"fichier illisible : {e}"]
    with f:
        r = Reader(MmapSource(f))
        try:
            h = r.header()
            meta = r.metadata()
        except Exception as e:  # en-tête corrompu ou fichier tronqué
            return [f"en-tête PMTiles illisible : {e}"]
        if h.get("min_zoom") != 0 or h.get("max_zoom") != 14:
            erreurs.append(f"zooms {h.get('min_zoom')}–{h.get('max_zoom')} au lieu de 0–14")
        w, s, e, n = (float(v) for v in bornes.split(","))
        emprise = (h["min_lon_e7"] / 1e7, h["min_lat_e7"] / 1e7, h["max_lon_e7"] / 1e7, h["max_lat_e7"] / 1e7)
        tol = 0.01
        if emprise[0] > w + tol or emprise[1] > s + tol or emprise[2] < e - tol or emprise[3] < n - tol:
            erreurs.append(f"emprise {emprise} ne couvre pas {bornes}")
        declarees = {c.get("id") for c in (meta.get("vector_layers") or [])}
        if not COUCHES <= declarees:
            erreurs.append(f"couches manquantes : {sorted(COUCHES - declarees)}")
        x, y = tuile(*CENTRE, 14)
        data = r.get(14, x, y)
        if not data:
            erreurs.append("aucune tuile au centre-ville (zoom 14)")
        else:
            t = mvt.decode(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)
            for couche in ("batiments", "routes"):
                if not t.get(couche, {}).get("features"):
                    erreurs.append(f"tuile du centre-ville sans « {couche} »")
    return erreurs


if __name__ == "__main__":
    erreurs = valider(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "-1.72,12.20,-1.36,12.53")
    if erreurs:
        print("[tuiles] INVALIDE : " + " ; ".join(erreurs))
        sys.exit(1)
    print(json.dumps({"tuiles": "valides", "fichier": sys.argv[1]}, ensure_ascii=False))
