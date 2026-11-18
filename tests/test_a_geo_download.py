"""core.geo.download : fichiers locaux lus en priorité, rien de retéléchargé, pas de plantage sans réseau."""

import json
from pathlib import Path
from typing import Any

import pytest

from core.geo import download

TINY_OSM = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6">
  <node id="1" lat="12.0" lon="-1.0"/><node id="2" lat="12.0" lon="-0.9"/>
  <node id="3" lat="12.1" lon="-0.9"/><node id="4" lat="12.1" lon="-1.0"/>
  <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="building" v="yes"/></way>
  <way id="11"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
  <way id="12"><nd ref="2"/><nd ref="3"/><tag k="highway" v="residential"/></way>
</osm>
"""


class _NoNetwork:
    """Faux osmnx : tout appel réseau échoue."""

    def __getattr__(self, name: str) -> Any:
        """Lève à chaque appel de fonction."""
        def _fail(*_a: Any, **_k: Any) -> None:
            raise ConnectionError("réseau coupé (test)")
        return _fail


def _config(tmp_path: Path) -> Path:
    """Configuration minimale pointant vers des dossiers temporaires."""
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"place_query": "Ville test", "bbox": {"west": 0, "south": 0, "east": 1, "north": 1},
                                "paths": {"raw_dir": str(tmp_path / "raw"), "processed_dir": str(tmp_path / "out")}}),
                    encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remplace osmnx réseau par un faux et supprime la pause entre essais."""
    monkeypatch.setattr(download, "_configure_osmnx", lambda _cache: _NoNetwork())
    monkeypatch.setattr(download, "RETRY_PAUSE_S", 0)


def test_building_centroid_is_mean_of_nodes(tmp_path: Path) -> None:
    """Le centre d'un bâtiment fermé est la moyenne de ses nœuds, sans compter deux fois le premier."""
    osm = tmp_path / "t.osm"
    osm.write_text(TINY_OSM, encoding="utf-8")
    coords, skipped = download.building_centroids_from_osm(osm)
    assert coords.shape == (1, 2) and skipped == 0
    assert coords[0] == pytest.approx([12.05, -0.95])


def test_local_files_are_used_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Avec les fichiers locaux, aucun appel réseau, et un second passage ne refait rien."""
    monkeypatch.setattr(download, "LOCAL_PBF", "zone.osm")  # pyosmium choisit le format d'après l'extension
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / download.LOCAL_ROADS_XML).write_text(TINY_OSM, encoding="utf-8")
    (raw / download.LOCAL_PBF).write_text(TINY_OSM, encoding="utf-8")
    cfg = str(_config(tmp_path))
    assert download.run(cfg) == 0
    meta = json.loads((tmp_path / "out" / download.META_FILE).read_text(encoding="utf-8"))
    assert meta["roads"]["nodes"] == 3 and meta["buildings"]["buildings"] == 1
    assert download.run(cfg) == 0


def test_network_failure_reports_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans fichier local ni réseau : deux essais par donnée, code 1 et liste de ce qui manque.

    Le réseau est simulé en panne (aucun appel réel à Nominatim ou Overpass, dont l'état varie)."""
    class NoNetwork:
        def __getattr__(self, name: str) -> Any:
            def fail(*_a: Any, **_k: Any) -> Any:
                raise ConnectionError("réseau indisponible (simulé)")
            return fail
    monkeypatch.setattr(download, "_configure_osmnx", lambda *_a, **_k: NoNetwork())
    monkeypatch.setattr(download, "RETRY_PAUSE_S", 0)
    assert download.run(str(_config(tmp_path))) == 1
    out = capsys.readouterr().out
    assert "MANQUANT" in out and download.ROADS_PICKLE in out and download.BUILDINGS_FILE in out
    assert out.count("[routes] échec à l'essai") == 2
