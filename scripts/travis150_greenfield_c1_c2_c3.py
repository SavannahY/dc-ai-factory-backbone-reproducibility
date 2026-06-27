#!/usr/bin/env python
"""Run Travis 150 greenfield C1/C2/C3 data-center configuration screens."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

warnings.filterwarnings("ignore", message="Pandas requires version .*", category=UserWarning)

import pandas as pd

from ai_dc_backbone.travis150_greenfield import (
    DEFAULT_FLAGSHIP_POCKET,
    DEFAULT_LOADS_MW,
    DEFAULT_OUTPUT_STUDY_LOAD_MW,
    load_travis_greenfield_corridors,
    run_harmonic_screen,
    run_transfer_screen,
    run_voltage_screen,
    summarize_greenfield,
)


DATA = ROOT / "data"
DOCS = ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--travis-case",
        type=Path,
        default=None,
        help="Optional downloaded Travis 150 electric case as PowerWorld .aux, MATPOWER .m, or corridor CSV.",
    )
    parser.add_argument("--flagship-pocket", default=DEFAULT_FLAGSHIP_POCKET)
    parser.add_argument("--loads-mw", nargs="+", type=float, default=list(DEFAULT_LOADS_MW))
    parser.add_argument("--base-load-mw", type=float, default=DEFAULT_OUTPUT_STUDY_LOAD_MW)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--docs-dir", type=Path, default=DOCS)
    parser.add_argument("--harmonic-trials", type=int, default=600)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Report Travis case and optional simulator availability without writing outputs.",
    )
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


def _check_environment(args: argparse.Namespace) -> None:
    case_state = "provided" if args.travis_case and args.travis_case.exists() else "fallback"
    try:
        import helics  # noqa: F401

        helics_state = "available"
    except ImportError:
        helics_state = "missing"
    try:
        import opendssdirect  # noqa: F401

        opendss_state = "available"
    except ImportError:
        opendss_state = "missing"
    griddyn_state = "available" if shutil.which("gridDynMain") else "missing"
    gridpack_state = "available" if shutil.which("dsf.x") else "missing"
    print(f"travis_case: {case_state}")
    print(f"helics_python: {helics_state}")
    print(f"opendssdirect: {opendss_state}")
    print(f"gridDynMain: {griddyn_state}")
    print(f"GridPACK dsf.x: {gridpack_state}")


def _write_markdown(
    path: Path,
    source: str,
    transfer: pd.DataFrame,
    harmonics: pd.DataFrame,
    voltage: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    base = summary.sort_values("scenario_id").copy()
    display = base[
        [
            "scenario_id",
            "architecture",
            "max_transfer_mw",
            "median_efficiency_at_base_load",
            "thdv_p95_pct",
            "p95_pcc_voltage_deviation_pct",
            "data_center_load_served_min_fraction",
            "data_center_tripped",
        ]
    ].rename(
        columns={
            "scenario_id": "Scenario",
            "architecture": "Architecture",
            "max_transfer_mw": "Max transfer MW",
            "median_efficiency_at_base_load": "Efficiency at 1 GW",
            "thdv_p95_pct": "p95 THDv %",
            "p95_pcc_voltage_deviation_pct": "p95 voltage dev %",
            "data_center_load_served_min_fraction": "Min load served",
            "data_center_tripped": "Trip flag",
        }
    )
    for column in ["Max transfer MW", "p95 THDv %", "p95 voltage dev %"]:
        display[column] = display[column].map(lambda value: _fmt(value))
    display["Efficiency at 1 GW"] = display["Efficiency at 1 GW"].map(lambda value: _fmt(100.0 * value))
    display["Min load served"] = display["Min load served"].map(lambda value: _fmt(100.0 * value))

    c1 = summary[summary["scenario_id"] == "C1"].iloc[0]
    c3 = summary[summary["scenario_id"] == "C3"].iloc[0]
    tbase = transfer[transfer["study_load_mw"] == 1000.0]
    top_corridor = tbase["pocket_id"].iloc[0] if not tbase.empty else transfer["pocket_id"].iloc[0]
    span = f"{transfer['source_bus'].iloc[0]} to {transfer['load_bus'].iloc[0]}"
    if source.startswith("fallback"):
        limitation_source_note = (
            "This run used the archived Austin/Travis electrical corridor catalog already in the "
            "repository because no external Travis electric case was supplied."
        )
    else:
        limitation_source_note = (
            "This run used the supplied Travis electric case for corridor siting and electrical "
            "context. The dynamic voltage result should be rerun through the GridPACK/HELICS "
            "path when a POI-voltage recorder or post-processor is available."
        )

    lines = [
        "# Travis 150 Greenfield Data-Center Configuration Study",
        "",
        "This v2 study uses the Travis 150 synthetic electric test case as a",
        "data-center configuration test bed. The gas network is ignored.",
        "",
        "The TAMU source describes the dataset as a 150-bus synthetic electric",
        "test case corresponding to the Austin-Travis County T&D system and notes",
        "that it is synthetic rather than an actual grid:",
        "https://electricgrids.engr.tamu.edu/synthetic-gas-electric-test-case-for-the-travis-150-system/",
        "",
        "HELICS is the intended T&D coupling layer. The transmission-dynamic",
        "path uses GridPACK with the Travis 150 RAW/DYR case, while the",
        "distribution side uses OpenDSS/OpenDSSDirect.py/PyDSS.",
        "",
        "## Configuration",
        "",
        f"- Input source: `{source}`.",
        f"- Flagship data-center corridor: `{top_corridor}` / `{span}`.",
        "- C1 is a new traditional AC data-center supply ending at 480 V AC.",
        "- C2 is a new AC corridor with local SST and 34.5 kV-side VAR support.",
        "- C3 is a new dedicated bipolar DC data-center corridor with centralized",
        "  AC/DC-terminal voltage support.",
        "- These are new-build data-center configurations, not conversions of an",
        "  existing AC line.",
        "- For PowerWorld AUX inputs, existing Travis branch routes provide siting,",
        "  voltage class and impedance context; transfer limits use new-build",
        "  data-center corridor assumptions.",
        "",
        "## Base 1 GW Results",
        "",
        _markdown_table(display),
        "",
        "## Interpretation",
        "",
        f"C3 raises the useful transfer limit from {_fmt(c1['max_transfer_mw'])} MW",
        f"for C1 to {_fmt(c3['max_transfer_mw'])} MW for the new DC corridor. At",
        "the same 1 GW data-center load, C3 centralizes AC harmonic ownership at",
        "one grid-facing converter terminal and keeps the data-center load served",
        "through the repeated voltage-sag screen.",
        "",
        "The voltage output is wired for a GridPACK/HELICS/OpenDSS workflow",
        "using `Travis150-updated/150.RAW` and the GridPACK-ready DYR file.",
        "GridPACK publishes or post-processes the transmission POI voltage,",
        "OpenDSS receives that POI voltage for the data-center feeder, and the",
        "controller federate applies C2 local VAR or C3 centralized",
        "AC/DC-terminal support.",
        "",
        "## Output Files",
        "",
        "- `data/travis150_greenfield_c1_c2_c3_transfer_v2.csv`",
        "- `data/travis150_greenfield_c1_c2_c3_harmonics_v2.csv`",
        "- `data/travis150_greenfield_c1_c2_c3_voltage_v2.csv`",
        "- `data/travis150_greenfield_c1_c2_c3_summary_v2.csv`",
        "",
        "## Limitations",
        "",
        limitation_source_note,
        "A utility-grade result should rerun the same scenarios with a validated",
        "GridPACK Travis 150 dynamic case, a POI-voltage recorder or",
        "post-processor, and an OpenDSS feeder tied through HELICS.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.check_only:
        _check_environment(args)
        return

    args.data_dir.mkdir(parents=True, exist_ok=True)
    args.docs_dir.mkdir(parents=True, exist_ok=True)

    loads_mw = tuple(float(load) for load in args.loads_mw)
    corridors, source = load_travis_greenfield_corridors(args.travis_case, args.flagship_pocket)
    transfer = run_transfer_screen(corridors, loads_mw=loads_mw)
    harmonics = run_harmonic_screen(corridors, loads_mw=loads_mw, trials=args.harmonic_trials)
    voltage = run_voltage_screen(corridors, loads_mw=loads_mw)
    summary = summarize_greenfield(transfer, harmonics, voltage, base_load_mw=args.base_load_mw)
    summary.insert(0, "input_source", source)

    transfer_path = args.data_dir / "travis150_greenfield_c1_c2_c3_transfer_v2.csv"
    harmonics_path = args.data_dir / "travis150_greenfield_c1_c2_c3_harmonics_v2.csv"
    voltage_path = args.data_dir / "travis150_greenfield_c1_c2_c3_voltage_v2.csv"
    summary_path = args.data_dir / "travis150_greenfield_c1_c2_c3_summary_v2.csv"
    doc_path = args.docs_dir / "travis150_greenfield_data_center_config_study.md"

    transfer.to_csv(transfer_path, index=False)
    harmonics.to_csv(harmonics_path, index=False)
    voltage.to_csv(voltage_path, index=False)
    summary.to_csv(summary_path, index=False)
    _write_markdown(doc_path, source, transfer, harmonics, voltage, summary)

    print(transfer_path)
    print(harmonics_path)
    print(voltage_path)
    print(summary_path)
    print(doc_path)
    print(summary[["scenario_id", "max_transfer_mw", "thdv_p95_pct", "data_center_load_served_min_fraction"]].to_string(index=False))


if __name__ == "__main__":
    main()
