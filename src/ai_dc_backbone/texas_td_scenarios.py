"""C0/C1/C2/C3 screening models for Texas T&D load-pocket studies.

The module is intentionally dependency-light.  It can build a corridor catalog
from a MATPOWER case when one is available, and otherwise falls back to archived
screening catalogs for the Full Texas T&D and Austin/Travis validation cases.
The fallback catalogs are not substitutes for the downloaded Texas A&M cases;
they make the scenario definitions and regression tests reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd


ARCHITECTURES = {
    "C0": "C0/C1 Traditional 400 V AC",
    "C2": "MV SST",
    "C3": "Converted DC backbone",
}

HARMONICS = np.array([5, 7, 11, 13, 17, 19, 23, 25], dtype=float)
BASE_HARMONIC_FRAC = np.array([0.080, 0.060, 0.035, 0.025, 0.016, 0.013, 0.010, 0.009])
HARMONIC_SCREENING_TRANSFER = 0.085
EASTERN_INTERCONNECTION_2024_SAG_EVENTS = (
    (30.0, 0.38, 0.042),
    (46.4, 0.35, 0.050),
    (62.8, 0.40, 0.066),
    (79.2, 0.25, 0.058),
    (95.6, 0.32, 0.045),
    (112.0, 0.37, 0.060),
)


@dataclass(frozen=True)
class CorridorCase:
    """A candidate transmission corridor or load-pocket source path."""

    dataset_id: str
    dataset_role: str
    pocket_id: str
    source_bus: str
    load_bus: str
    voltage_kv: float
    length_km: float
    r_ohm_km: float
    x_ohm_km: float
    current_limit_kA: float
    short_circuit_gva: float
    source_q_limit_mvar: float
    converter_rating_mw: float
    existing_load_mw: float = 0.0
    vdc_pp_kv: float | None = None

    @property
    def effective_vdc_pp_kv(self) -> float:
        return self.vdc_pp_kv if self.vdc_pp_kv is not None else 2.0 * self.voltage_kv

    @property
    def r_total_ohm(self) -> float:
        return self.r_ohm_km * self.length_km

    @property
    def x_total_ohm(self) -> float:
        return self.x_ohm_km * self.length_km

    @property
    def s_base_mva(self) -> float:
        return max(100.0, self.short_circuit_gva * 1000.0)

    @property
    def z_base_ohm(self) -> float:
        return self.voltage_kv**2 / self.s_base_mva

    @property
    def line_z_pu(self) -> complex:
        return complex(self.r_total_ohm / self.z_base_ohm, self.x_total_ohm / self.z_base_ohm)

    @property
    def current_base_kA(self) -> float:
        return self.s_base_mva / (math.sqrt(3.0) * self.voltage_kv)


@dataclass(frozen=True)
class ScenarioConfig:
    """Architecture-specific assumptions at the 800 VDC useful-load boundary."""

    scenario_id: str
    label: str
    ac_pf: float
    downstream_efficiency: float
    terminal_efficiency: float
    dc_stage_efficiency: float
    local_q_support_mvar: float
    grid_tau_s: float
    harmonic_scale: float
    harmonic_source_count: int
    load_interface: str
    load_boundary_voltage_v: float
    voltage_support_pu: float
    ride_through_current_cap_pu: float
    ride_through_recovery_tau_s: float
    dc_buffer_for_ride_through: bool
    voltage_support_location: str
    voltage_support_role: str
    var_coordination_risk: str


SCENARIOS = {
    "C0": ScenarioConfig(
        scenario_id="C0",
        label=ARCHITECTURES["C0"],
        ac_pf=0.98,
        downstream_efficiency=0.991 * 0.982,
        terminal_efficiency=1.0,
        dc_stage_efficiency=1.0,
        local_q_support_mvar=0.0,
        grid_tau_s=0.0,
        harmonic_scale=1.0,
        harmonic_source_count=3,
        load_interface="400 V AC facility distribution",
        load_boundary_voltage_v=400.0,
        voltage_support_pu=0.0,
        ride_through_current_cap_pu=1.70,
        ride_through_recovery_tau_s=5.0,
        dc_buffer_for_ride_through=False,
        voltage_support_location="none",
        voltage_support_role="baseline voltage-sensitive load without active dynamic VAR support",
        var_coordination_risk="not applicable",
    ),
    "C2": ScenarioConfig(
        scenario_id="C2",
        label=ARCHITECTURES["C2"],
        ac_pf=0.995,
        downstream_efficiency=0.985,
        terminal_efficiency=1.0,
        dc_stage_efficiency=1.0,
        local_q_support_mvar=160.0,
        grid_tau_s=1.1,
        harmonic_scale=0.32,
        harmonic_source_count=3,
        load_interface="800 V DC data-center interface",
        load_boundary_voltage_v=800.0,
        voltage_support_pu=0.10,
        ride_through_current_cap_pu=1.25,
        ride_through_recovery_tau_s=1.0,
        dc_buffer_for_ride_through=False,
        voltage_support_location="34.5 kV AC side near the data-center SST",
        voltage_support_role="local distributed SST and dynamic VAR support at the data-center interface",
        var_coordination_risk=(
            "local Volt-VAR controls can fight nearby inverters or slower utility LTC, regulator, "
            "capacitor-bank, STATCOM or SVC controls without supervisory coordination"
        ),
    ),
    "C3": ScenarioConfig(
        scenario_id="C3",
        label=ARCHITECTURES["C3"],
        ac_pf=1.0,
        downstream_efficiency=1.0,
        terminal_efficiency=0.994,
        dc_stage_efficiency=0.994 * 0.992,
        local_q_support_mvar=260.0,
        grid_tau_s=16.0,
        harmonic_scale=0.055,
        harmonic_source_count=1,
        load_interface="800 V DC data-center interface",
        load_boundary_voltage_v=800.0,
        voltage_support_pu=0.16,
        ride_through_current_cap_pu=1.25,
        ride_through_recovery_tau_s=0.6,
        dc_buffer_for_ride_through=True,
        voltage_support_location="115/138 kV data-center interconnection AC side",
        voltage_support_role="centralized utility-side dynamic VAR support at the interconnection or AC/DC terminal",
        var_coordination_risk=(
            "centralized support reduces campus-to-campus control fighting but requires utility-side "
            "ownership, protection coordination and adequate high-voltage VAR rating"
        ),
    ),
}


SCENARIO_ALIASES = {"C1": "C0"}


def normalize_scenario_id(scenario_id: str) -> str:
    """Map equivalent user-facing scenario names to internal IDs."""

    normalized = scenario_id.upper()
    return SCENARIO_ALIASES.get(normalized, normalized)


def default_corridors() -> list[CorridorCase]:
    """Return archived screening corridors for datasets A and B.

    The values are engineering-screening assumptions calibrated to the voltage
    classes and scale of the Texas7k/Full-Texas and Austin/Travis examples.
    They are used only when the downloaded MATPOWER case is not supplied.
    """

    rows = [
        ("A", "Full Texas Combined T&D", "FTX-HOU-138-01", "A_1412", "A_1890", 138, 18, 0.010, 0.095, 5.5, 10.5, 470, 1650, 210),
        ("A", "Full Texas Combined T&D", "FTX-DFW-138-02", "A_2301", "A_2388", 138, 26, 0.011, 0.105, 5.2, 8.5, 410, 1500, 180),
        ("A", "Full Texas Combined T&D", "FTX-AUS-138-03", "A_3310", "A_3372", 138, 14, 0.010, 0.088, 5.8, 11.8, 520, 1800, 130),
        ("A", "Full Texas Combined T&D", "FTX-SAT-138-04", "A_4108", "A_4210", 138, 31, 0.012, 0.115, 4.8, 6.8, 360, 1380, 160),
        ("A", "Full Texas Combined T&D", "FTX-WTX-138-05", "A_5124", "A_5242", 138, 46, 0.013, 0.125, 4.5, 5.5, 330, 1220, 90),
        ("A", "Full Texas Combined T&D", "FTX-RGV-138-06", "A_6101", "A_6189", 138, 34, 0.012, 0.118, 4.9, 6.0, 350, 1350, 120),
        ("A", "Full Texas Combined T&D", "FTX-345-138-07", "A_0905", "A_0960", 138, 22, 0.010, 0.092, 6.1, 13.5, 560, 1900, 260),
        ("A", "Full Texas Combined T&D", "FTX-COAST-138-08", "A_7014", "A_7085", 138, 28, 0.011, 0.105, 5.0, 7.2, 390, 1450, 150),
        ("B", "Austin-Travis 150-bus T&D", "ATX-138-01", "B_12", "B_47", 138, 12, 0.010, 0.090, 4.2, 5.0, 260, 950, 80),
        ("B", "Austin-Travis 150-bus T&D", "ATX-138-02", "B_18", "B_64", 138, 19, 0.011, 0.102, 4.0, 4.5, 240, 900, 65),
        ("B", "Austin-Travis 150-bus T&D", "ATX-138-03", "B_21", "B_83", 138, 25, 0.012, 0.110, 3.8, 3.9, 220, 820, 55),
        ("B", "Austin-Travis 150-bus T&D", "ATX-230-138-04", "B_04", "B_101", 138, 15, 0.010, 0.095, 4.6, 5.8, 300, 1050, 95),
    ]
    return [
        CorridorCase(
            dataset_id=dataset_id,
            dataset_role=dataset_role,
            pocket_id=pocket_id,
            source_bus=source_bus,
            load_bus=load_bus,
            voltage_kv=float(voltage_kv),
            length_km=float(length_km),
            r_ohm_km=float(r_ohm_km),
            x_ohm_km=float(x_ohm_km),
            current_limit_kA=float(current_limit_kA),
            short_circuit_gva=float(short_circuit_gva),
            source_q_limit_mvar=float(source_q_limit_mvar),
            converter_rating_mw=float(converter_rating_mw),
            existing_load_mw=float(existing_load_mw),
        )
        for (
            dataset_id,
            dataset_role,
            pocket_id,
            source_bus,
            load_bus,
            voltage_kv,
            length_km,
            r_ohm_km,
            x_ohm_km,
            current_limit_kA,
            short_circuit_gva,
            source_q_limit_mvar,
            converter_rating_mw,
            existing_load_mw,
        ) in rows
    ]


def _parse_matpower_matrix(text: str, key: str) -> np.ndarray:
    pattern = re.compile(rf"mpc\.{re.escape(key)}\s*=\s*\[(.*?)\];", re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"MATPOWER case does not contain mpc.{key}")
    rows: list[list[float]] = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.split("%", 1)[0].strip().rstrip(";")
        if not line:
            continue
        values = [float(part) for part in line.split()]
        rows.append(values)
    if not rows:
        raise ValueError(f"mpc.{key} is empty")
    return np.array(rows, dtype=float)


def load_matpower_corridors(
    path: str | Path,
    dataset_id: str = "A",
    dataset_role: str = "Full Texas Combined T&D",
    max_corridors: int = 48,
) -> list[CorridorCase]:
    """Build a 138 kV corridor catalog from a MATPOWER case file.

    MATPOWER does not carry physical line length in the standard branch table,
    so this reader estimates an effective length from branch reactance and a
    representative 138 kV reactance per km.  If ``rateA`` is missing, a
    conservative 5 kA corridor current limit is used.
    """

    text = Path(path).read_text()
    bus = _parse_matpower_matrix(text, "bus")
    branch = _parse_matpower_matrix(text, "branch")
    bus_by_id = {int(row[0]): row for row in bus}
    corridors: list[CorridorCase] = []
    for idx, row in enumerate(branch):
        if len(row) < 11 or int(row[10]) == 0:
            continue
        fbus = int(row[0])
        tbus = int(row[1])
        if fbus not in bus_by_id or tbus not in bus_by_id:
            continue
        kv_f = float(bus_by_id[fbus][9])
        kv_t = float(bus_by_id[tbus][9])
        if not (120.0 <= kv_f <= 170.0 and 120.0 <= kv_t <= 170.0):
            continue
        kv = 0.5 * (kv_f + kv_t)
        rate_mva = float(row[5]) if len(row) > 5 and row[5] > 0 else 0.0
        current_limit = rate_mva / (math.sqrt(3.0) * kv) if rate_mva > 0 else 5.0
        current_limit = min(max(current_limit, 2.0), 7.0)
        x_pu = abs(float(row[3]))
        r_pu = abs(float(row[2]))
        z_base = kv**2 / 100.0
        x_ohm = x_pu * z_base
        r_ohm = max(r_pu * z_base, 0.01)
        length_km = min(max(x_ohm / 0.10, 5.0), 120.0)
        r_ohm_km = max(r_ohm / length_km, 0.004)
        x_ohm_km = max(x_ohm / length_km, 0.060)
        pd = float(bus_by_id[tbus][2])
        short_circuit_gva = max(3.0, min(16.0, rate_mva / 250.0 if rate_mva > 0 else 6.0))
        corridors.append(
            CorridorCase(
                dataset_id=dataset_id,
                dataset_role=dataset_role,
                pocket_id=f"{dataset_id}-mpc-{idx:04d}",
                source_bus=str(fbus),
                load_bus=str(tbus),
                voltage_kv=kv,
                length_km=length_km,
                r_ohm_km=r_ohm_km,
                x_ohm_km=x_ohm_km,
                current_limit_kA=current_limit,
                short_circuit_gva=short_circuit_gva,
                source_q_limit_mvar=max(220.0, min(620.0, short_circuit_gva * 45.0)),
                converter_rating_mw=max(800.0, min(2200.0, rate_mva * 0.95 if rate_mva > 0 else 1250.0)),
                existing_load_mw=pd,
            )
        )
        if len(corridors) >= max_corridors:
            break
    if not corridors:
        raise ValueError("No in-service 138 kV corridors were found in the MATPOWER case")
    return corridors


def solve_ac_corridor(
    corridor: CorridorCase,
    useful_mw: float,
    config: ScenarioConfig,
    voltage_min_pu: float = 0.95,
) -> dict[str, float | bool | str]:
    """Solve a two-bus AC loadability screen for C0/C2."""

    p_corridor_mw = useful_mw / config.downstream_efficiency + corridor.existing_load_mw
    pf = min(0.9999, max(0.8, config.ac_pf))
    q_load_mvar = p_corridor_mw * math.tan(math.acos(pf))
    q_corridor_mvar = max(0.0, q_load_mvar - config.local_q_support_mvar)
    p_pu = p_corridor_mw / corridor.s_base_mva
    q_pu = q_corridor_mvar / corridor.s_base_mva
    z = corridor.line_z_pu
    vs = complex(1.0, 0.0)
    x = np.array([1.0, 0.0], dtype=float)

    def mismatch(v: np.ndarray) -> np.ndarray:
        vr = complex(v[0], v[1])
        current = (vs - vr) / z
        s_recv = vr * np.conjugate(current)
        return np.array([s_recv.real - p_pu, s_recv.imag - q_pu])

    converged = False
    for _ in range(40):
        f = mismatch(x)
        if float(np.linalg.norm(f)) < 1e-9:
            converged = True
            break
        jac = np.empty((2, 2), dtype=float)
        h = 1e-6
        for j in range(2):
            xp = x.copy()
            xp[j] += h
            jac[:, j] = (mismatch(xp) - f) / h
        try:
            step = np.linalg.solve(jac, -f)
        except np.linalg.LinAlgError:
            break
        old_norm = float(np.linalg.norm(f))
        alpha = 1.0
        while alpha > 1e-4:
            candidate = x + alpha * step
            if float(np.linalg.norm(mismatch(candidate))) < old_norm:
                x = candidate
                break
            alpha *= 0.5
        else:
            break

    vr = complex(x[0], x[1])
    line_current_kA = abs((vs - vr) / z) * corridor.current_base_kA
    s_send_mva = vs * np.conjugate((vs - vr) / z) * corridor.s_base_mva
    current_margin = corridor.current_limit_kA - line_current_kA
    q_margin = corridor.source_q_limit_mvar - float(s_send_mva.imag)
    voltage_min = abs(vr)
    line_loading_pct = 100.0 * line_current_kA / corridor.current_limit_kA
    line_loss_mw = 3.0 * (line_current_kA * 1000.0) ** 2 * corridor.r_total_ohm / 1e6
    existing_current_kA = 0.0
    if corridor.existing_load_mw > 0.0:
        existing_current_kA = corridor.existing_load_mw / (math.sqrt(3.0) * corridor.voltage_kv * pf)
    baseline_line_loss_mw = 3.0 * (existing_current_kA * 1000.0) ** 2 * corridor.r_total_ohm / 1e6
    incremental_line_loss_mw = max(0.0, line_loss_mw - baseline_line_loss_mw)
    conversion_loss_mw = useful_mw * (1.0 / config.downstream_efficiency - 1.0)
    input_mw = useful_mw / config.downstream_efficiency + incremental_line_loss_mw
    efficiency = useful_mw / input_mw if input_mw > 0 else 0.0
    stability_margin_mw = _stability_margin_mw(corridor, p_corridor_mw)

    binding = "none"
    if not converged:
        binding = "power_flow_nonconvergence"
    elif voltage_min < voltage_min_pu:
        binding = "voltage_limit"
    elif q_margin < 0:
        binding = "reactive_power_limit"
    elif current_margin < 0:
        binding = "thermal_current_limit"
    elif stability_margin_mw < 0:
        binding = "stability_screen"

    return {
        "useful_mw": useful_mw,
        "corridor_transfer_mw": p_corridor_mw,
        "loss_mw": incremental_line_loss_mw + conversion_loss_mw,
        "efficiency_to_load_boundary": efficiency,
        "efficiency_to_800v": efficiency,
        "voltage_min_pu": voltage_min,
        "line_loading_pct": line_loading_pct,
        "line_current_kA": line_current_kA,
        "source_q_mvar": float(s_send_mva.imag),
        "q_margin_mvar": q_margin,
        "stability_margin_mw": stability_margin_mw,
        "binding_constraint": binding,
        "converged": converged,
    }


def solve_dc_corridor(corridor: CorridorCase, useful_mw: float, config: ScenarioConfig) -> dict[str, float | bool | str]:
    """Screen the converted DC backbone case for the same physical corridor."""

    dc_load_mw = useful_mw / config.dc_stage_efficiency
    current_kA = dc_load_mw / corridor.effective_vdc_pp_kv
    pole_loss_mw = 2.0 * (current_kA * 1000.0) ** 2 * corridor.r_total_ohm / 1e6
    converter_input_mw = (dc_load_mw + pole_loss_mw) / config.terminal_efficiency
    loss_mw = converter_input_mw - useful_mw
    q_margin = corridor.source_q_limit_mvar + config.local_q_support_mvar
    line_loading_pct = 100.0 * current_kA / corridor.current_limit_kA
    voltage_min_pu = 0.995
    binding = "none"
    if current_kA > corridor.current_limit_kA:
        binding = "dc_current_limit"
    elif useful_mw > corridor.converter_rating_mw:
        binding = "converter_rating_limit"

    return {
        "useful_mw": useful_mw,
        "corridor_transfer_mw": dc_load_mw,
        "loss_mw": loss_mw,
        "efficiency_to_load_boundary": useful_mw / converter_input_mw if converter_input_mw > 0 else 0.0,
        "efficiency_to_800v": useful_mw / converter_input_mw if converter_input_mw > 0 else 0.0,
        "voltage_min_pu": voltage_min_pu,
        "line_loading_pct": line_loading_pct,
        "line_current_kA": current_kA,
        "source_q_mvar": 0.0,
        "q_margin_mvar": q_margin,
        "stability_margin_mw": math.inf,
        "binding_constraint": binding,
        "converged": True,
    }


def _stability_margin_mw(corridor: CorridorCase, transfer_mw: float) -> float:
    """Simple steady-state stability-margin proxy for AC corridors."""

    x = max(corridor.x_total_ohm, 0.01)
    pmax_mw = 0.72 * corridor.voltage_kv**2 / x
    pmax_mw *= min(1.15, max(0.70, corridor.short_circuit_gva / 8.0))
    return pmax_mw - transfer_mw


def evaluate_scenario(corridor: CorridorCase, scenario_id: str, useful_mw: float) -> dict[str, float | bool | str]:
    scenario_id = normalize_scenario_id(scenario_id)
    config = SCENARIOS[scenario_id]
    if scenario_id == "C3":
        metrics = solve_dc_corridor(corridor, useful_mw, config)
    else:
        metrics = solve_ac_corridor(corridor, useful_mw, config)
    return {
        "dataset_id": corridor.dataset_id,
        "dataset_role": corridor.dataset_role,
        "pocket_id": corridor.pocket_id,
        "source_bus": corridor.source_bus,
        "load_bus": corridor.load_bus,
        "scenario_id": scenario_id,
        "architecture": config.label,
        "load_interface": config.load_interface,
        "load_boundary_voltage_v": config.load_boundary_voltage_v,
        "voltage_support_location": config.voltage_support_location,
        "voltage_support_role": config.voltage_support_role,
        "var_coordination_risk": config.var_coordination_risk,
        "voltage_kv": corridor.voltage_kv,
        "vdc_pp_kv": corridor.effective_vdc_pp_kv if scenario_id == "C3" else np.nan,
        "corridor_length_km": corridor.length_km,
        "current_limit_kA": corridor.current_limit_kA,
        "short_circuit_gva": corridor.short_circuit_gva,
        **metrics,
    }


def hosting_capacity(
    corridor: CorridorCase,
    scenario_id: str,
    lower_mw: float = 20.0,
    upper_mw: float | None = None,
    tolerance_mw: float = 2.5,
) -> dict[str, float | bool | str]:
    """Find maximum useful MW before a scenario violates a screening limit."""

    scenario_id = normalize_scenario_id(scenario_id)
    if upper_mw is None:
        upper_mw = max(500.0, corridor.converter_rating_mw * 1.6)
    low = lower_mw
    high = upper_mw
    low_row = evaluate_scenario(corridor, scenario_id, low)
    if low_row["binding_constraint"] != "none":
        return low_row | {
            "max_transfer_mw": 0.0,
            "binding_constraint_at_limit": str(low_row["binding_constraint"]),
            "first_violation_mw": lower_mw,
        }
    first_bad: dict[str, float | bool | str] | None = None
    for _ in range(42):
        mid = 0.5 * (low + high)
        row = evaluate_scenario(corridor, scenario_id, mid)
        if row["binding_constraint"] == "none":
            low = mid
            low_row = row
        else:
            high = mid
            first_bad = row
        if high - low <= tolerance_mw:
            break
    binding = str(first_bad["binding_constraint"]) if first_bad is not None else "none"
    return low_row | {
        "max_transfer_mw": low,
        "binding_constraint_at_limit": binding,
        "first_violation_mw": high if first_bad is not None else np.nan,
    }


def run_hosting_capacity(corridors: list[CorridorCase]) -> pd.DataFrame:
    rows = []
    for corridor in corridors:
        for scenario_id in ("C0", "C2", "C3"):
            rows.append(hosting_capacity(corridor, scenario_id))
    return pd.DataFrame(rows)


def ai_load_pu(t: np.ndarray) -> np.ndarray:
    p = np.ones_like(t, dtype=float)
    for k in np.arange(-240 + 5, 480, 7.0):
        p -= 0.28 * np.exp(-0.5 * ((t - k) / 0.45) ** 2)
    for k in np.arange(-240 + 35, 480, 70.0):
        p -= 0.23 * np.exp(-0.5 * ((t - k) / 1.2) ** 2)
    p += 0.015 * np.sin(2 * np.pi * 0.045 * t)
    p += 0.006 * np.sin(2 * np.pi * 0.33 * t + 0.4)
    return np.clip(p / np.mean(p), 0.50, 1.15)


def low_pass(x: np.ndarray, tau_s: float, dt_s: float) -> np.ndarray:
    if tau_s <= 0:
        return x.copy()
    y = np.empty_like(x)
    y[0] = x[0]
    alpha = dt_s / (tau_s + dt_s)
    for i in range(1, len(x)):
        y[i] = y[i - 1] + alpha * (x[i] - y[i - 1])
    return y


def spectral_rss(x: np.ndarray, dt_s: float, fmin: float = 0.1, fmax: float = 20.0) -> float:
    y = x - np.mean(x)
    freqs = np.fft.rfftfreq(len(y), dt_s)
    mag = np.abs(np.fft.rfft(y)) / len(y) * 2.0
    mask = (freqs >= fmin) & (freqs <= fmax)
    return float(np.sqrt(np.sum(mag[mask] ** 2)))


def lel_voltage_event_pu(t: np.ndarray) -> np.ndarray:
    """Eastern-Interconnection-inspired RMS voltage sag train for LEL screening.

    This is not a reconstruction of a specific disturbance.  It is a
    deterministic screening waveform inspired by the July 10, 2024 voltage-
    sensitive-load event: six short transmission-fault voltage depressions
    spread across about 82 seconds, with local voltage minima in the 0.25-0.40
    pu range.  The waveform is used to exercise large-electronic-load
    ride-through concepts: sag-proportional active-power reduction, 90% recovery
    within two seconds after voltage returns above 0.9 pu, filtered protection,
    and a 125% current cap during ride-through.
    """

    voltage = np.ones_like(t, dtype=float)
    for start_s, depth_pu, duration_s in EASTERN_INTERCONNECTION_2024_SAG_EVENTS:
        mask = (t >= start_s) & (t < start_s + duration_s)
        voltage[mask] = np.minimum(voltage[mask], depth_pu)
    return voltage


def apply_voltage_support(poi_voltage_pu: np.ndarray, config: ScenarioConfig) -> np.ndarray:
    """Approximate local or POI dynamic VAR support during voltage sags."""

    support = config.voltage_support_pu * np.clip(1.0 - poi_voltage_pu, 0.0, 1.0)
    return np.minimum(1.0, poi_voltage_pu + support)


def lel_grid_power_fraction(
    service_voltage_pu: np.ndarray,
    config: ScenarioConfig,
    dt_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return grid-side power and current fractions during a LEL VRT event."""

    if config.scenario_id == "C0":
        target = np.minimum(1.0, config.ride_through_current_cap_pu * np.maximum(service_voltage_pu, 0.05))
    else:
        target = np.minimum(1.0, np.maximum(0.0, service_voltage_pu / 0.80))
        target = np.minimum(target, config.ride_through_current_cap_pu * np.maximum(service_voltage_pu, 0.05))

    power = np.empty_like(target)
    power[0] = 1.0
    alpha_up = dt_s / (config.ride_through_recovery_tau_s + dt_s)
    for i in range(1, len(target)):
        if target[i] < power[i - 1]:
            power[i] = target[i]
        else:
            power[i] = power[i - 1] + alpha_up * (target[i] - power[i - 1])
    current = power / np.maximum(service_voltage_pu, 0.05)
    return power, current


def lel_recovery_time_s(
    t: np.ndarray,
    poi_voltage_pu: np.ndarray,
    grid_power_fraction: np.ndarray,
    threshold: float = 0.90,
) -> float:
    """Worst recovery time after sub-0.8 pu voltage conditions clear above 0.9 pu."""

    below = poi_voltage_pu < 0.80
    if not np.any(below):
        return 0.0
    recoveries: list[float] = []
    for idx in range(1, len(t)):
        if below[idx - 1] and poi_voltage_pu[idx] > 0.90:
            restored = np.flatnonzero(grid_power_fraction[idx:] >= threshold)
            if len(restored) == 0:
                recoveries.append(math.inf)
            else:
                recoveries.append(float(t[idx + int(restored[0])] - t[idx]))
    return max(recoveries) if recoveries else 0.0


def lel_ride_through_metrics(
    t: np.ndarray,
    nominal_load_mw: float,
    config: ScenarioConfig,
) -> dict[str, float | bool | str]:
    """Screen large-electronic-load voltage ride-through behavior."""

    dt = float(t[1] - t[0])
    poi_voltage = lel_voltage_event_pu(t)
    service_voltage = apply_voltage_support(poi_voltage, config)
    grid_fraction, current_fraction = lel_grid_power_fraction(service_voltage, config, dt)
    dc_load_fraction = np.ones_like(grid_fraction) if config.dc_buffer_for_ride_through else grid_fraction
    current_over_125_s = float(np.sum(current_fraction > 1.25 + 1e-9) * dt)
    recovery_s = lel_recovery_time_s(t, poi_voltage, grid_fraction)
    multi_sag_trip_risk = bool(config.scenario_id == "C0" and np.sum(np.diff((poi_voltage < 0.80).astype(int)) == 1) >= 3)
    pass_screen = current_over_125_s == 0.0 and recovery_s <= 2.0 and not multi_sag_trip_risk
    buffer_mwh = 0.0
    if config.dc_buffer_for_ride_through:
        buffer_mw = (dc_load_fraction - grid_fraction) * nominal_load_mw
        e_mwh = np.cumsum(buffer_mw) * dt / 3600.0
        buffer_mwh = float(e_mwh.max() - e_mwh.min())
    return {
        "lel_vrt_event": "eastern_interconnection_2024_repeated_voltage_sag_screen",
        "lel_poi_min_voltage_pu": float(np.min(poi_voltage)),
        "lel_service_min_voltage_pu": float(np.min(service_voltage)),
        "lel_grid_power_min_fraction": float(np.min(grid_fraction)),
        "lel_load_served_min_fraction": float(np.min(dc_load_fraction)),
        "lel_load_loss_max_mw": float((1.0 - np.min(dc_load_fraction)) * nominal_load_mw),
        "lel_current_max_pu": float(np.max(current_fraction)),
        "lel_current_over_125pct_s": current_over_125_s,
        "lel_recovery_to_90pct_s": recovery_s,
        "lel_multiple_sag_trip_risk": multi_sag_trip_risk,
        "lel_ride_through_pass": pass_screen,
        "lel_dc_buffer_event_mwh": buffer_mwh,
    }


def run_voltage_dynamics(corridors: list[CorridorCase], load_fraction: float = 0.72) -> pd.DataFrame:
    t = np.arange(0.0, 240.0, 0.02)
    dt = float(t[1] - t[0])
    rows = []
    for corridor in corridors:
        base_mw = min(corridor.converter_rating_mw, corridor.current_limit_kA * corridor.voltage_kv * 1.55)
        load = ai_load_pu(t) * base_mw * load_fraction
        for scenario_id, config in SCENARIOS.items():
            grid = low_pass(load, config.grid_tau_s, dt)
            ssc_mw = corridor.short_circuit_gva * 1000.0
            voltage_scale = (138.0 / corridor.voltage_kv) ** 2 * (corridor.length_km / 20.0) ** 0.5
            pcc_v_pct = 100.0 * (grid - np.mean(grid)) / ssc_mw * voltage_scale
            ramp_mw_s = float(np.percentile(np.abs(np.diff(grid) / dt), 99))
            row = {
                "dataset_id": corridor.dataset_id,
                "dataset_role": corridor.dataset_role,
                "pocket_id": corridor.pocket_id,
                "scenario_id": scenario_id,
                "architecture": config.label,
                "nominal_load_mw": float(np.mean(load)),
                "rss_0p1_20hz_mw": spectral_rss(grid, dt),
                "rss_0p1_20hz_pct_load": 100.0 * spectral_rss(grid, dt) / np.mean(load),
                "p99_ramp_mw_s": ramp_mw_s,
                "p99_ramp_pct_load_per_s": 100.0 * ramp_mw_s / np.mean(load),
                "p95_pcc_voltage_deviation_pct": float(np.quantile(np.abs(pcc_v_pct), 0.95)),
                "voltage_support_location": config.voltage_support_location,
                "voltage_support_role": config.voltage_support_role,
                "var_coordination_risk": config.var_coordination_risk,
            }
            row.update(lel_ride_through_metrics(t, float(np.mean(load)), config))
            if scenario_id == "C3":
                buffer = load - grid
                e_mwh = np.cumsum(buffer) * dt / 3600.0
                row["buffer_energy_window_mwh"] = float(e_mwh.max() - e_mwh.min())
            else:
                row["buffer_energy_window_mwh"] = 0.0
            rows.append(row)
    return pd.DataFrame(rows)


def run_harmonic_screen(corridors: list[CorridorCase], seed: int = 20260528, trials: int = 600) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for corridor in corridors:
        v_phase = corridor.voltage_kv * 1000.0 / math.sqrt(3.0)
        z1 = corridor.voltage_kv**2 / (corridor.short_circuit_gva * 1000.0)
        for scenario_id, config in SCENARIOS.items():
            thd_trials = []
            for _ in range(trials):
                sc_mult = rng.triangular(0.65, 1.0, 1.45)
                resonance_center = rng.normal(11.0, 1.2)
                thd_sq = 0.0
                for h, frac in zip(HARMONICS, BASE_HARMONIC_FRAC):
                    resonance = 1.0 + 2.5 * np.exp(-0.5 * ((h - resonance_center) / 1.7) ** 2)
                    z_h = z1 * h * resonance / sc_mult
                    source_sum = _harmonic_source_sum(rng, config.harmonic_source_count)
                    i_base = corridor.converter_rating_mw * 1e6 / (math.sqrt(3.0) * corridor.voltage_kv * 1000.0)
                    vh_pct = (
                        100.0
                        * abs(i_base * frac * config.harmonic_scale * source_sum * z_h)
                        / v_phase
                        * HARMONIC_SCREENING_TRANSFER
                    )
                    thd_sq += vh_pct**2
                thd_trials.append(math.sqrt(thd_sq))
            rows.append(
                {
                    "dataset_id": corridor.dataset_id,
                    "dataset_role": corridor.dataset_role,
                    "pocket_id": corridor.pocket_id,
                    "scenario_id": scenario_id,
                    "architecture": config.label,
                    "thdv_p50_pct": float(np.quantile(thd_trials, 0.50)),
                    "thdv_p95_pct": float(np.quantile(thd_trials, 0.95)),
                    "thdv_max_pct": float(np.max(thd_trials)),
                    "source_count": config.harmonic_source_count,
                }
            )
    return pd.DataFrame(rows)


def _harmonic_source_sum(rng: np.random.Generator, n_sources: int) -> float:
    if n_sources <= 1:
        return 1.0
    phases = rng.uniform(0.0, 2.0 * np.pi, size=n_sources)
    return abs(np.sum(np.exp(1j * phases))) / math.sqrt(n_sources)


def summarize_by_architecture(hosting: pd.DataFrame, harmonics: pd.DataFrame, voltage: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dataset_id in sorted(hosting["dataset_id"].unique()):
        h = hosting[hosting["dataset_id"] == dataset_id]
        hm = harmonics[harmonics["dataset_id"] == dataset_id]
        v = voltage[voltage["dataset_id"] == dataset_id]
        for scenario_id, label in ARCHITECTURES.items():
            hs = h[h["scenario_id"] == scenario_id]
            hms = hm[hm["scenario_id"] == scenario_id]
            vs = v[v["scenario_id"] == scenario_id]
            rows.append(
                {
                    "dataset_id": dataset_id,
                    "scenario_id": scenario_id,
                    "architecture": label,
                    "median_max_transfer_mw": hs["max_transfer_mw"].median(),
                    "p10_max_transfer_mw": hs["max_transfer_mw"].quantile(0.10),
                    "p90_max_transfer_mw": hs["max_transfer_mw"].quantile(0.90),
                    "median_efficiency_to_load_boundary": hs["efficiency_to_load_boundary"].median(),
                    "median_efficiency_to_800v": hs["efficiency_to_800v"].median(),
                    "median_loss_mw_at_limit": hs["loss_mw"].median(),
                    "median_thdv_p95_pct": hms["thdv_p95_pct"].median(),
                    "median_p95_voltage_deviation_pct": vs["p95_pcc_voltage_deviation_pct"].median(),
                    "median_p99_ramp_pct_load_per_s": vs["p99_ramp_pct_load_per_s"].median(),
                    "lel_vrt_pass_fraction": vs["lel_ride_through_pass"].mean(),
                    "median_lel_current_max_pu": vs["lel_current_max_pu"].median(),
                    "median_lel_recovery_to_90pct_s": vs["lel_recovery_to_90pct_s"].median(),
                    "median_lel_load_loss_max_mw": vs["lel_load_loss_max_mw"].median(),
                    "median_lel_dc_buffer_event_mwh": vs["lel_dc_buffer_event_mwh"].median(),
                }
            )
    return pd.DataFrame(rows)
