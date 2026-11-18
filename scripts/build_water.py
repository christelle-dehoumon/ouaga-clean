"""Plans d'eau et cours d'eau OSM de la commune (préparation unique, réseau requis la première fois).

    python -m scripts.build_water

- paths.water_bodies (data/water_bodies.geojson) : polygones natural=water (barrages, retenues, mares), pour l'alerte
  PRES_PLAN_EAU du tri.
- paths.waterways (data/processed/waterways.geojson) : lignes waterway=river|stream|canal|drain|ditch, pour les
  coupures de routes par temps de pluie (seuls les types de network.flood_waterway_types coupent).
Réponse Overpass gardée en cache dans paths.raw_dir/water_osm.json. © contributeurs OpenStreetMap, ODbL.
"""

from __future__ import annotations

import json
import sys
import time

from core.config import config_path, load_config, resolve

LINE_TYPES = ("river", "stream", "canal", "drain", "ditch")


def _fetch(cfg: dict) -> dict:
    """Réponse Overpass (cache local d'abord)."""
    cache = resolve(cfg["paths"]["raw_dir"]) / "water_osm.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import requests

    b = cfg["bbox"]
    box = f"{b['south']},{b['west']},{b['north']},{b['east']}"
    query = (f'[out:json][timeout:180];(way["natural"="water"]({box});relation["natural"="water"]({box});'
             f'way["waterway"~"{"|".join(LINE_TYPES)}"]({box}););out geom;')
    url = str((cfg.get("download") or {}).get("overpass_url") or "https://overpass-api.de/api").rstrip("/")
    for attempt in range(5):
        resp = requests.post(url + "/interpreter", data={"data": query}, timeout=240,
                             headers={"User-Agent": "ouaga-clean (logiciel libre, hackathon)"})
        if resp.ok:
            break
        print(f"[eau] Overpass HTTP {resp.status_code}, nouvel essai dans {15 * 2 ** attempt} s")
        time.sleep(15 * 2 ** attempt)
    resp.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(resp.text, encoding="utf-8")
    return resp.json()


def main() -> int:
    from shapely.geometry import LineString, Polygon, mapping
    from shapely.ops import polygonize, unary_union

    cfg = load_config(config_path())
    data = _fetch(cfg)
    polys, lines = [], []
    for e in data.get("elements", []):
        tags = e.get("tags", {})
        if e["type"] == "way" and tags.get("natural") == "water" and len(e.get("geometry", [])) >= 4:
            ring = [(p["lon"], p["lat"]) for p in e["geometry"]]
            if ring[0] == ring[-1]:
                polys.append((Polygon(ring).buffer(0), tags.get("name")))
        elif e["type"] == "relation" and tags.get("natural") == "water":
            outer = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in e.get("members", [])
                     if m.get("role") == "outer" and len(m.get("geometry", [])) >= 2]
            merged = unary_union(list(polygonize(unary_union(outer)))) if outer else None
            if merged is not None and not merged.is_empty:
                polys.append((merged.buffer(0), tags.get("name")))
        elif e["type"] == "way" and tags.get("waterway") in LINE_TYPES and len(e.get("geometry", [])) >= 2:
            lines.append((LineString([(p["lon"], p["lat"]) for p in e["geometry"]]), tags))
    meta = {"source": "documented", "license": "ODbL-1.0", "attribution": "© contributeurs OpenStreetMap"}
    water = {"type": "FeatureCollection", **meta, "features": [
        {"type": "Feature", "geometry": mapping(g.simplify(0.00002)), "properties": {"name": n, "natural": "water"}}
        for g, n in polys if not g.is_empty]}
    ways = {"type": "FeatureCollection", **meta, "features": [
        {"type": "Feature", "geometry": mapping(g.simplify(0.00002)),
         "properties": {"waterway": t.get("waterway"), "name": t.get("name"), "bridge": t.get("bridge")}}
        for g, t in lines]}
    for key, fc in (("water_bodies", water), ("waterways", ways)):
        path = resolve(cfg["paths"][key])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"[eau] {len(fc['features'])} objets écrits dans {path} ({path.stat().st_size / 1024:.0f} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
