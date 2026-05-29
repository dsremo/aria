# Physics pods — analytical and parametric domain models for spacecraft reasoning

The physics subsystem is ARIA's domain-compute layer: 199 Python files across 34 subdirectories under `../../src/aria/physics/`, grouped into 34 pods (the README calls the count "26"; the disk has 34 subdirectories that each constitute a distinct physical domain). The pods are pure computation — they receive inputs, apply equations rooted in published references, and return results. They do not maintain state, do not read telemetry, and do not issue commands. The cognitive engine calls them via tool wrappers; the subsystems compute and the engine decides.

The README is explicit about the research status: **TRL 3–5, nothing has flown, no DO-178C / NPR-7150.2D Class B paperwork exists.** The models here are analytical and parametric; high-fidelity alternatives (FEA solvers, GEANT4 Monte Carlo, MCNP/FLUKA neutron transport, Grad-Shafranov PDE solvers) are deferred or present only as optional upgrade paths.

---

## Where it sits in the architecture

The cognitive engine (`src/aria/cognitive/`) holds a registry of 55+ tools. When the engine needs a physics answer it calls the relevant tool, which calls into `src/aria/physics/<pod>/`. The physics layer has no upward imports — it does not know about the engine, the constitution, or the monitor. This keeps the domain models independently testable and prevents the compute layer from influencing any decision pathway.

The two cross-cutting primitives in the physics package root are:

- `../../src/aria/physics/uncertainty.py` — a four-tier `ConfidenceTier` (A: validated in window; B: extrapolation ≤ 10×; C: extrapolation > 10× or no flight validation; D: no model) with a `Prediction` dataclass that carries value, tier, units, model citation, and falsification path. TIER_D predictions raise `TierDQuotedError` if asked to yield a number, preventing silently-zero values from reaching operator dashboards.
- `../../src/aria/physics/__init__.py` — declares the citation and test-case obligations every pod must meet.

---

## The pods

The 34 pod directories on disk, in alphabetical order, with their scope and primary methods:

**`attitude/`** (Pod C4) — Ship-level attitude dynamics and CMG actuators. Models a 4-CMG skewed-pyramid cluster (Wie 1998 §7.4), dual-spin angular-momentum bookkeeping, Modified Rodrigues Parameter (MRP) feedback control with gain tuning, and the Margulies-Aubrun singularity metric for CMG steering. The `mrp_control.py` module integrates the Euler attitude ODE; `cmg_steering.py` computes pseudoinverse steering and detects imminent singularities. CMG desaturation via RCS impulse is provided in `momentum_management.py`.

**`bioregen/`** — MELiSSA-fidelity (ESA Micro-Ecological Life Support System Alternative) bioregenerative life-support at 1–3 person scale. Six compartments: anaerobic liquefaction (C-I), photoheterotrophic bacteria (C-II), nitrification (C-III), higher-plant cultivation (C-IV-A), Spirulina photobioreactor (C-IV-B), and crew metabolic loads from NASA BVAD. Implemented as a steady-state mass balance; dynamic instabilities, trace contaminant kinetics, and micro-nutrient balances are explicitly out of scope. Validation data comes from ESA MELiSSA pilot-plant annual reports 2009–2024 and the Lasseur 2010 / Hendrickx 2006 published compartment fluxes.

**`cardio/`** (Pod K2) — Cardiovascular deconditioning under partial-g. Biphasic Convertino 1996 plasma-volume kinetics, cephalic fluid-shift first-order lag, cardiac-mass atrophy ODE, SANS progression probability (Mader 2011 / Lee 2018), orthostatic-intolerance logistic model (Buckey 1996), and ARED countermeasure effectiveness factor (Lee 2015).

**`cfd/`** (Pods H1 + H3) — Habitat fluid mechanics and compressible flow primitives. Sutherland dynamic viscosity (White 2006), ideal-gas EoS for gas mixtures, dimensionless numbers (Re, Ra, Pr, Gr, Ma), Blasius flat-plate skin friction and displacement thickness, Launder-Spalding k-ε closure constants and Smagorinsky LES constant, log-law wall function, Courant-Friedrichs-Lewy time-step bound, exact Sod shock-tube reference state (Toro 2009 Table 4.1), Churchill-Chu 1975 natural-convection Nusselt correlation for vertical plates, and an ISS US-Lab cabin-turnover-time benchmark (Son, Zhang & Lu 2015). Phase equilibria (vapor pressure, latent heat, phase safety margin) for O₂, N₂, H₂O, CO₂, and several alkali metals via Antoine and Clausius-Clapeyron. This is not a finite-volume CFD solver; the scope note explicitly defers that to a downstream effort.

**`corrosion/`** — High-temperature oxidation kinetics (Wagner parabolic, linear, Cabrera-Mott logarithmic), Pilling-Bedworth ratio, Godard 1967 pitting depth, atomic-oxygen (ATOX) LEO erosion for Al-oxide and Kapton (Brinza 2001), and ASTM E1820 stress-corrosion-cracking threshold check. Material presets: Ti-6Al-4V, EUROFER97, Mo-Re, Al 6061.

**`cruise_drag/`** — Interstellar-cruise drag and accretion. Ram-pressure drag acceleration and stopping length for ISM passage, Bondi-Hoyle accretion rate (Bondi & Hoyle 1944, Bondi 1952), and Chandrasekhar 1943 dynamical friction. ISM phase table covers the Local Bubble, Local Interstellar Cloud, Warm Neutral Medium, and Cold Neutral Medium (Ferrière 2001, Redfield & Linsky 2008).

**`dark_sector/`** (Pods M1-M3) — Speculative-physics upper-bound budgets. Dark-matter drag upper bound and cosmological-constant acceleration (bounds from Read 2014, XENONnT), MICROSCOPE weak-equivalence-principle differential-acceleration bound (Touboul et al. 2017), and time-drift bounds on the fine-structure constant α (Webb 2011), proton-to-electron mass ratio μ (Ubachs 2016), and Newton's constant G (Hofmann & Müller 2018). These pods do not add forces to the simulator; they emit upper-bound rows for the navigation error budget so downstream consumers can prove "this effect is below mission sensitivity."

**`departure/`** (Pod A3) — Earth-to-deep-space departure mechanics. Tsiolkovsky rocket equation (single and multi-stage), escape velocity, hyperbolic excess velocity, vis-viva speed, Oberth perihelion-burn gain (Δv_∞² ≈ 2 v_p Δv_burn), sphere-of-influence radius, patched-conic slingshot Δv (2 v_∞ sin δ), Forward 1984 laser-sail acceleration (2P/(mc)), and a `DepartureDeltaVBudget` accounting dataclass. Tests verify the Saturn V TLI Δv against Curtis 3rd ed Example 6.1 (3.18 km/s ± 20 m/s), PSP perihelion speed against Fox 2016 (192 km/s ± 1 %), and Forward's 10 GW / 1 tonne sail example.

**`electrical/`** — Spacecraft electrical power models. Solar-cell temperature and radiation degradation (triple-junction GaAs/Ge, Bett 2007, Messenger 2001, BOL efficiency 29.5–30 %); NMC lithium-ion battery with Arrhenius calendar aging, cycle aging, C-rate derating, and SOC/thermal safety gates; Joule/AC/eddy-current resistive heating with Matula 1979 temperature-dependent resistivity and skin depth (Incropera 2007).

**`eps/`** — Electrical Power System vendor-cell models. Spectrolab XTJ-Prime and Azur Space 3G30A triple-junction solar cells; Saft VES180 50 Ah 180 Wh Li-ion cell (flown on numerous LEO and GEO spacecraft). An ISS validation module checks modelled power against published ISS EPS specifications.

**`fire_safety/`** — Spacecraft fire models. Arrhenius global reaction rates, Metghalchi-Keck 1982 laminar flame speed with pressure and temperature corrections, adiabatic flame temperature, NASA-STD-6001B limiting-oxygen-index criterion, Ronney 1985 microgravity flame-speed correction factor, and Quintiere 1995 flashover heat-release-rate threshold. Fuel presets: methane, ethanol, n-heptane, hydrogen.

**`fusion_xsec/`** (Pod E1) — D-T fusion cross sections and tritium breeding. Bosch-Hale 1992 Maxwellian-averaged D-T reactivity fit, volumetric fusion power density, single-level Breit-Wigner capture cross section (zero-temperature kernel, Doppler broadening deferred to ENDF pipeline), and ⁶Li/⁷Li tritium breeding ratio gate against the Abdou 2015 TBR ≥ 1.10 requirement and ENDF/B-VIII.0 thermal cross-section anchors (Brown 2018).

**`gravity/`** (Pod A1) — Orbital mechanics, N-body integration, and space environment. Newtonian two-body analytics (Kepler's third law, vis-viva, Hohmann transfer Δv, planetary capture Δv), gravitational slingshot in 3-D vector form, star proper-motion propagation, N-body integrator with RK4 and Dormand-Prince 8(7) adaptive step, Circular Restricted 3-Body Problem (CR3BP), MEGNO chaos indicator, IAS15 Gauss-Radau 15th-order implicit integrator, SPICE/DE440 ephemeris wrapper (optional dependency, degrades gracefully), orbit determination, zonal-harmonic perturbations (J₂, J₃, J₄), atmospheric density for drag, SGP4 TLE propagation, IGRF dipole magnetic field, Van Allen belt dose and flux models, Lorentz force and gyroradius, and spacecraft-charging risk assessment. The SPICE-dependent tests (Voyager Jupiter flyby, DE440 Mars position, Sun-SSB offset) are marked deferred pending the spiceypy + kernel install.

**`gravity_relativistic/`** (Pod A2) — Post-Newtonian and relativistic gravity effects. Newtonian tidal tensor E^i_j = (GM/r³)(δ − 3n̂n̂) and its total over N perturbers, post-Newtonian Schwarzschild correction factor, gravitational time-dilation rate (dτ/dt = 1 + Φ/c²), gravitational redshift (Δν/ν = ΔΦ/c²), Pound-Rebka shift, Lense-Thirring frame-dragging precession rate (Ω_LT = GJ(3(Ĵ·r̂)r̂ − Ĵ)/(c²r³)), Peters-Mathews gravitational-wave power (32G⁴m₁²m₂²(m₁+m₂)/(5c⁵r⁵)), Oort A/B galactic tidal tensor, and hull tidal-loading diagnostics (differential acceleration profile, bending moment, and tension along a finite-length hull).

**`hull_fatigue/`** — Consumer-layer bridge combining pressure-vessel hoop/axial stress (F1), Goodman mean-stress correction + Basquin S-N life (F2), Miner cumulative damage (F2), and constrained thermal-stress (F5) into a single `HullFatigueReport` for the docking-event plus day-night thermal-cycle load case.

**`impact/`** (Pod F4) — Hypervelocity impact and Whipple shield mechanics across four velocity regimes. Hertzian elastic contact (v < ~50 m/s); Hugoniot shock propagation via the linear Rankine-Hugoniot U_s = c₀ + s u_p relation (Marsh 1980); crater depth from the Christiansen 1993 / NASA TM-105002 scaling law; Whipple New-Non-Optimum ballistic-limit equation (NNO-BLE) for the hypervelocity regime (3–15 km/s); ejecta mass (Schönberg scaling); relativistic-dust kinetic energy and momentum; and ISM ablation models for dust-grain impact, gas sputtering, proton kinetic energy, and material ablation depth at cruise velocities. The ultra-relativistic regime (> 0.01 c) is explicitly flagged as an ESTIMATE regime.

**`life_support/`** — ECLSS atmosphere and humidity models. O₂/CO₂ cabin partial-pressure mass balance with crew metabolic loads (NASA BVAD rates), CDRA two-bed molecular-sieve scrubbing efficiency decay, Sabatier reactor CO₂ methanation fraction, OGA electrolysis O₂-generation rate, CO₂ incapacitation and O₂ hypoxia risk thresholds, saturation vapour pressure (Magnus approximation), dew-point, relative humidity, and condensation-risk assessment.

**`low_g_fluids/`** (Pod H2) — Capillary-dominated and low-gravity fluids. Young-Laplace pressure jump and capillary-rise (Jurin's law); Bond, Capillary, Weber, Ohnesorge, and Marangoni dimensionless numbers; Abramson 1966 / NASA SP-106 sloshing natural frequencies for upright cylindrical and centrifuged ring tanks; Carreau, power-law, and Bingham non-Newtonian viscosity models (with a Yeleswarapu 1998 blood-rheology preset); regime classification (capillary-dominated vs inertia-dominated).

**`mhd_plasma/`** (Pod D1) — Tokamak and fusion-plasma MHD primitives. Alfvén speed, ion gyroradius, plasma beta, Spitzer resistivity (Wesson 2011), Kruskal-Shafranov ideal-kink limit (q_a ≥ 1), Greenwald density limit (Greenwald 2002), Troyon beta limit (Troyon 1984), Eich heat-flux width scaling (Eich 2013 Nucl Fusion), Dreicer runaway-electron field (Dreicer 1960), and Rosenbluth-Putvinski avalanche amplification (Rosenbluth & Putvinski 1997). Reference ITER baseline parameters are bundled. Grad-Shafranov PDE solver, neoclassical transport ODE, and Sauter bootstrap-current fit are deferred, requiring PETSc/SLEPc.

**`navigation_budget/`** — Consumer-layer navigation uncertainty budget. Aggregates per-effect position-error contributions (dark-matter drag, cosmological-constant acceleration, varying constants, ISM ram pressure, gravitational perturbations) via quadrature sum into a `NavigationBudget` report. Provides preset mission profiles for Mars transit and Proxima Centauri cruise. Imports only from the physics primitives; no simulator dependency.

**`propulsion/`** — Propellant tank pressurization physics. Blowdown pressure histories (isothermal and adiabatic closed forms), regulated pressurant mass budget (Larson & Wertz 1999), Henry's-law pressurant absorption by propellant (Wiktorowicz 1972), and absorbed-pressurant volume fraction. Pressurant gas presets: helium, nitrogen, GN₂.

**`radchem/`** (Pod J2) — Water radiolysis and polymer radiation damage. Primary G-values with LET dependence (Spinks & Woods 1990, Elliot & Bartels 2009, Pastina & LaVerne 2001), H₂ source term, hydrogen steady-state concentration and outgassing rate in shield water, Charlesby-Pinner 1959 sol fraction for crosslinked polymers, and Clough 1988 Weibull mechanical degradation for elongation and tensile retention. Polymer presets include HDPE, PTFE, and EPDM.

**`radiation_transport/`** — Analytical dose proxy with optional GEANT4 Monte Carlo upgrade path. The analytical backend (Cucinotta 2014 GCR LET model + NIST PSTAR stopping powers + NCRP-153 flux) is always available; the GEANT4 backend (Allison et al. 2016) activates when `geant4-pybind` is installed (~2 GB). The analytical backend is explicitly described as a screening tool not validated for shielding-design TRL > 4. The `preferred_backend()` function selects GEANT4 if installed with a warning otherwise.

**`rigid_body/`** (Pod C3) — Rigid-body rotation library. Inertia tensor from point masses, parallel-axis (Steiner) transform, principal-axis diagonalization, Euler equations of motion (τ = (dL/dt)_body + ω × L), RK4 torque-free and externally-torqued integrators, torque-free precession rate, fast-spin (gyroscope) precession rate, unit-quaternion kinematics (multiply, normalize, kinematic matrix, quaternion-to-rotation-matrix, axis-angle construction), and 3-1-3 Euler angles. Used by both the rotating-frame pod and the attitude-control pod.

**`rotating_frame/`** (Pod C1) — Habitat ring kinematics. Closed-form centrifugal (ω²r), Coriolis (−2Ω × v), and Euler (−dΩ/dt × r) accelerations in vector and scalar form; differential-g gradient across crew body height; deflection of a dropped object at deck level; paraboloid free-surface shape; cosine-smoothed spin-up profile with peak angular acceleration. Designed for a rigid ring of configurable radius and nominal rotation rate.

**`sc_charging/`** (Pod D2) — Spacecraft surface and deep-dielectric charging. Ambient electron/ion and photoemission current densities, orbital equilibrium surface potential, Child-Langmuir sheath thickness, Debye length, CSDA range for electrons in dielectrics, peak internal electric field in a parallel-plate geometry (Lai 2012, NASA-HDBK-4002A), electrostatic-discharge trigger probability and arc energy. Dielectric material presets (Kapton, PTFE, FR-4, polyimide) with permittivity and breakdown field.

**`shield_ble/`** — Consumer-layer bridge reporting Whipple NNO ballistic-limit diameter and impact-regime classification for a given shield layer stack. Thin wrapper over `impact/` F4 primitives; no new physics.

**`solid_mechanics/`** (Pods F1 + F2) — Elasticity, plasticity, fatigue, fracture, creep, modal analysis, and radiation embrittlement. Lamé constants, shear/bulk modulus, deviatoric stress and J₂ invariant, von Mises yield check and effective plastic strain increment (J₂ radial-return), thin-wall hoop and axial stress; Basquin S-N life, mean-stress corrections (Goodman, Gerber, SWT, Morrow), Miner cumulative damage, ASTM E1049 rainflow cycle counting (Downing-Socie algorithm), Coffin-Manson and Manson-Hirschberg strain-life; Paris-Erdogan crack growth rate, Walker Δ K effective, block-integrated crack growth, stress intensity factor K_I (edge and center crack), critical crack length, Ti-6Al-4V K_Ic; beam and plate natural frequencies, cylindrical-shell ring and flexural frequencies, critical spin speed, dynamic magnification factor; Norton-Bailey creep rate and damage for Ti-6Al-4V, EUROFER97, Inconel 718, Mo-Re; Larson-Miller parameter and rupture life; radiation embrittlement DBTT shift and master-curve fracture toughness (RG 1.99 / JEAC 4201 for steel; GCR displacement cross section for structural alloys).

**`thermal_protection/`** — Ablative TPS models. Goldstein 1965 charring-ablator recession rate and cumulative ablation depth for a parametric heat pulse. Material presets: AVCOAT, PICA, SLA-561V, carbon-phenolic. Used for entry-vehicle TPS sizing.

**`thermal_radiator/`** — Space radiator thermodynamics. Net heat rejection accounting for the CMB 2.7 K sink temperature (Fixsen 2009), Gardner 1945 rectangular-fin efficiency (corrects the naïve isothermal area × T⁴ estimate by 10–30 %), solar-albedo effective sky temperature for near-Sun missions, Carnot ceiling efficiency, and iterative area solver. Replaces the earlier lumped P = εσAT⁴ model.

**`thermal_stress/`** (Pod F5) — Thermal expansion and thermomechanical coupling. Linear thermal strain ε^θ = α ΔT, full thermal-strain tensor for isotropic and anisotropic (composite) materials, uniaxial/plane-stress/triaxial constrained thermal stresses, through-thickness gradient peak stress (Boley-Weiner 1960), bimetallic-strip curvature (Timoshenko 1925), and Kingery 1955 thermal-shock figure of merit and margin. Material CTE table covers Ti-6Al-4V, Al 7075-T6, EUROFER97, Invar, and several ceramics (MMPDS-17, Lindau 2005).

**`transport/`** (Pod E2) — Neutron and nucleon radiation transport. Cucinotta 2014 GCR differential/integral proton flux with solar modulation, exponential shielding attenuation with macroscopic cross section, Letaw 1983 p-A inelastic cross-section parameterization, ICRP-60 quality factors per GCR species, HZE dose breakdown by ion species, SPE large-event and extreme-event dose models (NCRP-153), secondary-neutron budget (spallation yield, exit flux, buildup factor, ICRP-74 neutron dose coefficients), albedo neutron dose, pion/muon decay chain kinematics (PDG lifetimes), and Groom 2001 muon CSDA range in water. Full discrete-ordinates (S_N) solver and ENDF/B-VIII.0 tabulated cross-section wrapper are deferred.

**`venting/`** — Choked-flow venting and breach physics. Isentropic choked mass-flow and exit velocity, vent thrust and torque coupling on the spacecraft (models the Cassini-class slow-ΔV scenario), time-stepped hull-breach decompression (Bernoulli + real-gas compressibility — models the Soyuz 11 class of rapid cabin loss), stuck-open valve failure mode, and open-loop water-flash sublimator thermal model (Apollo PLSS class).

**`vestibular/`** (Pod C2) — Human vestibular response to rotating-frame motion. Semicircular-canal torsion-pendulum transfer function and step response (Steinhausen 1933 / Van Egmond 1949), otolith overdamped first-order response (Grant & Best 1987), cross-coupled Coriolis illusion when the crew tilts their head in the spinning ring (Guedry & Benson 1978), Oman 1982/1990 motion-sickness dose model, and cumulative-adaptation probability sigmoid (Young 2019). Naive and adapted 5 rpm / 10 rpm rotation thresholds for motion sickness are provided as operational outputs.

---

## Validation against published missions

The test suite (`../../tests/unit/physics/`) records these mission-anchored checks:

- **Saturn V TLI Δv** (`test_departure_a3.py` §9.1): Tsiolkovsky with J-2 engine Isp 421 s and Apollo 15 S-IVB mass ratio reproduces Curtis 3rd ed Example 6.1 at 3,180 m/s ± 20 m/s (NASA MR-15 NTRS 19720005108).
- **Parker Solar Probe perihelion speed** (`test_departure_a3.py` §9.2): vis-viva at PSP's 9.86 R_☉ perihelion matches Fox 2016 (192 km/s) within 1 %.
- **Earth-to-Mars Hohmann Δv** (`test_gravity_a1.py` §9.3): matches Curtis 3rd ed Table 8.3.
- **Proxima Centauri proper motion** (`test_gravity_a1.py`): star position propagated over decades against the Hipparcos / Gaia catalog entry bundled in `gravity/proper_motion.py`.
- **ISS cabin turnover time** (`test_cfd_h1_h3.py`): Churchill-Chu Nusselt + ISS US-Lab geometry reproduces the Son, Zhang & Lu 2015 SAE benchmark.
- **Sod shock-tube star state** (`test_cfd_h1_h3.py`): exact solution matches Toro 2009 Table 4.1 reference values.
- **Pound-Rebka gravitational redshift** (`test_gravity_relativistic_a2.py`): gh/c² for Harvard Tower geometry matches the 1959 Pound-Rebka result.
- **Lunar TLI ΔV / Artemis 2 reentry peak-g**: the README states "Lunar TLI ΔV within 0.28 % of Apollo 11; reentry peak-g matches Artemis 2 at L/D = 0.3" — these checks live in the simulation scenarios (`src/aria/simulation/`) not in the physics unit tests.

The test suite does not include GEANT4 Monte Carlo validation, FEA mesh convergence studies, or full CFD-solver benchmarks. Those are stated future work.

---

## The ESTIMATE-tag situation

Grepping the physics source for bare `# ESTIMATE` tags:

```
grep -rn "# ESTIMATE" src/aria/physics | wc -l
```

returns **4** tagged lines across the entire physics subdirectory:

| File | Tag |
|------|-----|
| `gravity/space_environment.py:517` | GTO transit time assumed 2 h apogee-to-perigee passage |
| `cardio/sans_model.py:18` | SANS progression rate fit to Mader 2011 cohort without independent validation |
| `cfd/phase_transitions.py:170` | Alkali-metal triple-point vapor pressure set to 1.0 Pa (order-of-magnitude) |
| `cfd/phase_transitions.py:172` | Alkali-metal critical pressure set to 25 MPa (order-of-magnitude) |

This is a low count for the physics subdirectory specifically. Context from the README: across the full `src/aria/` codebase (all 35 subpackages), **904 `# ESTIMATE` tags** remain, with ~466 described as "bare reasons" awaiting published citations. The physics pods are the *first* priority for closing this gap. The four tags found in `src/aria/physics/` represent the residue in the physics layer after recent citation work; the bulk of the 904-tag debt lives elsewhere in the codebase (simulation scenarios, digital-twin defaults, agent heuristics).

The `# ESTIMATE` convention is the honest-uncertainty system's early-warning tier. The full runtime tier system lives in `uncertainty.py`: a TIER_C prediction (extrapolation > 10×, or no flight validation) is tagged at output time; a TIER_D prediction raises at the API surface before the value reaches an operator. The SANS model note (`cardio/sans_model.py`) is an example of a constant that is cited but flagged because the cohort sample is small and inter-study spread is wide.

---

## Current limitations

**Analytical models only.** Every physics pod uses closed-form equations and low-order parameterizations. None use a meshed solver, a Monte Carlo transport kernel, or a discretized PDE. Specifically:

- The `cfd/` pod provides turbulence closures (k-ε constants, Smagorinsky coefficient) and correlation-level benchmarks; it does not contain a finite-volume Navier-Stokes solver.
- The `radiation_transport/` pod defaults to the Cucinotta 2014 analytical proxy; GEANT4 is an optional heavyweight add-on, not the standard path.
- The `transport/` pod (neutron transport) uses exponential attenuation and the Letaw 1983 parametric cross-section fit; full S_N discrete-ordinates or MCNP/FLUKA kernels are deferred.
- The `solid_mechanics/` pod provides rainflow, Paris-law crack growth, creep, and modal analytics; no FEA mesh, no plastic return-mapping integration beyond the radial-return yield-surface step.
- The `mhd_plasma/` pod covers algebraic MHD stability limits; the Grad-Shafranov equilibrium solver requiring SLEPc/PETSc is deferred.
- The `bioregen/` pod is a steady-state mass balance; dynamic instabilities and kinetic micro-models are explicitly out of scope.

**No flight heritage.** As the README states: "No flight heritage. No DO-178C / NPR-7150.2D Class B paperwork." The physics pods are research-grade. Mission-validation test cases compare against textbook worked examples and published mission reports; they do not constitute airworthiness certification.

**Optional dependencies.** `gravity/ephemeris.py` requires `spiceypy` + a DE440.bsp kernel (several hundred MB); without them it degrades to analytic Kepler. `radiation_transport/` requires `geant4-pybind` (~2 GB) for the high-fidelity path; without it only the analytical Cucinotta proxy runs.

---

## Where to start reading

Entry points, in recommended reading order:

1. **`../../src/aria/physics/__init__.py`** — the citation and test-case obligations every pod must meet.
2. **`../../src/aria/physics/uncertainty.py`** — the four-tier confidence system and `Prediction` dataclass; understanding this first makes the pods' output contracts clear.
3. **`../../src/aria/physics/gravity/__init__.py`** — the largest pod; covers two-body, N-body, slingshot, ephemeris, and space-environment in one namespace.
4. **`../../src/aria/physics/departure/__init__.py`** — the departure chain from Tsiolkovsky through Oberth to laser sail; self-contained and well-tested.
5. **`../../src/aria/physics/solid_mechanics/__init__.py`** — the deepest structural pod; covers elasticity through creep through radiation embrittlement.

Corresponding test files:

- `../../tests/unit/physics/test_gravity_a1.py` — Hohmann, Proxima proper motion, N-body energy conservation.
- `../../tests/unit/physics/test_departure_a3.py` — TLI Δv, PSP perihelion, Forward laser-sail, Oberth gain.
- `../../tests/unit/physics/test_gravity_relativistic_a2.py` — tidal tensor, Pound-Rebka, Lense-Thirring, Peters-Mathews.
- `../../tests/unit/physics/test_cfd_h1_h3.py` — Sutherland viscosity, Blasius flat plate, Sod shock tube, ISS turnover time.
- `../../tests/unit/physics/test_solid_mechanics_f1_f2.py` — thin-wall stress, von Mises, Basquin life, Paris crack growth.
- `../../tests/unit/physics/test_impact_f4.py` — Hertzian contact, Hugoniot shock, Whipple BLE, ISM ablation.
