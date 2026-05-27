
# Direct-current subtransmission backbones for grid-stable AI factories

This repository contains the data, screening models, figures and OpenDSS-compatible files for the manuscript
"Direct-current subtransmission backbones for grid-stable AI factories".

## Contents
- `data/`: CSV inputs and outputs for all manuscript and supplementary figures.
- `figures/`: publication figures in PNG/SVG form.
- `src/ai_dc_backbone/`: reusable Python model modules.
- `scripts/`: reproduction helpers and optional OpenDSS runner.
- `opendss/`: OpenDSS-compatible harmonic network files.

## Reproducing results
```bash
python scripts/reproduce_all.py
python scripts/run_opendss_if_available.py  # optional, requires opendssdirect.py
```

`scripts/reproduce_all.py` regenerates Fig. 3 and Fig. 4 from the archived CSV
outputs into `reproduced/figures`. The manuscript figures were generated with
transparent Python models. Fig. 3 includes direct OpenDSSDirect.py harmonic-run
artifacts and an internal nodal-frequency solver check. OpenDSS circuit files
and the run log are included under `opendss/`.

## Citation
See `CITATION.cff`. This repository is structured for GitHub release and Zenodo deposition.

## Figure and drafting provenance
- Figure provenance is documented in `docs/figure_provenance.md`.
- AI-assisted drafting disclosure language is provided in
  `docs/ai_assisted_drafting_disclosure.md`.

## Direct OpenDSS check
This repository includes `scripts/run_true_opendss.py`,
`opendss/true_opendss_harmonic_network_v3.dss`, and the resulting
`data/true_opendss_*` CSV files.
