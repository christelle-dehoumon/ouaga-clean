"""Préparation unique des routes et bâtiments OSM : fichiers locaux de data/raw/ d'abord, Overpass seulement s'ils manquent (seul module autorisé à utiliser le réseau)."""

from __future__ import annotations

import argparse
import inspect
import json
import math
import pickle
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

import numpy as np

from core.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
# Fichiers locaux fournis (extraits Geofabrik), lus en priorité dans paths.raw_dir.
LOCAL_ROADS_XML = "ouaga_roads.osm"
LOCAL_PBF = "ouaga.osm.pbf"
# Fichiers produits.
BOUNDARY_FILE = "boundary.geojson"
ROADS_PICKLE = "roads_graph.pkl"
BUILDINGS_FILE = "buildings_centroids.npz"
WATERWAYS_FILE = "waterways.geojson"
META_FILE = "download_meta.json"
# Réglages de téléchargement (pas des paramètres métier) : petits morceaux mis en cache pour survivre à un réseau instable.
CHUNK_AREA_M2 = 25_000_000
REQUEST_TIMEOUT_S = 120
RETRY_PAUSE_S = 10
OSM_ATTRIBUTION = "© contributeurs OpenStreetMap, licence ODbL"

# Balises d'arête utiles au modèle de pluie, gardées en plus des balises osmnx par défaut.
ROAD_EDGE_TAGS = ("surface", "bridge", "tunnel", "ford", "flood_prone", "width", "lanes")
# Balises de nœud gardées ; un nœud qui en porte une reste une extrémité d'arête après simplification.
ROAD_NODE_TAGS = ("ford",)

T = TypeVar("T")


def _resolve(path_str: str) -> Path:
    """Chemin de la configuration rendu absolu par rapport à la racine du dépôt."""
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


def _human_size(path: Path) -> str:
    """Taille lisible d'un fichier."""
    size = float(path.stat().st_size)
    for unit in ("o", "Ko", "Mo"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} Go"


def _with_retry(label: str, fn: Callable[[], T]) -> T | None:
    """Exécute fn, réessaie une seule fois en cas d'échec, renvoie None si les deux essais échouent."""
    for attempt in (1, 2):
        try:
            print(f"[{label}] essai {attempt}…", flush=True)
            return fn()
        except Exception as exc:  # noqa: BLE001 - le réseau peut lever n'importe quoi ; on rapporte et on continue
            print(f"[{label}] échec à l'essai {attempt} : {type(exc).__name__}: {exc}", flush=True)
            if attempt == 1:
                time.sleep(RETRY_PAUSE_S)
    return None


OSMNX_MIN = "2.0"         # simplify_graph(node_attrs_include=...) n'existe qu'à partir d'OSMnx 2.0 (absent en 1.9.4)


def check_osmnx(ox: Any) -> None:
    """Lève une erreur claire si l'OSMnx installé n'accepte pas simplify_graph(node_attrs_include=...)."""
    if "node_attrs_include" not in inspect.signature(ox.simplify_graph).parameters:
        raise RuntimeError(f"Version d'OSMnx incompatible ({getattr(ox, '__version__', '?')} installée), attendu >= {OSMNX_MIN} : "
                           "simplify_graph n'accepte pas node_attrs_include. Installer requirements.txt.")


def _configure_osmnx(cache_dir: Path, cfg: dict[str, Any] | None = None) -> Any:
    """Importe osmnx (version vérifiée) et règle le cache disque, les délais et le serveur Overpass (download.overpass_url)."""
    import osmnx as ox

    check_osmnx(ox)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(cache_dir)
    ox.settings.requests_timeout = REQUEST_TIMEOUT_S
    ox.settings.max_query_area_size = CHUNK_AREA_M2
    url = ((cfg or {}).get("download") or {}).get("overpass_url") if isinstance(cfg, dict) else None
    if isinstance(url, str) and url:
        ox.settings.overpass_url = url.rstrip("/")
    ox.settings.log_console = False
    _keep_road_tags(ox)
    return ox


def _keep_road_tags(ox: Any) -> None:
    """Ajoute aux réglages osmnx les balises d'arête et de nœud nécessaires au modèle de pluie."""
    ox.settings.useful_tags_way = list(dict.fromkeys([*ox.settings.useful_tags_way, *ROAD_EDGE_TAGS]))
    ox.settings.useful_tags_node = list(dict.fromkeys([*ox.settings.useful_tags_node, *ROAD_NODE_TAGS]))


def _boundary(ox: Any, cfg: dict[str, Any], raw_dir: Path) -> Any:
    """Contour de l'emprise pour Overpass : fichier existant, sinon géocodage, sinon rectangle bbox."""
    import geopandas as gpd
    from shapely.geometry import box

    path = raw_dir / BOUNDARY_FILE
    if path.exists():
        return gpd.read_file(path).geometry.union_all()
    if cfg["place_query"]:
        gdf = _with_retry("contour", lambda: ox.geocode_to_gdf(cfg["place_query"]))
        if gdf is not None and not gdf.empty and gdf.geometry.iloc[0].geom_type in ("Polygon", "MultiPolygon"):
            gdf[["geometry"]].assign(emprise="commune", source="documented").to_file(path, driver="GeoJSON")
            return gdf.geometry.iloc[0]
    if cfg["bbox"] is None:
        raise RuntimeError("Ni contour de commune ni emprise « bbox » valide dans la configuration.")
    print("[contour] ATTENTION : emprise réduite au rectangle « bbox » de la configuration.")
    bbox = cfg["bbox"]
    return box(bbox["west"], bbox["south"], bbox["east"], bbox["north"])


def _pilot_boundary(cfg: dict[str, Any], buffer_m: float = 0.0) -> Any:
    """Emprise de la zone pilote officielle avec marge optionnelle en mètres."""
    from shapely.geometry import box
    from core.geo.territories import _pilot_square, METRES_PER_DEGREE_LAT

    square = _pilot_square(cfg, np.zeros(0), np.zeros(0), [])
    if square is None:
        raise RuntimeError("Impossible de déterminer la zone pilote.")
    if buffer_m <= 0:
        return square
    minx, miny, maxx, maxy = square.bounds
    center_lat = (miny + maxy) / 2.0
    dlat = buffer_m / METRES_PER_DEGREE_LAT
    dlon = buffer_m / (METRES_PER_DEGREE_LAT * math.cos(math.radians(center_lat)))
    return box(minx - dlon, miny - dlat, maxx + dlon, maxy + dlat)


def roads_from_xml(xml_path: Path) -> Any:
    """Graphe routier osmnx construit depuis un fichier OSM XML local, balises de pluie gardées."""
    import osmnx as ox

    check_osmnx(ox)
    _keep_road_tags(ox)
    graph = ox.graph_from_xml(xml_path, simplify=False, retain_all=True)
    return ox.simplify_graph(graph, node_attrs_include=list(ROAD_NODE_TAGS))


def waterways_from_osm(osm_path: Path, types: set[str]) -> list[dict[str, Any]]:
    """Lit un fichier OSM en flux et renvoie les cours d'eau (ways « waterway » des types demandés) en Features GeoJSON."""
    import osmium

    class _Handler(osmium.SimpleHandler):  # type: ignore[misc]
        """Accumule le tracé de chaque way cours d'eau."""

        def __init__(self) -> None:
            super().__init__()
            self.features: list[dict[str, Any]] = []

        def way(self, w: Any) -> None:
            """Garde le tracé si le type de cours d'eau est demandé."""
            kind = w.tags.get("waterway")
            if kind not in types:
                return
            pts = [[n.location.lon, n.location.lat] for n in w.nodes if n.location.valid()]
            if len(pts) < 2:
                return
            self.features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": pts},
                                  "properties": {"osm_id": w.id, "waterway": kind, "name": w.tags.get("name"),
                                                 "source": "documented"}})

    handler = _Handler()
    handler.apply_file(str(osm_path), locations=True, idx="flex_mem")
    return handler.features


def building_centroids_from_osm(osm_path: Path) -> tuple[np.ndarray, int]:
    """Lit un fichier OSM (pbf ou xml) en flux et renvoie (centres lat/lon des ways « building », ways ignorés)."""
    import osmium

    class _Handler(osmium.SimpleHandler):  # type: ignore[misc]
        """Accumule le centre de chaque way bâtiment, sans garder de géométrie."""

        def __init__(self) -> None:
            super().__init__()
            self.coords: list[tuple[float, float]] = []
            self.skipped = 0

        def way(self, w: Any) -> None:
            """Moyenne des coordonnées des nœuds du way (le nœud de fermeture compté une fois)."""
            if "building" not in w.tags:
                return
            nodes = list(w.nodes)
            if len(nodes) > 1 and nodes[0].ref == nodes[-1].ref:
                nodes = nodes[:-1]
            pts = [(n.location.lat, n.location.lon) for n in nodes if n.location.valid()]
            if not pts:
                self.skipped += 1
                return
            self.coords.append((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))

    handler = _Handler()
    handler.apply_file(str(osm_path), locations=True, idx="flex_mem")
    return np.asarray(handler.coords, dtype=np.float64).reshape(-1, 2), handler.skipped


def _prepare_roads(cfg: dict[str, Any], raw_dir: Path, out_dir: Path, force: bool,
                   pilot: bool = False) -> dict[str, Any] | None:
    """Graphe routier enregistré en pickle : fichier local d'abord, Overpass sinon ; renvoie ses chiffres."""
    out = out_dir / ROADS_PICKLE
    if out.exists() and not force:
        print(f"[routes] déjà présent : {out.name} ({_human_size(out)})")
        return None
    local = raw_dir / LOCAL_ROADS_XML
    start = time.perf_counter()
    if local.exists():
        print(f"[routes] lecture locale de {local.name} ({_human_size(local)})…", flush=True)
        graph, origin = roads_from_xml(local), f"fichier local {local.name}"
    else:
        ox = _configure_osmnx(raw_dir / "osm_cache", cfg)
        if pilot:
            print("[routes] téléchargement Overpass (zone pilote avec marge de 500 m).", flush=True)
            polygon = _pilot_boundary(cfg, buffer_m=500.0)
            origin = "Overpass (zone pilote)"
        else:
            print(f"[routes] {local.name} absent : téléchargement Overpass.")
            polygon = _boundary(ox, cfg, raw_dir)
            origin = "Overpass"
        graph = _with_retry("routes", lambda: ox.graph_from_polygon(polygon, network_type="all", retain_all=True))
        if graph is None or graph.number_of_nodes() == 0:
            print("[routes] Échec : graphe vide ou non récupéré.", flush=True)
            return {"ok": False}
    build_s = time.perf_counter() - start
    tmp_out = out.with_suffix(".tmp")
    try:
        with tmp_out.open("wb") as fh:
            pickle.dump(graph, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp_out.replace(out)
    except Exception as exc:
        if tmp_out.exists():
            tmp_out.unlink()
        print(f"[routes] échec écriture atomique : {exc}", flush=True)
        return {"ok": False}
    start = time.perf_counter()
    with out.open("rb") as fh:
        pickle.load(fh)
    load_s = time.perf_counter() - start
    stats = {"ok": True, "origin": origin, "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
             "build_s": round(build_s, 1), "pickle_load_s": round(load_s, 2), "size": _human_size(out)}
    print(f"[routes] {out.name} ({stats['size']}) — {stats['nodes']} nœuds, {stats['edges']} arêtes ; "
          f"construction {stats['build_s']} s, rechargement {stats['pickle_load_s']} s")
    return stats


def _prepare_buildings(cfg: dict[str, Any], raw_dir: Path, out_dir: Path, force: bool,
                       pilot: bool = False) -> dict[str, Any] | None:
    """Centres des bâtiments en tableau lat/lon : pbf local d'abord, Overpass sinon ; renvoie leurs chiffres."""
    out = out_dir / BUILDINGS_FILE
    if out.exists() and not force:
        print(f"[bâtiments] déjà présent : {out.name} ({_human_size(out)})")
        return None
    local = raw_dir / LOCAL_PBF
    start = time.perf_counter()
    skipped = 0
    if local.exists():
        print(f"[bâtiments] lecture en flux de {local.name} ({_human_size(local)})…", flush=True)
        coords, skipped = building_centroids_from_osm(local)
        origin = f"fichier local {local.name}"
    else:
        ox = _configure_osmnx(raw_dir / "osm_cache", cfg)
        if pilot:
            print("[bâtiments] téléchargement Overpass (zone pilote).", flush=True)
            polygon = _pilot_boundary(cfg, buffer_m=0.0)
            origin = "Overpass (zone pilote)"
        else:
            print(f"[bâtiments] {local.name} absent : téléchargement Overpass.")
            polygon = _boundary(ox, cfg, raw_dir)
            origin = "Overpass"
        gdf = _with_retry("bâtiments", lambda: ox.features_from_polygon(polygon, tags={"building": True}))
        if gdf is None or gdf.empty:
            print("[bâtiments] Échec : aucun bâtiment récupéré.", flush=True)
            return {"ok": False}
        cent = gdf.geometry.centroid
        coords, origin = np.column_stack([cent.y.to_numpy(), cent.x.to_numpy()]), origin
    if len(coords) == 0:
        print("[bâtiments] Échec : coordonnées des bâtiments vides.", flush=True)
        return {"ok": False}
    build_s = time.perf_counter() - start
    tmp_out = out.with_suffix(".tmp.npz")
    try:
        np.savez_compressed(tmp_out, lat=coords[:, 0], lon=coords[:, 1], source=np.array("documented"))
        tmp_out.replace(out)
    except Exception as exc:
        if tmp_out.exists():
            tmp_out.unlink()
        print(f"[bâtiments] échec écriture atomique : {exc}", flush=True)
        return {"ok": False}
    stats = {"ok": True, "origin": origin, "buildings": int(len(coords)), "ways_without_location": skipped,
             "build_s": round(build_s, 1), "size": _human_size(out)}
    print(f"[bâtiments] {out.name} ({stats['size']}) — {stats['buildings']} centres ; lecture {stats['build_s']} s")
    return stats


def _prepare_waterways(cfg: dict[str, Any], raw_dir: Path, out_dir: Path, force: bool) -> dict[str, Any] | None:
    """Cours d'eau OSM en GeoJSON, extraits du pbf local (pas de téléchargement) ; renvoie leurs chiffres."""
    out = _resolve(cfg["paths"]["waterways"])
    if out.exists() and not force:
        print(f"[cours d'eau] déjà présent : {out.name} ({_human_size(out)})")
        return None
    local = raw_dir / LOCAL_PBF
    if not local.exists():
        print(f"[cours d'eau] {local.name} absent : cours d'eau non extraits (le modèle de pluie s'en passera).")
        return {"ok": False}
    types = {t for t in cfg["network"]["flood_waterway_types"] if isinstance(t, str)}
    start = time.perf_counter()
    features = waterways_from_osm(local, types)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "source": "documented", "attribution": OSM_ATTRIBUTION,
                               "features": features}, ensure_ascii=False), encoding="utf-8")
    counts: dict[str, int] = {}
    for f in features:
        counts[f["properties"]["waterway"]] = counts.get(f["properties"]["waterway"], 0) + 1
    stats = {"ok": True, "origin": f"fichier local {local.name}", "waterways": len(features), "by_type": counts,
             "build_s": round(time.perf_counter() - start, 1), "size": _human_size(out)}
    print(f"[cours d'eau] {out.name} ({stats['size']}) — {len(features)} tracés {counts}")
    return stats


def _update_meta(out_dir: Path, roads: dict[str, Any] | None, buildings: dict[str, Any] | None,
                 waterways: dict[str, Any] | None) -> dict[str, Any]:
    """Met à jour le fichier de provenance et de chiffres."""
    path = out_dir / META_FILE
    meta: dict[str, Any] = {}
    if path.exists():
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta.update({"source": "documented", "attribution": OSM_ATTRIBUTION})
    if roads and roads.get("ok"):
        meta["roads"] = {**roads, "prepared_at": now, "file": ROADS_PICKLE}
    if buildings and buildings.get("ok"):
        meta["buildings"] = {**buildings, "prepared_at": now, "file": BUILDINGS_FILE,
                             "note": "centre = moyenne des nœuds de chaque way « building » ; relations multipolygones non comptées"}
    if waterways and waterways.get("ok"):
        meta["waterways"] = {**waterways, "prepared_at": now, "file": WATERWAYS_FILE}
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def run(config_path: str, force: bool = False, pilot: bool = False) -> int:
    """Prépare ce qui manque dans data/processed/ ; renvoie 0 si tout est présent, 1 sinon."""
    cfg = load_config(config_path)
    for warning in cfg["_warnings"]:
        print(f"[configuration] {warning}")
    raw_dir = _resolve(cfg["paths"]["raw_dir"])
    out_dir = _resolve(cfg["paths"]["processed_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any] | None] = {}
    for name, step, is_pilot_step in ((ROADS_PICKLE, _prepare_roads, True),
                                      (BUILDINGS_FILE, _prepare_buildings, True),
                                      (WATERWAYS_FILE, _prepare_waterways, False)):
        try:
            results[name] = step(cfg, raw_dir, out_dir, force, pilot) if is_pilot_step else step(cfg, raw_dir, out_dir, force)
        except Exception as exc:  # noqa: BLE001 - toute erreur devient un message, jamais un plantage
            print(f"[{name}] échec : {type(exc).__name__}: {exc}")
            results[name] = {"ok": False}
    meta = _update_meta(out_dir, results[ROADS_PICKLE], results[BUILDINGS_FILE], results[WATERWAYS_FILE])
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    missing = [name for name, res in results.items() if res and not res.get("ok")]
    if missing:
        print("MANQUANT : " + ", ".join(missing) + ".")
        return 1
    return 0


def main() -> None:
    """Point d'entrée en ligne de commande : python -m core.geo.download."""
    parser = argparse.ArgumentParser(description="Prépare une fois les données OpenStreetMap de la commune.")
    from core.config import config_path

    parser.add_argument("--config", default=str(config_path()))
    parser.add_argument("--force", action="store_true", help="refait la préparation même si les fichiers existent")
    parser.add_argument("--pilot", action="store_true", help="limite le téléchargement Overpass à la zone pilote")
    args = parser.parse_args()
    sys.exit(run(args.config, args.force, args.pilot))


if __name__ == "__main__":
    main()
