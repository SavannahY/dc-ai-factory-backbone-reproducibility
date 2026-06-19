import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_dc_backbone.texas_td_scenarios import default_corridors, evaluate_scenario, run_hosting_capacity


def test_default_catalog_has_main_and_validation_datasets():
    corridors = default_corridors()
    dataset_ids = {c.dataset_id for c in corridors}

    assert dataset_ids == {"A", "B"}
    assert any(c.dataset_role == "Full Texas Combined T&D" for c in corridors)
    assert any(c.dataset_role == "Austin-Travis 150-bus T&D" for c in corridors)
    assert all(abs(c.voltage_kv - 138.0) < 1e-9 for c in corridors)


def test_reference_hosting_capacity_ordering():
    corridors = default_corridors()
    hosting = run_hosting_capacity(corridors)
    summary = hosting.groupby(["dataset_id", "scenario_id"])["max_transfer_mw"].median().unstack()
    efficiency = hosting.groupby(["dataset_id", "scenario_id"])["efficiency_to_800v"].median().unstack()

    assert (summary["C3"] > summary["C0"]).all()
    assert (summary["C3"] >= summary["C2"]).all()
    assert (efficiency["C3"] > efficiency["C0"]).all()


def test_c1_alias_matches_c0_traditional_400v_case():
    corridor = default_corridors()[0]
    c0 = evaluate_scenario(corridor, "C0", 500.0)
    c1 = evaluate_scenario(corridor, "C1", 500.0)

    assert c1["scenario_id"] == "C0"
    assert c1["architecture"] == c0["architecture"]
    assert c1["load_interface"] == "400 V AC facility distribution"
    assert c1["load_boundary_voltage_v"] == 400.0
    assert c1["voltage_support_location"] == "none"
    assert c1["efficiency_to_load_boundary"] == c0["efficiency_to_load_boundary"]


def test_archived_texas_td_outputs_preserve_benefit_ordering():
    summary = pd.read_csv(ROOT / "data" / "texas_td_c0_c2_c3_summary_v1.csv")
    wide_transfer = summary.pivot(index="dataset_id", columns="scenario_id", values="median_max_transfer_mw")
    wide_eff = summary.pivot(index="dataset_id", columns="scenario_id", values="median_efficiency_to_load_boundary")
    wide_harm = summary.pivot(index="dataset_id", columns="scenario_id", values="median_thdv_p95_pct")
    wide_voltage = summary.pivot(index="dataset_id", columns="scenario_id", values="median_p95_voltage_deviation_pct")

    assert (wide_transfer["C3"] > wide_transfer["C0"]).all()
    assert (wide_eff["C3"] > wide_eff["C0"]).all()
    assert (wide_harm["C3"] < wide_harm["C2"]).all()
    assert (wide_harm["C2"] < wide_harm["C0"]).all()
    assert (wide_voltage["C3"] < wide_voltage["C2"]).all()
    assert (wide_voltage["C2"] < wide_voltage["C0"]).all()


def test_hosting_capacity_keeps_binding_constraints():
    hosting = pd.read_csv(ROOT / "data" / "texas_td_c0_c2_c3_hosting_capacity_v1.csv")

    assert {"binding_constraint_at_limit", "first_violation_mw"}.issubset(hosting.columns)
    assert hosting["binding_constraint_at_limit"].notna().all()
    assert {"thermal_current_limit", "dc_current_limit", "reactive_power_limit", "stability_screen"} & set(
        hosting["binding_constraint_at_limit"]
    )


def test_voltage_outputs_include_large_electronic_load_ride_through_screen():
    voltage = pd.read_csv(ROOT / "data" / "texas_td_c0_c2_c3_voltage_dynamics_v1.csv")
    summary = pd.read_csv(ROOT / "data" / "texas_td_c0_c2_c3_summary_v1.csv")

    required = {
        "lel_vrt_event",
        "lel_poi_min_voltage_pu",
        "lel_service_min_voltage_pu",
        "lel_current_max_pu",
        "lel_current_over_125pct_s",
        "lel_recovery_to_90pct_s",
        "lel_ride_through_pass",
        "lel_load_loss_max_mw",
        "lel_dc_buffer_event_mwh",
        "voltage_support_location",
        "voltage_support_role",
        "var_coordination_risk",
    }
    assert required.issubset(voltage.columns)
    assert {"lel_vrt_pass_fraction", "median_lel_current_max_pu", "median_lel_load_loss_max_mw"}.issubset(
        summary.columns
    )

    a = summary[summary["dataset_id"] == "A"].set_index("scenario_id")
    voltage_a = voltage[voltage["dataset_id"] == "A"]
    assert voltage_a["lel_vrt_event"].str.startswith("eastern_interconnection_2024").all()
    assert voltage_a["lel_poi_min_voltage_pu"].min() == 0.25
    locations = voltage_a.groupby("scenario_id")["voltage_support_location"].first()
    assert "34.5 kV AC" in locations["C2"]
    assert "115/138 kV" in locations["C3"]
    assert a.loc["C3", "lel_vrt_pass_fraction"] >= a.loc["C2", "lel_vrt_pass_fraction"]
    assert a.loc["C3", "median_lel_current_max_pu"] < a.loc["C0", "median_lel_current_max_pu"]
    assert a.loc["C3", "median_lel_load_loss_max_mw"] < a.loc["C0", "median_lel_load_loss_max_mw"]
