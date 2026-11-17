"""Les fichiers d'exemple de data/mock respectent docs/contracts.md."""

import json
from pathlib import Path

MOCK = Path(__file__).resolve().parents[1] / "data" / "mock"
TAGS = {"observed", "provided", "estimated", "synthetic", "simulated", "documented"}
REPORT_KEYS = {"id", "lat", "lon", "size", "photo_url", "photo_hash", "timestamp", "source", "status", "trust",
               "reason", "dumpsite_id", "validated_by", "validated_at"}
PLAN_KEYS = {"plan_id", "computed_at", "mode", "compute_ms", "params_used", "collection_points", "routes",
             "unserved", "ignored_reports", "checks", "totals", "assumptions", "warnings"}


def test_reports_follow_contract() -> None:
    """Chaque signalement a les clés et valeurs autorisées du contrat."""
    reports = json.loads((MOCK / "signalements.json").read_text(encoding="utf-8"))
    assert reports
    for r in reports:
        assert set(r) == REPORT_KEYS
        assert r["status"] in {"pending", "accepted", "rejected", "to_review"}
        assert r["size"] in {"small", "medium", "large"}
        assert r["source"] == "synthetic"


def test_plan_follows_contract() -> None:
    """Le plan d'exemple a la forme du contrat et est cohérent."""
    plan = json.loads((MOCK / "plan_exemple.json").read_text(encoding="utf-8"))
    assert set(plan) == PLAN_KEYS
    assert plan["mode"] in {"optimized", "partial", "fallback"}
    point_ids = {p["id"] for p in plan["collection_points"]}
    assert all(p["data_tag"] in TAGS and p["access"] in {"truck", "tricycle"} and p["type"] in {"center", "dumpsite"}
               for p in plan["collection_points"])
    assert all("_trip" in route["vehicle"] for route in plan["routes"]) and "uncollected_kg" in plan["totals"]
    served = [s for route in plan["routes"] for s in route["stops"]]
    unserved = [u["point_id"] for u in plan["unserved"]]
    assert sorted(served + unserved) == sorted(point_ids)
    assert all(u["reason"] in {"capacity", "budget", "access", "time", "no_route"} for u in plan["unserved"])
    assert all(route["load_kg"] <= route["capacity_kg"] for route in plan["routes"])
    assert plan["totals"]["cost"] == sum(route["cost"] for route in plan["routes"])
    assert plan["totals"]["points_served"] == len(served)
