"""Exports des signalements RÉELS (reel.db seulement, jamais sim.db) : GeoJSON sous licence ouverte et fichier OSM.

Seuls les cas confirmés par la brigade (confirme) ou nettoyés (nettoye) sont exportés, sans photo, sans empreinte
de photo et sans aucune donnée personnelle (le citoyen n'a pas de compte). L'export OSM est un FICHIER à relire
dans JOSM avant tout import manuel : rien n'est jamais envoyé à OpenStreetMap par ce logiciel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import quoteattr

from core.config import get_config
from core.db import get_db

LICENSE = "ODbL-1.0"
LICENSE_URL = "https://opendatacommons.org/licenses/odbl/1-0/"


def confirmed_reports() -> list[dict[str, Any]]:
    """Cas réels confirmés ou nettoyés (reel.db, source reel uniquement)."""
    conn = get_db("reel")
    try:
        rows = conn.execute("SELECT id, type, statut, lat, lon, reported_at, nb_signalements FROM reports "
                            "WHERE statut IN ('confirme', 'nettoye') AND source='reel' ORDER BY reported_at").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def reports_geojson() -> dict[str, Any]:
    """FeatureCollection des cas réels exportables, avec licence et attribution."""
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r["lon"], 6), round(r["lat"], 6)]},
              "properties": {"id": r["id"], "type": r["type"], "statut": r["statut"], "date": r["reported_at"],
                             "nb_signalements": r["nb_signalements"]}} for r in confirmed_reports()]
    return {"type": "FeatureCollection", "name": f"Dépotoirs signalés et vérifiés, {get_config().get('commune')}",
            "license": LICENSE, "license_url": LICENSE_URL,
            "attribution": "Signalements citoyens vérifiés par la brigade Laabal, projet Yilgré",
            "data_tag": "observed", "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "features": feats}


def reports_osm_xml() -> str:
    """Fichier OSM (JOSM) des dépotoirs encore présents (confirme, type depotoir), identifiants négatifs."""
    lines = ["<?xml version='1.0' encoding='UTF-8'?>",
             "<osm version='0.6' generator='yilgre (export fichier, jamais envoyé)' upload='never'>"]
    for i, r in enumerate((r for r in confirmed_reports() if r["statut"] == "confirme" and r["type"] == "depotoir"), 1):
        lines.append(f"  <node id='-{i}' lat='{r['lat']:.7f}' lon='{r['lon']:.7f}'>")
        for k, v in (("landuse", "landfill"), ("informal", "yes"), ("source", "survey"),
                     ("note", f"Dépotoir sauvage signalé {r['nb_signalements']} fois, vérifié sur place ({r['reported_at'][:10]})")):
            lines.append(f"    <tag k={quoteattr(k)} v={quoteattr(v)}/>")
        lines.append("  </node>")
    lines.append("</osm>")
    return "\n".join(lines) + "\n"
