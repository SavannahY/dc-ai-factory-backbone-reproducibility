This repository is structured for public release. To regenerate the two
highest-risk manuscript figures from archived CSV outputs, run:

```bash
python scripts/reproduce_all.py
```

The script writes Fig. 3 and Fig. 4 to `reproduced/figures`. OpenDSSDirect.py
harmonic-run artifacts are archived under `opendss/` and
`data/true_opendss_*`. To rerun OpenDSS in a local environment with
OpenDSSDirect.py installed, run:

```bash
python scripts/run_true_opendss.py
```

The complete manuscript-package generator is `scripts/build_dc_backbone_v3.py`.
It is retained for auditability and can be used to rebuild the full manuscript
package in an environment with the dependencies listed in `requirements.txt`.
