"""Scénarios du rapport technique, recalculés à la demande : python -m scripts.scenarios_rapport

Écrit docs/scenarios.md : plan de gestion de la zone pilote (paramètres de la configuration) et scénarios de l'épreuve
en direct (panne, pluie, nouveau quartier, flotte réduite), avec la simulation multi-agents de 7 jours (graine 0).
Les signalements ne sont pas utilisés : seuls les points de regroupement issus des bâtiments sont planifiés.
"""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from pathlib import Path

from core.config import config_path, get_config
from core.optim.events import plan_with_events
from core.sim.model import MOTEUR, run_scenario

OUT = Path(__file__).resolve().parents[1] / "docs" / "scenarios.md"
MODE = {"optimized": "complet", "partial": "partiel", "fallback": "secours"}


def n(x: float, d: int = 0) -> str:
    """Nombre à la française : espace pour les milliers, virgule décimale."""
    return f"{x:,.{d}f}".replace(",", "\u202f").replace(".", ",")


def ligne(nom: str, plan: dict, sim: dict) -> str:
    ch = plan["checks"]
    n_pts = len(plan["collection_points"])
    camions = len({r["vehicle"].split("_trip")[0] for r in plan["routes"]})
    servis = n_pts - ch["unserved_count"] - ch.get("postponed_count", 0)
    part = f"{n(sim['part_ramassee'] * 100, 1)} %" if sim.get("part_ramassee") is not None else "—"
    return (f"| {nom} | {MODE.get(plan['mode'], plan['mode'])} | {servis}/{n_pts} | {ch['unserved_count']} | {ch.get('postponed_count', 0)} | "
            f"{camions} | {n(plan['totals']['distance_km'], 1)} | {n(plan['totals']['cost'])} | {n(plan['totals']['collected_kg'] / 1000, 1)} | "
            f"{plan['compute_ms']} | {part} | {sim.get('depotoirs_restants', '—')} | {n(sim.get('cout_fcfa', 0))} | {'oui' if ch['ok'] else 'non'} |")


def main() -> None:
    cfg = get_config()
    base = dict(cfg["params"])
    rows = []

    def run(nom, params, events=None, previous=None):
        plan = plan_with_events(params, [], events, None, previous)
        sim = run_scenario({}, plan, 7, seed=0)
        rows.append(ligne(nom, plan, sim))
        return plan

    defaut = run("Défaut (configuration)", base)
    camion = sorted({r["vehicle"].split("_trip")[0] for r in defaut["routes"]})[0]
    run(f"Panne de {camion} (recalcul partiel)", base, [{"type": "truck_down", "vehicle_id": camion}], defaut)
    serre = run("Flotte réduite : 6 camions", {**base, "trucks": 6})
    camion6 = sorted({r["vehicle"].split("_trip")[0] for r in serre["routes"]})[0]
    run(f"6 camions + panne de {camion6}", {**base, "trucks": 6}, [{"type": "truck_down", "vehicle_id": camion6}], serre)
    run("Saison des pluies", base, [{"type": "rain"}])
    run("Pluie + nouveau quartier Kalgodin", base, [{"type": "rain"}, {"type": "new_district", "territory_id": "kalgodin"}])
    run("Nouveau quartier Paglayiri", base, [{"type": "new_district", "territory_id": "paglayiri"}])

    routes = [r for r in defaut["routes"]]
    lines = [
        "# Scénarios et plan de gestion de la zone pilote",
        "",
        f"Générés le {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC par `python -m scripts.scenarios_rapport` "
        f"({platform.processor() or platform.machine()}, Python {platform.python_version()}, simulation {MOTEUR}).",
        f"Configuration : `{config_path().name}` ({cfg.get('commune')}). Paramètres : {base['trucks']} camions de "
        f"{n(base['truck_capacity_kg'])} kg, {base['frequency_per_week']} passages par semaine, population {n(base['population'])}, "
        f"abonnement {n(base['subscription_rate'] * 100)} %, budget {n(base['budget'])} FCFA par jour de collecte.",
        "Les chiffres de la simulation reposent sur des hypothèses non mesurées (configuration, section hypotheses).",
        "",
        "| Scénario | Mode | Points servis | Non desservis | Reportés | Camions utilisés | Distance (km) | Coût d'un passage (FCFA) "
        "| Collecté par passage (t) | Calcul (ms) | Part ramassée, 7 j (simulée) | Dépotoirs restants (simulés) | Coût 7 j (simulé, FCFA) | checks.ok |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## Plan de gestion par défaut de la zone pilote",
        "",
        f"{len(defaut['collection_points'])} points de regroupement, {len(routes)} tournées (trajets de camions), "
        f"{n(defaut['totals']['distance_km'], 1)} km, coût d'un passage {n(defaut['totals']['cost'])} FCFA, "
        f"{n(defaut['totals']['collected_kg'] / 1000, 1)} t collectées par passage ; masse non collectée (ménages non abonnés) "
        f"{n(defaut['totals']['uncollected_kg'] / 1000, 1)} t par passage.",
        "",
        "| Trajet | Arrêts | Distance (km) | Durée (min) | Charge (kg) |",
        "|---|---|---|---|---|",
        *[f"| {r['vehicle']} | {len(r['stops'])} | {n(r['distance_km'], 1)} | {n(r['duration_min'])} | {n(r['load_kg'])} |" for r in routes],
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    main()
