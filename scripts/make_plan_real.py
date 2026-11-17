"""Plan réel pour l'équipe : vraies routes, configuration du dépôt, 10 signalements synthétiques acceptés
(python -m scripts.make_plan_real ; lancer d'abord python -m scripts.make_synthetic)."""

from __future__ import annotations

import json
from pathlib import Path

from core.config import load_config
from core.geo.download import REPO_ROOT
from core.optim.plan import CONFIG_PATH, compute_plan
from scripts.make_synthetic import OUT_PLAUSIBLE

N_REPORTS = 10
OUT = "plan_real.json"


def main() -> None:
    """Calcule et écrit data/mock/plan_real.json (format du contrat v2, géométrie des trajets)."""
    cfg = load_config(CONFIG_PATH)
    mock = Path(cfg["paths"]["mock_dir"])
    mock = mock if mock.is_absolute() else REPO_ROOT / mock
    src = mock / OUT_PLAUSIBLE
    reports = json.loads(src.read_text(encoding="utf-8"))[:N_REPORTS] if src.exists() else []
    reports = [{**r, "status": "accepted"} for r in reports]
    plan = compute_plan(cfg["params"], reports)
    (mock / OUT).write_text(json.dumps(plan, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{OUT} : mode {plan['mode']}, {len(plan['collection_points'])} points, {len(plan['routes'])} tournées, "
          f"{plan['totals']['points_served']} servis, {len(plan['unserved'])} non servis, "
          f"{len(plan['ignored_reports'])} signalements écartés, {plan['compute_ms']} ms.")


if __name__ == "__main__":
    main()
