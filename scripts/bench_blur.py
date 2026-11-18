"""Mesure du floutage sur les images de test (tests/data/blur), vérité terrain relevée à l'œil.

    python -m scripts.bench_blur          # affiche le tableau ; scripts/bench.py l'inclut dans docs/mesures.md

Un visage ou une plaque est « couvert » si la zone de 9 × 9 pixels autour de son centre a changé de plus de
COVER_DELTA niveaux de gris en moyenne après floutage. La part floutée de l'image indique le sur-floutage.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from core.privacy import blur_photo

DATA = Path(__file__).resolve().parents[1] / "tests" / "data" / "blur"
COVER_DELTA = 8.0


def measure() -> list[dict[str, object]]:
    """Une ligne par image : détections, éléments couverts, part floutée, durée."""
    truth = json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8"))["images"]
    rows = []
    for name, gt in truth.items():
        raw = (DATA / name).read_bytes()
        t0 = time.perf_counter()
        out, report = blur_photo(raw)
        ms = (time.perf_counter() - t0) * 1000
        before = cv2.cvtColor(cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY)
        after = cv2.cvtColor(cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY)
        diff = np.abs(before.astype(float) - after.astype(float))

        def covered(points: list[list[int]]) -> int:
            return sum(1 for x, y in points if diff[max(y - 4, 0):y + 5, max(x - 4, 0):x + 5].mean() > COVER_DELTA)

        rows.append({"image": name, "scene": gt["scene"], "faces_gt": len(gt["faces"]), "faces_ok": covered(gt["faces"]),
                     "plates_gt": len(gt["plates"]), "plates_ok": covered(gt["plates"]),
                     "zones": report["faces"] + report["plates"], "blurred_share": float((diff > COVER_DELTA).mean()),
                     "ms": ms})
    return rows


def markdown(rows: list[dict[str, object]]) -> list[str]:
    """Section Markdown de docs/mesures.md."""
    faces = (sum(r["faces_ok"] for r in rows), sum(r["faces_gt"] for r in rows))
    plates = (sum(r["plates_ok"] for r in rows), sum(r["plates_gt"] for r in rows))
    lines = ["## Floutage des visages et des plaques (core/privacy.py)", "",
             f"Mesuré par `python -m scripts.bench_blur` sur {len(rows)} images libres de droits (tests/data/blur, "
             "licences dans LICENSES.md), vérité terrain relevée à l'œil. Couvert = zone de 9 × 9 px autour du centre "
             f"modifiée de plus de {COVER_DELTA:g} niveaux de gris.", "",
             "| Image | Scène | Visages couverts | Plaques couvertes | Zones floutées | Part de l'image floutée | Durée |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['image']} | {r['scene']} | {r['faces_ok']}/{r['faces_gt']} | {r['plates_ok']}/{r['plates_gt']} | "
                     f"{r['zones']} | {r['blurred_share']:.1%} | {r['ms']:.0f} ms |")
    lines += ["", f"Total sur ce petit jeu : visages couverts {faces[0]}/{faces[1]}, plaques couvertes {plates[0]}/{plates[1]}. "
              "Sept images ne suffisent pas à estimer un taux de détection général : aucun pourcentage n'est annoncé "
              "au-delà de ces comptes. Les zones floutées en trop (panneaux, écussons) sont acceptées : la règle est de "
              "flouter trop plutôt que pas assez.", ""]
    return lines


if __name__ == "__main__":
    print("\n".join(markdown(measure())))
