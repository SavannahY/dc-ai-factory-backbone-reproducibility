"""Austin/Travis 150-bus DC-backbone corridor siting screen."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


SCENARIOS = ("C0", "C2", "C3")
SCORE_WEIGHTS = {
    "absolute_c3_transfer": 0.25,
    "transfer_gain_vs_c0": 0.18,
    "transfer_gain_vs_c2": 0.12,
    "efficiency_gain_vs_c0": 0.15,
    "harmonic_reduction": 0.12,
    "dynamic_voltage_reduction": 0.12,
    "source_strength": 0.06,
}


def _read(data_dir: Path, name: str) -> pd.DataFrame:
    path = data_dir / name
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def _scenario_wide(frame: pd.DataFrame, value: str, suffix: str) -> pd.DataFrame:
    wide = frame.pivot(index="pocket_id", columns="scenario_id", values=value)
    missing = set(SCENARIOS) - set(wide.columns)
    if missing:
        raise ValueError(f"{value} is missing scenarios: {sorted(missing)}")
    wide = wide.loc[:, SCENARIOS]
    return wide.rename(columns={scenario: f"{scenario.lower()}_{suffix}" for scenario in SCENARIOS})


def _unit_interval(series: pd.Series) -> pd.Series:
    numeric = series.astype(float)
    minimum = numeric.min()
    maximum = numeric.max()
    if maximum <= minimum:
        return pd.Series(1.0, index=series.index)
    return (numeric - minimum) / (maximum - minimum)


def _pct_gain(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return 100.0 * (numerator / denominator - 1.0)


def _pct_reduction(new: pd.Series, old: pd.Series) -> pd.Series:
    return 100.0 * (1.0 - new / old)


def _interpret(row: pd.Series) -> str:
    if row["rank"] == 1:
        return "best first build: highest C3 transfer, strongest source and clear C3 gain over local SST"
    if row["centralized_transfer_advantage_vs_local_sst_met"]:
        return "good candidate: C3 adds transfer beyond local SST and keeps harmonic and dynamic benefits"
    if row["c3_transfer_gain_vs_c0_pct"] >= 25.0:
        return "relief candidate: large gain over traditional AC, but C3 does not beat local SST on transfer"
    return "lower priority: benefits are present, but incremental C3 transfer gain is smaller"


def build_travis150_siting_table(data_dir: str | Path, dataset_id: str = "B") -> pd.DataFrame:
    """Rank Austin/Travis corridors for conversion to a subtransmission DC line."""

    data_path = Path(data_dir)
    catalog = _read(data_path, "texas_td_corridor_catalog_v1.csv")
    hosting = _read(data_path, "texas_td_c0_c2_c3_hosting_capacity_v1.csv")
    harmonics = _read(data_path, "texas_td_c0_c2_c3_harmonics_v1.csv")
    voltage = _read(data_path, "texas_td_c0_c2_c3_voltage_dynamics_v1.csv")

    catalog = catalog[catalog["dataset_id"] == dataset_id].copy()
    if catalog.empty:
        raise ValueError(f"No corridor catalog rows found for dataset_id={dataset_id!r}")

    hosting = hosting[hosting["dataset_id"] == dataset_id].copy()
    harmonics = harmonics[harmonics["dataset_id"] == dataset_id].copy()
    voltage = voltage[voltage["dataset_id"] == dataset_id].copy()

    base_columns = [
        "dataset_id",
        "dataset_role",
        "pocket_id",
        "source_bus",
        "load_bus",
        "voltage_kv",
        "length_km",
        "current_limit_kA",
        "short_circuit_gva",
        "source_q_limit_mvar",
        "converter_rating_mw",
        "existing_load_mw",
        "vdc_pp_kv_effective",
    ]
    result = catalog.loc[:, [column for column in base_columns if column in catalog.columns]].set_index("pocket_id")

    for value, suffix in [
        ("max_transfer_mw", "max_transfer_mw"),
        ("efficiency_to_load_boundary", "efficiency_to_load_boundary"),
        ("loss_mw", "loss_mw_at_limit"),
    ]:
        result = result.join(_scenario_wide(hosting, value, suffix))
    result = result.join(_scenario_wide(hosting, "binding_constraint_at_limit", "binding_constraint"))
    result = result.join(_scenario_wide(harmonics, "thdv_p95_pct", "thdv_p95_pct"))
    result = result.join(_scenario_wide(voltage, "p95_pcc_voltage_deviation_pct", "p95_voltage_deviation_pct"))
    result = result.join(_scenario_wide(voltage, "p99_ramp_mw_s", "p99_ramp_mw_s"))
    result = result.join(_scenario_wide(voltage, "lel_load_loss_max_mw", "lel_load_loss_max_mw"))
    result = result.join(_scenario_wide(voltage, "lel_ride_through_pass", "lel_ride_through_pass"))

    result["recommended_dc_line_location"] = result["source_bus"].astype(str) + " to " + result["load_bus"].astype(str)
    result["c3_transfer_gain_vs_c0_pct"] = _pct_gain(
        result["c3_max_transfer_mw"], result["c0_max_transfer_mw"]
    )
    result["c3_transfer_gain_vs_c2_pct"] = _pct_gain(
        result["c3_max_transfer_mw"], result["c2_max_transfer_mw"]
    )
    result["c3_efficiency_pct"] = 100.0 * result["c3_efficiency_to_load_boundary"]
    result["c0_efficiency_pct"] = 100.0 * result["c0_efficiency_to_load_boundary"]
    result["c2_efficiency_pct"] = 100.0 * result["c2_efficiency_to_load_boundary"]
    result["c3_efficiency_gain_vs_c0_pctpt"] = result["c3_efficiency_pct"] - result["c0_efficiency_pct"]
    result["c3_efficiency_gain_vs_c2_pctpt"] = result["c3_efficiency_pct"] - result["c2_efficiency_pct"]
    result["c3_thdv_reduction_vs_c0_pct"] = _pct_reduction(
        result["c3_thdv_p95_pct"], result["c0_thdv_p95_pct"]
    )
    result["c3_thdv_reduction_vs_c2_pct"] = _pct_reduction(
        result["c3_thdv_p95_pct"], result["c2_thdv_p95_pct"]
    )
    result["c3_voltage_deviation_reduction_vs_c0_pct"] = _pct_reduction(
        result["c3_p95_voltage_deviation_pct"], result["c0_p95_voltage_deviation_pct"]
    )
    result["c3_voltage_deviation_reduction_vs_c2_pct"] = _pct_reduction(
        result["c3_p95_voltage_deviation_pct"], result["c2_p95_voltage_deviation_pct"]
    )
    result["c3_ramp_reduction_vs_c0_pct"] = _pct_reduction(
        result["c3_p99_ramp_mw_s"], result["c0_p99_ramp_mw_s"]
    )
    result["c3_ramp_reduction_vs_c2_pct"] = _pct_reduction(
        result["c3_p99_ramp_mw_s"], result["c2_p99_ramp_mw_s"]
    )

    result["benefit_transfer_efficiency_met"] = (
        (result["c3_max_transfer_mw"] > result["c0_max_transfer_mw"])
        & (result["c3_efficiency_to_load_boundary"] > result["c0_efficiency_to_load_boundary"])
    )
    result["benefit_harmonic_ownership_met"] = (
        (result["c3_thdv_p95_pct"] < result["c2_thdv_p95_pct"])
        & (result["c2_thdv_p95_pct"] < result["c0_thdv_p95_pct"])
    )
    result["benefit_dynamic_voltage_vrt_met"] = (
        (result["c3_p95_voltage_deviation_pct"] < result["c2_p95_voltage_deviation_pct"])
        & (result["c2_p95_voltage_deviation_pct"] < result["c0_p95_voltage_deviation_pct"])
        & result["c3_lel_ride_through_pass"].astype(bool)
        & ~result["c0_lel_ride_through_pass"].astype(bool)
    )
    benefit_columns = [
        "benefit_transfer_efficiency_met",
        "benefit_harmonic_ownership_met",
        "benefit_dynamic_voltage_vrt_met",
    ]
    result["three_benefits_met"] = result[benefit_columns].all(axis=1)
    result["benefits_met_count"] = result[benefit_columns].sum(axis=1)
    result["centralized_transfer_advantage_vs_local_sst_met"] = (
        result["c3_max_transfer_mw"] > result["c2_max_transfer_mw"]
    )
    result["centralized_efficiency_advantage_vs_local_sst_met"] = (
        result["c3_efficiency_to_load_boundary"] > result["c2_efficiency_to_load_boundary"]
    )

    result["absolute_c3_transfer_score"] = _unit_interval(result["c3_max_transfer_mw"])
    result["transfer_gain_vs_c0_score"] = _unit_interval(result["c3_transfer_gain_vs_c0_pct"])
    result["transfer_gain_vs_c2_score"] = _unit_interval(result["c3_transfer_gain_vs_c2_pct"])
    result["efficiency_gain_vs_c0_score"] = _unit_interval(result["c3_efficiency_gain_vs_c0_pctpt"])
    result["harmonic_reduction_score"] = (result["c3_thdv_reduction_vs_c0_pct"] / 100.0).clip(0.0, 1.0)
    result["dynamic_voltage_reduction_score"] = (
        result["c3_voltage_deviation_reduction_vs_c0_pct"] / 100.0
    ).clip(0.0, 1.0)
    result["source_strength_score"] = _unit_interval(result["short_circuit_gva"])
    result["suitability_score"] = (
        SCORE_WEIGHTS["absolute_c3_transfer"] * result["absolute_c3_transfer_score"]
        + SCORE_WEIGHTS["transfer_gain_vs_c0"] * result["transfer_gain_vs_c0_score"]
        + SCORE_WEIGHTS["transfer_gain_vs_c2"] * result["transfer_gain_vs_c2_score"]
        + SCORE_WEIGHTS["efficiency_gain_vs_c0"] * result["efficiency_gain_vs_c0_score"]
        + SCORE_WEIGHTS["harmonic_reduction"] * result["harmonic_reduction_score"]
        + SCORE_WEIGHTS["dynamic_voltage_reduction"] * result["dynamic_voltage_reduction_score"]
        + SCORE_WEIGHTS["source_strength"] * result["source_strength_score"]
    )

    result = result.sort_values(
        ["suitability_score", "c3_max_transfer_mw", "c3_transfer_gain_vs_c2_pct"],
        ascending=[False, False, False],
    ).reset_index()
    result.insert(0, "rank", range(1, len(result) + 1))
    result["planning_interpretation"] = result.apply(_interpret, axis=1)

    leading = [
        "rank",
        "pocket_id",
        "recommended_dc_line_location",
        "source_bus",
        "load_bus",
        "suitability_score",
        "planning_interpretation",
    ]
    return result.loc[:, leading + [column for column in result.columns if column not in leading]]


def summarize_travis150_siting(ranking: pd.DataFrame) -> pd.DataFrame:
    """Build a one-row summary for the Austin/Travis siting screen."""

    top = ranking.sort_values("rank").iloc[0]
    return pd.DataFrame(
        [
            {
                "dataset_id": top["dataset_id"],
                "dataset_role": top["dataset_role"],
                "candidate_count": int(len(ranking)),
                "top_ranked_pocket_id": top["pocket_id"],
                "top_ranked_location": top["recommended_dc_line_location"],
                "top_ranked_c3_transfer_mw": top["c3_max_transfer_mw"],
                "top_ranked_c3_transfer_gain_vs_c0_pct": top["c3_transfer_gain_vs_c0_pct"],
                "top_ranked_c3_transfer_gain_vs_c2_pct": top["c3_transfer_gain_vs_c2_pct"],
                "all_three_benefits_count": int(ranking["three_benefits_met"].sum()),
                "centralized_beats_local_transfer_count": int(
                    ranking["centralized_transfer_advantage_vs_local_sst_met"].sum()
                ),
                "centralized_beats_local_efficiency_count": int(
                    ranking["centralized_efficiency_advantage_vs_local_sst_met"].sum()
                ),
                "median_c3_transfer_gain_vs_c0_pct": ranking["c3_transfer_gain_vs_c0_pct"].median(),
                "median_c3_thdv_reduction_vs_c0_pct": ranking["c3_thdv_reduction_vs_c0_pct"].median(),
                "median_c3_voltage_deviation_reduction_vs_c0_pct": ranking[
                    "c3_voltage_deviation_reduction_vs_c0_pct"
                ].median(),
            }
        ]
    )
