"""API de signalement. Lancer : uvicorn api.main:app --host 0.0.0.0 --port 8000"""
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.validation.rules import Validator

app = FastAPI(title="Ouaga Assainissement - API signalements", version="0.1")
V = Validator(os.environ.get("COMMUNE_CONFIG", "config/commune_config.json"))


@app.get("/api/health")
def health():
    return {"ok": True, "reports": V.stats()["total"]}


@app.post("/api/reports")
async def post_report(request: Request):
    try:
        raw = await request.json()
    except Exception:
        return V._result(None, "rejete", "FORMAT_INVALIDE")
    return V.submit(raw)  # toujours HTTP 200 avec statut + motif


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


@app.post("/api/admin/reset")
def reset():
    V.reset()
    return {"reset": True}


@app.get("/")
def root():
    return RedirectResponse("/citizen/")


app.mount("/citizen", StaticFiles(directory="web/citizen", html=True), name="citizen")
