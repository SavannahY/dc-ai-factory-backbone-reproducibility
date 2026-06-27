"""Screening models for AC-to-DC corridor transfer capability.

These models are intentionally compact.  They are meant to separate thermal
ampacity from usable transfer capability before moving to a production power
flow, EMT or planning-tool study.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class TransferCapacityAssumptions:
    """Shared assumptions for corridor transfer-capacity screens."""

    length_km: float = 20.0
    vac_ll_kv: float = 138.0
    vdc_pp_kv: float = 276.0
    high_voltage_envelope_factor: float = 1.5
    dc_current_retention_factor: float = 1.0
    converter_cap_multiplier: float = 2.0
    r_ohm_km: float = 0.01
    x_ohm_km: float = 0.10
    pf: float = 0.98
    ac_downstream_efficiency: float = 0.991 * 0.982
    dc_stage1_efficiency: float = 0.994
    dc_stage2_efficiency: float = 0.992
    current_limit_kA: float = 5.5
    voltage_min_pu: float = 0.95
    source_q_limit_mvar: float = 400.0
    s_base_mva: float = 1000.0
    source_voltage_pu: float = 1.0
    stability_pmax_pre_mw: float = 2500.0
    stability_post_fault_factor: float = 0.75
    inertia_H_s: float = 4.0
    min_critical_clearing_s: float = 0.10
    system_frequency_hz: float = 60.0

    @property
    def dc_downstream_efficiency(self) -> float:
        return self.dc_stage1_efficiency * self.dc_stage2_efficiency

    @property
    def z_base_ohm(self) -> float:
        return self.vac_ll_kv**2 / self.s_base_mva

    @property
    def line_z_pu(self) -> complex:
        r = self.r_ohm_km * self.length_km / self.z_base_ohm
        x = self.x_ohm_km * self.length_km / self.z_base_ohm
        return complex(r, x)

    @property
    def ac_current_base_kA(self) -> float:
        return self.s_base_mva / (math.sqrt(3.0) * self.vac_ll_kv)

    @property
    def ac_line_to_ground_peak_kv(self) -> float:
        return math.sqrt(2.0 / 3.0) * self.vac_ll_kv


def ac_transfer_capacity_mw(
    vac_ll_kv: float,
    current_limit_kA: float,
    pf: float,
) -> float:
    """AC corridor active transfer from voltage, current and power factor."""

    return math.sqrt(3.0) * vac_ll_kv * current_limit_kA * pf


def dc_transfer_capacity_mw(
    v_pole_kv: float,
    current_limit_kA: float,
    current_retention: float = 1.0,
    converter_cap_mw: float = math.inf,
) -> float:
    """Bipolar DC corridor transfer with optional current retention and converter cap."""

    thermal_mw = 2.0 * v_pole_kv * current_limit_kA * current_retention
    return min(thermal_mw, converter_cap_mw)


def corridor_capacity_envelope(
    assumptions: TransferCapacityAssumptions = TransferCapacityAssumptions(),
    *,
    voltage_envelope_factor: float | None = None,
    v_pole_kv: float | None = None,
    current_retention: float | None = None,
    converter_cap_multiplier: float | None = None,
) -> dict[str, float | str]:
    """Compare AC transfer capacity with an AC-to-DC conversion envelope."""

    a = assumptions
    alpha = (
        a.high_voltage_envelope_factor
        if voltage_envelope_factor is None
        else voltage_envelope_factor
    )
    pole_kv = alpha * a.ac_line_to_ground_peak_kv if v_pole_kv is None else v_pole_kv
    alpha = pole_kv / a.ac_line_to_ground_peak_kv
    retention = a.dc_current_retention_factor if current_retention is None else current_retention
    cap_multiplier = a.converter_cap_multiplier if converter_cap_multiplier is None else converter_cap_multiplier
    ac_mw = ac_transfer_capacity_mw(a.vac_ll_kv, a.current_limit_kA, a.pf)
    dc_thermal_mw = 2.0 * pole_kv * a.current_limit_kA * retention
    converter_cap_mw = cap_multiplier * ac_mw
    dc_mw = min(dc_thermal_mw, converter_cap_mw)
    return {
        "ac_transfer_capacity_mw": ac_mw,
        "dc_transfer_capacity_mw": dc_mw,
        "dc_thermal_capacity_mw": dc_thermal_mw,
        "dc_pole_kv": pole_kv,
        "voltage_envelope_factor": alpha,
        "current_retention_factor": retention,
        "converter_cap_mw": converter_cap_mw,
        "capacity_multiplier": dc_mw / ac_mw,
        "capacity_increase_pct": 100.0 * (dc_mw / ac_mw - 1.0),
        "binding_constraint": (
            "converter_rating_cap" if converter_cap_mw < dc_thermal_mw else "thermal_current_limit"
        ),
    }


def thermal_capacity_envelope(
    assumptions: TransferCapacityAssumptions = TransferCapacityAssumptions(),
    current_limit_kA: float | None = None,
) -> dict[str, float]:
    """Compare same-current AC and DC transfer under the same corridor ampacity.

    The returned useful MW values are at the paper's 800 VDC boundary.  They
    therefore include downstream AC/DC or DC/DC conversion assumptions.
    """

    a = assumptions
    current = a.current_limit_kA if current_limit_kA is None else current_limit_kA
    ac_corridor_mw = math.sqrt(3.0) * a.vac_ll_kv * current * a.pf
    dc_corridor_mw = a.vdc_pp_kv * current
    ac_useful_mw = ac_corridor_mw * a.ac_downstream_efficiency
    dc_useful_mw = dc_corridor_mw * a.dc_downstream_efficiency
    return {
        "current_limit_kA": current,
        "ac_corridor_mw": ac_corridor_mw,
        "dc_corridor_mw": dc_corridor_mw,
        "ac_useful_mw": ac_useful_mw,
        "dc_useful_mw": dc_useful_mw,
        "dc_to_ac_corridor_ratio": dc_corridor_mw / ac_corridor_mw,
        "dc_to_ac_useful_ratio": dc_useful_mw / ac_useful_mw,
    }


def _receiving_power_pu(useful_mw: float, assumptions: TransferCapacityAssumptions) -> tuple[float, float]:
    p_corridor_mw = useful_mw / assumptions.ac_downstream_efficiency
    p_pu = p_corridor_mw / assumptions.s_base_mva
    q_pu = p_pu * math.tan(math.acos(assumptions.pf))
    return p_pu, q_pu


def solve_two_bus_ac(
    useful_mw: float,
    assumptions: TransferCapacityAssumptions = TransferCapacityAssumptions(),
    initial_voltage: complex | None = None,
    max_iter: int = 40,
    tol: float = 1e-9,
) -> dict[str, float | bool | str]:
    """Solve a two-bus AC load-flow screen for a fixed delivered useful MW.

    The source bus is a slack bus at 1.0 pu.  The receiving bus load is the
    useful 800 VDC power divided by the downstream AC conversion efficiency,
    with the paper's power-factor assumption.  The line is an effective
    corridor impedance, not a detailed tower/conductor model.
    """

    a = assumptions
    z = a.line_z_pu
    vs = complex(a.source_voltage_pu, 0.0)
    p_pu, q_pu = _receiving_power_pu(useful_mw, a)
    x = np.array([1.0, 0.0], dtype=float)
    if initial_voltage is not None:
        x[:] = [initial_voltage.real, initial_voltage.imag]

    def mismatch(v: np.ndarray) -> np.ndarray:
        vr = complex(v[0], v[1])
        current = (vs - vr) / z
        s_recv = vr * np.conjugate(current)
        return np.array([s_recv.real - p_pu, s_recv.imag - q_pu])

    converged = False
    for _ in range(max_iter):
        f = mismatch(x)
        if float(np.linalg.norm(f)) < tol:
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
            new_norm = float(np.linalg.norm(mismatch(candidate)))
            if new_norm < old_norm:
                x = candidate
                break
            alpha *= 0.5
        else:
            break

    vr = complex(x[0], x[1])
    current_pu = abs((vs - vr) / z)
    current_ka = current_pu * a.ac_current_base_kA
    s_send_mva = vs * np.conjugate((vs - vr) / z) * a.s_base_mva
    p_corridor_mw = p_pu * a.s_base_mva
    q_corridor_mvar = q_pu * a.s_base_mva
    q_line_mvar = float(s_send_mva.imag - q_corridor_mvar)

    voltage_ok = abs(vr) >= a.voltage_min_pu
    thermal_ok = current_ka <= a.current_limit_kA
    q_ok = float(s_send_mva.imag) <= a.source_q_limit_mvar
    binding = "none"
    if not converged:
        binding = "power_flow_nonconvergence"
    elif not voltage_ok:
        binding = "voltage_limit"
    elif not q_ok:
        binding = "reactive_power_limit"
    elif not thermal_ok:
        binding = "thermal_current_limit"

    return {
        "useful_mw": useful_mw,
        "ac_corridor_mw": p_corridor_mw,
        "ac_receiving_q_mvar": q_corridor_mvar,
        "receiving_voltage_pu": abs(vr),
        "receiving_angle_deg": math.degrees(math.atan2(vr.imag, vr.real)),
        "line_current_kA": current_ka,
        "source_q_mvar": float(s_send_mva.imag),
        "line_reactive_burden_mvar": q_line_mvar,
        "converged": converged,
        "voltage_ok": voltage_ok,
        "thermal_ok": thermal_ok,
        "source_q_ok": q_ok,
        "binding_constraint": binding,
        "receiving_voltage_real_pu": vr.real,
        "receiving_voltage_imag_pu": vr.imag,
    }


def scan_ac_loadability(
    assumptions: TransferCapacityAssumptions = TransferCapacityAssumptions(),
    max_useful_mw: float = 2000.0,
    step_mw: float = 5.0,
) -> list[dict[str, float | bool | str]]:
    """Continuation-style AC transfer scan until the requested upper bound."""

    rows: list[dict[str, float | bool | str]] = []
    initial_voltage: complex | None = None
    useful_mw = step_mw
    while useful_mw <= max_useful_mw + 1e-9:
        row = solve_two_bus_ac(useful_mw, assumptions, initial_voltage=initial_voltage)
        rows.append(row)
        if row["converged"]:
            initial_voltage = complex(
                float(row["receiving_voltage_real_pu"]),
                float(row["receiving_voltage_imag_pu"]),
            )
        else:
            break
        useful_mw += step_mw
    return rows


def first_binding(rows: list[dict[str, float | bool | str]]) -> dict[str, float | str | None]:
    """Return the first violated constraint and the last feasible transfer."""

    last_ok = 0.0
    for row in rows:
        binding = str(row["binding_constraint"])
        if binding == "none":
            last_ok = float(row["useful_mw"])
            continue
        return {
            "last_feasible_mw": last_ok,
            "first_violation_mw": float(row["useful_mw"]),
            "binding_constraint": binding,
        }
    return {
        "last_feasible_mw": last_ok,
        "first_violation_mw": None,
        "binding_constraint": "none",
    }


def smib_critical_clearing_time_s(
    transfer_mw: float,
    assumptions: TransferCapacityAssumptions = TransferCapacityAssumptions(),
) -> float:
    """Classical equal-area critical-clearing-time screen.

    The fault-on transfer is assumed to be zero and the post-fault transfer
    curve is reduced by ``stability_post_fault_factor``.  This is a planning
    screen only; it is not a validated generator or converter dynamic model.
    """

    a = assumptions
    pm = transfer_mw / a.s_base_mva
    pmax_pre = a.stability_pmax_pre_mw / a.s_base_mva
    pmax_post = pmax_pre * a.stability_post_fault_factor
    if pm <= 0.0:
        return math.inf
    if pm >= pmax_post:
        return 0.0

    delta_0 = math.asin(min(0.999999, pm / pmax_pre))
    delta_u = math.pi - math.asin(min(0.999999, pm / pmax_post))
    cos_delta_c = pm * (delta_u - delta_0) / pmax_post + math.cos(delta_u)
    if cos_delta_c >= 1.0:
        return 0.0
    cos_delta_c = max(-1.0, min(1.0, cos_delta_c))
    delta_c = math.acos(cos_delta_c)
    if delta_c <= delta_0:
        return 0.0

    omega_s = 2.0 * math.pi * a.system_frequency_hz
    return math.sqrt(4.0 * a.inertia_H_s * (delta_c - delta_0) / (omega_s * pm))


def scan_transient_stability(
    assumptions: TransferCapacityAssumptions = TransferCapacityAssumptions(),
    max_useful_mw: float = 2200.0,
    step_mw: float = 5.0,
) -> list[dict[str, float | bool | str]]:
    """Scan useful transfer against a classical transient-stability screen."""

    rows: list[dict[str, float | bool | str]] = []
    useful_mw = step_mw
    while useful_mw <= max_useful_mw + 1e-9:
        corridor_mw = useful_mw / assumptions.ac_downstream_efficiency
        cct = smib_critical_clearing_time_s(corridor_mw, assumptions)
        ac_current = corridor_mw / (math.sqrt(3.0) * assumptions.vac_ll_kv * assumptions.pf)
        thermal_ok = ac_current <= assumptions.current_limit_kA
        stability_ok = cct >= assumptions.min_critical_clearing_s
        binding = "none"
        if not stability_ok:
            binding = "transient_stability_limit"
        elif not thermal_ok:
            binding = "thermal_current_limit"
        rows.append(
            {
                "useful_mw": useful_mw,
                "ac_corridor_mw": corridor_mw,
                "line_current_kA": ac_current,
                "critical_clearing_time_s": cct,
                "stability_ok": stability_ok,
                "thermal_ok": thermal_ok,
                "binding_constraint": binding,
            }
        )
        useful_mw += step_mw
    return rows
