"""Événements de l'épreuve en direct appliqués à un calcul de plan : panne, pluie, nouveau quartier, routes coupées.

- truck_down {vehicle_id} : le camion passe en panne ; avec le plan précédent, recalcul PARTIEL (seuls ses arrêts sont
  redistribués) ; ses arrêts qui ne trouvent pas de place sont « reportés » (postponed), séparés de unserved.
- rain : vue réseau pluie (voies non revêtues plus lentes, voies près des cours d'eau coupées).
- new_district {territory_id} : quartier de data/territories.geojson ajouté (bâtiments, demande, points).
- cut_roads [{edge_id} | {lat, lon}] : arêtes retirées d'une COPIE du réseau pour ce calcul seulement.
"""

from __future__ import annotations

import json
import re
from typing import Any

from core.config import get_config, resolve, section
from core.geo.graph import Network, cut_network, nearest_node, resolve_cuts
from core.optim.plan import compute_plan, default_network, global_checks


class EventError(ValueError):
    """Événement refusé (type inconnu, quartier inconnu, camion inexistant) : message en français pour l'API (422)."""


def list_territories(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Quartiers ajoutables : [{id, nom, approximate}] lus dans paths.territories (aucun identifiant dans le code)."""
    cfg = cfg or get_config()
    path_str = section(cfg, "paths").get("territories")
    if not isinstance(path_str, str) or not resolve(path_str).exists():
        return []
    try:
        data = json.loads(resolve(path_str).read_text(encoding="utf-8"))
    except Exception:  # fichier illisible : aucun quartier proposé
        return []
    out = []
    for f in data.get("features", []):
        props = f.get("properties") or {}
        if isinstance(props.get("id"), str):
            out.append({"id": props["id"], "nom": props.get("nom") or props.get("name") or props["id"],
                        "approximate": bool(props.get("approximate"))})
    return out


def _truck_id(value: Any, trucks: int) -> str:
    """« truck3 », « truck3_trip2 » ou 3 -> « truck3 » ; EventError si le camion n'existe pas."""
    text = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    match = re.fullmatch(r"(?:truck)?(\d+)(?:_trip\d+)?", text.strip())
    if not match or not 1 <= int(match.group(1)) <= trucks:
        raise EventError(f"Camion « {value} » inconnu : la flotte compte {trucks} camion(s), truck1 à truck{trucks}.")
    return f"truck{int(match.group(1))}"


def apply_events(params: dict[str, Any], events: Any, cfg: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Paramètres modifiés par les événements et liste des véhicules mis en panne par ces événements."""
    out = dict(params)
    if events is None:
        return out, []
    if not isinstance(events, list):
        raise EventError("events doit être une liste d'objets {type: ...}.")
    trucks = int(out.get("trucks", section(cfg, "params").get("trucks", 0)) or 0)
    known = {t["id"] for t in list_territories(cfg)}
    down: list[str] = []
    for ev in events:
        kind = ev.get("type") if isinstance(ev, dict) else None
        if kind == "truck_down":
            truck = _truck_id(ev.get("vehicle_id"), trucks)
            out["broken_trucks"] = sorted(set(out.get("broken_trucks") or []) | {truck})
            down.append(truck)
        elif kind == "rain":
            out["rainy_season"] = True
        elif kind == "new_district":
            tid = ev.get("territory_id")
            if tid not in known:
                raise EventError(f"Quartier « {tid} » inconnu : voir GET /api/territories ({sorted(known)}).")
            out["extra_territories"] = list(dict.fromkeys([*(out.get("extra_territories") or []), tid]))
        else:
            raise EventError(f"Événement « {kind} » inconnu : truck_down, rain ou new_district.")
    return out, down


def _postponed(plan: dict[str, Any], previous: dict[str, Any] | None, down: list[str], cfg: dict[str, Any]) -> None:
    """Arrêts des camions en panne restés sans tournée : sortis de unserved et listés dans postponed."""
    lost = {s for r in (previous or {}).get("routes", []) if isinstance(r, dict)
            and str(r.get("vehicle", "")).split("_trip")[0] in down for s in r.get("stops", [])}
    plan["postponed"] = [{"id": u["point_id"], "reason": "Camion en panne : arrêt reporté au prochain passage.",
                          "detail": u.get("detail", "")} for u in plan["unserved"] if u["point_id"] in lost]
    plan["unserved"] = [u for u in plan["unserved"] if u["point_id"] not in lost]
    global_checks(plan, cfg, bool(plan["checks"].get("network_available", True)))


def _inaccessible(plan: dict[str, Any], base: Network, cut: Network) -> list[dict[str, Any]]:
    """Points dont le nœud routier le plus proche était praticable et ne l'est plus après les coupures."""
    out = []
    for view_name in ("truck_rain" if plan["params_used"].get("rainy_season") else "truck_dry",):
        bv, cv = base.views[view_name], cut.views[view_name]
        for p in plan["collection_points"]:
            near = nearest_node(bv, p.get("lat"), p.get("lon"))
            if near and not cv.node_mask[base.index_of[near[0]]]:
                out.append({"id": p["id"], "reason": "Route coupée : point isolé du réseau camion."})
    return out


def plan_with_events(params: dict[str, Any] | None, reports: list[dict[str, Any]], events: Any = None,
                     cut_roads: Any = None, previous_plan: dict[str, Any] | None = None,
                     cfg: dict[str, Any] | None = None, net: Network | None = None) -> dict[str, Any]:
    """Plan recalculé après les événements ; EventError si un événement est refusé."""
    cfg = cfg or get_config()
    base_net = net or default_network()
    params = dict(params or {})
    if previous_plan and not params:
        params = dict(previous_plan.get("params_used") or {})
    params, down = apply_events(params, events, cfg)
    snap = float(section(cfg, "network").get("cut_snap_m") or 0)
    mask, cuts, cut_warnings = resolve_cuts(base_net, cut_roads or [], snap)
    work_net = cut_network(base_net, mask)
    plan = compute_plan(params, reports, previous_plan=previous_plan, cfg=cfg, net=work_net)
    plan["events"] = events or []
    plan["cut_roads"] = cuts
    plan["warnings"] = plan["warnings"] + cut_warnings
    plan["inaccessible_due_to_cuts"] = _inaccessible(plan, base_net, work_net) if cuts else []
    _postponed(plan, previous_plan, down, cfg)
    return plan
