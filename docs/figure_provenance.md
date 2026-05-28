# Figure provenance

All manuscript and supplementary figures in this reproducibility package are
programmatic outputs from `scripts/build_dc_backbone_v3.py` or from the archived
CSV outputs under `data/`.

No final manuscript figure is a generative-AI image, photo-realistic rendering,
stock image, screenshot collage or manually edited bitmap. The distributed PNG,
SVG and PDF files are Matplotlib exports. The SVG files can be inspected as
vector graphics. `scripts/reproduce_all.py` regenerates the archived OpenDSS
Fig. 3 diagnostic and Fig. 4 from source CSV files as a fast submission check.
`scripts/harmonic_robustness_sweep.py` regenerates the final two-panel Fig. 3,
the harmonic robustness screening figures and the supporting CSV tables.

Final figure files:

- Fig. 1: `figures/fig1_architecture_formal_v3.{png,svg}`
- Fig. 2: `figures/fig2_efficiency_uncertainty_designspace_v3.{png,svg}`
- Fig. 3: `figures/fig3_harmonic_two_panel_screening_v3.{png,svg}`
- Fig. 4: `figures/fig4_voltage_stabilization_averaged_emt_v3.{png,svg}`
- Fig. 5: `figures/fig5_case_study_voltage_envelope_v3.{png,svg}`
- Supplementary Fig. S1: `figures/supp_fig_s1_dc_fault_protection_dynamic_v3.{png,svg}`
- Supplementary Fig. S2: `figures/supp_fig_s2_averaged_emt_validation_v3.{png,svg}`
- Supplementary Fig. S3: `figures/supp_fig_s3_buffer_feasibility_v3.{png,svg}`
- Supplementary Fig. S4: `figures/supp_fig_s4_cost_copper_envelope_v3.{png,svg}`
- Supplementary Fig. S5: `figures/supp_fig_s5_harmonic_robustness_envelope_v3.{png,svg}`
- Supplementary Fig. S6: `figures/supp_fig_s6_harmonic_sourcecount_phase_sensitivity_v3.{png,svg}`
