# Figure provenance

All manuscript and supplementary figures in this reproducibility package are
programmatic outputs from `scripts/build_dc_backbone_v3.py` or from the archived
CSV outputs under `data/`.

No final manuscript figure is a generative-AI image, stock image, screenshot
collage or manually edited bitmap. Fig. 1 is the supplied architecture PNG used
consistently in Word, TeX and PDF. The other distributed PNG, SVG and PDF files
are Matplotlib exports. The SVG files can be inspected as vector graphics.
`scripts/reproduce_all.py` regenerates the archived Fig. 3 diagnostic and Fig. 5
from source CSV files as a fast submission check.
`scripts/dynamic_robustness_sweep.py` regenerates a supplemental dynamic
screening grid and supporting CSV tables.
`scripts/harmonic_robustness_sweep.py` regenerates the harmonic robustness
screening figures and the supporting CSV tables.
`scripts/travis150_greenfield_c1_c2_c3.py` and
`scripts/run_gridpack_td_dynamic_var.py` provide the Travis 150 greenfield and
GridPACK/HELICS/OpenDSS workflow used for Figs. 4 and 6. Fig. 4 and panel 6c are generated from
`cosim/gridpack_td_dynamic_var/results_event_sweep/event_sweep_summary_compact.csv`
and the six `gridpack_poi_voltage_event_*.csv` bus-150 POI traces.

Final figure files:

- Fig. 1: `figures/Figure_1_architecture.png`
- Fig. 2: `figures/fig2_transfer_capacity_loss_designspace_v3.{png,svg}`
- Fig. 3: `figures/fig3_harmonic_ownership_opendss_screening_v3.{png,svg}`
- Fig. 4: `figures/fig4_voltage_control_turbulence_gridpack_v3.{png,svg}`
- Fig. 5: `figures/fig5_case_study_voltage_envelope_v3.{png,svg}`
- Fig. 6: `figures/fig6_travis150_greenfield_benefits_v2.{png,svg,pdf}`
- Supplementary Fig. S1: `figures/supp_fig_s1_dc_fault_protection_dynamic_v3.{png,svg}`
- Supplementary Fig. S2: `figures/supp_fig_s2_averaged_emt_validation_v3.{png,svg}`
- Supplementary Fig. S3: `figures/supp_fig_s3_buffer_feasibility_v3.{png,svg}`
- Supplementary Fig. S4: `figures/supp_fig_s4_cost_copper_envelope_v3.{png,svg}`
