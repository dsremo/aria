# Generation-Ship Engineering Lab — drive the ship, break things, learn

The Engineering Lab is the interactive layer of ARIA that turns the digital
twin and physics modules into a live, tickable whole-ship simulation. It lets
an engineer start a mission from a cold ship in cislunar assembly orbit, watch
every subsystem come online through the cold-start sequence, fly through a
multi-decade interstellar cruise, inject failures, observe the cascade of
alarms and degradation, and save or restore the full mission state at any
point.

The word "lab" is intentional: this is a research and training tool, not a
validated flight system. It is currently at TRL 3–5. The physics are
parametric models with literature-cited constants; they are not certified
digital twins and have not been validated against hardware test data.

---

## Where it sits in the architecture

```
aria.digital_twin            aria.physics
(geometry, FEA, materials,   (radiation, ECLSS, thermal, structural)
 dependency_graph, BoM)              │
          │                          │
          └──────────────┬───────────┘
                         ▼
              aria.simulator (this package)
                         │
            ┌────────────┼────────────────┐
            ▼            ▼                ▼
       tick_engine   mission_phases   subsystem physics
       event_bus     startup_sequence (bearing, propulsion,
       auto_tick      narrative_log    power, ECLSS, hull,
                                       crew, comms, agri, …)
                         │
                         ▼
                   web_dashboard.py  ←  aiohttp REST + WebSocket
                         │
                    web/ (React)     ←  101 React components
                         │
                    /api/ai/advise   ←  ARIA cognitive engine
                    /api/ai/reason       (LLM reasoning loop)
```

The simulator package sits one layer above the digital twin. It reads
parametric geometry and part relationships from the twin's dependency graph
(`aria.digital_twin.dependency_graph`) and the ship's `ShipParameters`, then
advances their state second-by-second through the tick engine. The web
dashboard exposes the live simulation state over HTTP and WebSocket; the React
console at `web/` subscribes to those endpoints to render panels. The AI
advisor (`/api/ai/advise`, `/api/ai/reason`) is a gateway into the cognitive
engine, which runs the full LLM reasoning loop and returns structured decisions
that operators can approve or veto through the safety console.

---

## The REST API

`web_dashboard.py` registers all routes. The full list extracted from the
source (alphabetical, one-line description each):

### Status and configuration
| Endpoint | Description |
|---|---|
| `GET /api/status` | Server health and uptime |
| `GET /api/config` | Dashboard configuration (host, port, auth mode) |
| `GET /api/metrics` | Prometheus-style metrics snapshot |
| `GET /healthz` | Kubernetes liveness probe |
| `GET /readyz` | Kubernetes readiness probe |

### Authentication and access control
| Endpoint | Description |
|---|---|
| `GET /api/auth/challenge` | Fetch CHAP nonce for login |
| `POST /api/auth/login` | Authenticate and get session cookie |
| `POST /api/auth/logout` | Revoke current session |
| `GET /api/auth/me` | Current principal identity |
| `GET /api/admin/principals` | List all principals |
| `POST /api/admin/principals` | Create a new principal |
| `POST /api/admin/principals/{id}/revoke` | Revoke a principal |
| `POST /api/admin/principals/{id}/role` | Assign role to principal |
| `GET /api/admin/roles` | List available roles |
| `POST /api/admin/roles/custom` | Create a custom role |
| `POST /api/admin/roles/custom/{name}/revoke` | Delete a custom role |
| `GET /api/admin/permissions` | List all permission names |

### Part inspection and dependency graph
| Endpoint | Description |
|---|---|
| `GET /api/inspect/parts` | All parts with operational snapshots |
| `GET /api/inspect/part/{part_id}` | Single part snapshot (health, temperature, power, MTBF) |
| `GET /api/inspect/deps/{part_id}` | Direct dependency edges for a part |
| `GET /api/inspect/cascade/{part_id}` | Full failure-cascade subgraph from a part |
| `GET /api/inspect/graph` | Whole dependency graph as nodes + edges |

### Mission phase state machine
| Endpoint | Description |
|---|---|
| `GET /api/mission/phase` | Current phase, elapsed time, spec, transition history |
| `POST /api/mission/transition` | Force a phase transition (operator command) |
| `POST /api/mission/tick` | Advance mission time by a specified delta |

### Cold-start sequence
| Endpoint | Description |
|---|---|
| `GET /api/startup/status` | Step-by-step bringup state |
| `POST /api/startup/tick` | Advance the startup sequence |
| `POST /api/startup/reset` | Reset bringup to step 0 |
| `POST /api/startup/abort` | Abort the current startup step |

### Tick engine and event bus
| Endpoint | Description |
|---|---|
| `GET /api/tick/status` | Tick engine statistics (registered subsystems, step count, wall time) |
| `POST /api/tick/advance` | Advance the simulation by a delta in seconds |
| `GET /api/events/recent` | Recent events from the ring buffer, filterable by topic/severity |
| `GET /api/events/health` | Event bus health: per-topic counts, spam detection |
| `POST /api/events/publish` | Inject an arbitrary event (testing and operator notes) |

### Auto-tick background playback
| Endpoint | Description |
|---|---|
| `GET /api/auto_tick` | Auto-tick status (running, speed factor, tick count) |
| `POST /api/auto_tick/start` | Start background playback |
| `POST /api/auto_tick/stop` | Pause background playback |
| `POST /api/auto_tick/speed` | Set simulation speed (wall-seconds per simulated unit) |

### Subsystem physics — propulsion and power
| Endpoint | Description |
|---|---|
| `GET /api/reactor` | Reactor thermal/electrical output, operating mode |
| `GET /api/reactor/state` | Alias for `/api/reactor` |
| `GET /api/propulsion/thermal` | Nozzle-plume back-radiation heat load and throttle state |
| `GET /api/power` | Power budget summary (generation, demand, shed loads) |
| `GET /api/power/budget` | Alias with full per-consumer breakdown |
| `GET /api/fuel` | Propellant inventory across all tanks |
| `GET /api/trajectory` | Ship position, velocity, distance to target |
| `GET /api/trajectory/targets` | Available interstellar and solar-system targets |
| `POST /api/trajectory/target` | Set mission target |
| `POST /api/trajectory/refuel` | Refill propellant (operator override) |
| `POST /api/trajectory/gravity_assist_plan` | Compute a gravity-assist trajectory |

### Subsystem physics — habitat and crew
| Endpoint | Description |
|---|---|
| `GET /api/bearing` | Habitat-ring bearing state (maglev / roller / off) |
| `POST /api/bearing/trip` | Force the maglev bearing to trip to roller backup |
| `POST /api/bearing/restore` | Restore maglev bearing |
| `GET /api/eclss` | ECLSS summary |
| `GET /api/eclss/contaminants` | Per-contaminant concentrations vs SMAC limits |
| `GET /api/crew/health` | Crew population health indices (SANS, bone density, VO₂max, cohesion) |
| `GET /api/crew/schedule` | Shift roster, productivity index, sleep debt |
| `POST /api/crew/overtime` | Authorize overtime for repair surge |
| `GET /api/agriculture` | Crop yield, food store, calorie and protein balance |
| `POST /api/agriculture/failure` | Inject an agriculture failure scenario |
| `POST /api/agriculture/restore` | Restore agriculture to nominal |

### Subsystem physics — hull and radiation
| Endpoint | Description |
|---|---|
| `GET /api/hull` | Hull-damage summary (per-region health, fatigue indices) |
| `GET /api/hull/damage` | Alias with per-zone impact detail |
| `POST /api/hull/impact` | Inject a micrometeoroid impact |
| `POST /api/hull/damage` | Apply damage directly to a hull region |
| `POST /api/hull/repair` | Mark a hull region as repaired |
| `GET /api/avionics/seu` | SEU/radiation bit-flip statistics (ECC correction rate, TMR votes) |

### Failure injection and random events
| Endpoint | Description |
|---|---|
| `GET /api/failures/scenarios` | Named failure scenarios available for injection |
| `POST /api/failures/trigger` | Apply a named failure scenario |
| `GET /api/random_events` | Random-event engine status (enabled, rates) |
| `POST /api/random_events/toggle` | Enable or disable stochastic events |
| `POST /api/random_events/force_mmod` | Force an immediate micrometeoroid strike |
| `POST /api/random_events/force_flare` | Force an immediate solar-flare event |

### Repair queue and in-flight manufacturing
| Endpoint | Description |
|---|---|
| `GET /api/repair` | Repair task queue and feedstock inventory |
| `POST /api/repair/enqueue` | Add a repair task |
| `POST /api/repair/cancel` | Cancel a queued task |
| `POST /api/repair/refill` | Refill 3D-printer feedstock from cargo manifest |

### Communications budget
| Endpoint | Description |
|---|---|
| `GET /api/comms` | Earth-link state: light-time delay, bandwidth, modulation mode |
| `POST /api/comms/queue` | Add a message to the outbound queue |

### Bill of materials
| Endpoint | Description |
|---|---|
| `GET /api/bom` | Full bill of materials |
| `GET /api/bom/{item_id}` | Single BOM item |
| `GET /api/bom/spof` | Single-points-of-failure identified by the dependency graph |
| `GET /api/materials` | Material property catalogue |
| `GET /api/ship/params` | Current `ShipParameters` (geometry, mass budget, reactor spec) |
| `GET /api/ship/parts` | Parts list from the digital twin |
| `GET /api/ship/classes` | Available pre-defined ship classes |
| `POST /api/ship/apply_class` | Apply a ship class preset |
| `POST /api/ship/rebuild` | Recompute geometry and BoM from parameters |
| `POST /api/ship/analyze` | Run an engineering analysis pass |
| `GET /api/ship/review` | Engineering review report |
| `POST /api/ship/optimize` | Run a multi-objective optimizer over ship parameters |
| `GET /api/ship/status` | Combined ship health status strip |
| `POST /api/ship/assembly/compute_mass` | Compute assembly mass from part list |
| `POST /api/ship/assembly/save` | Save a named assembly configuration |
| `GET /api/ship/assembly/load/{uid}` | Load a saved assembly |
| `GET /api/ship/assembly/list` | List saved assemblies |
| `POST /api/ship/assembly/simulate` | Run a tick-simulation of an assembly |

### Faults and incident management
| Endpoint | Description |
|---|---|
| `GET /api/faults` | Active fault list |
| `POST /api/faults/report` | Report a new fault |
| `POST /api/faults/{id}/acknowledge` | Acknowledge a fault |
| `POST /api/faults/{id}/shelve` | Shelve a non-critical fault |
| `POST /api/faults/{id}/resolve` | Resolve and close a fault |
| `GET /api/faults/stats` | Fault statistics |
| `GET /api/incidents` | Incident log |
| `GET /api/incidents/{id}` | Single incident record |
| `POST /api/incidents/{id}/note` | Add operator note |
| `POST /api/incidents/{id}/fix` | Record a fix attempt |
| `POST /api/incidents/{id}/root_cause` | Record root cause |
| `POST /api/incidents/{id}/resolve` | Close incident |
| `POST /api/incidents/{id}/defer` | Defer incident |

### Mission persistence and objectives
| Endpoint | Description |
|---|---|
| `GET /api/save` | Snapshot full mission state to JSON |
| `POST /api/load` | Restore mission state from a JSON snapshot |
| `GET /api/objectives` | Mission objectives checklist with completion timestamps |
| `GET /api/snapshots` | All recorded simulator snapshots (replay mode) |
| `GET /api/snapshot/{year}` | Single snapshot by mission year |

### Narrative log and event scheduler
| Endpoint | Description |
|---|---|
| `GET /api/narrative` | Narrative log as structured entries |
| `GET /api/narrative/text` | Narrative log as plain text (captain's log format) |
| `POST /api/narrative/note` | Insert an operator annotation |
| `POST /api/narrative/clear` | Clear the narrative log |
| `GET /api/scheduler` | Scheduled-event queue |
| `POST /api/scheduler/add` | Add a future event (fires at a specified mission time) |
| `POST /api/scheduler/cancel` | Cancel a scheduled event |

### AI advisor
| Endpoint | Description |
|---|---|
| `GET /api/ai/advise` | Current AI advisor recommendation (cached) |
| `POST /api/ai/advise` | Request a fresh advisory with context body |
| `POST /api/ai/reason` | Ask the cognitive engine to reason over a question |
| `GET /api/ai/decisions` | Recent AI decisions and their justifications |
| `GET /api/ai/recent_actions` | Recent actions taken by ARIA agents |

### Safety console
| Endpoint | Description |
|---|---|
| `GET /api/safety/state` | Full safety state (kill-switch, deadman, proposals) |
| `GET /api/safety/proposals` | Pending approval-queue proposals |
| `POST /api/safety/approve` | Sign off on a proposal |
| `POST /api/safety/veto` | Veto a proposal |
| `POST /api/safety/revert` | Revert an already-applied action |
| `POST /api/safety/kill_assert` | Assert the hardware kill switch |
| `POST /api/safety/kill_reset` | Clear the kill switch |
| `POST /api/safety/deadman_affirm` | Affirm the deadman heartbeat |
| `GET /api/safety/replay` | Safety-replay test status |
| `POST /api/safety/replay/run` | Run the sealed safety-replay test set |
| `GET /api/safety/sandbagging` | Sandbagging-detector state |
| `GET /api/safety/boot_manifest` | Boot integrity manifest |

### Telemetry
| Endpoint | Description |
|---|---|
| `GET /api/telemetry/live` | Live snapshot of all subsystem telemetry |
| `GET /api/telemetry/live_state` | Extended live state (used by status strip) |
| `GET /api/telemetry/snapshot` | Telemetry buffer snapshot |
| `GET /api/telemetry/dsn` | Deep Space Network pass schedule |
| `GET /api/telemetry/separation` | Telemetry/command separation state |
| `GET /api/telemetry/mission_schedule` | Upcoming mission event schedule |

### Mission design and astrodynamics
| Endpoint | Description |
|---|---|
| `GET /api/mission_design/earth_mars` | Earth–Mars mission design report |
| `GET /api/porkchop/{origin}/{dest}` | Porkchop plot data (launch window vs delta-V) |
| `GET /api/mission/porkchop` | Porkchop query from query string |
| `GET /api/mission/ensemble/stream` | Monte-Carlo ensemble stream |
| `GET /api/mission/aerocapture` | Aerocapture feasibility and delta-V |
| `GET /api/lunar/feasibility` | Lunar mission feasibility report |
| `GET /api/moon_mission` | Moon mission state |

### Astronomy catalogs
| Endpoint | Description |
|---|---|
| `GET /api/nearby_stars` | Nearby star catalog with 3-D coordinates |
| `GET /api/exoplanets` | Exoplanet catalog |
| `GET /api/star_field` | Background star field for 3-D view |
| `GET /api/solar_system` | Solar-system body positions |
| `GET /api/orbits` | Orbit data for known bodies |
| `GET /api/belt_cloud` | Asteroid belt point cloud |
| `GET /api/astro_events` | Upcoming astronomical events |
| `GET /api/sky_now` | Current sky from a given location |
| `GET /api/satellites` | Satellite catalog |
| `GET /api/tle/catalog` | TLE catalog |
| `GET /api/pulsars` | Pulsar catalog |
| `GET /api/variable_stars` | Variable star catalog |
| `GET /api/double_stars` | Double star catalog |
| `GET /api/ngc_highlights` | NGC highlights |
| `GET /api/cities` | City database (for ground-track / DSN geometry) |
| `GET /api/constellation/{name}` | Single constellation data |
| `GET /api/constellation_list` | All constellation names |

### Replay and audit
| Endpoint | Description |
|---|---|
| `POST /api/replay/run` | Re-run a recorded mission segment |
| `POST /api/replay/report` | Generate an after-action report for a replay |
| `GET /api/audit/trace` | Audit-chain trace for a given event |
| `GET /api/audit/chain_status` | Integrity status of the audit chain |

### Knowledge and doctrine
| Endpoint | Description |
|---|---|
| `POST /api/doctrine/search` | Search engineering doctrine database |
| `POST /api/lessons/search` | Search lessons-learned database |

### WebSocket
| Endpoint | Description |
|---|---|
| `WS /ws` | Real-time push of snapshots and events to all connected clients |

---

## What's in the package

The `src/aria/simulator/` package contains **37 Python files**. They group into
eight functional clusters:

### Inspection layer
`part_inspector.py` — builds a `PartSnapshot` for any part ID (static geometry,
design role, and dynamic operational state in one call). Pulls from
`aria.digital_twin.dependency_graph` and `ShipParameters`.

### Tick engine and events
`tick_engine.py` — registers named tickable subsystems in priority order
(reactor=10, power distribution=20, propulsion/thermal=30, consumers=40,
sensors=50, bookkeeping=60+) and advances them in lockstep with optional
substep splitting (max 60 s per substep by default). `event_bus.py` — in-process
pub/sub with dotted-topic prefix matching, a 20 000-event ring buffer, per-subscriber
bounded queues, and a spam detector. `auto_tick.py` — background daemon that
drives the tick engine at a configurable speed factor (1× real-time to
86400× fast-forward). `event_scheduler.py` — mission-time–triggered event queue.
`recorder.py` — snapshots every tick for playback.

### Subsystem physics
`bearing_dynamics.py` — magnetic-levitation primary bearing plus Lundberg-Palmgren
L₁₀ roller-bearing wear model; models the habitat ring's 54.9 Mt load.
`propulsion_thermal.py` — nozzle back-radiation heat load (Frisbee 2003 §4.3
plasma deflection efficiency) and radiator-capacity throttle feedback.
`power_tracker.py` — reactor Brayton-cycle power distribution with priority-ordered
load shedding.
`eclss_contaminants.py` — four airborne contaminants (CO₂, ethylene, formaldehyde,
ammonia) modelled with first-order generation plus scrubber removal kinetics;
SMAC limits from NASA-TM-104827.
`computing_radiation.py` — GCR-driven SEU bit-flip model with ECC (SECDED),
TMR voting, and scrubbing layers; cross-sections from Dodd & Massengill 2003.
`hull_damage.py` — 10 hull regions with Miner's-rule fatigue accumulation from
micrometeoroid impacts.
`agriculture_yield.py` — 40 000 m² hydroponic rotation across five crops with
harvest cycles, calorie and protein balance, and four failure modes.
`comms_budget.py` — Earth-link light-time delay and Friis-equation bandwidth
with modulation stepping from Ka-band QAM down to BPSK at interstellar range.
`crew_health.py` — five spaceflight-medicine effects (SANS, bone loss,
cardiovascular deconditioning, vestibular adaptation, psychological cohesion)
at population scale.
`crew_schedule.py` — three-shift roster, circadian productivity dip, sleep-debt
accumulation, and available crew-hours for the repair queue.
`fuel_tracker.py` — propellant inventory across named tanks.
`trajectory_state.py` — 3-D position and velocity integration keyed off
mission phase and propulsion thermal output.
`trajectory.py` — Tsiolkovsky delta-V and propulsion option tables.
`gravity_assist.py` — gravity-assist trajectory layer.
`targets.py` — star catalog with real 3-D unit vectors for interstellar targets.

### Mission state
`mission_phases.py` — six-phase state machine (PRELAUNCH → BOOST → CRUISE →
DECELERATION → ARRIVAL → ORBIT) plus an EMERGENCY sideband; phase specs carry
nominal duration, power/thermal/RCS load fractions, and main-thrust fraction.
`mission_objectives.py` — milestone checklist evaluated lazily each tick.
`bill_of_materials.py` — full part BOM with single-point-of-failure analysis.
`random_events.py` — stochastic micrometeoroid, solar-flare, and subsystem-fault
events.

### Failures
`failure_injector.py` — nine named injection scenarios including maglev trip,
radiator loss, ECLSS scrubber fault, main-tank fuel leak, shield micrometeoroid,
SEU storm, APU fault, TMR burst, and avionics ECC cascade. Each mutates the
relevant singleton and publishes a bus event so the cascade propagates naturally.

### Operations
`startup_sequence.py` — ordered cold-start bringup with per-step preconditions,
success probabilities, and abort/retry logic; modelled on NASA-HDBK-6000 and
JSC-66545.
`repair_queue.py` — 3D-printer feedstock plus repair task queue driven by
crew-hours from the schedule; sourced from the hull-damage and failure-injector
event stream.
`telemetry.py`, `telemetry_buffer.py` — live-state snapshot buffering.
`telemetry_otel.py` — optional OpenTelemetry spans on every tick.
`ccsds_packet.py` — CCSDS Space Packet Protocol framing.

### Persistence
`mission_persistence.py` — serialises and restores 17 subsystem singletons
(mission clock, mission state, phases, startup, trajectory, fuel, crew,
radiation, ECLSS, bearing, propulsion, power, comms, agriculture, hull, random
events, scheduler) to a single JSON document. Save files are not
backward-compatible across package versions.

### Narrative
`narrative_log.py` — deterministic template-based "captain's log"; subscribes to
the event bus and renders each high-level event (phase transitions, bearing trips,
reactor scrams, hull impacts, arrivals) as a dated prose line. No LLM involved.

### Web layer
`web_dashboard.py` — aiohttp server that registers all REST routes and a
WebSocket endpoint. Serves the built React app from `web/dist/` when present,
with SPA fallback. Auth/authz middleware (CHAP-based sessions, RBAC) is
enabled via `ARIA_AUTH_REQUIRED=1`. `web_assets/` — three static HTML pages
(`index.html`, `engineering_lab.html`, `ship_viewer.html`) used when the
React build is not present.

---

## Running it

### Console entry point

```
aria-dashboard [--host HOST] [--port PORT] [--recording PATH]
```

The `aria-dashboard` console script (registered in `pyproject.toml`) resolves
to `aria.simulator.web_dashboard:main`. The server listens on port 8090 by
default. You can override the host, port, and CORS origin via environment
variables (`ARIA_HOST`, `ARIA_PORT`, `ARIA_CORS_ORIGIN`). Authentication is
off by default; set `ARIA_AUTH_REQUIRED=1` to enable RBAC.

You can also run it directly:

```
python -m aria.simulator.web_dashboard --port 8090
```

Or drive it programmatically in live mode:

```python
from aria.simulator.web_dashboard import WebDashboard, DashboardConfig

dashboard = WebDashboard(DashboardConfig(port=8090))
await dashboard.start()
dashboard.push_snapshot(state_dict)
dashboard.push_event(event_dict)
```

Or in replay mode (load a recorded mission and serve it via HTTP):

```python
dashboard = WebDashboard()
dashboard.load_recording("/path/to/mission.json")
await dashboard.start()
```

### React console

The React frontend lives in `web/`. Build it with `npm run build` inside that
directory; the output lands in `web/dist/` and the dashboard serves it
automatically at `/app`. The 101 React components cover every panel in the
lab: trajectory view, subsystem health gauges, bearing visualizer, power-flow
diagram, hull-damage heatmap, ECLSS atmosphere monitor, crew life panel,
agriculture dashboard, failure drill menu, safety console, AI advisor panel,
planetarium, ship builder, porkchop plotter, and others. The WebSocket at
`/ws` pushes live snapshots and events to all connected clients.

---

## Current limitations

These are the known engineering gaps at TRL 3–5:

- **1-D trajectory approximation.** `trajectory_state.py` integrates velocity
  in 3-D (x, y, z in light-years) but the thrust model is point-mass; no
  orbital mechanics, no Jacobi integrals, no finite-burn arc integration.
  Gravity-assist trajectories (`gravity_assist.py`) are order-of-magnitude
  estimates, not numerically propagated.
- **Parametric physics, not validated models.** Every physics module cites
  sources (Frisbee 2003, Dodd & Massengill 2003, Lundberg-Palmgren 1947,
  NASA-TM-104827, etc.) but the numerical constants are rule-of-thumb estimates
  scaled from those references, not validated against hardware test data.
  The models are useful for relative comparisons and cascade studies, not
  for safety-critical sizing.
- **Population-level crew health.** `crew_health.py` tracks aggregate indices
  for a 1 000-person crew; no per-individual health timeline.
- **No inter-process communication.** The tick engine, event bus, and all
  subsystem singletons are in-process; there is no distributed or multi-node
  deployment path.
- **Save-file compatibility.** Snapshot format (`mission_persistence.py`) is
  not promised to be stable across package versions. Old saves may not
  restore correctly after a dependency is added to `_SUBSYSTEMS`.
- **No hardware-in-the-loop.** The CCSDS packet layer (`ccsds_packet.py`) and
  DSN telemetry model (`telemetry_otel.py`) do not interface with physical
  hardware or any validated flight-software stack.

---

## Where to start reading

To understand the simulator end-to-end, read these files in order:

1. `../../src/aria/simulator/tick_engine.py` — the central advance/substep
   loop and the `TickableProtocol` every subsystem must implement.
2. `../../src/aria/simulator/mission_phases.py` — the phase state machine
   and its interaction with `MissionClock`.
3. `../../src/aria/simulator/event_bus.py` — pub/sub ring buffer and topic
   matching syntax.
4. `../../src/aria/simulator/web_dashboard.py` — all route registrations
   (lines 493–656) and the `main()` entry point.
5. `../../src/aria/simulator/startup_sequence.py` — the cold-start step list.
6. `../../src/aria/simulator/failure_injector.py` — the nine named scenarios
   and how they mutate singletons and emit bus events.
7. `../../src/aria/simulator/mission_persistence.py` — the `_SUBSYSTEMS`
   table, `snapshot()`, and `restore()`.

Tests:

- `tests/integration/test_simulator.py` — end-to-end tick tests.
- `tests/integration/test_web_dashboard.py` — HTTP handler tests.
- `tests/integration/test_web_dashboard_authz.py` — auth/authz tests.
- `tests/integration/test_4d_simulator.py` — 4-D engine integration tests.

Related subsystem docs:

- `./digital-twin.md` — the dependency graph, FEA, and parametric geometry
  that the inspector layer reads.
- `./physics.md` — the physics pod implementations the tick engine drives.
- `./cognitive.md` — the LLM reasoning loop behind `/api/ai/advise` and
  `/api/ai/reason`.
- `./safety-and-monitor.md` — the failsafe controls exposed through
  `/api/safety/*`.
- `../../README.md` — project overview and TRL framing.
