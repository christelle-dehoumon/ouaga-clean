"""Chronomètre compute_plan sur les vraies données, zone pilote : complet, panne, pluie, quartier, 20 signalements
(python -m scripts.measure_plan). Le quartier et les signalements ajoutés sont synthétiques (étiquette « synthetic »)."""

from __future__ import annotations

import math
import time
from collections import Counter
from typing import Any

import numpy as np

from core.config import config_path, load_config
from core.geo.buildings import load_buildings
from core.geo.graph import load_network
from core.geo.territories import commune_polygon
from core.optim.plan import compute_plan

SEED = 0
N_REPORTS = 20
QUARTER_SIDE_M = 1500


def _show(label: str, plan: dict[str, Any], seconds: float) -> None:
    """Une ligne de résultats."""
    tot = plan["totals"]
    print(f"{label:<28} {seconds:6.2f} s  mode {plan['mode']:<9} points {len(plan['collection_points']):>3}  "
          f"servis {tot['points_served']:>3}  non servis {dict(Counter(u['reason'] for u in plan['unserved']))}  "
          f"tournées {len(plan['routes'])}  {tot['distance_km']:.1f} km  contrôles "
          f"{'OK' if all(v for k, v in plan['checks'].items() if k != 'messages') else plan['checks']['messages']}")


def _timed(label: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """compute_plan chronométré et affiché."""
    t = time.perf_counter()
    plan = compute_plan(*args, **kwargs)
    _show(label, plan, time.perf_counter() - t)
    return plan


def main() -> None:
    """Mesure les cinq scénarios demandés, réseau chargé une fois."""
    cfg = load_config(config_path())
    t = time.perf_counter()
    net = load_network(cfg)
    print(f"Chargement du réseau : {time.perf_counter() - t:.1f} s")
    params = cfg["params"]
    full = _timed("Complet (cache froid)", params, [], cfg=cfg, net=net)
    full = _timed("Complet (cache chaud)", params, [], cfg=cfg, net=net)
    _timed("Panne truck2 (partiel)", {**params, "broken_trucks": ["truck2"]}, [], previous_plan=full, cfg=cfg, net=net)
    _timed("Pluie (complet, froid)", {**params, "rainy_season": True}, [], previous_plan=full, cfg=cfg, net=net)
    _timed("Pluie (complet, chaud)", {**params, "rainy_season": True}, [], previous_plan=full, cfg=cfg, net=net)
    pilot = [p for p in full["collection_points"] if p["type"] == "center"]
    lat0 = max(p["lat"] for p in pilot)
    lon0 = float(np.mean([p["lon"] for p in pilot]))
    dlat = QUARTER_SIDE_M / 111_320
    dlon = dlat / math.cos(math.radians(lat0))
    quarter = {"type": "Feature", "properties": {"id": "q_synth_1", "name": "Quartier synthétique", "source": "synthetic"},
               "geometry": {"type": "Polygon", "coordinates": [[[lon0, lat0 + 0.004], [lon0 + dlon, lat0 + 0.004],
                                                                [lon0 + dlon, lat0 + 0.004 + dlat],
                                                                [lon0, lat0 + 0.004 + dlat], [lon0, lat0 + 0.004]]]}}
    _timed("Nouveau quartier (partiel)", {**params, "extra_territories": [quarter]}, [], previous_plan=full,
           cfg=cfg, net=net)
    lat, lon, _ = load_buildings(cfg)
    commune, _ = commune_polygon(cfg)
    rng = np.random.default_rng(SEED)
    inside = [i for i in rng.permutation(len(lat))[:2000] if abs(lat[i] - lat0) < 0.02 and abs(lon[i] - lon0) < 0.02]
    reports = [{"id": f"s{n}", "lat": float(lat[i]) + 0.0002, "lon": float(lon[i]), "size": "medium", "status": "accepted",
                "source": "synthetic"} for n, i in enumerate(inside[:N_REPORTS])]
    plan = _timed(f"+{len(reports)} signalements (partiel)", params, reports, previous_plan=full, cfg=cfg, net=net)
    print(f"Signalements écartés : {len(plan['ignored_reports'])} ; commune connue : {commune is not None}")


if __name__ == "__main__":
    main()
