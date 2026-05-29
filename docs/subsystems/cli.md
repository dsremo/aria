# The `aria` CLI — command dispatcher for ARIA

The `aria` command is the single entry point for all ARIA operations: running
spacecraft simulations, inspecting system health, managing data, generating
reports, and interfacing with external tools.  Every subcommand routes through
[`src/aria/cli/main.py`](../../src/aria/cli/main.py), which builds the
top-level argparse tree and dynamically imports the appropriate service module.

All commands accept two global flags:

| Flag | Description |
|---|---|
| `--output {text,json}` | Output format (default: `text`) |
| `-v` / `--verbose` | Enable verbose error traces |
| `--version` | Print version and exit |

---

## Entry points

Defined in [`pyproject.toml`](../../pyproject.toml):

```
aria           →  aria.cli.main:main
aria-dashboard →  aria.simulator.web_dashboard:main
```

`aria` is the full CLI documented here.  `aria-dashboard` launches the
standalone web dashboard; see [./engineering-lab.md](./engineering-lab.md) for
dashboard configuration and usage.

---

## Command groups

### `aria sim`

Source: [`src/aria/cli/sim.py`](../../src/aria/cli/sim.py).
Runs and analyses spacecraft simulations.  See
[./simulation.md](./simulation.md) for the underlying simulation architecture.

#### `aria sim run`

Run a single mission simulation.

| Flag | Default | Description |
|---|---|---|
| `--mission` / `-m` | `leo-iss` | Mission type: `leo-iss`, `leo-sso`, `geo`, `geo-comms`, `interstellar` |
| `--duration` | — | Simulation duration in seconds (orbital) |
| `--speed` / `-s` | `0` | Real-time speed multiplier (0 = max) |
| `--years` | `100` | Duration in years (interstellar only) |
| `--crew` | `4` | Crew size |
| `--altitude` | — | Override orbit altitude (km) |
| `--agents` / `--no-agents` | agents on | Enable or disable ARIA agents |
| `--dashboard` / `-d` | off | Start telemetry dashboard alongside simulation |
| `--port` | `8080` | Dashboard server port |

```
aria sim run --mission leo-iss
aria sim run --mission interstellar --years 500 --crew 100
aria sim run --mission geo --altitude 35786 --no-agents
aria sim run --mission leo-sso --dashboard --port 9090
```

Reports are auto-saved to `reports/<mission-name>_report.{txt,json}` after each run.

#### `aria sim montecarlo`

Run Monte Carlo statistical analysis across multiple seeds.

| Flag | Default | Description |
|---|---|---|
| `--mission` / `-m` | `interstellar` | Mission type |
| `--runs` / `-n` | `100` | Number of independent runs |
| `--years` | `100` | Duration per run (years) |
| `--crew` | `4` | Crew size |
| `--seeds` | `42` | Base random seed |

```
aria sim montecarlo --runs 50 --years 200 --crew 10
aria sim montecarlo --mission interstellar --runs 100 --years 100 --output json
```

#### `aria sim compare`

Compare Legacy (2024-era) technology against Breakthrough technology modes
across multiple seeds.

| Flag | Default | Description |
|---|---|---|
| `--years` | `200` | Mission duration |
| `--seeds` | `20` | Seeds per technology mode |

```
aria sim compare --years 200 --seeds 20
```

#### `aria sim scenario`

Run a named historical failure scenario with injected faults.

| Flag | Required | Description |
|---|---|---|
| `--name` / `-n` | yes | Scenario key: `apollo-13`, `salyut-7`, `columbia`, `mir-collision` |

```
aria sim scenario --name apollo-13
aria sim scenario --name salyut-7
```

#### `aria sim generation-ship`

Full multi-century generation ship simulation.

| Flag | Default | Description |
|---|---|---|
| `--years` | `1000` | Journey duration |
| `--crew` | `4` | Initial crew size |
| `--mode` | `breakthrough` | `legacy` or `breakthrough` technology mode |
| `--seed` | `42` | Random seed |

```
aria sim generation-ship --years 1000 --mode breakthrough
aria sim generation-ship --years 200 --mode legacy --crew 200
```

#### `aria sim first-1000-days`

Day-by-day simulation tracking mass balance (water, food, O2, CO2) and
expert-panel commentary.

| Flag | Default | Description |
|---|---|---|
| `--crew` | `1000` | Crew size |
| `--days` | `1000` | Days to simulate |
| `--seed` | `42` | Random seed |
| `--report` | off | Print full mission report at end |

```
aria sim first-1000-days --crew 500 --days 1000
aria sim first-1000-days --report --output json
```

#### `aria sim target`

Run a generation-ship simulation aimed at a specific star.

| Flag | Default | Description |
|---|---|---|
| `--star` | — | Star key (e.g. `proxima_centauri`) |
| `--list` | off | List all available star targets |
| `--crew` | `4` | Crew size |
| `--mode` | `breakthrough` | Technology mode |
| `--seed` | `42` | Random seed |

```
aria sim target --list
aria sim target --star proxima_centauri --crew 100
```

#### `aria sim target-sweep`

Run all catalog stars within a distance limit and tabulate outcomes.

| Flag | Default | Description |
|---|---|---|
| `--max-distance` | `15.0` | Maximum distance in light-years |
| `--crew` | `4` | Crew size |
| `--mode` | `breakthrough` | Technology mode |
| `--seed` | `42` | Random seed |

```
aria sim target-sweep --max-distance 10 --mode legacy
```

#### `aria sim validate`

Run a physics validation pass against a simulation run and report any
conservation-law violations.

| Flag | Default | Description |
|---|---|---|
| `--years` | `200` | Simulation years to validate |
| `--seed` | `42` | Random seed |

```
aria sim validate --years 100
aria sim validate --years 200 --output json
```

#### `aria sim duration-sweep`

Compare mission outcomes (events, terminal challenges, food ratio, hull
integrity) across fixed duration milestones (50, 100, 200, 500, 1000 years) in
both technology modes.  Takes no flags.

```
aria sim duration-sweep
```

---

### `aria system`

Source: [`src/aria/cli/system.py`](../../src/aria/cli/system.py).
Inspect and manage the ARIA runtime environment.

#### `aria system status`

Print ARIA version, source-file counts, dependency availability, and data-source inventory.

```
aria system status
aria system status --output json
```

#### `aria system health`

Run importability and instantiation checks across eight subsystems (core,
simulation engine, interstellar simulation, shield system, crew ecosystem,
reporting, health dashboard, agent framework).

```
aria system health
```

#### `aria system agents list`

List all nine registered ARIA agents with their module paths and import status.

```
aria system agents list
```

#### `aria system agents restart <name>`

Signal a restart request for a named agent (requires a running ARIA
coordinator instance to take effect).

```
aria system agents restart ThermalAgent
aria system agents restart NavigationAgent
```

#### `aria system benchmark`

Run five performance benchmarks: interstellar 1000-year simulation,
challenges orchestrator 1000-year run, telemetry history store (100 K writes),
Basilisk single-orbit step (skipped if Basilisk is not installed), and health
dashboard (10 K snapshots).

```
aria system benchmark
aria system benchmark --output json
```

#### `aria system config show`

Print the active runtime configuration as a key-value table.

```
aria system config show
```

#### `aria system config set <key> <value>`

Record a configuration override (persisted via a YAML config file when
`--config` is provided; otherwise informational only).

```
aria system config set simulation.default_crew 100
```

---

### `aria data`

Source: [`src/aria/cli/data.py`](../../src/aria/cli/data.py).
Import, replay, list, and convert mission data.

#### `aria data import`

Import data from an external source into the ARIA data directory.

| Flag | Required | Values | Description |
|---|---|---|---|
| `--source` / `-s` | yes | `noaa`, `battery`, `eden`, `voyager` | Data source type |
| `--path` / `-p` | yes | path | Path to source data (file or directory) |

```
aria data import --source noaa --path /data/goes16/
aria data import --source battery --path /data/nasa_battery/B0005.mat
aria data import --source voyager --path /data/voyager.zip
```

#### `aria data replay`

Replay a real-data file through the ARIA processing pipeline.

| Flag | Required | Values | Description |
|---|---|---|---|
| `--source` / `-s` | yes | `noaa`, `battery`, `eden` | Data source type |
| `--file` / `-f` | yes | path | Data file path |

```
aria data replay --source battery --file data/raw/nasa_battery/B0005.mat
aria data replay --source noaa --file data/raw/noaa_goes/goes16_2023.csv
```

#### `aria data list`

List all data sources and their availability under `data/`.

```
aria data list
```

#### `aria data convert`

Convert between data formats using source-specific converters or pandas.

| Flag | Required | Values | Description |
|---|---|---|---|
| `--from` | yes | `netcdf`, `csv`, `mat`, `json` | Source format |
| `--to` | yes | `csv`, `json`, `parquet` | Target format |
| `--input` / `-i` | yes | path | Input file |
| `--output` / `-o` | no | path | Output file (auto-generated if omitted) |

```
aria data convert --from netcdf --to csv --input goes16.nc
aria data convert --from mat --to csv --input B0005.mat --output battery.csv
```

---

### `aria report`

Source: [`src/aria/cli/report.py`](../../src/aria/cli/report.py).
Generate and inspect mission reports saved by simulation runs.

#### `aria report generate`

Generate a report from a saved mission JSON.

| Flag | Required | Default | Description |
|---|---|---|---|
| `--mission-id` / `-m` | yes | — | Mission identifier |
| `--format` / `-f` | no | `text` | `text`, `json`, or `html` |

```
aria report generate --mission-id leo-iss_2024-01-01
aria report generate --mission-id leo-iss_2024-01-01 --format html
```

#### `aria report list`

List all reports found in the `reports/` directory with their available formats and sizes.

```
aria report list
```

#### `aria report score`

Show the score breakdown for a specific mission.

| Flag | Required | Description |
|---|---|---|
| `--mission-id` / `-m` | yes | Mission identifier |

```
aria report score --mission-id leo-iss_2024-01-01
```

---

### `aria tools`

Source: [`src/aria/cli/tools.py`](../../src/aria/cli/tools.py).
Interface with external spacecraft simulation and operations tools.
All subcommands degrade gracefully when the corresponding tool is not
installed.

#### `aria tools basilisk run`

Run a Basilisk astrodynamics simulation.

| Flag | Default | Values | Description |
|---|---|---|---|
| `--orbit` / `-o` | `leo` | `leo`, `leo-sso`, `meo`, `geo`, `heo`, `lunar` | Orbit preset |
| `--duration` / `-d` | `5520` | — | Duration in seconds |
| `--timestep` | `1.0` | — | Integration timestep in seconds |

```
aria tools basilisk run --orbit leo --duration 5520
aria tools basilisk run --orbit geo --duration 86400
```

Requires Basilisk (`pip install bsk`).  Returns a warning and exits cleanly if
the package is absent.

#### `aria tools basilisk orbits`

List all built-in orbit presets with altitude and inclination.

```
aria tools basilisk orbits
```

#### `aria tools gmat plan`

Plan a trajectory using the GMAT bridge.

| Flag | Default | Description |
|---|---|---|
| `--from` | `earth` | Departure body |
| `--to` | `mars` | Arrival body |
| `--launch-date` | — | Launch date (`YYYY-MM-DD`) |

```
aria tools gmat plan --from earth --to mars
aria tools gmat plan --from earth --to jupiter --launch-date 2030-06-01
```

Requires GMAT R2022a+ and `GMAT_ROOT` to be set.

#### `aria tools openmct start`

Start the ARIA telemetry server that an OpenMCT front-end can connect to.

| Flag | Default | Description |
|---|---|---|
| `--port` / `-p` | `8080` | Server port |

```
aria tools openmct start --port 8080
```

#### `aria tools openc3 status`

Show the status of the OpenC3 command-and-control bridge.

```
aria tools openc3 status
```

---

### `aria shield`

Source: [`src/aria/cli/shield.py`](../../src/aria/cli/shield.py).
Analyse the seven-layer relativistic shield system.

#### `aria shield analyze`

Compute ISM particle flux, dust-grain kinetic energy, and sputtering erosion
for a given velocity and journey distance.

| Flag | Default | Description |
|---|---|---|
| `--velocity` / `-v` | `0.1` | Cruise velocity as fraction of c |
| `--distance` / `-d` | `100` | Journey distance in light-years |
| `--shield-mass` | `10000` | Initial ablation shield mass in kg |

```
aria shield analyze --velocity 0.1 --distance 4.2
aria shield analyze --velocity 0.2 --distance 100 --shield-mass 36800
```

#### `aria shield budget`

Print the mass and power budget for all seven shield layers (detection,
deflection, magnetic, electrostatic, ablation, Whipple, structural hull).
Takes no flags.

```
aria shield budget
aria shield budget --output json
```

#### `aria shield erosion`

Calculate sputtering erosion rates for a specific material.

| Flag | Default | Values | Description |
|---|---|---|---|
| `--velocity` / `-v` | `0.1` | — | Cruise velocity as fraction of c |
| `--material` / `-m` | `carbon` | `carbon`, `beryllium`, `tungsten`, `ice`, `aluminum` | Shield material |
| `--area` | `100.0` | — | Forward-facing area in m² |
| `--years` | `1000` | — | Journey duration in years |

```
aria shield erosion --velocity 0.1 --material carbon --years 1000
aria shield erosion --velocity 0.2 --material tungsten --area 50
```

---

### `aria crew`

Source: [`src/aria/cli/crew.py`](../../src/aria/cli/crew.py).
Simulate long-duration crew population dynamics, closed-loop ecosystems, and
genetic diversity.

#### `aria crew lifecycle`

Simulate crew births, deaths, and population change year by year.

| Flag | Default | Description |
|---|---|---|
| `--years` | `200` | Simulation duration |
| `--initial-crew` | `100` | Starting crew size |

```
aria crew lifecycle --years 200 --initial-crew 100
aria crew lifecycle --years 500 --initial-crew 500 --output json
```

#### `aria crew ecosystem`

Simulate a closed-loop life-support ecosystem tracking elemental mass balances.

| Flag | Default | Description |
|---|---|---|
| `--years` | `500` | Simulation duration |

```
aria crew ecosystem --years 500
```

#### `aria crew genetics`

Analyse genetic diversity decay, inbreeding coefficient, and frozen embryo
reserve over multiple generations.

| Flag | Default | Description |
|---|---|---|
| `--population` | `50` | Initial population |
| `--years` | `300` | Simulation duration |

```
aria crew genetics --population 200 --years 1000
```

---

### `aria mission`

Source: [`src/aria/cli/mission.py`](../../src/aria/cli/mission.py).
Query and manage the mission persistence store (SQLite via `MissionStore`).
Missions are saved automatically after each `aria sim run`.

#### `aria mission list`

List all saved missions with ID, type, date, status, score, and grade.

```
aria mission list
aria mission list --output json
```

#### `aria mission show <id>`

Show full details for a saved mission: timing, telemetry counts, orbit range,
severity distribution, challenge states, and any logged errors.

```
aria mission show abc123
aria mission show abc123 --output json
```

#### `aria mission delete <id>`

Delete a mission record from the store.

```
aria mission delete abc123
```

---

### `aria analyze`

Source: [`src/aria/cli/analyze.py`](../../src/aria/cli/analyze.py).
Parameter sweeps and comparative analysis.

#### `aria analyze sweep`

Sweep a single parameter across a list of values and compare outcomes.

| Flag | Default | Values | Description |
|---|---|---|---|
| `--param` | `crew_size` | `crew_size`, `velocity`, `years` | Parameter to sweep |
| `--values` | `4,10,50` | comma-separated | Values to test |
| `--years` | `100` | — | Simulation years per run |

```
aria analyze sweep --param crew_size --values 4,10,50,200
aria analyze sweep --param velocity --values 0.05,0.1,0.2 --years 200
```

#### `aria analyze diff`

Compare two missions by ID.  Full implementation pending; currently prints
usage guidance.

#### `aria analyze batch`

Run a batch of missions from a YAML config.  Full implementation pending;
currently prints usage guidance.

---

### `aria test`

Source: [`src/aria/cli/test_runner.py`](../../src/aria/cli/test_runner.py).
Validation shortcuts that complement the standard `pytest` test suite.

#### `aria test quick`

Run a 30-second import and smoke validation (imports, Basilisk, interstellar
simulation, generation ship, health dashboard).

```
aria test quick
```

#### `aria test full`

Invoke the full `pytest tests/` suite with `-q --tb=line`.

```
aria test full
```

#### `aria test smoke`

Run `tests/integration/test_system_smoke.py` only.

```
aria test smoke
```

---

## Common recipes

**Start fresh and confirm the environment is healthy:**

```
aria system status
aria system health
aria test quick
```

**Run a LEO mission with the live dashboard, then review the report:**

```
aria sim run --mission leo-iss --dashboard --port 8080
aria report list
aria report generate --mission-id <id-from-list> --format html
```

**Compare technology modes over a long interstellar journey:**

```
aria sim compare --years 500 --seeds 20
aria sim generation-ship --years 1000 --mode legacy
aria sim generation-ship --years 1000 --mode breakthrough
```

**Sweep crew size to find the population floor for mission viability:**

```
aria analyze sweep --param crew_size --values 4,10,20,50,100,200 --years 200
```

**Assess the shield before committing to a target star:**

```
aria sim target --list
aria shield analyze --velocity 0.1 --distance 4.2
aria shield erosion --material carbon --velocity 0.1 --years 43
aria sim target --star proxima_centauri --crew 100
```

**Machine-readable pipeline (pipe JSON output into jq):**

```
aria sim run --mission interstellar --years 200 --output json | jq .score
aria shield analyze --velocity 0.1 --distance 100 --output json
aria mission list --output json | jq '.[0].id'
```

---

## Where to start reading

| File | Why |
|---|---|
| [`src/aria/cli/main.py`](../../src/aria/cli/main.py) | Authoritative argparse tree; all command groups and flags are defined here |
| [`src/aria/cli/sim.py`](../../src/aria/cli/sim.py) | Largest subcommand module; shows the full dispatch pattern and how simulation results are rendered |
| [`src/aria/cli/shield.py`](../../src/aria/cli/shield.py) | Self-contained physics; good second read — no external imports needed to understand the output |
| [`src/aria/cli/formatting.py`](../../src/aria/cli/formatting.py) | `OutputContext`, `print_table`, `print_kv` — used by every module; read this before adding a new subcommand |
| `tests/integration/test_system_smoke.py` | End-to-end smoke tests that exercise the same dispatch path |

The dispatch chain is: `main()` → `build_parser()` → `dispatch()` →
`importlib.import_module(service_map[args.service])` → `mod.dispatch(args)` (or
`mod.handle_<service>(args, output_json)` for `crew`, `analyze`, and `test`).
