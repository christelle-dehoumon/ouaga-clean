"""Cycle de vie par l'API : 7 transitions valides, transitions interdites (409), rôles (401/403), historique."""

from __future__ import annotations

import base64
import io
import sqlite3
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.conftest import BRIGADE, MAIRIE

CENTER = (12.3672, -1.5337)


def photo(seed: int = 0) -> str:
    """Petite image JPEG unique (bruit) encodée en base64."""
    import cv2

    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)
    return base64.b64encode(cv2.imencode(".jpg", img)[1].tobytes()).decode()


def send(client: TestClient, lat: float = CENTER[0], lon: float = CENTER[1], seed: int = 0, **extra: Any) -> None:
    body = {"lat": lat, "lon": lon, "reported_at": datetime.now(timezone.utc).isoformat(), "photo_b64": photo(seed),
            **extra}
    r = client.post("/api/reports", json=body)
    assert r.status_code == 200 and r.json() == {"ok": True}


def only_case(client: TestClient) -> dict[str, Any]:
    cases = client.get("/api/reports", headers=MAIRIE).json()
    assert len(cases) == 1
    return cases[0]


def act(client: TestClient, rid: str, path: str, headers: dict[str, str], action: str | None = None) -> Any:
    body = {"action": action} if action else None
    return client.post(f"/api/reports/{rid}/{path}", json=body, headers=headers)


def test_full_cycle_and_history(client: TestClient) -> None:
    """Les 7 transitions valides, chacune écrite une fois dans l'historique."""
    send(client)
    case = only_case(client)
    assert (case["type"], case["statut"]) == ("depotoir", "a_verifier")
    rid = case["id"]
    steps = [("decision", BRIGADE, "rejeter", ("depotoir", "rejete")),                  # 2
             ("reset", MAIRIE, None, ("depotoir", "a_verifier")),                       # 6
             ("decision", BRIGADE, "confirmer", ("depotoir", "confirme")),              # 1
             ("mark-clean", MAIRIE, None, ("nettoyage", "a_verifier")),                 # 3
             ("decision", BRIGADE, "rejeter", ("nettoyage", "rejete")),                 # 5
             ("reset", MAIRIE, None, ("nettoyage", "a_verifier")),                      # 7
             ("decision", BRIGADE, "confirmer", ("nettoyage", "nettoye"))]              # 4
    for path, who, action, expected in steps:
        r = act(client, rid, path, who, action)
        assert r.status_code == 200, r.text
        assert (r.json()["type"], r.json()["statut"]) == expected
    history = client.get(f"/api/reports/{rid}/history", headers=MAIRIE).json()
    assert len(history) == 1 + len(steps)                       # création + une ligne par transition
    assert history[0]["qui"] == "citoyen" and [h["qui"] for h in history[1:]] == [s[1] is MAIRIE and "mairie" or "brigade"
                                                                                  for s in steps]
    assert all(h["quand"] for h in history)
    # nettoyé : absent des listes par défaut, jamais supprimé
    assert client.get("/api/reports", headers=MAIRIE).json() == []
    assert client.get("/api/reports?inclure_nettoyes=1", headers=MAIRIE).json()[0]["statut"] == "nettoye"


@pytest.mark.parametrize("path,who,action", [
    ("mark-clean", MAIRIE, None),          # à vérifier -> nettoyé : interdit
    ("reset", MAIRIE, None),               # à vérifier n'est pas rejeté
])
def test_forbidden_transitions_are_409(client: TestClient, path: str, who: dict[str, str], action: str | None) -> None:
    send(client)
    rid = only_case(client)["id"]
    r = act(client, rid, path, who, action)
    assert r.status_code == 409 and "impossible" in r.json()["detail"]


def test_replay_is_409_and_unknown_is_404(client: TestClient) -> None:
    send(client)
    rid = only_case(client)["id"]
    assert act(client, rid, "decision", BRIGADE, "confirmer").status_code == 200
    again = act(client, rid, "decision", BRIGADE, "confirmer")
    assert again.status_code == 409 and again.json()["detail"]
    assert act(client, "inconnu", "decision", BRIGADE, "confirmer").status_code == 404
    assert act(client, rid, "decision", BRIGADE, "valider").status_code == 422


def test_roles(client: TestClient) -> None:
    send(client)
    rid = only_case(client)["id"]
    assert act(client, rid, "decision", {}, "confirmer").status_code == 401
    assert act(client, rid, "decision", {"X-Role-Code": "devine"}, "confirmer").status_code == 401
    assert act(client, rid, "decision", MAIRIE, "confirmer").status_code == 403      # la mairie ne vérifie pas
    assert act(client, rid, "mark-clean", BRIGADE).status_code == 403                # la brigade ne nettoie pas
    assert client.get("/api/ecartes", headers=BRIGADE).status_code == 403
    assert client.post("/api/admin/reset", headers=BRIGADE).status_code == 403
    assert client.get("/api/reports").status_code == 401


def test_brigade_sees_only_to_verify(client: TestClient) -> None:
    send(client, seed=1)
    send(client, lat=CENTER[0] + 0.01, seed=2)
    a, b = (c["id"] for c in client.get("/api/reports", headers=BRIGADE).json())
    act(client, a, "decision", BRIGADE, "confirmer")
    seen = client.get("/api/reports", headers=BRIGADE).json()
    assert [c["id"] for c in seen] == [b] and all(c["statut"] == "a_verifier" for c in seen)
    assert {c["id"] for c in client.get("/api/reports?statut=confirme", headers=BRIGADE).json()} == {b}  # forcé
    act(client, a, "mark-clean", MAIRIE)
    types = {c["id"]: c["type"] for c in client.get("/api/reports", headers=BRIGADE).json()}
    assert types == {a: "nettoyage", b: "depotoir"}                                 # le type est visible


def test_history_is_one_row_per_transition_in_db(client: TestClient, tmp_path: Any) -> None:
    send(client)
    rid = only_case(client)["id"]
    act(client, rid, "decision", BRIGADE, "confirmer")
    act(client, rid, "decision", BRIGADE, "confirmer")       # rejoué : refusé, rien d'écrit
    conn = sqlite3.connect(tmp_path / "reel.db")
    rows = conn.execute("SELECT qui, de_statut, vers_statut FROM historique WHERE report_id=? ORDER BY id", (rid,)).fetchall()
    assert rows == [("citoyen", None, "a_verifier"), ("brigade", "a_verifier", "confirme")]


def test_photo_is_blurred_copy_and_served_to_staff(client: TestClient, tmp_path: Any) -> None:
    send(client, seed=9)
    case = only_case(client)
    assert client.get(case["photo_url"]).status_code == 401
    r = client.get(case["photo_url"], headers=BRIGADE)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    stored = list((tmp_path / "photos").rglob("*.jpg"))
    assert len(stored) == 1 and stored[0].read_bytes() != base64.b64decode(photo(9))   # jamais la photo brute
    assert io.BytesIO(r.content).getbuffer().nbytes > 0
