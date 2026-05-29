# Integrations & external-tool bridges — ground tools, simulators, and the hardware boundary

ARIA's integrations subsystem is the outward-facing edge of the system. It contains every adapter that crosses a boundary ARIA does not own: ground-segment mission-control software, high-fidelity simulation frameworks, telemetry standards, public data feeds, and the simulated hardware-abstraction layer that the closed-loop demo talks to in place of real flight hardware.

The subsystem lives in `../../src/aria/integrations/` and spans 35 Python files (~12,077 LOC as counted on disk). The private index dated the directory at 20 files/8,878 LOC — that figure is stale; the on-disk reality is larger due to subsequent additions (the full HAL sidecar package, several public data loaders, and the Dsremo correlator and channel-mapper sub-modules).

Everything here is TRL 3–5. Nothing has flown. Several bridges require the external tool to be installed separately before the live path activates; all of them degrade to a documented mock or error path when the dependency is absent.

---

## Where it sits in the architecture

ARIA's runtime is a message bus (`aria.bus`) surrounded by agent processes. The integrations layer attaches to both sides of that bus and to an external UDP socket:

```
                       ┌─────────────────────────────────┐
  Ground / external    │  OpenC3Bridge  —  bidirectional  │
  mission-control      │  (cmd → bus, bus telemetry → UI) │
  tools                └─────────────────────────────────┘
                                  │ aria.sensor.* / aria.command.*
                                  ▼
                          ┌───────────────┐
                          │  ARIA bus     │
                          └───────────────┘
                                  │
  Simulation /         ┌──────────┴──────────┐
  ephemeris            │                     │
  sources              ▼                     ▼
              BasiliskBridge           OpenMCTBridge
              Nasa42Bridge             (telemetry → WebSocket)
              GmatBridge
              (file I/O / subprocess)

                       ┌─────────────────────────────────┐
  Hardware             │  HAL sidecar  (UDP, HMAC-signed) │
  boundary             │  ActuatorBank — thruster / RW /  │
                       │  heater / payload                │
                       └─────────────────────────────────┘
```

Ground-tool bridges (OpenC3, OpenMCT) are bidirectional: commands arrive from the ground tool and land on the bus; sensor messages on the bus are forwarded back as telemetry. Simulation bridges (Basilisk, NASA 42, GMAT) are primarily inbound: they push physics state onto the bus. The HAL sidecar is an outbound UDP server that receives HMAC-signed command frames from the ARIA agent and drives a simulated (or, in principle, real) actuator bank.

---

## The bridges

### GMAT — General Mission Analysis Tool

**What it is.** GMAT is NASA's open-source high-fidelity trajectory tool. It propagates orbits with configurable force models (point-mass, harmonic gravity, drag, SRP, third-body) and supports differential-corrector targeting for Hohmann transfers, lunar transfers, and interplanetary trajectories. It produces ReportFile (ASCII tabular) and CCSDS-OEM ephemeris output.

**Adapter status: working adapter, GMAT binary optional.** `../../src/aria/integrations/gmat_bridge.py` (1,529 LOC) implements:

- `GmatScriptGenerator` — generates complete `.script` files for LEO, GEO Hohmann, lunar transfer, Mars transfer, and custom scenarios from a `MissionConfig` dataclass. Physical constants match GMAT defaults; coordinate frames cover EarthMJ2000Eq, EarthFixed, MoonInertial, MarsMJ2000Eq, and SunEcliptic.
- `GmatOutputParser` — pure-Python parsers for both ReportFile (whitespace-delimited, UTCGregorian or MJD epochs, full 13-column and compact Cartesian variants) and CCSDS-OEM. No GMAT installation required to parse.
- `GmatRunner` — wraps `subprocess.run(["GmatConsole", "--run", ...])`. Searches common install paths and `PATH`; reports `is_available = False` and returns a structured error when GMAT is absent. The `plan_trajectory()` method always writes the script to disk; execution is conditional on `is_available`.
- `GmatBridge` — high-level entry point. `trajectory_to_nav_update()` extracts a single ephemeris point into the `aria.sensor.nav.gps` payload shape that NavigationAgent expects.

Tests: `../../tests/integration/test_gmat_bridge.py`.

### OpenC3 / COSMOS

**What it is.** OpenC3 (formerly COSMOS) is an open-source command-and-telemetry system used for real spacecraft operations. It models a target/packet hierarchy; commands carry typed parameters, telemetry packets carry named items with engineering limits.

**Adapter status: working adapter, mock-mode default.** `../../src/aria/integrations/openc3_bridge.py` (1,523 LOC) implements a full bidirectional bridge. It defines:

- Five ARIA commands (`SAFE_MODE`, `LOAD_SHED`, `ATTITUDE_CHANGE`, `ORBIT_MANEUVER`, `ECLSS_ADJUST`) with typed parameters, state enumerations, range bounds, and hazardous flags — all with validated bus-topic wiring to the correct agent handlers.
- Six telemetry packets (`HEALTH_STATUS`, `NAVIGATION`, `POWER`, `THERMAL`, `PROPULSION`, `ECLSS`) with per-item limits tables.
- Topic extractors that flatten ARIA bus payloads into OpenC3 packet item dictionaries.
- `OpenC3ApiClient` — a live `aiohttp`-based JSON-RPC client for the OpenC3 `cmd-tlm-api` REST endpoint.
- `MockOpenC3ApiClient` — an in-process mock that records sent commands and injected telemetry; the bridge defaults to mock mode (`mock_mode=True` in `OpenC3Config`).
- `generate_target_cmd_tlm()` / `generate_plugin_txt()` — export OpenC3 target definition files so ARIA can be loaded into a running OpenC3 instance without manual config.

Live mode requires a running OpenC3 server; `aiohttp` must be installed. Tests: `../../tests/integration/test_openc3_bridge.py`.

### Basilisk

**What it is.** Basilisk (University of Colorado / AVS Lab) is a Python-wrapped C++ spacecraft simulation framework covering 6-DOF attitude/orbit dynamics, reaction wheels, thrusters, solar arrays, thermal node networks, and sensor models (star tracker, IMU, sun sensor, CSS).

**Adapter status: working adapter, Basilisk installation optional.** `../../src/aria/integrations/basilisk_bridge.py` (882 LOC) defines `BasiliskConfig`, a `SpacecraftState` dataclass (attitude quaternion, angular velocity, ECI position/velocity, Keplerian elements, power, thermal nodes, reaction wheel speeds, thruster flags), and three operating modes via `SimulationMode.LIVE / MOCK / REPLAY`. The bridge uses `Protocol`-typed stubs against Basilisk's messaging API and degrades to an internal mock telemetry generator when the `Basilisk` package is not importable.

### NASA 42

**What it is.** NASA 42 (Goddard Space Flight Center) is a multi-body attitude and orbit dynamics simulator with features not in Basilisk: IGRF magnetic field, solar pressure and albedo, multi-spacecraft simulation, and the DE430/DE440 planetary ephemeris.

**Adapter status: working adapter, NASA 42 binary optional.** `../../src/aria/integrations/nasa42_bridge.py` (466 LOC) generates `Inp_Sim.txt` and companion orbit/spacecraft config files from `Nasa42SimConfig`, `Nasa42OrbitConfig`, and `Nasa42SpacecraftConfig` dataclasses. It includes an IPC socket reader for receiving real-time state vectors when NASA 42 is running with `enable_ipc=True`, and a `Nasa42State` dataclass mapping to ARIA bus topics.

### OpenMCT

**What it is.** OpenMCT (Open Mission Control Technologies, NASA Ames) is a browser-based mission control dashboard. It consumes a dictionary endpoint (available telemetry points), a history endpoint, and a real-time WebSocket stream.

**Adapter status: working adapter, `aiohttp` required.** `../../src/aria/integrations/openmct_bridge.py` (593 LOC) subscribes to all `aria.sensor.*` bus topics, flattens nested payloads into individual `TelemetryPoint` records, maintains a rolling in-memory history buffer (configurable depth, default 50,000 points per key), and serves the OpenMCT dictionary and history via an `aiohttp` REST server on port 8082 by default. Real-time values are pushed over WebSocket to connected OpenMCT clients.

### ConjunctionWatch

**What it is.** ConjunctionWatch is a Python conjunction-screening library (not a REST API) used directly via import. It runs a Smart Sieve KD-tree pre-filter and then computes probability of collision (Pc) via Foster/Chan and Monte Carlo ensemble methods.

**Adapter status: tool wrapper, library must be installed.** `../../src/aria/integrations/conjunction_watch/tools.py` exposes two `ARIATool` subclasses (`ConjunctionWatchRunScreening`, `ConjunctionWatchGetManeuverPlan`). If `aria.conjunction.pipeline.runner` cannot be imported, the screening tool returns `success=False` with a clear error message — it does not return mock zero-conjunction data, which would be a safety hazard. See `./conjunction.md` for the full conjunction stack.

### Dsremo (anomaly detection)

**What it is.** Dsremo is ARIA's companion telemetry anomaly-detection service, which runs a 12-detector ensemble (EWMA, CUSUM, z-score, GMM, BOCPD, and others) over named telemetry channels.

**Adapter status: working adapter, local import preferred over REST fallback.** The `../../src/aria/integrations/dsremo/` sub-package contains four modules:

- `channel_mapper.py` — converts every numeric value in every ARIA bus sensor payload into a named channel (`eps.battery.soc_percent`, `thermal.battery_pack.temperature_c`, etc.) for Dsremo ingestion.
- `correlator.py` — cross-channel root-cause analysis; correlates anomaly signals across subsystems.
- `tools.py` — six `ARIATool` subclasses covering anomaly queries, single-channel and batch ingest, channel listing, health, and real-time score endpoints. Prefers direct Python import of `aria.dsremo.detection.*`; falls back to `httpx` REST calls.
- `websocket_tool.py` — subscribes to `ws://dsremo:8000/api/v1/alerts` and forwards alerts onto the ARIA bus as `aria.anomaly.dsremo` events. Returns a mock status when the server is unreachable.

The `../../src/aria/integrations/eden_iss_dsremo.py` script runs Dsremo on the real 2020 EDEN ISS ISS greenhouse telemetry (see below) as a validation harness.

### GenAstra (crew health and biosignatures)

**What it is.** GenAstra is a companion service providing radiation dose tracking, gene-expression models, protein structure prediction, and air-quality biosignature detection — crew-health layers that ARIA's ECLSS agent calls.

**Adapter status: tool wrapper, local import preferred.** `../../src/aria/integrations/genastra/tools.py` (187 LOC) exposes `ARIATool` subclasses for radiation damage prediction, gene expression, protein structure, and air quality. Prefers `aria.genastra.radiation.environment.RadiationEnvironment` via direct import; falls back to `httpx` REST calls against `http://localhost:8001`.

---

## Telemetry decoders and standards ingest

### SatNOGS live decoder path

`../../src/aria/integrations/satnogs.py` implements a caching REST client for the SatNOGS DB public API (CC-BY-SA 4.0). It pulls satellite catalogue entries, transmitter configurations, TLEs, and — with an `ARIA_SATNOGS_API_KEY` environment variable — raw telemetry frames.

`../../src/aria/integrations/satnogs_live.py` implements `SatNOGSLivePump`, a polling loop (default 60-second interval) that fetches new frames from the authenticated `/api/telemetry/` endpoint for a configured set of NORAD IDs, deduplicates by frame hex, calls registered `SatNOGSDecoder` instances, and passes decoded frames to registered `FrameSink` callbacks.

`../../src/aria/integrations/satnogs_decoders.py` provides two concrete decoders:
- `FuncubeOneDecoder` (NORAD 39444) — parses FUNcube-1 EPS frames: sequence number, bus voltage (0.04 V/LSB), battery temperature (0.5 °C/LSB), RSSI.
- `GenericAx25KissDecoder` — generic KISS/AX.25 frame stripper that extracts destination, source callsigns, and info-field length for any satellite not covered by a specific decoder.

`../../src/aria/integrations/kaitai_schema_registry.py` is a pure-Python registry that walks `data/satnogs_kaitai/` for `.ksy` files, parses their YAML `meta:` blocks and `doc-ref:` fields, and provides `lookup(schema_id)` and `search_by_keyword()`. The registry does not invoke the Kaitai compiler at runtime — it reads the schema text as a reference document, which the cognitive engine can inspect when deciding how to decode an unknown frame. On disk there are **156** Kaitai Struct schema files covering CubeSats, weather satellites, ham-radio satellites, and common frame layers (`ax25frames.ksy`, `csp.ksy`, etc.).

Tests: `../../tests/integration/test_satnogs.py`, `test_satnogs_live.py`, `test_satnogs_decoders.py`.

### Real-data ingest: EDEN ISS and NOAA GOES

`../../src/aria/integrations/eden_iss_loader.py` streams the EDEN ISS 2020 ISS greenhouse telemetry (Romberg et al. 2024, Zenodo 11485183) from CSV files under `data/raw/eden_iss/edeniss2020/`. It exposes a `TelemetryPoint` iterator and per-channel statistics for use as a ground-truth ECLSS anomaly benchmark.

`../../src/aria/integrations/noaa_goes_loader.py` loads GOES-16 SGPS Level-2 1-minute-average netCDF files (proton differential flux spectra, 13 energy bands, 1–404 MeV). It applies ICRP 123 dose coefficients to produce effective dose estimates and flags SEP events against the NOAA 10 PFU threshold. Requires `numpy` and the netCDF4 Python library. The bundled dataset is GOES-16 March 2025 (a quiet period with no large SPEs).

### Public data feeds

Several lightweight read-only clients complete the integrations layer:

- `../../src/aria/integrations/jpl_sbdb.py` — JPL Small-Body Database (CAD close-approach and SBDB orbital elements). No authentication. Responses are cached with a 1-hour TTL.
- `../../src/aria/integrations/launch_library.py` — TheSpaceDevs Launch Library 2 upcoming-launch schedule. Rate-limited to 15 anonymous calls/hour; ARIA caches with a 10-minute TTL.
- `../../src/aria/integrations/nasa_public/dsn_now.py` — NASA DSN-Now XML feed (antenna pointing and contact state, ~5-second refresh upstream, 30-second cache in ARIA).
- `../../src/aria/integrations/nasa_public/artemis_schedule.py` — curated milestone list for Artemis 2 and 3, with inline citations; not a live feed.

None of these feeds require authentication in their current form. They fail gracefully when the upstream is unreachable.

---

## The HAL sidecar

The HAL (Hardware Abstraction Layer) sidecar is a small UDP server that stands between ARIA's cognitive engine and real or simulated actuators. The closed-loop demo uses it instead of bit-banging hardware registers or spawning a full physics simulator.

Source: `../../src/aria/integrations/hal_sidecar/` (five files).

**Protocol (`protocol.py`).** Every command travels as a JSON frame carrying a monotonically increasing counter, a 32-character random hex nonce, a wall-clock timestamp, the command name, a parameter object, an issuer label, and an HMAC-SHA-256 signature over a canonical `counter|nonce|timestamp|sha256(body)` string. The server rejects frames that are missing or mismatched, older than 60 seconds, future-dated by more than 30 seconds, replay nonces (ring-buffer window of 4,096 nonces), or non-monotonic counters per issuer. The minimum secret length is 16 bytes; the secret is loaded from a file or environment variable at startup.

**Actuator bank (`actuators.py`).** `ActuatorBank` dispatches six command strings:

| Command | Model |
|---|---|
| `thruster.fire` | `ColdGasThruster` — Tsiolkovsky ΔV via GN2 cold-gas Isp (70 s, VACCO MiPS class), propellant-limited burn |
| `wheel.torque` | `ReactionWheelTriad` — 3-axis momentum accumulation, clamped at ±0.10 N·m torque and ±0.40 N·m·s momentum (Blue Canyon RWp050 parameters) |
| `heater.on/off/step` | `SurvivalHeater` — first-order thermal model, 10 W input, ~1,200 J/K mass (estimated Al component), 0.05 W/K MLI-equivalent leak |
| `payload.on/off` | Boolean flag |
| `ping` | Returns `pong` |

Magnetic torque rods, solar array drives, deployable structures, and propulsion modes beyond cold-gas monopropellant are not modelled. The `__main__.py` entry point (`python -m aria.integrations.hal_sidecar`) accepts `--bind`, `--port`, `--key-file`, `--dry-mass-kg`, `--propellant-kg`, and `--max-frame-age-s` arguments.

**Client (`client.py`).** `HalSidecarClient` is a synchronous UDP client with typed helper methods (`fire_thruster`, `apply_wheel_torque`, `heater_on/off/step`, `payload_on/off`, `ping`). It auto-increments the counter, generates a fresh nonce per call, signs the frame, sends it, and parses the reply into a `HalCommandResult`.

**Replacing the simulation with real hardware** requires substituting `actuators.py` with GPIO drivers for the target flight computer (e.g. Jetson Orin). The protocol, server loop, and client are hardware-independent.

The closed-loop demo drives the HAL sidecar over localhost. See `./replay.md` for how the Apollo 13 replay scenario uses it.

Tests: `../../tests/integration/test_hal_sidecar.py`.

---

## Current limitations

**Bridges that require the external tool to be installed.** GMAT (`GmatConsole` binary), Basilisk (`Basilisk` Python package), NASA 42 (42 binary with IPC mode), OpenC3 (running `cmd-tlm-api` server), ConjunctionWatch (`aria.conjunction.pipeline.runner`), Dsremo (`aria.dsremo.*` or running REST service), and GenAstra (`aria.genastra.*` or running REST service) each have a live path that silently or explicitly degrades when the dependency is absent. Callers must check `is_available`, the returned `success` flag, or the tool's error message before trusting the result.

**SatNOGS live telemetry requires an API key.** The public catalogue (satellites, transmitters, TLEs) is unauthenticated. Raw frame ingestion via `SatNOGSLivePump` requires `ARIA_SATNOGS_API_KEY`. Without it the pump raises at construction time.

**Kaitai schemas are reference material only.** The 156 `.ksy` files in `data/satnogs_kaitai/` are inspected by the cognitive engine as text. They are not compiled to Python decoders at runtime; the Kaitai compiler is not a dependency. Custom decoding beyond the two hand-written decoders in `satnogs_decoders.py` requires either compiling the relevant schema or writing a new `SatNOGSDecoder` subclass.

**HAL sidecar models a CubeSat-class actuator set.** The `ColdGasThruster` (Isp 70 s, 1 N), `ReactionWheelTriad` (BCT RWp050 parameters), and `SurvivalHeater` (10 W, first-order) are appropriate for a 6–12 kg CubeSat. Larger spacecraft, hydrazine or electric propulsion, and multi-wheel configurations are outside the current model.

**NOAA GOES loader requires `netCDF4` and the bundled dataset.** The loader reads from `data/raw/noaa_goes/`; if those files are absent or `netCDF4` is not installed, it raises at load time. The bundled dataset is a single quiet month (March 2025); it does not cover major SPE events.

**No ECSS standards ingest module exists on disk.** The README mentions ECSS standards as a covered topic; no `ecss*.py` file was found in the integrations directory or elsewhere in the source tree. This is a gap between the README description and the current code.

**No NASA LLIS ingest module exists on disk.** Similarly, the README mentions NASA LLIS (Lessons Learned Information System) ingest; no corresponding source file is present. Both items are aspirational and not yet implemented.

**No flight heritage.** All bridges are TRL 3–5 (working lab demonstrations). Nothing in this subsystem has been qualified, space-rated, or operated on an actual mission.

---

## Where to start reading

| Entry point | What it covers |
|---|---|
| `../../src/aria/integrations/gmat_bridge.py` | GMAT script generation, OEM/report parsing, trajectory → nav-update conversion |
| `../../src/aria/integrations/openc3_bridge.py` | Full bidirectional command/telemetry bridge; read `_build_aria_commands()` and `_build_aria_telemetry()` for the data model |
| `../../src/aria/integrations/hal_sidecar/__init__.py` | Public API of the HAL sidecar; `__main__.py` to run it standalone |
| `../../src/aria/integrations/hal_sidecar/protocol.py` | Frame signing and verification — the security-critical path |
| `../../src/aria/integrations/hal_sidecar/actuators.py` | Actuator physics models |
| `../../src/aria/integrations/satnogs_live.py` | Live frame poll loop and decoder dispatch |
| `../../src/aria/integrations/kaitai_schema_registry.py` | How the 156-schema Kaitai catalogue is indexed and served to the cognitive engine |
| `../../src/aria/integrations/dsremo/channel_mapper.py` | How ARIA sensor bus topics become Dsremo channel IDs |
| **Tests** | |
| `../../tests/integration/test_hal_sidecar.py` | Protocol replay protection, actuator dispatch, client round-trip |
| `../../tests/integration/test_gmat_bridge.py` | Script generation, report parser, OEM parser |
| `../../tests/integration/test_openc3_bridge.py` | Command validation, telemetry extraction, mock API round-trip |
| `../../tests/integration/test_satnogs.py` / `test_satnogs_live.py` / `test_satnogs_decoders.py` | SatNOGS client and decoder coverage |

Cross-links: the HAL sidecar is used directly by the closed-loop demo described in `./replay.md`. The ConjunctionWatch tools feed the conjunction-analysis layer documented in `./conjunction.md`.
