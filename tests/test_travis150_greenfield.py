import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_dc_backbone.travis150_greenfield import (
    SCENARIOS,
    fallback_travis_corridors,
    greenfield_corridor,
    run_harmonic_screen,
    run_transfer_screen,
    run_voltage_screen,
    summarize_greenfield,
)


def test_greenfield_scenarios_are_distinct_new_data_center_configurations():
    assert set(SCENARIOS) == {"C1", "C2", "C3"}
    assert SCENARIOS["C1"].load_boundary_voltage_v == 480.0
    assert SCENARIOS["C1"].corridor_build == "new_ac_data_center_corridor"
    assert SCENARIOS["C2"].corridor_build == "new_ac_corridor_with_local_sst"
    assert SCENARIOS["C3"].corridor_build == "new_dedicated_bipolar_dc_data_center_corridor"
    assert "C0" not in SCENARIOS


def test_fallback_uses_one_flagship_travis_corridor_and_excludes_native_load():
    corridor = fallback_travis_corridors()[0]
    dcorridor = greenfield_corridor(corridor, SCENARIOS["C3"])

    assert corridor.pocket_id == "ATX-230-138-04"
    assert corridor.source_bus == "B_04"
    assert corridor.load_bus == "B_101"
    assert corridor.existing_load_mw > 0.0
    assert dcorridor.existing_load_mw == 0.0
    assert dcorridor.converter_rating_mw > corridor.converter_rating_mw


def test_greenfield_transfer_capacity_reports_new_line_not_conversion():
    corridor = fallback_travis_corridors()[0]
    transfer = run_transfer_screen([corridor], loads_mw=(1000.0,))
    summary = summarize_greenfield(
        transfer,
        run_harmonic_screen([corridor], loads_mw=(1000.0,), trials=80),
        run_voltage_screen([corridor], loads_mw=(1000.0,)),
    ).set_index("scenario_id")

    assert set(transfer["new_line_or_conversion"]) == {"new_greenfield_line"}
    assert transfer["new_data_center_load_is_incremental"].all()
    assert (transfer["existing_native_load_mw_excluded_from_new_corridor"] == corridor.existing_load_mw).all()
    assert summary.loc["C3", "max_transfer_mw"] > summary.loc["C1", "max_transfer_mw"]
    assert summary.loc["C3", "three_benefits_met_vs_c1"]


def test_greenfield_harmonics_and_voltage_ordering():
    corridor = fallback_travis_corridors()[0]
    harmonics = run_harmonic_screen([corridor], loads_mw=(1000.0,), trials=120)
    voltage = run_voltage_screen([corridor], loads_mw=(1000.0,))

    h = harmonics.set_index("scenario_id")
    v = voltage.set_index("scenario_id")
    assert h.loc["C1", "thdv_p95_pct"] > h.loc["C2", "thdv_p95_pct"] > h.loc["C3", "thdv_p95_pct"]
    assert h.loc["C3", "harmonic_source_count"] == 1
    assert set(voltage["coupling_tool"]) == {"HELICS"}
    assert v.loc["C1", "data_center_tripped"]
    assert not v.loc["C3", "data_center_tripped"]
    assert v.loc["C3", "data_center_load_served_min_fraction"] == 1.0


def test_archived_greenfield_outputs_exist_and_preserve_expected_meaning():
    transfer = pd.read_csv(ROOT / "data" / "travis150_greenfield_c1_c2_c3_transfer_v2.csv")
    summary = pd.read_csv(ROOT / "data" / "travis150_greenfield_c1_c2_c3_summary_v2.csv").set_index("scenario_id")

    assert {"C1", "C2", "C3"} == set(summary.index)
    assert summary.loc["C1", "data_center_tripped"]
    assert not summary.loc["C3", "data_center_tripped"]
    assert summary.loc["C3", "max_transfer_mw"] > summary.loc["C1", "max_transfer_mw"]
    assert summary.loc["C3", "thdv_p95_pct"] < summary.loc["C2", "thdv_p95_pct"]
    assert (transfer["load_boundary_voltage_v"][transfer["scenario_id"] == "C1"] == 480.0).all()
