"""Crée data/reel.db et data/sim.db (même schéma) et charge le jeu factice de démonstration dans sim.db seulement.

    python -m scripts.init_db            # idempotent : ne recharge pas le jeu factice si sim.db a déjà des cas
Le jeu factice (data/mock/signalements_synthetiques.geojson) est étiqueté « synthetic » : il ne touche jamais reel.db.
"""

from __future__ import annotations

import json
import sys
import uuid

from core import lifecycle
from core.config import config_path, resolve
from core.db import db_path, get_db, now
from core.validation.rules import Triage

DEMO = "data/mock/signalements_synthetiques.geojson"


def seed_sim() -> int:
    """Charge les cas factices dans sim.db (statut à vérifier ; ceux marqués accepted dans le jeu : confirmés)."""
    conn = get_db("sim")
    try:
        if conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]:
            return 0
        grid = Triage().grid
        fc = json.loads(resolve(DEMO).read_text(encoding="utf-8"))
        n = 0
        for f in fc["features"]:
            lon, lat = f["geometry"]["coordinates"]
            rid = f"sim_{f['properties']['id']}_{uuid.uuid4().hex[:4]}"
            lifecycle.create(conn, {"id": rid, "lat": lat, "lon": lon, "reported_at": f["properties"]["date"],
                                    "alertes": ["CAS_SIMULE"], "source": "sim", "cell": grid.key(lat, lon)}, who="systeme")
            if f["properties"].get("status_source") == "accepted":
                with conn:
                    conn.execute("UPDATE reports SET statut='confirme', updated_at=? WHERE id=?", (now(), rid))
                    conn.execute("INSERT INTO historique(report_id, qui, quand, action, de_type, de_statut, vers_type, "
                                 "vers_statut) VALUES(?,?,?,?,?,?,?,?)", (rid, "systeme", now(), "import_demo_confirme",
                                                                         "depotoir", "a_verifier", "depotoir", "confirme"))
            n += 1
        return n
    finally:
        conn.close()


def main() -> int:
    for mode in ("reel", "sim"):
        get_db(mode).close()
        print(f"[base] {mode} : {db_path(mode)}")
    print(f"[configuration] {config_path()}")
    n = seed_sim()
    print(f"[sim] {n} cas factices chargés dans sim.db" if n else "[sim] sim.db contient déjà des cas : rien chargé")
    return 0


if __name__ == "__main__":
    sys.exit(main())
