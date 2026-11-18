"""Réglages par commune : COMMUNE_CONFIG=config/commune_config.koudougou.json change le comportement sans code."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import MAIRIE
from tests.test_lifecycle import photo


@pytest.fixture()
def koudougou(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("COMMUNE_CONFIG", "config/commune_config.koudougou.json")
    return client


def test_center_and_params_come_from_config(client: TestClient, koudougou: TestClient) -> None:
    cfg = koudougou.get("/api/config").json()
    assert cfg["commune"] == "Koudougou" and cfg["center"] == [12.2526, -2.3627]
    assert cfg["params"]["population"]["default"] == 160_000 and cfg["params"]["trucks"]["default"] == 3


def test_missing_road_data_falls_back_and_says_so(koudougou: TestClient) -> None:
    plan = koudougou.post("/api/plans", json={}, headers=MAIRIE).json()
    assert plan["mode"] == "secours" and plan["checks"]["ok"] is False
    assert any("Réseau routier introuvable" in w for w in plan["warnings"])
    assert any("Aucun réseau routier" in m for m in plan["checks"]["messages"])


def test_triage_uses_the_commune_area(koudougou: TestClient) -> None:
    ouaga = {"lat": 12.3672, "lon": -1.5337, "photo_b64": photo(1)}
    koud = {"lat": 12.2526, "lon": -2.3627, "photo_b64": photo(2)}
    for body in (ouaga, koud):
        assert koudougou.post("/api/reports", json=body).json() == {"ok": True}
    assert [e["motif_code"] for e in koudougou.get("/api/ecartes", headers=MAIRIE).json()] == ["HORS_VILLE"]
    cases = koudougou.get("/api/reports", headers=MAIRIE).json()
    assert len(cases) == 1 and cases[0]["lon"] == pytest.approx(-2.3627)
