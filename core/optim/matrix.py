"""Matrice de distances entre points de regroupement et dépôt, avec cache par (vue, nœud source) (section 7 des règles)."""

from __future__ import annotations

import math
import numpy as np
from scipy.sparse.csgraph import dijkstra

from core.geo.graph import EARTH_RADIUS_M, Network


def straight_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance à vol d'oiseau (haversine) en mètres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


class MatrixCache:
    """Lignes de Dijkstra (poids de la vue + prédécesseurs) gardées en mémoire, clé = (vue, nœud source)."""

    def __init__(self) -> None:
        """Cache vide ; compteurs d'appels SciPy et de sources calculées."""
        self.rows: dict[tuple[str, int], tuple[np.ndarray, np.ndarray]] = {}
        self.dijkstra_calls = 0
        self.sources_computed = 0

    def _fill(self, net: Network, view_name: str, nodes: list[int]) -> None:
        """Calcule en un seul appel Dijkstra les sources de la vue absentes du cache."""
        view = net.views[view_name]
        missing = sorted({n for n in nodes if (view_name, n) not in self.rows
                          and n in net.index_of and view.node_mask[net.index_of[n]]})
        if not missing:
            return
        idx = np.array([net.index_of[n] for n in missing], dtype=np.int32)
        dist, pred = dijkstra(view.matrix, directed=True, indices=idx, return_predecessors=True)
        self.dijkstra_calls += 1
        self.sources_computed += len(missing)
        for i, n in enumerate(missing):
            self.rows[(view_name, n)] = (dist[i], pred[i].astype(np.int32))

    def matrix(self, net: Network, view_name: str, nodes: list[int | None], coords: list[tuple[float, float]],
               factor: float) -> tuple[np.ndarray, list[str]]:
        """Matrice n × n des poids de la vue (mètres, ou mètres équivalents en pluie) ; vol d'oiseau × factor sans chemin."""
        warnings: list[str] = []
        self._fill(net, view_name, [n for n in nodes if n is not None])
        size = len(nodes)
        out = np.zeros((size, size))
        cols = np.array([net.index_of.get(n, -1) if n is not None else -1 for n in nodes], dtype=np.int64)
        fallback = 0
        for i, a in enumerate(nodes):
            row = self.rows.get((view_name, a)) if a is not None else None
            for j in range(size):
                if i == j:
                    continue
                d = row[0][cols[j]] if row is not None and cols[j] >= 0 else math.inf
                if not math.isfinite(d):
                    d = straight_m(*coords[i], *coords[j]) * factor
                    fallback += 1
                out[i, j] = d
        if fallback:
            warnings.append(f"{fallback} trajet(s) sans chemin dans la vue « {view_name} » : distance à vol d'oiseau "
                            f"× {factor:g} (network.straight_line_factor).")
        return out, warnings

    def path(self, net: Network, view_name: str, a: int | None, b: int | None) -> list[int] | None:
        """Indices des nœuds du plus court chemin de a à b (depuis le cache), None si inconnu."""
        row = self.rows.get((view_name, a)) if a is not None else None
        if row is None or b not in net.index_of:
            return None
        target, src = net.index_of[b], net.index_of[a]
        if not math.isfinite(row[0][target]):
            return None
        seq = [target]
        while seq[-1] != src:
            prev = int(row[1][seq[-1]])
            if prev < 0:
                return None
            seq.append(prev)
        return seq[::-1]


def path_length_m(net: Network, view_name: str, seq: list[int]) -> float:
    """Longueur réelle (mètres) d'une suite d'indices de nœuds dans la vue."""
    length = net.views[view_name].length
    return float(sum(length[u, v] for u, v in zip(seq[:-1], seq[1:])))


def straight_matrix(coords: list[tuple[float, float]], factor: float) -> np.ndarray:
    """Matrice de secours : vol d'oiseau × factor, sans réseau."""
    size = len(coords)
    out = np.zeros((size, size))
    for i in range(size):
        for j in range(size):
            if i != j:
                out[i, j] = straight_m(*coords[i], *coords[j]) * factor
    return out

