"""Mesure le chargement des quatre vues, la mémoire, la taille des vues et un Dijkstra multi-sources (python -m scripts.measure_network)."""

from __future__ import annotations

import argparse
import resource
import time

import numpy as np

from core.config import load_config
from core.geo.graph import Network, load_network, shortest_paths


def _view_bytes(net: Network) -> dict[str, int]:
    """Octets occupés par la matrice CSR, les masques et l'index spatial de chaque vue."""
    out = {}
    for name, v in net.views.items():
        m = v.matrix
        tree = v.tree.data.nbytes * 2 if v.tree is not None else 0   # données + copie interne de l'arbre (ordre de grandeur)
        out[name] = m.data.nbytes + m.indices.nbytes + m.indptr.nbytes + v.edge_mask.nbytes + v.node_mask.nbytes \
            + v.tree_idx.nbytes + tree
    return out


def main() -> None:
    """Affiche les mesures en Markdown."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/commune_config.json")
    parser.add_argument("--sources", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    cfg = load_config(args.config)
    t0 = time.perf_counter()
    net = load_network(cfg)
    load_s = time.perf_counter() - t0
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"Chargement pickle + 4 vues : {load_s:.2f} s ; mémoire max du processus : {rss_mb:.0f} Mo")
    for w in net.warnings:
        print("AVERTISSEMENT :", w)
    sizes = _view_bytes(net)
    print("| Vue | Nœuds | Arêtes orientées | Mémoire propre |\n|---|---|---|---|")
    for name, v in net.views.items():
        print(f"| {name} | {v.n_nodes} | {v.n_edges} | {sizes[name] / 2**20:.1f} Mo |")
    print("Pluie :", ", ".join(f"{k} = {v}" for k, v in net.stats.items()))
    view = net.views["truck_dry"]
    rng = np.random.default_rng(args.seed)
    src = [int(s) for s in rng.choice(view.node_ids[view.node_mask], size=args.sources, replace=False)]
    times = []
    for _ in range(3):
        t = time.perf_counter()
        dist, _, kept = shortest_paths(view, net.index_of, src)
        times.append(time.perf_counter() - t)
    print(f"Dijkstra {len(kept)} sources, truck_dry, un seul appel : min {min(times):.2f} s, "
          f"médiane {sorted(times)[1]:.2f} s sur 3 essais ; atteignables par source : {int(np.isfinite(dist[0]).sum())}")
    for a in net.assumptions:
        print("HYPOTHÈSE :", a)


if __name__ == "__main__":
    main()
