This repository is structured for public release. To regenerate the archived
OpenDSS Fig. 3 diagnostic, Fig. 4 and Fig. 5 from archived CSV outputs, run:

```bash
python scripts/reproduce_all.py
```

The script writes the diagnostic Fig. 3, Fig. 4 and Fig. 5 to
`reproduced/figures`.
OpenDSSDirect.py harmonic-run artifacts are archived under `opendss/` and
`data/true_opendss_*`. To rerun OpenDSS in a local environment with
OpenDSSDirect.py installed, run:

```bash
python scripts/run_true_opendss.py
```

To regenerate the dynamic robustness grid used for the Fig. 4 fluctuation and
voltage envelopes, run:

```bash
python scripts/dynamic_robustness_sweep.py
```

To regenerate the harmonic robustness sweep, the supporting Fig. 3 screening
variant, Supplementary Figs. S5-S6 and the supporting CSV tables, run:

```bash
python scripts/harmonic_robustness_sweep.py
```

To regenerate the Texas T&D C0/C1/C2/C3 add-on study for transfer capacity,
efficiency, harmonics and dynamic voltage exposure, run:

```bash
python scripts/texas_td_c0_c2_c3_scenarios.py
```

The script uses the archived A/B screening catalogs by default. C0 and C1 are
treated as the same traditional 400 V AC facility-side architecture. To build
the main-dataset A corridor catalog from a downloaded Texas7k MATPOWER case,
pass `--texas7k-matpower path/to/case.m`. PowerWorld and PSS/E are not required
for this steady-state screening path. Distribution validation remains an OpenDSS
selected-feeder path; the full Texas OpenDSS dataset is intentionally not pulled
into the main transmission hosting-capacity loop.

To rank the Austin/Travis 150-bus validation corridors for conversion to a DC
line, run:

```bash
python scripts/travis150_dc_line_siting.py
```

This writes `data/travis150_dc_line_siting_candidates_v1.csv`,
`data/travis150_dc_line_siting_summary_v1.csv` and
`docs/travis150_dc_line_siting_study.md`. The ranking is a synthetic
bus-to-bus corridor screen, not a geospatial right-of-way route selection.

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

The HELICS GridDyn/OpenDSS protocol for a follow-on transmission-distribution
dynamic VAR study is documented in `docs/helics_td_dynamic_var_study.md`. It is
not part of the archived smoke-test command because it requires external
simulator installation and case-specific co-simulation setup.

To run the local executed demo after building GridDyn and installing HELICS plus
OpenDSSDirect.py in the Python environment, run:

```bash
python scripts/run_griddyn_td_dynamic_var.py \
  --griddyn-exe /path/to/gridDynMain \
  --travis-case Travis150/Travis150_Electric_Data.aux \
  --execute
```

The resulting manifest, GridDyn recorder, HELICS/OpenDSS time series and summary
CSV files are under `cosim/griddyn_td_dynamic_var/results/`. The default demo
uses a Travis-derived GridDyn proxy when `--travis-case` is supplied and labels
the three configurations as C1, C2 and C3; pass `--griddyn-case` and
`--poi-voltage-field` for a full IEEE 118 or Texas A&M 150-bus dynamic case.

The dynamic and harmonic sweeps each evaluate 3,072 input-grid points and 9,216
architecture cases across campus count, cluster load, voltage class,
short-circuit ratio, phase coherence and corridor length.

The complete manuscript-package generator is `scripts/build_dc_backbone_v3.py`.
It is retained for auditability and can be used to rebuild the full manuscript
package in an environment with the dependencies listed in `requirements.txt`.
