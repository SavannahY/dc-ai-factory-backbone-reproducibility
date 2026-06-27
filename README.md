# Direct-current subtransmission backbones for grid-stable AI factories

This repository is the public reproducibility package for the manuscript
**"Direct-current subtransmission backbones for grid-stable AI factories."**

The scientific question is where the AC/DC boundary should sit when AI data
centers become clustered, synchronized and DC-native. Conventional planning
often treats a data center as a large passive AC load. The manuscript instead
tests an architecture-level claim: for multi-campus AI factory load pockets, a
utility-operated subtransmission DC backbone can make the AC/DC boundary a grid
planning variable, not only a building-level design choice.

## Scientific Overview

The study compares three architectures serving the same useful 800 VDC
data-center boundary:

1. **Traditional AC delivery (C1)**: AC remains in the subtransmission
   corridor and each campus is served through conventional 480 V AC facility
   distribution.
2. **Local solid-state transformer (SST)**: the AC corridor is retained, but
   each campus uses a medium-voltage SST interface.
3. **Subtransmission DC backbone**: one grid-facing AC/DC terminal feeds a
   bipolar DC corridor, with campus DC/DC stations stepping down to 34.5 kV DC
   and then to 800 VDC.

The analysis is deliberately not a single efficiency calculation. It evaluates
whether moving the first AC/DC boundary upstream co-locates three system-level
benefits:

- higher useful transfer capacity with lower corridor/conversion losses
  relative to traditional AC delivery;
- centralized AC harmonic ownership at one utility-operated terminal;
- reduced grid-side voltage modulation from synchronized AI-training loads and
  improved large-electronic-load voltage ride-through behavior.

The package includes archived CSV outputs, figure files, OpenDSS-compatible
harmonic cases, Python reproduction scripts and smoke tests for the key
ordering claims.

## Repository Structure

```text
data/        Archived CSV inputs and outputs used by the figures and tests.
figures/     Final manuscript and supplementary figures in PNG/SVG form.
scripts/     Figure-generation, robustness-sweep and optional OpenDSS runners.
src/         Small reusable model modules for efficiency, harmonics and dynamics.
opendss/     OpenDSS-compatible harmonic-network cases and run logs.
docs/        Reproduction notes, figure provenance and drafting disclosure.
references/ Numbered reference metadata only; downloaded PDFs are not tracked.
tests/       Pytest smoke tests for core numerical relationships.
```

Reference PDFs, Overleaf folders and journal submission packages are
intentionally excluded from the public repository. Some local reference copies
are restricted by publisher or standards-body terms and should not be
redistributed through GitHub.

## Figures And Data Map

| Manuscript item | Figure file | Main data files |
| --- | --- | --- |
| Fig. 1: delivery architectures | `figures/Figure_1_architecture.png` | supplied architecture diagram used consistently in Word, TeX and PDF |
| Fig. 2: useful transfer capacity | `figures/fig2_transfer_capacity_loss_designspace.{png,svg}` | `transfer_capacity_reference_case_v3.csv`, `transfer_capacity_uncertainty_reference_v3.csv`, `transfer_capacity_design_space_v3.csv`, `transfer_capacity_sensitivity_v3.csv` |
| Fig. 3: harmonic ownership | `figures/fig3_harmonic_ownership_opendss_screening.{png,svg}` | `harmonic_thdv_monte_carlo_v3.csv`, `harmonic_individual_p95_v3.csv`, `true_opendss_harmonic_thdv_monte_carlo_v3.csv` |
| Fig. 4: GridPACK voltage ride-through | `figures/fig4_voltage_control_turbulence_gridpack.{png,svg}` | `gridpack_voltage_turbulence_event_sweep_v3.csv`, `gridpack_voltage_control_event_response_v3.csv`, `gridpack_voltage_control_summary_v3.csv` |
| Fig. 5: load-pocket context | `figures/fig5_case_study_voltage_envelope.{png,svg}` | `cost_copper_envelope_v3.csv`, `assumption_provenance_table_v3.csv` |
| Fig. 6: Travis 150 validation | `figures/fig6_travis150_greenfield_benefits.{png,svg,pdf}` | `travis150_greenfield_c1_c2_c3_summary_v2.csv`, `event_sweep_summary_compact.csv`, `gridpack_poi_voltage_event_*.csv` |
| Austin/Travis greenfield data-center configurations | `docs/travis150_greenfield_data_center_config_study.md` | `travis150_greenfield_c1_c2_c3_transfer_v2.csv`, `travis150_greenfield_c1_c2_c3_harmonics_v2.csv`, `travis150_greenfield_c1_c2_c3_voltage_v2.csv`, `travis150_greenfield_c1_c2_c3_summary_v2.csv` |
| Supplementary Figs. S1-S4 | `figures/supp_fig_s*.{png,svg}` | fault-protection, EMT-validation, buffer-feasibility and cost/copper CSVs |

The final figure provenance is summarized in
`docs/figure_provenance.md`. No final figure in this reproducibility package is
a generative-AI image, stock image, screenshot collage or manually edited
bitmap; the distributed figures are programmatic Matplotlib exports.

## Quick Validation

Create an environment with the packages in `requirements.txt`, then run:

```bash
python -m pytest -q
shasum -c SHA256SUMS.txt
```

The tests check the key archived numerical relationships:

- DC backbone and local SST efficiency exceed traditional AC in the reference
  case.
- Harmonic THD ordering is traditional AC > local SST > DC backbone.
- Dynamic grid-side fluctuation metrics are lower for the DC backbone than for
  local SST or traditional AC.
- Robustness-grid summaries preserve the same architectural ordering.

`SHA256SUMS.txt` and `MANIFEST_SHA256.csv` provide file-level integrity checks
for the public repository contents.

## Reproducing Results

Fast figure regeneration from archived CSV outputs:

```bash
python scripts/reproduce_all.py
```

This writes regenerated diagnostic figures into `reproduced/figures/`, which is
ignored by Git because it is a derived-output directory.

Full dynamic robustness grid:

```bash
python scripts/dynamic_robustness_sweep.py
```

Full harmonic robustness grid and supporting harmonic figures:

```bash
python scripts/harmonic_robustness_sweep.py
```

Austin/Travis 150-bus greenfield data-center configuration screen:

```bash
python scripts/travis150_greenfield_c1_c2_c3.py
```

The HELICS validation protocol for voltage-dip and dynamic VAR co-simulation is
documented in `docs/helics_td_dynamic_var_study.md`. It now describes a
GridPACK transmission federate using the real Travis 150 RAW/DYR case, an
OpenDSS/PyDSS distribution federate, and local versus centralized
voltage-support controller cases. The archived smoke tests do not require those
external simulators.

GridPACK-backed Travis 150 voltage-dip study:

```bash
python scripts/run_gridpack_td_dynamic_var.py \
  --gridpack-exe /path/to/dsf.x \
  --execute
```

Optional OpenDSS check:

```bash
python scripts/run_opendss_if_available.py
```

The optional OpenDSS step requires `opendssdirect.py`. The repository already
contains archived OpenDSS-compatible cases and run artifacts under `opendss/`
and `data/true_opendss_*`, so OpenDSS is not required for the smoke tests.

## What To Inspect First

For a quick scientific review, start with:

1. `figures/Figure_1_architecture.png` for the architectural claim.
2. `figures/fig2_transfer_capacity_loss_designspace.png` for useful transfer
   capacity, loss reduction and uncertainty.
3. `figures/fig3_harmonic_ownership_opendss_screening.png` for harmonic
   ownership.
4. `figures/fig4_voltage_control_turbulence_gridpack.png` for GridPACK
   voltage ride-through.
5. `tests/test_reproduction_outputs.py` for the core falsifiable relationships.
6. `docs/reproduction.md` for a concise reproduction guide.
7. `references/references.md` for the numbered scientific reference list.

## Scope And Limitations

The models are architecture-level screening models. They are intended to make a
systems claim falsifiable, not to replace site-specific protection design,
project-specific IEEE 519 studies, switching EMT validation or utility
interconnection studies. The Travis 150 dynamic result used in the manuscript
is a synthetic GridPACK branch-fault event sweep, not a site-selection study or
reconstruction of a real disturbance. DC protection, grounding, insulation
coordination, converter interoperability, detailed HELICS T&D co-simulation and
hardware-in-the-loop validation remain required before any deployment claim.

The study therefore asks a planning question rather than proposing a finished
equipment design: if a clustered AI load is served by an upstream DC boundary,
do losses, harmonic ownership and grid-side dynamic exposure move in the same
favorable direction relative to architectures that keep AC in the corridor?

## Citation

See `CITATION.cff`. This repository is structured for GitHub release and Zenodo
deposition.
