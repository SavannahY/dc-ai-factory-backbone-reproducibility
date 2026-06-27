This repository is structured for public release. To regenerate the archived
OpenDSS Fig. 3 diagnostic and Fig. 5 from archived CSV outputs, run:

```bash
python scripts/reproduce_all.py
```

The script writes the diagnostic Fig. 3 and Fig. 5 to
`reproduced/figures`.
OpenDSSDirect.py harmonic-run artifacts are archived under `opendss/` and
`data/true_opendss_*`. To rerun OpenDSS in a local environment with
OpenDSSDirect.py installed, run:

```bash
python scripts/run_true_opendss.py
```

To regenerate the supplemental dynamic robustness grid, run:

```bash
python scripts/dynamic_robustness_sweep.py
```

To regenerate the harmonic robustness sweep, the supporting Fig. 3 screening
variant and optional harmonic-robustness diagnostic outputs, run:

```bash
python scripts/harmonic_robustness_sweep.py
```

The optional diagnostic plots are written under `reproduced/figures` and are
not part of the final manuscript `figures/` folder.

To run the corrected greenfield Travis 150 data-center configuration study,
where C1, C2 and C3 are all new systems built to serve incremental data-center
load, run:

```bash
python scripts/travis150_greenfield_c1_c2_c3.py
```

This writes `data/travis150_greenfield_c1_c2_c3_transfer_v2.csv`,
`data/travis150_greenfield_c1_c2_c3_harmonics_v2.csv`,
`data/travis150_greenfield_c1_c2_c3_voltage_v2.csv`,
`data/travis150_greenfield_c1_c2_c3_summary_v2.csv` and
`docs/travis150_greenfield_data_center_config_study.md`. Pass
`--travis-case path/to/downloaded/travis150-electric-case.m` when the TAMU
electric case is available; otherwise the script uses the archived fallback
Austin/Travis flagship corridor `B_04` to `B_101`.

To run the real Travis 150 transmission path after building GridPACK and
installing HELICS plus OpenDSSDirect.py in the Python environment, run:

```bash
python scripts/run_gridpack_td_dynamic_var.py \
  --gridpack-exe /path/to/dsf.x \
  --execute
```

The single-event manifest, GridPACK input deck, generator watch file,
HELICS/OpenDSS time series and summary CSV files are under
`cosim/gridpack_td_dynamic_var/results/`. The default case is
`Travis150-updated/150.RAW` plus
`Travis150-updated/150_gridpack_REECA1_candidate.dyr`.

The manuscript Fig. 6c uses the archived event sweep under
`cosim/gridpack_td_dynamic_var/results_event_sweep/`. The compact source table
is `event_sweep_summary_compact.csv`; the six `gridpack_poi_voltage_event_*.csv`
files contain the shifted 3 s GridPACK bus-150 POI voltage traces passed to the
HELICS/OpenDSS federation at 20 ms resolution.

The dynamic and harmonic sweeps each evaluate 3,072 input-grid points and 9,216
architecture cases across campus count, cluster load, voltage class,
short-circuit ratio, phase coherence and corridor length.

The complete manuscript-package generator is `scripts/build_dc_backbone_v3.py`.
It rebuilds the Word manuscript, supplementary information, figures, source
data folder and public-code archive in an environment with the dependencies
listed in `requirements.txt`.
