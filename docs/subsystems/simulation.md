# Mission simulation — mission-scenario engine from LEO to interstellar

`aria.simulation` is the mission-scenario engine: it defines and runs mission
profiles, chains physics primitives into phase sequences, and compares results
against published mission data. It is the largest subsystem by source volume —
126 Python files, ~67,200 lines of code.

The package is concerned with what happens during a mission: what burns are
needed, in what order, consuming how much propellant, producing what
environment for the crew and spacecraft. It is deliberately distinct from the
interactive engineering lab (see [./engineering-lab.md](./engineering-lab.md)).

---

## Where it sits in the architecture

```
aria.simulation   ← mission scenarios and physics integration (this document)
      │
      ├── Basilisk (optional)  ← 6-DOF orbit/attitude propagation for LEO/GEO
      │         ↓
      ├── aria.physics         ← gravity, propulsion, thermal, radiation pods
      │         ↓
      ├── aria.bus             ← telemetry frames published as bus messages
      │         ↓
      ├── aria.agents          ← 9 subsystem agents process telemetry
      │         ↓
      └── aria.cognitive       ← coordinator correlates anomalies, makes decisions
```

`aria.simulation` drives the physics pods and feeds the agent loop.
`aria.simulator` (a separate package) is the interactive engineering lab that
provides a tick-by-tick 4D simulator with time-travel replay; see
[./engineering-lab.md](./engineering-lab.md).

Cross-links:

- Physics primitives live in `aria.physics` — [./physics.md](./physics.md).
- Digital-twin bridge (component degradation replay) —
  [./digital-twin.md](./digital-twin.md).
- Top-level README — [../../README.md](../../README.md).

---

## The scenario framework

### MissionConfig and MissionRunner

The central entry point is
[`mission_runner.py`](../../src/aria/simulation/mission_runner.py).
A `MissionConfig` dataclass captures all scenario parameters: mission type
(LEO, GEO, INTERSTELLAR), orbital altitude and inclination, simulation
duration and timestep, and optional paths to real-data replay files (NASA
battery telemetry, NOAA GOES proton-flux CSV, EDEN ISS plant-sensor logs).

`MissionRunner` provides named constructors for standard profiles:

| Constructor | Profile |
|---|---|
| `MissionRunner.leo_iss()` | ISS-like, 400 km / 51.6°, one orbit (5 520 s) |
| `MissionRunner.leo_sso()` | Sun-synchronous, 600 km / 97.4° |
| `MissionRunner.geo_comms()` | Geostationary, 35 786 km, one day |
| `MissionRunner.interstellar(years, crew)` | Generation-ship, configurable duration |
| `MissionRunner.with_real_data(…)` | LEO with real-sensor overlay |

Calling `runner.run()` is fully async and executes in three stages:

1. **Setup** — starts the message bus, conditionally initialises the Basilisk
   physics runner (if installed), creates the interstellar challenge
   orchestrator (if INTERSTELLAR type), and starts all nine ARIA subsystem
   agents.
2. **Simulation loop** — `_run_orbital` steps Basilisk forward in
   `telemetry_interval_s` increments, publishing each telemetry frame to the
   bus; `_run_interstellar` iterates year by year through `InterstellarSimulation`
   and `InterstellarChallengeOrchestrator`.
3. **Real-data overlay** — `DataReplayEngine` can post-overlay NASA battery
   data, NOAA proton-flux readings, or EDEN ISS plant-sensor readings onto the
   same bus, so agents see a mix of simulated and real telemetry.

The Basilisk runner
([`basilisk_runner.py`](../../src/aria/simulation/basilisk_runner.py)) wraps
the optional `bsk` package to produce 6-DOF orbit + attitude propagation,
reaction-wheel attitude control, solar-panel eclipse modelling, and
battery charge/discharge. When Basilisk is not installed the runner fails
gracefully and `MissionResults.errors` records the shortfall.

### Scenario data classes

Each physics module in the package defines its own frozen dataclasses for
inputs and results:

- `TLIBurn`, `TLIMission` — TLI burn and propellant budget
  ([`tli.py`](../../src/aria/simulation/tli.py))
- `LunarOrbitConfig`, `TEIResult`, `ReturnTrajectory`, `ReentryAnalysis` —
  return-leg analysis ([`lunar_return.py`](../../src/aria/simulation/lunar_return.py))
- `ReentryConfig`, `ReentryResult`, `ReentryState` — ballistic EDL trajectory
  ([`reentry_simulation.py`](../../src/aria/simulation/reentry_simulation.py))
- `Artemis2MissionResult` — full Artemis 2 chain
  ([`artemis2_mission.py`](../../src/aria/simulation/artemis2_mission.py))
- `GenerationShipConfig`, `GenerationShipResults` — interstellar simulation
  ([`generation_ship.py`](../../src/aria/simulation/generation_ship.py))

Phase results are chained: each phase's `mass_after` becomes the next phase's
`mass_kg` input, so propellant mass is conserved across the full mission.
`MoonMissionResult.overall_success` is `False` if any phase exhausts its
propellant before completing the required ΔV.

### Monte Carlo ensemble

[`mission_ensemble.py`](../../src/aria/simulation/mission_ensemble.py) wraps
`GenerationShipSimulation` in a sequential Monte Carlo runner that fans out
over N seeds and aggregates per-field statistics (min, max, mean, median, P5,
P95) and survival rates. Runs are kept sequential because the simulator
subsystems share module-level singletons that are not thread-safe.

---

## The scenarios

### LEO / Earth-orbit

| File | Description |
|---|---|
| [`basilisk_runner.py`](../../src/aria/simulation/basilisk_runner.py) | ISS-like LEO orbit (400 km) and GEO via Basilisk 6-DOF |
| [`satellite_propagator.py`](../../src/aria/simulation/satellite_propagator.py) | SGP4-style analytical orbit propagation |
| [`tle_parser.py`](../../src/aria/simulation/tle_parser.py) | Two-line element ingestion and epoch normalisation |
| [`satellite_catalog.py`](../../src/aria/simulation/satellite_catalog.py) | Multi-object catalog management |
| [`ground_track.py`](../../src/aria/simulation/ground_track.py) | Sub-satellite latitude/longitude track |
| [`ground_station.py`](../../src/aria/simulation/ground_station.py) | Antenna coverage and link availability |
| [`cw_docking.py`](../../src/aria/simulation/cw_docking.py) | Clohessy-Wiltshire proximity operations / docking |
| [`debris_environment.py`](../../src/aria/simulation/debris_environment.py) | LEO debris collision probability and Whipple shield sizing |
| [`atmo_drag.py`](../../src/aria/simulation/atmo_drag.py) | NRLMSISE-00 atmospheric drag and orbital decay |
| [`constellation_design.py`](../../src/aria/simulation/constellation_design.py) | Walker and other constellation geometries |
| [`constellations.py`](../../src/aria/simulation/constellations.py) | IAU constellation boundaries for sky-navigation context |

### Lunar missions (Apollo / Artemis)

| File | Description |
|---|---|
| [`tli.py`](../../src/aria/simulation/tli.py) | Trans-Lunar Injection: Hohmann and fast-transfer ΔV, C3, Tsiolkovsky propellant |
| [`lunar_mission.py`](../../src/aria/simulation/lunar_mission.py) | TLI + LOI using JPL ephemeris (astropy DE430/440), launch-window scan |
| [`free_return.py`](../../src/aria/simulation/free_return.py) | Lambert solver for free-return constraint; corrects Hohmann 9% LOI error |
| [`lunar_descent.py`](../../src/aria/simulation/lunar_descent.py) | Powered descent (DOI → PDI → braking → terminal → touchdown), gravity losses |
| [`lunar_ascent.py`](../../src/aria/simulation/lunar_ascent.py) | Powered ascent from lunar surface to low lunar orbit |
| [`lunar_return.py`](../../src/aria/simulation/lunar_return.py) | TEI burn, patched-conic Earth-return trajectory, reentry corridor, peak heating |
| [`lunar_surface_thermal.py`](../../src/aria/simulation/lunar_surface_thermal.py) | Lunar surface thermal environment (day/night cycle) |
| [`moon_mission_e2e.py`](../../src/aria/simulation/moon_mission_e2e.py) | End-to-end Apollo/Artemis chain (TLI → LOI → descent → surface → ascent → TEI → EDL), mass-conserving |
| [`apollo_reference.py`](../../src/aria/simulation/apollo_reference.py) | Published ΔV/mass/entry-g data for Apollo 8, 11, 12, 14, 15, 16, 17 (NASA SP-4029 / Orloff 2000) |
| [`saturn_v_reference.py`](../../src/aria/simulation/saturn_v_reference.py) | Saturn V stage separation and performance reference values |
| [`saturn_v_launch.py`](../../src/aria/simulation/saturn_v_launch.py) | Saturn V ascent trajectory model |
| [`artemis2_mission.py`](../../src/aria/simulation/artemis2_mission.py) | Full Artemis 2 chain: parking orbit → TLI → n-body coast → reentry → GNC corridor |
| [`nbody.py`](../../src/aria/simulation/nbody.py) | N-body propagator (Earth + Moon + Sun), Lambert solver, RAAN optimisation for lunar launch |
| [`lagrange_points.py`](../../src/aria/simulation/lagrange_points.py) | Earth-Moon Lagrange point locations |
| [`lander_touchdown.py`](../../src/aria/simulation/lander_touchdown.py) | Touchdown dynamics and surface stability |

### Mars / interplanetary

| File | Description |
|---|---|
| [`mars_transfer.py`](../../src/aria/simulation/mars_transfer.py) | Patched-conic Earth–Mars Lambert transfer, C3, TMI/MOI ΔV, launch-window scan |
| [`mars_edl.py`](../../src/aria/simulation/mars_edl.py) | Mars EDL: hypersonic entry (Allen-Eggers + Mars-GRAM), DGB parachute, retropropulsion |
| [`porkchop.py`](../../src/aria/simulation/porkchop.py) | Porkchop C3 / ΔV grid over departure × arrival date space |
| [`porkchop_dsm.py`](../../src/aria/simulation/porkchop_dsm.py) | Porkchop with deep-space manoeuvre option |
| [`lambert_izzo.py`](../../src/aria/simulation/lambert_izzo.py) | Izzo (2015) Lancaster-Blanchard Lambert solver |
| [`gravity_assist.py`](../../src/aria/simulation/gravity_assist.py) | Gravity-assist ΔV and trajectory bending |
| [`maneuver_planning.py`](../../src/aria/simulation/maneuver_planning.py) | Multi-burn manoeuvre sequence builder and Tsiolkovsky fuel accounting |
| [`mission_design.py`](../../src/aria/simulation/mission_design.py) | Porkchop → Lambert → Tsiolkovsky integrated design workflow |
| [`isru_plant.py`](../../src/aria/simulation/isru_plant.py) | In-situ resource utilisation (propellant production) |
| [`low_thrust.py`](../../src/aria/simulation/low_thrust.py) | Low-thrust spiral trajectory model |
| [`propellant_depot.py`](../../src/aria/simulation/propellant_depot.py) | On-orbit propellant depot logistics |
| [`mining_mission.py`](../../src/aria/simulation/mining_mission.py) | Resource-mining mission to exoplanet bodies (55 Cancri e, icy bodies, metal-rich) |
| [`small_bodies.py`](../../src/aria/simulation/small_bodies.py) | Near-Earth asteroid and comet catalogue (Itokawa, Bennu, etc.) |

### Reentry / EDL

| File | Description |
|---|---|
| [`reentry_simulation.py`](../../src/aria/simulation/reentry_simulation.py) | Ballistic 3-DOF RK4 reentry (drag + gravity turn + Chapman heating) |
| [`reentry_corridor.py`](../../src/aria/simulation/reentry_corridor.py) | Entry corridor boundaries: skip-out and overheat limits |
| [`reentry_ld_control.py`](../../src/aria/simulation/reentry_ld_control.py) | Lifting entry guidance (L/D bank-angle modulation) |
| [`reentry_skip.py`](../../src/aria/simulation/reentry_skip.py) | Skip-reentry trajectory (double-dip entry profile) |
| [`gnc_entry.py`](../../src/aria/simulation/gnc_entry.py) | Navigation error budget, corridor probability, entry Monte Carlo |
| [`planetary_entry.py`](../../src/aria/simulation/planetary_entry.py) | Generic planetary atmosphere entry (configurable atmosphere model) |
| [`aerocapture.py`](../../src/aria/simulation/aerocapture.py) | Aerocapture corridor analysis (Mars / Titan / Venus) |
| [`dv_budget.py`](../../src/aria/simulation/dv_budget.py) | Mission-level ΔV budget accounting |

### ECLSS / closed-loop life support

| File | Description |
|---|---|
| [`first_1000_days.py`](../../src/aria/simulation/first_1000_days.py) | Day-by-day ECLSS mass balance for a 1 000-crew generation ship (BVAD-verified; CO₂, water, food, waste, laundry, dental, etc.) |
| [`eden_iss_baselines.py`](../../src/aria/simulation/eden_iss_baselines.py) | EDEN ISS plant-growth experiment baselines for food yield |
| [`crop_optimizer.py`](../../src/aria/simulation/crop_optimizer.py) | Hydroponic crop-mix optimisation (yield vs power vs water) |
| [`food_synthesis.py`](../../src/aria/simulation/food_synthesis.py) | Starch synthesiser + algae/insect protein production models |
| [`habitat_systems.py`](../../src/aria/simulation/habitat_systems.py) | Pressure, atmosphere, thermal, and habitability models |
| [`eva_consumables.py`](../../src/aria/simulation/eva_consumables.py) | EVA suit consumable (O₂, scrubber cartridge, battery) tracking |
| [`cabin_fire.py`](../../src/aria/simulation/cabin_fire.py) | Cabin fire propagation and suppression model |
| [`fire_safety.py`](../../src/aria/simulation/fire_safety.py) | Fire safety system analysis |
| [`sleep_model.py`](../../src/aria/simulation/sleep_model.py) | Circadian rhythm and crew sleep-quality model |
| [`crew_workload.py`](../../src/aria/simulation/crew_workload.py) | Workload, fatigue, and task-scheduling model |
| [`medical_robotics.py`](../../src/aria/simulation/medical_robotics.py) | Robotic surgical and diagnostic system capabilities |
| [`microbiome_evolution.py`](../../src/aria/simulation/microbiome_evolution.py) | Cabin microbiome drift over multi-year missions |
| [`genelab_spaceflight.py`](../../src/aria/simulation/genelab_spaceflight.py) | NASA GeneLab spaceflight biology data integration |
| [`space_medical_rates.py`](../../src/aria/simulation/space_medical_rates.py) | Epidemiological event rates for long-duration spaceflight |

### Interstellar / generation ship

| File | Description |
|---|---|
| [`interstellar.py`](../../src/aria/simulation/interstellar.py) | Core 100-year+ journey: laser-sail acceleration, D-T fusion, magsail deceleration, hull erosion, food/water/crew year-by-year |
| [`generation_ship.py`](../../src/aria/simulation/generation_ship.py) | Master composite simulation: all subsystems integrated for 1 000-year missions, legacy vs breakthrough-tech A/B comparison |
| [`interstellar_challenges.py`](../../src/aria/simulation/interstellar_challenges.py) | Six grand-challenge simulators (material entropy, food crisis, generational drift, etc.) with cascade detection |
| [`first_1000_days.py`](../../src/aria/simulation/first_1000_days.py) | Day-by-day ECLSS for large crew (also listed under ECLSS above) |
| [`mission_ensemble.py`](../../src/aria/simulation/mission_ensemble.py) | Monte Carlo ensemble runner for generation-ship survival statistics |
| [`relativistic_physics.py`](../../src/aria/simulation/relativistic_physics.py) | Exact Lorentz factor γ, time dilation, ISM drag, relativistic radiation dose |
| [`biology_social.py`](../../src/aria/simulation/biology_social.py) | Population genetics, genetic drift, social cohesion model |
| [`crew_ecosystem.py`](../../src/aria/simulation/crew_ecosystem.py) | Closed-loop crew lifecycle (births, deaths, education, skills) |
| [`breakthrough_tech.py`](../../src/aria/simulation/breakthrough_tech.py) | Glass archive, nanobot repair, torpor, biomanufacturing technology toggles |
| [`manufacturing.py`](../../src/aria/simulation/manufacturing.py) | 3D-printer types and von Neumann self-repair model |
| [`defense.py`](../../src/aria/simulation/defense.py) | Point defence, shielding, internal security |
| [`shield_system.py`](../../src/aria/simulation/shield_system.py) | 7-layer micrometeorite and radiation shield erosion |
| [`governance.py`](../../src/aria/simulation/governance.py) | Multi-generational governance and decision-making model |
| [`arrival_colonization.py`](../../src/aria/simulation/arrival_colonization.py) | Post-arrival phases: system survey, orbit selection, colony establishment |
| [`laser_sail.py`](../../src/aria/simulation/laser_sail.py) | Laser-sail acceleration physics (Forward 1984) |
| [`magsail_pic.py`](../../src/aria/simulation/magsail_pic.py) | Magnetic-sail deceleration (Zubrin 1991) |
| [`braking_architecture.py`](../../src/aria/simulation/braking_architecture.py) | Staged deceleration architecture comparison |
| [`light_lag_comms.py`](../../src/aria/simulation/light_lag_comms.py) | Speed-of-light communication latency model |
| [`quantum_timekeeping.py`](../../src/aria/simulation/quantum_timekeeping.py) | DSAC atomic clock drift, optical lattice, QKD, quantum sensor modelling |
| [`interstellar_challenges.py`](../../src/aria/simulation/interstellar_challenges.py) | (listed above) |
| [`nearby_stars.py`](../../src/aria/simulation/nearby_stars.py) | Catalogue of nearby stellar targets with coordinates and distances |
| [`exoplanets.py`](../../src/aria/simulation/exoplanets.py) | NASA Exoplanet Archive integration for target selection |

### Supplementary physics and utility modules

Supporting modules used across scenario types include: radiation transport
and SPE/GCR catalogues (`radiation_transport.py`, `eva_radiation.py`,
`spe_catalog.py`, `gcr_data_parser.py`); reliability engineering
(`mil_hdbk_217f.py`, `weibull_fitted.py`, `data_driven_degradation.py`,
`material_aging.py`); mass and thermal accounting (`mass_conservation.py`,
`mass_budget_calc.py`, `thermal_management.py`, `subsystem_sizing.py`);
real-data parsers (`battery_parser.py`, `noaa_converter.py`,
`voyager_parser.py`, `data_replay.py`); navigation and GNC utilities
(`rcs_attitude.py`, `range_only_observability.py`, `shooting_closest_approach.py`);
and observational astronomy context (`solar_system.py`, `moons.py`,
`star_field.py`, `messier.py`, `ngc_highlights.py`, `astro_events.py`,
`meteor_showers.py`, `pulsars.py`, `variable_stars.py`, `double_stars.py`).

---

## Validation against published missions

### Lunar TLI ΔV — Apollo 11

Two distinct code paths produce TLI ΔV estimates; they are validated
separately.

**`lunar_mission.py` — JPL ephemeris path.** `simulate_lunar_mission` uses
astropy's built-in DE430/440 ephemeris to look up the Moon's actual distance
on 1969-07-16, then computes a Hohmann ΔV to that real distance. At runtime
the module logs `tli_error_pct` against the published Apollo 11 value of
3 131 m/s (NASA SP-350, Orloff 2000). The unit test
[`test_lunar_mission.py`](../../tests/unit/test_lunar_mission.py)
`TestApollo11Validation.test_tli_within_1pct_of_apollo11` asserts that this
error is below **1%**. Running the computation live produces approximately
3 158 m/s — an error of ~0.86%.

The README headline claim is **0.28%**. That figure does not appear in any
test assertion or module docstring; it is not reproducible from the code as
written. The tightest test tolerance in the codebase is 1% (in
`test_lunar_mission.py`) and 5% (in `test_tli.py`). The 0.28% figure
should be treated as a best-case single-run number that is not enforced by
the test suite.

**`tli.py` — parameterised fast-transfer path.** `apollo_tli()` calls
`compute_tli_fast(185 km, 73 hr)` which applies an empirical transit-time
correction on top of a Hohmann baseline. This path produces ~3 224 m/s, a
~3.3% error against the published 3 120 m/s reference. The test
`TestApolloTLI.test_dv_within_5pct_of_published` asserts error < 5%.

Neither path performs full 3-body propagation for the TLI burn itself; both
use patched-conic approximations with analytical or empirically-corrected
expressions.

### Reentry peak-g — Artemis 2

[`lunar_return.py`](../../src/aria/simulation/lunar_return.py) `compute_reentry`
uses Apollo-calibrated Sutton-Graves / Allen-Eggers scaling anchored on the
published Apollo 11 reference point (6.9 g at 11 038 m/s entry, −6.49°,
NASA SP-350 Table 6-VII). For Artemis 2 conditions (11 000 m/s, −3.7°, Orion
L/D = 0.3, β = 335 kg/m²), the function scales by (v/v\_ref)² × sin|γ| /
sin|γ\_ref| × L/D correction (Loh 1963). At runtime this produces ~3.91 g,
against the published Artemis 2 value of 3.9 g — an error of ~0.3%.

This agreement holds because the model is calibrated to the Apollo reference
and the Artemis 2 entry conditions are close to Apollo-class. The test
[`test_artemis2_mission.py`](../../tests/unit/test_artemis2_mission.py)
`test_peak_decel_within_10pct` asserts only ≤10% error. The tighter comparison
function `compare_with_actual` tests error < 5%.

**Important caveat:** the entry speed (11 000 m/s) is passed directly as an
input constant `A2_ENTRY_SPEED_MS`; it is not computed by the simulator from
the trajectory. The `compare_with_actual` function records `error_pct = 0.0`
for that parameter explicitly. The peak-g result therefore validates the
*scaling formula* given the correct input conditions, not an end-to-end
trajectory prediction. The underlying model is a semi-analytical scaling law,
not a trajectory-integrated 3-DOF simulation for Artemis 2 specifically.

### Apollo reference data

[`apollo_reference.py`](../../src/aria/simulation/apollo_reference.py) stores
published ΔV, mass, and peak-entry-g values for all seven crewed lunar
missions (Apollo 8, 11, 12, 14, 15, 16, 17) drawn from NASA SP-4029 (Orloff
2000) and NSSDCA landing coordinates. These constants are used as calibration
anchors and test comparison targets throughout the lunar scenario modules.

### Mars transfer

[`mars_transfer.py`](../../src/aria/simulation/mars_transfer.py) validates the
C3 departure energy against published values for Perseverance/Mars 2020
(C3\_actual = 8.2 km²/s², JPL press kit July 2020) and Curiosity/MSL
(C3\_actual = 10.4 km²/s², JPL press kit Nov 2011). The method is patched-conic
Lambert + JPL ephemeris; the module docstring states ±5% accuracy against full
propagation for typical Earth-Mars windows.

### Ballistic reentry — Apollo 11

[`reentry_simulation.py`](../../src/aria/simulation/reentry_simulation.py)
implements a 3-DOF RK4 ballistic entry (no lift). `validate_apollo11`
compares the result against the Allen-Eggers (1958) analytical ballistic
estimate (~37 g), not against the actual Apollo 6.7 g value. Apollo flew a
lifting entry (L/D ≈ 0.3) that kept peak deceleration to 6.7 g; a ballistic
model at the same conditions produces ~15 g. The validation checks that the
simulation falls in the physical range (10–100 g) and that the vehicle is
subsonic at drogue deployment — not that it reproduces the lifting-entry
Apollo number.

---

## Current limitations

1. **Analytical and semi-analytical physics.** TLI ΔV uses Hohmann or
   empirically-corrected Hohmann approximations. Reentry peak-g uses
   Allen-Eggers scaling. Mars EDL uses exponential Mars-GRAM atmosphere with
   a single scale height. These are appropriate for mission design at TRL 3–5
   but diverge from full numerical propagation under non-nominal conditions.

2. **No flight heritage.** Nothing in this package has been used to command
   or control a real spacecraft. All validation is against published numbers
   from historical missions; no real-time onboard use has been demonstrated.

3. **Basilisk is optional.** When the `bsk` package is not installed, orbital
   missions fall back to a graceful error. The 6-DOF attitude dynamics,
   eclipse modelling, and reaction-wheel control that Basilisk provides are
   unavailable in that configuration.

4. **Entry speed as input, not output.** The Artemis 2 reentry validation
   passes the published entry speed as a constant input. The n-body coast
   ([`nbody.py`](../../src/aria/simulation/nbody.py)) does propagate the
   outbound translunar trajectory, but the arrival speed at the Entry Interface
   for the return leg is taken from a published value rather than computed from
   first principles end-to-end.

5. **1-D / scalar approximations.** Several modules use scalar ΔV rather than
   vector burns (e.g., LOI in `lunar_mission.py` uses a Hohmann vis-viva
   scalar; `lunar_return.py` uses a simplified patched-conic scalar energy
   balance for the return trajectory). Full 3-D trajectory fidelity requires
   the Lambert solver in `free_return.py` and the numerical integrator in
   `nbody.py`.

6. **Interstellar physics is speculative.** The generation-ship modules model
   physics (laser-sail acceleration to 0.1c, magsail deceleration, D-T fusion
   power) that is well beyond demonstrated technology. The models are
   physically motivated but not validated against real missions; they are
   research exercises at TRL 1–2.

7. **Monte Carlo thread-safety.** The ensemble runner must use sequential
   execution; subsystem singletons prevent parallelism. Large ensembles
   (>100 runs) require forking at the process level.

---

## Where to start reading

**Entry point:**

- [`mission_runner.py`](../../src/aria/simulation/mission_runner.py) —
  `MissionRunner.leo_iss()` / `.interstellar()` / `.run()` — the single
  entry point that wires Basilisk, agents, and the challenge orchestrator
  together.

**Core physics modules (read in order for a lunar mission):**

1. [`tli.py`](../../src/aria/simulation/tli.py) — TLI burn: Hohmann + fast
   transfer, Apollo/Artemis profiles.
2. [`lunar_mission.py`](../../src/aria/simulation/lunar_mission.py) — TLI + LOI
   with real ephemeris; `simulate_lunar_mission("1969-07-16")` to reproduce
   Apollo 11 numbers.
3. [`lunar_descent.py`](../../src/aria/simulation/lunar_descent.py) and
   [`lunar_ascent.py`](../../src/aria/simulation/lunar_ascent.py) — powered
   descent and ascent with gravity-loss accounting.
4. [`lunar_return.py`](../../src/aria/simulation/lunar_return.py) — TEI + reentry
   corridor + peak heating.
5. [`moon_mission_e2e.py`](../../src/aria/simulation/moon_mission_e2e.py) —
   `apollo_11_e2e()` runs all ten phases in sequence with mass conservation.
6. [`artemis2_mission.py`](../../src/aria/simulation/artemis2_mission.py) —
   `simulate_artemis2()` adds n-body coast, debris risk, and GNC Monte Carlo
   to the chain.

**Reentry in isolation:**

- [`reentry_simulation.py`](../../src/aria/simulation/reentry_simulation.py) —
  `simulate_reentry()` for a standalone ballistic 3-DOF trajectory.
- [`gnc_entry.py`](../../src/aria/simulation/gnc_entry.py) —
  `monte_carlo_entry()` for corridor-probability statistics.

**Tests:**

- [`tests/unit/test_tli.py`](../../tests/unit/test_tli.py)
- [`tests/unit/test_lunar_mission.py`](../../tests/unit/test_lunar_mission.py)
- [`tests/unit/test_moon_mission_e2e.py`](../../tests/unit/test_moon_mission_e2e.py)
- [`tests/unit/test_artemis2_mission.py`](../../tests/unit/test_artemis2_mission.py)
- [`tests/unit/test_reentry_simulation.py`](../../tests/unit/test_reentry_simulation.py)
- [`tests/integration/test_apollo_replay.py`](../../tests/integration/test_apollo_replay.py)
- [`tests/integration/test_artemis2_replay.py`](../../tests/integration/test_artemis2_replay.py)
