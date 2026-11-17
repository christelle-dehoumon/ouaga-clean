"""Contrôles de cohérence d'un plan avant de le renvoyer (section 11 des règles)."""

from __future__ import annotations

from collections import Counter
from typing import Any

# Tolérance d'arrondi sur les masses et les coûts.
EPS = 1e-6


def check_plan(plan: dict[str, Any], allowed_vehicles: set[str], broken_trucks: set[str], budget: float,
               max_minutes: float) -> dict[str, Any]:
    """Contrôles du contrat : capacité, véhicules, budget, chaque point servi ou signalé, arrêts existants."""
    messages: list[str] = []
    point_ids = [p.get("id") for p in plan.get("collection_points", [])]
    known = set(point_ids)
    routes = plan.get("routes", [])
    capacity_ok = all(r.get("load_kg", 0) <= r.get("capacity_kg", 0) + EPS for r in routes)
    if not capacity_ok:
        messages.append("Une tournée dépasse la capacité de son véhicule.")
    vehicles = Counter(r.get("vehicle") for r in routes)
    reused = [v for v, c in vehicles.items() if c > 1]
    foreign = [v for v in vehicles if v not in allowed_vehicles]
    on_broken = [v for v in vehicles if isinstance(v, str) and v.split("_trip")[0] in broken_trucks]
    vehicles_ok = not (reused or foreign or on_broken)
    if not vehicles_ok:
        messages.append(f"Véhicules incohérents : utilisés deux fois {reused}, inconnus {foreign}, en panne {on_broken}.")
    too_long = [r.get("vehicle") for r in routes if r.get("duration_min", 0) > max_minutes + EPS]
    if too_long:
        messages.append(f"Tournées trop longues (plus de {max_minutes:g} min) : {too_long}.")
    total_cost = sum(r.get("cost", 0) for r in routes)
    budget_ok = total_cost <= budget + EPS
    if not budget_ok:
        messages.append(f"Coût total {total_cost:.0f} supérieur au budget {budget:.0f}.")
    seen = Counter(s for r in routes for s in r.get("stops", []))
    seen.update(u.get("point_id") for u in plan.get("unserved", []))
    unknown = sorted(str(s) for s in seen if s not in known)
    if unknown:
        messages.append(f"Arrêts cités inexistants : {unknown}.")
    every = len(point_ids) == len(known) and all(seen.get(p, 0) == 1 for p in known) and not unknown
    if not every:
        messages.append("Un point de regroupement n'est pas dans exactement une tournée ou dans « unserved ».")
    return {"capacity_ok": capacity_ok, "budget_ok": budget_ok, "vehicles_ok": vehicles_ok and not too_long,
            "every_point_served_or_reported": every, "messages": messages}


def all_ok(checks: dict[str, Any]) -> bool:
    """Vrai si tous les contrôles sont au vert."""
    return all(checks.get(k) for k in ("capacity_ok", "budget_ok", "vehicles_ok", "every_point_served_or_reported")) \
        and checks.get("network_ok", True)
