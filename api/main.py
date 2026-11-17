"""API de signalement et intégration du plan de collecte."""

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.optim.plan import compute_plan
from core.sim.model import run_scenario
from core.validation.rules import Validator

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
CONFIG_PATH = Path(os.environ.get("COMMUNE_CONFIG", ROOT / "config" / "commune_config.json"))
if not CONFIG_PATH.is_absolute():
    CONFIG_PATH = ROOT / CONFIG_PATH
REPORTS_DB = os.environ.get("REPORTS_DB", str(ROOT / "data" / "reports.db"))

app = FastAPI(title="Ouaga Clean API", version="0.2")
V = Validator(str(CONFIG_PATH), db_path=REPORTS_DB, root=str(ROOT))
app.state.plans = {}

_SIZE_MAP = {"petit": "small", "moyen": "medium", "grand": "large",
             "small": "small", "medium": "medium", "large": "large"}
_STATUS_MAP = {"accepte": "accepted", "rejete": "rejected", "a_verifier": "to_review"}


def _planner_reports() -> list[dict[str, Any]]:
    """Convertit les enregistrements B vers les statuts et tailles du contrat partagé."""
    reports = []
    for row in V.list(limit=5000):
        reports.append({
            "id": row["id"],
            "lat": row["lat"],
            "lon": row["lon"],
            "size": _SIZE_MAP.get(row["size"], row["size"]),
            "status": _STATUS_MAP.get(row["status"], row["status"]),
            "reported_at": row["reported_at"],
            "source": "synthetic" if row["source"] == "simule" else "observed",
            "dumpsite_id": row["duplicate_of"],
        })
    return reports


def _save_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Garde plusieurs calculs même si leurs horodatages tombent dans la même seconde."""
    plan_id = plan["plan_id"]
    if plan_id in app.state.plans:
        suffix = 2
        while f"{plan_id}_{suffix}" in app.state.plans:
            suffix += 1
        plan_id = f"{plan_id}_{suffix}"
        plan["plan_id"] = plan_id
    app.state.plans[plan_id] = plan
    return plan


def _plan_features(plan: dict[str, Any]) -> dict[str, Any]:
    """Sérialise les points et géométries réellement présents dans un plan GeoJSON."""
    features = []
    for point in plan["collection_points"]:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [point["lon"], point["lat"]]},
            "properties": {
                "id": point["id"],
                "feature_type": point["type"],
                "demand_kg": point["demand_kg"],
                "data_tag": point["data_tag"],
            },
        })
    for route in plan["routes"]:
        geometry = route.get("geometry")
        if isinstance(geometry, dict):
            features.append({
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "vehicle": route["vehicle"],
                    "feature_type": "route",
                    "distance_km": route["distance_km"],
                    "load_kg": route["load_kg"],
                },
            })
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/health")
def health():
    return {"ok": True, "reports": V.stats()["total"]}


@app.post("/api/reports")
async def post_report(request: Request):
    try:
        raw = await request.json()
    except Exception:
        return V._result(None, "rejete", "FORMAT_INVALIDE")
    return V.submit(raw)


@app.post("/api/reports/bulk")
async def post_reports_bulk(request: Request):
    try:
        raw = await request.json()
    except Exception:
        return JSONResponse({"error": "Le corps doit contenir un tableau JSON."}, status_code=400)
    if not isinstance(raw, list):
        return JSONResponse({"error": "Le corps doit contenir un tableau JSON."}, status_code=400)
    return {"results": [V.submit(item) for item in raw], "stats": V.stats()}


@app.get("/api/reports")
def list_reports(status: str | None = None, limit: int = 1000):
    return V.list(status, min(max(limit, 1), 5000))


@app.get("/api/reports/{rid}")
def get_report(rid: str):
    r = V.get(rid)
    return r or JSONResponse({"error": "introuvable"}, status_code=404)


@app.post("/api/reports/{rid}/validate")
async def validate(rid: str, request: Request):
    try:
        b = await request.json()
        ok = V.validate_manually(rid, str(b.get("by", "?")), bool(b.get("accept")), str(b.get("note", "")))
    except Exception:
        return JSONResponse({"error": "requête invalide"}, status_code=400)
    return {"updated": ok}


@app.get("/api/stats")
def stats():
    return V.stats()


@app.post("/api/plans")
async def create_plan(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Le corps doit être un objet JSON avec params."}, status_code=400)
    if not isinstance(body, dict) or not isinstance(body.get("params", {}), dict):
        return JSONResponse({"error": "params doit être un objet JSON."}, status_code=400)

    plan = compute_plan(body.get("params", {}), _planner_reports())
    return _save_plan(plan)


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str):
    plan = app.state.plans.get(plan_id)
    return plan if plan is not None else JSONResponse({"error": "plan introuvable"}, status_code=404)


@app.post("/api/plans/{plan_id}/simulation")
async def simulate_plan(plan_id: str, request: Request):
    plan = app.state.plans.get(plan_id)
    if plan is None:
        return JSONResponse({"error": "plan introuvable"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Le corps doit contenir days."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Le corps doit contenir days."}, status_code=400)
    result = run_scenario(plan["params_used"], plan, body.get("days", 7))
    if "error" in result:
        return JSONResponse(result, status_code=422)
    return result


@app.get("/api/plans/{plan_id}/export")
def export_plan(plan_id: str):
    plan = app.state.plans.get(plan_id)
    if plan is None:
        return JSONResponse({"error": "plan introuvable"}, status_code=404)
    return JSONResponse(
        _plan_features(plan),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="plan-{plan_id}.geojson"'},
    )


@app.post("/api/admin/reset")
def reset():
    V.reset()
    return {"reset": True}


@app.get("/")
def root():
    return RedirectResponse("/citizen/")


@app.get("/dashboard", include_in_schema=False)
def dashboard_redirect():
    return RedirectResponse("/dashboard/")


app.mount("/citizen", StaticFiles(directory=str(WEB_ROOT / "citizen"), html=True), name="citizen")
app.mount("/dashboard", StaticFiles(directory=str(WEB_ROOT / "dashboard"), html=True), name="dashboard")
