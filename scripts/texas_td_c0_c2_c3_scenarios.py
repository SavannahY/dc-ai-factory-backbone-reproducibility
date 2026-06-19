#!/usr/bin/env python
"""Run Texas T&D C0/C1/C2/C3 architecture screens.

The runner writes reproducible CSV outputs for the Full Texas Combined T&D
main-data role (A) and Austin-Travis validation role (B).  If a Texas7k
MATPOWER case is supplied, the A transmission-corridor catalog is built from
that file; otherwise the archived screening catalog in ``texas_td_scenarios``
is used.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

cache_root = Path(tempfile.gettempdir()) / "dc_backbone_ai_factory_cache"
os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_root / "xdg"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ai_dc_backbone.texas_td_scenarios import (
    ARCHITECTURES,
    default_corridors,
    load_matpower_corridors,
    run_harmonic_screen,
    run_hosting_capacity,
    run_voltage_dynamics,
    summarize_by_architecture,
)


DATA = ROOT / "data"
FIG = ROOT / "figures"

COLORS = {
    "C0": "#377eb8",
    "C2": "#984ea3",
    "C3": "#e6550d",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--texas7k-matpower",
        type=Path,
        default=None,
        help="Optional Texas7k MATPOWER .m case. If omitted, archived A/B screening corridors are used.",
    )
    parser.add_argument(
        "--max-matpower-corridors",
        type=int,
        default=48,
        help="Maximum number of 138 kV corridors to extract from the MATPOWER case.",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--fig-dir", type=Path, default=FIG)
    parser.add_argument("--harmonic-trials", type=int, default=600)
    return parser.parse_args()


def load_corridors(args: argparse.Namespace):
    corridors = default_corridors()
    if args.texas7k_matpower is None:
        return corridors, "archived_screening_catalog"
    a_corridors = load_matpower_corridors(
        args.texas7k_matpower,
        dataset_id="A",
        dataset_role="Full Texas Combined T&D",
        max_corridors=args.max_matpower_corridors,
    )
    b_corridors = [c for c in corridors if c.dataset_id == "B"]
    return a_corridors + b_corridors, f"matpower:{args.texas7k_matpower}"


def savefig(fig: plt.Figure, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        path = out_dir / f"{name}.{ext}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        if ext == "svg":
            path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    plt.close(fig)


def plot_summary(summary: pd.DataFrame, hosting: pd.DataFrame, out_dir: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 7.3))
    order = ["C0", "C2", "C3"]
    labels = ["C0/C1\n400 V AC", "C2\nMV SST", "C3\nDC backbone"]

    ax = axes[0, 0]
    for dataset_id, offset in [("A", -0.18), ("B", 0.18)]:
        d = summary[summary["dataset_id"] == dataset_id].set_index("scenario_id").reindex(order)
        x = np.arange(len(order)) + offset
        ax.bar(
            x,
            d["median_max_transfer_mw"],
            width=0.32,
            color=[COLORS[s] for s in order],
            alpha=0.65 if dataset_id == "A" else 0.95,
            label=f"Dataset {dataset_id}",
        )
    ax.set_xticks(np.arange(len(order)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Median max useful transfer (MW)")
    ax.set_title("a  Transfer-capacity screen", loc="left", fontsize=11, weight="bold")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, fontsize=8)

    ax = axes[0, 1]
    for scenario_id in order:
        d = hosting[hosting["scenario_id"] == scenario_id]
        pos = order.index(scenario_id) + 1
        parts = ax.violinplot(
            [d["efficiency_to_load_boundary"]],
            positions=[pos],
            widths=0.65,
            showmedians=True,
            showextrema=False,
        )
        for body in parts["bodies"]:
            body.set_facecolor(COLORS[scenario_id])
            body.set_edgecolor(COLORS[scenario_id])
            body.set_alpha(0.42)
        parts["cmedians"].set_color(COLORS[scenario_id])
    ax.set_xticks(np.arange(1, len(order) + 1))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Efficiency to load boundary")
    ax.set_ylim(0.94, 1.0)
    ax.set_title("b  Efficiency at hosting limit", loc="left", fontsize=11, weight="bold")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[1, 0]
    for dataset_id, offset in [("A", -0.18), ("B", 0.18)]:
        d = summary[summary["dataset_id"] == dataset_id].set_index("scenario_id").reindex(order)
        x = np.arange(len(order)) + offset
        ax.bar(
            x,
            d["median_thdv_p95_pct"],
            width=0.32,
            color=[COLORS[s] for s in order],
            alpha=0.65 if dataset_id == "A" else 0.95,
            label=f"Dataset {dataset_id}",
        )
    ax.axhline(5.0, color="0.35", ls="--", lw=1.0)
    ax.text(2.45, 5.08, "5% guide", fontsize=7, ha="right", va="bottom", color="0.35")
    ax.set_xticks(np.arange(len(order)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Median p95 THDv (%)")
    ax.set_title("c  Harmonic ownership screen", loc="left", fontsize=11, weight="bold")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[1, 1]
    for dataset_id, offset in [("A", -0.18), ("B", 0.18)]:
        d = summary[summary["dataset_id"] == dataset_id].set_index("scenario_id").reindex(order)
        x = np.arange(len(order)) + offset
        ax.bar(
            x,
            d["median_p95_voltage_deviation_pct"],
            width=0.32,
            color=[COLORS[s] for s in order],
            alpha=0.65 if dataset_id == "A" else 0.95,
            label=f"Dataset {dataset_id}",
        )
    ax.set_xticks(np.arange(len(order)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Median p95 voltage deviation (%)")
    ax.set_title("d  Dynamic voltage exposure", loc="left", fontsize=11, weight="bold")
    ax.grid(axis="y", alpha=0.25)

    fig.tight_layout()
    savefig(fig, out_dir, "texas_td_c0_c2_c3_summary_v1")


def write_outputs(args: argparse.Namespace) -> None:
    args.data_dir.mkdir(parents=True, exist_ok=True)
    args.fig_dir.mkdir(parents=True, exist_ok=True)
    corridors, source = load_corridors(args)

    corridor_df = pd.DataFrame([c.__dict__ | {"vdc_pp_kv_effective": c.effective_vdc_pp_kv} for c in corridors])
    hosting = run_hosting_capacity(corridors)
    harmonics = run_harmonic_screen(corridors, trials=args.harmonic_trials)
    voltage = run_voltage_dynamics(corridors)
    summary = summarize_by_architecture(hosting, harmonics, voltage)

    provenance = pd.DataFrame(
        [
            {
                "dataset_id": "A",
                "role": "main",
                "dataset": "Texas A&M Full Texas Combined T&D",
                "transmission_runner": "MATPOWER-compatible AC steady-state screening; no PowerWorld/PSS/E required",
                "distribution_runner": "OpenDSS feeder validation only",
                "source_used": source if source.startswith("matpower:") else "archived screening catalog",
            },
            {
                "dataset_id": "B",
                "role": "validation",
                "dataset": "Texas A&M 150-bus T&D / Austin-Travis",
                "transmission_runner": "same C0/C1/C2/C3 screening interface; no PowerWorld/PSS/E required",
                "distribution_runner": "OpenDSS selected-feeder validation",
                "source_used": "archived validation catalog",
            },
        ]
    )
    voltage_sources = pd.DataFrame(
        [
            {
                "source": "HELICS tools showcase",
                "url": "https://helics.org/tools/",
                "model_use": "Identifies GridDyn as a supported transmission simulator and OpenDSS/OpenDSSDirect.py/PyDSS as supported distribution interfaces for T&D co-simulation.",
                "implemented_assumption": "Use GridDyn as the required transmission backend for the follow-on T&D dynamic VAR study; keep the current Python screen labelled as archived baseline until GridDyn/HELICS/OpenDSS are executed.",
            },
            {
                "source": "Keentel Engineering summary of NERC voltage-sensitive load incident, Oct. 19 2025",
                "url": "https://keentelengineering.com/nerc-voltage-sensitive-loads",
                "model_use": "Provides public event framing for the July 10, 2024 Eastern Interconnection voltage-sensitive-load disturbance.",
                "implemented_assumption": "Use a six-dip event-inspired voltage-sag train over about 82 s, with voltage minima spanning 0.25-0.40 pu, without claiming event reconstruction.",
            },
            {
                "source": "Utility Dive, April 21 2026",
                "url": "https://www.utilitydive.com/news/data-center-load-disruptions-nerc-alert-recommendations/818036/",
                "model_use": "Motivates treating large computational loads as ride-through and monitoring subjects, not only steady loads.",
                "implemented_assumption": "Report voltage-dip ride-through metrics alongside p95 dynamic voltage exposure.",
            },
            {
                "source": "ERCOT LEL Ride-Through Requirements, SPWG Feb. 24 2026",
                "url": "https://www.ercot.com/files/docs/2026/03/02/04_LEL-RT-Requirements_SPWG_Feb2026.pdf",
                "model_use": "Defines large electronic load framing and voltage ride-through performance checks.",
                "implemented_assumption": "Use a repeated voltage-sag screen with sag-proportional active-power reduction, 90% recovery within 2 s after voltage returns above 0.9 pu, and a 125% current cap.",
            },
        ]
    )

    corridor_df.to_csv(args.data_dir / "texas_td_corridor_catalog_v1.csv", index=False)
    hosting.to_csv(args.data_dir / "texas_td_c0_c2_c3_hosting_capacity_v1.csv", index=False)
    harmonics.to_csv(args.data_dir / "texas_td_c0_c2_c3_harmonics_v1.csv", index=False)
    voltage.to_csv(args.data_dir / "texas_td_c0_c2_c3_voltage_dynamics_v1.csv", index=False)
    summary.to_csv(args.data_dir / "texas_td_c0_c2_c3_summary_v1.csv", index=False)
    provenance.to_csv(args.data_dir / "texas_td_dataset_provenance_v1.csv", index=False)
    voltage_sources.to_csv(args.data_dir / "texas_td_voltage_ride_through_sources_v1.csv", index=False)

    plot_summary(summary, hosting, args.fig_dir)

    print(args.data_dir / "texas_td_c0_c2_c3_summary_v1.csv")
    print(args.fig_dir / "texas_td_c0_c2_c3_summary_v1.png")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    write_outputs(parse_args())
