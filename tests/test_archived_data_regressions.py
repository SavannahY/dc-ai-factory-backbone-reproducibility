"""Regression checks for archived manuscript data tables.

The tests assert relationships that are central to the manuscript's scientific
claims while avoiding overfitting every archived floating-point value. They are
intended to catch swapped files, stale runs, sign errors, and accidental changes
in the screening assumptions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OPENDSS = ROOT / "opendss"


def test_required_archived_outputs_are_present() -> None:
    required = [
        DATA / "efficiency_reference_case_v3.csv",
        DATA / "efficiency_design_space_v3.csv",
        DATA / "efficiency_uncertainty_reference_v3.csv",
        DATA / "harmonic_thdv_monte_carlo_v3.csv",
        DATA / "harmonic_robustness_summary_v3.csv",
        DATA / "dynamic_robustness_summary_v3.csv",
        DATA / "dynamic_timeseries_v3.csv",
        DATA / "true_opendss_harmonic_thdv_monte_carlo_v3.csv",
        OPENDSS / "true_opendss_run_log_v3.json",
    ]

    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert missing == []


def test_reference_efficiency_ordering_and_counter_case() -> None:
    df = pd.read_csv(DATA / "efficiency_reference_case_v3.csv").set_index("architecture")

    assert df.loc["Traditional AC", "loss_MW"] == pytest.approx(39.12461631186497)
    assert df.loc["Local SST", "loss_MW"] == pytest.approx(26.49903090586567)
    assert df.loc["Subtransmission DC backbone", "loss_MW"] == pytest.approx(
        25.704284346690656
    )
    assert df.loc["Subtransmission DC backbone", "loss_MW"] < df.loc["Traditional AC", "loss_MW"]
    assert df.loc["Subtransmission DC backbone", "loss_MW"] < df.loc["Local SST", "loss_MW"]
    assert df.loc["Local SST 99pct sensitivity", "loss_MW"] < df.loc[
        "Subtransmission DC backbone", "loss_MW"
    ]


def test_dynamic_robustness_summary_preserves_architectural_claim() -> None:
    df = pd.read_csv(DATA / "dynamic_robustness_summary_v3.csv").set_index("level")

    assert set(df.index) == {"Traditional AC", "Local SST", "Subtransmission DC backbone"}
    assert (df["n_scenarios"] == 3072).all()

    ramp = df["median_p99_ramp_pct_load_per_s"]
    voltage = df["median_p95_pcc_voltage_deviation_pct"]

    assert ramp["Subtransmission DC backbone"] < ramp["Local SST"] < ramp["Traditional AC"]
    assert voltage["Subtransmission DC backbone"] < voltage["Local SST"] < voltage["Traditional AC"]
    assert ramp["Subtransmission DC backbone"] / ramp["Traditional AC"] < 0.06


def test_harmonic_robustness_summary_preserves_architectural_claim() -> None:
    df = pd.read_csv(DATA / "harmonic_robustness_summary_v3.csv")
    arch = df[df["group"] == "architecture"].set_index("level")

    assert set(arch.index) == {"Traditional AC", "Local SST", "Subtransmission DC backbone"}
    assert (arch["cases"] == 3072).all()

    median = arch["median_p95_thdv_pct"]
    exceed = arch["fraction_exceeding_5pct_guide"]

    assert median["Subtransmission DC backbone"] < median["Local SST"] < median["Traditional AC"]
    assert exceed["Subtransmission DC backbone"] == pytest.approx(0.0)
    assert exceed["Traditional AC"] > exceed["Local SST"] > exceed["Subtransmission DC backbone"]


def test_true_opendss_log_is_consistent_with_archived_csv() -> None:
    with (OPENDSS / "true_opendss_run_log_v3.json").open() as fh:
        log = json.load(fh)
    df = pd.read_csv(DATA / "true_opendss_harmonic_thdv_monte_carlo_v3.csv")

    assert log["engine"] == "opendssdirect.py"
    assert log["n_trials"] == 60
    assert sorted(log["p95_thdv_pct"]) == ["dc_backbone", "local_sst", "traditional_ac"]

    computed = df.groupby("architecture")["thdv_pct"].quantile(0.95).to_dict()
    for key, value in computed.items():
        assert log["p95_thdv_pct"][key] == pytest.approx(value)

    assert computed["dc_backbone"] < computed["local_sst"] < computed["traditional_ac"]
