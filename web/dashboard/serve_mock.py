#!/usr/bin/env python3
"""Serveur local de démonstration du tableau de bord mairie — 100 % hors ligne.

Il ne fait aucun appel réseau sortant : il sert les fichiers de ``data/mock/``
et appelle directement ``core.sim.run_scenario(params, days, actors_enabled)``.

Lancement (depuis la racine du dépôt) :
    .venv/bin/python web/dashboard/serve_mock.py --port 8765
puis ouvrir http://127.0.0.1:8765/

Si une simulation échoue, le dernier résultat valide est renvoyé avec
``data_status = "ancien"`` et un message clair : le tableau de bord ne plante
jamais et n'invente jamais de chiffre.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

RACINE = Path(__file__).resolve().parents[2]
DASH = Path(__file__).resolve().parent
MOCK = RACINE / "data" / "mock"
CONFIG = RACINE / "config" / "commune_config.json"

if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from core.sim import ACTIFS_PAR_DEFAUT, NOMS_ACTEURS, run_scenario  # noqa: E402

# Dernier état valide connu, conservé en mémoire le temps du processus.
DERNIER_RESULTAT: dict[str, Any] | None = None


def _json(chemin: Path) -> Any:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except Exception:
        return None


def _bootstrap() -> dict[str, Any]:
    config = _json(CONFIG) or {}
    bbox = config.get("bbox") if isinstance(config.get("bbox"), dict) else {}
    try:
        centre = [
            (float(bbox["south"]) + float(bbox["north"])) / 2,
            (float(bbox["west"]) + float(bbox["east"])) / 2,
        ]
    except (KeyError, TypeError, ValueError):
        centre = None
    return {
        "plan": _json(MOCK / "plan_real.json"),
        "zones": _json(MOCK / "zones.geojson"),
        "water": _json(MOCK / "water.geojson"),
        "signalements": _json(MOCK / "signalements.json"),
        "centre": centre,
        "bbox": bbox or None,
        "commune": config.get("commune", ""),
        "simulation_defauts": {"days": 7, "seed": 42, "note": "valeurs de démonstration, pas des données métier"},
        "parametres_config": config.get("params") if isinstance(config.get("params"), dict) else {},
        "actifs_par_defaut": dict(ACTIFS_PAR_DEFAUT),
        "noms_acteurs": list(NOMS_ACTEURS),
        "sources": {
            "plan": "data/mock/plan_real.json",
            "zones": "data/mock/zones.geojson",
            "configuration": "config/commune_config.json",
        },
        "data_tag": "mock local",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "OuagaCleanMock/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _envoyer(self, code: int, corps: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def _json_response(self, code: int, donnees: Any) -> None:
        corps = json.dumps(donnees, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._envoyer(code, corps, "application/json; charset=utf-8")

    def _fichier(self, chemin: Path) -> None:
        try:
            cible = chemin.resolve()
            if not cible.is_relative_to(DASH.resolve()):
                self._json_response(403, {"erreur": "accès refusé"})
                return
            if not cible.is_file():
                self._json_response(404, {"erreur": "fichier introuvable: " + chemin.name})
                return
            type_mime = mimetypes.guess_type(cible.name)[0] or "application/octet-stream"
            if type_mime.startswith("text/") or type_mime in ("application/javascript", "image/svg+xml"):
                type_mime += "; charset=utf-8"
            self._envoyer(200, cible.read_bytes(), type_mime)
        except Exception as exc:
            self._json_response(500, {"erreur": "lecture impossible: %s" % type(exc).__name__})

    def do_GET(self) -> None:  # noqa: N802
        chemin = urlparse(self.path).path
        if chemin in ("/", "/index.html"):
            self._fichier(DASH / "index.html")
        elif chemin == "/api/bootstrap":
            self._json_response(200, _bootstrap())
        elif chemin.startswith("/vendor/leaflet/"):
            self._fichier(DASH / chemin.lstrip("/"))
        elif chemin.startswith("/icons/"):
            self._fichier(DASH / chemin.lstrip("/"))
        elif chemin.startswith("/data/mock/"):
            nom = chemin.rsplit("/", 1)[-1]
            donnees = _json(MOCK / nom)
            if donnees is None:
                self._json_response(404, {"erreur": "fichier mock introuvable"})
            else:
                self._json_response(200, donnees)
        elif chemin in ("/app.css", "/app.js"):
            self._fichier(DASH / chemin.lstrip("/"))
        else:
            self._json_response(404, {"erreur": "route inconnue"})

    def do_POST(self) -> None:  # noqa: N802
        global DERNIER_RESULTAT
        chemin = urlparse(self.path).path
        if chemin != "/api/simulation":
            self._json_response(404, {"erreur": "route inconnue"})
            return
        try:
            taille = int(self.headers.get("Content-Length", "0"))
            corps = json.loads(self.rfile.read(max(0, taille)).decode("utf-8")) if taille else {}
        except Exception as exc:
            corps = {"_erreur": "requête illisible: %s" % type(exc).__name__}
        if not isinstance(corps, dict):
            corps = {}
        params = corps.get("params") if isinstance(corps.get("params"), dict) else {}
        acteurs = corps.get("actors_enabled") if isinstance(corps.get("actors_enabled"), dict) else None
        try:
            jours = int(corps.get("days", 7))
        except (TypeError, ValueError):
            jours = 7
        try:
            resultat = run_scenario(params, jours, acteurs)
            if not isinstance(resultat, dict) or resultat.get("warnings"):
                raise RuntimeError("résultat de simulation incomplet")
            resultat = dict(resultat)
            resultat["data_status"] = "actuel"
            DERNIER_RESULTAT = resultat
            self._json_response(200, resultat)
        except Exception as exc:
            message = "Simulation indisponible : %s — dernier état valide affiché." % type(exc).__name__
            if DERNIER_RESULTAT is not None:
                ancien = dict(DERNIER_RESULTAT)
                ancien["data_status"] = "ancien"
                ancien["erreur"] = message
                self._json_response(200, ancien)
            else:
                self._json_response(503, {
                    "erreur": message,
                    "data_status": "ancien",
                    "part_ramassee": None,
                    "cout_m_fcfa": None,
                    "depotoirs_restants": None,
                    "series": [], "agent_states": [], "events": [],
                })


def main() -> None:
    parseur = argparse.ArgumentParser(description="Tableau de bord mairie local, sans Internet")
    parseur.add_argument("--host", default="127.0.0.1")
    parseur.add_argument("--port", type=int, default=8765)
    args = parseur.parse_args()
    serveur = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Tableau de bord local : http://%s:%d/" % (args.host, args.port))
    print("Données : data/mock/ — aucun appel réseau externe.")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur local.")
    finally:
        serveur.server_close()


if __name__ == "__main__":
    main()
