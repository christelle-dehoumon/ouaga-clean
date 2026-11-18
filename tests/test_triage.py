"""Tri automatique : écartés avec motif, alertes sans décision, doublons renforcés, réponse opaque, isolation sim/réel."""

from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from shapely.geometry import shape

from tests.conftest import BRIGADE, MAIRIE
from tests.test_lifecycle import CENTER, photo

NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def ok(client: TestClient, body: Any, **kw: Any) -> None:
    """Tout envoi citoyen : HTTP 200 {"ok": true}, rien d'autre."""
    r = client.post("/api/reports", **({"content": body} if isinstance(body, (bytes, str)) else {"json": body}), **kw)
    assert r.status_code == 200 and r.json() == {"ok": True}, r.text


def good(**extra: Any) -> dict[str, Any]:
    return {"lat": CENTER[0], "lon": CENTER[1], "reported_at": NOW(), "photo_b64": photo(extra.pop("seed", 0)), **extra}


def test_sixteen_traps_never_crash_and_are_logged(client: TestClient) -> None:
    """16 envois piégés : 200 {ok:true} partout, écartés visibles de la mairie avec motif, aucun cas créé."""
    traps: list[Any] = [
        b"{pas du json", b"", "[]", b"null", json.dumps("texte"),
        {**good(), "lat": "12.37"}, {**good(), "lat": None}, b'{"lat": NaN, "lon": -1.53}',
        {**good(), "lat": 95}, {**good(), "lat": 11.18, "lon": -4.29},                   # Bobo-Dioulasso : hors ville
        {**good(), "reported_at": "2099-01-01T00:00:00Z"}, {**good(), "reported_at": "hier"},
        {**good(), "reported_at": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()},
        {**good(), "photo_b64": "@@@pas-du-base64"}, {**good(), "photo_b64": base64.b64encode(b"pas une image").decode()},
        {k: v for k, v in good().items() if k != "photo_b64"},
    ]
    assert len(traps) == 16
    for t in traps:
        ok(client, t)
    ecartes = client.get("/api/ecartes", headers=MAIRIE).json()
    codes = [e["motif_code"] for e in ecartes]
    assert len(ecartes) == 16 and all(e["motif"] for e in ecartes)
    assert {"FORMAT_INVALIDE", "POSITION_INVALIDE", "HORS_VILLE", "DATE_FUTURE", "DATE_INVALIDE",
            "DATE_TROP_ANCIENNE", "PHOTO_INVALIDE", "PHOTO_ABSENTE"} <= set(codes)
    assert client.get("/api/reports", headers=MAIRIE).json() == []
    assert all("photo_b64\": {" in e["payload_resume"] or "photo_b64" not in e["payload_resume"] for e in ecartes)


def test_extra_fields_and_size_are_ignored(client: TestClient) -> None:
    ok(client, {**good(), "size": "enorme", "champ_inconnu": [1, 2, 3]})
    assert len(client.get("/api/reports", headers=MAIRIE).json()) == 1


def test_oversized_body_is_set_aside(client: TestClient) -> None:
    ok(client, b'{"photo_b64": "' + b"A" * 9_000_000 + b'"}')
    assert [e["motif_code"] for e in client.get("/api/ecartes", headers=MAIRIE).json()] == ["TROP_VOLUMINEUX"]


def test_same_answer_for_valid_and_set_aside(client: TestClient) -> None:
    a = client.post("/api/reports", json=good())
    b = client.post("/api/reports", content=b"{pas du json")
    assert (a.status_code, a.content, a.headers["content-type"]) == (b.status_code, b.content, b.headers["content-type"])


def test_duplicate_reinforces_existing_case(client: TestClient) -> None:
    """Moins de 30 m et 48 h : pas de nouveau point, nb_signalements + 1, alerte, historique « renforce »."""
    ok(client, good(seed=1))
    ok(client, good(seed=2, lat=CENTER[0] + 0.0001))        # ~11 m
    cases = client.get("/api/reports", headers=BRIGADE).json()
    assert len(cases) == 1 and cases[0]["nb_signalements"] == 2 and "DOUBLON_PROBABLE" in cases[0]["alertes"]
    history = client.get(f"/api/reports/{cases[0]['id']}/history", headers=BRIGADE).json()
    assert [h["action"] for h in history] == ["creation", "renforce"]
    ok(client, good(seed=3, lat=CENTER[0] + 0.001))         # ~110 m : nouveau cas
    assert len(client.get("/api/reports", headers=BRIGADE).json()) == 2


def test_repeated_photo_is_an_alert_not_a_rejection(client: TestClient) -> None:
    ok(client, good(seed=5))
    ok(client, good(seed=5, lat=CENTER[0] + 0.01))          # même photo, ailleurs
    cases = client.get("/api/reports", headers=BRIGADE).json()
    assert len(cases) == 2 and sum("PHOTO_DEJA_VUE" in c["alertes"] for c in cases) == 1
    assert all(c["statut"] == "a_verifier" for c in cases)   # transmis à la brigade, jamais rejeté par le système


def test_sector_water_and_gps_alerts(client: TestClient) -> None:
    root = Path(__file__).resolve().parents[1]
    water = json.loads((root / "data" / "water_bodies.geojson").read_text(encoding="utf-8"))
    from core.config import get_config
    from core.geo.territories import commune_polygon

    commune, _ = commune_polygon(get_config())
    lakes = [shape(f["geometry"]) for f in water["features"]]
    lake = max((g for g in lakes if commune.covers(g.representative_point())), key=lambda g: g.area).representative_point()
    ok(client, good(seed=7, lat=lake.y, lon=lake.x))                       # barrage dans la ville
    ok(client, good(seed=8, lat=CENTER[0] + 0.005, accuracy_m=500))
    ok(client, good(seed=9, lat=12.300, lon=-1.500))                        # Ouaga 2000 : dans la ville, hors secteur
    alerts = {tuple(sorted(c["alertes"])) for c in client.get("/api/reports", headers=BRIGADE).json()}
    assert any("PRES_PLAN_EAU" in a for a in alerts) and any("GPS_IMPRECIS" in a for a in alerts)
    assert any("HORS_SECTEUR" in a for a in alerts)
    assert all(c["statut"] == "a_verifier" for c in client.get("/api/reports", headers=BRIGADE).json())


def test_set_aside_can_be_put_back_by_city_hall(client: TestClient) -> None:
    ok(client, {**good(), "reported_at": "2099-01-01T00:00:00Z"})
    ecarte = client.get("/api/ecartes", headers=MAIRIE).json()[0]
    r = client.post(f"/api/ecartes/{ecarte['id']}/reset", headers=MAIRIE)
    assert r.status_code == 200 and r.json()["cas"]["statut"] == "a_verifier"
    assert client.post(f"/api/ecartes/{ecarte['id']}/reset", headers=MAIRIE).status_code == 409
    assert client.get("/api/ecartes", headers=MAIRIE).json() == []


def test_sim_cases_never_reach_reel(client: TestClient, tmp_path: Path) -> None:
    """Un cas simulé va dans sim.db ; il n'apparaît jamais en mode réel ni dans l'export réel."""
    assert client.post("/api/reports?mode=sim", json=good(seed=11)).status_code == 401
    ok(client, good(seed=11), params={"mode": "sim"}, headers=MAIRIE)
    ok(client, good(seed=12, lat=CENTER[0] + 0.02))
    reel = client.get("/api/reports?mode=reel", headers=MAIRIE).json()
    sim = client.get("/api/reports?mode=sim", headers=MAIRIE).json()
    assert [c["source"] for c in reel] == ["reel"] and [c["source"] for c in sim] == ["sim"]
    rows = sqlite3.connect(tmp_path / "reel.db").execute("SELECT COUNT(*) FROM reports WHERE source='sim'").fetchone()
    assert rows == (0,)
    rid = sim[0]["id"]
    client.post(f"/api/reports/{rid}/decision?mode=sim", json={"action": "confirmer"}, headers=BRIGADE)
    export = client.get("/api/export/reports.geojson", headers=MAIRIE).json()
    assert export["features"] == [] and export["license"].startswith("ODbL")


def test_export_contains_only_confirmed_real_cases(client: TestClient) -> None:
    ok(client, good(seed=21))
    ok(client, good(seed=22, lat=CENTER[0] + 0.02))
    a, b = (c["id"] for c in client.get("/api/reports", headers=BRIGADE).json())
    client.post(f"/api/reports/{a}/decision", json={"action": "confirmer"}, headers=BRIGADE)
    fc = client.get("/api/export/reports.geojson", headers=MAIRIE).json()
    assert [f["properties"]["id"] for f in fc["features"]] == [a]
    props = fc["features"][0]["properties"]
    assert set(props) == {"id", "type", "statut", "date", "nb_signalements"}      # ni photo ni donnée personnelle
    osm = client.get("/api/export/reports.osm", headers=MAIRIE).text
    assert "upload='never'" in osm and osm.count("<node") == 1


def test_burst_of_200_reports(client: TestClient) -> None:
    """200 envois en rafale (valides, doublons, piégés) : aucune erreur, aucun envoi perdu."""
    for i in range(200):
        body = good(seed=100 + i, lat=CENTER[0] + (i % 50) * 0.001) if i % 4 else b"{casse"
        ok(client, body)
    cases = client.get("/api/reports?limit=5000", headers=MAIRIE).json()
    ecartes = client.get("/api/ecartes", headers=MAIRIE).json()
    assert len(ecartes) == 50
    assert sum(c["nb_signalements"] for c in cases) == 150
