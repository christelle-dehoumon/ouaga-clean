"""Smoke test de l'API : /api/health et /api/config répondent."""

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True and data["simulation"].startswith("mesa ") and data["network_nodes"] > 0


def test_config_exposes_bounds_and_center(client: TestClient) -> None:
    data = client.get("/api/config").json()
    assert len(data["center"]) == 2 and data["zoom"]
    pop = data["params"]["population"]
    assert pop["min"] < pop["default"] < pop["max"] and pop["unit"] and pop["label"]


def test_unknown_route_and_errors_are_french_json(client: TestClient) -> None:
    r = client.get("/api/nexiste-pas")
    assert r.status_code == 404 and r.json() == {"detail": "Ressource introuvable."}
