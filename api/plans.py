"""Routes du plan de gestion : calcul avec événements, simulation, scénarios, quartiers, actions de simulation."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from api.roles import require
from core.config import get_config, section
from core.db import get_db, load_plan, now, save_plan
from core.optim.events import EventError, list_territories, plan_with_events
from core.sim.model import run_scenario

router = APIRouter(prefix="/api")
MAIRIE = Depends(require("mairie"))
MODE_LABEL = {"optimized": "complet", "partial": "partiel", "fallback": "secours"}


def _mode(value: Any) -> str:
    """Mode reel ou sim ; 422 sinon."""
    if value not in ("reel", "sim"):
        raise HTTPException(422, "mode doit valoir « reel » ou « sim ».")
    return value


def planner_reports(mode: str) -> list[dict[str, Any]]:
    """Dépotoirs qui alimentent le plan : cas confirmés par la brigade (type depotoir) de la base du mode ; en mode sim,
    aussi les dépotoirs fictifs ajoutés par la mairie. Le mode sim ne lit jamais reel.db, et inversement."""
    size = str(section(get_config(), "model").get("dumpsite_default_size") or "medium")
    conn = get_db(mode)
    try:
        rows = conn.execute("SELECT id, lat, lon, reported_at, nb_signalements FROM reports "
                            "WHERE statut='confirme' AND type='depotoir'").fetchall()
        out = [{"id": r["id"], "lat": r["lat"], "lon": r["lon"], "size": size, "status": "confirme",
                "reported_at": r["reported_at"], "report_count": r["nb_signalements"],
                "source": "synthetic" if mode == "sim" else "observed"} for r in rows]
        if mode == "sim":
            out += [{"id": r["id"], "lat": r["lat"], "lon": r["lon"], "status": "active", "estimated_kg": r["kg"],
                     "source": "synthetic"} for r in conn.execute("SELECT * FROM sim_dumpsites").fetchall()]
        return out
    finally:
        conn.close()


def _sim_cuts() -> list[dict[str, Any]]:
    """Routes coupées à la main par la mairie en simulation (sim.db)."""
    conn = get_db("sim")
    try:
        return [{"edge_id": r["edge_id"]} for r in conn.execute("SELECT edge_id FROM road_cuts").fetchall()]
    finally:
        conn.close()


def present(plan: dict[str, Any], mode: str) -> dict[str, Any]:
    """Plan au format du contrat : mode complet|partiel|secours, véhicules, tracés lat/lon par véhicule."""
    out = dict(plan)
    out["engine_mode"] = plan.get("mode")
    out["mode"] = MODE_LABEL.get(plan.get("mode"), "secours")
    out["data_mode"] = mode
    out["data_tag"] = "simulated" if mode == "sim" else "observed"
    out["consolidation_points"] = plan.get("collection_points", [])
    routes = []
    for r in plan.get("routes", []):
        geom = r.get("geometry") or {}
        coords = geom.get("coordinates") if isinstance(geom, dict) else None
        routes.append({**r, "vehicle_id": r.get("vehicle"),
                       "path": [[c[1], c[0]] for c in coords] if isinstance(coords, list) else []})
    out["routes"] = routes
    params = plan.get("params_used") or {}
    broken = set(params.get("broken_trucks") or [])
    out["vehicles"] = [{"id": f"truck{i}", "type": "truck", "status": "en panne" if f"truck{i}" in broken else "en service",
                        "trips": [r["vehicle"] for r in routes if r["vehicle"].split("_trip")[0] == f"truck{i}"]}
                       for i in range(1, int(params.get("trucks") or 0) + 1)]
    return out


def _record(mode: str, plan: dict[str, Any], label: str | None, sim: dict[str, Any] | None = None) -> dict[str, Any]:
    """Historique : chaque calcul enregistré avec paramètres, événements, résultats, durée, mode, horodatage."""
    results = {"cout_fcfa": plan["totals"].get("cost"), "non_servis": plan["checks"].get("unserved_count"),
               "reportes": plan["checks"].get("postponed_count", 0), "points": len(plan.get("collection_points", [])),
               "unserved_ratio": plan["checks"].get("unserved_ratio"), "checks_ok": plan["checks"].get("ok"),
               "kg_collectes_plan": plan["totals"].get("collected_kg"), "mode_plan": plan.get("mode"),
               "compute_ms": plan.get("compute_ms")}
    if sim and "error" not in sim:
        results.update({"part_ramassee": sim["part_ramassee"], "cout_sim_fcfa": sim["cout_fcfa"],
                        "depotoirs_restants": sim["depotoirs_restants"], "jours_simules": sim["jours"]})
    row = {"id": f"s_{plan['plan_id']}", "created_at": now(), "plan_id": plan["plan_id"], "label": label,
           "params": plan.get("params_used", {}), "events": plan.get("events", []), "results": results,
           "compute_ms": plan.get("compute_ms"), "mode": mode}
    conn = get_db(mode)
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO scenarios(id, created_at, plan_id, label, params, events, results, "
                         "compute_ms, mode) VALUES(?,?,?,?,?,?,?,?,?)",
                         (row["id"], row["created_at"], row["plan_id"], label, json.dumps(row["params"]),
                          json.dumps(row["events"]), json.dumps(results), row["compute_ms"], mode))
    finally:
        conn.close()
    return row


def compute(body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Calcule, enregistre et présente un plan à partir du corps de POST /api/plans."""
    if not isinstance(body, dict):
        raise HTTPException(422, "Le corps doit être un objet JSON.")
    mode = _mode(body.get("mode", "reel"))
    params = body.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(422, "params doit être un objet JSON.")
    previous = None
    if body.get("previous_plan_id"):
        found = load_plan(str(body["previous_plan_id"]))
        if found is None:
            raise HTTPException(404, f"Plan précédent « {body['previous_plan_id']} » introuvable.")
        previous = found[1]
    cuts = body.get("cut_roads") or []
    if not isinstance(cuts, list):
        raise HTTPException(422, "cut_roads doit être une liste.")
    if mode == "sim":
        cuts = [*_sim_cuts(), *cuts]
    try:
        plan = plan_with_events(params, planner_reports(mode), body.get("events"), cuts, previous)
    except EventError as exc:
        raise HTTPException(422, str(exc)) from exc
    plan.pop("_internal", None)
    save_plan(mode, plan)
    _record(mode, plan, body.get("label"))
    return mode, present(plan, mode)


@router.post("/plans")
def create_plan(body: Any = Body(default=None), _role: str = MAIRIE) -> dict[str, Any]:
    """Calcul (complet ou partiel) avec événements ; enregistré dans la base du mode."""
    return compute(body or {})[1]


@router.get("/plans/{plan_id}")
def get_plan(plan_id: str, _role: str = MAIRIE) -> dict[str, Any]:
    """Plan enregistré (survit au redémarrage)."""
    found = load_plan(plan_id)
    if found is None:
        raise HTTPException(404, f"Plan « {plan_id} » introuvable.")
    return present(*reversed(found))


def _sim_dumpsites() -> list[dict[str, Any]]:
    """Dépotoirs fictifs de sim.db."""
    conn = get_db("sim")
    try:
        return [dict(r) for r in conn.execute("SELECT id, lat, lon, kg FROM sim_dumpsites").fetchall()]
    finally:
        conn.close()


@router.post("/plans/{plan_id}/simulation")
def simulate(plan_id: str, body: Any = Body(default=None), _role: str = MAIRIE) -> dict[str, Any]:
    """Simulation multi-agents du plan ; ne lit jamais reel.db (dépotoirs fictifs pris dans sim.db seulement)."""
    found = load_plan(plan_id)
    if found is None:
        raise HTTPException(404, f"Plan « {plan_id} » introuvable.")
    mode, plan = found
    body = body if isinstance(body, dict) else {}
    days = body.get("days", 7)
    result = run_scenario(body.get("params") or {}, plan, days, body.get("actors_enabled"), body.get("seed", 0),
                          _sim_dumpsites())
    if "error" in result:
        raise HTTPException(422, result["error"])
    _record(mode, plan, None, result)
    return result


@router.get("/plans/{plan_id}/export")
def export_plan(plan_id: str, _role: str = MAIRIE) -> JSONResponse:
    """Plan en GeoJSON (points et tournées), fichier à télécharger."""
    found = load_plan(plan_id)
    if found is None:
        raise HTTPException(404, f"Plan « {plan_id} » introuvable.")
    mode, plan = found
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
              "properties": {"id": p["id"], "feature_type": p["type"], "demand_kg": p["demand_kg"],
                             "data_tag": p.get("data_tag")}} for p in plan["collection_points"]]
    feats += [{"type": "Feature", "geometry": r["geometry"], "properties": {
        "vehicle": r["vehicle"], "feature_type": "route", "distance_km": r["distance_km"], "load_kg": r["load_kg"]}}
        for r in plan["routes"] if isinstance(r.get("geometry"), dict)]
    fc = {"type": "FeatureCollection", "name": f"plan {plan_id}", "data_mode": mode,
          "license": "ODbL-1.0 (réseau et bâtiments dérivés d'OpenStreetMap)",
          "attribution": "© contributeurs OpenStreetMap", "features": feats}
    return JSONResponse(fc, media_type="application/geo+json",
                        headers={"Content-Disposition": f'attachment; filename="plan-{plan_id}.geojson"'})


@router.get("/territories")
def territories() -> list[dict[str, Any]]:
    """Quartiers proposés pour l'événement new_district."""
    return list_territories()


def _scenarios() -> list[dict[str, Any]]:
    """Scénarios des deux bases, du plus récent au plus ancien (deux lectures séparées, aucune jointure)."""
    rows = []
    for mode in ("reel", "sim"):
        conn = get_db(mode)
        try:
            for r in conn.execute("SELECT * FROM scenarios").fetchall():
                rows.append({**dict(r), "params": json.loads(r["params"]), "events": json.loads(r["events"]),
                             "results": json.loads(r["results"])})
        finally:
            conn.close()
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


@router.get("/scenarios")
def list_scenarios(_role: str = MAIRIE) -> list[dict[str, Any]]:
    """Historique des calculs."""
    return _scenarios()


@router.post("/scenarios")
def create_scenario(body: Any = Body(default=None), _role: str = MAIRIE) -> dict[str, Any]:
    """Scénario = plan (avec événements) puis simulation de `days` jours, enregistrés ensemble."""
    body = body if isinstance(body, dict) else {}
    t0 = time.perf_counter()
    mode, plan = compute(body)
    found = load_plan(plan["plan_id"])
    sim = run_scenario({}, found[1], body.get("days", 7), body.get("actors_enabled"), body.get("seed", 0),
                       _sim_dumpsites())
    if "error" in sim:
        raise HTTPException(422, sim["error"])
    row = _record(mode, found[1], body.get("label") or f"scénario {uuid.uuid4().hex[:4]}", sim)
    return {**row, "plan": plan, "simulation": sim, "total_ms": round((time.perf_counter() - t0) * 1000)}


COMPARED = ("part_ramassee", "cout_fcfa", "non_servis", "reportes", "depotoirs_restants", "compute_ms")


@router.get("/scenarios/compare")
def compare(a: str = Query(...), b: str = Query(...), _role: str = MAIRIE) -> dict[str, Any]:
    """Tableau des écarts B − A : part ramassée, coût, non servis, reportés, dépotoirs restants, durée."""
    rows = {r["id"]: r for r in _scenarios()}
    missing = [x for x in (a, b) if x not in rows]
    if missing:
        raise HTTPException(404, f"Scénario(s) introuvable(s) : {', '.join(missing)}.")
    ra, rb = rows[a]["results"], rows[b]["results"]
    lines = []
    for key in COMPARED:
        va, vb = ra.get(key), rb.get(key)
        diff = round(vb - va, 4) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
        lines.append({"indicateur": key, "a": va, "b": vb, "ecart": diff})
    return {"a": rows[a], "b": rows[b], "ecarts": lines}


def _point(body: Any) -> tuple[float, float]:
    """(lat, lon) valides d'un corps JSON ; 422 sinon."""
    lat, lon = (body or {}).get("lat"), (body or {}).get("lon")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lon)) \
            or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(422, "lat et lon doivent être des nombres valides.")
    return float(lat), float(lon)


@router.post("/sim/dumpsites")
def add_sim_dumpsite(body: Any = Body(default=None), _role: str = MAIRIE) -> dict[str, Any]:
    """Dépotoir fictif, écrit dans sim.db uniquement (jamais dans reel.db ni dans un export)."""
    lat, lon = _point(body)
    kg = body.get("kg") if isinstance(body.get("kg"), (int, float)) and not isinstance(body.get("kg"), bool) else None
    kg = float(kg) if kg is not None and 0 < kg <= 100_000 else float(
        section(section(get_config(), "model"), "dumpsite_kg_by_size").get("medium") or 0)
    row = {"id": f"sim_{uuid.uuid4().hex[:10]}", "lat": lat, "lon": lon, "kg": kg, "created_at": now(), "source": "sim"}
    conn = get_db("sim")
    try:
        with conn:
            conn.execute("INSERT INTO sim_dumpsites(id, lat, lon, kg, created_at) VALUES(?,?,?,?,?)",
                         (row["id"], lat, lon, kg, row["created_at"]))
    finally:
        conn.close()
    return row


@router.post("/sim/roads/cut")
def cut_road(body: Any = Body(default=None), _role: str = MAIRIE) -> dict[str, Any]:
    """Coupe (cut:true) ou rouvre (cut:false) une route en simulation (sim.db) ; appliquée aux plans mode=sim."""
    from core.geo.graph import resolve_cuts
    from core.optim.plan import default_network

    body = body if isinstance(body, dict) else {}
    net = default_network()
    snap = float(section(get_config(), "network").get("cut_snap_m") or 0)
    query = {"edge_id": body["edge_id"]} if isinstance(body.get("edge_id"), str) else dict(zip(("lat", "lon"), _point(body)))
    _mask, done, warnings = resolve_cuts(net, [query], snap)
    if not done:
        raise HTTPException(422, " ".join(warnings) or "Route introuvable.")
    cut = done[0]
    conn = get_db("sim")
    try:
        with conn:
            if body.get("cut", True) is False:
                conn.execute("DELETE FROM road_cuts WHERE edge_id=?", (cut["edge_id"],))
            else:
                conn.execute("INSERT OR REPLACE INTO road_cuts(edge_id, lat, lon, created_at) VALUES(?,?,?,?)",
                             (cut["edge_id"], cut["lat"], cut["lon"], now()))
        active = [dict(r) for r in conn.execute("SELECT * FROM road_cuts").fetchall()]
    finally:
        conn.close()
    return {"edge": cut, "cut": body.get("cut", True) is not False, "active_cuts": active}
