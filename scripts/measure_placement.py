"""Mesure la demande estimée et le placement des points de regroupement sur les vraies données (python -m scripts.measure_placement)."""

from __future__ import annotations

import argparse
import time
from collections import Counter

from core.config import load_config
from core.geo.buildings import building_demand
from core.geo.graph import load_network
from core.optim.placement import place_points


def main() -> None:
    """Affiche durées, nombre de points, accès et part de la demande à distance de marche."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/commune_config.json")
    parser.add_argument("--max-points", type=int, default=None, help="remplace solver.max_collection_points")
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.max_points:
        cfg["solver"]["max_collection_points"] = args.max_points
    net = load_network(cfg)
    t = time.perf_counter()
    demand = building_demand(cfg, cfg["params"])
    demand_s = time.perf_counter() - t
    t = time.perf_counter()
    out = place_points(net, demand, [], cfg, cfg["params"])
    place_s = time.perf_counter() - t
    print(f"Territoires actifs : {demand['territories']}")
    print(f"Bâtiments : {len(demand['kg'])} ; cellules : {out['cells']} ; demande par passage : {demand['kg'].sum() / 1000:.1f} t ; "
          f"non collecté : {demand['uncollected_kg'] / 1000:.1f} t ({demand_s:.2f} s)")
    print(f"Placement : {place_s:.2f} s ; k = {out['k']} ; points après fusion : {len(out['points'])} ; "
          f"accès : {dict(Counter(p['access'] for p in out['points']))}")
    print(f"Part de la demande à moins de {cfg['model']['precollect_radius_m']} m : {out['walk_share']:.1%}")
    for w in demand["warnings"] + out["warnings"]:
        print("AVERTISSEMENT :", w)


if __name__ == "__main__":
    main()
