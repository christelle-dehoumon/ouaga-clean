"""Fixtures communes : bases reel.db et sim.db temporaires (jamais celles du dépôt) et client de l'API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BRIGADE = {"X-Role-Code": "brigade-test"}
MAIRIE = {"X-Role-Code": "mairie-test"}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """API sur deux bases vides propres au test, codes de rôle de test."""
    monkeypatch.setenv("REEL_DB", str(tmp_path / "reel.db"))
    monkeypatch.setenv("SIM_DB", str(tmp_path / "sim.db"))
    monkeypatch.setenv("PHOTO_DIR", str(tmp_path / "photos"))
    monkeypatch.setenv("BRIGADE_CODE", BRIGADE["X-Role-Code"])
    monkeypatch.setenv("MAIRIE_CODE", MAIRIE["X-Role-Code"])
    from api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
