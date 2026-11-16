import base64, json, os, shutil
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

os.environ["REPORTS_DB"] = ":memory:"
from api.main import app, V  # noqa  # noqa

client = TestClient(app)
JPEG = base64.b64encode(b"\xff\xd8photo-1\xff\xd9").decode()
JPEG2 = base64.b64encode(b"\xff\xd8photo-2\xff\xd9").decode()
iso = lambda d=0: (datetime.now(timezone.utc) - timedelta(hours=d)).isoformat()


def rep(**kw):
    b = dict(lat=12.37, lon=-1.52, size="moyen", reported_at=iso(), photo_b64=JPEG, accuracy_m=10)
    b.update(kw); return b


@pytest.fixture(autouse=True)
def clean():
    V.reset(); V.water = []; yield


def post(b): return client.post("/api/reports", json=b).json()


def test_accepte():
    r = post(rep()); assert r["status"] == "accepte" and r["reason_code"] == "OK"


@pytest.mark.parametrize("bad,code", [
    (rep(lat="abc"), "POSITION_INVALIDE"), (rep(lat=None), "POSITION_INVALIDE"),
    (rep(lat=95), "POSITION_INVALIDE"),
    (rep(lat=True), "POSITION_INVALIDE"),
    (rep(size="énorme"), "TAILLE_INVALIDE"), (rep(reported_at="hier"), "DATE_INVALIDE"),
    (rep(reported_at=iso(-48)), "DATE_FUTURE"), (rep(reported_at=iso(24 * 90)), "DATE_TROP_ANCIENNE"),
    (rep(lat=48.85, lon=2.35), "HORS_ZONE"), (rep(photo_b64="!!pas-du-base64!!"), "PHOTO_INVALIDE"),
    (rep(photo_b64=12345), "PHOTO_INVALIDE"),
])
def test_rejets(bad, code):
    r = post(bad); assert r["status"] == "rejete" and r["reason_code"] == code and r["reason"]


@pytest.mark.parametrize("payload", [None, [], "texte", 42, {}, {"lat": {}, "lon": []}])
def test_entrees_absurdes_jamais_de_plantage(payload):
    r = client.post("/api/reports", json=payload); assert r.status_code == 200
    assert r.json()["status"] == "rejete" and r.json()["reason"]


def test_json_casse():
    r = client.post("/api/reports", content=b"{pas du json", headers={"Content-Type": "application/json"})
    assert r.status_code == 200 and r.json()["reason_code"] == "FORMAT_INVALIDE"


def test_doublon_renforce():
    a = post(rep())
    b = post(rep(lat=12.37010, photo_b64=JPEG2))  # ~11 m
    assert b["reason_code"] == "DOUBLON" and b["duplicate_of"] == a["id"]
    assert client.get(f"/api/reports/{a['id']}").json()["confirmations"] == 2


def test_pas_doublon_si_loin_ou_ancien():
    post(rep())
    assert post(rep(lat=12.3715, photo_b64=JPEG2))["status"] == "accepte"  # ~55 m
    post(rep(lat=12.40, photo_b64=JPEG2 + "AAAA"))
    assert post(rep(lat=12.40, reported_at=iso(72), photo_b64=base64.b64encode(b"x3").decode()))["status"] == "accepte"


def test_photo_deja_vue():
    post(rep()); r = post(rep(lat=12.40)); assert r["reason_code"] == "PHOTO_DEJA_VUE"


def test_a_verifier():
    assert post(rep(photo_b64=None))["status"] == "a_verifier"
    assert post(rep(lat=12.41, photo_b64=JPEG2, accuracy_m=500))["reason_code"] == "GPS_IMPRECIS"


def test_plan_d_eau():
    V.water = [[[[-1.521, 12.369], [-1.519, 12.369], [-1.519, 12.371], [-1.521, 12.371], [-1.521, 12.369]]]]
    assert post(rep())["reason_code"] == "PLAN_D_EAU"


def test_validation_manuelle_tracee():
    a = post(rep(photo_b64=None))
    assert client.post(f"/api/reports/{a['id']}/validate", json={"by": "agent1", "accept": True, "note": "vu sur place"}).json()["updated"]
    g = client.get(f"/api/reports/{a['id']}").json()
    assert g["status"] == "accepte" and g["validated_by"] == "agent1" and g["validated_at"]


def test_stats_et_reset():
    post(rep()); post(rep(lat=0)); s = client.get("/api/stats").json()
    assert s["total"] == 2 and s["par_statut"]["rejete"] == 1
    client.post("/api/admin/reset"); assert client.get("/api/stats").json()["total"] == 0


def test_nan_dans_le_json():
    r = client.post("/api/reports", content=b'{"lat": NaN, "lon": -1.5}', headers={"Content-Type": "application/json"}).json()
    assert r["reason_code"] == "POSITION_INVALIDE"
