#!/usr/bin/env python
"""Run the GridPACK-to-OpenDSS HELICS dynamic VAR study.

This is the real Travis 150 transmission path. It writes a GridPACK dynamic
simulation input deck for ``Travis150-updated/150.RAW`` plus the GridPACK-ready
DYR file, runs GridPACK ``dsf.x`` when available, and then exchanges a POI
voltage series with the existing HELICS/OpenDSS data-center feeder scenarios.

GridPACK's stock ``dsf.x`` application writes generator watch files, not a
bus-voltage recorder. If ``--gridpack-poi-voltage-csv`` is provided, that
post-processed POI voltage is used for HELICS. Otherwise, the runner uses the
retained sag-train fallback only as a coupling demo after the real GridPACK
case has been executed, and records that provenance in the manifest. Manuscript
Fig. 6 uses the exported GridPACK branch-fault POI traces in
``cosim/gridpack_td_dynamic_var/results_event_sweep/``.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_griddyn_td_dynamic_var as td  # noqa: E402

DEFAULT_OUTPUT_DIR = ROOT / "cosim" / "gridpack_td_dynamic_var" / "results"
DEFAULT_FEDERATION_PLAN = ROOT / "cosim" / "gridpack_td_dynamic_var" / "helics_federation_plan.json"
DEFAULT_RAW = ROOT / "Travis150-updated" / "150.RAW"
DEFAULT_DYR = ROOT / "Travis150-updated" / "150_gridpack_REECA1_candidate.dyr"
DEFAULT_EVENT_CSV = ROOT / "cosim" / "griddyn_td_dynamic_var" / "eastern_interconnection_2024_voltage_sag_train.csv"
DEFAULT_WATCH_FILE = "gridpack_travis150_generator_watch.csv"
DEFAULT_GRIDPACK_INPUT = "gridpack_travis150_dynamic_input.xml"
DEFAULT_FAULT_BRANCH = "137 150"
DEFAULT_POI_BUS = 150


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gridpack-exe",
        default="dsf.x",
        help="GridPACK dynamic simulation executable, normally dsf.x or a full path to dsf.x.",
    )
    parser.add_argument("--mpiexec", default=None, help="Optional MPI launcher, e.g. mpiexec or mpirun.")
    parser.add_argument("--mpi-ranks", type=int, default=1, help="MPI ranks to use when --mpiexec is set.")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="PSS/E RAW case for GridPACK.")
    parser.add_argument("--dyr", type=Path, default=DEFAULT_DYR, help="PSS/E DYR case for GridPACK.")
    parser.add_argument(
        "--gridpack-input",
        type=Path,
        default=None,
        help="Optional GridPACK XML input path. Defaults to output-dir/gridpack_travis150_dynamic_input.xml.",
    )
    parser.add_argument(
        "--gridpack-watch-csv",
        type=Path,
        default=None,
        help="Generator watch CSV written by GridPACK. Defaults to output-dir/gridpack_travis150_generator_watch.csv.",
    )
    parser.add_argument(
        "--gridpack-poi-voltage-csv",
        type=Path,
        default=None,
        help=(
            "Optional POI voltage CSV from GridPACK or post-processing. Accepted columns include "
            "time_s and poi_voltage_pu. If omitted, HELICS uses the documented sag event CSV after "
            "GridPACK execution."
        ),
    )
    parser.add_argument("--poi-bus", type=int, default=DEFAULT_POI_BUS, help="Bus to list as the GridPACK POI observation.")
    parser.add_argument("--fault-branch", default=DEFAULT_FAULT_BRANCH, help="GridPACK fault branch as 'from to'.")
    parser.add_argument("--simulation-time-s", type=float, default=td.default_time_stop(), help="Dynamic simulation stop time.")
    parser.add_argument("--gridpack-timestep-s", type=float, default=0.005, help="GridPACK dynamic time step.")
    parser.add_argument("--watch-frequency", type=int, default=1, help="GridPACK generatorWatchFrequency.")
    parser.add_argument("--max-watch-generators", type=int, default=8, help="Number of online generators to watch.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--event-csv", type=Path, default=DEFAULT_EVENT_CSV, help="Sag event CSV for provenance.")
    parser.add_argument("--federation-plan", type=Path, default=DEFAULT_FEDERATION_PLAN, help="HELICS plan JSON.")
    parser.add_argument("--recorder-period-s", type=float, default=0.02, help="HELICS time step.")
    parser.add_argument("--local-qmax-kvar", type=float, default=120_000.0)
    parser.add_argument("--central-qmax-kvar", type=float, default=120_000.0)
    parser.add_argument("--var-droop-kvar-per-pu", type=float, default=600_000.0)
    parser.add_argument("--var-vref-pu", type=float, default=0.95)
    parser.add_argument("--trip-threshold-pu", type=float, default=0.50)
    parser.add_argument("--trip-delay-s", type=float, default=0.04)
    parser.add_argument("--scenarios", nargs="+", choices=td.SCENARIO_CHOICES, default=list(td.SCENARIOS))
    parser.add_argument("--write-event-csv", action="store_true")
    parser.add_argument("--check-only", action="store_true", help="Write/print plan and validate paths without executing.")
    parser.add_argument("--execute", action="store_true", help="Run GridPACK, HELICS, and OpenDSS.")
    parser.add_argument("--skip-gridpack", action="store_true", help="Reuse existing GridPACK outputs and skip dsf.x.")
    parser.add_argument(
        "--require-gridpack-poi-voltage",
        action="store_true",
        help="Fail instead of using the event sag series when --gridpack-poi-voltage-csv is absent.",
    )
    return parser.parse_args()


def parse_psse_csv(line: str) -> list[str]:
    return next(csv.reader([line], quotechar="'", skipinitialspace=True))


def raw_sections(raw_path: Path) -> dict[str, list[tuple[int, str]]]:
    sections: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    for idx, line in enumerate(raw_path.read_text(errors="replace").splitlines(), 1):
        s = line.strip()
        if "BEGIN BUS DATA" in s:
            current = "bus"
            sections[current] = []
            continue
        if "END OF BUS DATA" in s:
            current = None
        if "BEGIN GENERATOR DATA" in s:
            current = "gen"
            sections[current] = []
            continue
        if "END OF GENERATOR DATA" in s:
            current = None
        if "BEGIN BRANCH DATA" in s:
            current = "branch"
            sections[current] = []
            continue
        if "END OF BRANCH DATA" in s:
            current = None
        if current and s and not s.startswith("@!") and not s.startswith("0 /"):
            sections[current].append((idx, line))
    return sections


def summarize_raw(raw_path: Path) -> dict[str, object]:
    sections = raw_sections(raw_path)
    buses: dict[int, dict[str, object]] = {}
    for line_no, line in sections.get("bus", []):
        row = parse_psse_csv(line)
        buses[int(row[0])] = {
            "name": row[1].strip(),
            "kv": float(row[2]),
            "line": line_no,
        }

    generators = []
    for line_no, line in sections.get("gen", []):
        row = parse_psse_csv(line)
        bus = int(row[0])
        generators.append(
            {
                "line": line_no,
                "bus": bus,
                "id": row[1].strip(),
                "pg": float(row[2]),
                "qg": float(row[3]),
                "mbase": float(row[9]),
                "status": int(row[15]),
                "kv": float(buses[bus]["kv"]),
                "name": str(buses[bus]["name"]),
            }
        )

    branches = []
    for line_no, line in sections.get("branch", []):
        row = parse_psse_csv(line)
        i_bus = int(row[0])
        j_bus = int(row[1])
        status = int(row[23])
        branches.append(
            {
                "line": line_no,
                "from": i_bus,
                "to": j_bus,
                "status": status,
                "from_kv": float(buses[i_bus]["kv"]),
                "to_kv": float(buses[j_bus]["kv"]),
            }
        )

    online_gens = [g for g in generators if g["status"] == 1]
    return {
        "bus_count": len(buses),
        "generator_count": len(generators),
        "online_generator_count": len(online_gens),
        "online_generation_mw": round(sum(float(g["pg"]) for g in online_gens), 6),
        "branch_count": len(branches),
        "online_branch_count": sum(1 for b in branches if b["status"] == 1),
        "online_generators": sorted(online_gens, key=lambda g: float(g["pg"]), reverse=True),
        "online_branches": [b for b in branches if b["status"] == 1],
    }


def choose_watch_generators(raw_path: Path, max_count: int) -> list[dict[str, object]]:
    summary = summarize_raw(raw_path)
    return list(summary["online_generators"])[:max_count]


def resolve_executable(command: str) -> str | None:
    path = Path(command)
    if path.exists():
        return str(path)
    return shutil.which(command)


def validate_fault_branch(raw_path: Path, fault_branch: str) -> None:
    try:
        i_bus, j_bus = [int(x) for x in fault_branch.split()[:2]]
    except ValueError as exc:
        raise ValueError("--fault-branch must be two integer bus IDs, e.g. '137 150'.") from exc
    summary = summarize_raw(raw_path)
    for branch in summary["online_branches"]:
        if {branch["from"], branch["to"]} == {i_bus, j_bus}:
            return
    raise ValueError(f"Fault branch {fault_branch!r} is not an online branch in {raw_path}.")


def prepare_gridpack_case_files(raw_path: Path, dyr_path: Path, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dst = output_dir / raw_path.name
    dyr_dst = output_dir / dyr_path.name
    if raw_path.resolve() != raw_dst.resolve():
        shutil.copy2(raw_path, raw_dst)
    if dyr_path.resolve() != dyr_dst.resolve():
        shutil.copy2(dyr_path, dyr_dst)
    return raw_dst, dyr_dst


def write_gridpack_input(
    path: Path,
    raw_file: Path,
    dyr_file: Path,
    watch_file: Path,
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    validate_fault_branch(raw_file, args.fault_branch)
    watch_generators = choose_watch_generators(raw_file, args.max_watch_generators)
    generator_watch = "\n".join(
        [
            "      <generator>\n"
            f"        <busID> {int(gen['bus'])} </busID>\n"
            f"        <generatorID> {gen['id']} </generatorID>\n"
            "      </generator>"
            for gen in watch_generators
        ]
    )
    observations = "\n".join(
        [
            "      <observation>\n"
            "        <type> bus </type>\n"
            f"        <busID> {args.poi_bus} </busID>\n"
            "      </observation>",
            *[
                "      <observation>\n"
                "        <type> generator </type>\n"
                f"        <busID> {int(gen['bus'])} </busID>\n"
                f"        <generatorID> {gen['id']} </generatorID>\n"
                "      </observation>"
                for gen in watch_generators[:3]
            ],
        ]
    )
    fault_events = "\n".join(
        [
            "      <faultEvent>\n"
            f"        <beginFault> {start_s:.6f} </beginFault>\n"
            f"        <endFault> {start_s + duration_s:.6f} </endFault>\n"
            f"        <faultBranch> {args.fault_branch} </faultBranch>\n"
            f"        <timeStep> {args.gridpack_timestep_s:.6f} </timeStep>\n"
            "      </faultEvent>"
            for start_s, _voltage_pu, duration_s in td.EASTERN_INTERCONNECTION_2024_SAG_EVENTS
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<Configuration>
  <Powerflow>
    <networkConfiguration> {raw_file.name} </networkConfiguration>
    <maxIteration>50</maxIteration>
    <tolerance>1.0e-6</tolerance>
    <UseNonLinear>false</UseNonLinear>
    <UseNewton>false</UseNewton>
    <LinearSolver>
      <PETScOptions>
        -ksp_type richardson
        -pc_type lu
        -pc_factor_mat_solver_type superlu_dist
        -ksp_max_it 1
      </PETScOptions>
    </LinearSolver>
  </Powerflow>
  <Dynamic_simulation>
    <generatorParameters> {dyr_file.name} </generatorParameters>
    <simulationTime>{args.simulation_time_s:.6f}</simulationTime>
    <timeStep>{args.gridpack_timestep_s:.6f}</timeStep>
    <Events>
{fault_events}
    </Events>
    <reportNonExistingElements>false</reportNonExistingElements>
    <observations>
{observations}
    </observations>
    <generatorWatch>
{generator_watch}
    </generatorWatch>
    <generatorWatchFrequency>{args.watch_frequency}</generatorWatchFrequency>
    <generatorWatchFileName>{watch_file.name}</generatorWatchFileName>
    <suppressWatchFiles>false</suppressWatchFiles>
    <LinearSolver>
      <SolutionTolerance>1.0E-12</SolutionTolerance>
      <ForceSerial>true</ForceSerial>
      <InitialGuessZero>true</InitialGuessZero>
      <SerialMatrixConstant>true</SerialMatrixConstant>
      <PETScOptions>
        -ksp_type richardson
        -pc_type lu
        -pc_factor_mat_solver_type superlu_dist
        -ksp_max_it 1
      </PETScOptions>
    </LinearSolver>
    <LinearMatrixSolver>
      <Ordering>nd</Ordering>
      <Package>superlu_dist</Package>
      <Iterations>1</Iterations>
      <Fill>5</Fill>
    </LinearMatrixSolver>
  </Dynamic_simulation>
</Configuration>
"""
    )
    return watch_generators


def run_gridpack(args: argparse.Namespace, gridpack_exe: str, input_xml: Path) -> subprocess.CompletedProcess[str]:
    command = [gridpack_exe, input_xml.name]
    if args.mpiexec:
        command = [args.mpiexec, "-n", str(args.mpi_ranks), *command]
    env = os.environ.copy()
    return subprocess.run(command, cwd=args.output_dir, check=False, text=True, capture_output=True, env=env)


def read_poi_voltage_csv(path: Path) -> list[tuple[float, float]]:
    with path.open(errors="replace") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise RuntimeError(f"POI voltage CSV has no header: {path}")
        fields = {name.strip(): name for name in reader.fieldnames}
        time_field = fields.get("time_s") or fields.get("time") or fields.get("t")
        voltage_field = fields.get("poi_voltage_pu") or fields.get("voltage_pu") or fields.get("v_pu")
        if time_field is None or voltage_field is None:
            raise RuntimeError(
                f"{path} must contain time_s/time/t and poi_voltage_pu/voltage_pu/v_pu columns."
            )
        series = []
        for row in reader:
            try:
                series.append((float(row[time_field]), float(row[voltage_field])))
            except (TypeError, ValueError):
                continue
    if not series:
        raise RuntimeError(f"No numeric POI voltage samples found in {path}")
    return series


def build_plan(
    args: argparse.Namespace,
    gridpack_path: str | None,
    input_xml: Path,
    watch_csv: Path,
    raw_case: Path,
    dyr_case: Path,
    watch_generators: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    raw_summary_full = summarize_raw(raw_case) if raw_case.exists() else {}
    raw_summary = {
        key: value
        for key, value in raw_summary_full.items()
        if key not in {"online_generators", "online_branches"}
    }
    return {
        "transmission_backend": "GridPACK",
        "distribution_backend": "OpenDSSDirect.py",
        "federation_layer": "HELICS",
        "gridpack_executable": gridpack_path,
        "gridpack_application": "dynamic_simulation_full_y/dsf.x",
        "gridpack_input_xml": str(input_xml),
        "gridpack_case_origin": "travis150_updated_real_raw_dyr",
        "raw_case": str(raw_case),
        "dyr_case": str(dyr_case),
        "gridpack_watch_csv": str(watch_csv),
        "gridpack_poi_voltage_csv": str(args.gridpack_poi_voltage_csv) if args.gridpack_poi_voltage_csv else None,
        "poi_bus": args.poi_bus,
        "fault_branch": args.fault_branch,
        "event_csv": str(args.event_csv),
        "federation_plan": str(args.federation_plan),
        "output_dir": str(args.output_dir),
        "scenarios": [td.canonical_scenario(scenario) for scenario in args.scenarios],
        "raw_summary": raw_summary,
        "watch_generators": watch_generators or [],
        "executed": False,
        "note": (
            "Uses the real Travis150-updated RAW/DYR transmission model in GridPACK. "
            "If no GridPACK POI voltage CSV is supplied, HELICS uses the retained "
            "sag-train fallback only as a coupling demo because stock dsf.x does not "
            "emit a bus-voltage recorder CSV. Manuscript Fig. 6 uses exported "
            "GridPACK branch-fault POI traces."
        ),
    }


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.write_event_csv or args.execute:
        td.write_event_csv(args.event_csv)

    gridpack_path = resolve_executable(args.gridpack_exe)
    input_xml = args.gridpack_input or (args.output_dir / DEFAULT_GRIDPACK_INPUT)
    watch_csv = args.gridpack_watch_csv or (args.output_dir / DEFAULT_WATCH_FILE)

    if not args.raw.exists():
        print(f"RAW case does not exist: {args.raw}", file=sys.stderr)
        return 2
    if not args.dyr.exists():
        print(f"DYR case does not exist: {args.dyr}", file=sys.stderr)
        return 2

    raw_case, dyr_case = prepare_gridpack_case_files(args.raw, args.dyr, args.output_dir)
    watch_generators = write_gridpack_input(input_xml, raw_case, dyr_case, watch_csv, args)
    plan = build_plan(args, gridpack_path, input_xml, watch_csv, raw_case, dyr_case, watch_generators)

    if args.check_only or not args.execute:
        print(json.dumps(plan, indent=2))
        if args.check_only and gridpack_path is None:
            print("GridPACK dsf.x was not found; build GridPACK or pass --gridpack-exe.", file=sys.stderr)
        return 0

    if not args.skip_gridpack and gridpack_path is None:
        (args.output_dir / "run_manifest.json").write_text(json.dumps(plan | {"blocked_reason": "missing_gridpack_executable"}, indent=2) + "\n")
        print("Cannot run GridPACK: dsf.x was not found.", file=sys.stderr)
        return 2

    try:
        h, dss = td.load_optional_modules()
    except RuntimeError as exc:
        plan["blocked_reason"] = str(exc)
        (args.output_dir / "run_manifest.json").write_text(json.dumps(plan, indent=2) + "\n")
        print(str(exc), file=sys.stderr)
        return 2

    if not args.skip_gridpack:
        completed = run_gridpack(args, str(gridpack_path), input_xml)
        (args.output_dir / "gridpack_stdout.log").write_text(completed.stdout)
        (args.output_dir / "gridpack_stderr.log").write_text(completed.stderr)
        plan["gridpack_returncode"] = completed.returncode
        if completed.returncode != 0:
            (args.output_dir / "run_manifest.json").write_text(json.dumps(plan, indent=2) + "\n")
            print(f"GridPACK failed with exit code {completed.returncode}. See {args.output_dir}", file=sys.stderr)
            return completed.returncode

    if args.gridpack_poi_voltage_csv is not None:
        series = read_poi_voltage_csv(args.gridpack_poi_voltage_csv)
        plan["poi_voltage_source"] = "gridpack_poi_voltage_csv"
    elif args.require_gridpack_poi_voltage:
        plan["blocked_reason"] = "missing_gridpack_poi_voltage_csv"
        (args.output_dir / "run_manifest.json").write_text(json.dumps(plan, indent=2) + "\n")
        print("--require-gridpack-poi-voltage was set but no --gridpack-poi-voltage-csv was supplied.", file=sys.stderr)
        return 2
    else:
        series = td.event_inspired_voltage_series(args.recorder_period_s)
        plan["poi_voltage_source"] = "retained_sag_train_fallback_after_gridpack_execution"

    poi_series_path = args.output_dir / "gridpack_poi_voltage_timeseries.csv"
    td.write_poi_series(poi_series_path, series, "gridpack_travis150_poi_voltage_pu")

    all_rows: list[dict[str, float | bool | str]] = []
    for scenario in args.scenarios:
        all_rows.extend(td.run_helics_opendss_scenario(h, dss, scenario, series, args))
    h.helicsCloseLibrary()

    timeseries_path = args.output_dir / "helics_opendss_dynamic_var_timeseries.csv"
    summary_path = args.output_dir / "helics_opendss_dynamic_var_summary.csv"
    manifest_path = args.output_dir / "run_manifest.json"
    td.write_rows(timeseries_path, all_rows)
    summary = td.summarize_rows(all_rows)
    td.write_summary(summary_path, summary)

    plan["executed"] = True
    plan["timeseries_csv"] = str(timeseries_path)
    plan["summary_csv"] = str(summary_path)
    plan["poi_voltage_timeseries_csv"] = str(poi_series_path)
    plan["gridpack_voltage_samples"] = len(series)
    plan["tool_versions"] = {
        "helics": h.helicsGetVersion(),
        "opendssdirect": getattr(dss, "__version__", "unknown"),
    }
    manifest_path.write_text(json.dumps(plan, indent=2) + "\n")

    print(json.dumps({"manifest": str(manifest_path), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
