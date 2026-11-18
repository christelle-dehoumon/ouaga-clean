"""Migration de l'ancienne base data/reports.db (statuts accepte/rejete/a_verifier) vers reel.db / sim.db.

    python -m scripts.migrate_reports_db [chemin/vers/reports.db]

- accepte -> à vérifier (le système ne décide plus), alertes reprises si pertinent (GPS imprécis, doublon) ;
- a_verifier -> à vérifier ;
- rejete -> table ecartes avec le motif d'origine (resolu = 0 : la mairie peut le remettre à vérifier) ;
- source « simule » -> sim.db, jamais reel.db. Les photos n'étaient pas conservées : cas migrés sans photo.
Idempotent : un identifiant déjà présent n'est pas recopié.
"""

from __future__ import annotations

import json
import sqlite3
import sys

from core import lifecycle
from core.config import resolve
from core.db import get_db, now
from core.validation.rules import Triage

ALERT_FROM_CODE = {"GPS_IMPRECIS": "GPS_IMPRECIS", "DOUBLON": "DOUBLON_PROBABLE", "PHOTO_DEJA_VUE": "PHOTO_DEJA_VUE",
                   "PLAN_D_EAU": "PRES_PLAN_EAU"}


def main() -> int:
    src = resolve(sys.argv[1] if len(sys.argv) > 1 else "data/reports.db")
    if not src.exists():
        print(f"Aucune ancienne base ({src}) : rien à migrer.")
        return 0
    old = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    grid = Triage().grid
    counts = {"cas": 0, "ecartes": 0, "deja": 0}
    for r in old.execute("SELECT * FROM reports ORDER BY received_at").fetchall():
        mode = "sim" if r["source"] == "simule" else "reel"
        conn = get_db(mode)
        try:
            if conn.execute("SELECT 1 FROM reports WHERE id=?", (r["id"],)).fetchone():
                counts["deja"] += 1
                continue
            if r["status"] == "rejete":
                with conn:
                    conn.execute("INSERT INTO ecartes(quand, motif_code, motif, payload_resume, lat, lon) VALUES(?,?,?,?,?,?)",
                                 (r["received_at"] or now(), r["reason_code"] or "MIGRATION", r["reason"] or "Rejeté (ancienne base)",
                                  json.dumps({"id": r["id"], "migre_de": "reports.db"}), r["lat"], r["lon"]))
                counts["ecartes"] += 1
                continue
            alerts = [ALERT_FROM_CODE[r["reason_code"]]] if r["reason_code"] in ALERT_FROM_CODE else []
            lifecycle.create(conn, {"id": r["id"], "lat": r["lat"], "lon": r["lon"], "reported_at": r["reported_at"],
                                    "photo_hash": r["photo_hash"], "alertes": alerts + ["MIGRE_SANS_PHOTO"], "source": mode,
                                    "cell": grid.key(r["lat"], r["lon"])}, who="systeme")
            counts["cas"] += 1
        finally:
            conn.close()
    print(f"Migration : {counts['cas']} cas à vérifier, {counts['ecartes']} écartés, {counts['deja']} déjà présents.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
