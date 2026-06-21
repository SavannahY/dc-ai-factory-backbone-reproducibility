# GridDyn T&D Dynamic VAR Co-Simulation

This directory is the GridDyn-backed follow-on path for the voltage-dip and
dynamic VAR study. The current CSV outputs in `data/texas_td_*` are still the
Texas screening outputs; the executed GridDyn/HELICS/OpenDSS demo outputs are
kept separately under `results/`.

Use this path when the transmission side must be a dynamic simulator:

```bash
python scripts/run_griddyn_td_dynamic_var.py \
  --griddyn-exe /path/to/gridDynMain \
  --travis-case Travis150/Travis150_Electric_Data.aux \
  --execute
```

With `--travis-case`, the executable demo writes a Travis-derived two-bus
GridDyn proxy from the selected electric corridor, runs GridDyn to validate that
proxy topology, publishes the documented event-inspired POI voltage series
through HELICS and solves a small OpenDSS data-center feeder for the three
greenfield data-center configurations:

- C1: traditional AC service ending at 480 V AC.
- C2: AC corridor plus SST with local 34.5 kV dynamic VAR support.
- C3: bipolar DC corridor with centralized 138 kV AC-side support and an 800 V
  DC ride-through boundary.

Stored local result:

- Manifest: `results/run_manifest.json`
- GridDyn proxy case: `results/griddyn_travis150_proxy_case.xml`
- GridDyn proxy recorder: `results/griddyn_travis150_proxy_recorder.csv`
- HELICS/OpenDSS time series: `results/helics_opendss_dynamic_var_timeseries.csv`
- Summary: `results/helics_opendss_dynamic_var_summary.csv`
- Minimum HELICS POI voltage: 0.250 pu at 79.20 s
- C1 minimum load-boundary voltage: 0.241 pu at the 480 V AC boundary; data
  center trips.
- C2 minimum load-boundary voltage: 0.241 pu at the 800 V DC SST boundary; data
  center trips in this severe uncoordinated local-support demo.
- C3 minimum OpenDSS AC-side voltage: 0.241 pu, but the modeled DC buffer holds
  the 800 V DC load boundary at 1.0 pu and the data center does not trip.

Pass `--griddyn-case` and `--poi-voltage-field` to run an IEEE 118 or Texas A&M
150-bus dynamic GridDyn case when that data is available.

The script still accepts the older aliases `baseline`, `local_34p5kv` and
`central_138kv`; these map to C1, C2 and C3 respectively. If `--travis-case` is
omitted, the script falls back to GridDyn's bundled IEEE 39 dynamic example as a
smoke test.

The shared disturbance is `eastern_interconnection_2024_voltage_sag_train.csv`.
It is an event-inspired sag train, not a reconstruction of the July 10, 2024
disturbance.
