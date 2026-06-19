#!/usr/bin/env python
"""Run the GridDyn-to-OpenDSS HELICS dynamic VAR study.

The executable path is intentionally explicit:

1. Build a repeated-fault GridDyn dynamic case.
2. Run GridDyn and parse the selected transmission POI voltage channel.
3. Exchange that voltage through HELICS with an OpenDSS distribution feeder and
   a dynamic VAR controller federate.
4. Write per-time-step and summary results for baseline, local 34.5 kV VAR and
   centralized 138 kV VAR support.

If an IEEE 118-bus or Texas A&M 150-bus dynamic GridDyn case is available, pass
it through ``--griddyn-case`` and ``--poi-voltage-field``. The default executable
demo uses GridDyn's bundled IEEE 39 dynamic case because the repository does not
ship an IEEE 118/Texas 150 dynamic-data package.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

warnings.filterwarnings("ignore", message="Pandas requires version .*", category=UserWarning)
try:
    from ai_dc_backbone.texas_td_scenarios import EASTERN_INTERCONNECTION_2024_SAG_EVENTS
except ModuleNotFoundError:
    EASTERN_INTERCONNECTION_2024_SAG_EVENTS = (
        (30.0, 0.38, 0.042),
        (46.4, 0.35, 0.050),
        (62.8, 0.40, 0.066),
        (79.2, 0.25, 0.058),
        (95.6, 0.32, 0.045),
        (112.0, 0.37, 0.060),
    )


DEFAULT_EVENT_CSV = ROOT / "cosim" / "griddyn_td_dynamic_var" / "eastern_interconnection_2024_voltage_sag_train.csv"
DEFAULT_OUTPUT_DIR = ROOT / "cosim" / "griddyn_td_dynamic_var" / "results"
DEFAULT_FEDERATION_PLAN = ROOT / "cosim" / "griddyn_td_dynamic_var" / "helics_federation_plan.json"
DEFAULT_GRIDDYN_IEEE39_DIR = Path("/tmp/GridDyn/test/test_files/IEEE_test_cases")
DEFAULT_POI_FIELD = "BUS_17:voltage"
SCENARIOS = ("baseline", "local_34p5kv", "central_138kv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--griddyn-exe",
        default="gridDynMain",
        help="GridDyn executable name or path. Example: /tmp/GridDyn-build/bin/gridDynMain.",
    )
    parser.add_argument(
        "--griddyn-case",
        type=Path,
        default=None,
        help=(
            "Optional existing GridDyn dynamic case. If omitted, the script writes a repeated-fault "
            "IEEE 39 GridDyn wrapper using --griddyn-ieee39-dir."
        ),
    )
    parser.add_argument(
        "--griddyn-ieee39-dir",
        type=Path,
        default=DEFAULT_GRIDDYN_IEEE39_DIR,
        help="Directory containing IEEE39.raw and IEEE39.dyr for the default GridDyn dynamic demo.",
    )
    parser.add_argument(
        "--poi-voltage-field",
        default=DEFAULT_POI_FIELD,
        help="GridDyn recorder field to publish into HELICS as the transmission POI voltage.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for GridDyn, HELICS/OpenDSS and summary outputs.",
    )
    parser.add_argument(
        "--event-csv",
        type=Path,
        default=DEFAULT_EVENT_CSV,
        help="Voltage-sag event CSV written for provenance.",
    )
    parser.add_argument(
        "--federation-plan",
        type=Path,
        default=DEFAULT_FEDERATION_PLAN,
        help="HELICS federation plan JSON to reference in the manifest.",
    )
    parser.add_argument(
        "--fault-link",
        default="LINK#5",
        help="GridDyn link target for default repeated-fault case.",
    )
    parser.add_argument(
        "--fault-value",
        default="0.5,-1",
        help="GridDyn fault value for default repeated-fault case.",
    )
    parser.add_argument(
        "--recorder-period-s",
        type=float,
        default=0.02,
        help="GridDyn recorder and HELICS time step in seconds.",
    )
    parser.add_argument(
        "--local-qmax-kvar",
        type=float,
        default=120_000.0,
        help="Maximum local 34.5 kV dynamic VAR injection.",
    )
    parser.add_argument(
        "--central-qmax-kvar",
        type=float,
        default=120_000.0,
        help="Maximum centralized 138 kV dynamic VAR injection.",
    )
    parser.add_argument(
        "--var-droop-kvar-per-pu",
        type=float,
        default=600_000.0,
        help="Dynamic VAR droop gain applied to voltage error below --var-vref-pu.",
    )
    parser.add_argument(
        "--var-vref-pu",
        type=float,
        default=0.95,
        help="Voltage reference for the dynamic VAR controller.",
    )
    parser.add_argument(
        "--trip-threshold-pu",
        type=float,
        default=0.50,
        help="AC-side voltage trip threshold used for the summary flag.",
    )
    parser.add_argument(
        "--trip-delay-s",
        type=float,
        default=0.04,
        help="Continuous time below --trip-threshold-pu before tripping is flagged.",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=SCENARIOS,
        default=list(SCENARIOS),
        help="Scenarios to run through the HELICS/OpenDSS federation.",
    )
    parser.add_argument(
        "--write-event-csv",
        action="store_true",
        help="Write the event CSV before doing any other work.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Report dependency and case availability without running GridDyn or HELICS.",
    )
    parser.add_argument(
        "--skip-griddyn",
        action="store_true",
        help="Reuse --griddyn-recorder-csv instead of launching GridDyn.",
    )
    parser.add_argument(
        "--griddyn-recorder-csv",
        type=Path,
        default=None,
        help="Existing GridDyn recorder CSV to reuse with --skip-griddyn.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run GridDyn, HELICS and OpenDSS. Without this flag the script prints a run plan only.",
    )
    return parser.parse_args()


def write_event_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["event_index", "start_s", "duration_s", "voltage_pu", "description"])
        for idx, (start_s, voltage_pu, duration_s) in enumerate(EASTERN_INTERCONNECTION_2024_SAG_EVENTS, start=1):
            writer.writerow([idx, start_s, duration_s, voltage_pu, "Eastern Interconnection 2024 inspired sag"])


def resolve_executable(command: str) -> str | None:
    path = Path(command)
    if path.exists():
        return str(path)
    return shutil.which(command)


def load_optional_modules() -> tuple[object, object]:
    try:
        import helics  # type: ignore
    except ImportError as exc:
        raise RuntimeError("HELICS Python bindings are not installed in this Python environment.") from exc

    try:
        import opendssdirect as dss  # type: ignore
    except ImportError as exc:
        raise RuntimeError("opendssdirect.py is not installed in this Python environment.") from exc

    return helics, dss


def default_time_stop() -> float:
    return max(start_s + duration_s for start_s, _voltage_pu, duration_s in EASTERN_INTERCONNECTION_2024_SAG_EVENTS) + 2.0


def write_default_griddyn_case(
    path: Path,
    recorder_csv: Path,
    ieee39_dir: Path,
    fault_link: str,
    fault_value: str,
    recorder_period_s: float,
) -> None:
    raw = ieee39_dir / "IEEE39.raw"
    dyr = ieee39_dir / "IEEE39.dyr"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<griddyn name="ieee39_repeated_fault_helics_source" version="0.0.1">',
        f'  <import file="{raw}"/>',
        f'  <import file="{dyr}"/>',
    ]
    for start_s, _voltage_pu, duration_s in EASTERN_INTERCONNECTION_2024_SAG_EVENTS:
        lines.extend(
            [
                "  <event>",
                f"    <target>{fault_link}</target>",
                "    <field>fault</field>",
                f"    <value>{fault_value}</value>",
                f"    <time>{start_s},{start_s + duration_s}</time>",
                "  </event>",
            ]
        )
    lines.extend(
        [
            f'  <recorder field="auto" period="{recorder_period_s}">',
            f"    <file>{recorder_csv}</file>",
            "  </recorder>",
            "  <timestart>0</timestart>",
            f"  <timestop>{default_time_stop():.6f}</timestop>",
            "</griddyn>",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def read_grid_dyn_recorder(path: Path, voltage_field: str) -> list[tuple[float, float]]:
    if not path.exists():
        raise FileNotFoundError(f"GridDyn recorder CSV does not exist: {path}")
    with path.open(errors="replace") as f:
        lines = [line for line in f if not line.startswith("#")]
    if not lines:
        raise RuntimeError(f"GridDyn recorder CSV has no tabular rows: {path}")

    reader = csv.reader(lines)
    header = [h.strip().strip('"') for h in next(reader)]
    if voltage_field not in header:
        voltage_options = [h for h in header if ":voltage" in h]
        sample = ", ".join(voltage_options[:8])
        raise RuntimeError(f"Field {voltage_field!r} not found in {path}. Voltage fields include: {sample}")
    voltage_idx = header.index(voltage_field)

    series: list[tuple[float, float]] = []
    for row in reader:
        if not row or len(row) <= voltage_idx:
            continue
        try:
            t_s = float(row[0].strip().rstrip("s"))
            v_pu = float(row[voltage_idx])
        except ValueError:
            continue
        series.append((t_s, v_pu))
    if not series:
        raise RuntimeError(f"No numeric voltage samples found for {voltage_field!r} in {path}")
    return series


def write_poi_series(path: Path, series: list[tuple[float, float]], voltage_field: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "poi_voltage_pu", "griddyn_field"])
        for t_s, v_pu in series:
            writer.writerow([f"{t_s:.6f}", f"{v_pu:.8f}", voltage_field])


class OpenDSSDataCenterFeeder:
    """Small OpenDSS feeder representing a 138 kV POI and 34.5 kV data-center load."""

    def __init__(self, dss: object) -> None:
        self.dss = dss
        self._build()

    def _cmd(self, command: str) -> None:
        self.dss.Text.Command(command)

    def _build(self) -> None:
        self._cmd("Clear")
        commands = [
            "New Circuit.DataCenter basekv=138 pu=1 phases=3 bus1=sourcebus.1.2.3",
            "Edit Vsource.Source bus1=sourcebus.1.2.3 basekv=138 pu=1 phases=3 MVAsc3=5000 MVAsc1=5000",
            (
                "New Transformer.Sub phases=3 windings=2 buses=[sourcebus.1.2.3,dc34.1.2.3] "
                "conns=[wye,wye] kvs=[138,34.5] kvas=[150000,150000] xhl=8"
            ),
            "New Linecode.Cable nphases=3 r1=0.08 x1=0.25 r0=0.24 x0=0.75 c1=1 c0=0 units=km",
            "New Line.Feeder bus1=dc34.1.2.3 bus2=datacenter.1.2.3 phases=3 linecode=Cable length=1 units=km",
            "New Load.DataCenter bus1=datacenter.1.2.3 phases=3 kv=34.5 kw=80000 kvar=25000 model=1",
            "New Generator.LocalVAR bus1=datacenter.1.2.3 phases=3 kv=34.5 kw=0 kvar=0 model=1",
            "New Generator.CentralVAR bus1=sourcebus.1.2.3 phases=3 kv=138 kw=0 kvar=0 model=1",
            "Set VoltageBases=[138,34.5]",
            "CalcVoltageBases",
            "Solve mode=snap",
        ]
        for command in commands:
            self._cmd(command)

    def solve(self, poi_voltage_pu: float, local_q_kvar: float, central_q_kvar: float) -> dict[str, float | bool]:
        self._cmd(f"Edit Vsource.Source pu={max(poi_voltage_pu, 0.001):.8f}")
        self._cmd(f"Edit Generator.LocalVAR kvar={max(local_q_kvar, 0.0):.6f}")
        self._cmd(f"Edit Generator.CentralVAR kvar={max(central_q_kvar, 0.0):.6f}")
        self._cmd("Solve mode=snap")

        self.dss.Circuit.SetActiveBus("datacenter")
        vmag = self.dss.Bus.puVmagAngle()
        datacenter_v = float(vmag[0]) if vmag else float("nan")

        self.dss.Circuit.SetActiveBus("dc34")
        vmag34 = self.dss.Bus.puVmagAngle()
        mv_v = float(vmag34[0]) if vmag34 else float("nan")

        self.dss.Circuit.SetActiveElement("Load.DataCenter")
        powers = self.dss.CktElement.Powers()
        load_kw = float(sum(powers[0::2]))
        load_kvar = float(sum(powers[1::2]))

        return {
            "datacenter_ac_voltage_pu": datacenter_v,
            "mv_bus_voltage_pu": mv_v,
            "load_kw": load_kw,
            "load_kvar": load_kvar,
            "opendss_converged": bool(self.dss.Solution.Converged()),
        }


def controller_q_kvar(
    scenario: str,
    measured_voltage_pu: float,
    vref_pu: float,
    droop_kvar_per_pu: float,
    local_qmax_kvar: float,
    central_qmax_kvar: float,
) -> tuple[float, float]:
    if scenario == "baseline":
        return 0.0, 0.0
    error = max(0.0, vref_pu - measured_voltage_pu)
    raw_q = error * droop_kvar_per_pu
    if scenario == "local_34p5kv":
        return min(raw_q, local_qmax_kvar), 0.0
    if scenario == "central_138kv":
        return 0.0, min(raw_q, central_qmax_kvar)
    raise ValueError(f"Unknown scenario: {scenario}")


def run_helics_opendss_scenario(
    h: object,
    dss: object,
    scenario: str,
    series: list[tuple[float, float]],
    args: argparse.Namespace,
) -> list[dict[str, float | bool | str]]:
    broker_name = f"td_dynamic_var_{scenario}_{uuid.uuid4().hex[:8]}"
    broker = h.helicsCreateBroker("inproc", broker_name, "--federates=3 --loglevel=warning")
    if not h.helicsBrokerIsConnected(broker):
        raise RuntimeError("HELICS broker failed to start")

    def make_fed(name: str) -> object:
        fedinfo = h.helicsCreateFederateInfo()
        h.helicsFederateInfoSetCoreTypeFromString(fedinfo, "inproc")
        h.helicsFederateInfoSetCoreInitString(fedinfo, f"--broker={broker_name} --federates=1")
        h.helicsFederateInfoSetTimeProperty(fedinfo, h.helics_property_time_delta, args.recorder_period_s)
        return h.helicsCreateValueFederate(name, fedinfo)

    tx_fed = make_fed(f"{scenario}_GridDynTransmission")
    dist_fed = make_fed(f"{scenario}_OpenDSSDistribution")
    ctrl_fed = make_fed(f"{scenario}_DynamicVARController")

    tx_v_pub = h.helicsFederateRegisterGlobalPublication(
        tx_fed, f"{scenario}/transmission/poi_voltage_pu", h.HELICS_DATA_TYPE_DOUBLE, "pu"
    )
    tx_load_kw_sub = h.helicsFederateRegisterSubscription(tx_fed, f"{scenario}/distribution/load_kw", "kW")

    dist_v_sub = h.helicsFederateRegisterSubscription(dist_fed, f"{scenario}/transmission/poi_voltage_pu", "pu")
    dist_q_local_sub = h.helicsFederateRegisterSubscription(dist_fed, f"{scenario}/controller/local_q_kvar", "kvar")
    dist_q_central_sub = h.helicsFederateRegisterSubscription(dist_fed, f"{scenario}/controller/central_q_kvar", "kvar")
    dist_v_pub = h.helicsFederateRegisterGlobalPublication(
        dist_fed, f"{scenario}/distribution/datacenter_ac_voltage_pu", h.HELICS_DATA_TYPE_DOUBLE, "pu"
    )
    dist_load_kw_pub = h.helicsFederateRegisterGlobalPublication(
        dist_fed, f"{scenario}/distribution/load_kw", h.HELICS_DATA_TYPE_DOUBLE, "kW"
    )
    dist_load_kvar_pub = h.helicsFederateRegisterGlobalPublication(
        dist_fed, f"{scenario}/distribution/load_kvar", h.HELICS_DATA_TYPE_DOUBLE, "kvar"
    )

    ctrl_v_sub = h.helicsFederateRegisterSubscription(
        ctrl_fed, f"{scenario}/distribution/datacenter_ac_voltage_pu", "pu"
    )
    ctrl_q_local_pub = h.helicsFederateRegisterGlobalPublication(
        ctrl_fed, f"{scenario}/controller/local_q_kvar", h.HELICS_DATA_TYPE_DOUBLE, "kvar"
    )
    ctrl_q_central_pub = h.helicsFederateRegisterGlobalPublication(
        ctrl_fed, f"{scenario}/controller/central_q_kvar", h.HELICS_DATA_TYPE_DOUBLE, "kvar"
    )

    h.helicsFederateEnterExecutingModeAsync(tx_fed)
    h.helicsFederateEnterExecutingModeAsync(ctrl_fed)
    h.helicsFederateEnterExecutingMode(dist_fed)
    h.helicsFederateEnterExecutingModeComplete(tx_fed)
    h.helicsFederateEnterExecutingModeComplete(ctrl_fed)

    feeder = OpenDSSDataCenterFeeder(dss)
    rows: list[dict[str, float | bool | str]] = []
    local_q_kvar = 0.0
    central_q_kvar = 0.0
    below_threshold_s = 0.0
    prev_time = series[0][0]
    controller_voltage = 1.0

    try:
        for idx, (time_s, griddyn_v_pu) in enumerate(series):
            h.helicsPublicationPublishDouble(tx_v_pub, griddyn_v_pu)
            h.helicsPublicationPublishDouble(ctrl_q_local_pub, local_q_kvar)
            h.helicsPublicationPublishDouble(ctrl_q_central_pub, central_q_kvar)

            h.helicsFederateRequestTimeAsync(tx_fed, time_s)
            h.helicsFederateRequestTimeAsync(ctrl_fed, time_s)
            granted_dist = h.helicsFederateRequestTime(dist_fed, time_s)
            granted_tx = h.helicsFederateRequestTimeComplete(tx_fed)
            granted_ctrl = h.helicsFederateRequestTimeComplete(ctrl_fed)

            poi_v = h.helicsInputGetDouble(dist_v_sub) if idx > 0 else griddyn_v_pu
            q_local_rx = h.helicsInputGetDouble(dist_q_local_sub) if idx > 0 else local_q_kvar
            q_central_rx = h.helicsInputGetDouble(dist_q_central_sub) if idx > 0 else central_q_kvar
            solved = feeder.solve(poi_v, q_local_rx, q_central_rx)

            datacenter_v = float(solved["datacenter_ac_voltage_pu"])
            load_kw = float(solved["load_kw"])
            load_kvar = float(solved["load_kvar"])
            h.helicsPublicationPublishDouble(dist_v_pub, datacenter_v)
            h.helicsPublicationPublishDouble(dist_load_kw_pub, load_kw)
            h.helicsPublicationPublishDouble(dist_load_kvar_pub, load_kvar)

            dt = max(0.0, time_s - prev_time)
            if datacenter_v < args.trip_threshold_pu:
                below_threshold_s += dt
            else:
                below_threshold_s = 0.0
            tripped = below_threshold_s >= args.trip_delay_s

            if idx > 0:
                controller_voltage = h.helicsInputGetDouble(ctrl_v_sub)
            local_q_kvar, central_q_kvar = controller_q_kvar(
                scenario,
                controller_voltage,
                args.var_vref_pu,
                args.var_droop_kvar_per_pu,
                args.local_qmax_kvar,
                args.central_qmax_kvar,
            )

            tx_observed_load_kw = h.helicsInputGetDouble(tx_load_kw_sub) if idx > 1 else 0.0
            rows.append(
                {
                    "scenario": scenario,
                    "time_s": time_s,
                    "helics_time_transmission_s": float(granted_tx),
                    "helics_time_distribution_s": float(granted_dist),
                    "helics_time_controller_s": float(granted_ctrl),
                    "griddyn_poi_voltage_pu": griddyn_v_pu,
                    "helics_poi_voltage_pu": poi_v,
                    "datacenter_ac_voltage_pu": datacenter_v,
                    "mv_bus_voltage_pu": float(solved["mv_bus_voltage_pu"]),
                    "local_q_kvar": q_local_rx,
                    "central_q_kvar": q_central_rx,
                    "load_kw": load_kw,
                    "load_kvar": load_kvar,
                    "tx_observed_load_kw": tx_observed_load_kw,
                    "below_trip_threshold_s": below_threshold_s,
                    "trip_flag": tripped,
                    "opendss_converged": bool(solved["opendss_converged"]),
                }
            )
            prev_time = time_s
    finally:
        disconnect = getattr(h, "helicsFederateDisconnect", h.helicsFederateFinalize)
        disconnect(tx_fed)
        disconnect(dist_fed)
        disconnect(ctrl_fed)
        h.helicsBrokerWaitForDisconnect(broker, 2000)
    return rows


def write_rows(path: Path, rows: list[dict[str, float | bool | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError("No rows to write")
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize_rows(rows: list[dict[str, float | bool | str]]) -> list[dict[str, float | bool | str]]:
    by_scenario: dict[str, list[dict[str, float | bool | str]]] = {}
    for row in rows:
        by_scenario.setdefault(str(row["scenario"]), []).append(row)

    summary: list[dict[str, float | bool | str]] = []
    for scenario, scenario_rows in by_scenario.items():
        min_row = min(scenario_rows, key=lambda r: float(r["datacenter_ac_voltage_pu"]))
        poi_min_row = min(scenario_rows, key=lambda r: float(r["griddyn_poi_voltage_pu"]))
        summary.append(
            {
                "scenario": scenario,
                "samples": len(scenario_rows),
                "poi_min_voltage_pu": float(poi_min_row["griddyn_poi_voltage_pu"]),
                "poi_min_time_s": float(poi_min_row["time_s"]),
                "datacenter_min_ac_voltage_pu": float(min_row["datacenter_ac_voltage_pu"]),
                "datacenter_min_ac_time_s": float(min_row["time_s"]),
                "max_local_q_kvar": max(float(r["local_q_kvar"]) for r in scenario_rows),
                "max_central_q_kvar": max(float(r["central_q_kvar"]) for r in scenario_rows),
                "tripped_on_ac_voltage": any(bool(r["trip_flag"]) for r in scenario_rows),
                "all_opendss_solves_converged": all(bool(r["opendss_converged"]) for r in scenario_rows),
            }
        )
    return summary


def write_summary(path: Path, summary: list[dict[str, float | bool | str]]) -> None:
    write_rows(path, summary)


def build_plan(args: argparse.Namespace, griddyn_path: str | None, recorder_csv: Path, case_path: Path) -> dict[str, object]:
    return {
        "transmission_backend": "GridDyn",
        "distribution_backend": "OpenDSSDirect.py",
        "federation_layer": "HELICS",
        "griddyn_executable": griddyn_path,
        "griddyn_case": str(case_path),
        "griddyn_recorder_csv": str(recorder_csv),
        "poi_voltage_field": args.poi_voltage_field,
        "event_csv": str(args.event_csv),
        "federation_plan": str(args.federation_plan),
        "output_dir": str(args.output_dir),
        "scenarios": args.scenarios,
        "executed": False,
        "note": (
            "Default case uses GridDyn's IEEE 39 dynamic event data. Pass --griddyn-case for an IEEE 118 "
            "or Texas A&M 150-bus dynamic GridDyn case when available."
        ),
    }


def run_griddyn(griddyn_path: str, case_path: Path, ieee39_dir: Path) -> subprocess.CompletedProcess[str]:
    # Avoid Anaconda's old ld in PATH when GridDyn was built with Homebrew GCC on macOS.
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin:/opt/homebrew/bin:/opt/homebrew/sbin"
    command = [griddyn_path, str(case_path), "--summary", "--dir", str(ieee39_dir)]
    return subprocess.run(command, check=False, text=True, capture_output=True, env=env)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.write_event_csv or args.execute:
        write_event_csv(args.event_csv)

    griddyn_path = resolve_executable(args.griddyn_exe)
    recorder_csv = args.griddyn_recorder_csv or (args.output_dir / "griddyn_ieee39_repeated_fault_recorder.csv")
    case_path = args.griddyn_case or (args.output_dir / "griddyn_ieee39_repeated_fault_case.xml")
    plan = build_plan(args, griddyn_path, recorder_csv, case_path)

    if args.check_only or not args.execute:
        print(json.dumps(plan, indent=2))
        if args.check_only:
            if griddyn_path is None:
                print("GridDyn executable was not found; build GridDyn or pass --griddyn-exe.", file=sys.stderr)
            if args.griddyn_case is None:
                raw = args.griddyn_ieee39_dir / "IEEE39.raw"
                dyr = args.griddyn_ieee39_dir / "IEEE39.dyr"
                if not raw.exists() or not dyr.exists():
                    print(f"Default IEEE 39 GridDyn files not found under {args.griddyn_ieee39_dir}.", file=sys.stderr)
            elif not args.griddyn_case.exists():
                print(f"GridDyn case does not exist: {args.griddyn_case}", file=sys.stderr)
        return 0

    if not args.skip_griddyn and griddyn_path is None:
        print("Cannot run GridDyn: executable was not found.", file=sys.stderr)
        return 2
    if args.skip_griddyn and args.griddyn_recorder_csv is None:
        print("--skip-griddyn requires --griddyn-recorder-csv.", file=sys.stderr)
        return 2

    try:
        h, dss = load_optional_modules()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not args.skip_griddyn:
        if args.griddyn_case is None:
            raw = args.griddyn_ieee39_dir / "IEEE39.raw"
            dyr = args.griddyn_ieee39_dir / "IEEE39.dyr"
            if not raw.exists() or not dyr.exists():
                print(f"Default IEEE 39 GridDyn files not found under {args.griddyn_ieee39_dir}.", file=sys.stderr)
                return 2
            write_default_griddyn_case(
                case_path,
                recorder_csv,
                args.griddyn_ieee39_dir,
                args.fault_link,
                args.fault_value,
                args.recorder_period_s,
            )
        elif not case_path.exists():
            print(f"GridDyn case does not exist: {case_path}", file=sys.stderr)
            return 2

        completed = run_griddyn(str(griddyn_path), case_path, args.griddyn_ieee39_dir)
        (args.output_dir / "griddyn_stdout.log").write_text(completed.stdout)
        (args.output_dir / "griddyn_stderr.log").write_text(completed.stderr)
        if completed.returncode != 0:
            print(f"GridDyn failed with exit code {completed.returncode}. See {args.output_dir}", file=sys.stderr)
            return completed.returncode

    series = read_grid_dyn_recorder(recorder_csv, args.poi_voltage_field)
    write_poi_series(args.output_dir / "griddyn_poi_voltage_timeseries.csv", series, args.poi_voltage_field)

    all_rows: list[dict[str, float | bool | str]] = []
    for scenario in args.scenarios:
        all_rows.extend(run_helics_opendss_scenario(h, dss, scenario, series, args))
    h.helicsCloseLibrary()

    timeseries_path = args.output_dir / "helics_opendss_dynamic_var_timeseries.csv"
    summary_path = args.output_dir / "helics_opendss_dynamic_var_summary.csv"
    manifest_path = args.output_dir / "run_manifest.json"
    write_rows(timeseries_path, all_rows)
    summary = summarize_rows(all_rows)
    write_summary(summary_path, summary)

    plan["executed"] = True
    plan["timeseries_csv"] = str(timeseries_path)
    plan["summary_csv"] = str(summary_path)
    plan["grid_dyn_voltage_samples"] = len(series)
    plan["tool_versions"] = {
        "helics": h.helicsGetVersion(),
        "opendssdirect": getattr(dss, "__version__", "unknown"),
    }
    manifest_path.write_text(json.dumps(plan, indent=2) + "\n")

    print(json.dumps({"manifest": str(manifest_path), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
