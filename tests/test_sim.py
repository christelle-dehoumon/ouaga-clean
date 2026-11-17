"""Tests de contrat du simulateur C."""

from core.sim.model import run_scenario


def test_run_scenario_uses_plan_cost_and_requested_horizon() -> None:
    plan = {
        "plan_id": "p_test",
        "totals": {"cost": 1_250_000},
        "params_used": {},
    }

    result = run_scenario({"subscription_rate": 0.4, "tricycles": 8}, plan, 3)

    assert result["plan_id"] == "p_test"
    assert result["cout_m_fcfa"] == 1.25
    assert result["jours"] == 3
    assert result["data_tag"] == "simulated"
    assert 0 <= result["part_ramassee"] <= 1
    assert isinstance(result["depotoirs_restants"], int)
    assert result["assumptions"]


def test_run_scenario_rejects_missing_plan_and_invalid_inputs() -> None:
    assert "error" in run_scenario({"subscription_rate": 0.4, "tricycles": 8}, {}, 7)
    assert "error" in run_scenario({"subscription_rate": 0.4, "tricycles": 8}, {"totals": {"cost": 10}}, 0)
    assert "error" in run_scenario({"subscription_rate": 2, "tricycles": 8}, {"totals": {"cost": 10}}, 7)
