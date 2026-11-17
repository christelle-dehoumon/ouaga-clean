"""Chargement et validation de config/commune_config.json, sans jamais lever d'exception."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

# Valeurs de repli utilisées seulement si une clé manque ou est absurde (un avertissement est alors émis).
# Aucune coordonnée ici : sans emprise valide, les modules géographiques refusent de travailler.
SAFE_DEFAULTS: dict[str, Any] = {
    "commune": None,
    "place_query": None,
    "bbox": None,
    "depot": {"lat": None, "lon": None},
    "paths": {
        "raw_dir": "data/raw",
        "processed_dir": "data/processed",
        "mock_dir": "data/mock",
        "territories": "data/processed/territories.geojson",
        "flood_zones": "data/processed/flood_zones.geojson",
        "waterways": "data/processed/waterways.geojson",
    },
    "params": {
        "population": 0,
        "subscription_rate": 0.0,
        "trucks": 0,
        "truck_capacity_kg": 0,
        "tricycles": 0,
        "tricycle_capacity_kg": 0,
        "frequency_per_week": 1,
        "budget": 0,
        "rainy_season": False,
        "broken_trucks": [],
        "extra_territories": [],
    },
    "model": {
        "waste_kg_per_person_day": 0.0,
        "persons_per_building": 1,
        "precollect_radius_m": 1500,
        "walk_coverage_target": 0.9,
        "truck_trips_per_day": 1,
        "cell_size_m": 100,
        "pilot_territory_ids": [],
        "pilot_square_m": 5000,
        "resnap_max_m": 300,
        "cost_per_km_truck": 0,
        "cost_per_km_tricycle": 0,
        "truck_speed_kmh": 20,
        "tricycle_speed_kmh": 10,
        "service_min_per_stop": 10,
        "shift_minutes": 480,
        "dumpsite_kg_by_size": {"small": 0, "medium": 0, "large": 0},
    },
    "network": {
        "truck_highways": [],
        "tricycle_extra_highways": [],
        "unpaved_surfaces": [],
        "unknown_surface_is_paved_for": [],
        "straight_line_factor": 1.4,
        "rain_unpaved_factor": 2.5,
        "flood_buffer_m": 30,
        "flood_waterway_types": [],
    },
    "solver": {
        "time_limit_s": 5,
        "max_collection_points": 60,
        "max_dumpsite_stops": 60,
        "min_collection_points": 1,
        "preselect_capacity_factor": 1.2,
    },
}

# Clés numériques qui doivent être strictement positives (zéro n'a pas de sens physique).
STRICTLY_POSITIVE: frozenset[str] = frozenset({
    "model.persons_per_building", "model.precollect_radius_m", "model.truck_trips_per_day", "model.cell_size_m",
    "model.pilot_square_m", "model.resnap_max_m", "solver.max_dumpsite_stops", "solver.preselect_capacity_factor", "model.truck_speed_kmh", "model.tricycle_speed_kmh",
    "model.shift_minutes", "network.straight_line_factor", "network.rain_unpaved_factor", "solver.time_limit_s",
    "solver.max_collection_points", "solver.min_collection_points", "params.frequency_per_week",
})
# Clés numériques bornées à [0, 1].
FRACTIONS: frozenset[str] = frozenset({"params.subscription_rate", "model.walk_coverage_target"})


def _is_number(value: Any) -> bool:
    """Vrai pour un int ou un float fini, faux pour un booléen."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf")


def _check_value(key: str, value: Any, default: Any, warnings: list[str]) -> Any:
    """Renvoie value si son type et sa plage conviennent, sinon default avec un avertissement."""
    if default is None:
        return value
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
    elif isinstance(default, (int, float)):
        if _is_number(value):
            if value < 0 or (key in STRICTLY_POSITIVE and value == 0) or (key in FRACTIONS and value > 1):
                warnings.append(f"Valeur hors plage pour « {key} » ({value!r}) : valeur de repli {default!r} utilisée.")
                return default
            return value
    elif isinstance(default, list):
        if isinstance(value, list):
            return value
    elif isinstance(default, str):
        if isinstance(value, str) and value:
            return value
    warnings.append(f"Type invalide pour « {key} » ({value!r}) : valeur de repli {default!r} utilisée.")
    return default


def _merge(raw: dict[str, Any], defaults: dict[str, Any], prefix: str, warnings: list[str]) -> dict[str, Any]:
    """Fusionne raw sur defaults, récursivement, en validant chaque clé connue."""
    out: dict[str, Any] = {k: v for k, v in raw.items() if k not in defaults}
    for key, default in defaults.items():
        full = f"{prefix}{key}"
        if key not in raw:
            warnings.append(f"Clé manquante « {full} » : valeur de repli {default!r} utilisée.")
            out[key] = copy.deepcopy(default)
        elif isinstance(default, dict):
            value = raw[key]
            if isinstance(value, dict):
                out[key] = _merge(value, default, f"{full}.", warnings)
            else:
                warnings.append(f"« {full} » devrait être un objet : valeurs de repli utilisées.")
                out[key] = copy.deepcopy(default)
        else:
            out[key] = _check_value(full, raw[key], default, warnings)
    return out


def _valid_bbox(bbox: Any) -> bool:
    """Vrai si bbox a quatre bornes numériques cohérentes en WGS84."""
    if not isinstance(bbox, dict) or not all(_is_number(bbox.get(k)) for k in ("west", "south", "east", "north")):
        return False
    return -180 <= bbox["west"] < bbox["east"] <= 180 and -90 <= bbox["south"] < bbox["north"] <= 90


def _check_cross_fields(cfg: dict[str, Any], warnings: list[str]) -> None:
    """Contrôles qui portent sur plusieurs clés à la fois."""
    if not _valid_bbox(cfg.get("bbox")):
        if cfg.get("bbox") is not None:
            warnings.append("Emprise « bbox » invalide (bornes manquantes ou incohérentes) : ignorée.")
        cfg["bbox"] = None
    if not isinstance(cfg.get("place_query"), str) or not cfg["place_query"].strip():
        cfg["place_query"] = None
    depot = cfg["depot"]
    lat, lon = depot.get("lat"), depot.get("lon")
    if lat is not None or lon is not None:
        if not (_is_number(lat) and _is_number(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            warnings.append("Dépôt invalide : le nœud routier le plus central sera utilisé.")
            depot["lat"], depot["lon"] = None, None
    solver = cfg["solver"]
    if solver["min_collection_points"] > solver["max_collection_points"]:
        warnings.append("« solver.min_collection_points » dépasse le maximum : les deux bornes sont inversées.")
        solver["min_collection_points"], solver["max_collection_points"] = (
            solver["max_collection_points"], solver["min_collection_points"])
    params = cfg["params"]
    if not all(isinstance(t, str) for t in params["broken_trucks"]):
        warnings.append("« params.broken_trucks » doit être une liste d'identifiants : liste vidée.")
        params["broken_trucks"] = []


def load_config(path: str | Path) -> dict[str, Any]:
    """Lit la configuration, remplace toute valeur manquante ou absurde, et range les avertissements dans « _warnings »."""
    warnings: list[str] = []
    raw: Any = {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        warnings.append(f"Fichier de configuration introuvable : {path}. Valeurs de repli utilisées.")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        warnings.append(f"Fichier de configuration illisible ({path}) : {exc}. Valeurs de repli utilisées.")
    if not isinstance(raw, dict):
        warnings.append("La configuration doit être un objet JSON : valeurs de repli utilisées.")
        raw = {}
    cfg = _merge(raw, SAFE_DEFAULTS, "", warnings)
    _check_cross_fields(cfg, warnings)
    cfg["_warnings"] = warnings
    return cfg
