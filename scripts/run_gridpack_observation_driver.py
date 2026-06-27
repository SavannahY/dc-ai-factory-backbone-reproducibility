#!/usr/bin/env python3
"""Run GridPACK through its Python wrapper and write observed POI voltage.

This script is intended to run inside the official GridPACK container. It uses
the same XML input deck as ``dsf2.x``, but drives ``DSFullApp`` one timestep at a
time so bus-voltage observations can be written to CSV for downstream T&D
coupling.
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import gridpack  # type: ignore
from gridpack.dynamic_simulation import DSFullApp  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-xml", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--poi-bus", type=int, default=150)
    parser.add_argument("--sample-period-s", type=float, default=0.02)
    parser.add_argument("--event-index", type=int, default=0, help="Zero-based XML faultEvent index to run.")
    parser.add_argument(
        "--shift-event-start-s",
        type=float,
        default=None,
        help="Optionally shift the selected fault event to this start time while preserving duration.",
    )
    parser.add_argument("--final-time-s", type=float, default=None, help="Optional dynamic simulation stop time.")
    parser.add_argument("--rank", type=int, default=-1)
    return parser.parse_args()


def selected_fault_event(input_xml: Path, event_index: int, shifted_start_s: float | None):
    from gridpack.dynamic_simulation import Event  # type: ignore

    root = ET.parse(input_xml).getroot()
    events = root.findall(".//Dynamic_simulation/Events/faultEvent")
    if not events:
        raise RuntimeError(f"No Dynamic_simulation/Events/faultEvent entries found in {input_xml}")
    if event_index < 0 or event_index >= len(events):
        raise RuntimeError(f"--event-index {event_index} is outside 0..{len(events) - 1}")

    elem = events[event_index]
    start = float((elem.findtext("beginFault") or "").strip())
    end = float((elem.findtext("endFault") or "").strip())
    step = float((elem.findtext("timeStep") or "").strip())
    branch = (elem.findtext("faultBranch") or "").strip().split()
    if len(branch) < 2:
        raise RuntimeError(f"faultEvent {event_index} does not define a two-bus faultBranch")
    if shifted_start_s is not None:
        duration = end - start
        start = shifted_start_s
        end = shifted_start_s + duration

    event = Event()
    event.start = start
    event.end = end
    event.step = step
    event.isBus = False
    event.isLine = True
    event.from_idx = int(branch[0])
    event.to_idx = int(branch[1])
    return event


def main() -> int:
    args = parse_args()
    input_xml = args.input_xml.resolve()
    output_csv = args.output_csv.resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    os.chdir(input_xml.parent)

    gridpack.NoPrint().setStatus(True)
    env = gridpack.Environment()
    _comm = gridpack.Communicator()

    ds_app = DSFullApp()
    ds_app.solvePowerFlowBeforeDynSimu(str(input_xml), args.rank)

    config = gridpack.Configuration()
    config.open(str(input_xml), _comm)
    cursor = config.getCursor("Configuration.Dynamic_simulation")

    ds_app.readGenerators(args.rank)
    ds_app.readSequenceData()
    ds_app.initialize()
    ds_app.setGeneratorWatch()
    ds_app.setObservations(cursor)
    if args.final_time_s is not None:
        ds_app.setFinalTime(float(args.final_time_s))
    event = selected_fault_event(input_xml, args.event_index, args.shift_event_start_s)
    ds_app.solvePreInitialize(event)

    obs_gen_bus, obs_gen_ids, obs_load_buses, obs_load_ids, obs_bus_ids = ds_app.getObservationLists()
    obs_bus_ids = list(obs_bus_ids)
    if args.poi_bus not in obs_bus_ids:
        raise RuntimeError(f"POI bus {args.poi_bus} is not in observed buses: {obs_bus_ids}")
    poi_idx = obs_bus_ids.index(args.poi_bus)

    dt = float(ds_app.getTimeStep())
    sample_every = max(1, round(args.sample_period_s / dt))
    rows: list[tuple[float, float, float]] = []
    step = 0
    while not ds_app.isDynSimuDone():
        ds_app.executeOneSimuStep()
        if step % sample_every == 0:
            v_mag, v_ang, r_spd, r_ang, gen_p, gen_q, load_online = ds_app.getObservations()
            rows.append((step * dt, float(v_mag[poi_idx]), float(v_ang[poi_idx])))
        step += 1

    with output_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "poi_voltage_pu", "poi_angle_rad", "poi_bus"])
        for time_s, voltage_pu, angle_rad in rows:
            writer.writerow([f"{time_s:.6f}", f"{voltage_pu:.8f}", f"{angle_rad:.8f}", args.poi_bus])

    # Release C++ objects in an order that avoids MPI finalization warnings.
    del ds_app
    del _comm
    del env
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
