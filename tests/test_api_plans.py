"""Plans par l'API : plan par défaut cohérent, panne partielle avec reports, pluie, quartier, routes coupées,
persistance, scénarios et rôles. Tourne sur les vraies données du dépôt (data/processed) et des bases temporaires."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from tests.conftest import BRIGADE, MAIRIE


def _plan(client: TestClient, **body: Any) -> dict[str, Any]:
    r = client.post("/api/plans", json=body, headers=MAIRIE)
    assert r.status_code == 200, r.text
    return r.json()


def test_default_plan_is_complete_and_honest(client: TestClient) -> None:
    """Plan par défaut : mode complet, au moins 90 % des points servis, checks.ok vrai, tracés lat/lon par véhicule."""
    plan = _plan(client)
    assert plan["mode"] == "complet" and plan["consolidation_points"]
    assert plan["checks"]["ok"] is True and plan["checks"]["unserved_ratio"] <= 0.10
    route = plan["routes"][0]
    lat, lon = route["path"][0]
    assert 11 < lat < 13 and -2 < lon < -1          # [lat, lon], pas [lon, lat]
    assert plan["vehicles"] and {v["status"] for v in plan["vehicles"]} == {"en service"}


def test_mostly_unserved_plan_is_never_green(client: TestClient) -> None:
    """Un seul camion : la majorité des points non servis, checks.ok faux même si les contrôles de forme passent."""
    plan = _plan(client, params={"trucks": 1})
    assert plan["checks"]["unserved_ratio"] > 0.5 and plan["checks"]["ok"] is False


def test_truck_down_is_partial_with_postponed(client: TestClient) -> None:
    """Panne d'un camion réel : recalcul partiel en moins de 5 s, reportés listés à part de unserved."""
    first = _plan(client, params={"trucks": 6})
    used = sorted({r["vehicle"].split("_trip")[0] for r in first["routes"]})
    t0 = time.perf_counter()
    plan = _plan(client, params={"trucks": 6}, events=[{"type": "truck_down", "vehicle_id": used[0]}],
                 previous_plan_id=first["plan_id"])
    assert time.perf_counter() - t0 < 5 and plan["compute_ms"] < 5000
    assert plan["mode"] == "partiel"
    assert not any(r["vehicle"].startswith(used[0] + "_") for r in plan["routes"])
    postponed = {p["id"] for p in plan["postponed"]}
    assert postponed and not postponed & {u["point_id"] for u in plan["unserved"]}
    assert plan["checks"]["postponed_count"] == len(postponed)
    assert next(v for v in plan["vehicles"] if v["id"] == used[0])["status"] == "en panne"


def test_unknown_truck_or_event_is_refused(client: TestClient) -> None:
    r = client.post("/api/plans", json={"events": [{"type": "truck_down", "vehicle_id": "truck99"}]}, headers=MAIRIE)
    assert r.status_code == 422 and "truck99" in r.json()["detail"]
    r = client.post("/api/plans", json={"events": [{"type": "meteorite"}]}, headers=MAIRIE)
    assert r.status_code == 422


def test_rain_uses_rain_view(client: TestClient) -> None:
    dry = _plan(client)
    rain = _plan(client, events=[{"type": "rain"}])
    assert rain["params_used"]["rainy_season"] is True
    assert any("pluie" in a.lower() for a in rain["assumptions"])
    assert rain["totals"]["distance_km"] != dry["totals"]["distance_km"] or rain["unserved"] != dry["unserved"]


def test_new_district_changes_plan_and_simulation(client: TestClient) -> None:
    """Quartier ajouté (data/territories.geojson) : plus de points et de demande, simulation différente."""
    territories = client.get("/api/territories").json()
    assert len(territories) >= 3
    base = _plan(client)
    with_district = None
    for t in territories:
        cand = _plan(client, events=[{"type": "new_district", "territory_id": t["id"]}])
        if len(cand["consolidation_points"]) > len(base["consolidation_points"]):
            with_district = cand
            break
    assert with_district is not None, "aucun quartier n'a de bâtiments téléchargés"
    s0 = client.post(f"/api/plans/{base['plan_id']}/simulation", json={"days": 7}, headers=MAIRIE).json()
    s1 = client.post(f"/api/plans/{with_district['plan_id']}/simulation", json={"days": 7}, headers=MAIRIE).json()
    assert s1["kg_produits"] > s0["kg_produits"]
    r = client.post("/api/plans", json={"events": [{"type": "new_district", "territory_id": "atlantide"}]},
                    headers=MAIRIE)
    assert r.status_code == 422


def test_cut_roads_are_listed_and_cache_untouched(client: TestClient) -> None:
    """Route coupée : retenue dans cut_roads ; le réseau en cache n'est pas modifié."""
    from core.optim.plan import default_network

    before = default_network().views["truck_dry"].n_edges
    base = _plan(client)
    lat, lon = base["routes"][0]["path"][1]
    plan = _plan(client, cut_roads=[{"lat": lat, "lon": lon}])
    assert plan["cut_roads"] and plan["cut_roads"][0]["edge_id"]
    assert isinstance(plan["inaccessible_due_to_cuts"], list)
    assert default_network().views["truck_dry"].n_edges == before


def test_plans_survive_restart_and_scenarios_compare(client: TestClient) -> None:
    a = client.post("/api/scenarios", json={"label": "A", "days": 3}, headers=MAIRIE).json()
    b = client.post("/api/scenarios", json={"label": "B", "days": 3, "events": [{"type": "rain"}]}, headers=MAIRIE).json()
    with TestClient(app) as again:                              # nouveau client : lecture depuis la base
        assert again.get(f"/api/plans/{a['plan_id']}", headers=MAIRIE).status_code == 200
        listed = {s["id"] for s in again.get("/api/scenarios", headers=MAIRIE).json()}
        assert {a["id"], b["id"]} <= listed
        diff = again.get(f"/api/scenarios/compare?a={a['id']}&b={b['id']}", headers=MAIRIE).json()
    keys = {line["indicateur"] for line in diff["ecarts"]}
    assert {"part_ramassee", "cout_fcfa", "non_servis", "reportes", "compute_ms"} <= keys


def test_plan_roles(client: TestClient) -> None:
    assert client.post("/api/plans", json={}).status_code == 401
    assert client.post("/api/plans", json={}, headers={"X-Role-Code": "faux"}).status_code == 401
    assert client.post("/api/plans", json={}, headers=BRIGADE).status_code == 403


def test_absurd_params_are_clamped(client: TestClient) -> None:
    plan = _plan(client, params={"population": 1e15, "trucks": -5})
    assert plan["params_used"]["population"] == client.get("/api/config").json()["params"]["population"]["max"]
    assert plan["params_used"]["trucks"] == 0 and any("ramené" in w for w in plan["warnings"])


def test_cutting_all_roads_around_a_point_isolates_it(client: TestClient) -> None:
    """Toutes les routes autour d'un point coupées : le point est listé comme rendu inaccessible."""
    from core.geo.graph import edge_id, nearest_node
    from core.optim.plan import default_network

    net = default_network()
    base = _plan(client)
    point = base["consolidation_points"][0]
    node, _ = nearest_node(net.views["truck_dry"], point["lat"], point["lon"])
    k = net.index_of[node]
    around = [edge_id(net, i) for i in range(len(net.edges["u"])) if k in (net.edges["u"][i], net.edges["v"][i])]
    plan = _plan(client, cut_roads=[{"edge_id": e} for e in around], previous_plan_id=base["plan_id"])
    assert point["id"] in {p["id"] for p in plan["inaccessible_due_to_cuts"]}
    assert len(plan["cut_roads"]) >= 1
