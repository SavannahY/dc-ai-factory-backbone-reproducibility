import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_dc_backbone.transfer_capacity import (
    TransferCapacityAssumptions,
    corridor_capacity_envelope,
    first_binding,
    scan_ac_loadability,
    scan_transient_stability,
    thermal_capacity_envelope,
)


def test_same_current_dc_has_higher_useful_transfer():
    result = thermal_capacity_envelope(TransferCapacityAssumptions())
    assert result["dc_useful_mw"] > result["ac_useful_mw"]
    assert result["dc_to_ac_useful_ratio"] > 1.15


def test_ac_to_dc_capacity_envelope_matches_reference_cases():
    assumptions = TransferCapacityAssumptions(current_limit_kA=3.2)
    conservative = corridor_capacity_envelope(assumptions, v_pole_kv=138.0)
    high_voltage = corridor_capacity_envelope(assumptions, voltage_envelope_factor=1.5)

    assert round(conservative["capacity_multiplier"], 2) == 1.18
    assert round(high_voltage["capacity_multiplier"], 2) == 1.44
    assert high_voltage["dc_pole_kv"] > 168.0


def test_ac_loadability_can_bind_before_thermal_current():
    assumptions = TransferCapacityAssumptions(current_limit_kA=7.0)
    rows = scan_ac_loadability(assumptions, max_useful_mw=1800, step_mw=5)
    binding = first_binding(rows)
    thermal_only = thermal_capacity_envelope(assumptions)["ac_useful_mw"]

    assert binding["binding_constraint"] in {"reactive_power_limit", "voltage_limit"}
    assert binding["last_feasible_mw"] < thermal_only


def test_ac_transient_stability_can_bind_before_thermal_current():
    assumptions = TransferCapacityAssumptions(current_limit_kA=7.0)
    rows = scan_transient_stability(assumptions, max_useful_mw=1900, step_mw=5)
    binding = first_binding(rows)
    thermal_only = thermal_capacity_envelope(assumptions)["ac_useful_mw"]

    assert binding["binding_constraint"] == "transient_stability_limit"
    assert binding["last_feasible_mw"] < thermal_only
