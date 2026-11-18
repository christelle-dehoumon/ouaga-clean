"""Matrice de contribution par membre et par couche (faits tirés de git) et briques réutilisées avec leur licence.

    python -m scripts.contribution_matrix      # écrit docs/contribution.md

Lignes ajoutées par auteur et par couche, toutes branches, sans les fusions. Sont comptés à part :
- les commits automatiques « Agent host session » (instantanés d'un outil, qui recopient l'état de travail, y compris
  des fichiers d'autres membres) : leurs lignes ne sont pas attribuées.
Les données (data/, city.json), bibliothèques copiées (vendor/) et images sont comptées en fichiers, pas en lignes.
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = [
    (r"^api/", "API"),
    (r"^core/validation/", "Tri"),
    (r"^core/(geo|optim)/", "Moteur (géo, optimisation)"),
    (r"^core/sim/", "Simulation"),
    (r"^core/", "Cycle de vie, bases, floutage"),
    (r"^web/citizen/", "Citoyen"),
    (r"^web/brigade/", "Brigade"),
    (r"^web/dashboard/(ville|shared)/", "Mairie 3D"),
    (r"^web/dashboard/", "Ancien tableau de bord"),
    (r"^(tests/|web/tools/e2e/)", "Tests"),
    (r"^(scripts/|web/tools/|Dockerfile|docker-compose|\.github/)", "Scripts, déploiement"),
    (r"^(docs/|README|web/README|CONTRIBUTING|THIRD_PARTY|CODEOWNERS|LICENSE)", "Documentation"),
    (r"^config/", "Configuration"),
]
DATA = re.compile(r"^data/|/data/city\.json$|/vendor/|\.(jpg|jpeg|png|pkl|npz|svg)$")
ROLES = {"TaniaW777": "géographie, optimisation des tournées", "jonathan-onjd": "API, tri, interfaces citoyen et brigade",
         "Christelle Dehoumon": "simulation, tableau de bord de la mairie, carte 3D"}

BRICKS = [
    ("FastAPI", "0.163.1", "MIT", "API web"), ("Uvicorn", "0.54.0", "BSD-3-Clause", "serveur HTTPS"),
    ("OR-Tools", "9.15.6755", "Apache-2.0", "tournées des camions"), ("OSMnx", "2.1.2", "MIT", "préparation du réseau OSM"),
    ("NetworkX", "3.7", "BSD-3-Clause", "graphe routier"), ("SciPy", "1.18.1", "BSD-3-Clause", "plus courts chemins"),
    ("NumPy", "2.2.6", "BSD-3-Clause", "calcul"), ("scikit-learn", "1.9.1", "BSD-3-Clause", "points de regroupement (KMeans)"),
    ("Shapely / GeoPandas / pyproj", "2.2.0 / 1.2.0 / 3.8.0", "BSD-3-Clause / BSD-3-Clause / MIT", "géométrie"),
    ("pyosmium", "4.3.2", "BSD-2-Clause", "lecture des fichiers OSM"), ("Mesa", "3.5.2", "Apache-2.0", "simulation multi-agents"),
    ("OpenCV (opencv-python-headless)", "4.12.0.88", "Apache-2.0 (roue avec FFmpeg LGPL-2.1, voir THIRD_PARTY_LICENSES.md)", "floutage"),
    ("Requests", "2.34.2", "Apache-2.0", "scripts de préparation"), ("pytest / httpx", "9.2.0 / 0.28.1", "MIT / BSD-3-Clause", "tests"),
    ("Three.js", "r170", "MIT", "camions 3D, ville 3D du secteur pilote"), ("Leaflet", "1.9.4", "BSD-2-Clause", "carte 2D de secours, carte de la brigade"),
    ("MapLibre GL JS", "6.16.0", "BSD-3-Clause", "carte 3D de l'agglomération"), ("PMTiles (JavaScript)", "4.5.0", "BSD-3-Clause", "lecture des tuiles auto-hébergées"),
    ("Polices Noto Sans", "—", "SIL OFL-1.1", "étiquettes de la carte"), ("Textures Poly Haven", "—", "CC0-1.0", "façades des bâtiments (stylistique)"),
    ("Planetiler (outil de fabrication, non livré)", "0.10.2", "Apache-2.0", "fabrication des tuiles"),
    ("pmtiles / mapbox-vector-tile (Python, fabrication, non livrés)", "3.8.1 / 2.2.0", "BSD-3-Clause / MIT", "validation des tuiles, index de recherche"),
    ("Playwright (outil de test, non livré)", "—", "Apache-2.0", "tests de bout en bout"),
    ("Données OpenStreetMap", "—", "ODbL-1.0, « © OpenStreetMap contributors »", "routes, bâtiments, eau, quartiers"),
    ("Images de test (Wikimedia Commons)", "—", "domaine public / CC0", "mesure du floutage"),
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def layer(path: str) -> str:
    return next((name for pattern, name in LAYERS if re.search(pattern, path)), "Autres")


def main() -> None:
    lines: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    data_files: dict[str, set[str]] = defaultdict(set)
    commits: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # commits, instantanés
    author, skip = "", False
    log = git("log", "--all", "--no-merges", "--numstat", "--pretty=format:@@%aN|%s")   # %aN : identités fusionnées par .mailmap
    for row in log.splitlines():
        if row.startswith("@@"):
            author, subject = (row[2:].split("|", 1) + [""])[:2]
            skip = subject.startswith("Agent host session")
            commits[author][1 if skip else 0] += 1
            continue
        parts = row.split("\t")
        if len(parts) != 3 or skip:
            continue
        added, _deleted, path = parts
        if DATA.search(path):
            data_files[author].add(path)
        elif added.isdigit():
            lines[author][layer(path)] += int(added)
    names = [n for _, n in LAYERS] + ["Autres"]
    authors = sorted(commits, key=lambda a: -sum(lines[a].values()))
    out = [
        "# Matrice de Contribution de VIELA",
        "",
        "Générée par `python -m scripts.contribution_matrix` à partir de git (toutes branches, sans fusions). "
        "Lignes ajoutées par couche, hors données, bibliothèques copiées et images (comptées en fichiers).",
        "",
        "## Commits",
        "",
        "| Membre (auteur git) | Rôle | Commits | Instantanés automatiques (non attribués) | Fichiers de données touchés |",
        "|---|---|---|---|---|",
        *[f"| {a} | {ROLES.get(a, 'à confirmer')} | {commits[a][0]} | {commits[a][1]} | {len(data_files[a])} |"
          for a in authors],
        "",
        "## Lignes ajoutées par couche",
        "",
        "| Couche | " + " | ".join(authors) + " |",
        "|---|" + "---|" * len(authors),
        *[f"| {n} | " + " | ".join(str(lines[a].get(n, 0) or "") for a in authors) + " |"
          for n in names if any(lines[a].get(n) for a in authors)],
        "",
        "Lecture et limites :",
        "",
        "- Les commits « Agent host session » sont des instantanés automatiques d'un outil : ils recopient l'état de travail,",
        "  y compris des fichiers d'autres membres. Leurs lignes ne sont attribuées à personne ; les statistiques brutes de",
        "  `git shortlog` les comptent et faussent donc la répartition.",
        
        "",
        "## Briques réutilisées",
        "",
        "| Brique | Version | Licence | Usage |",
        "|---|---|---|---|",
        *[f"| {b} | {v} | {lic} | {use} |" for b, v, lic, use in BRICKS],
        "",
        "Toutes ces licences sont compatibles avec la licence Apache-2.0 du projet. Les données dérivées d'OpenStreetMap",
        "restent sous ODbL. Inventaire détaillé : [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md).",
        "",
    ]
    (ROOT / "docs" / "contribution.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[:24]))


if __name__ == "__main__":
    main()
