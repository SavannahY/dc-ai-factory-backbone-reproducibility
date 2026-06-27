# Legacy GridDyn T&D Dynamic VAR Fallback

This directory contains the optional GridDyn/HELICS/OpenDSS fallback inputs for
local coupling tests. It is not part of the manuscript evidence chain. Use
`cosim/gridpack_td_dynamic_var/` and `scripts/run_gridpack_td_dynamic_var.py`
for the Travis 150 result.

Use this path only for a local executable coupling smoke test:

```bash
python scripts/run_griddyn_td_dynamic_var.py \
  --griddyn-exe /path/to/gridDynMain \
  --travis-case Travis150/Travis150_Electric_Data.aux \
  --execute
```

With `--travis-case`, the runner writes a Travis-derived two-bus GridDyn
fallback case from the selected electric corridor, publishes a retained
sag-train POI voltage series through HELICS, and solves a small OpenDSS
data-center feeder for the three greenfield data-center configurations:

- C1: traditional AC service ending at 480 V AC.
- C2: AC corridor plus SST with local 34.5 kV dynamic VAR support.
- C3: bipolar DC corridor with centralized 138 kV AC-side support and an 800 V
  DC ride-through boundary.

The real Travis 150 dynamic-transmission workflow is the GridPACK path, which
uses `Travis150-updated/150.RAW` plus
`Travis150-updated/150_gridpack_REECA1_candidate.dyr`.

The script still accepts the older aliases `baseline`, `local_34p5kv` and
`central_138kv`; these map to C1, C2 and C3 respectively. If `--travis-case` is
omitted, the script falls back to GridDyn's bundled IEEE 39 example as a smoke
test.

The shared fallback disturbance is
`eastern_interconnection_2024_voltage_sag_train.csv`. It is a retained
sag-train replay for coupling tests, not a reconstruction of a real
disturbance.
