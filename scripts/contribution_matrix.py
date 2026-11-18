"""Matrice de contribution par membre et par couche (git) et briques réutilisées avec leur licence.

    python -m scripts.contribution_matrix      # écrit docs/contribution.md

Lignes ajoutées par auteur et par couche, toutes branches, sans les fusions. Les commits automatiques
« Agent host session » (instantanés d'un outil) sont comptés à part : ils recopient souvent le travail des autres.
Données (data/), bibliothèques copiées (web/*/vendor) et images de test sont exclues des lignes de code.
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = [("api/", "API"), ("core/geo/", "Géo"), ("core/optim/", "Optimisation"), ("core/sim/", "Simulation"),
          ("core/validation/", "Tri"), ("core/", "Cœur (cycle de vie, config, bases, floutage)"),
          ("web/citizen/", "Page citoyen"), ("web/dashboard/", "Tableau de bord"), ("tests/", "Tests"),
          ("scripts/", "Scripts"), ("docs/", "Docs"), ("config/", "Configuration")]
EXCLUDE = re.compile(r"^(data/|web/.*/vendor/|tests/data/)|\.(jpg|png|pkl|npz)$")
ROLES = {"TaniaW777": "A (géo, optimisation)", "jonathan-onjd": "B (API, tri, mobile)",
         "Christelle Dehoumon": "C (simulation, tableau de bord)"}
BRICKS = [
    ("FastAPI", "MIT", "API web"), ("Uvicorn", "BSD-3-Clause", "serveur HTTPS"), ("OR-Tools", "Apache-2.0", "tournées"),
    ("OSMnx", "MIT", "préparation du réseau OSM"), ("NetworkX", "BSD-3-Clause", "graphe"),
    ("SciPy", "BSD-3-Clause", "plus courts chemins"), ("scikit-learn", "BSD-3-Clause", "KMeans des points de regroupement"),
    ("Shapely / GeoPandas / pyproj", "BSD-3-Clause / BSD-3-Clause / MIT", "géométrie"),
    ("NumPy", "BSD-3-Clause", "calcul"), ("pyosmium", "BSD-2-Clause", "lecture OSM"),
    ("Mesa", "Apache-2.0", "simulation multi-agents"),
    ("OpenCV (opencv-python-headless) et ses cascades Haar", "Apache-2.0 (cascades : licence Intel de type BSD)", "floutage"),
    ("Requests", "Apache-2.0", "scripts de préparation"), ("pytest / httpx", "MIT / BSD-3-Clause", "tests"),
    ("Leaflet 1.9.4", "BSD-2-Clause", "carte (front)"),
    ("Données OpenStreetMap (routes, bâtiments, eau, quartiers)", "ODbL-1.0, © contributeurs OpenStreetMap", "données"),
    ("Tuiles OpenStreetMap (front, en ligne)", "CC BY-SA 2.0 (tuiles) ; politique d'usage des tuiles OSMF", "fond de carte"),
    ("Images de test (Wikimedia Commons)", "Domaine public / CC0", "mesure du floutage"),
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def layer(path: str) -> str | None:
    if EXCLUDE.search(path):
        return None
    return next((name for prefix, name in LAYERS if path.startswith(prefix)), "Autres")


def main() -> None:
    lines: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    commits: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    author, auto = "", False
    for row in git("log", "--all", "--no-merges", "--numstat", "--pretty=format:@@%an|%s").splitlines():
        if row.startswith("@@"):
            author, subject = row[2:].split("|", 1)
            auto = subject.startswith("Agent host session")
            commits[author][1 if auto else 0] += 1
            continue
        parts = row.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and not auto and (name := layer(parts[2])):
            lines[author][name] += int(parts[0])
    names = [n for _, n in LAYERS] + ["Autres"]
    out = ["# Matrice de contribution", "", "Générée par `python -m scripts.contribution_matrix` à partir de git "
           "(toutes branches, sans fusions). Lignes ajoutées, hors données, bibliothèques copiées et images.", "",
           "| Membre | Rôle | Commits | Instantanés automatiques | " + " | ".join(names) + " |",
           "|---|---|---|---|" + "---|" * len(names)]
    for who in sorted(commits, key=lambda a: -sum(lines[a].values())):
        out.append(f"| {who} | {ROLES.get(who, '?')} | {commits[who][0]} | {commits[who][1]} | "
                   + " | ".join(str(lines[who].get(n, 0) or "") for n in names) + " |")
    out += ["", "Les instantanés automatiques (« Agent host session ») ne sont pas comptés dans les lignes : ils recopient "
            "l'état de travail, y compris des fichiers d'autres membres.", "",
            "Note : les commits du 2026-11-18 (refonte back-end) sont signés jonathan-onjd avec l'assistance de Claude "
            "(mention Co-Authored-By dans chaque message de commit).", "",
            "## Briques réutilisées", "", "| Brique | Licence | Usage |", "|---|---|---|"]
    out += [f"| {b} | {lic} | {use} |" for b, lic, use in BRICKS]
    out += ["", "Toutes ces licences sont compatibles avec la licence Apache-2.0 du projet. Les données dérivées "
            "d'OpenStreetMap restent sous ODbL et doivent être attribuées « © contributeurs OpenStreetMap ».", ""]
    (ROOT / "docs" / "contribution.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[:12]))


if __name__ == "__main__":
    main()
