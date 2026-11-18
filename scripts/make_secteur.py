"""Écrit paths.secteur (data/secteur.geojson) : secteur de l'équipe, par défaut le carré pilote de la configuration.

    python -m scripts.make_secteur        # à refaire seulement si model.pilot_square_m ou la commune change
Le fichier peut ensuite être ajusté à la main (polygone du vrai secteur) : le tri (HORS_SECTEUR) et le plan
(territoire « pilot ») le lisent directement.
"""

from __future__ import annotations

import json
import sys

import numpy as np
from shapely.geometry import mapping

from core.config import config_path, load_config, resolve
from core.geo.territories import _pilot_square


def main() -> int:
    cfg = load_config(config_path())
    square = _pilot_square(cfg, np.zeros(0), np.zeros(0), [])
    if square is None:
        print("Secteur impossible : ni limite communale ni emprise.")
        return 1
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": mapping(square), "properties": {
        "id": "pilot", "nom": "Secteur de l'équipe (carré pilote par défaut)",
        "method": f"carré de {cfg['model']['pilot_square_m']} m centré sur la commune ; à remplacer par le vrai secteur"}}]}
    path = resolve(cfg["paths"]["secteur"])
    path.write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Secteur écrit : {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
