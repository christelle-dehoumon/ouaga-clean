"""core.geo.territories : ajout d'un quartier, refus clairs sans exception."""

import json
from pathlib import Path

from core.config import load_config
from core.geo.territories import add_territory

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "commune_config.json"


def test_add_territory(tmp_path: Path) -> None:
    """Quartier valide enregistré (remplacé s'il existe) ; invalide ou hors commune refusé avec un message."""
    cfg = load_config(REPO_CONFIG)
    cfg["paths"].update({"raw_dir": str(tmp_path), "territories": str(tmp_path / "t.geojson")})
    cfg["bbox"] = {"west": -1.1, "south": 11.9, "east": -0.9, "north": 12.1}
    square = {"type": "Polygon", "coordinates": [[[-1.0, 12.0], [-0.99, 12.0], [-0.99, 12.01], [-1.0, 12.0]]]}
    feature = {"type": "Feature", "properties": {"id": "q1"}, "geometry": square}
    assert add_territory(cfg, feature) == ("q1", [])
    assert add_territory(cfg, feature) == ("q1", [])
    assert len(json.loads((tmp_path / "t.geojson").read_text())["features"]) == 1
    far = {**feature, "geometry": {"type": "Polygon", "coordinates": [[[5, 20], [5.1, 20], [5.1, 20.1], [5, 20]]]}}
    for bad, text in ((far, "hors de la commune"), ({"type": "Feature"}, "Feature GeoJSON"), ("abc", "Feature GeoJSON")):
        tid, warnings = add_territory(cfg, bad)
        assert tid is None and text in warnings[0]
