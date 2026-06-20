#!/usr/bin/env python
"""Rank Austin/Travis 150-bus corridors for a converted DC backbone."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from ai_dc_backbone.travis150_siting import build_travis150_siting_table, summarize_travis150_siting


DATA = ROOT / "data"
DOCS = ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--docs-dir", type=Path, default=DOCS)
    parser.add_argument("--dataset-id", default="B")
    return parser.parse_args()


def _fmt(value: float, digits: int = 2) -> str:
    return f"{float(value):.{digits}f}"


def _markdown_table(frame: pd.DataFrame) -> str:
    headers = [str(column) for column in frame.columns]
    rows = [[str(value) for value in row] for row in frame.itertuples(index=False, name=None)]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _write_markdown(path: Path, ranking: pd.DataFrame, summary: pd.DataFrame) -> None:
    top = ranking.sort_values("rank").iloc[0]
    table_columns = [
        "rank",
        "pocket_id",
        "recommended_dc_line_location",
        "c3_max_transfer_mw",
        "c3_transfer_gain_vs_c0_pct",
        "c3_transfer_gain_vs_c2_pct",
        "c3_efficiency_gain_vs_c0_pctpt",
        "c3_thdv_reduction_vs_c0_pct",
        "c3_voltage_deviation_reduction_vs_c0_pct",
        "planning_interpretation",
    ]
    display = ranking.loc[:, table_columns].copy()
    rename = {
        "rank": "Rank",
        "pocket_id": "Corridor",
        "recommended_dc_line_location": "Synthetic bus span",
        "c3_max_transfer_mw": "C3 transfer MW",
        "c3_transfer_gain_vs_c0_pct": "C3 vs C0 transfer %",
        "c3_transfer_gain_vs_c2_pct": "C3 vs C2 transfer %",
        "c3_efficiency_gain_vs_c0_pctpt": "C3 vs C0 eff pct-pt",
        "c3_thdv_reduction_vs_c0_pct": "THDv reduction vs C0 %",
        "c3_voltage_deviation_reduction_vs_c0_pct": "Voltage-deviation reduction vs C0 %",
        "planning_interpretation": "Interpretation",
    }
    display = display.rename(columns=rename)
    for column in [
        "C3 transfer MW",
        "C3 vs C0 transfer %",
        "C3 vs C2 transfer %",
        "C3 vs C0 eff pct-pt",
        "THDv reduction vs C0 %",
        "Voltage-deviation reduction vs C0 %",
    ]:
        display[column] = display[column].map(lambda value: _fmt(value))

    summary_row = summary.iloc[0]
    lines = [
        "# Austin/Travis 150-bus DC Line Siting Screen",
        "",
        "This note ranks candidate subtransmission corridors in the archived",
        "Austin/Travis 150-bus Texas T&D validation case for conversion to the",
        "C3 subtransmission DC-backbone architecture.",
        "",
        "## Inputs",
        "",
        "- Corridor catalog: `data/texas_td_corridor_catalog_v1.csv`, dataset B.",
        "- Scenario outputs: `data/texas_td_c0_c2_c3_hosting_capacity_v1.csv`,",
        "  `data/texas_td_c0_c2_c3_harmonics_v1.csv`, and",
        "  `data/texas_td_c0_c2_c3_voltage_dynamics_v1.csv`.",
        "- Scenarios compared: C0/C1 traditional 400 V AC delivery, C2 local SST",
        "  with 34.5 kV-side local VAR support, and C3 converted DC backbone with",
        "  115/138 kV-side centralized AC support.",
        "",
        "The result is a corridor-level planning screen, not a parcel-level route",
        "selection. The repository has synthetic bus spans and electrical",
        "attributes for these four Austin/Travis validation corridors, but it does",
        "not contain geospatial right-of-way data for final route engineering.",
        "",
        "## Result",
        "",
        f"Top ranked candidate: `{top['pocket_id']}` from `{top['recommended_dc_line_location']}`.",
        f"It reaches {_fmt(top['c3_max_transfer_mw'])} MW in the C3 screen,",
        f"{_fmt(top['c3_transfer_gain_vs_c0_pct'])}% above C0 and",
        f"{_fmt(top['c3_transfer_gain_vs_c2_pct'])}% above C2.",
        "",
        _markdown_table(display),
        "",
        "## Three-Benefit Check",
        "",
        f"- All {int(summary_row['all_three_benefits_count'])} of "
        f"{int(summary_row['candidate_count'])} candidate corridors meet the",
        "  three architecture-level benefit checks used here: transfer plus",
        "  efficiency improvement versus C0, centralized harmonic ownership, and",
        "  reduced dynamic voltage exposure with LEL ride-through pass.",
        f"- The median C3 transfer gain versus C0 is",
        f"  {_fmt(summary_row['median_c3_transfer_gain_vs_c0_pct'])}%.",
        f"- The median C3 p95 THDv reduction versus C0 is",
        f"  {_fmt(summary_row['median_c3_thdv_reduction_vs_c0_pct'])}%.",
        f"- The median C3 p95 voltage-deviation reduction versus C0 is",
        f"  {_fmt(summary_row['median_c3_voltage_deviation_reduction_vs_c0_pct'])}%.",
        "",
        "## Local Versus Centralized Support",
        "",
        f"C3 beats local SST on transfer in "
        f"{int(summary_row['centralized_beats_local_transfer_count'])} of "
        f"{int(summary_row['candidate_count'])} corridors and beats local SST on",
        f"efficiency in {int(summary_row['centralized_beats_local_efficiency_count'])} of "
        f"{int(summary_row['candidate_count'])}. This is why the ranking does not",
        "treat efficiency alone as decisive. The centralized C3 case is strongest",
        "where it also adds corridor capacity beyond the C2 local-SST case, while",
        "still keeping the harmonic and dynamic-voltage benefits.",
        "",
        "Local SST plus local VAR support remains useful, but the screen keeps the",
        "coordination disadvantage explicit: nearby Volt-VAR devices, LTCs,",
        "capacitor banks, voltage regulators, STATCOM/SVC equipment or other",
        "smart-inverter controls can respond on different time scales. That can",
        "produce hunting or poor voltage coordination unless the local controls",
        "are supervised and coordinated with utility devices.",
        "",
        "## Limitation",
        "",
        "The siting result depends on the archived synthetic corridor assumptions.",
        "A utility-grade placement would need the actual Austin/Travis bus",
        "geography, right-of-way constraints, protection studies, converter",
        "ratings, GridDyn or equivalent dynamic cases, and OpenDSS feeder mapping",
        "for each candidate interconnection.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    args.docs_dir.mkdir(parents=True, exist_ok=True)

    ranking = build_travis150_siting_table(args.data_dir, dataset_id=args.dataset_id)
    summary = summarize_travis150_siting(ranking)

    ranking_path = args.data_dir / "travis150_dc_line_siting_candidates_v1.csv"
    summary_path = args.data_dir / "travis150_dc_line_siting_summary_v1.csv"
    doc_path = args.docs_dir / "travis150_dc_line_siting_study.md"
    ranking.to_csv(ranking_path, index=False)
    summary.to_csv(summary_path, index=False)
    _write_markdown(doc_path, ranking, summary)

    print(ranking_path)
    print(summary_path)
    print(doc_path)
    print(ranking.loc[:, ["rank", "pocket_id", "recommended_dc_line_location", "suitability_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
