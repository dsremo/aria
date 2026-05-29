# Digital twin — parametric geometry, FEA, and engineering budgets

The digital twin is ARIA's self-model of the generation ship. It holds the
authoritative parametric geometry, material properties, structural and thermal
finite-element analyses, mass and power budgets, and a part-level dependency
graph. Downstream subsystems — the physics pods, the engineering-lab review
loop, and the 3-D web viewer — pull from the twin rather than from
hand-edited configuration constants, so every computed number traces back to
geometry and cited material data.

---

## Where it sits in the architecture

```
GenerationShipConfig ──▶ ShipParameters
                              │
          ┌───────────────────┼───────────────────────┐
          ▼                   ▼                       ▼
   geometry/             materials/              components_db
   (CadQuery solids)      material_db.py          (120-part BoH)
          │                   │
          ▼                   ▼
      mesher.py ──▶ solver.py (structural FEA)
                 └─▶ thermal_solver.py
                 └─▶ lbm_cfd.py / lbm_cfd_3d.py (CFD)
          │
          ▼
      bridge.py ──▶ TwinAnalysisResult ──▶ updated config
          │
          └──▶ export_gltf.py ──▶ ship.gltf (web 3-D viewer)
          └──▶ engineering_review.py ──▶ design review report
          └──▶ mass_budget.py / power_budget.py / deltav_budget.py
```

The `SimTwinBridge` in `bridge.py` closes the loop in both directions:
`GenerationShipConfig → geometry parameters → FEA → computed masses and
margins → back into config`. The physics pods (radiation, ECLSS, thermal
management) import from `parameters.py` and `materials/material_db.py`
directly; the twin is the single source of geometry truth they share.

---

## What's in the package

The package lives at `../../src/aria/digital_twin/` and contains 43 Python
files (~15,800 LOC total).

### Geometry modules (11 files under `geometry/`)

| Module | Builds |
|--------|--------|
| `hull.py` | Cylindrical pressure hull with hemispherical caps, 12 longitudinal stringers, ring frames, central spine truss, airlock hatch cutouts |
| `assembly.py` | Top-level `cq.Assembly` combining all sub-geometries; STEP and glTF export; centre-of-mass estimate |
| `compartments.py` | Seven internal zones (A–G) with inter-zone bulkheads |
| `habitat_ring.py` | O'Neill torus (500 m major radius, 20 m tube radius, 6 spokes, 1 RPM) |
| `radiator_array.py` | 100 panels × 500 m² (25 m × 20 m × 50 mm Al-7075 plate) |
| `reactor_module.py` | Nested shells: vessel, Li₂TiO₃ breeder blanket, B₄C shield, biological-shield sleeve |
| `shield_stack.py` | Seven-layer forward shield: LIDAR, plasma deflector, superconducting coil, tungsten mesh, ice ablation, Whipple bumper, structural hull |
| `propulsion.py` | Magnetic nozzle and magsail placeholder |
| `utility_systems.py` | LH₂ / LOX / N₂ cryo tanks, water and gas storage, cargo bay, docking ports, backup solar panels |
| `internal_details.py` | Bellows expansion joints, decks, rotation bearing, radiator hinges, coolant piping |
| `accessories.py` | Antenna dishes, escape pods, viewports |

All eleven modules use [CadQuery](https://cadquery.readthedocs.io/) to produce
`cq.Workplane` or `cq.Assembly` solids. Dimensions are pulled from
`../../src/aria/digital_twin/parameters.py` (`ShipParameters` dataclass), so
changing a hull radius or wall thickness propagates consistently across every
module. The `simplified` flag on `hull.create_hull_structure` and
`habitat_ring.create_habitat_ring` switches between lightweight wire
representations (suitable for a 16 GB workstation) and full solid geometry
suitable for Gmsh meshing.

The top-level pipeline (`run_pipeline.py`) calls `assemble_ship()` and then
passes the hull geometry to Gmsh for meshing; the full solid path takes
several minutes.

### FEA solvers

**Structural FEA** — `../../src/aria/digital_twin/solver.py`

Linear-elastic and J2 elastoplastic solver built on `scipy.sparse`. Supports
4-node (tet4, constant-strain) and 10-node (tet10, 4-point Gauss) tetrahedra.
Boundary conditions: fixed Dirichlet, surface pressure, body-force gravity.
Von Mises stress post-processing at element centroids; Incompletely
Conditioned Conjugate Gradient (ICCG) for meshes above 50 K DOFs. Nonlinear
elastoplastic solve (radial-return J₂, Simo & Hughes 1998) is opt-in via
`bridge.analyze(enable_plasticity=True)`.

**Thermal FEA** — `../../src/aria/digital_twin/thermal_solver.py`

Steady-state heat-conduction solver: ∇·(k∇T) + Q = 0 on the same tet4 meshes.
Stefan-Boltzmann radiation boundary condition at radiator surfaces
(T_space = 2.725 K, Fixsen 2009). ICCG solver.

**Mesher** — `../../src/aria/digital_twin/mesher.py`

Wraps the Gmsh Python API. Accepts a STEP file (from `cq.exporters.export`)
or parametric primitives (cylinder, sphere). Returns a `meshio.Mesh` object
with second-order tet10 elements by default.

**CFD** — `../../src/aria/digital_twin/lbm_cfd.py` and `lbm_cfd_3d.py`

2-D D2Q9 lattice Boltzmann (BGK collision, Smagorinsky LES, Coriolis forcing,
double distribution function thermal coupling) for habitat cross-section
airflow. `lbm_cfd_3d.py` extends this to a 3-D D3Q19 lattice for full-room
simulations; both run CPU-only.

### Materials database

`../../src/aria/digital_twin/materials/material_db.py` contains
**67 materials** organised into twelve categories:

| Category | Materials (examples) |
|---|---|
| Structural alloys | Ti-6Al-4V, EUROFER97, Inconel-718, Al-7075-T6, Al-6061-T6, Al-2024-T3, Al-2219-T87, AISI-4340, Maraging-300, 17-4PH-H900 |
| Stainless steels | SS-316L, AISI-304L, 15-5PH-H900 |
| Titanium | Ti-3Al-2.5V, CP-Ti-Grade4 |
| Nickel superalloys | Waspaloy, Hastelloy-X, Rene-41, A286, MP35N |
| Shielding | UHMWPE, B4C, Tungsten, Water-Ice, Borated-Concrete, Kevlar-49 |
| Ceramics | Alumina-99.5, SiC-Sintered, Zirconia-YSZ, Silicon-Nitride, HfB2, Li2TiO3 |
| Composites / advanced | IM7-977-3-CFRP, SiC-SiC-CMC, CNT-Composite |
| Thermal management | NaK-78, Aerogel, MLI-Mylar, Pyrolytic-Graphite-Sheet, CuMo-15-85, Vapor-Chamber-Cu, Liquid-Hydrogen, Potassium, Sintered-Nickel |
| Polymers | PEEK, PTFE, Polycarbonate, Vespel-SP1, PEI-Ultem9085, Nylon-PA12 |
| Seals / adhesives | Viton-FKM, RTV-Silicone, PTFE-Tape, Loctite-EA9394 |
| Electronics / PCB | FR4-G10, Copper-Foil-PCB, SAC305-Solder, Kovar, GaAs |
| ECLSS / biological | Activated-Carbon, Lithium-Hydroxide, Zeolite-13X |
| Superconductors | MgB2, Nb3Sn, YBCO |

Each record is a frozen `MaterialProperty` dataclass carrying density,
Young's modulus, Poisson's ratio, 0.2 % yield strength, UTS, thermal
conductivity, specific heat, CTE, emissivity, melting point, Basquin fatigue
limit and exponent, and a `source` citation string. Properties that are not
applicable for a given material (liquids, granular media, brittle ceramics
without a defined yield) are explicitly set to `None`.

### Components database (Bill of Hardware)

`../../src/aria/digital_twin/components_db.py` catalogs **120 hardware
components** in eight categories: fasteners (32), electrical (19), valves
(17), seals (13), actuators (11), sensors (11), pipes (10), bearings (7).
Each `Component` record carries a standard part number (ISO, NAS, MS,
AMS, MIL, or manufacturer reference), key dimensions, mass per piece,
maximum operating temperature, pressure rating where applicable, and a
citation. The categories span bolts, nuts, washers, rivets, studs,
Helicoil inserts, O-rings, spiral-wound gaskets, hatch seals, ball/angular
and magnetic bearings, stepper and BLDC motors, reaction wheels, ball-screw
linear actuators, ball and check valves, relief valves, AN pipe fittings,
Swagelok quick-disconnects, wiring harnesses, circuit breakers, sensors,
and tubing.

### Part manifest (Bill of Materials)

`../../src/aria/digital_twin/part_manifest.py` defines a **36-part ship
manifest** linking each physical assembly to a `MATERIAL_DATABASE` entry with
parametric dimensions and computed mass. The manifest covers structure (hull,
end caps, spine truss, ring frames), shield layers, reactor module, propulsion
nozzle, habitat ring and spokes, radiator panels, ECLSS core, and computing.
Mass is derived analytically (thin-wall cylinder and shell formulae) from the
same `ShipParameters` dimensions used by the geometry modules.

### Mass and power budgets

`../../src/aria/digital_twin/mass_budget.py` rolls up the 36-part manifest
plus subsystem-level mass fractions (propellant, crew, manufacturing,
electronics) into a total vs the 100 Mg config target, reporting per-subsystem
percentages and a discrepancy figure.

`../../src/aria/digital_twin/power_budget.py` does a bottom-up power
accounting from the 66 MWe reactor (200 MW thermal × 33 % Brayton cycle)
against all consumers: ECLSS pumps and scrubbers (~1,650 kW for 1,000 crew),
grow-lights (8,000 kW), reactor cryocooler (5,000 kW), propulsion attitude
control, computing, and habitat services. Cruise total comes to ~15.3 MW,
leaving a 77 % margin for propulsion thermal loads.

`../../src/aria/digital_twin/deltav_budget.py` maintains a per-phase Δv
ledger for the full mission (acceleration, coast, deceleration, contingency).

### Dependency graph

`../../src/aria/digital_twin/dependency_graph.py` represents the ship as a
directed acyclic graph of subsystem dependencies. An edge `A → B` means A
cannot function without B. Edges carry a kind tag (`power`, `coolant`,
`structural`, `data`, `fuel`, `ecs`) and a `critical` flag (immediate failure
vs degraded mode). The graph supports forward-reachability queries ("what goes
down if the reactor fails?") and backwards-reachability ("what does the
habitat ring depend on?"). Taxonomy follows NASA/SP-2016-6105 Rev2 §4.5.

### Other notable modules

| Module | Role |
|--------|------|
| `bridge.py` | `SimTwinBridge` — bidirectional sim ↔ twin closed loop |
| `engineering_review.py` | Automated design review: mass, power, Δv, structural, thermal, radiation |
| `export_gltf.py` | Procedural glTF 2.0 writer; feeds the web 3-D viewer |
| `optimizer.py` | COBYLA gradient-free mass minimisation subject to stress and thermal constraints |
| `fea_visualizer.py` | Von Mises / temperature / displacement plots (matplotlib/Plotly) |
| `radiation_geometry.py` | Shield-stack geometry used by the radiation Monte-Carlo |
| `eclss_bridge.py` | Maps twin volume and surface area to ECLSS simulator inputs |
| `degraded_mode.py` | Component failure simulations and structural/thermal impact assessment |
| `nasa42_models.py` | Inertia tensor from CadQuery geometry for NASA42 attitude dynamics |

---

## Key design decisions

### Why CadQuery (not FreeCAD/OCCT or STEP import)

CadQuery is Python-native, scriptable from the same codebase, and produces
`cq.Workplane` objects that can be passed directly to exporters (`export_step`,
`export_stl`) without a GUI or file-round-trip. That makes the geometry a
first-class data structure: every dimension is a Python expression referencing
`ShipParameters`, and changing one number re-derives the entire model. The
trade-off is real: CadQuery is built on OCCT but does not expose the full
OCCT API, so operations like swept-section profiles, fillet chaining, or
STEP-format assembly metadata are limited. The geometry produced here is
honest parametric primitives — cylinders, spheres, toroids, boxes — not the
detailed swept surfaces that a proper CAD package would produce for
manufacturing drawings.

### Cited materials database — why not MMPDS/MAPTIS files

The `material_db.py` entries are derived from published handbooks and
datasheets (MMPDS-17, MIL-HDBK-5J, ASM Handbook, ASTM, ISO, manufacturer
technical bulletins) and carry explicit `source` strings down to table and
section numbers. This is traceable to public literature without the export-
controlled access required for MMPDS raw files or the MAPTIS database. Values
should be treated as reference numbers for simulation, not as design-allowable
data: they have not gone through the coupon-test statistical basis (A-basis /
B-basis) required for a real spacecraft structural qualification. The
`CNT-Composite` entry is explicitly labelled `NOT YET FLIGHT-QUALIFIED` and
carries projected composite values scaled from single-tube measurements via
Halpin-Tsai micromechanics.

### How mass and power budgets roll up

`mass_budget.py` combines two approaches. For the 36 parts where geometry
exists, mass is computed from the `ShipParameters` dimensions and the
`MATERIAL_DATABASE` density. For subsystems without explicit geometry
(propellant, crew, consumables), it applies mass fractions taken from
generation-ship design literature (Long 2012; Matloff 2005). The budget
includes a `discrepancy_pct` field comparing computed total against the
`ship_mass_kg` config target; earlier versions showed a 77 % discrepancy
caused by a hull-length / wall-thickness mismatch which has since been
corrected by deriving both from `ShipParameters`.

`power_budget.py` works bottom-up from subsystem specifications rather than
top-down from a power fraction. Every consumer carries a `source` attribute
citing the specification that justifies its wattage.

### Dependency graph design

The graph is declarative — a flat list of `(src, dst, kind, critical, note)`
tuples compiled into networkx-compatible adjacency structures. Keeping it flat
makes it diffable and auditable without traversing code logic. The `critical`
flag distinguishes hard failures (loss of reactor power) from degraded-mode
scenarios (loss of one radiator wing halves rejection capacity but does not
immediately cause mission failure).

---

## Data and citations

The materials database references the following published sources by number:

| Source | What it covers |
|--------|----------------|
| MMPDS-17 (Battelle, 2024) | Structural alloys: Ti-6Al-4V, Al-series, steel alloys, PH stainless, Inconel-718 — strength, fatigue |
| MIL-HDBK-5J | Legacy cross-check for Basquin fatigue exponents |
| ASM Handbook Vol. 1 / 2 | Steels, nonferrous alloys — density, CTE, conductivity |
| ASTM A240, A193, B265, B338, B209 | Material specifications for stainless, titanium, aluminium |
| AMS 5662/5663, AMS 5644, AMS 4911 | Alloy-specific heat-treatment conditions |
| NASA-STD-5001B | Fatigue guidance for space structures |
| NASA/TP-2013-217375 (Cucinotta 2014) | GCR shielding mass sizing (ice ablation layer) |
| NASA SP-100, Mason 2018 NASA/TM-2018-219910 | Kilopower / potassium heat-pipe radiator |
| ITER MPH, Federici 2017, Tavassoli 2014 | EUROFER97 RAFM steel properties |
| Fahrenholtz 2014, Opeka 2004 | HfB2 ultra-high-temperature ceramic |
| Dunn & Reay 1994, Chi 1976, Faghri 1995 | Heat-pipe working fluids (potassium, sintered nickel wick) |
| Nagamatsu 2001, Iwasa 2009 | Superconductors: MgB₂, Nb₃Sn |
| Ginley & Cava 1989, Larbalestier 2001 | YBCO HTS properties |
| IPC-4101C, IPC-4562, IPC-TM-650 | PCB substrate and copper foil |
| Parker O-Ring Handbook ORD 5700, ASME B16.20, API 520/526 | Seals and valves |

There are no separate data files under `data/materials/` in the current tree;
all values are inlined in `material_db.py` with their citations.

---

## Current limitations

**Parametric geometry, not production CAD.** Every solid is a CadQuery
primitive or boolean combination of primitives. Swept splines, filleted
joints, and mating interface geometry are absent. The twin is suitable for
mass roll-ups, broad FEA load cases, and visualisation — not for generating
manufacturing drawings or interface-control documents.

**Reference material data, not design allowables.** The 67 material entries
are derived from published handbooks and datasheets for simulation purposes.
They have not been put through statistical coupon-test programmes (A-basis /
B-basis per MMPDS Chapter 2) and are not certified design allowables. The
`CNT-Composite` entry is explicitly speculative (projected Halpin-Tsai bulk
values from single-tube measurements; insufficient fatigue data).

**No flight heritage.** The twin models a conceptual generation ship at
TRL 3–5. Nothing in this package has been exercised against hardware
telemetry or validated against physical test articles.

**FEA at assembly level, not joint level.** The structural solver treats
the hull as a continuous elastic body. Bolted-joint stiffness, weld properties,
and bearing clearances are modelled separately in
`../../src/aria/digital_twin/assembly_interfaces.py` but are not yet
integrated into the Gmsh mesh.

**CPU-only CFD.** The 3-D D3Q19 LBM in `lbm_cfd_3d.py` runs on CPU. A
habitat room at ~2,430 cells takes under a second per step, but scaling to
full-corridor models without a GPU port is not practical.

**Component catalog vs aerospace-standard BoH.** The 120-component database
draws from manufacturer catalogs and aerospace standards (ISO, NAS, ASME,
MIL-DTL, SKF, Swagelok, maxon). It is a design reference, not a flight-
certified hardware manifest with AS9100 traceability.

---

## Where to start reading

| File | What to read first |
|------|--------------------|
| `../../src/aria/digital_twin/parameters.py` | `ShipParameters` dataclass — every dimension and its derivation |
| `../../src/aria/digital_twin/geometry/assembly.py` | `assemble_ship()` — how all sub-geometries combine |
| `../../src/aria/digital_twin/geometry/hull.py` | `create_hull_structure()` — most-referenced single geometry |
| `../../src/aria/digital_twin/materials/material_db.py` | `MATERIAL_DATABASE` dict — 67 entries with citations |
| `../../src/aria/digital_twin/bridge.py` | `SimTwinBridge.analyze()` — the full analysis cycle |
| `../../src/aria/digital_twin/run_pipeline.py` | End-to-end CLI pipeline (6 steps) |
| `../../src/aria/digital_twin/engineering_review.py` | `run_engineering_review()` — top-level design review |
| `../../src/aria/digital_twin/solver.py` | `FEASolver` — structural FEA implementation |
| `../../src/aria/digital_twin/mass_budget.py` | `compute_mass_budget()` |
| `../../src/aria/digital_twin/dependency_graph.py` | `_RAW_EDGES` list — subsystem dependency topology |

Tests live under `tests/digital_twin/` and cover the FEA solvers (thin-wall
analytical reference cases), material database lookups, budget roll-ups, and
glTF export. Run them with:

```
pytest tests/digital_twin/ -m "not slow"
```
