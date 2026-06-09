# Direct-current subtransmission backbones for grid-stable AI factories

This repository contains the data, screening models, figures and OpenDSS-compatible files for the manuscript
"Direct-current subtransmission backbones for grid-stable AI factories".

## Contents
- `data/`: CSV inputs and outputs for all manuscript and supplementary figures.
- `figures/`: publication figures in PNG/SVG form.
- `src/ai_dc_backbone/`: reusable Python model modules.
- `scripts/`: reproduction helpers, reproducibility audit, and optional OpenDSS runner.
- `opendss/`: OpenDSS-compatible harmonic network files.
- `tests/`: model-invariant and archived-data regression tests used by CI.
- `docs/`: reproduction notes, figure provenance, AI disclosure language, and publication-risk review material.

## Reproducing results
```bash
python scripts/reproduce_all.py
python scripts/dynamic_robustness_sweep.py
python scripts/harmonic_robustness_sweep.py
python scripts/run_opendss_if_available.py  # optional, requires opendssdirect.py
```

`scripts/reproduce_all.py` regenerates the archived OpenDSS Fig. 3 diagnostic,
Fig. 4 and Fig. 5 from archived CSV outputs into `reproduced/figures`.
`scripts/dynamic_robustness_sweep.py` regenerates the full dynamic scenario grid
used for the Fig. 4 fluctuation and voltage envelopes.
`scripts/harmonic_robustness_sweep.py` regenerates the final two-panel Fig. 3
and the full harmonic robustness grid across campus count, cluster load, voltage
class, short-circuit ratio, phase coherence and corridor length. The manuscript
figures were generated with transparent Python models. The broader robustness
envelopes are archived as CSV tables under `data/` and, for harmonics, as
Supplementary Figs. S5-S6.
OpenDSS circuit files and the run log are included under `opendss/`.

## Fast validation before submission
```bash
pytest -q
python scripts/audit_reproducibility.py
```

The tests check the core model primitives, reference-case regression values,
archived dynamic/harmonic scenario summaries, and consistency between the
archived direct OpenDSS run log and CSV outputs. The audit script checks the DOI
manifest hashes and the claim-level rank orderings that the manuscript depends
on. For a release candidate, run:

```bash
python scripts/audit_reproducibility.py --strict
```

`--strict` also fails when release-like source/data files are missing from
`MANIFEST_SHA256.csv`; regenerate the manifest after final file changes.

## Publication-readiness notes
The repository supports an architecture-level screening claim, not a final
hardware design. Before journal submission, review:

- `docs/methodological_risk_register.md` for reviewer-facing risk boundaries.
- `docs/reproduction.md` for the complete reproduction sequence.
- `docs/figure_provenance.md` for figure-generation provenance.
- `docs/ai_assisted_drafting_disclosure.md` for disclosure language that must be approved by all authors.

Core guardrail: the manuscript should say that the DC-backbone architecture
centralizes AC harmonic ownership and reduces screening-level dynamic exposure
under stated assumptions. It should not claim site-specific IEEE 519 compliance,
validated DC protection, insulation coordination, or a completed capital-cost
case.

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
