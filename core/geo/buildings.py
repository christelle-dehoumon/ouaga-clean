"""Bâtiments OSM et demande estimée par bâtiment, recalée sur la population (étiquette « estimated »)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from core.geo.download import BUILDINGS_FILE, REPO_ROOT
from core.geo.territories import active_territories, assign

DAYS_PER_WEEK = 7


def _num(value: Any, default: float) -> float:
    """Nombre fini positif ou nul, sinon default."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return default
    return float(value)


def load_buildings(cfg: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Centres des bâtiments (lat, lon) lus dans data/processed/ ; tableaux vides et message si absents."""
    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    processed = str(paths.get("processed_dir", "data/processed"))
    path = (Path(processed) if Path(processed).is_absolute() else REPO_ROOT / processed) / BUILDINGS_FILE
    empty = np.zeros(0)
    if not path.exists():
        return empty, empty, [f"Bâtiments introuvables ({path}) : lancer une fois « python -m core.geo.download »."]
    try:
        with np.load(path) as data:
            lat, lon = np.asarray(data["lat"], dtype=float), np.asarray(data["lon"], dtype=float)
    except Exception as exc:  # fichier corrompu : repli sans plantage
        return empty, empty, [f"Bâtiments illisibles ({path}) : {exc}."]
    ok = np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
    return lat[ok], lon[ok], []


def _days_between(params: dict[str, Any]) -> tuple[float, float]:
    """(passages par semaine, jours entre deux passages) ; une semaine si la fréquence est absente ou nulle."""
    freq = _num(params.get("frequency_per_week"), 0.0)
    return freq, (DAYS_PER_WEEK / freq if freq > 0 else DAYS_PER_WEEK)


def estimate_demand(n_buildings: int, params: dict[str, Any], model: dict[str, Any]) -> tuple[np.ndarray, list[str]]:
    """Personnes par bâtiment : aucune si population 0, population répartie également, sinon model.persons_per_building."""
    if n_buildings <= 0:
        return np.zeros(0), []
    per_building = _num(model.get("persons_per_building"), 1.0)
    population = _num(params.get("population"), -1.0)
    if population == 0:
        return np.zeros(n_buildings), []
    if population > 0:
        persons = population / n_buildings
        return np.full(n_buildings, persons), [
            f"Population de {population:g} habitants répartie également sur les {n_buildings} bâtiments OSM de la commune : "
            f"{persons:.2f} personnes par bâtiment (au lieu de {per_building:g} dans model.persons_per_building)."]
    return np.full(n_buildings, per_building), [
        f"Population absente : {per_building:g} personnes par bâtiment (model.persons_per_building)."]


def building_demand(cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Demande par passage des bâtiments des territoires actifs (abonnés seulement) et masse non collectée."""
    params = params if isinstance(params, dict) else {}
    model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    lat, lon, warnings = load_buildings(cfg)
    persons, assumptions = estimate_demand(len(lat), params, model)
    waste = _num(model.get("waste_kg_per_person_day"), 0.0)
    rate = min(_num(params.get("subscription_rate"), 0.0), 1.0)
    freq, days = _days_between(params)
    territories, t_assumptions, t_warnings = active_territories(cfg, params, lat, lon)
    assumptions += t_assumptions
    warnings += t_warnings
    owner = assign(territories, lat, lon)
    zero = _num(params.get("population"), -1.0) == 0
    if zero:
        warnings.append("Population 0 : aucune demande des ménages, aucun point de regroupement ; "
                        "seuls les dépotoirs validés restent à servir.")
    summary = []
    for i, t in enumerate(territories):
        inside = owner == i
        n_t = int(inside.sum())
        if t["population"] is not None and n_t and not zero:
            persons[inside] = t["population"] / n_t
            pop, tag = t["population"], t["source"] or "provided"
        else:
            pop, tag = float(persons[inside].sum()), "estimated"
        summary.append({"id": t["id"], "name": t["name"], "buildings": n_t, "population": round(pop),
                        "population_tag": tag})
        if n_t == 0:
            warnings.append(f"Territoire « {t['id']} » : aucun bâtiment OSM à l'intérieur, aucune demande.")
    keep = owner >= 0
    per_person_pass = waste * days
    kg = persons[keep] * per_person_pass * rate
    uncollected = float(persons[keep].sum() * per_person_pass * (1 - rate))
    assumptions.append(f"Territoires actifs : {[s['id'] for s in summary]} (model.pilot_territory_ids + params.extra_territories) ; "
                       "population d'un territoire sans population fournie = population de la commune × part de ses bâtiments "
                       "(estimated). Le réseau routier reste celui de toute la commune.")
    assumptions.append(f"Demande par passage = population × {waste:g} kg/personne/jour × taux d'abonnement {rate:g} × "
                       f"{days:.2f} jours entre deux passages ({freq:g} par semaine) ; la part non abonnée "
                       f"({uncollected / 1000:.1f} t par passage) n'est pas collectée.")
    if freq <= 0:
        assumptions.append("Fréquence de passage absente ou nulle : une semaine entre deux passages.")
    return {"lat": lat[keep], "lon": lon[keep], "kg": kg, "territory_id": [territories[i]["id"] for i in owner[keep]],
            "territories": summary, "uncollected_kg": uncollected, "data_tag": "estimated",
            "assumptions": assumptions, "warnings": warnings}
