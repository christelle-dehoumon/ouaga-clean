"""Exports statiques des signalements RÉELS confirmés ou nettoyés (reel.db) : GeoJSON sous licence ODbL et fichier OSM.

    python -m scripts.export_geojson     # écrit data/export/signalements.geojson et data/export/depotoirs.osm
Jamais de cas simulé ; jamais d'envoi à OpenStreetMap (fichier à relire dans JOSM).
Avec --mock : convertit aussi data/mock/signalements*.json en GeoJSON étiqueté « synthetic ».
"""

from __future__ import annotations

import json
import sys

from core.config import resolve
from core.export import LICENSE, LICENSE_URL, reports_geojson, reports_osm_xml


def convert_mock() -> None:
    """Jeux fictifs JSON -> GeoJSON étiqueté synthetic, avec la licence."""
    for name in ("signalements", "signalements_pieges", "signalements_synthetiques"):
        rows = json.loads(resolve(f"data/mock/{name}.json").read_text(encoding="utf-8"))
        feats = []
        for r in rows:
            ok = all(isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool) for k in ("lat", "lon"))
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]} if ok else None,
                          "properties": {"id": r.get("id"), "date": r.get("timestamp"), "status_source": r.get("status"),
                                         "data_tag": "synthetic", "note": r.get("reason")}})
        fc = {"type": "FeatureCollection", "name": f"{name} (données SIMULÉES)", "data_tag": "synthetic",
              "license": LICENSE, "license_url": LICENSE_URL,
              "attribution": "Jeu fictif généré par scripts/make_synthetic.py (positions tirées des bâtiments OSM)",
              "features": feats}
        out = resolve(f"data/mock/{name}.geojson")
        out.write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[mock] {out} : {len(feats)} entités (synthetic)")


def main() -> int:
    out = resolve("data/export")
    out.mkdir(parents=True, exist_ok=True)
    fc = reports_geojson()
    (out / "signalements.geojson").write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "depotoirs.osm").write_text(reports_osm_xml(), encoding="utf-8")
    print(f"[export] {len(fc['features'])} signalement(s) réel(s) vérifié(s) -> {out}/signalements.geojson, depotoirs.osm")
    if "--mock" in sys.argv:
        convert_mock()
    return 0


if __name__ == "__main__":
    sys.exit(main())
