"""Tri automatique des signalements : accepté / rejeté / à vérifier.
Règle d'or : ne jamais lever d'exception vers l'appelant, toujours un motif."""
import base64, binascii, hashlib, json, math, os, sqlite3, time, uuid
from datetime import datetime, timedelta, timezone

from .grid import Grid, geojson_polygons, haversine_m, in_any

ACCEPTED, REJECTED, TO_VERIFY = "accepte", "rejete", "a_verifier"

REASONS = {
    "OK": "Signalement accepté.",
    "FORMAT_INVALIDE": "Données mal formées.",
    "POSITION_INVALIDE": "Position impossible ou manquante.",
    "TAILLE_INVALIDE": "Taille inconnue (petit, moyen ou grand).",
    "DATE_INVALIDE": "Date illisible.",
    "DATE_FUTURE": "Date dans le futur.",
    "DATE_TROP_ANCIENNE": "Signalement trop ancien.",
    "HORS_ZONE": "Position hors de la zone couverte.",
    "PLAN_D_EAU": "Position sur un plan d'eau.",
    "DOUBLON": "Dépotoir déjà signalé à moins de 30 m ces dernières 48 h ; il est renforcé.",
    "PHOTO_INVALIDE": "Photo illisible ou trop lourde.",
    "PHOTO_DEJA_VUE": "Cette photo a déjà été envoyée.",
    "PHOTO_ABSENTE": "Pas de photo : à vérifier.",
    "GPS_IMPRECIS": "Position GPS imprécise : à vérifier.",
    "ERREUR_INTERNE": "Erreur interne : signalement non traité.",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports(
  id TEXT PRIMARY KEY, lat REAL, lon REAL, size TEXT, reported_at TEXT,
  received_at TEXT, status TEXT, reason_code TEXT, reason TEXT,
  duplicate_of TEXT, confirmations INTEGER DEFAULT 1, photo_hash TEXT,
  source TEXT, accuracy_m REAL,
  validated_by TEXT, validated_at TEXT, validation_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_status ON reports(status);
"""


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _parse_dt(s):
    if not isinstance(s, str):
        raise ValueError
    d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class Validator:
    def __init__(self, config_path="config/commune_config.json", db_path=None, root="."):
        with open(config_path, encoding="utf-8") as f:
            self.cfg = json.load(f)["validation"]
        self.root = root
        self.zones = self._load(self.cfg["zones_file"])
        self.water = self._load(self.cfg["water_file"])
        self.db_path = db_path or os.environ.get("REPORTS_DB", "data/reports.db")
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.grid = Grid(self.cfg["duplicate_radius_m"], self.cfg["grid_center_lat"])
        self._rebuild()

    def _load(self, rel):
        try:
            with open(os.path.join(self.root, rel), encoding="utf-8") as f:
                return geojson_polygons(json.load(f))
        except FileNotFoundError:
            return []

    def _rebuild(self):
        self.grid.clear()
        for r in self.db.execute("SELECT id,lat,lon FROM reports WHERE status!=?", (REJECTED,)):
            self.grid.add(r["id"], r["lat"], r["lon"])

    def reset(self):
        self.db.execute("DELETE FROM reports")
        self.db.commit()
        self.grid.clear()

    # ------------------------------------------------------------------
    def submit(self, raw):
        t0 = time.perf_counter()
        try:
            res = self._submit(raw)
        except Exception as e:  # jamais de plantage
            res = self._result(None, REJECTED, "ERREUR_INTERNE", detail=type(e).__name__)
        res["ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return res

    def _result(self, rid, status, code, dup=None, detail=None):
        return {"id": rid, "status": status, "reason_code": code,
                "reason": REASONS[code], "duplicate_of": dup, "detail": detail}

    def _store(self, rid, lat, lon, size, rep_at, status, code, dup, photo_hash, source, acc):
        self.db.execute(
            "INSERT OR REPLACE INTO reports(id,lat,lon,size,reported_at,received_at,status,"
            "reason_code,reason,duplicate_of,photo_hash,source,accuracy_m) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, lat, lon, size, rep_at.isoformat(), datetime.now(timezone.utc).isoformat(),
             status, code, REASONS[code], dup, photo_hash, source, acc))
        self.db.commit()
        if status != REJECTED:
            self.grid.add(rid, lat, lon)

    def _submit(self, raw):
        c = self.cfg
        if not isinstance(raw, dict):
            return self._result(None, REJECTED, "FORMAT_INVALIDE")
        rid = raw.get("id") if isinstance(raw.get("id"), str) and raw.get("id") else uuid.uuid4().hex[:12]
        rid = rid[:64]
        lat, lon = raw.get("lat"), raw.get("lon")
        if not (_num(lat) and _num(lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return self._result(rid, REJECTED, "POSITION_INVALIDE")
        size = raw.get("size", "moyen")
        if size not in c["sizes"]:
            return self._result(rid, REJECTED, "TAILLE_INVALIDE")
        now = datetime.now(timezone.utc)
        try:
            rep_at = _parse_dt(raw["reported_at"]) if raw.get("reported_at") is not None else now
        except (ValueError, TypeError, OverflowError):
            return self._result(rid, REJECTED, "DATE_INVALIDE")
        if rep_at > now + timedelta(minutes=c["future_tolerance_min"]):
            return self._result(rid, REJECTED, "DATE_FUTURE")
        if rep_at < now - timedelta(days=c["max_report_age_days"]):
            return self._result(rid, REJECTED, "DATE_TROP_ANCIENNE")
        source = raw.get("source") if raw.get("source") in ("reel", "simule") else "reel"
        acc = raw.get("accuracy_m")
        acc = float(acc) if _num(acc) and acc >= 0 else None

        def reject(code, dup=None):
            self._store(rid, lat, lon, size, rep_at, REJECTED, code, dup, None, source, acc)
            return self._result(rid, REJECTED, code, dup)

        if not in_any(self.zones, lon, lat):
            return reject("HORS_ZONE")
        if in_any(self.water, lon, lat):
            return reject("PLAN_D_EAU")

        # doublon : grille puis distance exacte + fenêtre de temps
        win = timedelta(hours=c["duplicate_window_h"])
        for oid, olat, olon in self.grid.near(lat, lon):
            if oid == rid:
                continue
            if haversine_m(lat, lon, olat, olon) < c["duplicate_radius_m"]:
                row = self.db.execute("SELECT reported_at FROM reports WHERE id=?", (oid,)).fetchone()
                if row and abs(rep_at - datetime.fromisoformat(row["reported_at"])) < win:
                    self.db.execute("UPDATE reports SET confirmations=confirmations+1 WHERE id=?", (oid,))
                    self.db.commit()
                    return reject("DOUBLON", dup=oid)

        photo_hash = None
        p = raw.get("photo_b64")
        if p:
            try:
                if not isinstance(p, str):
                    raise ValueError
                if "," in p[:100]:  # préfixe data:image/jpeg;base64,
                    p = p.split(",", 1)[1]
                blob = base64.b64decode(p, validate=True)
                if not blob or len(blob) > c["max_photo_bytes"]:
                    raise ValueError
            except (binascii.Error, ValueError):
                return reject("PHOTO_INVALIDE")
            photo_hash = hashlib.sha256(blob).hexdigest()
            if self.db.execute("SELECT 1 FROM reports WHERE photo_hash=?", (photo_hash,)).fetchone():
                return reject("PHOTO_DEJA_VUE")

        if photo_hash is None:
            code, status = "PHOTO_ABSENTE", TO_VERIFY
        elif acc is not None and acc > c["max_accuracy_m"]:
            code, status = "GPS_IMPRECIS", TO_VERIFY
        else:
            code, status = "OK", ACCEPTED
        self._store(rid, lat, lon, size, rep_at, status, code, None, photo_hash, source, acc)
        return self._result(rid, status, code)

    # ------------------------------------------------------------------
    def list(self, status=None, limit=1000):
        q, a = "SELECT * FROM reports", []
        if status:
            q += " WHERE status=?"; a.append(status)
        q += " ORDER BY received_at DESC LIMIT ?"; a.append(limit)
        return [dict(r) for r in self.db.execute(q, a)]

    def get(self, rid):
        r = self.db.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
        return dict(r) if r else None

    def validate_manually(self, rid, by, accept, note=""):
        """Qui a validé, quand, pourquoi (greffe 4)."""
        status = ACCEPTED if accept else REJECTED
        cur = self.db.execute(
            "UPDATE reports SET status=?, validated_by=?, validated_at=?, validation_note=? WHERE id=?",
            (status, by, datetime.now(timezone.utc).isoformat(), note, rid))
        self.db.commit()
        self._rebuild()
        return cur.rowcount > 0

    def stats(self):
        s = {"total": 0, "par_statut": {}, "par_motif": {}}
        for r in self.db.execute("SELECT status, reason_code, COUNT(*) n FROM reports GROUP BY 1,2"):
            s["total"] += r["n"]
            s["par_statut"][r["status"]] = s["par_statut"].get(r["status"], 0) + r["n"]
            s["par_motif"][r["reason_code"]] = r["n"]
        return s
