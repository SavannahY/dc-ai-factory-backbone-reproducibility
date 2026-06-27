# GridPACK T&D Dynamic VAR Co-Simulation

This directory is the GridPACK-backed path for the Travis 150 voltage-dip and
dynamic VAR study. It replaces the earlier GridDyn fallback with the real
`Travis150-updated/150.RAW` transmission case and the GridPACK-ready DYR file.

Use this path when GridPACK is available:

```bash
python scripts/run_gridpack_td_dynamic_var.py \
  --gridpack-exe /path/to/dsf.x \
  --execute
```

The runner writes `results/gridpack_travis150_dynamic_input.xml`, copies the RAW
and DYR files into `results/`, runs GridPACK `dsf.x`, then exchanges the POI
voltage series through HELICS with the OpenDSS data-center feeder scenarios:

- C1: traditional AC service ending at 480 V AC.
- C2: AC corridor plus SST with local 34.5 kV dynamic VAR support.
- C3: bipolar DC corridor with centralized AC-side support and an 800 V DC
  ride-through boundary.

The manuscript Fig. 6c result is the archived event sweep in
`results_event_sweep/`. It contains six shifted 3 s branch-fault simulations on
the 137-150 branch, bus 150 as the POI observation, and 20 ms GridPACK POI
voltage traces passed to the HELICS/OpenDSS feeder. The compact summary is:

- `results_event_sweep/event_sweep_summary_compact.csv`

The lowest POI minimum is 0.091994 pu. C1 and C2 trip in the OpenDSS
data-center federation; C3 keeps the modeled 800 VDC load boundary served
through the centralized AC/DC-terminal and DC-buffer representation.

GridPACK's stock `dsf.x` writes generator watch files. The helper
`scripts/run_gridpack_observation_driver.py` uses the GridPACK Python
observation API to export the bus-150 POI voltage traces used by the archived
event sweep.

Check the configuration without running:

```bash
python scripts/run_gridpack_td_dynamic_var.py --check-only
```

Single-event result files:

- Manifest: `results/run_manifest.json`
- GridPACK input: `results/gridpack_travis150_dynamic_input.xml`
- GridPACK generator watch: `results/gridpack_travis150_generator_watch.csv`
- POI voltage time series: `results/gridpack_poi_voltage_timeseries.csv`
- HELICS/OpenDSS time series: `results/helics_opendss_dynamic_var_timeseries.csv`
- Summary: `results/helics_opendss_dynamic_var_summary.csv`

Event-sweep result files:

- Compact summary: `results_event_sweep/event_sweep_summary_compact.csv`
- POI traces: `results_event_sweep/gridpack_poi_voltage_event_*.csv`
- Per-event coupling summaries:
  `results_event_sweep/event_*/helics_opendss_dynamic_var_summary.csv`
