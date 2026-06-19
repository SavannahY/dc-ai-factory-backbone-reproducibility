#!/usr/bin/env python
"""Generate transfer-capacity screening data and figures.

This add-on study asks whether the AC corridor is limited only by conductor
ampacity, or whether voltage, reactive-power and transient-stability screens can
bind before the thermal limit.  It is not a substitute for a project-specific
planning study.
"""

from __future__ import annotations

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
import pandas as pd

from ai_dc_backbone.transfer_capacity import (
    TransferCapacityAssumptions,
    first_binding,
    scan_ac_loadability,
    scan_transient_stability,
    thermal_capacity_envelope,
)


DATA = ROOT / "data"
FIG = ROOT / "figures"


def savefig(fig: plt.Figure, name: str) -> None:
    for ext in ("png", "svg"):
        path = FIG / f"{name}.{ext}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        if ext == "svg":
            path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    plt.close(fig)


def row_for_limit(case: str, architecture: str, limit_mw: float, binding: str, note: str) -> dict[str, object]:
    return {
        "case": case,
        "architecture": architecture,
        "max_useful_transfer_mw": limit_mw,
        "binding_constraint": binding,
        "note": note,
    }


def main() -> None:
    DATA.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)

    base = TransferCapacityAssumptions()
    high_ampacity = TransferCapacityAssumptions(current_limit_kA=7.0)

    current_rows = [
        thermal_capacity_envelope(base, current_limit_kA=current)
        for current in [3.0, 4.0, 5.5, 7.0]
    ]
    current_df = pd.DataFrame(current_rows)
    current_df.to_csv(DATA / "transfer_capacity_current_envelope_v1.csv", index=False)

    loadability_rows = scan_ac_loadability(high_ampacity, max_useful_mw=1800.0, step_mw=5.0)
    loadability_df = pd.DataFrame(loadability_rows)
    loadability_df.to_csv(DATA / "transfer_capacity_loadability_curve_v1.csv", index=False)
    loadability_binding = first_binding(loadability_rows)

    stability_rows = scan_transient_stability(high_ampacity, max_useful_mw=1900.0, step_mw=5.0)
    stability_df = pd.DataFrame(stability_rows)
    stability_df.to_csv(DATA / "transfer_capacity_stability_curve_v1.csv", index=False)
    stability_binding = first_binding(stability_rows)

    base_envelope = thermal_capacity_envelope(base)
    high_envelope = thermal_capacity_envelope(high_ampacity)
    summary_rows = [
        row_for_limit(
            "same ROW current envelope",
            "Traditional AC",
            base_envelope["ac_useful_mw"],
            "thermal_current_limit",
            "Closed-form useful MW at the 800 VDC boundary for 5.5 kA corridor current.",
        ),
        row_for_limit(
            "same ROW current envelope",
            "Subtransmission DC backbone",
            base_envelope["dc_useful_mw"],
            "thermal_current_or_converter_limit",
            "Closed-form useful MW at the 800 VDC boundary for the same 5.5 kA corridor current.",
        ),
        row_for_limit(
            "AC loadability screen",
            "Traditional AC",
            float(loadability_binding["last_feasible_mw"]),
            str(loadability_binding["binding_constraint"]),
            "Two-bus AC screen with voltage and source-Mvar limits; current limit relaxed to expose non-thermal constraints.",
        ),
        row_for_limit(
            "AC transient stability screen",
            "Traditional AC",
            float(stability_binding["last_feasible_mw"]),
            str(stability_binding["binding_constraint"]),
            "Classical equal-area screen with 100 ms minimum critical clearing time; current limit relaxed to expose stability constraints.",
        ),
        row_for_limit(
            "same high-ampacity ROW current envelope",
            "Traditional AC",
            high_envelope["ac_useful_mw"],
            "thermal_current_limit",
            "Closed-form thermal-only AC limit for the same 7.0 kA current used in the non-thermal screens.",
        ),
        row_for_limit(
            "same high-ampacity ROW current envelope",
            "Subtransmission DC backbone",
            high_envelope["dc_useful_mw"],
            "thermal_current_or_converter_limit",
            "Closed-form thermal-only DC limit for the same 7.0 kA current used in the non-thermal screens.",
        ),
    ]
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(DATA / "transfer_capacity_constraint_summary_v1.csv", index=False)

    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.4))
    ac = "#377eb8"
    dc = "#e6550d"
    grey = "0.35"

    ax = axes[0, 0]
    ax.plot(current_df["current_limit_kA"], current_df["ac_useful_mw"], marker="o", color=ac, label="Traditional AC")
    ax.plot(current_df["current_limit_kA"], current_df["dc_useful_mw"], marker="o", color=dc, label="DC backbone")
    ax.set_title("a  Same-current transfer envelope", loc="left", fontsize=10, weight="bold")
    ax.set_xlabel("Corridor current limit (kA)")
    ax.set_ylabel("Useful transfer at 800 VDC boundary (MW)")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=8)

    ax = axes[0, 1]
    ok = loadability_df[loadability_df["binding_constraint"] == "none"]
    bad = loadability_df[loadability_df["binding_constraint"] != "none"]
    ax.plot(loadability_df["useful_mw"], loadability_df["receiving_voltage_pu"], color=ac, lw=1.7)
    ax.axhline(high_ampacity.voltage_min_pu, color=grey, ls="--", lw=1.0)
    if not bad.empty:
        first = bad.iloc[0]
        ax.scatter([first["useful_mw"]], [first["receiving_voltage_pu"]], color="black", s=24, zorder=5)
    ax.set_title("b  AC voltage-loadability screen", loc="left", fontsize=10, weight="bold")
    ax.set_xlabel("Useful transfer (MW)")
    ax.set_ylabel("Receiving-end voltage (pu)")
    ax.grid(alpha=0.25)
    ax2 = ax.twinx()
    ax2.plot(loadability_df["useful_mw"], loadability_df["source_q_mvar"], color="#984ea3", lw=1.2, alpha=0.75)
    ax2.axhline(high_ampacity.source_q_limit_mvar, color="#984ea3", ls=":", lw=1.0)
    ax2.set_ylabel("Source reactive output (Mvar)", color="#984ea3")
    ax2.tick_params(axis="y", labelcolor="#984ea3")

    ax = axes[1, 0]
    ax.plot(stability_df["useful_mw"], stability_df["critical_clearing_time_s"] * 1000.0, color=ac, lw=1.7)
    ax.axhline(high_ampacity.min_critical_clearing_s * 1000.0, color=grey, ls="--", lw=1.0)
    stab_bad = stability_df[stability_df["binding_constraint"] != "none"]
    if not stab_bad.empty:
        first = stab_bad.iloc[0]
        ax.scatter(
            [first["useful_mw"]],
            [first["critical_clearing_time_s"] * 1000.0],
            color="black",
            s=24,
            zorder=5,
        )
    ax.set_title("c  AC transient-stability screen", loc="left", fontsize=10, weight="bold")
    ax.set_xlabel("Useful transfer (MW)")
    ax.set_ylabel("Critical clearing time (ms)")
    ax.grid(alpha=0.25)

    ax = axes[1, 1]
    plot_rows = summary_df[
        summary_df["case"].isin(
            [
                "same ROW current envelope",
                "AC loadability screen",
                "AC transient stability screen",
            ]
        )
    ].copy()
    labels = [
        "AC\nthermal",
        "DC\nsame ROW",
        "AC\nloadability",
        "AC\nstability",
    ]
    values = [
        plot_rows.iloc[0]["max_useful_transfer_mw"],
        plot_rows.iloc[1]["max_useful_transfer_mw"],
        plot_rows.iloc[2]["max_useful_transfer_mw"],
        plot_rows.iloc[3]["max_useful_transfer_mw"],
    ]
    colors = [ac, dc, "#984ea3", "#4daf4a"]
    ax.bar(range(len(values)), values, color=colors, alpha=0.86)
    ax.set_xticks(range(len(values)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Useful transfer limit (MW)")
    ax.set_title("d  Binding-constraint summary", loc="left", fontsize=10, weight="bold")
    ax.grid(axis="y", alpha=0.25)
    for i, value in enumerate(values):
        ax.text(i, value + 25, f"{value:.0f}", ha="center", fontsize=8)

    fig.tight_layout()
    savefig(fig, "transfer_capacity_screening_v1")


if __name__ == "__main__":
    main()
