# HELICS T&D Dynamic VAR Study Protocol

This note defines the proposed follow-on study for voltage-dip ride-through and
dynamic VAR support. It is a validation protocol for the archived Texas T&D
C0/C1/C2/C3 screening results, not a completed co-simulation artifact in this
repository.

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

Use HELICS as the federation layer. The HELICS tools showcase lists
OpenDSS/OpenDSSDirect.py/PyDSS as supported distribution interfaces and GridDyn
as a supported transmission simulator:

- HELICS tools: https://helics.org/tools/
- PyDSS/OpenDSS interface: https://github.com/NREL/PyDSS

Recommended federates:

- Transmission federate: GridDyn dynamic transmission model.
- Distribution federate: OpenDSS or PyDSS feeder model representing the data
  center load and local 34.5 kV equipment.
- Controller federate: local SST dynamic VAR controller, centralized
  STATCOM/SVC or AC/DC-terminal controller, and optional supervisory
  coordination logic.
- Broker/logger federate: HELICS broker plus recorder for bus voltage, P/Q,
  device states, tap positions and trip logic.

## Network Choices

Use two transmission cases, in this order:

1. IEEE 118-bus in GridDyn for a low-dependency public demonstration of the
   coupling and control logic.
2. Texas A&M 150-bus Austin-Travis T&D case for validation against the public
   Texas add-on used elsewhere in this repository.

The OpenDSS side should start from a selected Texas A&M distribution feeder and
replace or augment the native load with a data-center aggregate:

- 115/138 kV transmission POI.
- Substation transformer to 34.5 kV.
- SST and dynamic VAR device at the 34.5 kV AC side for the local case.
- 800 VDC load boundary with voltage-sensitive ride-through and trip logic.

## Disturbance

Use an event-inspired voltage-sag train based on public summaries of the
July 10, 2024 Eastern Interconnection voltage-sensitive-load disturbance. The
Keentel summary describes a 230 kV line equipment failure, six sequential
faults over about 82 seconds, short fault durations, and voltage depressions in
the affected area of about 0.25-0.40 pu:

- https://keentelengineering.com/nerc-voltage-sensitive-loads

This study should treat that information as a reference waveform, not an event
reconstruction. The current archived Python screen uses six short dips spanning
0.25-0.40 pu and keeps the exact grid model abstract.

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

The archived Texas T&D tables still include the deterministic screening waveform
and architecture-level voltage-support assumptions in
`src/ai_dc_backbone/texas_td_scenarios.py`.

The GridDyn-backed path under `cosim/griddyn_td_dynamic_var/` now includes an
executed local GridDyn/HELICS/OpenDSS demo:

- GridDyn executable: `/opt/homebrew/bin/gridDynMain` in the local run.
- Transmission case: Travis-derived GridDyn proxy generated at
  `cosim/griddyn_td_dynamic_var/results/griddyn_travis150_proxy_case.xml` from
  `Travis150/Travis150_Electric_Data.aux`.
- HELICS/OpenDSS result: `cosim/griddyn_td_dynamic_var/results/helics_opendss_dynamic_var_summary.csv`.
- Result: the HELICS POI voltage reached 0.250 pu using the documented
  event-inspired sag train. C1 reached 0.241 pu at the 480 V AC load boundary
  and tripped. C2 reached 0.241 pu at the local SST boundary and still tripped
  in this severe uncoordinated local-support demo. C3 reached 0.241 pu on the
  OpenDSS AC side, but the modeled DC buffer held the 800 VDC load boundary at
  1.0 pu and the data center did not trip.

This is not yet a full Texas A&M Travis 150 dynamic result, because generator,
load and protection dynamic data are not included in the public AUX case. Use
`scripts/run_griddyn_td_dynamic_var.py --griddyn-case ... --poi-voltage-field ...`
when that full dynamic case is supplied.
