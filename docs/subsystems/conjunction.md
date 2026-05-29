# Conjunction screening — orbital collision assessment from TLE ingest to CDM

The conjunction subsystem implements a full CARA-style (Conjunction Assessment Risk Analysis) pipeline for screening tracked space objects against an orbital catalog, computing probability of collision (Pc), and emitting CCSDS-formatted Conjunction Data Messages (CDMs). It operates as both an embedded ARIA subsystem that feeds the navigation agent and a standalone REST service under the `ConjunctionWatch` product label.

The subsystem spans 60 Python files across nine sub-packages. All physics and algorithm choices are conservative estimates referencing published CARA and CCSDS practice; nothing here is flight-qualified or operationally certified.

---

## Where it sits in the architecture

The conjunction subsystem has two integration paths:

**Embedded path — navigation agent tool.** `aria.integrations.conjunction_watch.tools` exposes two `ARIATool` subclasses (`ConjunctionWatchRunScreening`, `ConjunctionWatchGetManeuverPlan`) that call `aria.conjunction.pipeline.runner` directly. The navigation agent (and via it the cognitive engine) invokes these tools to get RED/YELLOW conjunction alerts before any maneuver decision. If the conjunction package is not importable, the tool returns `success=False` — it does not silently return zero events, which would be a safety hazard.

**Standalone path — REST API.** `aria.conjunction.api.app` (FastAPI, `create_app()`) exposes HTTP endpoints for screening, Pc computation, maneuver planning, CDM generation, and fleet risk. The API wraps the same pipeline objects as the embedded path.

```
  NavigationAgent / CognitiveEngine
         │  (ARIATool calls)
         ▼
  aria.integrations.conjunction_watch.tools
         │
         ▼
  aria.conjunction.pipeline.runner.ConjunctionPipeline
         │
  ┌──────┴──────────────────────┐
  │                             │
  ▼                             ▼
screening.SmartSieveScreener   probability.PcCalculator
  (4-stage filter cascade)       (Foster / Chan / Monte Carlo)
  │                             │
  ▼                             ▼
conjunction.TCAFinder          pipeline.CDMWriter
                               pipeline.AlertClassifier
                               maneuver.ManeuverPlanner
```

The conjunction subsystem reads TLE catalogs from three optional external sources — Space-Track.org (`data.spacetrack_client`), Celestrak (`data.celestrak_client`), and LeoLabs (`data.leolabs_session`) — and can ingest CDMs published by 18 SDS or TraCSS.

See [./products.md](./products.md) for the `conjunction-screener` product wrapper and [./integrations.md](./integrations.md) for the `ConjunctionWatch` bridge details.

---

## The CARA-style pipeline

`ConjunctionPipeline.run()` in [`../../src/aria/conjunction/pipeline/runner.py`](../../src/aria/conjunction/pipeline/runner.py) orchestrates the full flow. The seven stages are:

### Stage 0 — TLE ingest

[`../../src/aria/conjunction/data/tle_parser.py`](../../src/aria/conjunction/data/tle_parser.py) parses 2-line and 3-line TLE text (standard and Alpha-5 extended NORAD IDs up to 359,999). It validates checksums, extracts classical orbital elements, converts Brouwer mean motion to osculating semi-major axis with a first-order J2 correction, solves Kepler's equation with Newton-Raphson to get true anomaly, and wraps the result as a `SpaceObject` carrying both a parsed `OrbitalElements` struct and a `sgp4.api.Satrec` ready for propagation.

Hard-body radius is estimated from a type × RCS-size table (`RADIUS_TABLE_M`); known objects (ISS, Hubble, CSS Tianhe) use explicit radii. Object type (PAYLOAD / DEBRIS / ROCKET_BODY) is auto-classified from the catalog name string.

Three catalog clients support live ingest: `SpaceTrackClient`, `CelestrakClient`, and `LeolabsSession`. `data.catalog.py` provides a unified catalog abstraction over them.

### Stage 1 — SGP4 propagation

[`../../src/aria/conjunction/propagation/sgp4_propagator.py`](../../src/aria/conjunction/propagation/sgp4_propagator.py) wraps Brandon Rhodes' `sgp4` package (C++ backend, MIT license). It propagates a `SpaceObject` to any UTC epoch and returns a `StateVector` in the TEME frame (km, km/s). Three entry points are provided: `propagate()` (single object, single epoch), `propagate_batch()` (single object, time range), and `propagate_many_batch()` (N objects × M epochs, NumPy array output).

TLE age is enforced: a warning is logged when the TLE epoch is more than 3 days old; a `StaleTLEError` is raised at 7 days. The code documents the reason — a 7-day-old LEO TLE accumulates ~10 km of position error, larger than typical miss distances.

[`../../src/aria/conjunction/propagation/frames.py`](../../src/aria/conjunction/propagation/frames.py) converts TEME → ECI (J2000) via precession/nutation, ECI → ECEF via GMST, ECI → RTN, and projects the 3D miss vector and covariance onto the B-plane (encounter plane) for 2D Pc computation.

### Stage 2 — Smart Sieve pre-filter

[`../../src/aria/conjunction/screening/screener.py`](../../src/aria/conjunction/screening/screener.py) runs a four-stage cascade that reduces an O(N²) all-pairs problem to a small candidate set:

**Stage 0 — Spatial index.** For catalogs of 500 or more objects, a `scipy.spatial.cKDTree` on (altitude, inclination) bins candidate pairs in O(N log N) before the cascade starts ([`screening/spatial_index.py`](../../src/aria/conjunction/screening/spatial_index.py)).

**Stage 1 — Apogee-Perigee (APS).** [`screening/apogee_perigee.py`](../../src/aria/conjunction/screening/apogee_perigee.py) uses a sweep-line on objects sorted by perigee radius. A pair survives only if their altitude bands (perigee–apogee) overlap within a configurable pad (default 10 km). No propagation required; eliminates roughly 95% of pairs.

**Stage 2 — Orbital Plane / MOID.** [`screening/orbital_plane.py`](../../src/aria/conjunction/screening/orbital_plane.py) computes a Minimum Orbit Intersection Distance (MOID) using vectorized orbit sampling (180 points) followed by `scipy.optimize.minimize` refinement. Pairs whose MOID exceeds the threshold (default 20 km, matching the NASA CARA screening distance) are discarded. Coplanar orbits are conservatively passed. Eliminates roughly 90% of Stage 1 survivors.

**Stage 3 — Time / phasing.** [`screening/time_filter.py`](../../src/aria/conjunction/screening/time_filter.py) propagates all unique objects once across the prediction window (default 72 h, 60 s steps) into a pre-computed ephemeris array, then checks each candidate pair for coarse distance below a threshold (default 50 km). Eliminates roughly 80% of Stage 2 survivors.

The `SmartSieveScreener.screen()` method also accepts an `ExclusionList` for intra-constellation pairs (e.g., Starlink vs. Starlink). `get_parameters()` returns a `SieveParameters` dataclass with every active threshold, allowing operators to understand why a pair passed or failed.

### Stage 3 — TCA refinement

[`../../src/aria/conjunction/conjunction/tca_finder.py`](../../src/aria/conjunction/conjunction/tca_finder.py) refines each candidate pair's approximate TCA from the Smart Sieve to sub-second accuracy. It evaluates coarse distance at 10 s intervals in a ±60 min window around the approximate TCA, finds local minima, then applies `scipy.optimize.minimize_scalar` (Brent's method) with 1 ms convergence tolerance. Multiple close approaches per pair within the window are handled.

[`conjunction/miss_distance.py`](../../src/aria/conjunction/conjunction/miss_distance.py) and [`conjunction/close_approach.py`](../../src/aria/conjunction/conjunction/close_approach.py) package the TCA result with miss distance, RTN-frame decomposition, relative speed, and combined hard-body radius into a `CloseApproach` object that carries through the rest of the pipeline.

### Stage 4 — Probability of collision (Pc)

See [Probability-of-collision methods](#probability-of-collision-methods) below. [`../../src/aria/conjunction/probability/pc_calculator.py`](../../src/aria/conjunction/probability/pc_calculator.py) is the unified dispatcher.

### Stage 5 — Alert classification and CDM generation

[`pipeline/alerts.py`](../../src/aria/conjunction/pipeline/alerts.py) classifies each close approach using the NASA CARA risk thresholds (constants in [`core/constants.py`](../../src/aria/conjunction/core/constants.py)):

| Level  | Pc threshold | Action |
|--------|-------------|--------|
| GREEN  | Pc < 1×10⁻⁵ | No action |
| YELLOW | 1×10⁻⁵ ≤ Pc < 1×10⁻⁴ | Monitor |
| RED    | Pc ≥ 1×10⁻⁴ | Maneuver required |

CDMs are generated for YELLOW and RED events using [`pipeline/cdm_writer.py`](../../src/aria/conjunction/pipeline/cdm_writer.py), which produces CCSDS 508.0-B-1 KVN text format. A second CDM writer at [`cdm/cdm_writer.py`](../../src/aria/conjunction/cdm/cdm_writer.py) is a parallel implementation used for standalone generation. Incoming CDMs from 18 SDS or TraCSS are parsed by [`pipeline/cdm_parser.py`](../../src/aria/conjunction/pipeline/cdm_parser.py).

### Stage 6 — Maneuver planning

[`maneuver/planning.py`](../../src/aria/conjunction/maneuver/planning.py), [`maneuver/delta_v.py`](../../src/aria/conjunction/maneuver/delta_v.py), and [`maneuver/fuel_cost.py`](../../src/aria/conjunction/maneuver/fuel_cost.py) compute collision-avoidance maneuvers for RED events. Fuel cost uses the Tsiolkovsky rocket equation. Maneuver planning is invoked automatically by `ConjunctionPipeline.run()` for RED-classified approaches.

---

## Probability-of-collision methods

All three methods work in the encounter (B-plane) frame. [`probability/covariance.py`](../../src/aria/conjunction/probability/covariance.py) handles covariance combination, RTN-to-ECI rotation, and encounter-plane projection. If no covariance is supplied for an object, a default spherical 1 km (1σ) covariance is generated.

A Mahalanobis pre-filter ([`probability/mahalanobis.py`](../../src/aria/conjunction/probability/mahalanobis.py)) computes D_M = √(mᵀ C⁻¹ m) in the encounter plane. When D_M > 5 (configurable), Pc is set to zero without further computation, saving roughly 70% of numerical integration calls.

### Foster (2D) — primary method

[`../../src/aria/conjunction/probability/foster.py`](../../src/aria/conjunction/probability/foster.py)

Implements the Alfano (2005) single-variable integral, which is the numerical core of the NASA CARA standard method. The 2D integral of a bivariate Gaussian over a circular hard-body disk is reduced to a 1D integral or a closed-form expression:

- **Equal-variance path** (σ₁/σ₂ < 1.001): uses the non-central chi-squared CDF (series expansion over regularized incomplete gamma functions). For zero non-centrality, reduces to 1 − exp(−R²/2σ²).
- **Unequal-variance path** (σ₁/σ₂ ≥ 1.001): integrates over the angular variable θ using 32-point Gauss-Legendre quadrature on [0, 2π]. Each quadrature evaluation computes the radial integral analytically via the ellipse-boundary transform.

Eigenvalue remediation clips near-zero covariance eigenvalues using the larger of an HBR-based floor and a miss-distance-based floor, following the NASA CARA `CovRemEigValClip` approach.

This method is the default in `auto` mode and is the method label written into generated CDMs (`COLLISION_PROBABILITY_METHOD = FOSTER-1992`).

### Chan analytical — fast batch method

[`../../src/aria/conjunction/probability/chan.py`](../../src/aria/conjunction/probability/chan.py)

Chan's method (Chan 2008) is a fast alternative for the near-equal-variance case. The implementation checks the variance ratio:

- **Ratio ≤ 1.5**: uses the non-central chi-squared CDF on the average variance — exact for isotropic covariances, a controlled approximation for mild anisotropy.
- **Ratio > 1.5**: delegates to Foster's Alfano integral for correctness. The comment in the code notes that the geometric-mean approximation used in some earlier Chan implementations introduces 15–50% error for variance ratios above 5; delegation to Foster is preferred.

Chan is available as an explicit method choice (`method="chan"`) and is one of three methods returned by `PcCalculator.calculate_all_methods()`.

### Monte Carlo — fallback for non-standard encounters

[`../../src/aria/conjunction/probability/monte_carlo.py`](../../src/aria/conjunction/probability/monte_carlo.py)

Three Monte Carlo entry points are implemented:

- **`monte_carlo_pc`** — 2D encounter-plane sampling via Cholesky factorization of the combined covariance. Default 10⁶ samples. Practical floor: Pc ~ 10⁻⁴ (100 expected hits at 10⁶ samples for 10% relative error); at Pc ~ 10⁻⁶ the analytical methods are more efficient.

- **`monte_carlo_pc_3d`** — 3D sampling that evaluates relative trajectory r(t) = Δr + Δv·t, finds the time of minimum distance per sample (clamped to an encounter window), and checks against the hard-body radius. Accepts an optional 3×3 velocity covariance so that positional uncertainty can grow with time offset from TCA. Used automatically by `PcCalculator` in `auto` mode when the encounter duration τ = σ_along-track / |v_rel| exceeds 600 s (indicating the short-encounter assumption is invalid — relevant for GEO and proximity operations).

- **`importance_sampling_pc`** — Importance Sampling variant using a proposal distribution centered at the hard-body origin. Returns (Pc estimate, relative standard error). Achieves 100–1000× variance reduction over standard MC; useful for events in the 10⁻⁵–10⁻⁷ range where direct MC is expensive.

### Method selection and inter-method comparison

`PcCalculator.calculate()` uses `method="auto"` by default: it checks the short-encounter validity criterion and dispatches to Foster (typical LEO) or 3D Monte Carlo (GEO / proximity ops). `calculate_all_methods()` runs Foster, Chan, and Monte Carlo in parallel and flags disagreement when any two methods differ by more than one order of magnitude.

---

## What's in the package

The 60 Python files are organized in nine sub-packages:

| Sub-package | Key files | Role |
|-------------|-----------|------|
| `core/` | `types.py`, `constants.py` | Shared data types (`SpaceObject`, `StateVector`, `CloseApproach`, `RiskLevel`), physical constants (WGS-84, EGM-96, CARA thresholds) |
| `data/` | `tle_parser.py`, `catalog.py`, `spacetrack_client.py`, `celestrak_client.py`, `leolabs_session.py`, `event_store.py` | TLE ingest and catalog management; SQLite persistence for events; breakup and maneuver detection in TLE time series |
| `propagation/` | `sgp4_propagator.py`, `frames.py`, `state_vector.py`, `space_weather.py` | SGP4/SDP4 wrapper, frame transforms (TEME/ECI/ECEF/RTN/B-plane), space weather drag inputs |
| `screening/` | `screener.py`, `apogee_perigee.py`, `orbital_plane.py`, `time_filter.py`, `spatial_index.py` | Smart Sieve cascade (Stage 0–3) |
| `conjunction/` | `tca_finder.py`, `close_approach.py`, `miss_distance.py` | TCA refinement, close-approach construction |
| `probability/` | `foster.py`, `chan.py`, `monte_carlo.py`, `pc_calculator.py`, `covariance.py`, `mahalanobis.py` | All Pc computation |
| `pipeline/` | `runner.py`, `cdm_parser.py`, `cdm_writer.py`, `alerts.py`, `trending.py` | End-to-end orchestration, CDM I/O, alert classification, Pc trending over successive updates |
| `maneuver/` | `planning.py`, `delta_v.py`, `fuel_cost.py` | Collision-avoidance maneuver planning and fuel budgeting |
| `analysis/` | `breakup_model.py`, `fleet_risk.py`, `sensitivity.py`, `atmosphere.py` | Post-event analysis: NASA Standard Breakup Model (EVOLVE 4.0), fleet-level risk aggregation, Pc sensitivity to covariance scaling, NRLMSISE-00 atmosphere |
| `api/` | `app.py` | FastAPI REST interface (ConjunctionWatch service) |

---

## Standards and references

The following standards and papers are cited directly in source-file module docstrings or inline comments:

**CCSDS 508.0-B-1** — *Conjunction Data Message* standard. CDM parsing ([`pipeline/cdm_parser.py`](../../src/aria/conjunction/pipeline/cdm_parser.py)) and writing ([`pipeline/cdm_writer.py`](../../src/aria/conjunction/pipeline/cdm_writer.py)) implement KVN format, RTN covariance lower-triangle layout, and the standard field names (TCA, MISS_DISTANCE, COLLISION_PROBABILITY, COLLISION_PROBABILITY_METHOD, CR_R, CT_T, CN_N …).

**Foster (1992)** — J.L. Foster, "The Analytic Basis for Debris Avoidance Operations for the International Space Station." Origin of the 2D bivariate Gaussian integral formulation.

**Alfano (2005)** — S. Alfano, "A Numerical Implementation of Spherical Object Collision Probability," AIAA/AAS. The single-variable Gauss-Legendre integral implemented in `foster.py`.

**Akella & Alfriend (2000)** — "Probability of Collision Between Space Objects." Cited in `foster.py` alongside Foster and Alfano.

**Chan (2008)** — F.K. Chan, *Spacecraft Collision Probability*. Cited in `chan.py` for the series-expansion method.

**Kelso (2009)** — T.S. Kelso, AIAA 2009-6173. Cited in `constants.py` for the 72 h screening window and 20 km MOID threshold matching NASA CARA operational practice.

**Hejduk & Snow (2018)** — Cited in `foster.py` §3.2 for the `CovRemEigValClip` covariance eigenvalue floor.

**Carpenter & Markley (2014)** — AAS 14-378, cited in `pc_calculator.py` for the covariance condition-number check (warning at condition number > 1000).

**Johnson et al. (2001) / Krisko (2011)** — NASA Standard Breakup Model (EVOLVE 4.0), cited in `analysis/breakup_model.py`.

**WGS-84** (NIMA TR8350.2) and **EGM-96** (Lemoine et al. 1998 NASA/TP-1998-206861) — gravitational parameters and J2–J4 harmonics in `core/constants.py`.

---

## Current limitations

**SGP4 accuracy.** SGP4/SDP4 is a General Perturbations model. In LEO, position error grows at roughly 1 km/day from epoch. TLEs older than 3 days trigger a warning; older than 7 days raise `StaleTLEError`. For precise Pc computation with realistic uncertainty, high-fidelity numerical propagators and actual orbit-determination covariances are needed. The subsystem can accept externally provided covariances from CDMs but does not itself produce OD-quality covariances from observations.

**Default covariance.** When no covariance data is available, a spherical 1 km (1σ) isotropic default is used. This is an order-of-magnitude approximation; real TLE-derived covariances are highly anisotropic (along-track uncertainty dominates) with condition numbers often exceeding 10³. The code logs a warning when the condition number threshold is crossed and recommends applying a realism scale factor.

**Chan delegation.** Chan `chan.py` delegates to Foster for variance ratios above 1.5×. For near-isotropic covariances (ratio ≤ 1.5) the result is the non-central chi-squared CDF on the average variance — this is an approximation, not the exact unequal-variance integral.

**Monte Carlo floor.** The direct Monte Carlo estimator cannot resolve Pc below roughly 10⁻⁷ at 10⁶ samples. For sub-threshold events the analytical methods (Foster or Chan) are the practical option; importance sampling extends the range to ~10⁻⁷ at 10⁵ samples.

**Hard-body radius estimates.** Radii are derived from RCS-size category lookups and a small table of named objects. Real object shapes are irregular; the sphere approximation introduces uncertainty that dominates for elongated objects.

**MOID computation.** Stage 2 uses vectorized orbit-position sampling (180 points per orbit) with `scipy.optimize.minimize` refinement. This is not the closed-form analytical MOID and can miss cases where the sample grid is coarser than the orbital curvature variation.

**Validation scope.** The historical-conjunction backtest catalog (`aria.validation.historical_conjunctions`) contains 12 events. Only one event (Iridium 33 / Cosmos 2251, 2009) has a static TOML payload checked into the repository. The remaining 11 require live SpaceTrack credentials and `ARIA_RUN_LIVE_BACKTESTS=1`. Assertions are intentionally coarse (TCA within 60 s of published value; miss distance positive; risk level in {RED, YELLOW, GREEN}) because archive TLEs carry uncertainty large enough to preclude exact reproduction. There is no validation against published CARA or CCSDS reference cases.

**No flight heritage.** This subsystem is a research prototype rated TRL 3–5. It has not been integrated with any operational space surveillance network, has not been flight-tested, and should not be used as the sole basis for operational collision-avoidance maneuver decisions.

---

## Where to start reading

**Pipeline entry point:**
[`../../src/aria/conjunction/pipeline/runner.py`](../../src/aria/conjunction/pipeline/runner.py) — `ConjunctionPipeline.run()` is the single function that drives the full flow from a list of `SpaceObject` instances to `PipelineResult` (CDMs, alerts, maneuver plans).

**Core data model:**
[`../../src/aria/conjunction/core/types.py`](../../src/aria/conjunction/core/types.py) — `SpaceObject`, `StateVector`, `CloseApproach`, `RiskLevel`, `CoordinateFrame`.

**Pc methods:**
- [`../../src/aria/conjunction/probability/foster.py`](../../src/aria/conjunction/probability/foster.py) — Foster/Alfano 2D integral (primary)
- [`../../src/aria/conjunction/probability/chan.py`](../../src/aria/conjunction/probability/chan.py) — Chan fast analytical
- [`../../src/aria/conjunction/probability/monte_carlo.py`](../../src/aria/conjunction/probability/monte_carlo.py) — 2D, 3D, and importance-sampling MC
- [`../../src/aria/conjunction/probability/pc_calculator.py`](../../src/aria/conjunction/probability/pc_calculator.py) — unified dispatcher

**Tests:**
- [`../../tests/unit/test_conjunction/test_foster_full.py`](../../tests/unit/test_conjunction/test_foster_full.py) — unit tests for all Foster/Alfano paths (equal variance, unequal variance, Mahalanobis early exit, dispatch logic)
- [`../../tests/unit/test_conjunction/test_pc_calculator_full.py`](../../tests/unit/test_conjunction/test_pc_calculator_full.py) — end-to-end Pc calculator tests
- [`../../tests/unit/test_conjunction/test_monte_carlo_full.py`](../../tests/unit/test_conjunction/test_monte_carlo_full.py) — Monte Carlo estimator tests
- [`../../tests/integration/test_historical_conjunctions.py`](../../tests/integration/test_historical_conjunctions.py) — 12-event backtest catalog (1 static, 11 require SpaceTrack credentials)
- [`../../tests/integration/test_conjunction_screener_service.py`](../../tests/integration/test_conjunction_screener_service.py) — screener service integration tests

See [`../../README.md`](../../README.md) for project-wide context and dependency installation instructions.
