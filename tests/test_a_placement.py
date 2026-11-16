"""core.geo.buildings et core.optim.placement : demande recalée, points déterministes posés sur le réseau."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.config import load_config
from core.geo import graph as g
from core.geo.buildings import building_demand, estimate_demand
from core.optim.placement import place_points
from tests.test_a_geo_graph import toy_graph

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "commune_config.json"


@pytest.fixture()
def cfg() -> dict[str, Any]:
    """Configuration du dépôt, petits bornes de points, sans fichiers de pluie."""
    c = load_config(REPO_CONFIG)
    c["paths"]["flood_zones"] = "/nonexistent/flood.geojson"
    c["paths"]["waterways"] = "/nonexistent/waterways.geojson"
    c["solver"]["min_collection_points"], c["solver"]["max_collection_points"] = 1, 4
    c["model"]["precollect_radius_m"] = 150
    c["model"]["cell_size_m"] = 10
    return c


def _demand(n: int = 200) -> dict[str, Any]:
    """Bâtiments jouets autour du carré 1-2-3-4 et de la piste 4-5-6, 1 kg chacun."""
    rng = np.random.default_rng(1)
    lat = 12.0 + rng.uniform(-0.0005, 0.0035, n)
    lon = -1.0 + rng.uniform(-0.0005, 0.0015, n)
    return {"lat": lat, "lon": lon, "kg": np.ones(n)}


def test_demand_population_split(cfg: dict[str, Any]) -> None:
    """Population répartie sur les bâtiments ; population 0 : personne ; population absente : persons_per_building."""
    persons, assumptions = estimate_demand(50, {"population": 1000}, cfg["model"])
    assert persons.sum() == pytest.approx(1000) and len(set(persons)) == 1 and assumptions
    assert estimate_demand(10, {"population": 0}, cfg["model"])[0].sum() == 0
    persons, _ = estimate_demand(10, {}, cfg["model"])
    assert persons.sum() == pytest.approx(10 * cfg["model"]["persons_per_building"])
    assert estimate_demand(0, {"population": 1}, cfg["model"])[0].size == 0


def _fake_buildings(cfg: dict[str, Any], tmp_path: Path) -> None:
    """Bâtiments jouets : 30 dans la zone pilote, 70 en dehors ; limite communale sans fichier (centre = bbox)."""
    lat = np.concatenate([np.full(30, 12.0), np.full(70, 12.4)])
    lon = np.concatenate([np.full(30, -1.0), np.full(70, -1.4)])
    np.savez(tmp_path / "buildings_centroids.npz", lat=lat, lon=lon)
    cfg["paths"]["processed_dir"] = str(tmp_path)
    cfg["paths"]["raw_dir"] = str(tmp_path)
    cfg["paths"]["territories"] = str(tmp_path / "territories.geojson")
    cfg["bbox"] = {"west": -1.5, "south": 11.5, "east": -0.5, "north": 12.5}
    cfg["model"]["pilot_territory_ids"] = ["pilot"]
    cfg["model"]["pilot_square_m"] = 2000


def test_demand_only_in_active_territories(cfg: dict[str, Any], tmp_path: Path) -> None:
    """Demande = abonnés des territoires actifs seulement ; le reste revient en uncollected_kg ; quartier ajouté compté."""
    _fake_buildings(cfg, tmp_path)
    params = {"population": 1000, "subscription_rate": 0.4, "frequency_per_week": 7, "extra_territories": []}
    out = building_demand(cfg, params)
    waste = cfg["model"]["waste_kg_per_person_day"]
    assert len(out["kg"]) == 30 and out["territories"][0]["population"] == 300
    assert out["kg"].sum() == pytest.approx(300 * waste * 0.4)
    assert out["uncollected_kg"] == pytest.approx(300 * waste * 0.6)
    assert set(out["territory_id"]) == {"pilot"} and out["data_tag"] == "estimated"
    quarter = {"type": "Feature", "properties": {"id": "q1", "population": 50, "source": "provided"},
               "geometry": {"type": "Polygon", "coordinates": [[[-1.41, 12.39], [-1.39, 12.39], [-1.39, 12.41],
                                                                 [-1.41, 12.41], [-1.41, 12.39]]]}}
    (tmp_path / "territories.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [quarter]}))
    out = building_demand(cfg, {**params, "extra_territories": ["q1", "absent"]})
    assert len(out["kg"]) == 100 and {"id": "q1", "name": "q1", "buildings": 70, "population": 50,
                                      "population_tag": "provided"} in out["territories"]
    assert any("absent" in w for w in out["warnings"])
    far = {**quarter, "properties": {"id": "q_far"}, "geometry": {"type": "Polygon", "coordinates": [
        [[5, 20], [5.1, 20], [5.1, 20.1], [5, 20]]]}}
    out = building_demand(cfg, {**params, "extra_territories": [far, {"type": "Feature", "geometry": None}]})
    assert len(out["kg"]) == 30 and any("hors de la commune" in w for w in out["warnings"])
    assert any("Feature GeoJSON" in w for w in out["warnings"])


def test_building_demand_missing_file(cfg: dict[str, Any], tmp_path: Path) -> None:
    """Fichier de bâtiments absent : demande vide et message, sans exception."""
    cfg["paths"]["processed_dir"] = str(tmp_path)
    out = building_demand(cfg, cfg["params"])
    assert out["kg"].size == 0 and "introuvables" in out["warnings"][0] and out["data_tag"] == "estimated"


def test_points_on_network_deterministic(cfg: dict[str, Any]) -> None:
    """Chaque point est sur un nœud de la vue, fusionné, au format du contrat ; deux appels donnent le même résultat."""
    net = g.build_network(toy_graph(), cfg)
    demand = _demand()
    first = place_points(net, demand, [], cfg)
    assert first == place_points(net, demand, [], cfg)
    assert first["points"] and len(first["node_ids"]) == len(set(first["node_ids"])) == len(first["points"])
    for p, node in zip(first["points"], first["node_ids"]):
        view = net.views["truck_dry" if p["access"] == "truck" else "tricycle_dry"]
        assert view.node_mask[net.index_of[node]]
        assert (p["lat"], p["lon"]) == pytest.approx((net.lat[net.index_of[node]], net.lon[net.index_of[node]]))
        assert set(p) == {"id", "lat", "lon", "demand_kg", "access", "territory_id", "type", "data_tag"}
        assert p["data_tag"] == "estimated"
    assert sum(p["demand_kg"] for p in first["points"]) == pytest.approx(200, abs=0.5)
    assert 0 <= first["walk_share"] <= 1


def test_far_demand_goes_to_tricycle_node(cfg: dict[str, Any]) -> None:
    """Demande seulement près du chemin 5-6 (hors camion, à plus de precollect_radius_m d'un nœud camion) : accès tricycle."""
    net = g.build_network(toy_graph(), cfg)
    cfg["model"]["precollect_radius_m"] = 100
    demand = {"lat": np.full(5, 12.003), "lon": np.full(5, -1.0), "kg": np.ones(5)}
    out = place_points(net, demand, [], cfg)
    assert [p["access"] for p in out["points"]] == ["tricycle"] and out["node_ids"] == [6]


def test_dumpsites_added_and_bad_inputs(cfg: dict[str, Any]) -> None:
    """Dépotoirs actifs comptés (poids estimé ou par taille), nettoyés ignorés, entrées absurdes sans exception."""
    net = g.build_network(toy_graph(), cfg)
    dumps = [{"lat": 12.0, "lon": -1.0, "estimated_kg": 800, "status": "active"},
             {"lat": 12.001, "lon": -0.999, "size": "large", "status": "active"},
             {"lat": 12.0, "lon": -1.0, "estimated_kg": 5000, "status": "cleaned"},
             {"lat": "abc", "lon": None}, "pas un dict"]
    out = place_points(net, {"lat": [], "lon": [], "kg": []}, dumps, cfg)
    total = 800 + cfg["model"]["dumpsite_kg_by_size"]["large"]
    assert sum(p["demand_kg"] for p in out["points"]) == pytest.approx(total)
    assert any("ignoré" in w for w in out["warnings"])
    assert place_points(net, {}, None, cfg)["points"] == []
    assert place_points(net, {"lat": [1, 2], "lon": [1], "kg": [1]}, [], cfg)["points"] == []
    assert place_points(net, _demand(), [], {"model": "x", "solver": None})["points"]


def test_empty_network_keeps_points(cfg: dict[str, Any], tmp_path: Path) -> None:
    """Sans réseau : points au centre des groupes, nœud None, avertissement."""
    cfg["paths"]["processed_dir"] = str(tmp_path)
    out = place_points(g.load_network(cfg), _demand(), [], cfg)
    assert out["points"] and all(n is None for n in out["node_ids"])
    assert any("indisponible" in w for w in out["warnings"])
