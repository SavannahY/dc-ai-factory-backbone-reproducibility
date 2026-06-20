# Austin/Travis 150-bus DC Line Siting Screen

This note ranks candidate subtransmission corridors in the archived
Austin/Travis 150-bus Texas T&D validation case for conversion to the
C3 subtransmission DC-backbone architecture.

## Inputs

- Corridor catalog: `data/texas_td_corridor_catalog_v1.csv`, dataset B.
- Scenario outputs: `data/texas_td_c0_c2_c3_hosting_capacity_v1.csv`,
  `data/texas_td_c0_c2_c3_harmonics_v1.csv`, and
  `data/texas_td_c0_c2_c3_voltage_dynamics_v1.csv`.
- Scenarios compared: C0/C1 traditional 400 V AC delivery, C2 local SST
  with 34.5 kV-side local VAR support, and C3 converted DC backbone with
  115/138 kV-side centralized AC support.

The result is a corridor-level planning screen, not a parcel-level route
selection. The repository has synthetic bus spans and electrical
attributes for these four Austin/Travis validation corridors, but it does
not contain geospatial right-of-way data for final route engineering.

## Result

Top ranked candidate: `ATX-230-138-04` from `B_04 to B_101`.
It reaches 1049.39 MW in the C3 screen,
14.30% above C0 and
7.65% above C2.

| Rank | Corridor | Synthetic bus span | C3 transfer MW | C3 vs C0 transfer % | C3 vs C2 transfer % | C3 vs C0 eff pct-pt | THDv reduction vs C0 % | Voltage-deviation reduction vs C0 % | Interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ATX-230-138-04 | B_04 to B_101 | 1049.39 | 14.30 | 7.65 | 1.24 | 94.97 | 87.25 | best first build: highest C3 transfer, strongest source and clear C3 gain over local SST |
| 2 | ATX-138-02 | B_18 to B_64 | 899.18 | 23.41 | 4.18 | 1.24 | 95.27 | 87.25 | good candidate: C3 adds transfer beyond local SST and keeps harmonic and dynamic benefits |
| 3 | ATX-138-03 | B_21 to B_83 | 819.93 | 31.59 | 0.00 | 1.34 | 95.17 | 87.25 | relief candidate: large gain over traditional AC, but C3 does not beat local SST on transfer |
| 4 | ATX-138-01 | B_12 to B_47 | 948.71 | 10.21 | 5.20 | 1.09 | 95.34 | 87.25 | good candidate: C3 adds transfer beyond local SST and keeps harmonic and dynamic benefits |

## Three-Benefit Check

- All 4 of 4 candidate corridors meet the
  three architecture-level benefit checks used here: transfer plus
  efficiency improvement versus C0, centralized harmonic ownership, and
  reduced dynamic voltage exposure with LEL ride-through pass.
- The median C3 transfer gain versus C0 is
  18.86%.
- The median C3 p95 THDv reduction versus C0 is
  95.22%.
- The median C3 p95 voltage-deviation reduction versus C0 is
  87.25%.

## Local Versus Centralized Support

C3 beats local SST on transfer in 3 of 4 corridors and beats local SST on
efficiency in 3 of 4. This is why the ranking does not
treat efficiency alone as decisive. The centralized C3 case is strongest
where it also adds corridor capacity beyond the C2 local-SST case, while
still keeping the harmonic and dynamic-voltage benefits.

Local SST plus local VAR support remains useful, but the screen keeps the
coordination disadvantage explicit: nearby Volt-VAR devices, LTCs,
capacitor banks, voltage regulators, STATCOM/SVC equipment or other
smart-inverter controls can respond on different time scales. That can
produce hunting or poor voltage coordination unless the local controls
are supervised and coordinated with utility devices.

## Limitation

The siting result depends on the archived synthetic corridor assumptions.
A utility-grade placement would need the actual Austin/Travis bus
geography, right-of-way constraints, protection studies, converter
ratings, GridDyn or equivalent dynamic cases, and OpenDSS feeder mapping
for each candidate interconnection.
