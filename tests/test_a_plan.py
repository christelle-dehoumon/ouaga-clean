"""core.optim.plan : compute_plan sur un graphe jouet (section 13 des règles, hors panne, pluie et quartier)."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.config import load_config
from core.geo import graph as g
from core.optim.coherence import all_ok
from core.optim.plan import compute_plan
from tests.test_a_geo_graph import toy_graph

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "commune_config.json"
PLAN_KEYS = {"plan_id", "computed_at", "mode", "compute_ms", "params_used", "collection_points", "routes", "unserved",
             "checks", "totals", "assumptions", "warnings", "ignored_reports"}


@pytest.fixture()
def setup(tmp_path: Path) -> tuple[dict[str, Any], g.Network, dict[str, Any]]:
    """Configuration jouet : 200 bâtiments autour du carré 1-2-3-4, zone pilote qui les couvre, 2 camions."""
    c = load_config(REPO_CONFIG)
    rng = np.random.default_rng(1)
    np.savez(tmp_path / "buildings_centroids.npz", lat=12.0 + rng.uniform(0, 0.001, 200),
             lon=-1.0 + rng.uniform(0, 0.001, 200))
    c["paths"].update({"processed_dir": str(tmp_path), "raw_dir": str(tmp_path), "territories": str(tmp_path / "t.geojson"),
                       "flood_zones": "/nonexistent/f.geojson", "waterways": "/nonexistent/w.geojson"})
    c["bbox"] = {"west": -1.001, "south": 11.999, "east": -0.998, "north": 12.002}
    c["model"].update({"precollect_radius_m": 150, "cell_size_m": 10, "pilot_square_m": 1000})
    c["solver"].update({"min_collection_points": 1, "max_collection_points": 4, "time_limit_s": 1})
    params = {**c["params"], "population": 2000, "trucks": 2, "truck_capacity_kg": 5000, "budget": 1e9}
    return c, g.build_network(toy_graph(), c), params


def _consistent(plan: dict[str, Any]) -> None:
    """Plan au format du contrat, contrôles au vert, chaque point servi ou signalé une fois."""
    assert set(plan) == PLAN_KEYS and all_ok(plan["checks"])
    ids = [p["id"] for p in plan["collection_points"]]
    cited = [s for r in plan["routes"] for s in r["stops"]] + [u["point_id"] for u in plan["unserved"]]
    assert sorted(cited) == sorted(ids)


def test_normal_plan(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Paramètres normaux : plan optimisé, tournées de véhicules virtuels, non collecté renvoyé ; même entrée = même plan."""
    cfg, net, params = setup
    plan = compute_plan(params, [], cfg=cfg, net=net)
    _consistent(plan)
    assert plan["mode"] == "optimized" and plan["routes"] and plan["totals"]["points_served"] > 0
    assert all(r["vehicle"].startswith("truck") and "_trip" in r["vehicle"] for r in plan["routes"])
    assert plan["totals"]["uncollected_kg"] > 0
    again = compute_plan(params, [], cfg=cfg, net=net)
    strip = lambda p: {k: v for k, v in p.items() if k not in ("plan_id", "computed_at", "compute_ms")}  # noqa: E731
    assert strip(plan) == strip(again)


@pytest.mark.parametrize("change,reason", [({"trucks": 0}, "capacity"), ({"budget": 0}, "budget")])
def test_no_truck_or_no_budget(setup: tuple[dict[str, Any], g.Network, dict[str, Any]], change: dict[str, Any],
                               reason: str) -> None:
    """Zéro camion ou budget nul : aucune tournée, tous les points dans unserved avec le bon motif."""
    cfg, net, params = setup
    plan = compute_plan({**params, **change}, [], cfg=cfg, net=net)
    _consistent(plan)
    assert not plan["routes"] and {u["reason"] for u in plan["unserved"]} == {reason}


def test_broken_trucks_lose_all_trips(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Un camion en panne n'apparaît dans aucune tournée."""
    cfg, net, params = setup
    plan = compute_plan({**params, "broken_trucks": ["truck1"]}, [], cfg=cfg, net=net)
    _consistent(plan)
    assert not any(r["vehicle"].startswith("truck1_") for r in plan["routes"])


def test_reports_inside_and_outside(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Signalement accepté dans la zone : demande ajoutée ; hors graphe ou absurde : ignoré sans exception."""
    cfg, net, params = setup
    base = sum(p["demand_kg"] for p in compute_plan(params, [], cfg=cfg, net=net)["collection_points"])
    reports = [{"id": "r1", "lat": 12.0005, "lon": -0.9995, "size": "large", "status": "accepted"},
               {"id": "r2", "lat": 40.0, "lon": 10.0, "size": "large", "status": "accepted"},
               {"id": "r3", "lat": "x", "lon": None, "status": "accepted"}, "pas un dict"]
    plan = compute_plan(params, reports, cfg=cfg, net=net)
    _consistent(plan)
    added = sum(p["demand_kg"] for p in plan["collection_points"]) - base
    assert added == pytest.approx(cfg["model"]["dumpsite_kg_by_size"]["large"], abs=1)


@pytest.mark.parametrize("params", [{"trucks": -3, "budget": "abc"}, {}, [], None, {"broken_trucks": [1, None]}])
def test_absurd_inputs(setup: tuple[dict[str, Any], g.Network, dict[str, Any]], params: Any) -> None:
    """Entrées absurdes : pas d'exception, plan cohérent, avertissement quand une valeur est remplacée."""
    cfg, net, _ = setup
    plan = compute_plan(params, "pas une liste", cfg=cfg, net=net)  # type: ignore[arg-type]
    _consistent(plan)


def test_no_network_never_raises(setup: tuple[dict[str, Any], g.Network, dict[str, Any]], tmp_path: Path) -> None:
    """Réseau absent : plan valide, points non servis faute de route."""
    cfg, _, params = setup
    empty = g.load_network({**cfg, "paths": {**cfg["paths"], "processed_dir": str(tmp_path / "rien")}})
    plan = compute_plan(params, [], cfg=cfg, net=empty)
    _consistent(plan)
    assert plan["mode"] == "fallback"
    assert not plan["routes"] and all(u["reason"] == "no_route" for u in plan["unserved"])


def test_missing_network_and_buildings_never_claims_optimized(tmp_path: Path) -> None:
    """Un environnement sans données géographiques renvoie un fallback explicite, pas un plan optimisé vide."""
    cfg = load_config(REPO_CONFIG)
    cfg["paths"]["processed_dir"] = str(tmp_path / "missing")
    net = g.load_network(cfg)

    plan = compute_plan(cfg["params"], [], cfg=cfg, net=net)

    assert plan["mode"] == "fallback"
    assert not plan["collection_points"] and not plan["routes"]
    assert any("Réseau routier introuvable" in warning for warning in plan["warnings"])


def test_ignored_reports_listed(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Chaque signalement écarté est listé avec une raison en français ; le dépotoir valide devient un arrêt."""
    cfg, net, params = setup
    reports = [{"id": "ok", "lat": 12.001, "lon": -0.999, "size": "medium", "status": "accepted"},
               {"id": "far", "lat": 40.0, "lon": 10.0, "size": "large", "status": "accepted"},
               {"id": "bad", "lat": "x", "lon": None, "status": "accepted"},
               {"id": "wait", "lat": 12.0, "lon": -1.0, "size": "small", "status": "pending"},
               {"id": "done", "lat": 12.0, "lon": -1.0, "estimated_kg": 10, "status": "cleaned"}, 42]
    plan = compute_plan(params, reports, cfg=cfg, net=net)
    _consistent(plan)
    assert {i["report_id"] for i in plan["ignored_reports"]} == {"far", "bad", "wait", "done", "#6"}
    assert all(i["reason"] for i in plan["ignored_reports"])
    stop = [p for p in plan["collection_points"] if p["type"] == "dumpsite"]
    assert [p["id"] for p in stop] == ["d_ok"] and stop[0]["demand_kg"] == cfg["model"]["dumpsite_kg_by_size"]["medium"]


def test_breakdown_is_partial(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Panne : mode partial, contrôles au vert, aucun arrêt perdu, camion en panne absent ; changed déduit seul."""
    cfg, net, params = setup
    params = {**params, "truck_capacity_kg": 300}
    first = compute_plan(params, [], cfg=cfg, net=net)
    lost = {s for r in first["routes"] if r["vehicle"].startswith("truck1_") for s in r["stops"]}
    assert lost
    plan = compute_plan({**params, "broken_trucks": ["truck1"]}, [], previous_plan=first, cfg=cfg, net=net)
    _consistent(plan)
    assert plan["mode"] == "partial" and not any(r["vehicle"].startswith("truck1_") for r in plan["routes"])
    assert {p["id"] for p in plan["collection_points"]} == {p["id"] for p in first["collection_points"]}
    kept = {r["vehicle"]: r["stops"] for r in first["routes"] if not r["vehicle"].startswith("truck1_")}
    served = {s for r in plan["routes"] for s in r["stops"]}
    assert all(s in served for stops in kept.values() for s in stops)


def test_new_reports_are_inserted(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Nouveau dépotoir : inséré en mode partial."""
    cfg, net, params = setup
    first = compute_plan(params, [], cfg=cfg, net=net)
    reports = [{"id": "r1", "lat": 12.001, "lon": -0.999, "size": "small", "status": "accepted"}]
    plan = compute_plan(params, reports, previous_plan=first, cfg=cfg, net=net)
    _consistent(plan)
    assert plan["mode"] == "partial" and "d_r1" in {s for r in plan["routes"] for s in r["stops"]}


def test_rain_avoids_cut_edges_and_resnaps(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Pluie : nœud 2 coupé (gué) ; l'arrêt posé dessus est recalé, ou non servi si le rayon est trop court ; aucun tronçon coupé."""
    cfg, _, params = setup
    graph = toy_graph()
    graph.nodes[2]["ford"] = "yes"
    net = g.build_network(graph, cfg)
    reports = [{"id": "r1", "lat": 12.0, "lon": -0.999, "size": "small", "status": "accepted"}]
    plan = compute_plan({**params, "rainy_season": True}, reports, cfg=cfg, net=net)
    _consistent(plan)
    assert plan["checks"]["network_ok"] and "d_r1" in {s for r in plan["routes"] for s in r["stops"]}
    node2 = (round(float(net.lon[net.index_of[2]]), 6), round(float(net.lat[net.index_of[2]]), 6))
    assert all(tuple(c) != node2 for r in plan["routes"] if r["geometry"] for c in r["geometry"]["coordinates"])
    cfg["model"]["resnap_max_m"] = 10
    plan = compute_plan({**params, "rainy_season": True}, reports, cfg=cfg, net=net)
    _consistent(plan)
    assert {"point_id": "d_r1", "reason": "access"}.items() <= next(
        u for u in plan["unserved"] if u["point_id"] == "d_r1").items()


def test_new_quarter_is_partial(setup: tuple[dict[str, Any], g.Network, dict[str, Any]], tmp_path: Path) -> None:
    """Nouveau quartier : ses points apparaissent, les anciens restent, mode partial ; polygone hors commune averti."""
    cfg, net, params = setup
    cfg["model"].update({"pilot_square_m": 300, "precollect_radius_m": 300})
    with np.load(tmp_path / "buildings_centroids.npz") as d:
        lat, lon = d["lat"], d["lon"]
    np.savez(tmp_path / "buildings_centroids.npz", lat=np.concatenate([lat, np.full(20, 12.0025)]),
             lon=np.concatenate([lon, np.full(20, -0.9995)]))
    first = compute_plan(params, [], cfg=cfg, net=net)
    quarter = {"type": "Feature", "properties": {"id": "q_new_1"}, "geometry": {"type": "Polygon", "coordinates": [
        [[-1.0, 12.002], [-0.999, 12.002], [-0.999, 12.003], [-1.0, 12.003], [-1.0, 12.002]]]}}
    plan = compute_plan({**params, "extra_territories": [quarter]}, [], previous_plan=first, cfg=cfg, net=net)
    _consistent(plan)
    assert plan["mode"] == "partial"
    assert {p["id"] for p in first["collection_points"]} <= {p["id"] for p in plan["collection_points"]}
    assert sum(p["demand_kg"] for p in plan["collection_points"]) > sum(p["demand_kg"] for p in first["collection_points"])
    far = {**quarter, "properties": {"id": "q_far"}, "geometry": {"type": "Polygon", "coordinates": [
        [[5, 20], [5.1, 20], [5.1, 20.1], [5, 20]]]}}
    plan = compute_plan({**params, "extra_territories": [far]}, [], previous_plan=first, cfg=cfg, net=net)
    _consistent(plan)
    assert any("hors de la commune" in w for w in plan["warnings"])


def test_time_limit_reached_is_reported(setup: tuple[dict[str, Any], g.Network, dict[str, Any]],
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """Limite de sécurité du solveur atteinte : écrit dans warnings."""
    from core.optim import plan as plan_mod

    cfg, net, params = setup
    real = plan_mod.solve_ortools
    monkeypatch.setattr(plan_mod, "solve_ortools", lambda *a: (real(*a)[0], True))
    plan = compute_plan(params, [], cfg=cfg, net=net)
    assert any("Limite de sécurité" in w for w in plan["warnings"])


def test_stable_ids_and_unknown_previous_point(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Points nommés c_<nœud> ; un point précédent inconnu du réseau force un calcul complet, sans exception."""
    cfg, net, params = setup
    first = compute_plan(params, [], cfg=cfg, net=net)
    assert all(p["id"] == f"c_{int(net.node_ids[net.index_of[int(p['id'][2:])]])}" for p in first["collection_points"])
    broken = {**first, "collection_points": [{**p, "id": "c_999999"} for p in first["collection_points"]]}
    plan = compute_plan({**params, "broken_trucks": ["truck1"]}, [], previous_plan=broken, cfg=cfg, net=net)
    _consistent(plan)
    assert plan["mode"] == "optimized"


def test_partial_with_unserved_also_tries_full(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Panne qui laisse des points non servis : le calcul complet est aussi lancé et le choix est expliqué."""
    cfg, net, params = setup
    params = {**params, "truck_capacity_kg": 300}
    first = compute_plan(params, [], cfg=cfg, net=net)
    plan = compute_plan({**params, "broken_trucks": ["truck1"]}, [], previous_plan=first, cfg=cfg, net=net)
    _consistent(plan)
    assert any(u["reason"] in ("capacity", "time") for u in plan["unserved"])
    assert any("calcul complet" in w for w in plan["warnings"])


def _dumps(trusts: list[float], kg: float) -> list[dict[str, Any]]:
    """Dépotoirs validés au même endroit du graphe jouet, un par confiance donnée."""
    return [{"id": f"s{i}", "lat": 12.0005, "lon": -0.9995, "size": "large", "estimated_kg": kg, "status": "active",
             "trust": t} for i, t in enumerate(trusts)]


def test_heavy_dumpsite_is_split(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Dépotoir de 12 t, camions de 5 t : trois arrêts au même nœud, 4 t chacun, tous servis."""
    cfg, net, params = setup
    plan = compute_plan({**params, "population": 0}, _dumps([0.5], 12000), cfg=cfg, net=net)
    _consistent(plan)
    parts = [p for p in plan["collection_points"] if p["type"] == "dumpsite"]
    assert sorted(p["id"] for p in parts) == ["d_s0_p1", "d_s0_p2", "d_s0_p3"]
    assert all(p["demand_kg"] == pytest.approx(4000) for p in parts) and len({(p["lat"], p["lon"]) for p in parts}) == 1
    assert plan["totals"]["points_served"] == 3


def test_preselection_keeps_priority_stops(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Demande au-delà de la flotte : arrêts les plus sûrs au solveur, les autres non servis (capacity) ; déterministe."""
    cfg, net, params = setup
    trips = cfg["model"]["truck_trips_per_day"]
    fleet_kg = 5000 * trips
    trusts = [0.1, 0.9, 0.3, 0.7, 0.5, 0.2, 0.8, 0.4]
    n_keep = int(cfg["solver"]["preselect_capacity_factor"] * fleet_kg // 4000)
    assert n_keep < len(trusts)
    run = lambda: compute_plan({**params, "population": 0, "trucks": 1}, _dumps(trusts, 4000), cfg=cfg, net=net)  # noqa: E731
    plan = run()
    _consistent(plan)
    dropped = {u["point_id"] for u in plan["unserved"] if u["detail"].startswith("Non présenté au solveur")}
    lowest = sorted(range(len(trusts)), key=lambda i: trusts[i])[:len(trusts) - n_keep]
    assert dropped == {f"d_s{i}" for i in lowest}
    assert all(u["reason"] == "capacity" for u in plan["unserved"] if u["point_id"] in dropped)
    assert plan["totals"]["trucks_needed"] == -(-len(trusts) * 4000 // fleet_kg)
    assert plan["totals"]["trucks_needed_tag"] == "estimated"
    again = run()
    assert plan["routes"] == again["routes"] and plan["unserved"] == again["unserved"]


def test_fill_pass_inserts_dropped_stops(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Arrêts légers écartés par la présélection : réinsérés là où il reste de la place, retirés d'unserved ; déterministe."""
    cfg, net, params = setup
    trips = cfg["model"]["truck_trips_per_day"]
    heavy, light = _dumps([0.9] * 8, 4000), _dumps([0.1] * 4, 500)
    for i, r in enumerate(light):
        r["id"] = f"l{i}"
    run = lambda: compute_plan({**params, "population": 0, "trucks": 1}, heavy + light, cfg=cfg, net=net)  # noqa: E731
    plan = run()
    _consistent(plan)
    served = {s for r in plan["routes"] for s in r["stops"]}
    unserved = {u["point_id"] for u in plan["unserved"]}
    assert len(served & {f"d_s{i}" for i in range(8)}) == trips
    filled = served & {f"d_l{i}" for i in range(4)}
    assert filled and not filled & unserved
    assert any(w.startswith("Passe de remplissage") for w in plan["warnings"])
    assert all(r["load_kg"] <= r["capacity_kg"] for r in plan["routes"])
    again = run()
    assert plan["routes"] == again["routes"] and plan["unserved"] == again["unserved"]


def test_population_zero_serves_only_dumpsites(setup: tuple[dict[str, Any], g.Network, dict[str, Any]]) -> None:
    """Population 0 : aucune demande des ménages (pas de repli par bâtiment), seuls les dépotoirs, avertissement."""
    cfg, net, params = setup
    plan = compute_plan({**params, "population": 0}, _dumps([0.5], 800), cfg=cfg, net=net)
    _consistent(plan)
    assert [p["id"] for p in plan["collection_points"]] == ["d_s0"]
    assert plan["totals"]["uncollected_kg"] == 0 and plan["totals"]["points_served"] == 1
    assert any(w.startswith("Population 0") for w in plan["warnings"])
