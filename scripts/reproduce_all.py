#!/usr/bin/env python
"""Regenerate key manuscript figures from the archived CSV outputs.

This public repository includes all source CSV files used for the manuscript
figures. Running this script rebuilds Fig. 3 and Fig. 4 into
``reproduced/figures`` as a fast submission-time reproducibility check.
"""
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

cache_root = Path(tempfile.gettempdir()) / "dc_backbone_ai_factory_cache"
os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_root / "xdg"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "reproduced" / "figures"
OUT.mkdir(parents=True, exist_ok=True)


COLORS = {
    "Traditional AC": "#377eb8",
    "AC + active filter/storage": "#80b1d3",
    "Local SST": "#984ea3",
    "Local SST + coordinated control": "#bc80bd",
    "Subtransmission DC backbone": "#e6550d",
}


def savefig(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def figure3():
    harm_df = pd.read_csv(DATA / "harmonic_thdv_monte_carlo_v3.csv")
    spec_p95 = pd.read_csv(DATA / "harmonic_individual_p95_v3.csv")
    res_scan = pd.read_csv(DATA / "harmonic_resonance_scan_v3.csv")
    names = [
        "Traditional AC",
        "AC + active filter/storage",
        "Local SST",
        "Local SST + coordinated control",
        "Subtransmission DC backbone",
    ]

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.8))

    ax = axes[0, 0]
    interfaces = [3, 3, 3, 3, 1]
    ax.bar(range(len(names)), interfaces, color=[COLORS[n] for n in names], alpha=0.85)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(
        ["Trad.\nAC", "AC+filter\n/storage", "Local\nSST", "SST+\ncoord.", "DC\nbackbone"],
        fontsize=7,
    )
    ax.set_ylabel("AC-facing large converter interfaces")
    ax.set_ylim(0, 3.6)
    ax.set_title("a  Harmonic ownership boundary", loc="left", fontsize=11, weight="bold")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[0, 1]
    data = [harm_df[harm_df.scenario == n].thdv_pct for n in names]
    parts = ax.violinplot(data, showmedians=True, showextrema=False)
    for pc, n in zip(parts["bodies"], names):
        pc.set_facecolor(COLORS[n])
        pc.set_edgecolor(COLORS[n])
        pc.set_alpha(0.42)
    ax.set_xticks(range(1, len(names) + 1))
    ax.set_xticklabels(
        ["Trad.\nAC", "AC+filter\n/storage", "Local\nSST", "SST+\ncoord.", "DC\nbackbone"],
        fontsize=7,
    )
    ax.set_ylabel("PCC voltage THD (%)")
    ax.set_title("b  Harmonic screening result", loc="left", fontsize=11, weight="bold")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[1, 0]
    for n in ["Traditional AC", "Local SST", "Subtransmission DC backbone"]:
        d = spec_p95[spec_p95.scenario == n]
        ax.plot(
            d.h,
            d.p95_individual_harmonic_voltage_pct,
            marker="o",
            label=n,
            color=COLORS[n],
            lw=1.4,
        )
    ax.set_xlabel("Harmonic order")
    ax.set_ylabel("95th percentile Vh/V1 (%)")
    ax.set_title("c  Individual harmonic voltage distortion", loc="left", fontsize=11, weight="bold")
    ax.legend(fontsize=7, frameon=False)
    ax.grid(alpha=0.25)

    ax = axes[1, 1]
    ax.plot(res_scan.harmonic_order, res_scan.nominal, label="nominal", color="0.3")
    ax.plot(res_scan.harmonic_order, res_scan.low_damping, label="low damping", color="#e6550d")
    ax.plot(res_scan.harmonic_order, res_scan.shifted, label="shifted resonance", color="#3182bd")
    ax.set_xlabel("Harmonic order")
    ax.set_ylabel("Network amplification factor")
    ax.set_title("d  Resonance scan", loc="left", fontsize=11, weight="bold")
    ax.legend(fontsize=7, frameon=False)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    savefig(fig, "fig3_harmonic_ownership_opendss_screening_v3")


def figure4():
    dyn = pd.read_csv(DATA / "dynamic_timeseries_v3.csv")
    metrics = pd.read_csv(DATA / "dynamic_metrics_v3.csv").set_index("architecture")
    sl = slice(0, min(len(dyn), int(150 / 0.02)))
    t = dyn.time_s.to_numpy()

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.8))

    ax = axes[0, 0]
    ax.plot(t[sl], dyn.AI_load_MW.to_numpy()[sl], color="0.55", lw=1.0, label="AI load")
    ax.plot(t[sl], dyn.grid_traditional_MW.to_numpy()[sl], color=COLORS["Traditional AC"], lw=0.8, label="Traditional AC")
    ax.plot(
        t[sl],
        dyn.grid_ac_filter_storage_MW.to_numpy()[sl],
        color=COLORS["AC + active filter/storage"],
        lw=1.0,
        label="AC + storage",
    )
    ax.plot(t[sl], dyn.grid_local_sst_MW.to_numpy()[sl], color=COLORS["Local SST"], lw=1.0, label="Local SST")
    ax.plot(
        t[sl],
        dyn.grid_dc_backbone_MW.to_numpy()[sl],
        color=COLORS["Subtransmission DC backbone"],
        lw=1.7,
        label="DC backbone",
    )
    ax.set_ylabel("Grid-side power (MW)")
    ax.set_xlabel("Time (s)")
    ax.set_title("a  AI training load and grid power", loc="left", fontsize=11, weight="bold")
    ax.legend(fontsize=7, ncol=2, frameon=False)
    ax.grid(alpha=0.25)

    ax = axes[0, 1]
    ax.plot(t[sl], dyn.pcc_v_ac_pct.to_numpy()[sl], color=COLORS["Traditional AC"], lw=0.8, label="Traditional AC")
    ax.plot(t[sl], dyn.pcc_v_local_sst_pct.to_numpy()[sl], color=COLORS["Local SST"], lw=1.0, label="Local SST")
    ax.plot(
        t[sl],
        dyn.pcc_v_dc_pct.to_numpy()[sl],
        color=COLORS["Subtransmission DC backbone"],
        lw=1.5,
        label="DC backbone",
    )
    ax.set_ylabel("PCC voltage-deviation proxy (%)")
    ax.set_xlabel("Time (s)")
    ax.set_title("b  Averaged voltage response", loc="left", fontsize=11, weight="bold")
    ax.legend(fontsize=7, frameon=False)
    ax.grid(alpha=0.25)

    ax = axes[1, 0]
    order = [
        "Traditional AC",
        "AC + active filter/storage",
        "Local SST",
        "Local SST + coordinated control",
        "Subtransmission DC backbone",
    ]
    rel = [metrics.loc[o, "relative_to_ac"] * 100 for o in order]
    ramp = [metrics.loc[o, "p99_ramp_MW_s"] for o in order]
    x = np.arange(len(order))
    w = 0.38
    ax.bar(x - w / 2, rel, width=w, color=[COLORS[o] for o in order], alpha=0.75, label="0.1-20 Hz energy (%)")
    ax2 = ax.twinx()
    ax2.plot(x + w / 2, ramp, marker="o", color="k", lw=1.2, label="p99 ramp")
    ax.set_xticks(x)
    ax.set_xticklabels(["Trad.\nAC", "AC+\nstorage", "Local\nSST", "SST+\ncoord.", "DC\nbackbone"], fontsize=7)
    ax.set_ylabel("Spectral energy vs AC (%)")
    ax2.set_ylabel("p99 ramp (MW/s)")
    ax.set_title("c  Frequency and ramp-rate mitigation", loc="left", fontsize=11, weight="bold")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[1, 1]
    buffer_power = dyn.dc_buffer_power_MW.to_numpy()
    buffer_energy = dyn.dc_buffer_energy_MWh.to_numpy()
    ax.plot(t[sl], buffer_power[sl], color="#e6550d", lw=1.3, label="buffer power")
    ax2 = ax.twinx()
    ax2.plot(t[sl], buffer_energy[sl] - buffer_energy[sl].min(), color="#756bb1", lw=1.0, label="energy state")
    ax.axhline(0, color="0.3", lw=0.7)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Shared DC buffer power (MW)")
    ax2.set_ylabel("Energy window (MWh)")
    ax.set_title("d  Shared DC buffer requirement", loc="left", fontsize=11, weight="bold")
    ax.grid(alpha=0.25)

    fig.tight_layout()
    savefig(fig, "fig4_voltage_stabilization_averaged_emt_v3")


def main():
    figure3()
    figure4()
    print(f"Reproduced Fig. 3 and Fig. 4 under {OUT}")


if __name__ == "__main__":
    main()
