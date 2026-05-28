from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIG = ROOT / "figures"
DATA.mkdir(exist_ok=True)
FIG.mkdir(exist_ok=True)

SEED = 20260527
N_TRIALS = 600
PF = 0.98

ARCH_ORDER = ["Traditional AC", "Local SST", "Subtransmission DC backbone"]
SHORT = {
    "Traditional AC": "Traditional AC",
    "Local SST": "Local SST",
    "Subtransmission DC backbone": "DC backbone",
}
COLORS = {
    "Traditional AC": "#377eb8",
    "Local SST": "#984ea3",
    "Subtransmission DC backbone": "#e6550d",
}

N_GRID = [1, 3, 6, 10]
P_GRID_GW = [0.25, 1.0, 2.0, 4.5]
V_GRID_KV = [69, 138, 230, 320]
SCR_GRID = [3, 5, 10, 20]
PHASE_MODES = ["random", "partial", "coherent"]
LENGTH_GRID_KM = [5, 20, 50, 100]

HARMONICS = np.array([5, 7, 11, 13, 17, 19, 23, 25, 29, 31], dtype=float)
TRAD_FRAC = np.array([0.080, 0.060, 0.035, 0.025, 0.016, 0.013, 0.010, 0.009, 0.007, 0.006])
LOCAL_FRAC = TRAD_FRAC * np.array([0.38, 0.36, 0.32, 0.30, 0.28, 0.28, 0.25, 0.25, 0.22, 0.22])
DC_FRAC = TRAD_FRAC * np.array([0.055, 0.050, 0.043, 0.040, 0.035, 0.035, 0.030, 0.030, 0.028, 0.028])

ARCH_PARAMS = {
    "Traditional AC": {"fracs": TRAD_FRAC, "factor": 0.19, "sources": "distributed"},
    "Local SST": {"fracs": LOCAL_FRAC, "factor": 0.23, "sources": "distributed"},
    "Subtransmission DC backbone": {"fracs": DC_FRAC, "factor": 0.56, "sources": "single"},
}


def resonance_factor(h, shift=0.0, strength=1.0):
    return 1 + strength * (
        3.2 * np.exp(-0.5 * ((h - (11 + shift)) / 1.6) ** 2)
        + 1.7 * np.exp(-0.5 * ((h - (23 + 0.5 * shift)) / 2.0) ** 2)
    )


def source_phasor_sum(rng, n_sources, phase_mode, n_trials, n_harmonics):
    if n_sources == 1:
        phases = rng.uniform(0, 2 * np.pi, size=(n_trials, n_harmonics, 1))
    elif phase_mode == "random":
        phases = rng.uniform(0, 2 * np.pi, size=(n_trials, n_harmonics, n_sources))
    elif phase_mode == "partial":
        common = rng.uniform(0, 2 * np.pi, size=(n_trials, n_harmonics, 1))
        phases = common + rng.normal(0, 0.75, size=(n_trials, n_harmonics, n_sources))
    elif phase_mode == "coherent":
        common = rng.uniform(0, 2 * np.pi, size=(n_trials, n_harmonics, 1))
        phases = np.repeat(common, n_sources, axis=2)
    else:
        raise ValueError(f"unknown phase mode {phase_mode}")
    return np.exp(1j * phases).sum(axis=2)


def simulate_architecture(rng, arch, n_campuses, p_gw, v_kv, scr, phase_mode, length_km):
    params = ARCH_PARAMS[arch]
    p_w = p_gw * 1e9
    v_ll = v_kv * 1e3
    v_ph = v_ll / np.sqrt(3.0)
    s_sc = scr * p_w
    z1 = v_ll**2 / s_sc

    sc_mult = rng.triangular(0.55, 1.0, 1.6, size=N_TRIALS)
    shift = rng.normal(0, 1.0, size=N_TRIALS)
    strength = rng.triangular(0.5, 1.0, 1.8, size=N_TRIALS)
    res = resonance_factor(HARMONICS[None, :], shift[:, None], strength[:, None])

    # Corridor length changes the effective harmonic-impedance envelope. The effect is
    # intentionally moderate and equals one at the 20 km reference case.
    if params["sources"] == "distributed":
        length_multiplier = 1.0 + 0.22 * (np.sqrt(length_km / 20.0) - 1.0)
    else:
        length_multiplier = 1.0 + 0.05 * (np.sqrt(length_km / 20.0) - 1.0)
    length_multiplier = max(0.65, float(length_multiplier))

    z_h = (z1 / sc_mult[:, None]) * HARMONICS[None, :] * res * length_multiplier

    if params["sources"] == "distributed":
        i_site = p_w / n_campuses / (np.sqrt(3.0) * v_ll * PF)
        phasors = source_phasor_sum(rng, n_campuses, phase_mode, N_TRIALS, len(HARMONICS))
        i_h = i_site * params["fracs"][None, :] * phasors
        ac_facing_sources = n_campuses
    else:
        i_total = p_w / (np.sqrt(3.0) * v_ll * PF)
        phasors = source_phasor_sum(rng, 1, phase_mode, N_TRIALS, len(HARMONICS))
        i_h = i_total * params["fracs"][None, :] * phasors
        ac_facing_sources = 1

    v_h_pct = 100.0 * np.abs(i_h * z_h) / v_ph * params["factor"]
    thd = np.sqrt((v_h_pct**2).sum(axis=1))
    individual_p95 = np.quantile(v_h_pct, 0.95, axis=0)
    dominant_idx = int(np.argmax(individual_p95))

    row = {
        "architecture": arch,
        "campus_count": n_campuses,
        "cluster_load_GW": p_gw,
        "voltage_kV": v_kv,
        "short_circuit_ratio": scr,
        "phase_mode": phase_mode,
        "corridor_length_km": length_km,
        "ac_facing_sources": ac_facing_sources,
        "short_circuit_strength_GVA": p_gw * scr,
        "trials": N_TRIALS,
        "p50_thdv_pct": float(np.quantile(thd, 0.50)),
        "p95_thdv_pct": float(np.quantile(thd, 0.95)),
        "p99_thdv_pct": float(np.quantile(thd, 0.99)),
        "mean_thdv_pct": float(thd.mean()),
        "max_individual_p95_pct": float(individual_p95[dominant_idx]),
        "dominant_harmonic": int(HARMONICS[dominant_idx]),
        "exceeds_5pct_guide_p95": bool(np.quantile(thd, 0.95) > 5.0),
    }
    spec_rows = [
        {
            "architecture": arch,
            "campus_count": n_campuses,
            "cluster_load_GW": p_gw,
            "voltage_kV": v_kv,
            "short_circuit_ratio": scr,
            "phase_mode": phase_mode,
            "corridor_length_km": length_km,
            "h": int(h),
            "p95_individual_harmonic_voltage_pct": float(val),
        }
        for h, val in zip(HARMONICS, individual_p95)
    ]
    return row, spec_rows


def run_grid():
    rng = np.random.default_rng(SEED)
    rows = []
    spec_rows = []
    input_rows = []
    for n, p, v, scr, phase, length in product(N_GRID, P_GRID_GW, V_GRID_KV, SCR_GRID, PHASE_MODES, LENGTH_GRID_KM):
        input_rows.append(
            {
                "campus_count": n,
                "cluster_load_GW": p,
                "voltage_kV": v,
                "short_circuit_ratio": scr,
                "phase_mode": phase,
                "corridor_length_km": length,
                "short_circuit_strength_GVA": p * scr,
            }
        )
        for arch in ARCH_ORDER:
            row, spec = simulate_architecture(rng, arch, n, p, v, scr, phase, length)
            rows.append(row)
            spec_rows.extend(spec)

    grid = pd.DataFrame(rows)
    spec = pd.DataFrame(spec_rows)
    inputs = pd.DataFrame(input_rows)

    key = ["campus_count", "cluster_load_GW", "voltage_kV", "short_circuit_ratio", "phase_mode", "corridor_length_km"]
    wide = grid.pivot_table(index=key, columns="architecture", values="p95_thdv_pct").reset_index()
    wide["dc_vs_traditional_reduction_pct"] = 100.0 * (
        1.0 - wide["Subtransmission DC backbone"] / wide["Traditional AC"]
    )
    wide["dc_vs_local_reduction_pct"] = 100.0 * (1.0 - wide["Subtransmission DC backbone"] / wide["Local SST"])
    wide["local_vs_traditional_reduction_pct"] = 100.0 * (1.0 - wide["Local SST"] / wide["Traditional AC"])
    wide["dc_p95_minus_traditional_p95_pctpt"] = wide["Subtransmission DC backbone"] - wide["Traditional AC"]
    wide["dc_p95_minus_local_p95_pctpt"] = wide["Subtransmission DC backbone"] - wide["Local SST"]

    summary = []
    for arch, d in grid.groupby("architecture"):
        summary.append(
            {
                "group": "architecture",
                "level": arch,
                "cases": len(d),
                "median_p95_thdv_pct": d["p95_thdv_pct"].median(),
                "p90_p95_thdv_pct": d["p95_thdv_pct"].quantile(0.90),
                "p99_p95_thdv_pct": d["p95_thdv_pct"].quantile(0.99),
                "max_p95_thdv_pct": d["p95_thdv_pct"].max(),
                "fraction_exceeding_5pct_guide": d["exceeds_5pct_guide_p95"].mean(),
            }
        )
    for phase, d in grid.groupby("phase_mode"):
        for arch, da in d.groupby("architecture"):
            summary.append(
                {
                    "group": f"phase_mode={phase}",
                    "level": arch,
                    "cases": len(da),
                    "median_p95_thdv_pct": da["p95_thdv_pct"].median(),
                    "p90_p95_thdv_pct": da["p95_thdv_pct"].quantile(0.90),
                    "p99_p95_thdv_pct": da["p95_thdv_pct"].quantile(0.99),
                    "max_p95_thdv_pct": da["p95_thdv_pct"].max(),
                    "fraction_exceeding_5pct_guide": da["exceeds_5pct_guide_p95"].mean(),
                }
            )

    grid.to_csv(DATA / "harmonic_robustness_scenario_grid_v3.csv", index=False)
    spec.to_csv(DATA / "harmonic_robustness_individual_p95_v3.csv", index=False)
    inputs.to_csv(DATA / "harmonic_robustness_input_grid_v3.csv", index=False)
    wide.to_csv(DATA / "harmonic_robustness_architecture_comparison_v3.csv", index=False)
    pd.DataFrame(summary).to_csv(DATA / "harmonic_robustness_summary_v3.csv", index=False)
    return grid, spec, inputs, wide, pd.DataFrame(summary)


def savefig(fig, name):
    fig.savefig(FIG / f"{name}.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIG / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def make_main_two_panel():
    thd = pd.read_csv(DATA / "harmonic_thdv_monte_carlo_v3.csv")
    spec = pd.read_csv(DATA / "harmonic_individual_p95_v3.csv")
    thd = thd[thd["scenario"].isin(ARCH_ORDER)]
    spec = spec[spec["scenario"].isin(ARCH_ORDER)]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [0.9, 1.35]})
    ax = axes[0]
    p95 = thd.groupby("scenario")["thdv_pct"].quantile(0.95).reindex(ARCH_ORDER)
    y = np.arange(len(ARCH_ORDER))
    ax.barh(y, p95.values, color=[COLORS[a] for a in ARCH_ORDER], alpha=0.88)
    for yi, arch in enumerate(ARCH_ORDER):
        ax.text(p95.loc[arch] + 0.06, yi, f"p95 {p95.loc[arch]:.2f}", va="center", fontsize=7, color=COLORS[arch])
    ax.axvline(5, color="0.35", ls="--", lw=1.0)
    ax.text(5.02, 2.35, "5% guide", fontsize=7, va="top", color="0.35")
    ax.set_yticks(y)
    ax.set_yticklabels([SHORT[a] for a in ARCH_ORDER], fontsize=7)
    ax.set_xlabel("PCC voltage THD (%)")
    ax.set_xlim(0, 5.55)
    ax.grid(axis="x", alpha=0.18)
    ax.set_title("a  p95 harmonic screening", loc="left", fontsize=11, weight="bold")

    ax = axes[1]
    for arch in ARCH_ORDER:
        d = spec[spec["scenario"] == arch]
        ax.plot(
            d["h"],
            d["p95_individual_harmonic_voltage_pct"],
            marker="o",
            ms=3.5,
            lw=1.5,
            color=COLORS[arch],
            label=SHORT[arch],
        )
    ax.set_xlabel("Harmonic order")
    ax.set_ylabel("95th percentile Vh/V1 (%)")
    ax.grid(axis="y", alpha=0.16)
    ax.legend(fontsize=7, frameon=False, loc="upper right")
    ax.set_title("b  Harmonic orders driving THD", loc="left", fontsize=11, weight="bold")
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.16, top=0.88, wspace=0.34)
    savefig(fig, "fig3_harmonic_two_panel_screening_v3")


def make_robustness_figures(grid, wide):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.2))

    ax = axes[0, 0]
    data = [grid.loc[grid["architecture"] == arch, "p95_thdv_pct"].values for arch in ARCH_ORDER]
    bp = ax.boxplot(data, patch_artist=True, showfliers=False, widths=0.55)
    for patch, arch in zip(bp["boxes"], ARCH_ORDER):
        patch.set_facecolor(COLORS[arch])
        patch.set_alpha(0.45)
        patch.set_edgecolor(COLORS[arch])
    for med in bp["medians"]:
        med.set_color("0.15")
        med.set_linewidth(1.2)
    ax.axhline(5, color="0.35", ls="--", lw=1.0)
    ax.text(3.35, 5.1, "5% guide", fontsize=7, color="0.35", ha="right", va="bottom")
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(["Traditional\nAC", "Local\nSST", "DC\nbackbone"], fontsize=7)
    ax.set_ylabel("Scenario p95 THD (%)")
    ax.set_yscale("log")
    ax.grid(axis="y", alpha=0.18)
    ax.set_title("a  Full-grid p95 THD envelope", loc="left", fontsize=11, weight="bold")

    ax = axes[0, 1]
    phase_order = ["random", "partial", "coherent"]
    pivot = (
        wide.groupby(["short_circuit_ratio", "phase_mode"])["dc_vs_traditional_reduction_pct"]
        .median()
        .unstack("phase_mode")
        .reindex(index=SCR_GRID, columns=phase_order)
    )
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlGnBu", vmin=0, vmax=100)
    ax.set_xticks(np.arange(len(phase_order)))
    ax.set_xticklabels(phase_order, fontsize=7)
    ax.set_yticks(np.arange(len(SCR_GRID)))
    ax.set_yticklabels(SCR_GRID, fontsize=7)
    ax.set_xlabel("Phase coherence")
    ax.set_ylabel("Short-circuit ratio")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.values[i, j]
            ax.text(
                j,
                i,
                f"{val:.0f}%",
                ha="center",
                va="center",
                fontsize=7,
                color="white" if val >= 70 else "0.10",
            )
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label("median DC reduction vs traditional", fontsize=7)
    cb.ax.tick_params(labelsize=6)
    ax.set_title("b  Median DC reduction across grid", loc="left", fontsize=11, weight="bold")

    ax = axes[1, 0]
    for arch in ARCH_ORDER:
        med = (
            grid.loc[grid["architecture"] == arch]
            .groupby("short_circuit_ratio")["p95_thdv_pct"]
            .median()
            .reindex(SCR_GRID)
        )
        q90 = (
            grid.loc[grid["architecture"] == arch]
            .groupby("short_circuit_ratio")["p95_thdv_pct"]
            .quantile(0.90)
            .reindex(SCR_GRID)
        )
        ax.plot(SCR_GRID, med, marker="o", color=COLORS[arch], lw=1.5, label=f"{SHORT[arch]} median")
        ax.plot(SCR_GRID, q90, color=COLORS[arch], lw=0.9, ls=":", alpha=0.8)
    ax.axhline(5, color="0.35", ls="--", lw=1.0)
    ax.set_yscale("log")
    ax.set_xticks(SCR_GRID)
    ax.set_xticklabels(SCR_GRID, fontsize=7)
    ax.set_xlabel("Short-circuit ratio Ssc/P")
    ax.set_ylabel("Scenario p95 THD (%)")
    ax.grid(axis="y", alpha=0.18)
    ax.legend(fontsize=6.4, frameon=False, ncol=1)
    ax.text(0.03, 0.05, "solid: median; dotted: p90", transform=ax.transAxes, fontsize=6.5, color="0.35")
    ax.set_title("c  Grid strength dominates the envelope", loc="left", fontsize=11, weight="bold")

    ax = axes[1, 1]
    variables = [
        ("campus_count", "campus count"),
        ("cluster_load_GW", "cluster load"),
        ("voltage_kV", "voltage class"),
        ("short_circuit_ratio", "SCR"),
        ("phase_mode", "phase coherence"),
        ("corridor_length_km", "corridor length"),
    ]
    spans = []
    for col, label in variables:
        med = wide.groupby(col)["dc_vs_traditional_reduction_pct"].median()
        spans.append({"label": label, "span": med.max() - med.min()})
    sens = pd.DataFrame(spans).sort_values("span")
    y = np.arange(len(sens))
    ax.barh(y, sens["span"], color="0.55")
    ax.set_yticks(y)
    ax.set_yticklabels(sens["label"], fontsize=7)
    ax.set_xlabel("Span in median DC reduction (percentage points)")
    ax.grid(axis="x", alpha=0.18)
    ax.set_title("d  Which assumptions change relative conclusion", loc="left", fontsize=11, weight="bold")

    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.08, top=0.93, wspace=0.34, hspace=0.36)
    savefig(fig, "supp_fig_s5_harmonic_robustness_envelope_v3")

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8), sharey=True)
    for ax, phase in zip(axes, ["random", "partial", "coherent"]):
        d = wide[wide["phase_mode"] == phase].copy()
        d["dc_to_traditional_ratio"] = d["Subtransmission DC backbone"] / d["Traditional AC"]
        pivot = (
            d.groupby(["short_circuit_ratio", "campus_count"])["dc_to_traditional_ratio"]
            .median()
            .unstack("campus_count")
            .reindex(index=SCR_GRID, columns=N_GRID)
        )
        im = ax.imshow(pivot.values, aspect="auto", cmap="OrRd_r", vmin=0, vmax=0.4)
        ax.set_title(phase, fontsize=10, weight="bold")
        ax.set_xticks(np.arange(len(N_GRID)))
        ax.set_xticklabels(N_GRID, fontsize=7)
        ax.set_yticks(np.arange(len(SCR_GRID)))
        ax.set_yticklabels(SCR_GRID, fontsize=7)
        ax.set_xlabel("campus count")
        for i in range(pivot.shape[0]):
            for j in range(pivot.shape[1]):
                val = pivot.values[i, j]
                ax.text(
                    j,
                    i,
                    f"{val:.2f}",
                    ha="center",
                    va="center",
                    fontsize=6.7,
                    color="white" if val < 0.16 else "0.10",
                )
    axes[0].set_ylabel("short-circuit ratio")
    cb = fig.colorbar(im, ax=axes.ravel().tolist(), fraction=0.025, pad=0.02)
    cb.set_label("DC p95 THD / traditional p95 THD", fontsize=7)
    cb.ax.tick_params(labelsize=6)
    fig.suptitle("Supplementary Fig. S6 | Source-count and phase-coherence sensitivity", fontsize=11, weight="bold", y=0.98)
    savefig(fig, "supp_fig_s6_harmonic_sourcecount_phase_sensitivity_v3")


def main():
    grid, spec, inputs, wide, summary = run_grid()
    make_main_two_panel()
    make_robustness_figures(grid, wide)
    print(f"wrote {len(grid)} architecture scenarios from {len(inputs)} input grid points")
    print(DATA / "harmonic_robustness_scenario_grid_v3.csv")
    print(FIG / "supp_fig_s5_harmonic_robustness_envelope_v3.png")
    print(FIG / "supp_fig_s6_harmonic_sourcecount_phase_sensitivity_v3.png")


if __name__ == "__main__":
    main()
