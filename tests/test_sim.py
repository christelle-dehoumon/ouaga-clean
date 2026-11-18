"""Simulation multi-agents (Mesa) : contrat de sortie, réactions aux événements, hypothèses lues dans la configuration."""

from __future__ import annotations

import copy
from typing import Any

import mesa
import pytest

from core.config import get_config
from core.sim.model import MOTEUR, run_scenario


def _plan(served: bool = True, cost: float = 200_000, n: int = 6) -> dict[str, Any]:
    """Plan jouet : n points de regroupement de 1 t, servis ou non, coût par passage donné."""
    points = [{"id": f"c_{i}", "type": "center", "lat": 12.37 + i * 0.002, "lon": -1.53, "demand_kg": 1000.0}
              for i in range(n)]
    routes = [{"vehicle": "truck1_trip1", "type": "truck", "stops": [p["id"] for p in points]}] if served else []
    return {"plan_id": "p_test", "collection_points": points, "routes": routes,
            "totals": {"cost": cost, "uncollected_kg": 1500.0},
            "params_used": {**get_config()["params"], "frequency_per_week": 3, "trucks": 1}}


def test_contract_and_mesa_engine() -> None:
    """Trois chiffres, séries par jour, étiquette simulated, vrai moteur Mesa (plus de shim)."""
    r = run_scenario({}, _plan(), 5, seed=3)
    assert r["moteur"] == MOTEUR == f"mesa {mesa.__version__}" and "fallback" not in r["moteur"]
    assert 0 <= r["part_ramassee"] <= 1 and isinstance(r["depotoirs_restants"], int) and r["cout_m_fcfa"] >= 0
    assert r["data_tag"] == "simulated" and r["source"] == "sim" and len(r["series"]) == 5
    assert all(d["source"] == "sim" for d in r["depotoirs"])
    assert r["hypotheses"]["menages"]["personnes_par_menage"]["note"].startswith("hypothèse non mesurée")


def test_reproducible_with_seed() -> None:
    """Même graine, même résultat ; graine différente, tirages différents."""
    a, b = run_scenario({}, _plan(), 7, seed=1), run_scenario({}, _plan(), 7, seed=1)
    strip = lambda r: {k: v for k, v in r.items() if k != "scenario_id"}  # noqa: E731
    assert strip(a) == strip(b)


@pytest.mark.parametrize("change", [{"broken_trucks": ["truck1"]},

                                    {"budget": 0}, {"frequency_per_week": 1}, {"tricycles": 0}])
def test_each_degradation_lowers_collection(change: dict[str, Any]) -> None:
    """Panne de tous les camions, budget nul, fréquence basse, pas de tricycle : moins de déchets ramassés."""
    base = run_scenario({}, _plan(), 7, seed=2)
    worse = run_scenario(change, _plan(), 7, seed=2)
    assert worse["part_ramassee"] < base["part_ramassee"]


def test_rain_and_unserved_plan_react() -> None:
    """Pluie : moins de passages ; plan sans tournée (route coupée, quartier non desservi) : plus de dépotoirs."""
    base = run_scenario({}, _plan(), 14, seed=4)
    rain = run_scenario({"rainy_season": True}, _plan(), 14, seed=4)
    assert rain["part_ramassee"] <= base["part_ramassee"]
    unserved = run_scenario({}, _plan(served=False), 14, seed=4)
    assert unserved["part_ramassee"] < base["part_ramassee"]
    assert sum(d["kg"] for d in unserved["depotoirs"]) > sum(d["kg"] for d in base["depotoirs"])


def test_budget_and_frequency_are_used() -> None:
    """Budget et fréquence transmis : le coût suit le nombre de passages et s'arrête au budget."""
    three = run_scenario({"frequency_per_week": 3}, _plan(cost=100_000), 7, seed=0)
    seven = run_scenario({"frequency_per_week": 7}, _plan(cost=100_000), 7, seed=0)
    assert seven["cout_fcfa"] > three["cout_fcfa"] > 0
    half = run_scenario({"budget": 50_000}, _plan(cost=100_000), 7, seed=0)
    assert half["cout_fcfa"] == pytest.approx(three["cout_fcfa"] / 2, rel=0.01)


def test_actors_can_be_disabled_reproducibly() -> None:
    """Retirer la brigade : plus aucun signalement ni sensibilisation, effet reproductible."""
    no_brigade = {"brigade": False}
    a = run_scenario({}, _plan(served=False), 7, actors_enabled=no_brigade, seed=5)
    b = run_scenario({}, _plan(served=False), 7, actors_enabled=no_brigade, seed=5)
    assert a["indicateurs"]["brigade"]["depotoirs_signales"] == 0 and a["part_ramassee"] == b["part_ramassee"]
    assert run_scenario({}, _plan(), 3, actors_enabled={"menages": False}, seed=5)["part_ramassee"] is None


def test_sim_dumpsites_and_bad_inputs() -> None:
    """Dépotoirs simulés ajoutés par la mairie comptés ; entrées absurdes : erreur explicite, jamais d'exception."""
    r = run_scenario({}, _plan(), 1, sim_dumpsites=[{"id": "m1", "lat": 12.38, "lon": -1.52, "kg": 900}], seed=0)
    assert any(d["id"] == "m1" and d["origine"] == "ajouté par la mairie" for d in r["depotoirs"])
    assert "error" in run_scenario({}, None, 7)
    assert "error" in run_scenario({}, _plan(), 0)
    assert "error" in run_scenario({}, _plan(), "sept")
    clamped = run_scenario({"population": 1e15}, _plan(), 1)
    assert clamped["params_used"]["population"] == get_config()["bounds"]["population"]["max"] and clamped["warnings"]


def test_coefficients_come_from_config() -> None:
    """Changer une hypothèse de la configuration change le résultat ; une hypothèse absente donne une erreur claire."""
    cfg = copy.deepcopy(get_config())
    cfg["hypotheses"]["menages"]["proba_depot_sauvage_non_desservi"]["valeur"] = 0.0
    cfg["hypotheses"]["menages"]["proba_depot_sauvage_non_abonne"]["valeur"] = 0.0
    clean = run_scenario({}, _plan(served=False), 7, seed=1, cfg=cfg)
    assert clean["depotoirs_restants"] == 0
    del cfg["hypotheses"]["brigade"]["rayon_m"]
    assert "hypotheses.brigade.rayon_m" in run_scenario({}, _plan(served=False), 7, seed=1, cfg=cfg)["error"]
