from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

SEED = 20260528
DT = 0.02
DURATION_S = 240

ARCH_ORDER = ["Traditional AC", "Local SST", "Subtransmission DC backbone"]
TAU_S = {
    "Traditional AC": 0.0,
    "Local SST": 1.1,
    "Subtransmission DC backbone": 16.0,
}

N_GRID = [1, 3, 6, 10]
P_GRID_GW = [0.25, 1.0, 2.0, 4.5]
V_GRID_KV = [69, 138, 230, 320]
SCR_GRID = [3, 5, 10, 20]
PHASE_MODES = ["random", "partial", "coherent"]
LENGTH_GRID_KM = [5, 20, 50, 100]


def ai_load_pu(tt):
    p = np.ones_like(tt, dtype=float)
    for k in np.arange(-240 + 5, 480, 7.0):
        p -= 0.28 * np.exp(-0.5 * ((tt - k) / 0.45) ** 2)
    for k in np.arange(-240 + 35, 480, 70.0):
        p -= 0.23 * np.exp(-0.5 * ((tt - k) / 1.2) ** 2)
    p += 0.015 * np.sin(2 * np.pi * 0.045 * tt)
    p += 0.006 * np.sin(2 * np.pi * 0.33 * tt + 0.4)
    return np.clip(p, 0.48, 1.08)


def campus_offsets(rng, n_campuses, phase_mode):
    if n_campuses == 1:
        return np.zeros(1)
    if phase_mode == "coherent":
        return np.zeros(n_campuses)
    if phase_mode == "partial":
        common = rng.uniform(0, 70)
        return common + rng.normal(0, 1.4, size=n_campuses)
    if phase_mode == "random":
        return rng.uniform(0, 70, size=n_campuses)
    raise ValueError(f"unknown phase mode {phase_mode}")


def aggregate_load(t, rng, n_campuses, phase_mode, cluster_load_gw):
    offsets = campus_offsets(rng, n_campuses, phase_mode)
    campus = np.vstack([ai_load_pu(t + offset) for offset in offsets])
    pu = campus.mean(axis=0)
    pu = pu / pu.mean()
    return pu * cluster_load_gw * 1000.0


def lpf(x, tau, dt=DT):
    if tau <= 0:
        return x.copy()
    y = np.empty_like(x)
    y[0] = x[0]
    a = dt / (tau + dt)
    for i in range(1, len(x)):
        y[i] = y[i - 1] + a * (x[i] - y[i - 1])
    return y


def spectral_rss(x, dt=DT, fmin=0.1, fmax=20):
    y = x - np.mean(x)
    freqs = np.fft.rfftfreq(len(y), dt)
    mag = np.abs(np.fft.rfft(y)) / len(y) * 2
    mask = (freqs >= fmin) & (freqs <= fmax)
    return float(np.sqrt(np.sum(mag[mask] ** 2)))


def voltage_multiplier(voltage_kv, length_km):
    raw = 1.0 + 0.08 * (length_km / 20.0) * (138.0 / voltage_kv) ** 2
    reference = 1.0 + 0.08
    return raw / reference


def simulate_grid():
    rng = np.random.default_rng(SEED)
    t = np.arange(0, DURATION_S, DT)
    rows = []
    input_rows = []
    profile_cache = {}
    grid_cache = {}
    for n, phase in product(N_GRID, PHASE_MODES):
        load_1gw = aggregate_load(t, rng, n, phase, 1.0)
        profile_cache[(n, phase)] = load_1gw
        for arch in ARCH_ORDER:
            grid_cache[(n, phase, arch)] = lpf(load_1gw, TAU_S[arch])

    for n, p_gw, v_kv, scr, phase, length in product(
        N_GRID, P_GRID_GW, V_GRID_KV, SCR_GRID, PHASE_MODES, LENGTH_GRID_KM
    ):
        input_rows.append(
            {
                "campus_count": n,
                "cluster_load_GW": p_gw,
                "voltage_kV": v_kv,
                "short_circuit_ratio": scr,
                "phase_mode": phase,
                "corridor_length_km": length,
                "short_circuit_strength_GVA": p_gw * scr,
            }
        )
        p_nom_mw = p_gw * 1000.0
        ssc_mw = scr * p_nom_mw
        v_mult = voltage_multiplier(v_kv, length)
        for arch in ARCH_ORDER:
            load = profile_cache[(n, phase)] * p_gw
            grid = grid_cache[(n, phase, arch)] * p_gw
            rss_mw = spectral_rss(grid)
            ramp_mw_s = float(np.percentile(np.abs(np.diff(grid) / DT), 99))
            pcc_v_pct = 100.0 * (grid - grid.mean()) / ssc_mw * v_mult
            row = {
                "architecture": arch,
                "campus_count": n,
                "cluster_load_GW": p_gw,
                "voltage_kV": v_kv,
                "short_circuit_ratio": scr,
                "phase_mode": phase,
                "corridor_length_km": length,
                "rss_0p1_20hz_MW": rss_mw,
                "rss_0p1_20hz_pct_load": 100.0 * rss_mw / p_nom_mw,
                "p99_ramp_MW_s": ramp_mw_s,
                "p99_ramp_pct_load_per_s": 100.0 * ramp_mw_s / p_nom_mw,
                "p95_pcc_voltage_deviation_pct": float(np.quantile(np.abs(pcc_v_pct), 0.95)),
            }
            if arch == "Subtransmission DC backbone":
                buffer = load - grid
                e_mwh = np.cumsum(buffer) * DT / 3600.0
                row.update(
                    {
                        "buffer_energy_window_MWh": float(e_mwh.max() - e_mwh.min()),
                        "buffer_energy_window_MWh_per_GW": float((e_mwh.max() - e_mwh.min()) / p_gw),
                        "buffer_max_discharge_MW_per_GW": float(buffer.max() / p_gw),
                        "buffer_max_charge_MW_per_GW": float((-buffer.min()) / p_gw),
                    }
                )
            rows.append(row)

    scenario = pd.DataFrame(rows)
    inputs = pd.DataFrame(input_rows)

    key = ["campus_count", "cluster_load_GW", "voltage_kV", "short_circuit_ratio", "phase_mode", "corridor_length_km"]
    ramp_wide = scenario.pivot_table(index=key, columns="architecture", values="p99_ramp_pct_load_per_s").reset_index()
    voltage_wide = scenario.pivot_table(index=key, columns="architecture", values="p95_pcc_voltage_deviation_pct").reset_index()
    comparison = ramp_wide.merge(voltage_wide, on=key, suffixes=("_ramp_pct_load_per_s", "_p95_voltage_pct"))
    comparison["dc_ramp_reduction_vs_traditional_pct"] = (
        1.0
        - comparison["Subtransmission DC backbone_ramp_pct_load_per_s"]
        / comparison["Traditional AC_ramp_pct_load_per_s"]
    ) * 100.0
    comparison["dc_voltage_reduction_vs_traditional_pct"] = (
        1.0
        - comparison["Subtransmission DC backbone_p95_voltage_pct"]
        / comparison["Traditional AC_p95_voltage_pct"]
    ) * 100.0

    summary_rows = []
    for arch, d in scenario.groupby("architecture"):
        summary_rows.append(
            {
                "group": "architecture",
                "level": arch,
                "n_scenarios": len(d),
                "median_p99_ramp_pct_load_per_s": d["p99_ramp_pct_load_per_s"].median(),
                "p95_p99_ramp_pct_load_per_s": d["p99_ramp_pct_load_per_s"].quantile(0.95),
                "median_p95_pcc_voltage_deviation_pct": d["p95_pcc_voltage_deviation_pct"].median(),
                "p95_p95_pcc_voltage_deviation_pct": d["p95_pcc_voltage_deviation_pct"].quantile(0.95),
            }
        )
    summary = pd.DataFrame(summary_rows)

    inputs.to_csv(DATA / "dynamic_robustness_input_grid_v3.csv", index=False)
    scenario.to_csv(DATA / "dynamic_robustness_scenario_grid_v3.csv", index=False)
    comparison.to_csv(DATA / "dynamic_robustness_architecture_comparison_v3.csv", index=False)
    summary.to_csv(DATA / "dynamic_robustness_summary_v3.csv", index=False)
    return scenario, summary


if __name__ == "__main__":
    scenario, summary = simulate_grid()
    print(DATA / "dynamic_robustness_scenario_grid_v3.csv")
    print(summary.to_string(index=False))
