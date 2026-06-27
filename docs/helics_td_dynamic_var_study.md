# HELICS T&D Dynamic VAR Study Protocol

This note records the GridPACK/HELICS/OpenDSS dynamic VAR workflow used for
the Travis 150 greenfield data-center comparison.

## Objective

Test whether a data-center-side SST plus local dynamic VAR support at the
34.5 kV AC interface can keep service voltage high enough to avoid tripping
during a severe transmission voltage-dip sequence. Compare that distributed
solution against centralized dynamic VAR support at the 115/138 kV
data-center interconnection AC side.

The key output is not only minimum voltage. The study should also report load
served, trip flags, current limiting, recovery time, VAR duty, controller
hunting, tap changes and capacitor-bank switching.

## Co-Simulation Stack

Use HELICS as the federation layer. The configured repository path uses
GridPACK as the transmission simulator for the Travis 150 RAW/DYR case, with
OpenDSS/OpenDSSDirect.py on the distribution side.

- HELICS tools: https://helics.org/tools/
- PyDSS/OpenDSS interface: https://github.com/NREL/PyDSS

Recommended federates:

- Transmission federate: GridPACK dynamic transmission model.
- Distribution federate: OpenDSS or PyDSS feeder model representing the data
  center load and local 34.5 kV equipment.
- Controller federate: local SST dynamic VAR controller, centralized
  STATCOM/SVC or AC/DC-terminal controller, and optional supervisory
  coordination logic.
- Broker/logger federate: HELICS broker plus recorder for bus voltage, P/Q,
  device states, tap positions and trip logic.

## Network Choices

Use two transmission cases, in this order:

1. Texas A&M 150-bus Austin-Travis transmission case in GridPACK using
   `Travis150-updated/150.RAW` and `150_gridpack_REECA1_candidate.dyr`.
2. IEEE 118-bus or another public dynamic case only as a low-dependency
   coupling and control demonstration.

The OpenDSS side should start from a selected Texas A&M distribution feeder and
replace or augment the native load with a data-center aggregate:

- 115/138 kV transmission POI.
- Substation transformer to 34.5 kV.
- SST and dynamic VAR device at the 34.5 kV AC side for the local case.
- 800 VDC load boundary with voltage-sensitive ride-through and trip logic.

## Disturbance

The manuscript evidence uses six shifted GridPACK branch-fault simulations on
the Travis 150 137-150 branch, with bus 150 as the POI voltage observation.
The exported 3 s POI traces are passed to the HELICS/OpenDSS data-center
federation at 20 ms resolution.

## Cases

Run the same disturbance under these cases:

- Baseline: no added dynamic VAR support, voltage-sensitive data-center load
  responds to the dip and may trip.
- Local/distributed: SST plus local dynamic VAR support at the 34.5 kV AC side.
- Local with legacy devices enabled: same as the local case, but with LTC,
  feeder regulator and capacitor-bank controls active.
- Centralized: STATCOM/SVC or AC/DC-terminal voltage support at the 115/138 kV
  data-center interconnection AC side.
- Coordinated combined sensitivity: local and centralized controls enabled with
  explicit deadbands, delays and priority rules.

## HELICS Exchanges

Minimum publications and subscriptions:

- Transmission to distribution: POI voltage magnitude, angle and frequency.
- Distribution to transmission: aggregate P and Q at the POI.
- Controller to distribution: SST VAR command, local voltage reference,
  current limit and trip-block state.
- Controller to transmission: centralized VAR command and voltage reference.
- Distribution to controller: 34.5 kV bus voltage, SST current, load-served
  fraction and trip state.
- Utility equipment to logger: LTC taps, voltage-regulator taps, capacitor-bank
  switching state and STATCOM/SVC output.

Use a sub-cycle or one-cycle communication step for short fault playback, then
repeat with a coarser step to check sensitivity.

## Metrics

Primary metrics:

- Minimum 115/138 kV POI voltage and 34.5 kV service voltage.
- Fraction of data-center load served through the event.
- Ride-through pass/fail based on current limit, trip logic and recovery time.
- Recovery time to 90% grid-side power after voltage returns above 0.9 pu.
- Maximum and RMS dynamic VAR output.

Coordination metrics:

- Number of LTC/regulator tap operations.
- Number of capacitor-bank switching events.
- Sign reversals or oscillations in VAR commands.
- Phase lag between local and centralized VAR response.
- Voltage hunting amplitude after each sag clears.

## Local-Control Risks To Report

The local SST case is useful because it lets the data center protect itself at
the 34.5 kV interface. It also has disadvantages that must be reported:

- Control fighting: nearby SSTs or smart inverters may inject and absorb VARs
  on different delays, causing voltage hunting instead of smooth recovery.
- Legacy-equipment interaction: local VAR injection may overlap with slower
  substation LTCs, voltage regulators, switched capacitor banks or centralized
  STATCOM/SVC devices.
- Visibility and ownership: a customer-side controller may solve local voltage
  while obscuring the system-level response from the utility.
- Settings burden: deadbands, droop slopes, current limits and intentional
  delays need coordination across customer and utility equipment.

These risks are why the centralized 115/138 kV case should be retained even if
the local case improves the data-center service voltage in isolation.

## Repository Status

The primary GridPACK-backed path is under `cosim/gridpack_td_dynamic_var/` and
uses `Travis150-updated/150.RAW` plus
`Travis150-updated/150_gridpack_REECA1_candidate.dyr`.

- GridPACK event sweep:
  `cosim/gridpack_td_dynamic_var/results_event_sweep/event_sweep_summary_compact.csv`.
- Transmission observation: six shifted 3 s branch-fault simulations on the
  137-150 branch with bus 150 as the POI voltage observation.
- Result: the lowest POI minimum is 0.091994 pu. C1 and C2 trip in the
  HELICS/OpenDSS data-center federation, while C3 keeps the modeled 800 VDC
  load boundary served through the centralized AC/DC-terminal and DC-buffer
  representation.
