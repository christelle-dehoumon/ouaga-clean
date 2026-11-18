"""Mesures reproductibles du membre A, écrites dans docs/mesures.md (python -m scripts.bench).

Chaque ligne : temps médian sur RUNS essais (sauf limite annoncée), sur la machine qui lance le script.
Les signalements utilisés sont synthétiques (scripts/make_synthetic.py, graine fixe)."""

from __future__ import annotations

import copy
import os
import platform
import statistics
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from sklearn.cluster import KMeans

from core.config import load_config
from core.geo.buildings import building_demand
from core.geo.download import REPO_ROOT
from core.geo.graph import Network, load_network, project
from core.optim.matrix import MatrixCache
from core.optim.placement import SEED, _cells
from core.config import config_path
from core.optim.plan import compute_plan
from scripts.make_synthetic import plausible_reports

RUNS = 5
N_SOURCES = 60
K_SAME = 46
REPORT_SIZES = (100, 1_000, 10_000)
POINT_COUNTS = (46, 120)
# Matrice sur n signalements : au-delà de ce nombre de sources, un seul essai (durée), et pas du tout au-delà de MATRIX_N_MAX.
MATRIX_N_ONE_RUN = 1_000
MATRIX_N_MAX = 1_000
CHUNK = 100
OUT = REPO_ROOT / "docs" / "mesures.md"


def timed(fn: Callable[[], Any], runs: int = RUNS) -> tuple[float, Any]:
    """Médiane des durées de runs appels et dernier résultat."""
    times, result = [], None
    for _ in range(runs):
        t = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t)
    return statistics.median(times), result


def machine() -> str:
    """Processeur, cœurs, système, Python."""
    cpu = platform.processor() or "inconnu"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return f"{cpu}, {os.cpu_count()} cœurs logiques, {platform.system()} {platform.release()}, Python {platform.python_version()}"


def served(plan: dict[str, Any]) -> str:
    """Résumé d'un plan : mode, points servis sur total."""
    return f"{plan['mode']}, {plan['totals']['points_served']}/{len(plan['collection_points'])} points servis"


def bench_dijkstra(net: Network, rows: list[list[str]]) -> None:
    """1. Dijkstra 60 sources, vue truck_dry : NetworkX (une source à la fois) contre SciPy (un appel)."""
    import networkx as nx

    view = net.views["truck_dry"]
    src = np.random.default_rng(SEED).choice(view.tree_idx, N_SOURCES, replace=False)
    t = time.perf_counter()
    graph = nx.from_scipy_sparse_array(view.matrix, create_using=nx.DiGraph)
    build = time.perf_counter() - t
    nx_s, nx_first = timed(lambda: [nx.single_source_dijkstra_path_length(graph, int(s), weight="weight") for s in src][0])
    sp_s, sp = timed(lambda: dijkstra(view.matrix, directed=True, indices=src))
    keys = np.fromiter(nx_first.keys(), dtype=np.int64)
    gap = float(np.max(np.abs(sp[0][keys] - np.fromiter(nx_first.values(), dtype=float))))
    rows.append(["1. Dijkstra 60 sources", "NetworkX, une source à la fois", f"{nx_s:.2f} s",
                 f"graphe NetworkX construit à part en {build:.2f} s", ""])
    rows.append(["", "SciPy, un appel", f"{sp_s:.2f} s", f"écart max des distances {gap:.3f} m",
                 f"Même vue, mêmes sources : SciPy prend {nx_s / sp_s:.1f} fois moins de temps que NetworkX sur cette machine."])


def bench_placement(cfg: dict[str, Any], net: Network, rows: list[list[str]]) -> None:
    """2. KMeans k = 46 sur les bâtiments de la zone pilote contre sur les cellules de 100 m."""
    demand = building_demand(cfg, cfg["params"])
    origin = (float(net.lat.mean()), float(net.lon.mean()))
    xy, kg = project(demand["lat"], demand["lon"], origin), demand["kg"]
    radius = cfg["model"]["precollect_radius_m"]
    cell = cfg["model"]["cell_size_m"]

    def fit(points: np.ndarray, w: np.ndarray) -> np.ndarray:
        """Centres KMeans pondéré, k fixe."""
        return KMeans(n_clusters=K_SAME, n_init=1, random_state=SEED).fit(points, sample_weight=w).cluster_centers_

    def share(centers: np.ndarray) -> float:
        """Part de la demande des bâtiments à moins du rayon."""
        d, _ = cKDTree(centers).query(xy)
        return float(kg[d <= radius].sum() / kg.sum())

    b_s, b_centers = timed(lambda: fit(xy, kg))
    c_s, c_centers = timed(lambda: fit(*_cells(xy, kg, cell)))
    n_cells = len(_cells(xy, kg, cell)[0])
    rows.append(["2. Placement, k = 46", f"KMeans sur {len(xy)} bâtiments", f"{b_s:.2f} s",
                 f"{share(b_centers):.1%} de la demande à moins de {radius:g} m", ""])
    rows.append(["", f"KMeans sur {n_cells} cellules de {cell:g} m", f"{c_s:.2f} s",
                 f"{share(c_centers):.1%} de la demande à moins de {radius:g} m",
                 f"Même zone et même k : les cellules prennent {b_s / c_s:.1f} fois moins de temps, couverture mesurée "
                 "dans la colonne Résultat."])


def bench_matrix(net: Network, plan: dict[str, Any], rows: list[list[str]]) -> None:
    """3. Matrice dépôt + points du plan : cache vide contre cache rempli."""
    nodes = [int(p["id"][2:]) for p in plan["collection_points"] if p["id"].startswith("c_")]
    coords = [(p["lat"], p["lon"]) for p in plan["collection_points"] if p["id"].startswith("c_")]
    cold_s, _ = timed(lambda: MatrixCache().matrix(net, "truck_dry", nodes, coords, 1.4))
    warm = MatrixCache()
    warm.matrix(net, "truck_dry", nodes, coords, 1.4)
    before = warm.dijkstra_calls
    warm_s, _ = timed(lambda: warm.matrix(net, "truck_dry", nodes, coords, 1.4))
    rows.append([f"3. Matrice {len(nodes)} × {len(nodes)}", "à froid (cache vide)", f"{cold_s:.3f} s", "1 appel Dijkstra", ""])
    rows.append(["", "cache rempli", f"{warm_s:.3f} s", f"{warm.dijkstra_calls - before} appel Dijkstra",
                 "Avec le cache, la matrice est relue sans Dijkstra ; il reste le temps de lecture des lignes."])


def bench_breakdown(params: dict[str, Any], base: dict[str, Any], rows: list[list[str]]) -> None:
    """4. Panne de truck2 : calcul complet contre recalcul partiel."""
    broken = {**params, "broken_trucks": ["truck2"]}
    full_s, full = timed(lambda: compute_plan(broken, []))
    part_s, part = timed(lambda: compute_plan(broken, [], previous_plan=base))
    rows.append(["4. Panne de truck2", "calcul complet", f"{full_s:.2f} s", served(full), ""])
    rows.append(["", "recalcul partiel", f"{part_s:.2f} s", served(part),
                 "Le mode et le nombre de points servis sont ceux du plan gardé (le partiel lance aussi le complet "
                 "s'il laisse des points non servis)."])


def bench_reports(cfg: dict[str, Any], net: Network, params: dict[str, Any], base: dict[str, Any],
                  rows: list[list[str]]) -> None:
    """5. Ajout de 20 signalements : calcul complet contre recalcul partiel."""
    reports = plausible_reports(cfg, net, 20, "accepted")
    full_s, full = timed(lambda: compute_plan(params, reports))
    part_s, part = timed(lambda: compute_plan(params, reports, previous_plan=base))
    rows.append(["5. +20 signalements", "calcul complet", f"{full_s:.2f} s", served(full), ""])
    rows.append(["", "recalcul partiel", f"{part_s:.2f} s", served(part),
                 f"Partiel {part_s:.2f} s contre complet {full_s:.2f} s ; le partiel lance aussi le complet s'il laisse "
                 "des points non servis, d'où un temps qui peut dépasser celui du complet."])


def _matrix_on_n(net: Network, report_nodes: np.ndarray) -> None:
    """Matrice n × n entre signalements, par paquets de sources (mémoire bornée)."""
    view = net.views["truck_dry"]
    for i in range(0, len(report_nodes), CHUNK):
        dist = dijkstra(view.matrix, directed=True, indices=report_nodes[i:i + CHUNK])
        _ = dist[:, report_nodes]


def bench_scale(cfg: dict[str, Any], net: Network, params: dict[str, Any], rows: list[list[str]]) -> None:
    """6. Passage à l'échelle : 100 / 1 000 / 10 000 signalements, puis 46 et 120 points."""
    view = net.views["truck_dry"]
    no_pre = copy.deepcopy(cfg)
    no_pre["solver"]["preselect_capacity_factor"] = 1e12      # présélection neutralisée : la mesure « avant »
    for n in REPORT_SIZES:
        reports = plausible_reports(cfg, net, n, "accepted")
        before_s, before = timed(lambda: compute_plan(params, reports, cfg=no_pre, net=net))
        plan_s, plan = timed(lambda: compute_plan(params, reports, cfg=cfg, net=net))
        dumps = sum(p["type"] == "dumpsite" for p in plan["collection_points"])
        rows.append([f"6. {n} signalements", "compute_plan sans présélection (avant)", f"{before_s:.2f} s",
                     f"{dumps} arrêts dépotoirs ; {served(before)}", ""])
        rows.append(["", "compute_plan avec présélection et remplissage (après, matrice sur k)", f"{plan_s:.2f} s",
                     f"{len(reports)} signalements -> {dumps} arrêts dépotoirs ; {served(plan)} ; "
                     f"camions nécessaires (estimation) : {plan['totals'].get('trucks_needed')}",
                     f"Avant / après présélection et remplissage : {before_s:.2f} s -> {plan_s:.2f} s."])
        if n <= MATRIX_N_MAX:
            nodes = np.array([int(view.tree_idx[view.tree.query(project(np.array([r["lat"]]), np.array([r["lon"]]),
                                                                          view.origin)[0])[1]]) for r in reports])
            runs = 1 if n >= MATRIX_N_ONE_RUN else RUNS
            m_s, _ = timed(lambda: _matrix_on_n(net, nodes), runs)
            rows.append(["", f"matrice sur n = {n} signalements", f"{m_s:.2f} s",
                         f"{runs} essai(s)" + (" (limité : durée)" if runs < RUNS else ""), ""])
        else:
            rows.append(["", f"matrice sur n = {n} signalements", "non mesuré",
                         f"limité : {n} sources Dijkstra, trop long pour ce banc", ""])
    rows[-1][4] = ("compute_plan ne calcule la matrice que sur les arrêts (k), regroupés au-delà de "
                   "solver.max_dumpsite_stops ; la matrice sur n est mesurée à part pour comparer.")
    reports = plausible_reports(cfg, net, REPORT_SIZES[0], "accepted")
    zero_s, zero = timed(lambda: compute_plan({**params, "population": 0}, reports, cfg=cfg, net=net))
    rows.append(["6. population 0", f"compute_plan, {len(reports)} signalements", f"{zero_s:.2f} s",
                 f"{served(zero)} ; {sum(p['type'] == 'center' for p in zero['collection_points'])} centre(s) ; "
                 f"contrôles {'au vert' if all(v for k, v in zero['checks'].items() if k != 'messages') else 'en échec'}",
                 "Population 0 sur le vrai réseau : seuls les dépotoirs sont servis."])
    for k in POINT_COUNTS:
        c = copy.deepcopy(cfg)
        c["solver"]["min_collection_points"] = c["solver"]["max_collection_points"] = k
        k_s, plan = timed(lambda: compute_plan(params, [], cfg=c, net=net))
        rows.append([f"6. {k} points imposés", "compute_plan", f"{k_s:.2f} s", served(plan),
                     "" if k != POINT_COUNTS[-1] else "Même zone, k imposé ; médiane qui inclut le premier essai à cache froid."])


def bench_default(cfg: dict[str, Any], rows: list[list[str]]) -> None:
    """0. Plan par défaut (paramètres de la configuration, sans signalement) : part servie et indicateur global."""
    secs, plan = timed(lambda: compute_plan(cfg["params"], []))
    n = len(plan["collection_points"])
    served = n - len(plan["unserved"])
    rows.append(["0. Plan par défaut", "compute_plan(config.params, [])", f"{secs:.2f} s",
                 f"{plan['mode']}, {served}/{n} points servis ({served / n:.1%}) ; checks.ok = {plan['checks']['ok']} ; "
                 f"unserved_ratio = {plan['checks']['unserved_ratio']}" if n else f"{plan['mode']}, aucun point",
                 "Critère de cohérence : au moins 90 % des points servis et checks.ok vrai."])


def main() -> None:
    """Lance les mesures et écrit docs/mesures.md."""
    started = datetime.now(timezone.utc)
    cfg = load_config(config_path())
    t = time.perf_counter()
    plan = compute_plan(cfg["params"], [])          # charge le réseau une fois (gardé en mémoire par core.optim.plan)
    load_s = time.perf_counter() - t
    from core.optim import plan as plan_mod
    net = plan_mod._STATE["net"]
    params = cfg["params"]
    rows: list[list[str]] = []
    for step in (lambda: bench_default(cfg, rows), lambda: bench_dijkstra(net, rows), lambda: bench_placement(cfg, net, rows),
                 lambda: bench_matrix(net, plan, rows), lambda: bench_breakdown(params, plan, rows),
                 lambda: bench_reports(cfg, net, params, plan, rows), lambda: bench_scale(cfg, net, params, rows)):
        step()
        print(rows[-1][:4], flush=True)
    lines = [
        "# Mesures reproductibles",
        "",
        f"Générées le {started.strftime('%Y-%m-%d %H:%M')} UTC par `python -m scripts.bench` (relançable, une commande).",
        f"Machine : {machine()}.",
        f"Temps médian sur {RUNS} essais sauf mention ; réseau chargé une fois avant les mesures "
        f"(premier calcul complet, chargement compris : {load_s:.1f} s). Secteur pilote, configuration du dépôt.",
        "Signalements : synthétiques (`scripts/make_synthetic.py`, graine fixe), statut accepted. Valeurs `observed` sur cette machine.",
        "",
        "| Mesure | Variante | Médiane | Résultat | Ce que ça montre |",
        "|---|---|---|---|---|",
    ] + ["| " + " | ".join(r) + " |" for r in rows] + [""]
    from scripts.bench_blur import markdown, measure
    lines += markdown(measure())
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Écrit {OUT} en {(datetime.now(timezone.utc) - started).total_seconds():.0f} s.")


if __name__ == "__main__":
    main()
