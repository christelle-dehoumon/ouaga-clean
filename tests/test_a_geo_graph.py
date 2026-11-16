"""core.geo.graph : vues camion / tricycle / pluie, composante principale, index spatial, Dijkstra multi-sources."""

import json
import math
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pytest

from core.config import load_config
from core.geo import graph as g

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "commune_config.json"


def _two_way(G: nx.MultiDiGraph, a: int, b: int, **d: Any) -> None:
    """Ajoute une voie à double sens."""
    G.add_edge(a, b, **d)
    G.add_edge(b, a, **d)


def toy_graph() -> nx.MultiDiGraph:
    """Carré 1-2-3-4 en résidentiel, raccourci primaire 1-3, piste 4-5, chemin 5-6, île 7-8, sens unique 2->9->1."""
    G = nx.MultiDiGraph()
    coords = {1: (12.0, -1.0), 2: (12.0, -0.999), 3: (12.001, -0.999), 4: (12.001, -1.0),
              5: (12.002, -1.0), 6: (12.003, -1.0), 7: (12.05, -1.05), 8: (12.05, -1.049), 9: (11.9995, -0.9995)}
    for n, (y, x) in coords.items():
        G.add_node(n, y=y, x=x)
    _two_way(G, 1, 2, highway="residential", length=100.0)
    _two_way(G, 2, 3, highway="residential", length=100.0)
    _two_way(G, 3, 4, highway="residential", length=100.0, surface="asphalt")
    _two_way(G, 4, 1, highway="residential", length=100.0)
    _two_way(G, 1, 3, highway="primary", length=150.0)
    _two_way(G, 1, 3, highway="primary_link", length=500.0)          # arête parallèle plus longue
    _two_way(G, 4, 5, highway="track", length=100.0)
    _two_way(G, 5, 6, highway=["path", "track"], length=100.0)
    _two_way(G, 2, 4, highway="footway", length=10.0)                # jamais ouvert
    _two_way(G, 7, 8, highway="primary", length=100.0)               # composante isolée
    G.add_edge(2, 9, highway="primary", length=50.0)
    G.add_edge(9, 1, highway="primary", length=50.0)
    return G


@pytest.fixture()
def cfg() -> dict[str, Any]:
    """Configuration du dépôt, sans zones inondables ni cours d'eau."""
    c = load_config(REPO_CONFIG)
    c["paths"]["flood_zones"] = "/nonexistent/flood.geojson"
    c["paths"]["waterways"] = "/nonexistent/waterways.geojson"
    return c


def _nodes(view: g.RoadView) -> set[int]:
    """Identifiants des nœuds d'une vue."""
    return {int(n) for n in view.node_ids[view.node_mask]}


def test_views_follow_rules(cfg: dict[str, Any]) -> None:
    """Camion sans piste ni chemin, tricycle avec, île retirée ; sans coupure, la pluie garde les mêmes nœuds."""
    net = g.build_network(toy_graph(), cfg)
    assert set(net.views) == set(g.VIEW_NAMES)
    assert _nodes(net.views["truck_dry"]) == {1, 2, 3, 4, 9}
    assert _nodes(net.views["tricycle_dry"]) == {1, 2, 3, 4, 5, 6, 9}
    assert _nodes(net.views["truck_rain"]) == _nodes(net.views["truck_dry"])
    assert _nodes(net.views["tricycle_rain"]) == _nodes(net.views["tricycle_dry"])
    assert net.stats["rain_cut"] == 0
    assert net.assumptions and not net.warnings
    assert any("mètres équivalents" in a for a in net.assumptions)


def test_rain_weights_are_equivalent_metres(cfg: dict[str, Any]) -> None:
    """Pluie : voie de revêtement inconnu hors grands axes × facteur ; asphalte et grands axes inchangés ; longueur réelle gardée."""
    net = g.build_network(toy_graph(), cfg)
    i, f = net.index_of, cfg["network"]["rain_unpaved_factor"]
    rain, dry = net.views["truck_rain"], net.views["truck_dry"]
    assert rain.matrix[i[1], i[2]] == pytest.approx(100.0 * f)
    assert rain.length[i[1], i[2]] == pytest.approx(100.0)
    assert dry.matrix[i[1], i[2]] == pytest.approx(100.0)
    assert rain.matrix[i[3], i[4]] == pytest.approx(100.0)        # asphalte
    assert rain.matrix[i[1], i[3]] == pytest.approx(150.0)        # primaire, réputé revêtu


def _write_geojson(path: Path, geometry: dict[str, Any], waterway: str = "river") -> str:
    """Écrit une FeatureCollection d'une seule géométrie (type de cours d'eau donné) et renvoie son chemin."""
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"waterway": waterway}, "geometry": geometry}]}))
    return str(path)


def test_rain_cuts_waterway_unless_bridge(cfg: dict[str, Any], tmp_path: Path) -> None:
    """Un cours d'eau au milieu de 1-2 coupe cette voie en pluie, sauf si elle est un pont ; rien ne change à sec."""
    cfg["paths"]["waterways"] = _write_geojson(tmp_path / "w.geojson", {
        "type": "LineString", "coordinates": [[-0.9995, 12.00005], [-0.9995, 11.99995]]})
    cfg["network"]["flood_buffer_m"] = 10
    net = g.build_network(toy_graph(), cfg)
    i = net.index_of
    assert net.views["truck_rain"].matrix[i[1], i[2]] == 0 and net.views["truck_dry"].matrix[i[1], i[2]] > 0
    assert net.stats["rain_cut_waterway"] == 2
    G = toy_graph()
    for a, b in ((1, 2), (2, 1)):
        G.edges[a, b, 0]["bridge"] = "yes"
    assert g.build_network(G, cfg).stats["rain_cut"] == 0
    cfg["paths"]["waterways"] = _write_geojson(tmp_path / "d.geojson", {
        "type": "LineString", "coordinates": [[-0.9995, 12.00005], [-0.9995, 11.99995]]}, "drain")
    assert g.build_network(toy_graph(), cfg).stats["rain_cut_waterway"] == 0    # caniveau : pas de coupure


def test_rain_cuts_ford_flood_prone_and_zone(cfg: dict[str, Any], tmp_path: Path) -> None:
    """Gué (arête ou nœud), flood_prone et zone inondable coupent la voie en pluie seulement."""
    G = toy_graph()
    G.edges[3, 4, 0]["ford"] = "yes"
    G.edges[1, 3, 0]["flood_prone"] = "yes"
    G.nodes[9]["ford"] = "yes"
    net = g.build_network(G, cfg)
    i, rain = net.index_of, net.views["truck_rain"]
    assert rain.matrix[i[3], i[4]] == 0 and rain.matrix[i[4], i[3]] > 0
    assert rain.matrix[i[1], i[3]] == pytest.approx(500.0)   # 1-3 inondable coupé, reste la bretelle parallèle
    assert 9 not in _nodes(rain) and 9 in _nodes(net.views["truck_dry"])
    poly = [[-0.9996, 12.0004], [-0.9994, 12.0004], [-0.9994, 12.0006], [-0.9996, 12.0006], [-0.9996, 12.0004]]
    cfg["paths"]["flood_zones"] = _write_geojson(tmp_path / "z.geojson", {"type": "Polygon", "coordinates": [poly]})
    net = g.build_network(toy_graph(), cfg)
    assert net.stats["rain_cut_flood_zone"] == 6             # 1-3 (deux arêtes parallèles) et le chemin piéton 2-4, deux sens
    assert net.views["truck_rain"].matrix[net.index_of[1], net.index_of[3]] == 0


def test_views_share_nodes_and_are_masks(cfg: dict[str, Any]) -> None:
    """Toutes les vues partagent le même jeu de nœuds ; une vue n'est qu'un masque d'arêtes."""
    net = g.build_network(toy_graph(), cfg)
    n = len(net.node_ids)
    for view in net.views.values():
        assert view.node_ids is net.node_ids
        assert view.matrix.shape == (n, n)
        assert view.edge_mask.shape == net.views["truck_dry"].edge_mask.shape
        assert view.length.shape == (n, n) and view.length.nnz == view.matrix.nnz
    assert net.views["truck_rain"].n_edges == net.views["truck_dry"].n_edges < net.views["tricycle_dry"].n_edges


def test_dijkstra_multi_source_parallel_and_oneway(cfg: dict[str, Any]) -> None:
    """Un seul appel pour plusieurs sources ; arête parallèle la plus courte retenue ; sens unique respecté."""
    net = g.build_network(toy_graph(), cfg)
    view = net.views["truck_dry"]
    dist, pred, kept = g.shortest_paths(view, net.index_of, [1, 2, 6, 999])
    assert kept == [1, 2] and dist.shape == (2, len(net.node_ids))
    i = net.index_of
    assert dist[0, i[3]] == pytest.approx(150.0)
    assert dist[1, i[1]] == pytest.approx(100.0)          # 2->9->1 = 100, égal au direct
    assert dist[0, i[9]] == pytest.approx(150.0)          # 1->2->9 : pas de 1->9 direct
    assert math.isinf(dist[0, i[7]])
    assert pred[0, i[9]] == i[2]


def test_nearest_node_stays_in_view(cfg: dict[str, Any]) -> None:
    """Le nœud le plus proche appartient à la vue ; entrées absurdes : None sans exception."""
    net = g.build_network(toy_graph(), cfg)
    node, dist = g.nearest_node(net.views["truck_dry"], 12.003, -1.0)   # sur le nœud 6, hors camion
    assert node == 4 and dist == pytest.approx(222, abs=5)
    assert g.nearest_node(net.views["tricycle_dry"], 12.003, -1.0)[0] == 6
    for bad in [(None, 1), ("abc", 1), (float("nan"), 0), (95, 0), (0, 500)]:
        assert g.nearest_node(net.views["truck_dry"], *bad) is None


def test_missing_or_broken_data_never_raises(cfg: dict[str, Any], tmp_path: Path) -> None:
    """Pickle absent ou corrompu, graphe vide, config absurde : réseau vide avec message en français."""
    cfg["paths"]["processed_dir"] = str(tmp_path)
    net = g.load_network(cfg)
    assert net.warnings and "introuvable" in net.warnings[0]
    assert g.nearest_node(net.views["truck_dry"], 12.0, -1.0) is None
    (tmp_path / "roads_graph.pkl").write_bytes(b"pas un pickle")
    assert "illisible" in g.load_network(cfg).warnings[0]
    empty = g.build_network(nx.MultiDiGraph(), {"network": "abc"})
    assert all(v.n_nodes == 0 for v in empty.views.values()) and len(empty.warnings) == 4
    dist, _, kept = g.shortest_paths(empty.views["truck_dry"], empty.index_of, [1])
    assert kept == [] and dist.shape[0] == 0
    assert np.all(np.isfinite(g.build_network(toy_graph(), cfg).views["truck_dry"].matrix.data))
