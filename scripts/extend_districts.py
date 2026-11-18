"""Quartiers ajoutables (« nouveau quartier ») : emprises approximatives et données OSM locales.

Une seule exécution, avant la démonstration (réseau requis) :

    python -m scripts.extend_districts            # emprises + téléchargement des routes et bâtiments manquants
    python -m scripts.extend_districts --only-territories

1. Emprises : OSM n'a pas de limites de quartier pour Ouagadougou. Pour chaque nœud OSM ``place=suburb|quarter|
   neighbourhood`` choisi dans ``districts.candidates`` (configuration), l'emprise est la cellule de Voronoï de ce nœud
   parmi tous les nœuds ``place`` de la commune, limitée à un disque de ``districts.radius_m`` et hors du secteur de
   l'équipe. Elle est étiquetée « approximate » : ce n'est pas une limite officielle.
2. Données : routes et bâtiments OSM de chaque quartier (Overpass), fusionnés dans data/processed/roads_graph.pkl et
   data/processed/buildings_centroids.npz. Les quartiers déjà couverts ne sont pas retéléchargés.

Aucune donnée inventée : seuls les noms et positions des nœuds OSM sont utilisés (© contributeurs OpenStreetMap, ODbL).
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from core.config import config_path, load_config, resolve
from core.geo import download
from core.geo.territories import METRES_PER_DEGREE_LAT, commune_polygon, sector_polygon


def _places(cfg: dict[str, Any], raw_dir: Path) -> list[dict[str, Any]]:
    """Nœuds OSM place=suburb|quarter|neighbourhood de l'emprise (cache data/raw/places.json)."""
    cache = raw_dir / "places.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import requests

    b = cfg["bbox"]
    query = (f'[out:json][timeout:90];node["place"~"suburb|quarter|neighbourhood"]'
             f'({b["south"]},{b["west"]},{b["north"]},{b["east"]});out tags;')
    url = str((cfg.get("download") or {}).get("overpass_url") or "https://overpass-api.de/api").rstrip("/")
    for attempt in range(5):  # serveur public souvent saturé : réessais avec attente croissante
        resp = requests.post(url + "/interpreter", data={"data": query}, timeout=120,
                             headers={"User-Agent": "ouaga-clean (logiciel libre, hackathon)"})
        if resp.ok:
            break
        print(f"[quartiers] Overpass HTTP {resp.status_code}, nouvel essai dans {15 * 2 ** attempt} s")
        time.sleep(15 * 2 ** attempt)
    resp.raise_for_status()
    places = [{"osm_id": e["id"], "name": e["tags"].get("name"), "place": e["tags"].get("place"),
               "lat": e["lat"], "lon": e["lon"]} for e in resp.json()["elements"] if e.get("tags", {}).get("name")]
    cache.write_text(json.dumps(places, ensure_ascii=False), encoding="utf-8")
    return places


def _slug(name: str) -> str:
    """Identifiant ASCII stable à partir d'un nom de quartier."""
    import unicodedata

    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return "".join(c if c.isalnum() else "_" for c in text).strip("_")


def build_territories(cfg: dict[str, Any], places: list[dict[str, Any]]) -> dict[str, Any]:
    """FeatureCollection des quartiers candidats : cellule de Voronoï ∩ disque ∩ commune, hors secteur."""
    from shapely.geometry import MultiPoint, Point, mapping
    from shapely.ops import voronoi_diagram

    dcfg = cfg.get("districts") or {}
    wanted = [str(n) for n in dcfg.get("candidates") or []]
    radius = float(dcfg.get("radius_m") or 1500)
    commune, _ = commune_polygon(cfg)
    sector = sector_polygon(cfg)
    cells = voronoi_diagram(MultiPoint([(p["lon"], p["lat"]) for p in places]), envelope=commune.envelope)
    feats = []
    for name in wanted:
        place = next((p for p in places if p["name"] == name), None)
        if place is None:
            print(f"[quartiers] « {name} » absent des nœuds OSM place : ignoré.")
            continue
        pt = Point(place["lon"], place["lat"])
        cell = next(c for c in cells.geoms if c.contains(pt))
        dlat = radius / METRES_PER_DEGREE_LAT
        dlon = radius / (METRES_PER_DEGREE_LAT * math.cos(math.radians(place["lat"])))
        disc = pt.buffer(1.0, 32)
        disc = __import__("shapely.affinity", fromlist=["scale"]).scale(disc, xfact=dlon, yfact=dlat, origin=pt)
        geom = cell.intersection(disc).intersection(commune)
        if sector is not None:
            geom = geom.difference(sector)
        if geom.is_empty:
            print(f"[quartiers] « {name} » : emprise vide après découpe : ignoré.")
            continue
        feats.append({"type": "Feature", "geometry": mapping(geom.simplify(0.0001)), "properties": {
            "id": _slug(name), "nom": name, "name": name, "osm_place_node": place["osm_id"], "place": place["place"],
            "approximate": True,
            "method": f"cellule de Voronoï du nœud OSM place={place['place']} parmi {len(places)} nœuds, "
                      f"limitée à {radius:g} m et hors du secteur de l'équipe ; pas une limite officielle"}})
    return {"type": "FeatureCollection", "license": "ODbL-1.0 (dérivé d'OpenStreetMap)",
            "attribution": download.OSM_ATTRIBUTION, "features": feats}


def _download(cfg: dict[str, Any], raw_dir: Path, polygon: Any) -> tuple[Any, np.ndarray]:
    """Routes (graphe osmnx) et centres des bâtiments d'un polygone, via Overpass."""
    ox = download._configure_osmnx(raw_dir / "osm_cache", cfg)
    graph = download._with_retry("routes", lambda: ox.graph_from_polygon(polygon, network_type="all", retain_all=True))
    gdf = download._with_retry("bâtiments", lambda: ox.features_from_polygon(polygon, tags={"building": True}))
    coords = np.zeros((0, 2))
    if gdf is not None and not gdf.empty:
        cent = gdf.to_crs(3857).geometry.centroid.to_crs(4326)
        coords = np.column_stack([cent.y.to_numpy(), cent.x.to_numpy()])
    return graph, coords


def main() -> int:
    """Construit data/territories.geojson puis complète routes et bâtiments des quartiers non couverts."""
    import networkx as nx
    from shapely.geometry import shape

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only-territories", action="store_true")
    args = parser.parse_args()
    cfg = load_config(config_path())
    raw_dir, out_dir = resolve(cfg["paths"]["raw_dir"]), resolve(cfg["paths"]["processed_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    fc = build_territories(cfg, _places(cfg, raw_dir))
    terr_path = resolve(cfg["paths"]["territories"])
    terr_path.parent.mkdir(parents=True, exist_ok=True)
    terr_path.write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[quartiers] {len(fc['features'])} emprises écrites dans {terr_path} : "
          f"{[f['properties']['id'] for f in fc['features']]}")
    if args.only_territories:
        return 0
    with (out_dir / download.ROADS_PICKLE).open("rb") as fh:
        graph = pickle.load(fh)
    with np.load(out_dir / download.BUILDINGS_FILE) as d:
        lat, lon = np.asarray(d["lat"]), np.asarray(d["lon"])
    margin = float((cfg.get("districts") or {}).get("download_margin_m") or 300)
    meta_path = out_dir / download.META_FILE
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    done = set(meta.get("districts", {}))
    for feat in fc["features"]:
        tid = feat["properties"]["id"]
        if tid in done:
            print(f"[{tid}] déjà téléchargé.")
            continue
        geom = shape(feat["geometry"])
        c = geom.centroid
        deg = margin / (METRES_PER_DEGREE_LAT * math.cos(math.radians(c.y)))
        t0 = time.perf_counter()
        sub, coords = _download(cfg, raw_dir, geom.buffer(deg))
        if sub is None or sub.number_of_nodes() == 0:
            print(f"[{tid}] échec du téléchargement des routes : quartier non couvert.")
            continue
        before = graph.number_of_nodes()
        graph = nx.compose(graph, sub)
        lat, lon = np.concatenate([lat, coords[:, 0]]), np.concatenate([lon, coords[:, 1]])
        key = np.round(lat, 6) * 1e7 + np.round(lon, 6)
        _, first = np.unique(key, return_index=True)
        first.sort()
        lat, lon = lat[first], lon[first]
        meta.setdefault("districts", {})[tid] = {
            "origin": "Overpass", "nodes_added": graph.number_of_nodes() - before, "buildings_in_download": int(len(coords)),
            "download_s": round(time.perf_counter() - t0, 1), "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        print(f"[{tid}] +{graph.number_of_nodes() - before} nœuds, {len(coords)} bâtiments, "
              f"{time.perf_counter() - t0:.0f} s")
        with (out_dir / download.ROADS_PICKLE).open("wb") as fh:
            pickle.dump(graph, fh, protocol=pickle.HIGHEST_PROTOCOL)
        np.savez_compressed(out_dir / download.BUILDINGS_FILE, lat=lat, lon=lon, source=np.array("documented"))
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
