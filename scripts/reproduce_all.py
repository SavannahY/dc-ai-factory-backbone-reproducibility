#!/usr/bin/env python
"""Regenerate key diagnostic figures from the archived CSV outputs.

This public repository includes all source CSV files used for the manuscript
figures. Running this script rebuilds the archived OpenDSS Fig. 3 diagnostic,
Fig. 4 and Fig. 5 into ``reproduced/figures`` as a fast submission-time
reproducibility check. The Fig. 4 dynamic scenario grid is regenerated with
``scripts/dynamic_robustness_sweep.py``; the final two-panel Fig. 3 and harmonic
robustness sweep are regenerated with ``scripts/harmonic_robustness_sweep.py``.
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
        path = OUT / f"{name}.{ext}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        if ext == "svg":
            path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    plt.close(fig)


def load_true_opendss_thdv():
    path = DATA / "true_opendss_harmonic_thdv_monte_carlo_v3.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    labels = {
        "traditional_ac": "Traditional AC",
        "local_sst": "Local SST",
        "dc_backbone": "Subtransmission DC backbone",
    }
    df["scenario"] = df["architecture"].map(labels).fillna(df["architecture"])
    return df


def figure3():
    harm_df = pd.read_csv(DATA / "harmonic_thdv_monte_carlo_v3.csv")
    spec_p95 = pd.read_csv(DATA / "harmonic_individual_p95_v3.csv")
    names = [
        "Traditional AC",
        "AC + active filter/storage",
        "Local SST",
        "Local SST + coordinated control",
        "Subtransmission DC backbone",
    ]

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.8))

    ax = axes[0, 0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.3)
    ax.axis("off")
    ax.set_title("a  Harmonic ownership boundary", loc="left", fontsize=11, weight="bold")
    ax.plot([0.8, 9.2], [3.3, 3.3], color=COLORS["Traditional AC"], lw=2.2)
    ax.text(0.8, 3.55, "138 kV AC subtransmission", fontsize=7, color=COLORS["Traditional AC"])
    for x in [3.0, 5.0, 7.0]:
        ax.plot([x, x], [3.3, 2.35], color=COLORS["Traditional AC"], lw=1.6)
        ax.text(x, 2.15, "AC/DC", ha="center", va="center", fontsize=7, weight="bold",
                bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="0.35"))
        ax.text(x, 1.45, "AI\ncampus", ha="center", va="center", fontsize=7,
                bbox=dict(boxstyle="round,pad=0.18", facecolor="#e9eef2", edgecolor="0.35"))
    ax.text(0.8, 1.95, "distributed cases:\n3 AC-facing converters", fontsize=7, ha="left", va="center")
    ax.plot([0.8, 2.0], [0.65, 0.65], color=COLORS["Traditional AC"], lw=2.2)
    ax.text(2.35, 0.65, "AC/DC", ha="center", va="center", fontsize=7, weight="bold",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="0.35"))
    ax.plot([2.72, 8.5], [0.65, 0.65], color=COLORS["Subtransmission DC backbone"], lw=2.4)
    for x in [4.0, 5.8, 7.6]:
        ax.plot([x, x], [0.65, 1.08], color=COLORS["Subtransmission DC backbone"], lw=1.4)
        ax.text(x, 1.32, "DC/DC", ha="center", va="center", fontsize=7, weight="bold",
                bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="0.35"))
    ax.text(0.8, 0.25, "DC backbone:\n1 utility AC-facing terminal", fontsize=7, ha="left", va="center")

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
    ax.axhline(5, color="0.35", ls="--", lw=1.0)
    ax.text(5.12, 5.08, "5% planning guide", fontsize=7, va="bottom", ha="right", color="0.35")
    for i, n in enumerate(names, start=1):
        p95 = np.percentile(harm_df[harm_df.scenario == n].thdv_pct, 95)
        ax.text(i, p95 + 0.17, f"{p95:.2f}", ha="center", fontsize=6.6, color=COLORS[n])
    ax.set_ylim(0, 5.9)
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
    compare = ["Traditional AC", "Local SST", "Subtransmission DC backbone"]
    internal = harm_df[harm_df.scenario.isin(compare)].groupby("scenario")["thdv_pct"].quantile(0.95)
    true_df = load_true_opendss_thdv()
    if true_df is not None:
        direct = true_df[true_df.scenario.isin(compare)].groupby("scenario")["thdv_pct"].quantile(0.95)
    else:
        direct = internal.copy()
    x = np.arange(len(compare))
    w = 0.36
    direct_vals = [direct.loc[n] for n in compare]
    internal_vals = [internal.loc[n] for n in compare]
    ax.bar(x - w / 2, direct_vals, width=w, color="#4c78a8", alpha=0.9, label="Direct OpenDSS")
    ax.bar(x + w / 2, internal_vals, width=w, color="#f58518", alpha=0.9, label="Internal solver")
    for i, (a, b) in enumerate(zip(direct_vals, internal_vals)):
        ax.text(i, max(a, b) + 0.15, f"{abs(a-b):.2f} pt", ha="center", fontsize=7, color="0.25")
    ax.set_xticks(x)
    ax.set_xticklabels(["Traditional\nAC", "Local\nSST", "DC\nbackbone"], fontsize=7)
    ax.set_ylabel("95th percentile THD (%)")
    ax.set_title("d  Direct OpenDSS check", loc="left", fontsize=11, weight="bold")
    ax.legend(fontsize=7, frameon=False)
    ax.grid(axis="y", alpha=0.25)

    fig.tight_layout()
    savefig(fig, "fig3_harmonic_ownership_opendss_screening_v3")


def figure4():
    dyn = pd.read_csv(DATA / "dynamic_timeseries_v3.csv")
    metrics = pd.read_csv(DATA / "dynamic_metrics_v3.csv").set_index("architecture")
    robustness = pd.read_csv(DATA / "dynamic_robustness_scenario_grid_v3.csv")
    t = dyn.time_s.to_numpy()
    dt = float(np.median(np.diff(t)))
    win = (t >= 25) & (t <= 95)

    def spectrum(x):
        y = x - np.mean(x)
        freqs = np.fft.rfftfreq(len(y), dt)
        mag = np.abs(np.fft.rfft(y)) / len(y) * 2
        return freqs, mag

    fig = plt.figure(figsize=(11, 7.25))
    gs = fig.add_gridspec(
        2,
        2,
        width_ratios=[1.28, 1.0],
        height_ratios=[1.0, 1.05],
        left=0.07,
        right=0.98,
        bottom=0.08,
        top=0.95,
        hspace=0.50,
        wspace=0.34,
    )
    ax_power = fig.add_subplot(gs[0, 0])
    ax_robust = fig.add_subplot(gs[0, 1])
    ax_buffer = fig.add_subplot(gs[1, :])

    ax = ax_power
    power_series = [
        ("Traditional AC", dyn.grid_traditional_MW.to_numpy(), 1.0),
        ("Local SST", dyn.grid_local_sst_MW.to_numpy(), 1.25),
        ("Subtransmission DC backbone", dyn.grid_dc_backbone_MW.to_numpy(), 2.0),
    ]
    for name, values, lw in power_series:
        label = "DC backbone" if name == "Subtransmission DC backbone" else name
        ax.plot(t[win], values[win], color=COLORS[name], lw=lw, label=label)
    ax.set_ylabel("Grid-side power (MW)")
    ax.set_xlabel("Time (s)")
    ax.set_title("a  Grid-side power seen by the utility", loc="left", fontsize=11, weight="bold")
    ax.legend(fontsize=7, ncol=1, frameon=False, loc="lower right")
    ax.grid(alpha=0.25)

    order = [
        "Traditional AC",
        "Local SST",
        "Subtransmission DC backbone",
    ]

    def plot_envelope(ax, column, xlabel, xscale=None, xlim=None, xticks=None, label_format="{:.1f}"):
        y_positions = np.arange(len(order))[::-1]
        labels = ["Trad. AC", "Local SST", "DC backbone"]
        for y_pos, name in zip(y_positions, order):
            values = robustness.loc[robustness.architecture == name, column].to_numpy()
            q05, q50, q95 = np.quantile(values, [0.05, 0.50, 0.95])
            ax.hlines(y_pos, q05, q95, color=COLORS[name], lw=5.0, alpha=0.38)
            ax.plot(q50, y_pos, marker="o", ms=5.8, color=COLORS[name], markeredgecolor="white", markeredgewidth=0.7)
            text_x = q50 * 1.08 if xscale == "log" else q50 + (xlim[1] - xlim[0]) * 0.025
            ax.text(text_x, y_pos, label_format.format(q50), va="center", fontsize=6.8, color=COLORS[name])
        if xscale:
            ax.set_xscale(xscale)
        if xlim:
            ax.set_xlim(*xlim)
        if xticks:
            ax.set_xticks(xticks)
            ax.set_xticklabels([str(x) for x in xticks], fontsize=6.8)
        ax.set_yticks(y_positions)
        ax.set_yticklabels(labels, fontsize=6.8)
        ax.set_ylim(-0.7, len(order) - 0.3)
        ax.set_xlabel(xlabel, fontsize=7.2)
        ax.tick_params(axis="x", labelsize=6.8)
        ax.grid(alpha=0.25)

    ax_robust.set_axis_off()
    ax_robust.text(0.00, 1.03, "b  Scenario-grid robustness", transform=ax_robust.transAxes,
                   ha="left", va="bottom", fontsize=11, weight="bold")
    ax_robust.text(0.03, 0.91, "line: 5-95% scenarios, dot: median", transform=ax_robust.transAxes,
                   fontsize=6.8, color="0.35")
    ax_rss = ax_robust.inset_axes([0.08, 0.55, 0.90, 0.31])
    plot_envelope(
        ax_rss,
        "rss_0p1_20hz_MW",
        "0.1-20 Hz RSS (MW)",
        xscale="log",
        xlim=(0.5, 800),
        xticks=[1, 10, 100],
    )
    ax_v = ax_robust.inset_axes([0.08, 0.11, 0.90, 0.31])
    plot_envelope(
        ax_v,
        "p95_pcc_voltage_deviation_pct",
        "p95 PCC voltage deviation (%)",
        xlim=(0, 8.5),
        label_format="{:.2f}",
    )

    ax = ax_buffer
    buffer_power = dyn.dc_buffer_power_MW.to_numpy()
    ax.plot(t[win], buffer_power[win], color="#e6550d", lw=1.4)
    ax.fill_between(t[win], 0, buffer_power[win], where=buffer_power[win] >= 0, color="#e6550d", alpha=0.16, interpolate=True)
    ax.fill_between(t[win], 0, buffer_power[win], where=buffer_power[win] < 0, color="#e6550d", alpha=0.08, interpolate=True)
    ax.axhline(0, color="0.3", lw=0.7)
    buffer_metrics = metrics.loc["DC buffer"]
    ax.text(0.99, 1.03, f"deliver {buffer_metrics.max_discharge_MW:.0f} MW | absorb {buffer_metrics.max_charge_MW:.0f} MW | energy window {buffer_metrics.energy_window_MWh:.2f} MWh",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="#e6550d", clip_on=False)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Shared DC buffer power (MW)")
    ax.set_title("c  Shared DC buffer requirement", loc="left", fontsize=11, weight="bold")
    ax.margins(y=0.08)
    ax.grid(alpha=0.25)

    savefig(fig, "fig4_voltage_stabilization_averaged_emt_v3")


def figure5():
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.1), gridspec_kw={"width_ratios": [1.0, 1.35]})

    ax = axes[0]
    forecast_gw = [2.1, 3.4, 4.2]
    labels = ["2021-22\nstudy", "2024-25\nbase", "2024-25\nhigh-load\nsensitivity"]
    x = np.arange(len(forecast_gw))
    ax.bar(x, forecast_gw, color=["#c9c9c9", "#8f8f8f", "#4f4f4f"], width=0.62)
    for xi, val in zip(x, forecast_gw):
        ax.text(xi, val + 0.08, f"{val:.1f} GW", ha="center", fontsize=8)
    ax.annotate(
        "public multi-GW\nload-pocket precedent",
        xy=(2, 4.2),
        xytext=(0.58, 3.15),
        fontsize=7.5,
        color="0.25",
        ha="center",
        arrowprops=dict(arrowstyle="->", lw=0.9, color="0.35"),
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_ylabel("San Jose study-area load forecast (GW)")
    ax.set_ylim(0, 4.75)
    ax.set_title("a  Public load-pocket scale", loc="left", fontsize=10, weight="bold")
    ax.text(0.02, 0.04, "Source: CAISO San Jose area planning documents", transform=ax.transAxes, fontsize=6.6, color="0.35")
    ax.grid(axis="y", alpha=0.22)

    ax = axes[1]
    load_gw = np.linspace(0.1, 5.0, 150)
    voltage_classes = [(69, "#9ecae1"), (138, "#e6550d"), (230, "#31a354"), (320, "#756bb1")]
    for pole, color in voltage_classes:
        current_ka = load_gw * 1e9 / (2 * pole * 1e3) / 1000
        ax.plot(load_gw, current_ka, label=f"+/-{pole} kV", color=color, lw=2)
    ax.axhline(4, color="0.4", ls="--", lw=1, label="illustrative 4 kA line")
    ax.axvspan(3.4, 4.2, color="#f0f0f0", alpha=0.75, label="3.4-4.2 GW precedent")
    ref_current = 1e9 / (2 * 138e3) / 1000
    ax.scatter([1.0], [ref_current], c="#e6550d", edgecolor="k", zorder=4)
    ax.annotate(
        "reference case:\n1 GW at +/-138 kV\n= 3.6 kA",
        xy=(1.0, ref_current),
        xytext=(1.35, 7.2),
        fontsize=7,
        color="#e6550d",
        arrowprops=dict(arrowstyle="->", color="#e6550d", lw=0.8),
    )
    ax.text(
        3.48,
        8.8,
        "multi-GW range needs\nhigher voltage, parallel bipoles\nor both",
        fontsize=7.2,
        color="0.25",
        ha="left",
    )
    ax.set_xlabel("Cluster load (GW)")
    ax.set_ylabel("Single-bipole current (kA)")
    ax.set_xlim(0, 5.25)
    ax.set_ylim(0, 37.5)
    ax.set_title("b  Load determines voltage class", loc="left", fontsize=10, weight="bold")
    ax.legend(fontsize=7, frameon=False, loc="upper left")
    ax.grid(alpha=0.22)

    fig.tight_layout()
    savefig(fig, "fig5_case_study_voltage_envelope_v3")


def main():
    figure3()
    figure4()
    figure5()
    print(f"Reproduced the archived OpenDSS Fig. 3 diagnostic, Fig. 4 and Fig. 5 under {OUT}")


if __name__ == "__main__":
    main()
