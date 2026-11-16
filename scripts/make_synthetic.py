"""Signalements synthétiques plausibles (près d'une route camion, loin des centres de bâtiments) et lot piégé pour le membre B.

Tout est étiqueté « synthetic ». Graine fixe : relancer donne les mêmes fichiers.
Usage : python -m scripts.make_synthetic [--n 100] [--status pending]
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point

from core.config import load_config
from core.geo.buildings import load_buildings
from core.geo.download import REPO_ROOT
from core.geo.graph import EARTH_RADIUS_M, Network, load_network, project
from core.geo.territories import commune_polygon

SEED = 0
SIZES = ("small", "medium", "large")
# Paramètres de fabrication (pas des paramètres du modèle) : écart à la route et distance minimale à un centre de bâtiment.
OFFSET_M = (8.0, 25.0)
MIN_FROM_BUILDING_M = 10.0
BASE_TIME = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)   # + 3 jours au plus : dates passées
OUT_PLAUSIBLE = "signalements_synthetiques.json"
OUT_TRAPS = "signalements_pieges.json"
OUT_EXPECTED = "signalements_pieges_attendus.json"


def _report(rid: str, lat: Any, lon: Any, size: Any, minutes: int, status: str) -> dict[str, Any]:
    """Signalement au format du contrat (section 1), étiqueté synthetic."""
    return {"id": rid, "lat": lat, "lon": lon, "size": size, "photo_url": None, "photo_hash": None,
            "timestamp": (BASE_TIME + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "synthetic",
            "status": status, "trust": 0.0, "reason": None, "dumpsite_id": None, "validated_by": None, "validated_at": None}


def plausible_reports(cfg: dict[str, Any], net: Network, n: int, status: str, seed: int = SEED) -> list[dict[str, Any]]:
    """n signalements à quelques mètres d'un nœud camion de la commune, loin de tout centre de bâtiment."""
    rng = np.random.default_rng(seed)
    view = net.views["truck_dry"]
    commune, _ = commune_polygon(cfg)
    b_lat, b_lon, _ = load_buildings(cfg)
    origin = view.origin
    b_tree = cKDTree(project(b_lat, b_lon, origin)) if len(b_lat) else None
    nodes = view.tree_idx
    out: list[dict[str, Any]] = []
    tries = 0
    while len(out) < n and tries < 50 * max(n, 1) and len(nodes):
        tries += 1
        i = int(nodes[rng.integers(len(nodes))])
        dist, angle = rng.uniform(*OFFSET_M), rng.uniform(0, 2 * math.pi)
        lat = float(net.lat[i]) + math.degrees(dist * math.sin(angle) / EARTH_RADIUS_M)
        lon = float(net.lon[i]) + math.degrees(dist * math.cos(angle) / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
        if commune is not None and not commune.covers(Point(lon, lat)):
            continue
        if b_tree is not None and b_tree.query(project(np.array([lat]), np.array([lon]), origin)[0])[0] < MIN_FROM_BUILDING_M:
            continue
        out.append(_report(f"s{len(out) + 1:05d}", round(lat, 6), round(lon, 6), SIZES[int(rng.integers(3))],
                           int(rng.integers(0, 3 * 24 * 60)), status))
    return out


def trap_reports(valid: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Lot piégé pour B et, pour chaque id, le défaut attendu."""
    base = valid[0]
    traps: list[tuple[dict[str, Any], str]] = [
        (_report("t_hors_commune", 11.1771, -4.2979, "large", 10, "pending"), "hors commune (Bobo-Dioulasso)"),
        (_report("t_mer", 0.0, 0.0, "small", 11, "pending"), "hors commune (0, 0, golfe de Guinée)"),
        (_report("t_doublon_3m", round(base["lat"] + 0.000027, 6), base["lon"], base["size"], 12, "pending"),
         f"doublon à 3 m de {base['id']}"),
        (_report("t_doublon_8m", base["lat"], round(base["lon"] + 0.000074, 6), base["size"], 13, "pending"),
         f"doublon à 8 m de {base['id']}"),
        (_report("t_lat_200", 200.0, -1.5, "medium", 14, "pending"), "latitude hors de [-90, 90]"),
        (_report("t_lon_texte", 12.37, "abc", "medium", 15, "pending"), "longitude non numérique"),
        (_report("t_lat_null", None, -1.52, "medium", 16, "pending"), "latitude absente (null)"),
        (_report("t_taille_inconnue", 12.37, -1.52, "enorme", 17, "pending"), "taille hors de small/medium/large"),
        ({k: v for k, v in _report("t_sans_lat", 12.37, -1.52, "small", 18, "pending").items() if k != "lat"},
         "champ lat manquant"),
        ({k: v for k, v in _report("t_sans_taille", 12.37, -1.52, "small", 19, "pending").items() if k != "size"},
         "champ size manquant"),
        ({**_report("t_date_13e_mois", 12.37, -1.52, "small", 20, "pending"), "timestamp": "2026-13-45T25:61:00Z"},
         "date impossible (mois 13, jour 45, 25 h 61)"),
        ({**_report("t_date_futur", 12.37, -1.52, "small", 21, "pending"), "timestamp": "2099-01-01T00:00:00Z"},
         "date dans le futur"),
        ({**_report("t_date_texte", 12.37, -1.52, "small", 22, "pending"), "timestamp": "hier soir"},
         "date non ISO 8601"),
        ({**_report("t_statut_inconnu", 12.37, -1.52, "small", 23, "pending"), "status": "validé"},
         "statut hors de pending/accepted/rejected/to_review"),
    ]
    return [t for t, _ in traps], {t["id"]: why for t, why in traps}


def main() -> None:
    """Écrit les signalements plausibles, le lot piégé et les défauts attendus dans paths.mock_dir."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--status", default="pending", choices=["pending", "accepted"])
    args = parser.parse_args()
    cfg = load_config(REPO_ROOT / "config" / "commune_config.json")
    net = load_network(cfg)
    valid = plausible_reports(cfg, net, args.n, args.status)
    if not valid:
        print("Aucun signalement fabriqué : réseau ou bâtiments absents (lancer python -m core.geo.download).")
        return
    traps, expected = trap_reports(valid)
    out = Path(cfg["paths"]["mock_dir"])
    out = out if out.is_absolute() else REPO_ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    for name, data in ((OUT_PLAUSIBLE, valid), (OUT_TRAPS, traps), (OUT_EXPECTED, expected)):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(valid)} signalements plausibles, {len(traps)} pièges, dans {out} (étiquette synthetic, graine {SEED}).")


if __name__ == "__main__":
    main()
