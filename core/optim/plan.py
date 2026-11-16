"""compute_plan : demande, points, matrice, tournées, recalcul partiel, contrôles et replis ; ne lève jamais (sections 8 à 11)."""

from __future__ import annotations

import copy
import math
import re
import time
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.config import _check_value, load_config
from core.geo.buildings import building_demand
from core.geo.download import REPO_ROOT
from core.geo.graph import Network, load_network, nearest_node
from core.optim.coherence import all_ok, check_plan
from core.optim.matrix import MatrixCache, path_length_m, straight_matrix
from core.optim.placement import place_points
from core.optim.dumpsites import dumpsite_stops
from core.optim.tournees import (Fleet, improve, insert_cheapest, route_minutes, solve_greedy, solve_ortools,
                                 trim_to_budget)

CONFIG_PATH = REPO_ROOT / "config" / "commune_config.json"
# État gardé en mémoire entre deux appels : configuration et réseau (chargé une seule fois).
_STATE: dict[str, Any] = {"cfg": None, "net": None}


def _context(cfg: dict[str, Any] | None, net: Network | None) -> tuple[dict[str, Any], Network]:
    """Configuration et réseau : ceux fournis, sinon ceux chargés une fois depuis le dépôt."""
    if cfg is None:
        if _STATE["cfg"] is None:
            _STATE["cfg"] = load_config(CONFIG_PATH)
        cfg = _STATE["cfg"]
    if net is None:
        if _STATE["net"] is None:
            _STATE["net"] = load_network(cfg)
        net = _STATE["net"]
    return cfg, net


def _num(value: Any, default: float) -> float:
    """Nombre fini positif ou nul, sinon default."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return default
    return float(value)


def sanitize_params(params: Any, defaults: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """Paramètres du jury validés un par un ; valeur de la configuration (avec avertissement) si absurde."""
    if not isinstance(params, dict):
        if params is not None:
            warnings.append("Les paramètres doivent être un objet : valeurs de la configuration utilisées.")
        params = {}
    out = {k: (_check_value(f"params.{k}", params[k], v, warnings) if k in params else copy.deepcopy(v))
           for k, v in defaults.items()}
    out["trucks"] = int(out["trucks"])
    out["broken_trucks"] = [t for t in out["broken_trucks"] if isinstance(t, str)]
    return out


def _empty_plan(params: dict[str, Any], points: list[dict[str, Any]], reason: str, detail: str) -> dict[str, Any]:
    """Plan valide sans tournée, tous les points dans « unserved »."""
    now = datetime.now(timezone.utc)
    return {"plan_id": f"p_{now.strftime('%Y%m%dT%H%M%SZ')}", "computed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "mode": "fallback", "compute_ms": 0, "params_used": params, "collection_points": points, "routes": [],
            "unserved": [{"point_id": p["id"], "reason": reason, "detail": detail} for p in points],
            "ignored_reports": [],
            "checks": {"capacity_ok": True, "budget_ok": True, "vehicles_ok": True, "network_ok": True,
                       "every_point_served_or_reported": True, "messages": []},
            "totals": {"distance_km": 0, "cost": 0, "collected_kg": 0, "budget_remaining": _num(params.get("budget"), 0),
                       "points_served": 0, "points_unserved": len(points), "uncollected_kg": 0},
            "assumptions": [], "warnings": []}


@dataclass
class Ctx:
    """Tout ce qu'un calcul partage : configuration, réseau, paramètres validés, flotte, vue, dépôt."""

    cfg: dict[str, Any]
    net: Network
    cache: MatrixCache
    params: dict[str, Any]
    view: str
    fleet: Fleet
    broken: set[str]
    depot: int | None
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def num(self, block: str, key: str, default: float) -> float:
        """Valeur numérique de la configuration."""
        section = self.cfg.get(block) if isinstance(self.cfg.get(block), dict) else {}
        return _num(section.get(key), default)


def _setup(params_in: Any, cfg: dict[str, Any], net: Network, cache: MatrixCache) -> Ctx:
    """Paramètres validés, vue sèche ou pluie, véhicules virtuels (une tournée par rotation), dépôt."""
    warnings: list[str] = []
    model = cfg["model"]
    params = sanitize_params(params_in, cfg["params"], warnings)
    view = "truck_rain" if params["rainy_season"] else "truck_dry"
    trips = max(int(_num(model.get("truck_trips_per_day"), 1)), 1)
    broken = set(params["broken_trucks"])
    vehicles = [f"truck{i}_trip{t}" for i in range(1, max(params["trucks"], 0) + 1) if f"truck{i}" not in broken
                for t in range(1, trips + 1)]
    fleet = Fleet(vehicles, _num(params["truck_capacity_kg"], 0.0), _num(model.get("shift_minutes"), 0.0) / trips,
                  _num(model.get("truck_speed_kmh"), 0.0), _num(model.get("service_min_per_stop"), 0.0))
    assumptions = list(net.assumptions) + [
        f"Rotations : {trips} tournées par camion et par jour (model.truck_trips_per_day), chacune part du dépôt et y revient, "
        f"{fleet.max_minutes:g} min au plus ; véhicules virtuels truckN_tripM. Vue du réseau : « {view} »."]
    v = net.views[view]
    depot_cfg = cfg.get("depot") or {}
    if isinstance(depot_cfg.get("lat"), (int, float)) and isinstance(depot_cfg.get("lon"), (int, float)):
        near = nearest_node(v, depot_cfg["lat"], depot_cfg["lon"])
    else:
        idx = v.tree_idx
        near = nearest_node(v, float(net.lat[idx].mean()), float(net.lon[idx].mean())) if len(idx) else None
        assumptions.append("Dépôt non configuré : nœud camion le plus proche du centre du réseau routier.")
    return Ctx(cfg, net, cache, params, view, fleet, broken, near[0] if near else None, warnings + list(net.warnings),
               assumptions)


def _base(ctx: Ctx, points: list[dict[str, Any]], uncollected: float, ignored: list[dict[str, str]]) -> dict[str, Any]:
    """Plan sans tournée, avec les points, la masse non collectée, les signalements écartés, hypothèses et avertissements."""
    plan = _empty_plan(ctx.params, points, "no_route", "")
    plan["unserved"] = []
    plan["totals"]["uncollected_kg"] = round(uncollected, 1)
    plan["ignored_reports"] = ignored
    plan["assumptions"], plan["warnings"] = ctx.assumptions, ctx.warnings
    return plan


def _classify(ctx: Ctx, points: list[dict[str, Any]], nodes: list[int | None], plan: dict[str, Any]
              ) -> tuple[list[dict[str, Any]], list[int]]:
    """Arrêts que les camions peuvent servir (nœud recalé en pluie) ; les autres vont dans plan.unserved."""
    net, v = ctx.net, ctx.net.views[ctx.view]
    resnap = ctx.num("model", "resnap_max_m", 0.0)
    cand, cand_nodes, moved = [], [], 0
    for p, node in zip(points, nodes):
        def out(reason: str, detail: str) -> None:
            """Range le point dans unserved."""
            plan["unserved"].append({"point_id": p["id"], "reason": reason, "detail": detail})
        if node is None or ctx.depot is None:
            out("no_route", "Aucun réseau routier disponible.")
            continue
        if p.get("access") != "truck":
            out("access", "Accessible seulement en tricycle (tournées tricycle pas encore faites).")
            continue
        if not v.node_mask[net.index_of[node]]:
            near = nearest_node(v, p["lat"], p["lon"])
            if near is None or near[1] > resnap:
                out("access", f"Nœud coupé (pluie) et aucun nœud camion praticable à moins de {resnap:g} m.")
                continue
            node, moved = near[0], moved + 1
        if p["demand_kg"] > ctx.fleet.capacity_kg:
            out("capacity", "Demande du point supérieure à la capacité d'un camion.")
        elif not ctx.fleet.vehicles:
            out("capacity", "Aucun camion disponible.")
        else:
            cand.append(p)
            cand_nodes.append(node)
    if moved:
        ctx.assumptions.append(f"{moved} arrêt(s) recalé(s) sur le nœud camion praticable le plus proche (moins de {resnap:g} m).")
    return cand, cand_nodes


def _matrix(ctx: Ctx, cand_nodes: list[int]) -> tuple[np.ndarray, list[int | None], bool]:
    """Matrice dépôt + arrêts depuis le cache de la vue ; vol d'oiseau si elle est indisponible."""
    net = ctx.net
    factor = ctx.num("network", "straight_line_factor", 1.4) or 1.4
    all_nodes: list[int | None] = [ctx.depot, *cand_nodes]
    coords = [(float(net.lat[net.index_of[n]]), float(net.lon[net.index_of[n]])) if n is not None else (0.0, 0.0)
              for n in all_nodes]
    try:
        dist, warn = ctx.cache.matrix(net, ctx.view, all_nodes, coords, factor)
        ctx.warnings.extend(warn)
        return dist, all_nodes, True
    except Exception as exc:  # matrice indisponible : secours à vol d'oiseau
        ctx.warnings.append(f"Matrice de distances indisponible ({exc}) : vol d'oiseau × {factor:g}.")
        return straight_matrix(coords, factor), all_nodes, False


def _build(ctx: Ctx, base: dict[str, Any], routes: list[list[int]], cand: list[dict[str, Any]], nodes: list[int | None],
           dist: np.ndarray, use_network: bool, reasons: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Plan du contrat à partir des tournées (indices 1..m dans cand), coûts réels, retrait au budget, contrôles."""
    net, cache, view, fleet = ctx.net, ctx.cache, ctx.view, ctx.fleet
    cost_km, budget = ctx.num("model", "cost_per_km_truck", 0.0), _num(ctx.params["budget"], 0.0)
    matrix = net.views[view].matrix
    legs: dict[tuple[int, int], tuple[float, list[int] | None]] = {}

    def leg(a: int, b: int) -> tuple[float, list[int] | None]:
        """Longueur réelle (m) et suite de nœuds d'un tronçon entre deux indices de la matrice."""
        if (a, b) not in legs:
            seq = cache.path(net, view, nodes[a], nodes[b]) if use_network else None
            legs[(a, b)] = (float(dist[a, b]), None) if seq is None else (path_length_m(net, view, seq), seq)
        return legs[(a, b)]

    def metres(stops: list[int]) -> float:
        """Longueur réelle d'une tournée dépôt -> arrêts -> dépôt."""
        seq = [0, *stops, 0]
        return sum(leg(a, b)[0] for a, b in zip(seq[:-1], seq[1:])) if stops else 0.0

    demand = [p["demand_kg"] for p in cand]
    routes, cut = trim_to_budget(routes, dist, demand, lambda rs: sum(metres(r) for r in rs) / 1000 * cost_km, budget)
    plan = copy.deepcopy(base)
    served = {i for r in routes for i in r}
    over = sum(demand) > fleet.capacity_kg * len(fleet.vehicles)
    room = max([fleet.capacity_kg - sum(demand[i - 1] for i in r) for r in routes] or [0.0])
    for i in range(1, len(cand) + 1):
        pid = cand[i - 1]["id"]
        if i in cut:
            plan["unserved"].append({"point_id": pid, "reason": "budget",
                                     "detail": "Retiré pour respecter le budget (point le moins rentable en kg par km)."})
        elif i not in served:
            full_load = over or demand[i - 1] > room
            plan["unserved"].append((reasons or {}).get(pid) or {
                "point_id": pid, "reason": "capacity" if full_load else "time",
                "detail": "Aucune tournée n'a assez de place pour ce point." if full_load
                else "Ne tient dans la durée d'aucune tournée."})
    off_view = 0
    for vehicle, stops in zip(fleet.vehicles, routes):
        if not stops:
            continue
        seq = [0, *stops, 0]
        path: list[int] = []
        geometry_ok = True
        for a, b in zip(seq[:-1], seq[1:]):
            part = leg(a, b)[1]
            geometry_ok &= part is not None
            path += (part or [])[1 if path else 0:]
        if geometry_ok and len(path) > 1:
            off_view += int((np.asarray(matrix[path[:-1], path[1:]]).ravel() <= 0).sum())
        km = metres(stops) / 1000
        plan["routes"].append({"vehicle": vehicle, "type": "truck", "stops": [cand[i - 1]["id"] for i in stops],
                               "distance_km": round(km, 3), "duration_min": round(route_minutes(stops, dist, fleet), 1),
                               "load_kg": round(sum(demand[i - 1] for i in stops), 1), "capacity_kg": fleet.capacity_kg,
                               "cost": round(km * cost_km), "geometry": {"type": "LineString", "coordinates": [
                                   [round(float(net.lon[i]), 6), round(float(net.lat[i]), 6)] for i in path]}
                               if geometry_ok and len(path) > 1 else None})
    t = plan["totals"]
    t["distance_km"] = round(sum(r["distance_km"] for r in plan["routes"]), 3)
    t["cost"] = sum(r["cost"] for r in plan["routes"])
    t["collected_kg"] = round(sum(r["load_kg"] for r in plan["routes"]), 1)
    t["budget_remaining"] = round(budget - t["cost"])
    t["points_served"] = sum(len(r["stops"]) for r in plan["routes"])
    t["points_unserved"] = len(plan["unserved"])
    plan["checks"] = check_plan(plan, set(fleet.vehicles), ctx.broken, budget, fleet.max_minutes)
    plan["checks"]["network_ok"] = off_view == 0
    if off_view:
        plan["checks"]["messages"].append(f"{off_view} tronçon(s) de tournée hors de la vue « {view} » (arête coupée).")
    return plan


def _solve(ctx: Ctx, base: dict[str, Any], cand: list[dict[str, Any]], cand_nodes: list[int]) -> dict[str, Any]:
    """Solveur complet, puis glouton si le solveur échoue ou si un contrôle est faux, puis plan vide."""
    dist, all_nodes, use_network = _matrix(ctx, cand_nodes)
    demand = [p["demand_kg"] for p in cand]
    limit = ctx.num("solver", "time_limit_s", 5.0) or 5.0
    routes, timed_out = solve_ortools(dist, demand, ctx.fleet, limit) if cand else ([[] for _ in ctx.fleet.vehicles], False)
    if timed_out:
        ctx.warnings.append(f"Limite de sécurité du solveur atteinte ({limit:g} s, solver.time_limit_s) : "
                            "meilleure solution trouvée à ce moment, résultat possiblement non reproductible.")
    if routes is not None:
        result = _build(ctx, base, routes, cand, all_nodes, dist, use_network)
        result["mode"] = "optimized" if use_network else "fallback"
        if all_ok(result["checks"]):
            return result
        ctx.warnings.append("Plan du solveur incohérent : secours glouton. " + " ".join(result["checks"]["messages"]))
    else:
        ctx.warnings.append("Le solveur OR-Tools n'a pas trouvé de solution : secours glouton.")
    result = _build(ctx, base, solve_greedy(dist, demand, ctx.fleet), cand, all_nodes, dist, use_network)
    result["mode"] = "fallback"
    if all_ok(result["checks"]):
        return result
    empty = copy.deepcopy(base)
    empty["unserved"] += [{"point_id": p["id"], "reason": "no_route", "detail": "Aucun plan cohérent trouvé."} for p in cand]
    empty["warnings"] = ctx.warnings + ["Aucun plan cohérent : plan vide."] + result["checks"]["messages"]
    empty["totals"]["points_unserved"] = len(empty["unserved"])
    return empty


def _full(ctx: Ctx, reports: Any) -> dict[str, Any]:
    """Calcul complet : points de regroupement des territoires actifs + arrêts dépotoirs, puis tournées."""
    demand = building_demand(ctx.cfg, ctx.params)
    placed = place_points(ctx.net, demand, [], ctx.cfg, ctx.params)
    dumps, dump_nodes, ignored, d_assumptions = dumpsite_stops(reports, ctx.cfg, ctx.net)
    ctx.warnings += demand["warnings"] + placed["warnings"]
    ctx.assumptions += demand["assumptions"] + placed["assumptions"] + d_assumptions
    points = placed["points"] + dumps
    base = _base(ctx, points, demand["uncollected_kg"], ignored)
    cand, cand_nodes = _classify(ctx, points, placed["node_ids"] + dump_nodes, base)
    return _solve(ctx, base, cand, cand_nodes)


def _change_kind(prev: dict[str, Any], params: dict[str, Any], dump_ids: set[str], changed: Any) -> str:
    """Nature du changement depuis previous_plan : breakdown, reports, territory, none ou full."""
    old = prev.get("params_used") if isinstance(prev.get("params_used"), dict) else {}
    keys = {k for k in params if old.get(k) != params[k]}
    if isinstance(changed, dict):
        keys |= {k for k in changed if k in params and old.get(k) != params[k]}
    prev_dumps = {p.get("id") for p in prev.get("collection_points", []) if isinstance(p, dict) and p.get("type") == "dumpsite"}
    if prev_dumps - dump_ids:
        return "full"
    new_reports = bool(dump_ids - prev_dumps)
    if not keys:
        return "reports" if new_reports else "none"
    if new_reports or len(keys) > 1:
        return "full"
    key = keys.pop()
    as_list = lambda v: v if isinstance(v, list) else []  # noqa: E731
    if key == "broken_trucks" and set(as_list(old.get(key))) <= set(params[key]):
        return "breakdown"
    old_t = [t if isinstance(t, str) else (t.get("properties") or {}).get("id") for t in as_list(old.get(key))
             if isinstance(t, (str, dict))]
    new_t = [t if isinstance(t, str) else (t.get("properties") or {}).get("id") for t in as_list(params.get(key))
             if isinstance(t, (str, dict))]
    if key == "extra_territories" and set(old_t) < set(new_t):
        return "territory"
    return "full"


def _partial(ctx: Ctx, prev: dict[str, Any], reports: Any, kind: str) -> dict[str, Any]:
    """Recalcul partiel : garde les tournées, réinsère les arrêts perdus et nouveaux (moindre coût), améliore localement."""
    net = ctx.net
    old_points = [dict(p) for p in prev["collection_points"] if p.get("type") != "dumpsite"]
    old_ids = {p["id"] for p in prev["collection_points"]}
    nodes: list[int | None] = []
    for p in old_points:
        match = re.fullmatch(r"c_(-?\d+)", str(p.get("id")))
        if match is None or int(match.group(1)) not in net.index_of:
            raise ValueError(f"Point « {p.get('id')} » du plan précédent introuvable sur le réseau.")
        nodes.append(int(match.group(1)))
    demand = building_demand(ctx.cfg, ctx.params)
    ctx.warnings += demand["warnings"]
    ctx.assumptions += demand["assumptions"]
    if kind == "territory":
        known = {p.get("territory_id") for p in old_points}
        keep = np.array([t not in known for t in demand["territory_id"]], dtype=bool)
        sub = {"lat": demand["lat"][keep], "lon": demand["lon"][keep], "kg": demand["kg"][keep],
               "territory_id": [t for t, k in zip(demand["territory_id"], keep) if k]}
        placed = place_points(net, sub, [], ctx.cfg, ctx.params)
        ctx.warnings += placed["warnings"]
        existing = {p["id"]: p for p in old_points}
        for p, node in zip(placed["points"], placed["node_ids"]):
            if p["id"] in existing:          # même nœud qu'un point existant : la demande s'y ajoute
                existing[p["id"]]["demand_kg"] = round(existing[p["id"]]["demand_kg"] + p["demand_kg"], 1)
            else:
                old_points.append(p)
                nodes.append(node)
        ctx.assumptions.append(f"Nouveau quartier : {len(placed['points'])} point(s) placé(s) dans ce quartier seulement.")
    dumps, dump_nodes, ignored, d_assumptions = dumpsite_stops(reports, ctx.cfg, net)
    ctx.assumptions += d_assumptions
    points = old_points + dumps
    base = _base(ctx, points, demand["uncollected_kg"], ignored)
    cand, cand_nodes = _classify(ctx, points, nodes + dump_nodes, base)
    index = {p["id"]: i + 1 for i, p in enumerate(cand)}
    prev_routes = {r.get("vehicle"): r.get("stops", []) for r in prev.get("routes", []) if isinstance(r, dict)}
    routes = [[index[s] for s in prev_routes.get(v, []) if s in index] for v in ctx.fleet.vehicles]
    in_routes = {i for r in routes for i in r}
    lost = {index[s] for v, stops in prev_routes.items() if v not in ctx.fleet.vehicles for s in stops if s in index}
    new = {i for pid, i in index.items() if pid not in old_ids}
    to_insert = sorted((lost | new) - in_routes)
    reasons = {u["point_id"]: u for u in prev.get("unserved", []) if isinstance(u, dict) and u.get("point_id") in index}
    dist, all_nodes, use_network = _matrix(ctx, cand_nodes)
    demand_kg = [p["demand_kg"] for p in cand]
    routes, _left = insert_cheapest(routes, to_insert, dist, demand_kg, ctx.fleet)
    limit = ctx.num("solver", "time_limit_s", 5.0) or 5.0
    routes, timed_out = improve(routes, dist, demand_kg, ctx.fleet, time.perf_counter() + limit)
    if timed_out:
        ctx.warnings.append(f"Limite de sécurité atteinte pendant l'amélioration locale ({limit:g} s, solver.time_limit_s).")
    ctx.assumptions.append(f"Recalcul partiel ({kind}) : tournées gardées, {len(to_insert)} arrêt(s) réinséré(s) au moindre "
                           "coût, puis amélioration locale (2-opt, déplacement d'arrêt).")
    result = _build(ctx, base, routes, cand, all_nodes, dist, use_network, reasons)
    result["mode"] = "partial" if use_network else "fallback"
    return result


def _score(plan: dict[str, Any]) -> tuple[int, float]:
    """Ordre de préférence entre deux plans : moins de points non servis, puis coût le plus bas."""
    return len(plan["unserved"]), float(plan["totals"]["cost"])


def compute_plan(params: dict, reports: list[dict], previous_plan: dict | None = None, changed: dict | None = None,
                 *, cfg: dict[str, Any] | None = None, net: Network | None = None) -> dict:
    """Plan du contrat (section 5) ; ne lève jamais : en dernier recours, plan vide valide et erreur dans warnings."""
    t0 = time.perf_counter()
    try:
        cfg, net = _context(cfg, net)
        cache = net.__dict__.setdefault("matrix_cache", MatrixCache())      # un cache de distances par réseau
        plan, note = None, "Plan précédent illisible : calcul complet."
        if isinstance(previous_plan, dict) and isinstance(previous_plan.get("collection_points"), list):
            ctx = _setup(params, cfg, net, cache)
            dump_ids = {p["id"] for p in dumpsite_stops(reports, cfg, net)[0]}
            try:
                kind = _change_kind(previous_plan, ctx.params, dump_ids, changed)
            except Exception:  # plan précédent mal formé : calcul complet
                kind = "full"
            if kind != "full":
                try:
                    plan = _partial(ctx, previous_plan, reports, kind)
                    if not all_ok(plan["checks"]):
                        plan = None
                except Exception:  # plan précédent inattendu : calcul complet
                    plan = None
            note = "Recalcul partiel incohérent ou impossible : calcul complet." if kind != "full" \
                else "Changement non traité en partiel : calcul complet."
        if plan is not None and any(u.get("reason") in ("capacity", "time") for u in plan["unserved"]):
            full = _full(_setup(params, cfg, net, cache), reports)
            if all_ok(full["checks"]) and _score(full) < _score(plan):
                full["warnings"].append(f"Recalcul partiel : {len(plan['unserved'])} point(s) non servi(s), coût "
                                        f"{plan['totals']['cost']} ; calcul complet meilleur ({len(full['unserved'])} non "
                                        f"servi(s), coût {full['totals']['cost']}) : plan complet gardé.")
                plan = full
            else:
                plan["warnings"].append("Recalcul partiel avec des points non servis : calcul complet lancé aussi, "
                                        "pas meilleur (points non servis puis coût) : plan partiel gardé.")
        if plan is None:
            plan = _full(_setup(params, cfg, net, cache), reports)
            if previous_plan is not None:
                plan["assumptions"].append(note)
    except Exception as exc:  # dernier recours : jamais d'exception vers l'appelant
        plan = _empty_plan(params if isinstance(params, dict) else {}, [], "no_route", "")
        plan["ignored_reports"] = []
        plan["warnings"] = [f"Erreur interne, plan vide : {type(exc).__name__}: {exc}"]
        plan["checks"]["messages"] = [traceback.format_exc(limit=3)]
    plan["compute_ms"] = round((time.perf_counter() - t0) * 1000)
    return plan
