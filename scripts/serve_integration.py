"""Serveur de test intégré (sans modifier api/main.py de Jonathan).

Lance l'API de B telle quelle, ajoute les routes attendues par le tableau de
bord de C et sert /dashboard. Le plan affiché est le plan de référence mocké :
le moteur de A ne peut pas tourner sans scipy/osmnx dans cet environnement.
Rien n'est présenté comme un plan OSM réel.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.main import app, V
from core.sim.model import simuler

RACINE = Path(__file__).resolve().parents[1]
PLAN_SOURCE = json.loads((RACINE / "data" / "mock" / "plan_real.json").read_text(encoding="utf-8"))
CONFIG = json.loads((RACINE / "config" / "commune_config.json").read_text(encoding="utf-8"))
PLANS: dict[str, dict[str, Any]] = {}

STATUTS = {"accepte": "accepté", "rejete": "rejeté", "a_verifier": "à vérifier"}


def _signalement(ligne: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": ligne.get("id"),
        "lat": ligne.get("lat"),
        "lon": ligne.get("lon"),
        "statut": STATUTS.get(ligne.get("status"), ligne.get("status")),
        "motif_rejet": ligne.get("reason"),
        "adresse_texte": ligne.get("size", ""),
        "source": ligne.get("source"),
    }


@app.get("/api/signalements")
def signalements():
    return [_signalement(x) for x in V.list(limit=5000)]


@app.post("/api/signalements/bulk")
async def signalements_bulk(request: Request):
    try:
        lot = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalide"}, status_code=400)
    if not isinstance(lot, list):
        lot = [lot]
    resultats = [V.submit(x) for x in lot[:200]]
    stats = {"acceptés": 0, "rejetés": 0, "à vérifier": 0}
    for r in resultats:
        cle = STATUTS.get(r.get("status"), "rejeté")
        stats["acceptés" if cle == "accepté" else "rejetés" if cle == "rejeté" else "à vérifier"] += 1
    return {"stats": stats, "resultats": resultats}


def _plan_dashboard(parametres: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    plan = json.loads(json.dumps(source))  # copie profonde
    crises = [str(c) for c in (parametres.get("crises_actives") or [])]
    changements: list[dict[str, str]] = []
    points = {p["id"]: p for p in plan["collection_points"]}
    pertes_kg = 0.0
    t0 = time.perf_counter()

    if "panne_camions" in crises and plan.get("routes"):
        retiree = plan["routes"].pop()
        pertes_kg += float(retiree.get("load_kg", 0))
        changements.append({
            "quoi": "Camion en panne",
            "pourquoi": f"Tournée {retiree.get('vehicle', '?')} retirée du plan",
            "impact": f"{retiree.get('load_kg', 0):.0f} kg à reporter",
        })
    if "saison_pluies" in crises:
        gardees = []
        for r in plan.get("routes", []):
            if r.get("type") == "truck":
                gardees.append(r)
            else:
                pertes_kg += float(r.get("load_kg", 0))
        plan["routes"] = gardees
        changements.append({
            "quoi": "Saison des pluies",
            "pourquoi": "Pistes non revêtues retirées du réseau",
            "impact": "tricycles suspendus",
        })
    if "nouveau_quartier" in crises:
        nouveau = {
            "id": "q_saaba", "lat": 12.396, "lon": -1.489,
            "demand_kg": 900.0, "access": "truck", "territory_id": "saaba",
            "type": "center", "data_tag": "synthetic",
        }
        plan.setdefault("collection_points", []).append(nouveau)
        points[nouveau["id"]] = nouveau
        pertes_kg += nouveau["demand_kg"]
        changements.append({
            "quoi": "Nouveau quartier (Saaba)",
            "pourquoi": "Quartier ajouté au périmètre",
            "impact": "+900 kg/j de demande",
        })

    traces_truck: list[dict[str, Any]] = []
    traces_tri: list[dict[str, Any]] = []
    for route in plan.get("routes", []):
        coords = (route.get("geometry") or {}).get("coordinates") or []
        trace = [[lat, lon] for lon, lat in coords if isinstance(lon, (int, float)) and isinstance(lat, (int, float))]
        sortie = {
            "id": route.get("vehicle", "?"),
            "trace": trace,
            "distance_km": round(route.get("distance_km", 0), 1),
            "duree_h": round(route.get("duration_min", 0) / 60, 1),
            "charge_kg": route.get("load_kg", 0),
        }
        (traces_tri if route.get("type") == "tricycle" else traces_truck).append(sortie)

    totaux = dict(plan.get("totals", {}))
    # Les telles quelles du mock ne changeraient pas avec les crises : on recalcule
    # les trois indicateurs à partir des tournées réellement conservées.
    cout_fcfa = sum(float(r.get("cost", 0)) for r in plan.get("routes", []))
    budget_fcfa = float(CONFIG.get("params", {}).get("budget", 10_000_000))
    totaux["cost"] = cout_fcfa
    totaux["budget_remaining"] = max(0.0, budget_fcfa - cout_fcfa)
    totaux["uncollected_kg"] = float(totaux.get("uncollected_kg", 0)) + pertes_kg
    checks = plan.get("checks", {})
    return {
        "id": "p_" + uuid.uuid4().hex[:10],
        "plan_id": plan.get("plan_id"),
        "mode": "secours — plan de référence simulé (moteur A indisponible ici)",
        "duree_calcul_ms": round((time.perf_counter() - t0) * 1000, 2),
        "genere_le": plan.get("computed_at"),
        "points_regroupement": [
            {
                "id": p["id"], "lat": p["lat"], "lon": p["lon"],
                "quartier_id": p.get("territory_id", "?"),
                "capacite_t": round(p.get("demand_kg", 0) / 1000, 2),
            }
            for p in plan.get("collection_points", [])
        ],
        "tournees_camions": traces_truck,
        "tournees_tricycles": traces_tri,
        "points_non_desservis": plan.get("unserved", []),
        "changements": changements,
        "coherence": {
            "capacite_ok": bool(checks.get("capacity_ok", True)),
            "budget_ok": bool(checks.get("budget_ok", True)),
            "cout_annuel_m_fcfa": round(totaux.get("cost", 0) / 1_000_000, 3),
            "tonnes_rue_par_jour": round(totaux.get("uncollected_kg", 0) / 1000, 1),
            "budget_restant_m_fcfa": round(totaux.get("budget_remaining", 0) / 1_000_000, 3),
        },
        "warnings": [
            "Plan de démonstration issu de data/mock/plan_real.json, pas un calcul OSM en direct.",
            "Le géographe doit installer scipy/osmnx et finaliser le téléchargement de la zone pilote.",
        ],
        "parametres": parametres,
        "_source": plan,
    }


@app.post("/api/plan/calculer")
async def calculer_plan(request: Request):
    try:
        corps = await request.json()
    except Exception:
        corps = {}
    parametres = corps.get("parametres") if isinstance(corps, dict) else {}
    if not isinstance(parametres, dict):
        parametres = {}
    plan = _plan_dashboard(parametres, PLAN_SOURCE)
    PLANS[plan["id"]] = plan
    return plan


@app.post("/api/plans/{plan_id}/simuler")
def simuler_plan(plan_id: str):
    plan = PLANS.get(plan_id)
    if plan is None:
        return JSONResponse({"error": "plan introuvable"}, status_code=404)
    return simuler(plan.get("_source"), plan.get("parametres", {}), CONFIG, jours=7, seed=42)


@app.post("/api/scenarios/compare")
def comparer(a_id: str = "", b_id: str = ""):
    a, b = PLANS.get(a_id), PLANS.get(b_id)
    if a is None or b is None:
        return JSONResponse({"error": "scénario introuvable"}, status_code=404)
    ca = a["coherence"]["cout_annuel_m_fcfa"]
    cb = b["coherence"]["cout_annuel_m_fcfa"]
    ta = a["coherence"]["tonnes_rue_par_jour"]
    tb = b["coherence"]["tonnes_rue_par_jour"]
    return {"diff_cout": round(cb - ca, 3), "diff_tonnes": round(tb - ta, 1)}


@app.get("/api/exports/osm")
def export_osm():
    return {
        "fichier": "exports/depotoirs_verifies.osm",
        "nb_noeuds": 52,
        "message": "Export de démonstration — aucun envoi automatique vers OpenStreetMap.",
    }


app.mount("/dashboard", StaticFiles(directory=RACINE / "web" / "dashboard", html=True), name="dashboard")
