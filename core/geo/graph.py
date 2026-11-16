"""Réseau routier en mémoire : quatre vues (masques d'arêtes) en matrices creuses SciPy, index spatial et plus courts chemins."""

from __future__ import annotations

import json
import math
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from core.geo.download import REPO_ROOT, ROADS_PICKLE

VIEW_NAMES: tuple[str, ...] = ("truck_dry", "truck_rain", "tricycle_dry", "tricycle_rain")
EARTH_RADIUS_M = 6_371_008.8
# Longueur minimale d'une arête : scipy ignorerait une arête de poids nul dans une matrice creuse.
MIN_EDGE_M = 1e-3


@dataclass
class RoadView:
    """Une vue du réseau : masque d'arêtes sur le jeu de nœuds commun, matrice CSR des longueurs, index spatial."""

    name: str
    edge_mask: np.ndarray            # bool, par arête du réseau commun
    node_mask: np.ndarray            # bool, nœuds de la plus grande composante fortement connexe
    matrix: csr_matrix               # n x n, poids : mètres (sec) ou mètres équivalents (pluie)
    length: csr_matrix               # n x n, même structure, longueurs réelles en mètres
    node_ids: np.ndarray             # identifiants OSM, partagés avec le réseau
    lat: np.ndarray
    lon: np.ndarray
    tree_idx: np.ndarray             # indices (dans node_ids) des nœuds indexés par tree
    tree: cKDTree | None
    origin: tuple[float, float]      # (lat0, lon0) de la projection locale

    @property
    def n_nodes(self) -> int:
        """Nombre de nœuds de la vue (plus grande composante)."""
        return int(self.node_mask.sum())

    @property
    def n_edges(self) -> int:
        """Nombre d'arêtes orientées de la vue."""
        return int(self.matrix.nnz)


@dataclass
class Network:
    """Nœuds communs, correspondance indice <-> identifiant, et les quatre vues."""

    node_ids: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    index_of: dict[int, int]
    views: dict[str, RoadView]
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    load_s: float = 0.0
    stats: dict[str, int] = field(default_factory=dict)


def project(lat: np.ndarray, lon: np.ndarray, origin: tuple[float, float]) -> np.ndarray:
    """Projection équirectangulaire locale en mètres (suffisante à l'échelle d'une commune)."""
    lat0, lon0 = origin
    x = np.radians(np.asarray(lon, dtype=float) - lon0) * math.cos(math.radians(lat0)) * EARTH_RADIUS_M
    y = np.radians(np.asarray(lat, dtype=float) - lat0) * EARTH_RADIUS_M
    return np.column_stack([x, y])


def _as_set(value: Any) -> set[str]:
    """Balise OSM (texte ou liste après simplification) en ensemble de valeurs, suffixe « _link » retiré."""
    values = value if isinstance(value, (list, tuple, set)) else [value]
    out = set()
    for v in values:
        if isinstance(v, str) and v:
            out.add(v[:-5] if v.endswith("_link") else v)
    return out


def _flag(value: Any) -> bool:
    """Vrai si une balise OSM est présente avec une valeur autre que « no »."""
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return any(isinstance(v, str) and v and v != "no" for v in values)


def _str_list(value: Any) -> set[str]:
    """Liste de configuration en ensemble de textes (vide si absurde)."""
    return {v for v in value if isinstance(v, str)} if isinstance(value, list) else set()


def _read_geojson(cfg: dict[str, Any], key: str, kinds: tuple[str, ...], label: str,
                  assumptions: list[str], warnings: list[str], waterway_types: set[str] | None = None) -> list[Any]:
    """Géométries des types demandés lues dans paths.<key> ; si waterway_types est donné, seuls ces cours d'eau sont gardés."""
    from shapely.geometry import shape

    path_str = cfg.get("paths", {}).get(key) if isinstance(cfg.get("paths"), dict) else None
    if not isinstance(path_str, str) or not path_str:
        assumptions.append(f"Aucun fichier de {label} configuré (paths.{key}) : critère ignoré par temps de pluie.")
        return []
    path = Path(path_str) if Path(path_str).is_absolute() else REPO_ROOT / path_str
    if not path.exists():
        assumptions.append(f"Fichier de {label} absent ({path_str}) : critère ignoré par temps de pluie.")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        feats = data.get("features", []) if data.get("type") == "FeatureCollection" else [data]
        if waterway_types is not None:
            feats = [f for f in feats if (f.get("properties") or {}).get("waterway") in waterway_types]
        geoms = [shape(f["geometry"] if "geometry" in f else f) for f in feats]
        return [g for g in geoms if g.geom_type in kinds and not g.is_empty]
    except Exception as exc:  # fichier fourni par un humain : tout format cassé donne un repli
        warnings.append(f"Fichier de {label} illisible ({path_str}) : {exc}. Critère ignoré par temps de pluie.")
        return []


def _edge_lines(edges: list[tuple[int, int, dict[str, Any]]], lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Tracé de chaque arête (géométrie osmnx, ou segment droit entre ses deux nœuds)."""
    from shapely.geometry import LineString

    return np.array([d.get("geometry") or LineString([(lon[ui], lat[ui]), (lon[vi], lat[vi])]) for ui, vi, d in edges],
                    dtype=object)


def _to_metres(geoms: Any, origin: tuple[float, float]) -> Any:
    """Géométries lon/lat passées dans la projection locale en mètres."""
    import shapely

    return shapely.transform(geoms, lambda c: project(c[:, 1], c[:, 0], origin))


def _near_waterway(lines_m: Any, waterways: list[Any], buffer_m: float, origin: tuple[float, float]) -> np.ndarray:
    """Masque des arêtes dont le milieu est à moins de buffer_m d'un cours d'eau."""
    import shapely

    mask = np.zeros(len(lines_m), dtype=bool)
    if not waterways or not len(lines_m):
        return mask
    mids = shapely.line_interpolate_point(lines_m, 0.5, normalized=True)
    _, edge_idx = shapely.STRtree(mids).query(_to_metres(np.array(waterways, dtype=object), origin),
                                               predicate="dwithin", distance=buffer_m)
    mask[np.unique(edge_idx)] = True
    return mask


def _in_flood_zone(lines: Any, polys: list[Any]) -> np.ndarray:
    """Masque des arêtes dont le tracé coupe un polygone de zone inondable."""
    import shapely

    mask = np.zeros(len(lines), dtype=bool)
    if not polys or not len(lines):
        return mask
    _, edge_idx = shapely.STRtree(lines).query(polys, predicate="intersects")
    mask[np.unique(edge_idx)] = True
    return mask


def _view(name: str, mask: np.ndarray, u: np.ndarray, v: np.ndarray, weight: np.ndarray, length: np.ndarray,
          node_ids: np.ndarray, lat: np.ndarray, lon: np.ndarray, origin: tuple[float, float]) -> RoadView:
    """Construit une vue : arêtes parallèles réduites au plus léger, plus grande composante fortement connexe, index spatial."""
    n = len(node_ids)
    mu, mv, ml, mr = u[mask], v[mask], weight[mask], length[mask]
    node_mask = np.zeros(n, dtype=bool)
    if len(mu):
        order = np.lexsort((ml, mv, mu))
        mu, mv, ml, mr = mu[order], mv[order], ml[order], mr[order]
        keep = np.ones(len(mu), dtype=bool)
        keep[1:] = (mu[1:] != mu[:-1]) | (mv[1:] != mv[:-1])
        mu, mv, ml, mr = mu[keep], mv[keep], ml[keep], mr[keep]
        full = csr_matrix((ml, (mu, mv)), shape=(n, n))
        touched = np.zeros(n, dtype=bool)
        touched[mu] = True
        touched[mv] = True
        _, labels = connected_components(full, directed=True, connection="strong")
        counts = np.bincount(labels[touched], minlength=labels.max() + 1)
        node_mask = labels == int(np.argmax(counts))
        node_mask &= touched
        inside = node_mask[mu] & node_mask[mv]
        mu, mv, ml, mr = mu[inside], mv[inside], ml[inside], mr[inside]
    matrix = csr_matrix((ml, (mu, mv)), shape=(n, n))
    real = csr_matrix((mr, (mu, mv)), shape=(n, n))
    edge_mask = mask.copy()
    edge_mask[mask] = node_mask[u[mask]] & node_mask[v[mask]]
    tree_idx = np.flatnonzero(node_mask)
    tree = cKDTree(project(lat[tree_idx], lon[tree_idx], origin)) if len(tree_idx) else None
    return RoadView(name, edge_mask, node_mask, matrix, real, node_ids, lat, lon, tree_idx, tree, origin)


def build_network(graph: Any, cfg: dict[str, Any]) -> Network:
    """Construit les quatre vues à partir d'un graphe NetworkX orienté (x = lon, y = lat, length en mètres)."""
    t0 = time.perf_counter()
    assumptions: list[str] = []
    warnings: list[str] = []
    net_cfg = cfg.get("network", {}) if isinstance(cfg.get("network"), dict) else {}
    truck_hw = _str_list(net_cfg.get("truck_highways"))
    tricycle_hw = truck_hw | _str_list(net_cfg.get("tricycle_extra_highways"))
    unpaved = _str_list(net_cfg.get("unpaved_surfaces"))
    paved_unknown = _str_list(net_cfg.get("unknown_surface_is_paved_for"))
    factor = net_cfg.get("rain_unpaved_factor", 1.0)
    factor = float(factor) if isinstance(factor, (int, float)) and math.isfinite(factor) and factor > 0 else 1.0
    buffer_m = net_cfg.get("flood_buffer_m", 0)
    buffer_m = float(buffer_m) if isinstance(buffer_m, (int, float)) and math.isfinite(buffer_m) and buffer_m > 0 else 0.0

    nodes = [(nid, d.get("y"), d.get("x")) for nid, d in graph.nodes(data=True)]
    nodes = [(nid, y, x) for nid, y, x in nodes if isinstance(y, (int, float)) and isinstance(x, (int, float))
             and math.isfinite(y) and math.isfinite(x)]
    node_ids = np.array([nid for nid, _, _ in nodes], dtype=np.int64)
    lat = np.array([y for _, y, _ in nodes], dtype=float)
    lon = np.array([x for _, _, x in nodes], dtype=float)
    index_of = {int(nid): i for i, nid in enumerate(node_ids)}
    ford_nodes = {int(nid) for nid, d in graph.nodes(data=True) if _flag(d.get("ford"))}
    origin = (float(np.mean(lat)), float(np.mean(lon))) if len(lat) else (0.0, 0.0)

    edges: list[tuple[int, int, dict[str, Any]]] = []
    ford_node_edge: list[bool] = []
    for a, b, d in graph.edges(data=True):
        ui, vi = index_of.get(a), index_of.get(b)
        ln = d.get("length")
        if ui is None or vi is None or ui == vi or not isinstance(ln, (int, float)) or not math.isfinite(ln) or ln < 0:
            continue
        edges.append((ui, vi, d))
        ford_node_edge.append(a in ford_nodes or b in ford_nodes)
    u = np.array([e[0] for e in edges], dtype=np.int32)
    v = np.array([e[1] for e in edges], dtype=np.int32)
    length = np.maximum(np.array([float(e[2]["length"]) for e in edges], dtype=float), MIN_EDGE_M)

    hw = [_as_set(d.get("highway")) for _, _, d in edges]
    surf = [_as_set(d.get("surface")) for _, _, d in edges]
    is_truck = np.array([bool(h) and h <= truck_hw for h in hw], dtype=bool)
    is_tricycle = np.array([bool(h) and h <= tricycle_hw for h in hw], dtype=bool)
    has_surface = np.array([bool(s) for s in surf], dtype=bool)
    is_unpaved = np.array([bool(s & unpaved) if s else not (bool(h) and h <= paved_unknown)
                           for s, h in zip(surf, hw)], dtype=bool)
    tagged_cut = np.array([_flag(d.get("ford")) or _flag(d.get("flood_prone")) for _, _, d in edges], dtype=bool)
    tagged_cut |= np.array(ford_node_edge, dtype=bool)
    crossing = np.array([_flag(d.get("bridge")) or _flag(d.get("tunnel")) for _, _, d in edges], dtype=bool)
    flood_types = _str_list(net_cfg.get("flood_waterway_types"))
    waterways = _read_geojson(cfg, "waterways", ("LineString", "MultiLineString"), "cours d'eau", assumptions, warnings,
                              flood_types)
    polys = _read_geojson(cfg, "flood_zones", ("Polygon", "MultiPolygon"), "zones inondables", assumptions, warnings)
    lines = _edge_lines(edges, lat, lon) if (waterways and buffer_m) or polys else np.zeros(0, dtype=object)
    near_water = _near_waterway(_to_metres(lines, origin), waterways, buffer_m, origin) if waterways and buffer_m \
        else np.zeros(len(edges), dtype=bool)
    near_water &= ~crossing
    in_zone = _in_flood_zone(lines, polys) if polys else np.zeros(len(edges), dtype=bool)
    rain_cut = tagged_cut | near_water | in_zone
    rain_weight = np.where(is_unpaved, length * factor, length)

    assumptions.append("Une arête issue de plusieurs voies OSM n'est ouverte à un véhicule que si toutes ses voies le sont ; "
                       "« X_link » est traité comme « X ».")
    assumptions.append(f"Surface absente sur {int((~has_surface).sum())} arêtes sur {len(edges)} : revêtue seulement pour "
                       f"les voies {sorted(paved_unknown)}, non revêtue sinon (network.unknown_surface_is_paved_for).")
    assumptions.append(f"Vues de pluie : poids en mètres équivalents, longueur × {factor} (network.rain_unpaved_factor) sur les "
                       "voies non revêtues ou de revêtement inconnu hors grands axes ; distances et coûts en mètres réels.")
    assumptions.append(f"Pluie : voie coupée si gué ou flood_prone, si son milieu est à moins de {buffer_m:g} m "
                       f"(network.flood_buffer_m) d'un cours d'eau OSM de type {sorted(flood_types)} (network.flood_waterway_types ; "
                       "drain et ditch, souvent des caniveaux de rue, ne coupent pas) hors pont ou tunnel, "
                       "ou si elle coupe une zone inondable.")
    assumptions.append("Chaque vue ne garde que sa plus grande composante fortement connexe (aller et retour possibles).")

    masks = {
        "truck_dry": is_truck,
        "truck_rain": is_truck & ~rain_cut,
        "tricycle_dry": is_tricycle,
        "tricycle_rain": is_tricycle & ~rain_cut,
    }
    views = {name: _view(name, m, u, v, rain_weight if name.endswith("_rain") else length, length,
                         node_ids, lat, lon, origin) for name, m in masks.items()}
    for name, view in views.items():
        if view.n_nodes == 0:
            warnings.append(f"La vue « {name} » est vide : aucune voie ne correspond à la configuration.")
    stats = {"edges": len(edges), "edges_with_surface": int(has_surface.sum()), "edges_unpaved_or_unknown": int(is_unpaved.sum()),
             "rain_cut": int(rain_cut.sum()), "rain_cut_tagged": int(tagged_cut.sum()),
             "rain_cut_waterway": int(near_water.sum()), "rain_cut_flood_zone": int(in_zone.sum()),
             "rain_cut_truck": int((is_truck & rain_cut).sum()), "rain_cut_tricycle": int((is_tricycle & rain_cut).sum())}
    return Network(node_ids, lat, lon, index_of, views, assumptions, warnings, time.perf_counter() - t0, stats)


def _empty_network(message: str) -> Network:
    """Réseau vide, pour ne jamais lever d'exception quand les données manquent."""
    return Network(
        np.zeros(0, dtype=np.int64), np.zeros(0), np.zeros(0), {},
        {name: _view(name, np.zeros(0, dtype=bool), np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32),
                     np.zeros(0), np.zeros(0), np.zeros(0, dtype=np.int64), np.zeros(0), np.zeros(0), (0.0, 0.0))
         for name in VIEW_NAMES},
        [], [message], 0.0)


def load_network(cfg: dict[str, Any]) -> Network:
    """Lit le graphe de data/processed/ (NetworkX ne sert qu'ici) et construit les quatre vues ; réseau vide si absent."""
    t0 = time.perf_counter()
    processed = cfg.get("paths", {}).get("processed_dir", "data/processed") if isinstance(cfg.get("paths"), dict) else "data/processed"
    path = Path(processed) if Path(str(processed)).is_absolute() else REPO_ROOT / str(processed)
    path = path / ROADS_PICKLE
    if not path.exists():
        return _empty_network(f"Réseau routier introuvable ({path}) : lancer une fois « python -m core.geo.download ».")
    try:
        with path.open("rb") as fh:
            graph = pickle.load(fh)
        net = build_network(graph, cfg)
    except Exception as exc:  # fichier corrompu ou d'une autre version : repli sans plantage
        return _empty_network(f"Réseau routier illisible ({path}) : {exc}.")
    net.load_s = time.perf_counter() - t0
    return net


def nearest_node(view: RoadView, lat: Any, lon: Any) -> tuple[int, float] | None:
    """Nœud de la vue le plus proche de (lat, lon) et sa distance en mètres ; None si entrée invalide ou vue vide."""
    if view.tree is None:
        return None
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(la) and math.isfinite(lo) and -90 <= la <= 90 and -180 <= lo <= 180):
        return None
    dist, k = view.tree.query(project(np.array([la]), np.array([lo]), view.origin)[0])
    return int(view.node_ids[view.tree_idx[int(k)]]), float(dist)


def shortest_paths(view: RoadView, index_of: dict[int, int], sources: list[int]) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Dijkstra depuis toutes les sources en un seul appel : (distances m, prédécesseurs, sources retenues)."""
    kept = [s for s in sources if s in index_of and view.node_mask[index_of[s]]]
    n = len(view.node_ids)
    if not kept:
        return np.zeros((0, n)), np.zeros((0, n), dtype=np.int32), []
    idx = np.array([index_of[s] for s in kept], dtype=np.int32)
    dist, pred = dijkstra(view.matrix, directed=True, indices=idx, return_predecessors=True)
    return dist, pred, kept
