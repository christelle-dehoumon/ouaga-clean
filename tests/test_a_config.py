"""Tests de core.config.load_config : jamais d'exception, replis signalés."""

import json
from pathlib import Path

from core.config import load_config

REAL_CONFIG = Path(__file__).resolve().parents[1] / "config" / "commune_config.json"


def _write(tmp_path: Path, content: str) -> Path:
    """Écrit un fichier de configuration temporaire."""
    path = tmp_path / "cfg.json"
    path.write_text(content, encoding="utf-8")
    return path


def test_real_config_loads_without_warning() -> None:
    """La configuration du dépôt se charge sans aucun repli."""
    cfg = load_config(REAL_CONFIG)
    assert cfg["_warnings"] == []
    assert cfg["params"]["trucks"] == json.loads(REAL_CONFIG.read_text(encoding="utf-8"))["params"]["trucks"]
    assert cfg["bbox"] is not None


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    """Un fichier absent donne des valeurs de repli et un avertissement."""
    cfg = load_config(tmp_path / "absent.json")
    assert cfg["_warnings"]
    assert cfg["bbox"] is None and cfg["place_query"] is None


def test_invalid_json_and_non_object(tmp_path: Path) -> None:
    """Un JSON cassé ou une liste ne fait pas planter."""
    assert load_config(_write(tmp_path, "{pas du json"))["_warnings"]
    assert load_config(_write(tmp_path, "[1, 2]"))["_warnings"]


def test_absurd_values_replaced(tmp_path: Path) -> None:
    """Valeurs négatives, mauvais types et emprise incohérente sont remplacés."""
    raw = json.loads(REAL_CONFIG.read_text(encoding="utf-8"))
    raw["params"]["trucks"] = -3
    raw["params"]["budget"] = "abc"
    raw["params"]["rainy_season"] = "oui"
    raw["params"]["subscription_rate"] = 4
    raw["bbox"] = {"west": 1, "south": 2, "east": 0, "north": 3}
    raw["depot"] = {"lat": 200, "lon": 0}
    cfg = load_config(_write(tmp_path, json.dumps(raw)))
    assert cfg["params"]["trucks"] >= 0
    assert isinstance(cfg["params"]["budget"], (int, float))
    assert isinstance(cfg["params"]["rainy_season"], bool)
    assert 0 <= cfg["params"]["subscription_rate"] <= 1
    assert cfg["bbox"] is None
    assert cfg["depot"] == {"lat": None, "lon": None}
    assert len(cfg["_warnings"]) >= 6


def test_missing_section_and_inverted_bounds(tmp_path: Path) -> None:
    """Une section absente est complétée, des bornes inversées sont remises dans l'ordre."""
    raw = json.loads(REAL_CONFIG.read_text(encoding="utf-8"))
    del raw["model"]
    raw["solver"]["min_collection_points"], raw["solver"]["max_collection_points"] = 50, 5
    cfg = load_config(_write(tmp_path, json.dumps(raw)))
    assert "precollect_radius_m" in cfg["model"]
    assert cfg["solver"]["min_collection_points"] <= cfg["solver"]["max_collection_points"]
