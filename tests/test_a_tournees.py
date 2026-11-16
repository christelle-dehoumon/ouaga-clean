"""core.optim.tournees : OR-Tools, secours glouton, retrait au budget."""

import numpy as np

from core.optim.tournees import Fleet, route_minutes, solve_greedy, solve_ortools, trim_to_budget


def _line() -> np.ndarray:
    """Dépôt en 0 et trois points sur une ligne, à 1, 2 et 10 km."""
    x = np.array([0.0, 1000.0, 2000.0, 10000.0])
    return np.abs(x[:, None] - x[None, :])


def test_ortools_and_greedy_respect_limits() -> None:
    """Capacité 2 t et 60 min : les deux méthodes respectent capacité et durée, servent au moins les points proches."""
    dist, demand = _line(), [1000.0, 1000.0, 1500.0]
    fleet = Fleet(["truck1_trip1", "truck1_trip2"], 2000, 60, 25, 10)
    for routes in (solve_ortools(dist, demand, fleet, 1)[0], solve_greedy(dist, demand, fleet)):
        assert routes is not None and len(routes) == 2
        assert all(sum(demand[i - 1] for i in r) <= 2000 and route_minutes(r, dist, fleet) <= 60 for r in routes)
        assert {1, 2} <= {i for r in routes for i in r}
    assert solve_ortools(dist, demand, Fleet([], 2000, 60, 25, 10), 1) == ([], False)


def test_trim_to_budget_drops_least_profitable() -> None:
    """Le point lointain (kg par km le plus faible) part le premier."""
    dist, demand = _line(), [1000.0, 1000.0, 1000.0]
    routes, removed = trim_to_budget([[1, 2, 3]], dist, demand, lambda rs: sum(len(r) for r in rs), 2)
    assert removed == [3] and routes == [[1, 2]]
