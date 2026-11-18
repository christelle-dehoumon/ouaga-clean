"""Tri automatique des envois : aide à la brigade, JAMAIS décideur.

Le tri ne produit aucun statut accepté/rejeté. Pour chaque envoi, une seule des trois issues :
- « ecarte » : écarté d'office, motif enregistré dans la table ecartes (forme, position, hors ville, date, photo) ;
- « renforce » : doublon (moins de duplicate_radius_m ET moins de duplicate_window_h d'un cas actif) : pas de nouveau
  point, le cas existant gagne un signalement et l'alerte DOUBLON_PROBABLE ;
- « cree » : nouveau cas à vérifier, avec des alertes pour la brigade (PHOTO_DEJA_VUE, PRES_PLAN_EAU, HORS_SECTEUR,
  GPS_IMPRECIS, FLOUTAGE_NON_VERIFIE).
La photo est floutée en mémoire avant tout stockage (core/privacy.py). Un envoi malformé ne lève jamais d'exception.
Tous les seuils sont dans la section « validation » de la configuration.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core import lifecycle
from core.config import get_config, resolve, section
from core.db import get_db, now
from core.geo.territories import commune_polygon, sector_polygon
from core.privacy import PhotoError, blur_photo

from .grid import Grid, geojson_polygons, haversine_m

REASONS = {
    "TROP_VOLUMINEUX": "Envoi trop volumineux.",
    "FORMAT_INVALIDE": "Données mal formées (JSON illisible ou pas un objet).",
    "POSITION_INVALIDE": "Position absente, non numérique ou impossible.",
    "HORS_VILLE": "Position hors de la commune.",
    "DATE_INVALIDE": "Date illisible.",
    "DATE_FUTURE": "Date dans le futur.",
    "DATE_TROP_ANCIENNE": "Signalement trop ancien.",
    "PHOTO_ABSENTE": "Pas de photo.",
    "PHOTO_INVALIDE": "Photo illisible (base64 ou image corrompue).",
    "PHOTO_TROP_LOURDE": "Photo trop lourde.",
    "ERREUR_INTERNE": "Erreur interne pendant le tri : envoi conservé pour la mairie.",
}
ALERTS = {
    "DOUBLON_PROBABLE": "Signalé plusieurs fois au même endroit en peu de temps.",
    "PHOTO_DEJA_VUE": "Photo identique à un envoi précédent.",
    "PRES_PLAN_EAU": "Position sur ou près d'un plan d'eau.",
    "HORS_SECTEUR": "Dans la ville mais hors du secteur de l'équipe.",
    "GPS_IMPRECIS": "Position GPS imprécise.",
    "FLOUTAGE_NON_VERIFIE": "Détection impossible : toute la photo a été floutée.",
}
ACTIVE = ("a_verifier", "confirme")


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _parse_dt(s: Any) -> datetime:
    if not isinstance(s, str) or len(s) > 64:
        raise ValueError("date")
    d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class Triage:
    """Tri d'un envoi brut (octets) vers reel.db ou sim.db ; une grille anti-doublon par mode."""

    def __init__(self, cfg: dict[str, Any] | None = None):
        import shapely

        self.cfg = cfg or get_config()
        self.v = section(self.cfg, "validation")
        self.commune, _ = commune_polygon(self.cfg)
        self.sector = sector_polygon(self.cfg)
        self.water = self._water()
        for geom in (self.commune, self.sector, self.water):
            if geom is not None:
                shapely.prepare(geom)
        self.grids: dict[str, Grid] = {}
        self.lock = threading.Lock()

    def _water(self) -> Any:
        """Plans d'eau (polygones OSM) élargis de water_buffer_m ; None si le fichier manque (règle alors inactive)."""
        from shapely.geometry import shape
        from shapely.ops import unary_union

        path = section(self.cfg, "paths").get("water_bodies")
        if not isinstance(path, str) or not resolve(path).exists():
            return None
        polys = geojson_polygons(json.loads(resolve(path).read_text(encoding="utf-8")))
        if not polys:
            return None
        lat0 = float(self.v.get("grid_center_lat") or 0)
        deg = float(self.v.get("water_buffer_m") or 0) / (111_320.0 * max(math.cos(math.radians(lat0)), 0.01))
        return unary_union([shape({"type": "Polygon", "coordinates": p}) for p in polys]).buffer(deg)

    @property
    def water_rule_active(self) -> bool:
        """Vrai si la règle PRES_PLAN_EAU peut se déclencher (fichier des plans d'eau présent et non vide)."""
        return self.water is not None

    def _grid(self, mode: str, conn: Any) -> Grid:
        """Grille des cas actifs du mode, construite une fois depuis la base."""
        if mode not in self.grids:
            grid = Grid(float(self.v["duplicate_radius_m"]), float(self.v["grid_center_lat"]))
            for r in conn.execute("SELECT id, lat, lon, reported_at FROM reports WHERE type='depotoir' AND statut IN (?,?)",
                                  ACTIVE).fetchall():
                grid.add(r["id"], r["lat"], r["lon"])
            self.grids[mode] = grid
        return self.grids[mode]

    def forget(self, mode: str | None = None) -> None:
        """Oublie la grille (remise à zéro de la base)."""
        if mode is None:
            self.grids.clear()
        else:
            self.grids.pop(mode, None)

    # ------------------------------------------------------------------ issues
    def _resume(self, raw: Any, body: bytes) -> str:
        """Résumé tronqué de l'envoi, photo remplacée par sa taille et son empreinte."""
        limit = int(self.v.get("payload_resume_chars") or 600)
        if isinstance(raw, dict):
            safe = {}
            for k, val in list(raw.items())[:20]:
                key = str(k)[:40]
                if key == "photo_b64":
                    text = val if isinstance(val, str) else repr(val)
                    safe[key] = {"octets": len(text), "sha256": hashlib.sha256(text.encode(errors="replace")).hexdigest()[:16]}
                else:
                    safe[key] = val if isinstance(val, (int, float, bool)) or val is None else str(val)[:80]
            text = json.dumps(safe, ensure_ascii=False, default=str)
        else:
            text = body[:limit].decode("utf-8", errors="replace")
        return text[:limit]

    def _reject(self, mode: str, code: str, raw: Any, body: bytes) -> dict[str, Any]:
        """Écarté d'office : ligne dans ecartes avec motif et résumé (photo exclue)."""
        lat = raw.get("lat") if isinstance(raw, dict) and _num(raw.get("lat")) and abs(raw["lat"]) <= 90 else None
        lon = raw.get("lon") if isinstance(raw, dict) and _num(raw.get("lon")) and abs(raw["lon"]) <= 180 else None
        conn = get_db(mode)
        try:
            with conn:
                cur = conn.execute("INSERT INTO ecartes(quand, motif_code, motif, payload_resume, lat, lon) VALUES(?,?,?,?,?,?)",
                                   (now(), code, REASONS[code], self._resume(raw, body), lat, lon))
            return {"issue": "ecarte", "motif_code": code, "ecarte_id": cur.lastrowid}
        finally:
            conn.close()

    def submit(self, body: bytes, mode: str = "reel") -> dict[str, Any]:
        """Trie un envoi ; ne lève jamais. Résultat interne (jamais renvoyé tel quel au citoyen)."""
        raw: Any = None
        try:
            return self._submit(body, mode)
        except Exception:  # dernier filet : l'envoi est gardé pour la mairie
            try:
                raw = json.loads(body) if len(body) <= int(self.v.get("max_body_bytes") or 0) else None
            except Exception:  # corps illisible
                raw = None
            return self._reject(mode, "ERREUR_INTERNE", raw, body)

    def _submit(self, body: bytes, mode: str) -> dict[str, Any]:
        v = self.v
        if len(body) > int(v["max_body_bytes"]):
            return self._reject(mode, "TROP_VOLUMINEUX", None, body[:200])
        try:
            raw = json.loads(body)
        except (ValueError, UnicodeDecodeError, RecursionError):
            return self._reject(mode, "FORMAT_INVALIDE", None, body)
        if not isinstance(raw, dict):
            return self._reject(mode, "FORMAT_INVALIDE", raw if isinstance(raw, dict) else None, body)
        lat, lon = raw.get("lat"), raw.get("lon")
        if not (_num(lat) and _num(lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return self._reject(mode, "POSITION_INVALIDE", raw, body)
        if self.commune is None or not self.commune.covers(__import__("shapely").Point(lon, lat)):
            return self._reject(mode, "HORS_VILLE", raw, body)
        current = datetime.now(timezone.utc)
        try:
            reported = _parse_dt(raw["reported_at"]) if raw.get("reported_at") is not None else current
        except (ValueError, TypeError, OverflowError):
            return self._reject(mode, "DATE_INVALIDE", raw, body)
        if reported > current + timedelta(minutes=float(v["future_tolerance_min"])):
            return self._reject(mode, "DATE_FUTURE", raw, body)
        if reported < current - timedelta(days=float(v["max_report_age_days"])):
            return self._reject(mode, "DATE_TROP_ANCIENNE", raw, body)
        photo = raw.get("photo_b64")
        if not photo:
            return self._reject(mode, "PHOTO_ABSENTE", raw, body)
        try:
            if not isinstance(photo, str):
                raise ValueError("photo")
            data = base64.b64decode(photo.split(",", 1)[1] if "," in photo[:100] else photo, validate=True)
        except (binascii.Error, ValueError):
            return self._reject(mode, "PHOTO_INVALIDE", raw, body)
        if not data:
            return self._reject(mode, "PHOTO_INVALIDE", raw, body)
        if len(data) > int(v["max_photo_bytes"]):
            return self._reject(mode, "PHOTO_TROP_LOURDE", raw, body)
        photo_hash = hashlib.sha256(data).hexdigest()
        try:
            blurred, blur_report = blur_photo(data, self.cfg)   # en mémoire : l'original n'est jamais écrit
        except PhotoError:
            return self._reject(mode, "PHOTO_INVALIDE", raw, body)
        del data
        alerts = []
        acc = raw.get("accuracy_m")
        if _num(acc) and acc > float(v["max_accuracy_m"]):
            alerts.append("GPS_IMPRECIS")
        point = __import__("shapely").Point(lon, lat)
        if self.sector is not None and not self.sector.covers(point):
            alerts.append("HORS_SECTEUR")
        if self.water is not None and self.water.covers(point):
            alerts.append("PRES_PLAN_EAU")
        if blur_report.get("status") != "ok":
            alerts.append("FLOUTAGE_NON_VERIFIE")
        source = "sim" if mode == "sim" else "reel"
        with self.lock:
            conn = get_db(mode)
            try:
                grid = self._grid(mode, conn)
                window = timedelta(hours=float(v["duplicate_window_h"]))
                for oid, olat, olon in grid.near(lat, lon):
                    if haversine_m(lat, lon, olat, olon) >= float(v["duplicate_radius_m"]):
                        continue
                    row = conn.execute("SELECT reported_at FROM reports WHERE id=? AND type='depotoir' AND statut IN (?,?)",
                                       (oid, *ACTIVE)).fetchone()
                    if row and abs(reported - _parse_dt(row["reported_at"])) < window:
                        count = lifecycle.reinforce(conn, oid, "DOUBLON_PROBABLE")
                        return {"issue": "renforce", "id": oid, "nb_signalements": count}
                if conn.execute("SELECT 1 FROM reports WHERE photo_hash=? LIMIT 1", (photo_hash,)).fetchone():
                    alerts.append("PHOTO_DEJA_VUE")
                rid = uuid.uuid4().hex[:16]
                photo_path = self._store_photo(mode, rid, blurred)
                lifecycle.create(conn, {"id": rid, "lat": float(lat), "lon": float(lon), "photo_path": photo_path,
                                        "photo_hash": photo_hash, "reported_at": reported.isoformat(),
                                        "alertes": sorted(set(alerts)), "source": source})
                grid.add(rid, lat, lon)
                return {"issue": "cree", "id": rid, "alertes": sorted(set(alerts)), "floutage": blur_report}
            finally:
                conn.close()

    def _store_photo(self, mode: str, rid: str, blurred: bytes) -> str:
        """Écrit la photo FLOUTÉE (jamais l'originale) ; renvoie son chemin relatif au dossier des photos."""
        root = photos_root()
        folder = root / mode
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{rid}.jpg").write_bytes(blurred)
        return f"{mode}/{rid}.jpg"


def photos_root() -> Path:
    """Dossier des photos floutées : $PHOTO_DIR, sinon paths.photos_dir."""
    env = os.environ.get("PHOTO_DIR")
    return Path(env) if env else resolve(section(get_config(), "paths").get("photos_dir") or "data/photos")
