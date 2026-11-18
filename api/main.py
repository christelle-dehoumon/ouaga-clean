"""API Ouaga Clean : signalements (cycle de vie), plan de gestion, simulation, exports.

Toutes les erreurs sont du JSON {"detail": "..."} en français, jamais une trace Python.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import plans, reports
from core.config import config_path, get_config, section
from core.geo.territories import sector_polygon
from core.sim.model import MOTEUR

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
LOG = logging.getLogger("ouaga")

app = FastAPI(title="Ouaga Clean API", version="1.0")

STATUS_TEXT = {400: "Requête invalide.", 401: "Code d'accès manquant ou incorrect.", 403: "Action non autorisée.",
               404: "Ressource introuvable.", 405: "Méthode non autorisée pour ce chemin.", 409: "Conflit.",
               413: "Requête trop volumineuse.", 422: "Données invalides."}


@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Erreurs HTTP en français (y compris les 404 et 405 de routage)."""
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail not in ("Not Found", "Method Not Allowed") \
        else STATUS_TEXT.get(exc.status_code, "Erreur.")
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Corps ou paramètres illisibles : 422 avec un message court, sans trace."""
    where = ", ".join(".".join(str(x) for x in e.get("loc", [])) for e in exc.errors()[:3])
    return JSONResponse({"detail": f"Données invalides ({where})." if where else "Données invalides."}, status_code=422)


@app.exception_handler(Exception)
async def internal_error(_request: Request, exc: Exception) -> JSONResponse:
    """Dernier filet : aucune exception non gérée ne sort en trace Python."""
    LOG.exception("Erreur interne : %s", exc)
    return JSONResponse({"detail": "Erreur interne du serveur : l'opération n'a pas été faite."}, status_code=500)


app.include_router(plans.router)
app.include_router(reports.router)


@app.get("/api/health")
def health() -> dict[str, Any]:
    """État du service."""
    from core.optim.plan import default_network

    net = default_network()
    return {"ok": True, "commune": get_config().get("commune"), "config": config_path().name,
            "simulation": MOTEUR, "network_nodes": net.views["truck_dry"].n_nodes,
            "network_warnings": net.warnings}


@app.get("/api/config")
def public_config() -> dict[str, Any]:
    """Centre de carte, zoom et paramètres réglables {min, max, default, unit, label} pour le front."""
    cfg = get_config()
    view = section(cfg, "map")
    center = view.get("center")
    if not (isinstance(center, list) and len(center) == 2):
        sector = sector_polygon(cfg)
        center = [round(sector.centroid.y, 6), round(sector.centroid.x, 6)] if sector is not None else None
    defaults = section(cfg, "params")
    params = {k: {"min": v.get("min"), "max": v.get("max"), "default": defaults.get(k), "unit": v.get("unit"),
                  "label": v.get("label")} for k, v in section(cfg, "bounds").items() if isinstance(v, dict)}
    return {"commune": cfg.get("commune"), "center": center, "zoom": view.get("zoom"), "params": params,
            "modes": ["reel", "sim"], "territories": plans.list_territories(cfg),
            "attribution": "© OpenStreetMap contributors"}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/citizen/")


@app.get("/dashboard", include_in_schema=False)
def dashboard_redirect() -> RedirectResponse:
    return RedirectResponse("/dashboard/")


for _name in ("citizen", "brigade", "dashboard"):
    if (WEB_ROOT / _name).is_dir():
        app.mount(f"/{_name}", StaticFiles(directory=str(WEB_ROOT / _name), html=True), name=_name)
