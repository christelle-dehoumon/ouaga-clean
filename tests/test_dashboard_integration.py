"""Vérifie les ressources et le flux API réellement utilisés par le dashboard."""

import os
import base64
from datetime import datetime, timezone

os.environ["REPORTS_DB"] = ":memory:"

from fastapi.testclient import TestClient

from api import main
from api.main import V, app

client = TestClient(app)


def setup_function() -> None:
    V.reset()
    app.state.plans.clear()


def test_dashboard_and_local_assets_are_served() -> None:
    page = client.get("/dashboard/")
    assert page.status_code == 200
    assert '/dashboard/dashboard.css' in page.text
    assert '/dashboard/dashboard.js' in page.text
    css = client.get("/dashboard/dashboard.css")
    javascript = client.get("/dashboard/dashboard.js")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    assert javascript.status_code == 200 and javascript.headers["content-type"].startswith("text/javascript")
    assert "body{" in css.text
    assert '"/api/plans"' in javascript.text
    assert client.get("/dashboard").status_code == 200


def test_bulk_reports_uses_the_real_validator() -> None:
    now = datetime.now(timezone.utc).isoformat()
    response = client.post("/api/reports/bulk", json=[
        {"id": "invalid-location", "lat": 95, "lon": -1.5, "size": "moyen", "reported_at": now},
        {"id": "needs-review", "lat": 12.37, "lon": -1.52, "size": "moyen", "reported_at": now},
    ])
    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["reason_code"] for item in results] == ["POSITION_INVALIDE", "PHOTO_ABSENTE"]
    assert response.json()["stats"]["total"] == 1

    bad_body = client.post("/api/reports/bulk", json={"reports": []})
    assert bad_body.status_code == 400


def test_planner_adapter_maps_member_b_report_values() -> None:
    report = {
        "id": "accepted-report",
        "lat": 12.37,
        "lon": -1.52,
        "size": "moyen",
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "photo_b64": base64.b64encode(b"synthetic-photo").decode("ascii"),
        "accuracy_m": 10,
    }
    submitted = V.submit(report)
    assert submitted["status"] == "accepte"

    planner_report = main._planner_reports()[0]

    assert planner_report["status"] == "accepted"
    assert planner_report["size"] == "medium"
    assert planner_report["reported_at"] == report["reported_at"]


def test_plans_with_same_timestamp_are_both_retrievable() -> None:
    first = main._save_plan({"plan_id": "p_same", "totals": {}})
    second = main._save_plan({"plan_id": "p_same", "totals": {}})

    assert first["plan_id"] == "p_same"
    assert second["plan_id"] == "p_same_2"
    assert client.get("/api/plans/p_same").status_code == 200
    assert client.get("/api/plans/p_same_2").status_code == 200


def test_dashboard_plan_simulation_and_export_workflow() -> None:
    assert client.get("/api/reports?limit=1").status_code == 200
    response = client.post("/api/plans", json={"params": {}})
    assert response.status_code == 200
    plan = response.json()
    assert {"plan_id", "params_used", "collection_points", "routes", "checks", "totals"} <= plan.keys()

    fetched = client.get(f"/api/plans/{plan['plan_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == plan

    simulation = client.post(f"/api/plans/{plan['plan_id']}/simulation", json={"days": 2})
    assert simulation.status_code == 200
    assert simulation.json()["plan_id"] == plan["plan_id"]
    assert simulation.json()["days"] == 2
    assert simulation.json()["data_tag"] == "simulated"

    exported = client.get(f"/api/plans/{plan['plan_id']}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/geo+json")
    assert exported.json()["type"] == "FeatureCollection"

    assert client.get("/api/plans/missing").status_code == 404
    assert client.post("/api/plans/missing/simulation", json={"days": 1}).status_code == 404


def test_plan_api_rejects_malformed_parameters() -> None:
    response = client.post("/api/plans", json={"params": []})
    assert response.status_code == 400
