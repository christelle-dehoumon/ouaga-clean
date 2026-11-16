"""Dépotoirs validés -> arrêts de ramassage ponctuels ; tout signalement écarté est listé avec sa raison."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from core.geo.graph import Network, nearest_node, project
from core.geo.territories import commune_polygon

SIZES = ("small", "medium", "large")


def _num(value: Any) -> float | None:
    """Nombre fini, sinon None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _collect(reports: Any, by_size: dict[str, Any], commune: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Dépotoirs actifs (validés, ou signalements acceptés regroupés par dumpsite_id) dans la commune, et les écartés."""
    ignored: list[dict[str, str]] = []
    if not isinstance(reports, list):
        if reports is not None:
            ignored.append({"report_id": "-", "reason": "Les signalements doivent être une liste : tout est ignoré."})
        return [], ignored
    sites: dict[str, dict[str, Any]] = {}
    for n, r in enumerate(reports, start=1):
        rid = str(r.get("id")) if isinstance(r, dict) and r.get("id") not in (None, "") else f"#{n}"
        if not isinstance(r, dict):
            ignored.append({"report_id": rid, "reason": "Entrée illisible : ce n'est pas un objet JSON."})
            continue
        status = r.get("status")
        if status == "cleaned":
            ignored.append({"report_id": rid, "reason": "Dépotoir déjà nettoyé."})
            continue
        if status not in ("active", "accepted"):
            ignored.append({"report_id": rid, "reason": f"Statut « {status} » : signalement non validé."})
            continue
        lat, lon = _num(r.get("lat")), _num(r.get("lon"))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            ignored.append({"report_id": rid, "reason": "Coordonnées absentes ou invalides."})
            continue
        if commune is not None and not commune.covers(_point(lon, lat)):
            ignored.append({"report_id": rid, "reason": "Hors de la commune."})
            continue
        kg = _num(r.get("estimated_kg")) if status == "active" else None
        size = r.get("size") if r.get("size") in SIZES else None
        if kg is None or kg < 0:
            kg = _num(by_size.get(size)) if size else None
        if kg is None or kg < 0:
            ignored.append({"report_id": rid, "reason": "Ni « estimated_kg » ni taille connue (small, medium, large)."})
            continue
        key = rid if status == "active" else str(r.get("dumpsite_id") or rid)
        site = sites.get(key)
        if site is None:
            sites[key] = {"id": key, "lat": lat, "lon": lon, "kg": kg, "validated": status == "active", "members": [rid],
                          "synthetic": False}
            site = sites[key]
        elif status == "active" and not site["validated"]:
            sites[key].update({"lat": lat, "lon": lon, "kg": kg, "validated": True})
            site["members"].append(rid)
        else:
            if not site["validated"]:
                site["kg"] = max(site["kg"], kg)
            site["members"].append(rid)
        site["synthetic"] |= r.get("source") == "synthetic"
    return sorted(sites.values(), key=lambda s: s["id"]), ignored


def _point(lon: float, lat: float) -> Any:
    """Point shapely."""
    from shapely.geometry import Point

    return Point(lon, lat)


def _group(sites: list[dict[str, Any]], max_stops: int, cell: float) -> list[dict[str, Any]]:
    """Regroupe les dépotoirs par cellule (taille doublée) tant qu'il y en a plus que max_stops."""
    if len(sites) <= max_stops or max_stops <= 0:
        return sites
    lat = np.array([s["lat"] for s in sites])
    lon = np.array([s["lon"] for s in sites])
    kg = np.array([s["kg"] for s in sites])
    xy = project(lat, lon, (float(lat.mean()), float(lon.mean())))
    size = max(cell, 1.0)
    while True:
        _, inverse = np.unique(np.floor(xy / size).astype(np.int64), axis=0, return_inverse=True)
        inverse = inverse.ravel()
        if inverse.max() + 1 <= max_stops:
            break
        size *= 2
    groups = []
    for g in range(int(inverse.max()) + 1):
        idx = np.flatnonzero(inverse == g)
        members = [m for i in idx for m in sites[i]["members"]]
        w = kg[idx] if kg[idx].sum() > 0 else np.ones(len(idx))
        groups.append({"id": sites[idx[0]]["id"] + (f"_{len(idx)}" if len(idx) > 1 else ""),
                       "lat": float((lat[idx] * w).sum() / w.sum()), "lon": float((lon[idx] * w).sum() / w.sum()),
                       "kg": float(kg[idx].sum()), "members": members,
                       "synthetic": any(sites[i]["synthetic"] for i in idx)})
    return groups


def dumpsite_stops(reports: Any, cfg: dict[str, Any], net: Network
                   ) -> tuple[list[dict[str, Any]], list[int], list[dict[str, str]], list[str]]:
    """Arrêts ponctuels (format point du contrat, type « dumpsite »), leurs nœuds camion, les écartés, les hypothèses."""
    model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    solver = cfg.get("solver") if isinstance(cfg.get("solver"), dict) else {}
    by_size = model.get("dumpsite_kg_by_size") if isinstance(model.get("dumpsite_kg_by_size"), dict) else {}
    resnap = _num(model.get("resnap_max_m")) or 0.0
    max_stops = int(_num(solver.get("max_dumpsite_stops")) or 0)
    commune, how = commune_polygon(cfg)
    sites, ignored = _collect(reports, by_size, commune)
    assumptions = [f"Dépotoirs validés dans la commune ({how or 'aucune limite connue'}) : un arrêt ponctuel chacun, recalé sur "
                   f"le nœud camion le plus proche à moins de {resnap:g} m (model.resnap_max_m), demande = estimated_kg "
                   "ou forfait par taille ; regroupés par cellule au-delà de solver.max_dumpsite_stops."]
    groups = _group(sites, max_stops, _num(model.get("cell_size_m")) or 100.0)
    if len(groups) < len(sites):
        assumptions.append(f"{len(sites)} dépotoirs regroupés en {len(groups)} arrêts (solver.max_dumpsite_stops = {max_stops}).")
    points, nodes = [], []
    view = net.views["truck_dry"]
    for g in groups:
        near = nearest_node(view, g["lat"], g["lon"])
        if near is None or near[1] > resnap:
            ignored += [{"report_id": m, "reason": f"Aucune route camion à moins de {resnap:g} m : non recalable."}
                        for m in g["members"]]
            continue
        i = net.index_of[near[0]]
        points.append({"id": f"d_{g['id']}", "lat": round(float(net.lat[i]), 7), "lon": round(float(net.lon[i]), 7),
                       "demand_kg": round(g["kg"], 1), "access": "truck", "territory_id": None, "type": "dumpsite",
                       "data_tag": "synthetic" if g.get("synthetic") else "estimated"})
        nodes.append(near[0])
    return points, nodes, ignored, assumptions
