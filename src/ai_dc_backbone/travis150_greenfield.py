"""Greenfield data-center configurations for the Travis 150 electric test case."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import math
import re
import shlex

import numpy as np
import pandas as pd

from ai_dc_backbone.texas_td_scenarios import (
    BASE_HARMONIC_FRAC,
    EASTERN_INTERCONNECTION_2024_SAG_EVENTS,
    HARMONICS,
    HARMONIC_SCREENING_TRANSFER,
    CorridorCase,
    ai_load_pu,
    default_corridors,
    lel_recovery_time_s,
    lel_voltage_event_pu,
    load_matpower_corridors,
    low_pass,
    solve_ac_corridor,
    solve_dc_corridor,
    spectral_rss,
)


ARCHITECTURES = {
    "C1": "Greenfield traditional AC data-center supply",
    "C2": "Greenfield AC corridor with data-center SST",
    "C3": "Greenfield bipolar DC data-center corridor",
}

DEFAULT_FLAGSHIP_POCKET = "ATX-230-138-04"
DEFAULT_LOADS_MW = (250.0, 500.0, 1000.0)
DEFAULT_OUTPUT_STUDY_LOAD_MW = 1000.0
DEFAULT_HARMONIC_SEED = 20260620


@dataclass(frozen=True)
class GreenfieldScenarioConfig:
    """Scenario assumptions for new data-center supply configurations."""

    scenario_id: str
    label: str
    corridor_build: str
    ac_pf: float
    downstream_efficiency: float
    terminal_efficiency: float
    dc_stage_efficiency: float
    local_q_support_mvar: float
    grid_tau_s: float
    harmonic_scale: float
    harmonic_source_count: int
    harmonic_ownership: str
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
    "C1": GreenfieldScenarioConfig(
        scenario_id="C1",
        label=ARCHITECTURES["C1"],
        corridor_build="new_ac_data_center_corridor",
        ac_pf=0.98,
        downstream_efficiency=0.991 * 0.982,
        terminal_efficiency=1.0,
        dc_stage_efficiency=1.0,
        local_q_support_mvar=0.0,
        grid_tau_s=0.0,
        harmonic_scale=1.0,
        harmonic_source_count=4,
        harmonic_ownership="distributed AC-facing rectifier and UPS harmonic sources at the data-center campus",
        load_interface="480 V AC facility distribution",
        load_boundary_voltage_v=480.0,
        voltage_support_pu=0.0,
        ride_through_current_cap_pu=1.70,
        ride_through_recovery_tau_s=5.0,
        dc_buffer_for_ride_through=False,
        voltage_support_location="none",
        voltage_support_role="new traditional AC supply with voltage-sensitive data-center load",
        var_coordination_risk="not applicable",
    ),
    "C2": GreenfieldScenarioConfig(
        scenario_id="C2",
        label=ARCHITECTURES["C2"],
        corridor_build="new_ac_corridor_with_local_sst",
        ac_pf=0.995,
        downstream_efficiency=0.985,
        terminal_efficiency=1.0,
        dc_stage_efficiency=1.0,
        local_q_support_mvar=160.0,
        grid_tau_s=1.1,
        harmonic_scale=0.32,
        harmonic_source_count=3,
        harmonic_ownership="distributed SST front ends with local filtering at the data-center campus",
        load_interface="800 V DC data-center interface through SST",
        load_boundary_voltage_v=800.0,
        voltage_support_pu=0.10,
        ride_through_current_cap_pu=1.25,
        ride_through_recovery_tau_s=1.0,
        dc_buffer_for_ride_through=False,
        voltage_support_location="34.5 kV AC side near the data-center SST",
        voltage_support_role="local SST dynamic VAR support and ride-through control",
        var_coordination_risk=(
            "local SST Volt-VAR controls can fight utility LTCs, regulators, capacitor banks, "
            "nearby smart inverters or centralized STATCOM/SVC controls without supervisory coordination"
        ),
    ),
    "C3": GreenfieldScenarioConfig(
        scenario_id="C3",
        label=ARCHITECTURES["C3"],
        corridor_build="new_dedicated_bipolar_dc_data_center_corridor",
        ac_pf=1.0,
        downstream_efficiency=1.0,
        terminal_efficiency=0.994,
        dc_stage_efficiency=0.994 * 0.992,
        local_q_support_mvar=260.0,
        grid_tau_s=16.0,
        harmonic_scale=0.055,
        harmonic_source_count=1,
        harmonic_ownership="single grid-facing AC/DC terminal owns AC-side harmonic compliance",
        load_interface="800 V DC data-center interface through DC/DC conversion",
        load_boundary_voltage_v=800.0,
        voltage_support_pu=0.16,
        ride_through_current_cap_pu=1.25,
        ride_through_recovery_tau_s=0.6,
        dc_buffer_for_ride_through=True,
        voltage_support_location="transmission interconnection AC side at the grid-facing AC/DC terminal",
        voltage_support_role="centralized AC/DC-terminal voltage support plus DC corridor buffering",
        var_coordination_risk=(
            "centralized support reduces campus-level control fighting but requires utility-side "
            "ownership, protection coordination and adequate terminal VAR rating"
        ),
    ),
}


def greenfield_corridor(
    corridor: CorridorCase,
    config: GreenfieldScenarioConfig | None = None,
) -> CorridorCase:
    """Return the same source-sink span with no native load assigned to the new line."""

    if config is not None and config.scenario_id == "C3":
        dc_current_envelope_mw = corridor.effective_vdc_pp_kv * corridor.current_limit_kA * 0.98
        return replace(
            corridor,
            existing_load_mw=0.0,
            converter_rating_mw=max(corridor.converter_rating_mw, dc_current_envelope_mw),
        )
    return replace(corridor, existing_load_mw=0.0)


def fallback_travis_corridors(flagship_pocket: str = DEFAULT_FLAGSHIP_POCKET) -> list[CorridorCase]:
    """Return fallback Travis 150 candidate spans from the archived validation catalog."""

    corridors = [corridor for corridor in default_corridors() if corridor.dataset_id == "B"]
    matches = [corridor for corridor in corridors if corridor.pocket_id == flagship_pocket]
    if matches:
        return matches
    if not corridors:
        raise ValueError("No Austin/Travis fallback corridors are available")
    return sorted(corridors, key=lambda c: (c.converter_rating_mw, c.short_circuit_gva), reverse=True)[:1]


def load_powerworld_aux_corridors(path: str | Path, max_corridors: int = 12) -> list[CorridorCase]:
    """Build greenfield data-center corridor candidates from a PowerWorld AUX case.

    The Travis 150 public electric case is distributed as PowerWorld data.  For
    this greenfield study, the AUX branch data is used for placement, voltage
    class, impedance and source strength; the modeled corridor is still a new
    purpose-built data-center line rather than an existing-line conversion.
    """

    blocks = _parse_powerworld_aux(Path(path))
    buses = _require_aux_rows(blocks, "Bus")
    branches = _require_aux_rows(blocks, "Branch")
    bus_by_num = {_to_int(row["BusNum"]): row for row in buses if _has_value(row.get("BusNum"))}
    coords_by_sub = _substation_coordinates(blocks.get("Substation", []))
    load_mw = _aux_load_mw_by_bus(blocks.get("Load", []))
    gen_mw = _aux_gen_mw_by_bus(blocks.get("Gen", []), "GenMWSetPoint")
    gen_mvar_cap = _aux_gen_mw_by_bus(blocks.get("Gen", []), "GenMVRMax")

    candidates = []
    for row in branches:
        if row.get("BranchDeviceType", "").strip() != "Line":
            continue
        if not _aux_is_closed(row.get("LineStatus", "")):
            continue
        from_bus_num = _to_int(row.get("BusNum"))
        to_bus_num = _to_int(row.get("BusNum:1"))
        if from_bus_num not in bus_by_num or to_bus_num not in bus_by_num:
            continue

        from_bus = bus_by_num[from_bus_num]
        to_bus = bus_by_num[to_bus_num]
        from_kv = _to_float(from_bus.get("BusNomVolt"))
        to_kv = _to_float(to_bus.get("BusNomVolt"))
        if not math.isfinite(from_kv) or not math.isfinite(to_kv):
            continue
        voltage_kv = min(from_kv, to_kv)
        if voltage_kv < 100.0:
            continue
        if abs(from_kv - to_kv) / max(from_kv, to_kv, 1.0) > 0.10:
            continue

        source_num, sink_num = _orient_source_sink(from_bus_num, to_bus_num, bus_by_num, gen_mw, load_mw)
        source_bus = bus_by_num[source_num]
        sink_bus = bus_by_num[sink_num]

        length_km = _aux_branch_length_km(row, from_bus, to_bus, coords_by_sub)
        line_r_pu = abs(_to_float(row.get("LineR"), 0.0))
        line_x_pu = abs(_to_float(row.get("LineX"), 0.0))
        z_base_ohm = voltage_kv**2 / 100.0
        r_ohm_km = _bounded_impedance(line_r_pu * z_base_ohm / length_km, 0.004, 0.080, 0.026)
        x_ohm_km = _bounded_impedance(line_x_pu * z_base_ohm / length_km, 0.030, 0.420, 0.155)

        aux_rate_mva = max(_to_float(row.get("LineAMVA"), 0.0), 0.0)
        aux_current_kA = aux_rate_mva / (math.sqrt(3.0) * voltage_kv) if aux_rate_mva > 0 else 0.0
        current_limit_kA = max(aux_current_kA, _greenfield_current_floor_kA(voltage_kv))
        planned_mva = math.sqrt(3.0) * voltage_kv * current_limit_kA
        source_gen_mw = max(gen_mw.get(source_num, 0.0), 0.0)
        sink_gen_mw = max(gen_mw.get(sink_num, 0.0), 0.0)
        sink_load_mw = max(load_mw.get(sink_num, 0.0), 0.0)
        short_circuit_gva = min(16.0, max(4.0, 3.5 + source_gen_mw / 180.0 + planned_mva / 250.0))
        source_q_limit_mvar = min(850.0, max(260.0, 45.0 * short_circuit_gva + 0.20 * gen_mvar_cap.get(source_num, 0.0)))
        converter_rating_mw = max(1000.0, 0.95 * planned_mva, 0.95 * aux_rate_mva)

        data_center_bonus = 40.0 if "Travis_DS" in str(sink_bus.get("BusName", "")) else 0.0
        score = planned_mva + 0.30 * source_gen_mw + 2.0 * sink_load_mw - 0.55 * sink_gen_mw - 1.1 * length_km
        score += data_center_bonus
        candidates.append(
            (
                score,
                CorridorCase(
                    dataset_id="B",
                    dataset_role="Travis 150 synthetic electric case (PowerWorld AUX electric side; gas ignored)",
                    pocket_id="",
                    source_bus=_aux_bus_label(source_num, source_bus),
                    load_bus=_aux_bus_label(sink_num, sink_bus),
                    voltage_kv=float(voltage_kv),
                    length_km=float(length_km),
                    r_ohm_km=float(r_ohm_km),
                    x_ohm_km=float(x_ohm_km),
                    current_limit_kA=float(current_limit_kA),
                    short_circuit_gva=float(short_circuit_gva),
                    source_q_limit_mvar=float(source_q_limit_mvar),
                    converter_rating_mw=float(converter_rating_mw),
                    existing_load_mw=float(sink_load_mw),
                    vdc_pp_kv=2.0 * float(voltage_kv),
                ),
            )
        )

    if not candidates:
        raise ValueError(f"No closed high-voltage Travis 150 line candidates were found in {path}")

    ranked = sorted(candidates, key=lambda item: item[0], reverse=True)[:max_corridors]
    corridors = []
    seen: set[tuple[str, str, float]] = set()
    for rank, (_score, corridor) in enumerate(ranked, start=1):
        key = (corridor.source_bus, corridor.load_bus, round(corridor.length_km, 3))
        if key in seen:
            continue
        seen.add(key)
        corridors.append(replace(corridor, pocket_id=f"TRAVIS150-AUX-{rank:03d}"))
    if not corridors:
        raise ValueError(f"No unique Travis 150 high-voltage line candidates were found in {path}")
    return corridors[:max_corridors]


def load_travis_greenfield_corridors(
    travis_case: str | Path | None = None,
    flagship_pocket: str = DEFAULT_FLAGSHIP_POCKET,
    max_corridors: int = 12,
) -> tuple[list[CorridorCase], str]:
    """Load Travis 150 electric corridors from a user-supplied case or fallback catalog.

    The importer supports a CSV corridor catalog with ``source_bus`` and
    ``load_bus`` columns, a MATPOWER-style ``.m`` case, or the Travis 150
    PowerWorld ``.aux`` electric case.  The repository keeps a deterministic
    fallback for tests and examples when a downloaded case is not supplied.
    """

    if travis_case is None:
        return fallback_travis_corridors(flagship_pocket), "fallback_archived_travis150_corridor_catalog"

    path = Path(travis_case)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        required = {
            "source_bus",
            "load_bus",
            "voltage_kv",
            "length_km",
            "r_ohm_km",
            "x_ohm_km",
            "current_limit_kA",
            "short_circuit_gva",
            "source_q_limit_mvar",
            "converter_rating_mw",
        }
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Travis corridor CSV is missing columns: {sorted(missing)}")
        corridors = []
        for idx, row in df.head(max_corridors).iterrows():
            corridors.append(
                CorridorCase(
                    dataset_id=str(row.get("dataset_id", "B")),
                    dataset_role=str(row.get("dataset_role", "Travis 150 synthetic electric case")),
                    pocket_id=str(row.get("pocket_id", f"TRAVIS150-{idx + 1:03d}")),
                    source_bus=str(row["source_bus"]),
                    load_bus=str(row["load_bus"]),
                    voltage_kv=float(row["voltage_kv"]),
                    length_km=float(row["length_km"]),
                    r_ohm_km=float(row["r_ohm_km"]),
                    x_ohm_km=float(row["x_ohm_km"]),
                    current_limit_kA=float(row["current_limit_kA"]),
                    short_circuit_gva=float(row["short_circuit_gva"]),
                    source_q_limit_mvar=float(row["source_q_limit_mvar"]),
                    converter_rating_mw=float(row["converter_rating_mw"]),
                    existing_load_mw=float(row.get("existing_load_mw", 0.0)),
                    vdc_pp_kv=float(row["vdc_pp_kv"]) if "vdc_pp_kv" in row and not pd.isna(row["vdc_pp_kv"]) else None,
                )
            )
        return _select_flagship(corridors), f"csv:{path}"

    if path.suffix.lower() == ".m":
        corridors = load_matpower_corridors(
            path,
            dataset_id="B",
            dataset_role="Travis 150 synthetic electric case",
            max_corridors=max_corridors,
        )
        return _select_flagship(corridors), f"matpower:{path}"

    if path.suffix.lower() == ".aux":
        corridors = load_powerworld_aux_corridors(path, max_corridors=max_corridors)
        return _select_flagship(corridors), f"powerworld_aux:{path}"

    raise ValueError(f"Unsupported Travis electric case format: {path.suffix}")


def _select_flagship(corridors: list[CorridorCase]) -> list[CorridorCase]:
    if not corridors:
        raise ValueError("No Travis 150 electric corridors were found")
    return [sorted(corridors, key=lambda c: (c.converter_rating_mw, c.short_circuit_gva, -c.length_km), reverse=True)[0]]


def _parse_powerworld_aux(path: Path) -> dict[str, list[dict[str, str]]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks: dict[str, list[dict[str, str]]] = {}
    pattern = re.compile(r"DATA\s*\(([^,]+),\s*\[(.*?)\]\)\s*\{(.*?)\r?\n\}", re.S)
    for match in pattern.finditer(text):
        block_name = match.group(1).strip()
        columns = [column.strip() for column in re.sub(r"\s+", "", match.group(2)).split(",") if column.strip()]
        rows = blocks.setdefault(block_name, [])
        for line in match.group(3).splitlines():
            if not line.strip():
                continue
            values = _split_aux_row(line)
            if len(values) == len(columns):
                rows.append(dict(zip(columns, values)))
    return blocks


def _split_aux_row(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [value.strip() for value in lexer]


def _require_aux_rows(blocks: dict[str, list[dict[str, str]]], block_name: str) -> list[dict[str, str]]:
    rows = blocks.get(block_name, [])
    if not rows:
        raise ValueError(f"PowerWorld AUX file does not contain parseable {block_name} rows")
    return rows


def _aux_is_closed(value: str) -> bool:
    return str(value).strip().lower() == "closed"


def _has_value(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def _to_float(value: str | None, default: float = math.nan) -> float:
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(str(value).strip())
    except ValueError:
        return default


def _to_int(value: str | None, default: int = -1) -> int:
    numeric = _to_float(value, math.nan)
    return int(numeric) if math.isfinite(numeric) else default


def _substation_coordinates(rows: list[dict[str, str]]) -> dict[int, tuple[float, float]]:
    coords: dict[int, tuple[float, float]] = {}
    for row in rows:
        sub_num = _to_int(row.get("SubNum"))
        lat = _to_float(row.get("Latitude"))
        lon = _to_float(row.get("Longitude"))
        if sub_num >= 0 and math.isfinite(lat) and math.isfinite(lon):
            coords[sub_num] = (lat, lon)
    return coords


def _aux_load_mw_by_bus(rows: list[dict[str, str]]) -> dict[int, float]:
    loads: dict[int, float] = {}
    for row in rows:
        if not _aux_is_closed(row.get("LoadStatus", "")):
            continue
        bus_num = _to_int(row.get("BusNum"))
        if bus_num < 0:
            continue
        mw = _to_float(row.get("LoadSMW"), 0.0) + _to_float(row.get("LoadIMW"), 0.0) + _to_float(row.get("LoadZMW"), 0.0)
        loads[bus_num] = loads.get(bus_num, 0.0) + max(0.0, mw)
    return loads


def _aux_gen_mw_by_bus(rows: list[dict[str, str]], field: str) -> dict[int, float]:
    values: dict[int, float] = {}
    for row in rows:
        if not _aux_is_closed(row.get("GenStatus", "")):
            continue
        bus_num = _to_int(row.get("BusNum"))
        if bus_num < 0:
            continue
        values[bus_num] = values.get(bus_num, 0.0) + max(0.0, _to_float(row.get(field), 0.0))
    return values


def _orient_source_sink(
    from_bus_num: int,
    to_bus_num: int,
    bus_by_num: dict[int, dict[str, str]],
    gen_mw: dict[int, float],
    load_mw: dict[int, float],
) -> tuple[int, int]:
    def score(bus_num: int) -> float:
        kv = _to_float(bus_by_num[bus_num].get("BusNomVolt"), 0.0)
        return 2.0 * kv + gen_mw.get(bus_num, 0.0) - 0.35 * load_mw.get(bus_num, 0.0)

    if score(to_bus_num) > score(from_bus_num):
        return to_bus_num, from_bus_num
    return from_bus_num, to_bus_num


def _aux_branch_length_km(
    row: dict[str, str],
    from_bus: dict[str, str],
    to_bus: dict[str, str],
    coords_by_sub: dict[int, tuple[float, float]],
) -> float:
    powerworld_length = _to_float(row.get("LineLength"), 0.0)
    if powerworld_length > 0:
        return max(0.5, powerworld_length * 1.609344)

    from_coord = _aux_bus_coordinate(from_bus, coords_by_sub)
    to_coord = _aux_bus_coordinate(to_bus, coords_by_sub)
    if from_coord and to_coord:
        return max(0.5, _haversine_km(from_coord[0], from_coord[1], to_coord[0], to_coord[1]))
    return 2.0


def _aux_bus_coordinate(row: dict[str, str], coords_by_sub: dict[int, tuple[float, float]]) -> tuple[float, float] | None:
    lat = _to_float(row.get("Latitude"))
    lon = _to_float(row.get("Longitude"))
    if math.isfinite(lat) and math.isfinite(lon):
        return lat, lon
    return coords_by_sub.get(_to_int(row.get("SubNum")))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius_km * math.asin(math.sqrt(min(1.0, a)))


def _bounded_impedance(value: float, low: float, high: float, default: float) -> float:
    if not math.isfinite(value) or value <= 0.0:
        return default
    return min(high, max(low, value))


def _greenfield_current_floor_kA(voltage_kv: float) -> float:
    if voltage_kv >= 200.0:
        return 3.2
    if voltage_kv >= 100.0:
        return 4.6
    return 3.5


def _aux_bus_label(bus_num: int, row: dict[str, str]) -> str:
    name = str(row.get("BusName", "")).strip()
    return f"{bus_num} {name}".strip()


def solve_greenfield_corridor(
    corridor: CorridorCase,
    useful_mw: float,
    config: GreenfieldScenarioConfig,
) -> dict[str, float | bool | str]:
    dcorridor = greenfield_corridor(corridor, config)
    if config.scenario_id == "C3":
        return solve_dc_corridor(dcorridor, useful_mw, config)
    return solve_ac_corridor(dcorridor, useful_mw, config)


def hosting_capacity(
    corridor: CorridorCase,
    config: GreenfieldScenarioConfig,
    lower_mw: float = 20.0,
    upper_mw: float | None = None,
    tolerance_mw: float = 2.5,
) -> dict[str, float | bool | str]:
    """Find maximum useful new data-center MW for a scenario."""

    if upper_mw is None:
        upper_mw = max(500.0, corridor.converter_rating_mw * 1.6)
    low = lower_mw
    high = upper_mw
    low_row = solve_greenfield_corridor(corridor, low, config)
    if low_row["binding_constraint"] != "none":
        return low_row | {
            "max_transfer_mw": 0.0,
            "binding_constraint_at_limit": str(low_row["binding_constraint"]),
            "first_violation_mw": lower_mw,
        }
    first_bad: dict[str, float | bool | str] | None = None
    for _ in range(42):
        mid = 0.5 * (low + high)
        row = solve_greenfield_corridor(corridor, mid, config)
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


def run_transfer_screen(corridors: list[CorridorCase], loads_mw: tuple[float, ...] = DEFAULT_LOADS_MW) -> pd.DataFrame:
    rows = []
    for corridor in corridors:
        for scenario_id, config in SCENARIOS.items():
            capacity = hosting_capacity(corridor, config)
            for load_mw in loads_mw:
                load_row = solve_greenfield_corridor(corridor, load_mw, config)
                rows.append(
                    _base_row(corridor, config)
                    | {
                        "study_load_mw": load_mw,
                        "existing_native_load_mw_excluded_from_new_corridor": corridor.existing_load_mw,
                        "new_data_center_load_is_incremental": True,
                        "max_transfer_mw": capacity["max_transfer_mw"],
                        "mw_per_km_at_limit": float(capacity["max_transfer_mw"]) / corridor.length_km,
                        "binding_constraint_at_limit": capacity["binding_constraint_at_limit"],
                        "first_violation_mw": capacity["first_violation_mw"],
                        "load_feasible_at_study_load": load_row["binding_constraint"] == "none",
                        "study_load_binding_constraint": load_row["binding_constraint"],
                    }
                    | _prefixed(load_row, "study_load_")
                )
    return pd.DataFrame(rows)


def run_harmonic_screen(
    corridors: list[CorridorCase],
    loads_mw: tuple[float, ...] = DEFAULT_LOADS_MW,
    seed: int = DEFAULT_HARMONIC_SEED,
    trials: int = 600,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for corridor in corridors:
        v_phase = corridor.voltage_kv * 1000.0 / math.sqrt(3.0)
        z1 = corridor.voltage_kv**2 / (corridor.short_circuit_gva * 1000.0)
        for load_mw in loads_mw:
            for scenario_id, config in SCENARIOS.items():
                thd_trials = []
                for _ in range(trials):
                    sc_mult = rng.triangular(0.65, 1.0, 1.45)
                    resonance_center = rng.normal(11.0, 1.2)
                    thd_sq = 0.0
                    for harmonic, frac in zip(HARMONICS, BASE_HARMONIC_FRAC):
                        resonance = 1.0 + 2.5 * np.exp(-0.5 * ((harmonic - resonance_center) / 1.7) ** 2)
                        z_h = z1 * harmonic * resonance / sc_mult
                        source_sum = _harmonic_source_sum(rng, config.harmonic_source_count)
                        i_base = load_mw * 1e6 / (math.sqrt(3.0) * corridor.voltage_kv * 1000.0)
                        vh_pct = (
                            100.0
                            * abs(i_base * frac * config.harmonic_scale * source_sum * z_h)
                            / v_phase
                            * HARMONIC_SCREENING_TRANSFER
                        )
                        thd_sq += vh_pct**2
                    thd_trials.append(math.sqrt(thd_sq))
                rows.append(
                    _base_row(corridor, config)
                    | {
                        "study_load_mw": load_mw,
                        "thdv_p50_pct": float(np.quantile(thd_trials, 0.50)),
                        "thdv_p95_pct": float(np.quantile(thd_trials, 0.95)),
                        "thdv_max_pct": float(np.max(thd_trials)),
                        "harmonic_source_count": config.harmonic_source_count,
                        "harmonic_ownership": config.harmonic_ownership,
                    }
                )
    return pd.DataFrame(rows)


def run_voltage_screen(corridors: list[CorridorCase], loads_mw: tuple[float, ...] = DEFAULT_LOADS_MW) -> pd.DataFrame:
    t = np.arange(0.0, 240.0, 0.02)
    dt = float(t[1] - t[0])
    poi_voltage = lel_voltage_event_pu(t)
    rows = []
    for corridor in corridors:
        ssc_mw = corridor.short_circuit_gva * 1000.0
        voltage_scale = (138.0 / corridor.voltage_kv) ** 2 * (corridor.length_km / 20.0) ** 0.5
        for load_mw in loads_mw:
            load_profile = ai_load_pu(t) * load_mw
            for scenario_id, config in SCENARIOS.items():
                grid = low_pass(load_profile, config.grid_tau_s, dt)
                pcc_v_pct = 100.0 * (grid - np.mean(grid)) / ssc_mw * voltage_scale
                service_voltage = _apply_voltage_support(poi_voltage, config)
                grid_fraction, current_fraction = _grid_power_fraction(service_voltage, config, dt)
                load_fraction = np.ones_like(grid_fraction) if config.dc_buffer_for_ride_through else grid_fraction
                recovery_s = lel_recovery_time_s(t, poi_voltage, grid_fraction)
                below_trip_s = _continuous_time_below(service_voltage, threshold=0.50, dt_s=dt)
                multiple_sag_risk = bool(
                    config.scenario_id == "C1" and np.sum(np.diff((poi_voltage < 0.80).astype(int)) == 1) >= 3
                )
                current_over_125_s = float(np.sum(current_fraction > 1.25 + 1e-9) * dt)
                ride_through_pass = current_over_125_s == 0.0 and recovery_s <= 2.0 and not multiple_sag_risk
                data_center_tripped = bool(config.scenario_id == "C1" and (below_trip_s >= 0.04 or multiple_sag_risk))
                buffer_mwh = 0.0
                if config.dc_buffer_for_ride_through:
                    buffer_mw = (load_fraction - grid_fraction) * load_mw
                    e_mwh = np.cumsum(buffer_mw) * dt / 3600.0
                    buffer_mwh = float(e_mwh.max() - e_mwh.min())
                rows.append(
                    _base_row(corridor, config)
                    | {
                        "study_load_mw": load_mw,
                        "coupling_tool": "HELICS",
                        "transmission_federate": "GridPACK Travis 150 real RAW/DYR case",
                        "distribution_federate": "OpenDSS data-center feeder proxy",
                        "helics_status": "screen_outputs; run scripts/run_gridpack_td_dynamic_var.py for the real Travis 150 GridPACK/HELICS path",
                        "disturbance": "eastern_interconnection_2024_repeated_voltage_sag_screen",
                        "poi_min_voltage_pu": float(np.min(poi_voltage)),
                        "service_34p5kv_min_voltage_pu": float(np.min(service_voltage)),
                        "load_boundary_min_voltage_pu": float(np.min(service_voltage)),
                        "load_boundary_nominal_voltage_v": config.load_boundary_voltage_v,
                        "grid_power_min_fraction": float(np.min(grid_fraction)),
                        "data_center_load_served_min_fraction": float(np.min(load_fraction)),
                        "data_center_load_loss_max_mw": float((1.0 - np.min(load_fraction)) * load_mw),
                        "data_center_tripped": data_center_tripped,
                        "ride_through_pass": ride_through_pass,
                        "current_max_pu": float(np.max(current_fraction)),
                        "current_over_125pct_s": current_over_125_s,
                        "recovery_to_90pct_s": recovery_s,
                        "p99_grid_ramp_mw_s": float(np.percentile(np.abs(np.diff(grid) / dt), 99)),
                        "rss_0p1_20hz_mw": spectral_rss(grid, dt),
                        "p95_pcc_voltage_deviation_pct": float(np.quantile(np.abs(pcc_v_pct), 0.95)),
                        "max_dynamic_var_mvar": config.local_q_support_mvar,
                        "dc_buffer_event_mwh": buffer_mwh,
                    }
                )
    return pd.DataFrame(rows)


def summarize_greenfield(
    transfer: pd.DataFrame,
    harmonics: pd.DataFrame,
    voltage: pd.DataFrame,
    base_load_mw: float = DEFAULT_OUTPUT_STUDY_LOAD_MW,
) -> pd.DataFrame:
    rows = []
    for scenario_id, config in SCENARIOS.items():
        t = _base_load_rows(transfer, scenario_id, base_load_mw)
        h = _base_load_rows(harmonics, scenario_id, base_load_mw)
        v = _base_load_rows(voltage, scenario_id, base_load_mw)
        rows.append(
            {
                "scenario_id": scenario_id,
                "architecture": config.label,
                "corridor_build": config.corridor_build,
                "base_load_mw": base_load_mw,
                "max_transfer_mw": t["max_transfer_mw"].median(),
                "mw_per_km_at_limit": t["mw_per_km_at_limit"].median(),
                "base_load_feasible": bool(t["load_feasible_at_study_load"].all()),
                "median_efficiency_at_base_load": t["study_load_efficiency_to_load_boundary"].median(),
                "median_loss_mw_at_base_load": t["study_load_loss_mw"].median(),
                "thdv_p95_pct": h["thdv_p95_pct"].median(),
                "harmonic_source_count": int(h["harmonic_source_count"].median()),
                "harmonic_ownership": config.harmonic_ownership,
                "p95_pcc_voltage_deviation_pct": v["p95_pcc_voltage_deviation_pct"].median(),
                "data_center_load_served_min_fraction": v["data_center_load_served_min_fraction"].median(),
                "data_center_tripped": bool(v["data_center_tripped"].any()),
                "ride_through_pass_fraction": v["ride_through_pass"].mean(),
                "dc_buffer_event_mwh": v["dc_buffer_event_mwh"].median(),
                "voltage_support_location": config.voltage_support_location,
            }
        )
    summary = pd.DataFrame(rows)
    c1 = summary[summary["scenario_id"] == "C1"].iloc[0]
    c2 = summary[summary["scenario_id"] == "C2"].iloc[0]
    c3 = summary[summary["scenario_id"] == "C3"].iloc[0]
    summary["benefit_transfer_vs_c1"] = summary["max_transfer_mw"] > float(c1["max_transfer_mw"])
    summary["benefit_harmonics_vs_c1"] = summary["thdv_p95_pct"] < float(c1["thdv_p95_pct"])
    summary["benefit_voltage_vs_c1"] = (
        (summary["p95_pcc_voltage_deviation_pct"] < float(c1["p95_pcc_voltage_deviation_pct"]))
        & (~summary["data_center_tripped"])
    )
    summary.loc[summary["scenario_id"] == "C1", ["benefit_transfer_vs_c1", "benefit_harmonics_vs_c1", "benefit_voltage_vs_c1"]] = False
    summary["three_benefits_met_vs_c1"] = (
        summary["benefit_transfer_vs_c1"] & summary["benefit_harmonics_vs_c1"] & summary["benefit_voltage_vs_c1"]
    )
    summary["c3_vs_c2_transfer_gain_pct"] = np.nan
    summary.loc[summary["scenario_id"] == "C3", "c3_vs_c2_transfer_gain_pct"] = (
        100.0 * (float(c3["max_transfer_mw"]) / float(c2["max_transfer_mw"]) - 1.0)
    )
    return summary


def _base_load_rows(frame: pd.DataFrame, scenario_id: str, base_load_mw: float) -> pd.DataFrame:
    rows = frame[(frame["scenario_id"] == scenario_id) & (frame["study_load_mw"] == base_load_mw)]
    if rows.empty:
        rows = frame[frame["scenario_id"] == scenario_id]
    return rows


def _base_row(corridor: CorridorCase, config: GreenfieldScenarioConfig) -> dict[str, float | str]:
    return {
        "dataset_id": corridor.dataset_id,
        "dataset_role": corridor.dataset_role,
        "pocket_id": corridor.pocket_id,
        "source_bus": corridor.source_bus,
        "load_bus": corridor.load_bus,
        "scenario_id": config.scenario_id,
        "architecture": config.label,
        "corridor_build": config.corridor_build,
        "new_line_or_conversion": "new_greenfield_line",
        "load_interface": config.load_interface,
        "load_boundary_voltage_v": config.load_boundary_voltage_v,
        "voltage_support_location": config.voltage_support_location,
        "voltage_support_role": config.voltage_support_role,
        "var_coordination_risk": config.var_coordination_risk,
        "voltage_kv": corridor.voltage_kv,
        "vdc_pp_kv": corridor.effective_vdc_pp_kv if config.scenario_id == "C3" else np.nan,
        "corridor_length_km": corridor.length_km,
        "current_limit_kA": corridor.current_limit_kA,
        "short_circuit_gva": corridor.short_circuit_gva,
        "source_q_limit_mvar": corridor.source_q_limit_mvar,
        "converter_rating_mw": corridor.converter_rating_mw,
    }


def _prefixed(values: dict[str, float | bool | str], prefix: str) -> dict[str, float | bool | str]:
    return {f"{prefix}{key}": value for key, value in values.items()}


def _apply_voltage_support(poi_voltage_pu: np.ndarray, config: GreenfieldScenarioConfig) -> np.ndarray:
    support = config.voltage_support_pu * np.clip(1.0 - poi_voltage_pu, 0.0, 1.0)
    return np.minimum(1.0, poi_voltage_pu + support)


def _grid_power_fraction(
    service_voltage_pu: np.ndarray,
    config: GreenfieldScenarioConfig,
    dt_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    if config.scenario_id == "C1":
        target = np.minimum(1.0, config.ride_through_current_cap_pu * np.maximum(service_voltage_pu, 0.05))
    else:
        target = np.minimum(1.0, np.maximum(0.0, service_voltage_pu / 0.80))
        target = np.minimum(target, config.ride_through_current_cap_pu * np.maximum(service_voltage_pu, 0.05))

    power = np.empty_like(target)
    power[0] = 1.0
    alpha_up = dt_s / (config.ride_through_recovery_tau_s + dt_s)
    for idx in range(1, len(target)):
        if target[idx] < power[idx - 1]:
            power[idx] = target[idx]
        else:
            power[idx] = power[idx - 1] + alpha_up * (target[idx] - power[idx - 1])
    current = power / np.maximum(service_voltage_pu, 0.05)
    return power, current


def _continuous_time_below(values: np.ndarray, threshold: float, dt_s: float) -> float:
    longest = 0
    current = 0
    for below in values < threshold:
        if below:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return float(longest * dt_s)


def _harmonic_source_sum(rng: np.random.Generator, n_sources: int) -> float:
    if n_sources <= 1:
        return 1.0
    phases = rng.uniform(0.0, 2.0 * np.pi, size=n_sources)
    return abs(np.sum(np.exp(1j * phases))) / math.sqrt(n_sources)
