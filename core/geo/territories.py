"""Territoires : zone pilote, quartiers ajoutés, territoires actifs et appartenance des bâtiments."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from core.geo.download import BOUNDARY_FILE, REPO_ROOT

PILOT_ID = "pilot"
METRES_PER_DEGREE_LAT = 111_320.0


def _resolve(path_str: str) -> Path:
    """Chemin de la configuration rendu absolu par rapport à la racine du dépôt."""
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


def _feature(item: Any) -> tuple[str, Any, dict[str, Any]] | None:
    """(id, géométrie shapely, propriétés) d'une Feature GeoJSON Polygon/MultiPolygon, None si invalide."""
    from shapely.geometry import shape

    if not isinstance(item, dict) or not isinstance(item.get("geometry"), dict):
        return None
    props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    tid = props.get("id", item.get("id"))
    if not isinstance(tid, str) or not tid:
        return None
    try:
        geom = shape(item["geometry"])
    except Exception:  # géométrie fournie par un humain : on ignore ce qui est cassé
        return None
    if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
        return None
    return tid, (geom if geom.is_valid else geom.buffer(0)), props


def _file_territories(cfg: dict[str, Any], warnings: list[str]) -> dict[str, tuple[Any, dict[str, Any]]]:
    """Territoires lus dans paths.territories (dictionnaire vide si le fichier manque ou est illisible)."""
    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    path_str = paths.get("territories")
    if not isinstance(path_str, str) or not path_str or not _resolve(path_str).exists():
        return {}
    try:
        data = json.loads(_resolve(path_str).read_text(encoding="utf-8"))
        feats = data.get("features", []) if isinstance(data, dict) else []
    except Exception as exc:  # fichier fourni par un humain : repli sans plantage
        warnings.append(f"Fichier de territoires illisible ({path_str}) : {exc}.")
        return {}
    out = {}
    for f in feats if isinstance(feats, list) else []:
        parsed = _feature(f)
        if parsed:
            out[parsed[0]] = (parsed[1], parsed[2])
    return out


def commune_polygon(cfg: dict[str, Any]) -> tuple[Any, str]:
    """Limite de la commune (limite OSM de data/raw, sinon rectangle bbox) et sa description ; (None, "") si aucune."""
    from shapely.geometry import box, shape

    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    boundary = _resolve(str(paths.get("raw_dir", "data/raw"))) / BOUNDARY_FILE
    try:
        data = json.loads(boundary.read_text(encoding="utf-8"))
        geom = shape(data.get("features", [data])[0]["geometry"])
        if not geom.is_empty:
            return (geom if geom.is_valid else geom.buffer(0)), "limite communale OSM"
    except Exception:  # limite absente ou illisible : repli sur l'emprise
        pass
    bbox = cfg.get("bbox")
    if isinstance(bbox, dict) and all(isinstance(bbox.get(k), (int, float)) for k in ("west", "south", "east", "north")):
        return box(bbox["west"], bbox["south"], bbox["east"], bbox["north"]), "emprise bbox"
    return None, ""


def add_territory(cfg: dict[str, Any], feature: Any) -> tuple[str | None, list[str]]:
    """Valide un quartier GeoJSON (polygone, dans la commune) et l'ajoute à paths.territories ; (None, avertissements) sinon."""
    parsed = _feature(feature)
    if parsed is None:
        return None, ["Quartier refusé : il faut une Feature GeoJSON Polygon ou MultiPolygon avec une propriété « id »."]
    tid, geom, _ = parsed
    commune, _how = commune_polygon(cfg)
    if commune is not None and not commune.intersects(geom):
        return None, [f"Quartier « {tid} » refusé : il est entièrement hors de la commune."]
    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    path_str = paths.get("territories")
    if not isinstance(path_str, str) or not path_str:
        return None, ["Quartier refusé : aucun fichier de territoires configuré (paths.territories)."]
    path = _resolve(path_str)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        feats = data.get("features", []) if isinstance(data, dict) and isinstance(data.get("features"), list) else []
        feats = [f for f in feats if (_feature(f) or ("",))[0] != tid] + [feature]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # disque plein, fichier corrompu : avertissement, pas d'exception
        return None, [f"Quartier « {tid} » non enregistré ({path_str}) : {exc}."]
    return tid, []


def _city_center(cfg: dict[str, Any], lat: np.ndarray, lon: np.ndarray) -> tuple[tuple[float, float] | None, str]:
    """Centre de la commune : centroïde de la limite OSM, sinon centre de bbox, sinon moyenne des bâtiments."""
    from shapely.geometry import shape

    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    boundary = _resolve(str(paths.get("raw_dir", "data/raw"))) / BOUNDARY_FILE
    try:
        data = json.loads(boundary.read_text(encoding="utf-8"))
        feats = data.get("features", [data])
        c = shape(feats[0]["geometry"]).centroid
        return (float(c.y), float(c.x)), "centroïde de la limite communale OSM"
    except Exception:  # limite absente ou illisible : replis suivants
        pass
    bbox = cfg.get("bbox")
    if isinstance(bbox, dict) and all(isinstance(bbox.get(k), (int, float)) for k in ("west", "south", "east", "north")):
        return ((bbox["south"] + bbox["north"]) / 2, (bbox["west"] + bbox["east"]) / 2), "centre de l'emprise bbox"
    if len(lat):
        return (float(lat.mean()), float(lon.mean())), "centre moyen des bâtiments"
    return None, ""


def _pilot_square(cfg: dict[str, Any], lat: np.ndarray, lon: np.ndarray, assumptions: list[str]) -> Any:
    """Carré pilote de model.pilot_square_m de côté centré sur la commune (None si aucun centre connu)."""
    from shapely.geometry import box

    model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    side = model.get("pilot_square_m")
    side = float(side) if isinstance(side, (int, float)) and not isinstance(side, bool) and math.isfinite(side) and side > 0 \
        else 5000.0
    center, how = _city_center(cfg, lat, lon)
    if center is None:
        return None
    half_lat = side / 2 / METRES_PER_DEGREE_LAT
    half_lon = side / 2 / (METRES_PER_DEGREE_LAT * math.cos(math.radians(center[0])))
    assumptions.append(f"Zone pilote : carré de {side / 1000:g} km de côté (model.pilot_square_m) centré sur le {how} "
                       f"({center[0]:.4f}, {center[1]:.4f}) ; aucune limite d'arrondissement ou de secteur dans les données OSM.")
    return box(center[1] - half_lon, center[0] - half_lat, center[1] + half_lon, center[0] + half_lat)


def active_territories(cfg: dict[str, Any], params: dict[str, Any], lat: np.ndarray, lon: np.ndarray
                       ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Territoires actifs (zone pilote + params.extra_territories) : id, nom, géométrie, population fournie ou None."""
    assumptions: list[str] = []
    warnings: list[str] = []
    model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    pilot_ids = model.get("pilot_territory_ids") if isinstance(model.get("pilot_territory_ids"), list) else []
    extra = params.get("extra_territories") if isinstance(params, dict) else None
    extra = extra if isinstance(extra, list) else []
    known = _file_territories(cfg, warnings)
    commune, _how = commune_polygon(cfg)
    wanted: list[Any] = extra + [t for t in pilot_ids if isinstance(t, str)]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in wanted:
        if isinstance(item, dict):
            parsed = _feature(item)
            if parsed is None:
                warnings.append("Quartier ajouté ignoré : il faut une Feature GeoJSON Polygon ou MultiPolygon avec un « id ».")
                continue
            tid, geom, props = parsed
        elif isinstance(item, str) and item in known:
            tid, (geom, props) = item, known[item]
        elif item == PILOT_ID:
            pilot_pop = None
            if isinstance(params, dict) and params.get("pilot_population") is not None:
                pilot_pop = params.get("pilot_population")
            elif isinstance(model, dict) and model.get("pilot_population") is not None:
                cfg_pop = cfg.get("params", {}).get("population")
                param_pop = params.get("population") if isinstance(params, dict) else None
                if param_pop is None or param_pop == cfg_pop:
                    pilot_pop = model.get("pilot_population")
            props = {"name": "Zone pilote"}
            if isinstance(pilot_pop, (int, float)) and pilot_pop > 0:
                props["population"] = int(pilot_pop)
                props["source"] = "estimated"
            tid, geom, props = PILOT_ID, _pilot_square(cfg, lat, lon, assumptions), props
            if geom is None:
                warnings.append("Zone pilote impossible à construire : ni limite communale, ni emprise, ni bâtiments.")
                continue
        else:
            warnings.append(f"Territoire « {item} » introuvable dans {cfg.get('paths', {}).get('territories')} : ignoré.")
            continue
        if tid in seen:
            continue
        if commune is not None and not commune.intersects(geom):
            warnings.append(f"Quartier « {tid} » ignoré : il est entièrement hors de la commune.")
            continue
        seen.add(tid)
        pop = props.get("population")
        pop = float(pop) if isinstance(pop, (int, float)) and not isinstance(pop, bool) and math.isfinite(pop) and pop >= 0 \
            else None
        out.append({"id": tid, "name": props.get("name") or tid, "geometry": geom, "population": pop,
                    "source": props.get("source") if pop is not None and isinstance(props.get("source"), str) else None})
    return out, assumptions, warnings


def assign(territories: list[dict[str, Any]], lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Indice du premier territoire actif contenant chaque bâtiment (-1 si aucun)."""
    import shapely

    owner = np.full(len(lat), -1, dtype=np.int64)
    for i, t in enumerate(territories):
        shapely.prepare(t["geometry"])
        free = owner < 0
        if not free.any():
            break
        inside = shapely.contains_xy(t["geometry"], lon[free], lat[free])
        idx = np.flatnonzero(free)[inside]
        owner[idx] = i
    return owner
