"""Outils géographiques sans dépendance : distance, point-dans-polygone, grille."""
import math
from collections import defaultdict

R = 6371000.0


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _ring_contains(ring, lon, lat):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            if lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def polygon_contains(rings, lon, lat):
    """rings = [exterieur, trou1, ...] au format GeoJSON (lon, lat)."""
    if not rings or not _ring_contains(rings[0], lon, lat):
        return False
    return not any(_ring_contains(h, lon, lat) for h in rings[1:])


def geojson_polygons(fc):
    """Liste de polygones (liste d'anneaux) depuis une FeatureCollection."""
    out = []
    for f in (fc or {}).get("features", []):
        g = f.get("geometry") or {}
        if g.get("type") == "Polygon":
            out.append(g["coordinates"])
        elif g.get("type") == "MultiPolygon":
            out.extend(g["coordinates"])
    return out


def in_any(polys, lon, lat):
    return any(polygon_contains(p, lon, lat) for p in polys)


class Grid:
    """Grille de cellules ~ radius_m : on ne compare qu'aux 9 cellules voisines
    au lieu de toutes les paires (amélioration chiffrée, voir bench)."""

    def __init__(self, radius_m):
        self.r = radius_m
        self.dlat = radius_m / 111320.0
        self.cells = defaultdict(list)

    def _dlon(self, lat):
        return self.r / (111320.0 * max(math.cos(math.radians(lat)), 0.01))

    def _key(self, lat, lon):
        return (int(math.floor(lat / self.dlat)), int(math.floor(lon / self._dlon(12.37))))

    def add(self, item_id, lat, lon):
        self.cells[self._key(lat, lon)].append((item_id, lat, lon))

    def near(self, lat, lon):
        ky, kx = self._key(lat, lon)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                yield from self.cells.get((ky + dy, kx + dx), ())

    def clear(self):
        self.cells.clear()
