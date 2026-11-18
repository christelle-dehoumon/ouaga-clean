"""Routes des cas : envoi citoyen (réponse opaque), listes par rôle, décisions, historique, écartés, exports."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from api.roles import require, role_of
from core import lifecycle
from core.config import get_config, section
from core.db import get_db, now, reset as reset_db
from core.validation.rules import ALERTS, REASONS, Triage, photos_root

router = APIRouter(prefix="/api")
_TRIAGE: dict[str, Triage] = {}
STAFF = Depends(require("brigade", "mairie"))
MAIRIE = Depends(require("mairie"))
BRIGADE = Depends(require("brigade"))


def triage() -> Triage:
    """Tri de la commune courante (construit une fois)."""
    from core.config import config_path

    key = str(config_path())
    if key not in _TRIAGE:
        _TRIAGE.clear()
        _TRIAGE[key] = Triage()
    return _TRIAGE[key]


def _mode(value: str) -> str:
    if value not in ("reel", "sim"):
        raise HTTPException(422, "mode doit valoir « reel » ou « sim ».")
    return value


def _case(row: Any) -> dict[str, Any]:
    """Cas pour le front : alertes avec libellé, sans chemin de fichier ni empreinte de photo."""
    alerts = json.loads(row["alertes"] or "[]")
    return {"id": row["id"], "type": row["type"], "statut": row["statut"], "lat": row["lat"], "lon": row["lon"],
            "reported_at": row["reported_at"], "created_at": row["created_at"], "updated_at": row["updated_at"],
            "alertes": alerts, "alertes_libelles": [ALERTS.get(a, a) for a in alerts],
            "nb_signalements": row["nb_signalements"], "duplicate_of": row["duplicate_of"], "source": row["source"],
            "photo": bool(row["photo_path"]),
            "photo_url": f"/api/reports/{row['id']}/photo?mode={row['source']}" if row["photo_path"] else None}


@router.post("/reports")
async def post_report(request: Request, mode: str = "reel") -> JSONResponse:
    """Envoi citoyen : toujours HTTP 200 {"ok": true}, même écarté (aucun verdict ni motif renvoyé).

    mode=sim (cas factice de démonstration) : réservé à la mairie, écrit seulement dans sim.db."""
    if mode == "sim":
        if role_of(request) != "mairie":
            raise HTTPException(403, "Les cas simulés sont réservés à la mairie.")
    elif mode != "reel":
        return JSONResponse({"ok": True})
    limit = int(section(get_config(), "validation").get("max_body_bytes") or 0)
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            chunks = [b"x" * (limit + 1)]   # trop gros : on n'en garde rien, le tri l'écarte
            break
        chunks.append(chunk)
    await run_in_threadpool(triage().submit, b"".join(chunks), mode)
    return JSONResponse({"ok": True})


@router.get("/reports")
def list_reports(request: Request, mode: str = "reel", statut: str | None = None, type: str | None = None,  # noqa: A002
                 inclure_nettoyes: int = 0, depuis: str | None = None, limit: int = 2000,
                 role: str = STAFF) -> list[dict[str, Any]]:
    """Brigade : seulement les cas à vérifier (dépotoir et nettoyage). Mairie : tout sauf nettoyé par défaut.

    depuis=<horodatage> : cas modifiés depuis (sondage de la brigade pour être notifiée des nouveaux cas)."""
    mode = _mode(mode)
    where, args = [], []
    if role == "brigade":
        where.append("statut='a_verifier'")
    elif statut:
        where.append("statut=?")
        args.append(statut)
    elif not inclure_nettoyes:
        where.append("statut!='nettoye'")
    if type:
        where.append("type=?")
        args.append(type)
    if depuis:
        where.append("updated_at>?")
        args.append(depuis)
    sql = "SELECT * FROM reports" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY updated_at DESC LIMIT ?"
    conn = get_db(mode)
    try:
        return [_case(r) for r in conn.execute(sql, [*args, max(1, min(limit, 5000))]).fetchall()]
    finally:
        conn.close()


def _transition(report_id: str, mode: str, role: str, action: str) -> dict[str, Any]:
    conn = get_db(_mode(mode))
    try:
        result = lifecycle.apply(conn, report_id, role, action)
        row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    except lifecycle.LifecycleError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    finally:
        conn.close()
    triage().forget(mode)   # la grille anti-doublon ne garde que les cas actifs
    return {**result, "cas": _case(row)}


@router.post("/reports/{report_id}/decision")
def decision(report_id: str, body: Any = Body(default=None), mode: str = "reel",
             role: str = Depends(require("brigade", "mairie"))) -> dict[str, Any]:
    """Brigade : {action: "confirmer" | "rejeter"} sur un cas à vérifier (dépotoir ou nettoyage)."""
    action = body.get("action") if isinstance(body, dict) else None
    if action not in ("confirmer", "rejeter"):
        raise HTTPException(422, "action doit valoir « confirmer » ou « rejeter ».")
    return _transition(report_id, mode, role, action)


@router.post("/reports/{report_id}/mark-clean")
def mark_clean(report_id: str, mode: str = "reel", role: str = Depends(require("brigade", "mairie"))) -> dict[str, Any]:
    """Mairie : dépotoir confirmé nettoyé par ses agents -> nettoyage à vérifier."""
    return _transition(report_id, mode, role, "marquer_nettoye")


@router.post("/reports/{report_id}/reset")
def reset_case(report_id: str, mode: str = "reel", role: str = Depends(require("brigade", "mairie"))) -> dict[str, Any]:
    """Mairie : cas rejeté -> à vérifier (même type), sans note."""
    return _transition(report_id, mode, role, "remettre_a_verifier")


@router.get("/reports/{report_id}/history")
def report_history(report_id: str, mode: str = "reel", _role: str = STAFF) -> list[dict[str, Any]]:
    """Historique : une ligne par transition [{qui, quand, action, de, vers}]."""
    conn = get_db(_mode(mode))
    try:
        if not conn.execute("SELECT 1 FROM reports WHERE id=?", (report_id,)).fetchone():
            raise HTTPException(404, f"Cas « {report_id} » introuvable.")
        return lifecycle.history(conn, report_id)
    finally:
        conn.close()


@router.get("/reports/{report_id}/photo")
def report_photo(request: Request, report_id: str, mode: str = "reel", code: str | None = None) -> FileResponse:
    """Photo FLOUTÉE (brigade, mairie). Le code peut aussi venir de ?code= pour une balise <img>."""
    from api.roles import role_codes

    header = request.headers.get("X-Role-Code") or code or ""
    if header not in [c for c in role_codes().values() if c]:
        raise HTTPException(401, "Code d'accès manquant ou incorrect.")
    conn = get_db(_mode(mode))
    try:
        row = conn.execute("SELECT photo_path FROM reports WHERE id=?", (report_id,)).fetchone()
    finally:
        conn.close()
    if not row or not row["photo_path"]:
        raise HTTPException(404, "Photo introuvable.")
    path = (photos_root() / row["photo_path"]).resolve()
    if photos_root().resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "Photo introuvable.")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/ecartes")
def list_ecartes(mode: str = "reel", inclure_resolus: int = 0, _role: str = MAIRIE) -> list[dict[str, Any]]:
    """Envois écartés d'office, avec leur motif (visible de la mairie seulement)."""
    conn = get_db(_mode(mode))
    try:
        sql = "SELECT * FROM ecartes" + ("" if inclure_resolus else " WHERE resolu=0") + " ORDER BY id DESC LIMIT 2000"
        return [{**dict(r), "resolu": bool(r["resolu"]), "remettable": r["lat"] is not None and r["lon"] is not None}
                for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


@router.post("/ecartes/{ecarte_id}/reset")
def reset_ecarte(ecarte_id: int, mode: str = "reel", _role: str = MAIRIE) -> dict[str, Any]:
    """Mairie : remet un écarté en « à vérifier » (nouveau cas sans photo, alerte ECARTE_REMIS)."""
    import uuid

    mode = _mode(mode)
    conn = get_db(mode)
    try:
        row = conn.execute("SELECT * FROM ecartes WHERE id=?", (ecarte_id,)).fetchone()
        if row is None:
            raise HTTPException(404, f"Écarté n°{ecarte_id} introuvable.")
        if row["resolu"]:
            raise HTTPException(409, "Cet écarté a déjà été remis à vérifier.")
        if row["lat"] is None or row["lon"] is None:
            raise HTTPException(409, "Impossible de remettre à vérifier : l'envoi n'avait pas de position valide.")
        rid = uuid.uuid4().hex[:16]
        lifecycle.create(conn, {"id": rid, "lat": row["lat"], "lon": row["lon"], "reported_at": now(),
                                "alertes": ["ECARTE_REMIS"], "source": mode}, who="mairie")
        with conn:
            conn.execute("UPDATE ecartes SET resolu=1, report_id=? WHERE id=?", (rid, ecarte_id))
        case = conn.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
    finally:
        conn.close()
    triage().forget(mode)
    return {"ecarte_id": ecarte_id, "cas": _case(case)}


@router.get("/export/reports.geojson")
def export_reports(_role: str = MAIRIE) -> JSONResponse:
    """Cas RÉELS confirmés ou nettoyés (reel.db seulement), sans photo ni donnée personnelle, licence indiquée."""
    from core.export import reports_geojson

    return JSONResponse(reports_geojson(), media_type="application/geo+json",
                        headers={"Content-Disposition": 'attachment; filename="signalements.geojson"'})


@router.get("/export/reports.osm")
def export_osm(_role: str = MAIRIE) -> JSONResponse:
    """Fichier OSM (à relire dans JOSM) des dépotoirs réels confirmés ; jamais envoyé à OpenStreetMap."""
    from fastapi.responses import Response

    from core.export import reports_osm_xml

    return Response(reports_osm_xml(), media_type="application/xml",  # type: ignore[return-value]
                    headers={"Content-Disposition": 'attachment; filename="depotoirs.osm"'})


@router.post("/admin/reset")
def admin_reset(confirm: str | None = Query(default=None), _role: str = MAIRIE) -> dict[str, Any]:
    """Remise à zéro de sim.db ; reel.db seulement avec ?confirm=reel."""
    modes = ["sim"] + (["reel"] if confirm == "reel" else [])
    for mode in modes:
        reset_db(mode)
        triage().forget(mode)
    return {"reset": modes}


ALERTS.setdefault("ECARTE_REMIS", "Envoi écarté d'office puis remis à vérifier par la mairie.")
__all__ = ["router", "REASONS"]
