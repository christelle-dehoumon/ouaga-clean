"""Tournées camion : OR-Tools avec capacité, durée et abandon pénalisé, secours glouton, retrait au budget (sections 8 et 10)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

# Pénalité d'abandon d'un point (en mètres de trajet) : bien plus grande que toute tournée, donc le solveur sert
# tout ce qu'il peut ; le terme proportionnel à la masse fait abandonner d'abord les petits points.
DROP_PENALTY_M = 10_000_000
DROP_PENALTY_PER_KG = 100


@dataclass
class Fleet:
    """Véhicules (virtuels, un par rotation) et leurs limites communes."""

    vehicles: list[str]
    capacity_kg: float
    max_minutes: float
    speed_kmh: float
    service_min: float

    def travel_min(self, metres: float) -> float:
        """Minutes de trajet pour une distance (mètres ou mètres équivalents)."""
        return metres / 1000 / self.speed_kmh * 60 if self.speed_kmh > 0 else math.inf


def route_minutes(stops: list[int], dist: np.ndarray, fleet: Fleet) -> float:
    """Durée d'une tournée dépôt -> arrêts -> dépôt, arrêts comptés au temps de service."""
    seq = [0, *stops, 0]
    return sum(fleet.travel_min(dist[a, b]) for a, b in zip(seq[:-1], seq[1:])) + fleet.service_min * len(stops)


def solve_ortools(dist: np.ndarray, demand: list[float], fleet: Fleet, time_limit_s: float
                  ) -> tuple[list[list[int]] | None, bool]:
    """Tournées OR-Tools (nœud 0 = dépôt), une liste d'arrêts par véhicule (None si échec), et vrai si la limite de temps a coupé."""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    n, n_veh = len(demand) + 1, len(fleet.vehicles)
    if n_veh == 0 or n == 1:
        return [[] for _ in fleet.vehicles], False
    dist_i = np.rint(np.minimum(dist, 1e9)).astype(np.int64)
    load_i = [0] + [int(math.ceil(d)) for d in demand]
    speed_ms = fleet.speed_kmh / 3.6
    service_s = int(round(fleet.service_min * 60))
    manager = pywrapcp.RoutingIndexManager(n, n_veh, 0)
    routing = pywrapcp.RoutingModel(manager)

    def arc(i: int, j: int) -> int:
        """Mètres entre deux index du solveur."""
        return int(dist_i[manager.IndexToNode(i), manager.IndexToNode(j)])

    def travel(i: int, j: int) -> int:
        """Secondes de trajet plus service au point de départ."""
        a = manager.IndexToNode(i)
        return int(dist_i[a, manager.IndexToNode(j)] / speed_ms) + (service_s if a != 0 else 0)

    def load(i: int) -> int:
        """Masse à charger au nœud."""
        return load_i[manager.IndexToNode(i)]

    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(arc))
    routing.AddDimension(routing.RegisterTransitCallback(travel), 0, int(fleet.max_minutes * 60), True, "time")
    routing.AddDimensionWithVehicleCapacity(routing.RegisterUnaryTransitCallback(load), 0,
                                            [int(fleet.capacity_kg)] * n_veh, True, "load")
    for node in range(1, n):
        routing.AddDisjunction([manager.NodeToIndex(node)], DROP_PENALTY_M + DROP_PENALTY_PER_KG * load_i[node])
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GREEDY_DESCENT
    params.time_limit.FromMilliseconds(max(int(time_limit_s * 1000), 100))
    solution = routing.SolveWithParameters(params)
    status = routing_enums_pb2.RoutingSearchStatus
    timed_out = routing.status() in (status.ROUTING_FAIL_TIMEOUT, status.ROUTING_PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED)
    if solution is None:
        return None, timed_out
    routes = []
    for v in range(n_veh):
        idx, stops = routing.Start(v), []
        idx = solution.Value(routing.NextVar(idx))
        while not routing.IsEnd(idx):
            stops.append(manager.IndexToNode(idx))
            idx = solution.Value(routing.NextVar(idx))
        routes.append(stops)
    return routes, timed_out


def solve_greedy(dist: np.ndarray, demand: list[float], fleet: Fleet) -> list[list[int]]:
    """Secours : chaque véhicule va au point non servi le plus proche tant que capacité et durée le permettent."""
    left = set(range(1, len(demand) + 1))
    routes = []
    for _ in fleet.vehicles:
        stops: list[int] = []
        here, load = 0, 0.0
        while True:
            options = sorted((dist[here, p], p) for p in left if load + demand[p - 1] <= fleet.capacity_kg
                             and route_minutes([*stops, p], dist, fleet) <= fleet.max_minutes)
            if not options:
                break
            here = options[0][1]
            stops.append(here)
            load += demand[here - 1]
            left.discard(here)
        routes.append(stops)
    return routes


def trim_to_budget(routes: list[list[int]], dist: np.ndarray, demand: list[float],
                   cost_of: Callable[[list[list[int]]], float], budget: float) -> tuple[list[list[int]], list[int]]:
    """Retire le point le moins rentable (kg par km économisé) tant que le coût dépasse le budget."""
    routes = [list(r) for r in routes]
    removed: list[int] = []
    while cost_of(routes) > budget and any(routes):
        best: tuple[float, int, int] | None = None
        for v, stops in enumerate(routes):
            seq = [0, *stops, 0]
            for k in range(1, len(seq) - 1):
                saved = dist[seq[k - 1], seq[k]] + dist[seq[k], seq[k + 1]] - dist[seq[k - 1], seq[k + 1]]
                ratio = demand[seq[k] - 1] / max(saved / 1000, 1e-6)
                if best is None or ratio < best[0]:
                    best = (ratio, v, k - 1)
        if best is None:
            break
        removed.append(routes[best[1]].pop(best[2]))
    return routes, removed


def _feasible(stops: list[int], dist: np.ndarray, demand: list[float], fleet: Fleet) -> bool:
    """Vrai si la tournée respecte capacité et durée."""
    return sum(demand[i - 1] for i in stops) <= fleet.capacity_kg + 1e-6 and \
        route_minutes(stops, dist, fleet) <= fleet.max_minutes + 1e-6


def _delta(stops: list[int], k: int, s: int, dist: np.ndarray) -> float:
    """Mètres ajoutés en insérant s à la position k de la tournée."""
    seq = [0, *stops, 0]
    return float(dist[seq[k], s] + dist[s, seq[k + 1]] - dist[seq[k], seq[k + 1]])


def insert_cheapest(routes: list[list[int]], to_insert: list[int], dist: np.ndarray, demand: list[float],
                    fleet: Fleet) -> tuple[list[list[int]], list[int]]:
    """Insère chaque arrêt (plus lourd d'abord) à la place la moins chère qui respecte capacité et durée ; renvoie les restes."""
    routes = [list(r) for r in routes]
    left = []
    for s in sorted(to_insert, key=lambda i: (-demand[i - 1], i)):
        best: tuple[float, int, int] | None = None
        for v, stops in enumerate(routes):
            for k in range(len(stops) + 1):
                cand = stops[:k] + [s] + stops[k:]
                if (best is None or _delta(stops, k, s, dist) < best[0]) and _feasible(cand, dist, demand, fleet):
                    best = (_delta(stops, k, s, dist), v, k)
        if best is None:
            left.append(s)
        else:
            routes[best[1]].insert(best[2], s)
    return routes, left


def _length(stops: list[int], dist: np.ndarray) -> float:
    """Longueur d'une tournée dépôt -> arrêts -> dépôt."""
    seq = [0, *stops, 0]
    return float(sum(dist[a, b] for a, b in zip(seq[:-1], seq[1:])))


def improve(routes: list[list[int]], dist: np.ndarray, demand: list[float], fleet: Fleet,
            deadline: float) -> tuple[list[list[int]], bool]:
    """Amélioration locale déterministe (2-opt dans une tournée, déplacement d'un arrêt) ; vrai si l'échéance a coupé."""
    import time

    routes = [list(r) for r in routes]
    improved = True
    while improved:
        improved = False
        if time.perf_counter() > deadline:
            return routes, True
        for v, stops in enumerate(routes):
            for i in range(len(stops) - 1):
                for j in range(i + 1, len(stops)):
                    cand = stops[:i] + stops[i:j + 1][::-1] + stops[j + 1:]
                    if _length(cand, dist) < _length(stops, dist) - 1e-6 and _feasible(cand, dist, demand, fleet):
                        routes[v], stops, improved = cand, cand, True
        for v in range(len(routes)):
            for pos in range(len(routes[v])):
                if pos >= len(routes[v]):
                    break
                s = routes[v][pos]
                rest = routes[v][:pos] + routes[v][pos + 1:]
                gain = _length(routes[v], dist) - _length(rest, dist)
                for w in range(len(routes)):
                    base = rest if w == v else routes[w]
                    for k in range(len(base) + 1):
                        cand = base[:k] + [s] + base[k:]
                        if _delta(base, k, s, dist) < gain - 1e-6 and _feasible(cand, dist, demand, fleet):
                            routes[v] = rest
                            routes[w] = cand
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
    return routes, False
