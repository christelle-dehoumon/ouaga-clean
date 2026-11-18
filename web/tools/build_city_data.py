"""Prépare les données de la ville 3D (web/dashboard/ville/data/city.json) à partir des données OSM déjà locales.

    .venv/bin/python web/tools/build_city_data.py [--cache-dir DOSSIER ...]

Lecture seule de data/ : graphe routier (data/processed/roads_graph.pkl), emprises des bâtiments dans les réponses
Overpass en cache (data/raw/osm_cache/ et les dossiers --cache-dir), quartiers (data/territories.geojson), secteur
(data/secteur.geojson), plans d'eau (data/water_bodies.geojson). Rien n'est téléchargé.

Distinction réel / illustratif :
- emprises des bâtiments, tracés et revêtement des routes, plans d'eau : OpenStreetMap (ODbL) ;
- hauteur des bâtiments : balises OSM building:levels / height quand elles existent, sinon ESTIMÉE (1 à 3 niveaux,
  tirage déterministe pondéré par la surface) : le fichier marque chaque bâtiment « h_src » = osm | estimee.
Coordonnées : mètres locaux (x vers l'est, z vers le sud) autour de l'origine, en décimètres entiers, codées en deltas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import sys

import shapely
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "dashboard" / "ville" / "data" / "city.json"
M_PER_DEG = 111_320.0
WIDTH = {"motorway": 16, "trunk": 14, "primary": 13, "secondary": 11, "tertiary": 9, "unclassified": 6.5,
         "residential": 6, "living_street": 5, "service": 4, "track": 3.5, "path": 2, "footway": 2}
PAVED = {"asphalt", "paved", "concrete", "concrete:plates", "paving_stones", "sett", "cobblestone"}
MAJOR = {"motorway", "trunk", "primary", "secondary"}


class Proj:
    """Projection équirectangulaire locale, identique à celle du navigateur (map3d/geo.js)."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0, self.k = lat0, lon0, math.cos(math.radians(lat0))

    def __call__(self, lat: float, lon: float) -> tuple[int, int]:
        """(x, z) en décimètres entiers."""
        return round((lon - self.lon0) * self.k * M_PER_DEG * 10), round(-(lat - self.lat0) * M_PER_DEG * 10)


def deltas(points: list[tuple[int, int]]) -> list[int]:
    """[x0, z0, dx1, dz1, ...] : compact en JSON."""
    out, px, pz = [], 0, 0
    for i, (x, z) in enumerate(points):
        out += [x, z] if i == 0 else [x - px, z - pz]
        px, pz = x, z
    return out


def first(value):
    return value[0] if isinstance(value, list) else value


def roads(proj: Proj, cfg: dict, extent) -> list[dict]:
    """Une entrée par paire de nœuds (un sens), identifiant d'arête accepté par l'API (cut_roads edge_id)."""
    with (ROOT / "data" / "processed" / "roads_graph.pkl").open("rb") as fh:
        graph = pickle.load(fh)
    paved_unknown = set(cfg["network"].get("unknown_surface_is_paved_for") or [])
    truck = set(cfg["network"].get("truck_highways") or [])
    seen, out = set(), []
    for u, v, d in graph.edges(data=True):
        key = (min(u, v), max(u, v))
        if key in seen or u == v:
            continue
        seen.add(key)
        hw = str(first(d.get("highway")) or "unclassified").replace("_link", "")
        if hw not in WIDTH:
            continue
        geom = d.get("geometry")
        coords = list(geom.coords) if geom is not None else [(graph.nodes[u]["x"], graph.nodes[u]["y"]),
                                                              (graph.nodes[v]["x"], graph.nodes[v]["y"])]
        if not any(shapely.contains_xy(extent, x, y) for x, y in coords):
            continue
        surface = first(d.get("surface"))
        paved = surface in PAVED if surface else hw in paved_unknown
        out.append({"e": f"{u}-{v}", "k": hw, "w": WIDTH[hw], "p": int(paved), "t": int(hw in truck),
                    "n": first(d.get("name")) or None, "c": deltas([proj(y, x) for x, y in coords])})
    return out


def buildings(proj: Proj, cache_dirs: list[Path], extent) -> tuple[list[list], dict]:
    """Emprises OSM (ways building) ; hauteur OSM si balisée, sinon estimée (déterministe)."""
    from shapely.geometry import Polygon

    seen: set[int] = set()
    out, stats = [], {"osm_height": 0, "estimated_height": 0}
    for folder in cache_dirs:
        for f in sorted(folder.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # cache illisible : ignoré
                continue
            if not isinstance(data, dict):
                continue
            nodes = {e["id"]: (e["lat"], e["lon"]) for e in data.get("elements", []) if e["type"] == "node"}
            for e in data.get("elements", []):
                tags = e.get("tags") or {}
                if e["type"] != "way" or "building" not in tags or e["id"] in seen:
                    continue
                pts = [nodes[n] for n in e.get("nodes", []) if n in nodes]
                if len(pts) < 4 or pts[0] != pts[-1]:
                    continue
                poly = Polygon([(lon, lat) for lat, lon in pts])
                if not poly.is_valid or not shapely.contains_xy(extent, *poly.centroid.coords[0]):
                    continue
                seen.add(e["id"])
                simple = poly.simplify(0.000004, preserve_topology=True)
                ring = [proj(lat, lon) for lon, lat in list(simple.exterior.coords)[:-1]]
                if len(ring) < 3:
                    continue
                levels = tags.get("building:levels")
                height = tags.get("height")
                h_src = "osm"
                try:
                    h = float(str(height).replace("m", "").strip()) if height else float(levels) * 3.2 + 0.6 if levels else None
                except ValueError:
                    h = None
                if h is None or not 2 <= h <= 120:
                    area = poly.area * (M_PER_DEG ** 2) * proj.k
                    r = int(hashlib.md5(str(e["id"]).encode()).hexdigest()[:6], 16) / 0xFFFFFF
                    lv = 1 + (r > 0.72) + (r > 0.93 and area > 160) + (area > 600 and r > 0.5)
                    h, h_src = round(lv * 3.1 + 0.4 + r * 0.8, 1), "estimee"
                stats["osm_height" if h_src == "osm" else "estimated_height"] += 1
                out.append([round(h * 10), 1 if h_src == "osm" else 0, *deltas(ring)])
    return out, stats


def rings(geom, proj: Proj) -> list[list[int]]:
    polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
    return [deltas([proj(lat, lon) for lon, lat in list(p.exterior.coords)[:-1]]) for p in polys if not p.is_empty]


def main() -> int:
    from shapely.geometry import box, shape
    from shapely.ops import unary_union

    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", action="append", default=[])
    args = parser.parse_args()
    cfg = json.loads((ROOT / "config" / "commune_config.json").read_text(encoding="utf-8"))
    sector = unary_union([shape(f["geometry"]) for f in json.loads(
        (ROOT / "data" / "secteur.geojson").read_text(encoding="utf-8"))["features"]])
    terr = json.loads((ROOT / "data" / "territories.geojson").read_text(encoding="utf-8"))["features"]
    c = sector.centroid
    proj = Proj(round(c.y, 6), round(c.x, 6))
    extent = unary_union([sector] + [shape(t["geometry"]) for t in terr]).buffer(0.002)
    caches = [ROOT / "data" / "raw" / "osm_cache", *map(Path, args.cache_dir)]
    blds, hstats = buildings(proj, caches, extent)
    rds = roads(proj, cfg, extent.envelope)
    water = [{"n": f["properties"].get("name"), "r": rings(g, proj)}
             for f in json.loads((ROOT / "data" / "water_bodies.geojson").read_text(encoding="utf-8"))["features"]
             if (g := shape(f["geometry"])).intersects(extent.envelope)]
    territories = [{"id": "pilot", "nom": "Secteur de l'équipe", "approximate": False, "secteur": True,
                    "r": rings(sector, proj)}]
    territories += [{"id": t["properties"]["id"], "nom": t["properties"].get("nom") or t["properties"]["id"],
                     "approximate": bool(t["properties"].get("approximate")), "secteur": False,
                     "r": rings(shape(t["geometry"]), proj)} for t in terr]
    minx, miny, maxx, maxy = extent.bounds
    city = {
        "meta": {
            "commune": cfg.get("commune"), "origin": [proj.lat0, proj.lon0], "unit": "décimètres, deltas", "axes": "x est, z sud",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "extent_lonlat": [round(minx, 5), round(miny, 5), round(maxx, 5), round(maxy, 5)],
            "counts": {"buildings": len(blds), "roads": len(rds), "water": len(water), **hstats},
            "sources": [
                {"data": "emprises des bâtiments, routes, revêtement, plans d'eau", "source": "OpenStreetMap",
                 "license": "ODbL-1.0", "attribution": "© contributeurs OpenStreetMap"},
                {"data": "hauteur des bâtiments sans balise OSM", "source": "estimation déterministe (1 à 3 niveaux)",
                 "license": "-", "attribution": "illustratif, non mesuré"},
                {"data": "limites de quartiers", "source": "cellules de Voronoï autour des nœuds OSM place=suburb",
                 "license": "ODbL-1.0", "attribution": "emprise approximative, pas une limite officielle"}],
            "coverage": "Secteur pilote de 5 km et quartiers téléchargés (Kalgodin, Paglayiri, partie de Tampouy) ; "
                        "le reste de Ouagadougou n'est pas modélisé."},
        "buildings": blds, "roads": rds, "water": water, "territories": territories}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(city, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT} : {OUT.stat().st_size / 1e6:.2f} Mo, {city['meta']['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
