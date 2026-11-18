"""core.optim.matrix : Dijkstra multi-sources, cache par (vue, source), repli à vol d'oiseau."""

from pathlib import Path
from typing import Any

import pytest

from core.config import load_config
from core.geo import graph as g
from core.optim.matrix import MatrixCache, path_length_m, straight_matrix
from tests.test_a_geo_graph import toy_graph

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "commune_config.json"


@pytest.fixture()
def net() -> g.Network:
    """Réseau jouet sans fichiers de pluie."""
    c: dict[str, Any] = load_config(REPO_CONFIG)
    c["paths"]["flood_zones"] = "/nonexistent/flood.geojson"
    c["paths"]["waterways"] = "/nonexistent/waterways.geojson"
    return g.build_network(toy_graph(), c)


def _coords(net: g.Network, nodes: list[int]) -> list[tuple[float, float]]:
    """Coordonnées des nœuds."""
    return [(float(net.lat[net.index_of[n]]), float(net.lon[net.index_of[n]])) for n in nodes]


def test_cache_counts_and_values(net: g.Network) -> None:
    """Un seul appel pour toutes les sources ; second appel identique sans Dijkstra ; ajout d'un point = une source."""
    cache = MatrixCache()
    m, warnings = cache.matrix(net, "truck_dry", [1, 3], _coords(net, [1, 3]), 1.4)
    assert cache.dijkstra_calls == 1 and cache.sources_computed == 2 and not warnings
    assert m[0, 1] == pytest.approx(150.0) and m[1, 0] == pytest.approx(150.0)
    cache.matrix(net, "truck_dry", [1, 3], _coords(net, [1, 3]), 1.4)
    assert cache.dijkstra_calls == 1
    m, _ = cache.matrix(net, "truck_dry", [1, 3, 2], _coords(net, [1, 3, 2]), 1.4)
    assert cache.dijkstra_calls == 2 and cache.sources_computed == 3
    assert m[1, 2] == pytest.approx(100.0) and m[2, 0] == pytest.approx(100.0)   # 2 -> 9 -> 1 (sens unique)
    cache.matrix(net, "truck_dry", [1, 2], _coords(net, [1, 2]), 1.4)             # retrait : rien à calculer
    assert cache.dijkstra_calls == 2
    seq = cache.path(net, "truck_dry", 2, 1)
    assert seq is not None and path_length_m(net, "truck_dry", seq) == pytest.approx(100.0)


def test_unknown_node_uses_straight_line(net: g.Network) -> None:
    """Nœud hors vue (île 7) ou absent : vol d'oiseau × facteur et avertissement, sans exception."""
    cache = MatrixCache()
    nodes: list[int | None] = [1, 7, None]
    coords = _coords(net, [1, 7]) + [(12.0, -1.0)]
    m, warnings = cache.matrix(net, "truck_dry", nodes, coords, 1.4)
    assert m.shape == (3, 3) and m[0, 1] > 0 and warnings
    assert straight_matrix(coords, 1.4)[0, 1] == pytest.approx(m[0, 1])
    assert cache.path(net, "truck_dry", None, 1) is None
