# Travis 150 Greenfield Data-Center Configuration Study

This v2 study uses the Travis 150 synthetic electric test case as a
data-center configuration test bed. The gas network is ignored.

The TAMU source describes the dataset as a 150-bus synthetic electric
test case corresponding to the Austin-Travis County T&D system and notes
that it is synthetic rather than an actual grid:
https://electricgrids.engr.tamu.edu/synthetic-gas-electric-test-case-for-the-travis-150-system/

HELICS is the intended T&D coupling layer because its tool list includes
OpenDSS/OpenDSSDirect.py/PyDSS for distribution simulation and GridDyn
for transmission simulation: https://helics.org/tools/

## Configuration

- Input source: `powerworld_aux:Travis150/Travis150_Electric_Data.aux`.
- Flagship data-center corridor: `TRAVIS150-AUX-001` / `163 Decker Creek Power Plant 1 to 147 Travis_DS_127 1`.
- C1 is a new traditional AC data-center supply ending at 480 V AC.
- C2 is a new AC corridor with local SST and 34.5 kV-side VAR support.
- C3 is a new dedicated bipolar DC data-center corridor with centralized
  AC/DC-terminal voltage support.
- These are new-build data-center configurations, not conversions of an
  existing AC line.
- For PowerWorld AUX inputs, existing Travis branch routes provide siting,
  voltage class and impedance context; transfer limits use new-build
  data-center corridor assumptions.

## Base 1 GW Results

| Scenario | Architecture | Max transfer MW | Efficiency at 1 GW | p95 THDv % | p95 voltage dev % | Min load served | Trip flag |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Greenfield traditional AC data-center supply | 1173.60 | 96.37 | 1.67 | 0.42 | 42.50 | True |
| C2 | Greenfield AC corridor with data-center SST | 1235.40 | 97.62 | 0.53 | 0.25 | 40.62 | False |
| C3 | Greenfield bipolar DC data-center corridor | 1441.41 | 97.59 | 0.08 | 0.05 | 100.00 | False |

## Interpretation

C3 raises the useful transfer limit from 1173.60 MW
for C1 to 1441.41 MW for the new DC corridor. At
the same 1 GW data-center load, C3 centralizes AC harmonic ownership at
one grid-facing converter terminal and keeps the data-center load served
through the repeated voltage-sag screen.

The voltage output is a HELICS-compatible proxy screen unless a true
Travis 150 GridDyn dynamic case is supplied. It preserves the intended
federate roles: GridDyn publishes transmission POI voltage, OpenDSS
receives the POI voltage for the data-center feeder, and the controller
federate applies C2 local VAR or C3 centralized AC/DC-terminal support.

## Output Files

- `data/travis150_greenfield_c1_c2_c3_transfer_v2.csv`
- `data/travis150_greenfield_c1_c2_c3_harmonics_v2.csv`
- `data/travis150_greenfield_c1_c2_c3_voltage_v2.csv`
- `data/travis150_greenfield_c1_c2_c3_summary_v2.csv`

## Limitations

This run used the supplied Travis electric case for corridor siting and electrical context, while the dynamic voltage result remains a HELICS-compatible proxy screen.
A utility-grade result should rerun the same scenarios with a validated
Travis 150 GridDyn dynamic model and an OpenDSS feeder tied through
HELICS.
