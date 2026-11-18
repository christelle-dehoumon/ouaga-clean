"""Index de recherche de la carte, tiré des tuiles fabriquées (aucun service de géocodage) :
quartiers et lieux nommés, rues (emprise de tous les tronçons du même nom), points d'intérêt nommés.

    python scripts/tuiles/index_recherche.py web/dashboard/ville/carte/data/ouagadougou.pmtiles \
        web/dashboard/ville/carte/data/recherche.json

Dépendances de fabrication seulement (scripts/tuiles/requirements.txt) : pmtiles (BSD-3), mapbox-vector-tile (MIT).
"""
from __future__ import annotations

import gzip
import json
import math
import sys
from collections import defaultdict

import mapbox_vector_tile as mvt
from pmtiles.reader import MmapSource, all_tiles

Z = 14
EXTENT = 4096
LIEUX = {"city": "Ville", "town": "Commune", "suburb": "Arrondissement / secteur", "quarter": "Quartier",
         "neighbourhood": "Quartier", "village": "Village", "hamlet": "Hameau", "borough": "Arrondissement"}
FAMILLES = {"sante": "Santé", "education": "Éducation", "commerce": "Commerce, marché", "culte": "Lieu de culte",
            "administration": "Administration", "transport": "Transport", "loisirs": "Loisirs", "autre": "Lieu"}


def lonlat(z: int, x: int, y: int, px: float, py: float) -> tuple[float, float]:
    n = 2 ** z
    lon = (x + px / EXTENT) / n * 360 - 180
    yy = y + (1 - py / EXTENT)  # mapbox-vector-tile renvoie y vers le haut par défaut
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
    return round(lon, 6), round(lat, 6)


def coords(geom: dict) -> list:
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        return [c]
    if t == "MultiPoint" or t == "LineString":
        return c
    if t == "MultiLineString" or t == "Polygon":
        return [p for part in c for p in part]
    if t == "MultiPolygon":
        return [p for poly in c for ring in poly for p in ring]
    return []


def main(src: str, dst: str) -> None:
    lieux: dict[tuple, dict] = {}
    poi: dict[tuple, dict] = {}
    rues: dict[str, dict] = defaultdict(lambda: {"b": [999, 999, -999, -999], "classes": set()})
    with open(src, "rb") as f:
        for (z, x, y), data in all_tiles(MmapSource(f)):
            if z != Z:
                continue
            tile = mvt.decode(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)
            for feat in tile.get("lieux", {}).get("features", []):
                p = feat["properties"]
                if not p.get("nom"):
                    continue
                lon, lat = lonlat(z, x, y, *feat["geometry"]["coordinates"])
                lieux[(p["nom"], p.get("classe"))] = {"n": p["nom"], "t": LIEUX.get(p.get("classe"), "Lieu"), "c": [lon, lat], "z": 15 if p.get("classe") in ("city", "town") else 15.5}
            for feat in tile.get("poi", {}).get("features", []):
                p = feat["properties"]
                if not p.get("nom") or feat["geometry"]["type"] != "Point":
                    continue
                lon, lat = lonlat(z, x, y, *feat["geometry"]["coordinates"])
                poi[(p["nom"], round(lon, 4), round(lat, 4))] = {"n": p["nom"], "t": FAMILLES.get(p.get("famille"), "Lieu"), "c": [lon, lat], "z": 17.5}
            for feat in tile.get("routes", {}).get("features", []):
                p = feat["properties"]
                if not p.get("nom"):
                    continue
                r = rues[p["nom"]]
                r["classes"].add(p.get("classe"))
                for px, py in coords(feat["geometry"]):
                    lon, lat = lonlat(z, x, y, px, py)
                    b = r["b"]
                    b[0], b[1], b[2], b[3] = min(b[0], lon), min(b[1], lat), max(b[2], lon), max(b[3], lat)
    sortie = list(lieux.values()) + [{"n": n, "t": "Rue", "b": [round(v, 6) for v in r["b"]]} for n, r in rues.items()] + list(poi.values())
    sortie.sort(key=lambda e: e["n"].lower())
    with open(dst, "w", encoding="utf-8") as out:
        json.dump({"source": "© contributeurs OpenStreetMap (ODbL), extrait des tuiles Yilgré", "entrees": sortie}, out, ensure_ascii=False, separators=(",", ":"))
    print(f"index : {len(lieux)} lieux, {len(rues)} rues, {len(poi)} points d'intérêt -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
