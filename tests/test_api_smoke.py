"""Smoke test de l'API — vérifie que /api/health répond correctement."""
import os

os.environ["REPORTS_DB"] = ":memory:"

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert isinstance(data["reports"], int)
