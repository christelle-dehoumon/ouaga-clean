"""Points de regroupement : KMeans pondéré sur la demande, recalage sur le réseau, fusion (section 6 des règles)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from sklearn.cluster import KMeans

from core.geo.graph import EARTH_RADIUS_M, Network, nearest_node, project

# Graine fixe : même entrée, mêmes points.
SEED = 0


def _num(value: Any, default: float) -> float:
    """Nombre fini positif ou nul, sinon default."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return default
    return float(value)


def _dumpsite_points(dumpsites: Any, model: dict[str, Any], warnings: list[str]) -> list[tuple[float, float, float]]:
    """Dépotoirs actifs valides en (lat, lon, kg) ; les entrées invalides sont ignorées et comptées."""
    if not isinstance(dumpsites, list):
        return []
    by_size = model.get("dumpsite_kg_by_size") if isinstance(model.get("dumpsite_kg_by_size"), dict) else {}
    out, skipped = [], 0
    for d in dumpsites:
        if not isinstance(d, dict):
            skipped += 1
            continue
        if d.get("status", "active") != "active":
            continue
        lat, lon = d.get("lat"), d.get("lon")
        if not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in (lat, lon)) \
                or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            skipped += 1
            continue
        kg = _num(d.get("estimated_kg"), -1.0)
        if kg < 0:
            kg = _num(by_size.get(d.get("size")), 0.0)
        out.append((float(lat), float(lon), kg))
    if skipped:
        warnings.append(f"{skipped} dépotoir(s) ignoré(s) : coordonnées ou format invalides.")
    return out


def _cells(xy: np.ndarray, w: np.ndarray, size: float) -> tuple[np.ndarray, np.ndarray]:
    """Agrège les points par cellule carrée de size mètres : centres pondérés et poids cumulés."""
    keys = np.floor(xy / size).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    weight = np.bincount(inverse, weights=w)
    count = np.bincount(inverse).astype(float)
    safe = np.where(weight > 0, weight, 1.0)
    cx = np.where(weight > 0, np.bincount(inverse, weights=xy[:, 0] * w) / safe, np.bincount(inverse, weights=xy[:, 0]) / count)
    cy = np.where(weight > 0, np.bincount(inverse, weights=xy[:, 1] * w) / safe, np.bincount(inverse, weights=xy[:, 1]) / count)
    return np.column_stack([cx, cy]), weight


def _fit_ok(centers: np.ndarray, xy: np.ndarray, w: np.ndarray, radius: float, target: float, capacity: float) -> bool:
    """Vrai si la couverture visée est atteinte et si aucun point ne reçoit plus que capacity (0 = sans limite)."""
    dist, owner = cKDTree(centers).query(xy)
    total = float(w.sum())
    if total > 0 and float(w[dist <= radius].sum()) / total < target:
        return False
    return capacity <= 0 or float(np.bincount(owner, weights=w, minlength=len(centers)).max()) <= capacity


def _search_k(xy: np.ndarray, w: np.ndarray, k_min: int, k_max: int, radius: float, target: float, capacity: float,
              warnings: list[str]) -> np.ndarray:
    """Plus petit k de [k_min, k_max] qui atteint couverture et capacité (dichotomie) ; k_max sinon."""
    fits: dict[int, np.ndarray] = {}

    def fit(k: int) -> np.ndarray:
        """Centres du KMeans pondéré à k groupes (mémorisés)."""
        if k not in fits:
            fits[k] = KMeans(n_clusters=k, n_init=1, random_state=SEED).fit(xy, sample_weight=w).cluster_centers_
        return fits[k]

    if not _fit_ok(fit(k_max), xy, w, radius, target, capacity):
        warnings.append(f"Même avec {k_max} points de regroupement (solver.max_collection_points), moins de {target:.0%} "
                        f"de la demande est à moins de {radius:g} m, ou un point dépasse la capacité d'un camion : maximum gardé.")
        return fit(k_max)
    lo, hi = k_min, k_max
    while lo < hi:
        mid = (lo + hi) // 2
        if _fit_ok(fit(mid), xy, w, radius, target, capacity):
            hi = mid
        else:
            lo = mid + 1
    return fit(lo)


def _snap(net: Network, lat: float, lon: float, radius: float) -> tuple[int | None, str]:
    """Nœud camion à distance de marche, sinon nœud tricycle (access « tricycle ») ; None si le réseau est vide."""
    truck = nearest_node(net.views["truck_dry"], lat, lon)
    if truck is not None and truck[1] <= radius:
        return truck[0], "truck"
    tricycle = nearest_node(net.views["tricycle_dry"], lat, lon)
    if tricycle is not None:
        return tricycle[0], "tricycle"
    return (truck[0], "tricycle") if truck is not None else (None, "tricycle")


def place_points(net: Network, demand: dict[str, Any], dumpsites: Any, cfg: dict[str, Any],
                 params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Points de regroupement du contrat (section 5), leurs nœuds, la part de demande dans le rayon de pré-collecte."""
    model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    solver = cfg.get("solver") if isinstance(cfg.get("solver"), dict) else {}
    params = params if isinstance(params, dict) else (cfg.get("params") if isinstance(cfg.get("params"), dict) else {})
    radius = _num(model.get("precollect_radius_m"), 0.0)
    target = min(_num(model.get("walk_coverage_target"), 1.0), 1.0)
    cell = _num(model.get("cell_size_m"), 0.0) or 100.0
    capacity = _num(params.get("truck_capacity_kg"), 0.0)
    k_max = max(int(_num(solver.get("max_collection_points"), 1)), 1)
    k_min = min(max(int(_num(solver.get("min_collection_points"), 1)), 1), k_max)
    warnings: list[str] = []
    assumptions = [
        "Point de regroupement : centre où les pré-collecteurs déposent les déchets des ménages abonnés ; les camions le vident.",
        f"Bâtiments agrégés par cellule de {cell:g} m (model.cell_size_m, centre pondéré) ; KMeans pondéré sur les cellules "
        f"(graine {SEED}), plus petit nombre de points entre {k_min} et {k_max} mettant {target:.0%} de la demande à moins de "
        f"{radius:g} m à vol d'oiseau (model.precollect_radius_m) et dont aucun ne dépasse la capacité d'un camion "
        f"({capacity:g} kg), pour être vidé en un seul arrêt (recherche par dichotomie).",
        f"Chaque point est recalé sur le nœud camion le plus proche s'il est à moins de {radius:g} m, "
        "sinon sur le nœud tricycle le plus proche (accès « tricycle ») ; réseau de saison sèche.",
    ]
    lat = np.asarray(demand.get("lat", []), dtype=float)
    lon = np.asarray(demand.get("lon", []), dtype=float)
    kg = np.asarray(demand.get("kg", []), dtype=float)
    tid = list(demand.get("territory_id") or [None] * len(lat))
    if not (len(lat) == len(lon) == len(kg) == len(tid)):
        warnings.append("Demande des bâtiments incohérente (tableaux de longueurs différentes) : ignorée.")
        lat = lon = kg = np.zeros(0)
        tid = []
    dumps = _dumpsite_points(dumpsites, model, warnings)
    if dumps:
        lat = np.concatenate([lat, [d[0] for d in dumps]])
        lon = np.concatenate([lon, [d[1] for d in dumps]])
        kg = np.concatenate([kg, [d[2] for d in dumps]])
        tid += [None] * len(dumps)
    ok = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(kg) & (kg >= 0)
    lat, lon, kg = lat[ok], lon[ok], kg[ok]
    tid = [t for t, keep in zip(tid, ok) if keep]
    result: dict[str, Any] = {"points": [], "node_ids": [], "walk_share": 0.0, "k": 0, "cells": 0, "data_tag": "estimated",
                              "assumptions": assumptions, "warnings": warnings}
    if len(lat) == 0 or kg.sum() <= 0:
        warnings.append("Aucune demande à collecter : aucun point de regroupement placé.")
        return result
    origin = (float(net.lat.mean()), float(net.lon.mean())) if len(net.lat) else (float(lat.mean()), float(lon.mean()))
    xy = project(lat, lon, origin)
    cxy, cw = _cells(xy, kg, cell)
    result["cells"] = len(cxy)
    centers = _search_k(cxy, cw, min(k_min, len(cxy)), min(k_max, len(cxy)), radius, target, capacity, warnings)
    c_lat = origin[0] + np.degrees(centers[:, 1] / EARTH_RADIUS_M)
    c_lon = origin[1] + np.degrees(centers[:, 0] / (EARTH_RADIUS_M * math.cos(math.radians(origin[0]))))

    merged: dict[Any, dict[str, Any]] = {}
    for i, (la, lo) in enumerate(zip(c_lat, c_lon)):
        node, access = _snap(net, float(la), float(lo), radius)
        key = node if node is not None else ("center", i)
        if node is not None:
            idx = net.index_of[node]
            la, lo = float(net.lat[idx]), float(net.lon[idx])
        entry = merged.setdefault(key, {"node": node, "lat": float(la), "lon": float(lo), "access": access})
        if access == "truck":
            entry["access"] = "truck"
    if any(e["node"] is None for e in merged.values()):
        warnings.append("Réseau routier indisponible : points laissés au centre de leur groupe, sans nœud routier.")
    entries = sorted(merged.values(), key=lambda e: (e["lat"], e["lon"]))
    p_xy = project(np.array([e["lat"] for e in entries]), np.array([e["lon"] for e in entries]), origin)
    dist, owner = cKDTree(p_xy).query(xy)
    loads = np.bincount(owner, weights=kg, minlength=len(entries))
    names = sorted({t for t in tid if t is not None})
    code = np.array([names.index(t) if t is not None else -1 for t in tid], dtype=np.int64) if names else np.full(len(tid), -1)
    territory: list[str | None] = [None] * len(entries)
    if names and (code >= 0).any():
        counts = np.zeros((len(entries), len(names)))
        np.add.at(counts, (owner[code >= 0], code[code >= 0]), kg[code >= 0])
        territory = [names[int(r.argmax())] if r.max() > 0 else None for r in counts]
    result["walk_share"] = float(kg[dist <= radius].sum() / kg.sum())
    result["k"] = len(centers)
    final_points = []
    final_node_ids = []
    for i, e in enumerate(entries):
        load_i = float(loads[i])
        if capacity > 0 and load_i > capacity:
            n_splits = int(math.ceil(load_i / capacity))
            split_load = round(load_i / n_splits, 1)
            for s_idx in range(n_splits):
                suffix = f"_{s_idx + 1}" if s_idx > 0 else ""
                pid = f"c_{e['node']}{suffix}" if e["node"] is not None else f"c_x{i + 1}{suffix}"
                final_points.append({"id": pid, "lat": round(e["lat"], 7), "lon": round(e["lon"], 7),
                                     "demand_kg": split_load, "access": e["access"], "territory_id": territory[i],
                                     "type": "center", "data_tag": "estimated"})
                final_node_ids.append(e["node"])
        else:
            final_points.append({"id": f"c_{e['node']}" if e["node"] is not None else f"c_x{i + 1}",
                                 "lat": round(e["lat"], 7), "lon": round(e["lon"], 7),
                                 "demand_kg": round(load_i, 1), "access": e["access"], "territory_id": territory[i],
                                 "type": "center", "data_tag": "estimated"})
            final_node_ids.append(e["node"])
    result["node_ids"] = final_node_ids
    result["points"] = final_points
    assumptions.append(f"Demande de chaque point = demande des bâtiments et dépotoirs dont il est le plus proche ; "
                       f"{result['walk_share']:.1%} de la demande est à moins de {radius:g} m d'un point.")
    return result
