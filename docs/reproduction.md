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

To regenerate the final two-panel Fig. 3, the full harmonic robustness sweep,
Supplementary Figs. S5-S6 and the supporting CSV tables, run:

```bash
python scripts/harmonic_robustness_sweep.py
```

This sweep evaluates 3,072 input-grid points and 9,216 architecture cases across
campus count, cluster load, voltage class, short-circuit ratio, phase coherence
and corridor length.

The complete manuscript-package generator is `scripts/build_dc_backbone_v3.py`.
It is retained for auditability and can be used to rebuild the full manuscript
package in an environment with the dependencies listed in `requirements.txt`.
