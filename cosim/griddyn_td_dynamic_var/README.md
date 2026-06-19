# GridDyn T&D Dynamic VAR Co-Simulation

This directory is the GridDyn-backed follow-on path for the voltage-dip and
dynamic VAR study. The current CSV outputs in `data/texas_td_*` are still the
Texas screening outputs; the executed GridDyn/HELICS/OpenDSS demo outputs are
kept separately under `results/`.

Use this path when the transmission side must be a dynamic simulator:

```bash
python scripts/run_griddyn_td_dynamic_var.py \
  --griddyn-exe /path/to/gridDynMain \
  --execute
```

The default executable demo writes a repeated-fault IEEE 39 GridDyn case, runs
GridDyn, publishes the selected GridDyn POI voltage through HELICS and solves a
small OpenDSS data-center feeder with baseline, local 34.5 kV VAR and
centralized 138 kV VAR support cases.

Stored local result:

- Manifest: `results/run_manifest.json`
- GridDyn recorder: `results/griddyn_ieee39_repeated_fault_recorder.csv`
- HELICS/OpenDSS time series: `results/helics_opendss_dynamic_var_timeseries.csv`
- Summary: `results/helics_opendss_dynamic_var_summary.csv`
- Minimum POI voltage: 0.325 pu at 62.86 s
- Minimum data-center AC voltage: 0.313 pu baseline, 0.322 pu with local or
  centralized 120 Mvar support
- AC-side trip flag: true in all three cases for this severe event

Pass `--griddyn-case` and `--poi-voltage-field` to run an IEEE 118 or Texas A&M
150-bus dynamic GridDyn case when that data is available.

Study cases:

- Baseline: no added dynamic VAR support.
- Local: SST plus local dynamic VAR support at the 34.5 kV AC side.
- Local plus legacy devices: local support with LTCs, regulators and capacitor
  banks enabled.
- Centralized: voltage support at the 115/138 kV data-center interconnection.
- Coordinated combined sensitivity: local and centralized controls with
  explicit deadbands, delays and priority rules.

The shared disturbance is `eastern_interconnection_2024_voltage_sag_train.csv`.
It is an event-inspired sag train, not a reconstruction of the July 10, 2024
disturbance.
