"""Data-Driven Equipment Degradation from NASA C-MAPSS Turbofan Data.

Replaces fake linear degradation (health -= 0.003) with REAL run-to-failure
curves extracted from the NASA Commercial Modular Aero-Propulsion System
Simulation (C-MAPSS) dataset.

DATA SOURCE:
  NASA Prognostics Data Repository — Turbofan Engine Degradation Simulation
  https://data.nasa.gov/dataset/C-MAPSS-Aircraft-Engine-Simulator-Data/
  train_FD001.txt: 100 engines, 20,631 rows, run-to-failure
  RUL_FD001.txt: remaining useful life for test engines

METHODOLOGY:
  1. Parse all 100 engine trajectories from train_FD001.txt
  2. For each engine, normalize cycle count to [0, 1] (0=new, 1=failure)
  3. Compute sensor health index from sensors 11, 14, 15 (best predictors)
  4. Average across all engines to get the canonical degradation curve
  5. Fit parametric model: health(t) = 1 - (t/T_max)^alpha
  6. Also keep raw mean trajectory as lookup table for fidelity

ALSO PARSES:
  NASA spirulina (algae) growth data from algae.mat — directly relevant to
  closed-loop life support food production on a generation ship.

Reference:
  Saxena, A. & Goebel, K. (2008). "Turbofan Engine Degradation Simulation
  Data Set", NASA Ames Prognostics Data Repository.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()

# Default data paths
_DEFAULT_TURBOFAN_DIR = Path("/tmp/turbofan_extract")  # nosec B108 (test/dev fixture path; not a security boundary)
_DEFAULT_ALGAE_PATH = Path("/tmp/algae_extract/algae.mat")  # nosec B108 (test/dev fixture path; not a security boundary)

# C-MAPSS column layout: engine_id, cycle, op1, op2, op3, s1..s21
_CMAPSS_COLS = (
    ["engine_id", "cycle", "op1", "op2", "op3"]
    + [f"s{i}" for i in range(1, 22)]
)

# Sensors that best predict failure (from literature and correlation analysis)
# s11 = Total temperature at LPT outlet
# s14 = Corrected static pressure at HPC outlet
# s15 = Ratio of fuel flow to Ps30
_KEY_SENSORS = [11, 14, 15]

# Number of interpolation points for the canonical degradation curve
_CURVE_RESOLUTION = 200


@dataclass
class EngineTrajectory:
    """Single engine run-to-failure trajectory."""
    engine_id: int
    max_cycle: int
    # Normalized health index at each cycle (1.0=healthy, 0.0=failed)
    health_curve: np.ndarray
    # Normalized cycle fraction [0, 1]
    cycle_fraction: np.ndarray


@dataclass
class TurbofanDegradationModel:
    """Degradation model derived from NASA C-MAPSS data.

    Attributes:
        n_engines: Number of engines in the dataset.
        mean_lifetime_cycles: Average cycles to failure.
        std_lifetime_cycles: Std dev of cycles to failure.
        alpha: Exponent in parametric model health(t) = 1 - (t/T)^alpha.
        mean_curve: Mean degradation curve (shape: [_CURVE_RESOLUTION]).
        std_curve: Std dev at each point (shape: [_CURVE_RESOLUTION]).
        curve_fractions: Corresponding normalized time fractions.
    """
    n_engines: int = 0
    mean_lifetime_cycles: float = 0.0
    std_lifetime_cycles: float = 0.0
    alpha: float = 2.0  # fitted exponent
    mean_curve: np.ndarray = field(default_factory=lambda: np.ones(_CURVE_RESOLUTION))
    std_curve: np.ndarray = field(default_factory=lambda: np.zeros(_CURVE_RESOLUTION))
    curve_fractions: np.ndarray = field(
        default_factory=lambda: np.linspace(0, 1, _CURVE_RESOLUTION)
    )


@dataclass
class AlgaeGrowthModel:
    """Growth model derived from NASA spirulina raceway data.

    Attributes:
        n_raceways: Number of raceways in the dataset.
        growth_curves: Density vs time for each raceway.
        mean_growth_curve: Average density trajectory (g/L).
        time_days: Time axis in days.
        max_density: Peak density achieved (g/L).
        lag_phase_days: Days before exponential growth begins.
        doubling_time_days: Estimated doubling time during exponential phase.
    """
    n_raceways: int = 0
    growth_curves: list[np.ndarray] = field(default_factory=list)
    mean_growth_curve: np.ndarray = field(default_factory=lambda: np.array([]))
    time_days: np.ndarray = field(default_factory=lambda: np.array([]))
    max_density: float = 0.0
    lag_phase_days: float = 0.0
    doubling_time_days: float = 0.0


def parse_turbofan_data(
    data_dir: Path | str = _DEFAULT_TURBOFAN_DIR,
) -> list[EngineTrajectory]:
    """Parse NASA C-MAPSS train_FD001.txt into engine trajectories.

    Each engine runs from cycle 1 to failure. We compute a health index
    from sensors 11, 14, 15 by normalizing each sensor's values so that
    the initial reading = 1.0 and the final reading maps to degraded state.

    Returns:
        List of EngineTrajectory objects, one per engine.
    """
    data_dir = Path(data_dir)
    train_path = data_dir / "train_FD001.txt"

    if not train_path.exists():
        raise FileNotFoundError(f"C-MAPSS data not found: {train_path}")

    # Parse the whitespace-delimited file
    raw = np.loadtxt(str(train_path))
    n_rows, n_cols = raw.shape
    logger.info("cmapss.loaded", rows=n_rows, cols=n_cols)

    engine_ids = raw[:, 0].astype(int)
    cycles = raw[:, 1].astype(int)
    unique_engines = np.unique(engine_ids)

    trajectories: list[EngineTrajectory] = []

    for eid in unique_engines:
        mask = engine_ids == eid
        eng_cycles = cycles[mask]
        eng_data = raw[mask]
        max_cycle = eng_cycles.max()

        # Compute composite health index from key sensors
        # Sensor columns: s1 is col 5, so s_i is col 4+i
        health_components = []
        for s_idx in _KEY_SENSORS:
            col = 4 + s_idx  # 0-indexed: engine_id=0, cycle=1, op1=2, op2=3, op3=4, s1=5
            sensor_vals = eng_data[:, col]

            # Normalize: initial reading = baseline
            # Use first 5 cycles as baseline to reduce noise
            baseline = np.mean(sensor_vals[:min(5, len(sensor_vals))])
            if abs(baseline) < 1e-10:
                # Skip sensors with zero baseline
                continue

            # Normalized sensor value
            normalized = sensor_vals / baseline

            # For sensors that increase with degradation (s11, s14), health
            # decreases as value increases. For s15 (decreases with degradation),
            # health decreases as value decreases.
            # Determine direction: if final values > initial, sensor increases
            initial_mean = np.mean(normalized[:min(10, len(normalized))])
            final_mean = np.mean(normalized[max(0, len(normalized) - 10):])

            if final_mean > initial_mean:
                # Sensor increases → invert for health
                # Map [1, max_val] → [1, 0]
                max_val = normalized.max()
                if max_val > 1.0:
                    health = 1.0 - (normalized - 1.0) / (max_val - 1.0)
                else:
                    health = np.ones_like(normalized)
            else:
                # Sensor decreases → direct mapping
                # Map [1, min_val] → [1, 0]
                min_val = normalized.min()
                if min_val < 1.0:
                    health = (normalized - min_val) / (1.0 - min_val)
                else:
                    health = np.ones_like(normalized)

            health_components.append(health)

        if not health_components:
            # Fallback: linear degradation
            n_pts = len(eng_cycles)
            composite_health = np.linspace(1.0, 0.0, n_pts)
        else:
            # Average across sensors for composite health index
            composite_health = np.mean(health_components, axis=0)

        # Clip to [0, 1]
        composite_health = np.clip(composite_health, 0.0, 1.0)

        # Normalize cycle to fraction [0, 1]
        cycle_fraction = (eng_cycles - 1) / max(max_cycle - 1, 1)

        trajectories.append(EngineTrajectory(
            engine_id=int(eid),
            max_cycle=int(max_cycle),
            health_curve=composite_health,
            cycle_fraction=cycle_fraction,
        ))

    logger.info("cmapss.parsed", n_engines=len(trajectories))
    return trajectories


def build_degradation_model(
    trajectories: list[EngineTrajectory],
) -> TurbofanDegradationModel:
    """Build the canonical degradation model from engine trajectories.

    1. Interpolate all trajectories onto a common time grid [0, 1].
    2. Compute mean and std at each point.
    3. Fit parametric model: health(t) = 1 - t^alpha.

    Returns:
        TurbofanDegradationModel with mean curve and fitted parameters.
    """
    fractions = np.linspace(0, 1, _CURVE_RESOLUTION)
    interpolated = np.zeros((len(trajectories), _CURVE_RESOLUTION))

    lifetimes = []
    for i, traj in enumerate(trajectories):
        interpolated[i] = np.interp(fractions, traj.cycle_fraction, traj.health_curve)
        lifetimes.append(traj.max_cycle)

    mean_curve = np.mean(interpolated, axis=0)
    std_curve = np.std(interpolated, axis=0)

    # Anchor curve: normalize so it starts at exactly 1.0
    # Real sensor data has early-life noise; we preserve the *shape*
    # but ensure health(0) = 1.0 for clean API behavior.
    if mean_curve[0] > 0:
        scale = 1.0 / mean_curve[0]
        mean_curve = np.clip(mean_curve * scale, 0.0, 1.0)

    # Ensure monotonicity: health should generally decrease
    # Apply isotonic regression (simple: enforce non-increasing)
    for i in range(1, len(mean_curve)):
        if mean_curve[i] > mean_curve[i - 1]:
            mean_curve[i] = mean_curve[i - 1]

    # Fit alpha: health(t) = 1 - t^alpha
    # Use least squares on the mean curve
    # Avoid t=0 (log(0) undefined) and t=1
    mask = (fractions > 0.01) & (fractions < 0.99) & (mean_curve > 0.01) & (mean_curve < 0.99)
    if mask.sum() > 5:
        t_fit = fractions[mask]
        h_fit = mean_curve[mask]
        # health = 1 - t^alpha → 1-health = t^alpha → log(1-health) = alpha*log(t)
        degradation = np.clip(1.0 - h_fit, 1e-10, 1.0 - 1e-10)
        log_t = np.log(t_fit)
        log_d = np.log(degradation)
        # Least squares: log_d = alpha * log_t → alpha = (log_t . log_d) / (log_t . log_t)
        alpha = float(np.dot(log_t, log_d) / np.dot(log_t, log_t))
        alpha = max(0.5, min(5.0, alpha))  # Clamp to reasonable range
    else:
        alpha = 2.0  # Default: quadratic degradation

    model = TurbofanDegradationModel(
        n_engines=len(trajectories),
        mean_lifetime_cycles=float(np.mean(lifetimes)),
        std_lifetime_cycles=float(np.std(lifetimes)),
        alpha=alpha,
        mean_curve=mean_curve,
        std_curve=std_curve,
        curve_fractions=fractions,
    )

    logger.info(
        "cmapss.model_built",
        n_engines=model.n_engines,
        mean_lifetime=f"{model.mean_lifetime_cycles:.1f}",
        alpha=f"{model.alpha:.3f}",
    )
    return model


def parse_algae_data(
    mat_path: Path | str = _DEFAULT_ALGAE_PATH,
) -> AlgaeGrowthModel:
    """Parse NASA spirulina (algae) raceway data from algae.mat.

    Extracts density (biomass concentration) time series from each raceway.
    This data represents real spirulina growth in open raceways — directly
    applicable to modeling food production in a closed-loop life support system.

    The .mat file contains structured arrays with fields including density,
    irradiance, temperature, pH, etc. for 3 raceways over ~354 days.

    Returns:
        AlgaeGrowthModel with growth curves and derived parameters.
    """
    import scipy.io

    mat_path = Path(mat_path)
    if not mat_path.exists():
        raise FileNotFoundError(f"Algae data not found: {mat_path}")

    data = scipy.io.loadmat(str(mat_path))
    ts = data["algae_ts"]
    n_raceways = int(data["num_raceways"].flatten()[0])

    growth_curves: list[np.ndarray] = []
    all_times: list[np.ndarray] = []

    for r in range(n_raceways):
        density_struct = ts[0, r]["density"]
        density_data = density_struct[0, 0][0].flatten()
        time_data = density_struct[0, 0][1].flatten()
        growth_curves.append(density_data)
        all_times.append(time_data)

    # Use first raceway's time axis as reference (all same length)
    time_days = all_times[0]

    # Stack and compute mean
    stacked = np.column_stack(growth_curves)
    mean_curve = np.mean(stacked, axis=1)

    # Peak density
    max_density = float(np.max([c.max() for c in growth_curves]))

    # Estimate lag phase: time until density exceeds 5% of max
    threshold = 0.05 * max_density
    lag_idx = np.argmax(mean_curve > threshold)
    lag_phase_days = float(time_days[lag_idx]) if lag_idx > 0 else 0.0

    # Estimate doubling time during exponential phase
    # Find region where growth is approximately exponential (density 5-50% of max)
    low_thresh = 0.05 * max_density
    high_thresh = 0.50 * max_density
    exp_mask = (mean_curve > low_thresh) & (mean_curve < high_thresh)
    if exp_mask.sum() > 5:
        exp_times = time_days[exp_mask]
        exp_densities = mean_curve[exp_mask]
        # ln(N) = ln(N0) + mu*t → mu = slope of ln(N) vs t
        log_d = np.log(np.clip(exp_densities, 1e-10, None))
        # Linear fit
        coeffs = np.polyfit(exp_times, log_d, 1)
        mu = coeffs[0]  # growth rate (1/day)
        doubling_time = float(np.log(2) / mu) if mu > 0 else float("inf")
    else:
        doubling_time = float("inf")

    model = AlgaeGrowthModel(
        n_raceways=n_raceways,
        growth_curves=growth_curves,
        mean_growth_curve=mean_curve,
        time_days=time_days,
        max_density=max_density,
        lag_phase_days=lag_phase_days,
        doubling_time_days=doubling_time,
    )

    logger.info(
        "algae.model_built",
        n_raceways=n_raceways,
        max_density=f"{max_density:.3f} g/L",
        lag_days=f"{lag_phase_days:.1f}",
        doubling_time=f"{doubling_time:.2f} days",
    )
    return model


class DataDrivenDegradation:
    """Equipment degradation model backed by real NASA turbofan data.

    Usage:
        model = DataDrivenDegradation.from_nasa_data()
        health = model.predict_health(age_years=15.0, design_life_years=50.0)
        rul = model.predict_rul(current_health=0.7, design_life_years=50.0)

    Equipment type scaling:
        Different equipment has different expected lifetimes but follows
        the same degradation *shape*. The turbofan curve captures the
        universal pattern: slow initial degradation → accelerating failure.
        We scale the time axis by design_life_years.
    """

    def __init__(self, model: TurbofanDegradationModel) -> None:
        self._model = model

    @classmethod
    def from_nasa_data(
        cls, data_dir: Path | str = _DEFAULT_TURBOFAN_DIR
    ) -> DataDrivenDegradation:
        """Load and build model from NASA C-MAPSS data."""
        trajectories = parse_turbofan_data(data_dir)
        model = build_degradation_model(trajectories)
        return cls(model)

    @classmethod
    def from_precomputed(
        cls, alpha: float, mean_lifetime: float
    ) -> DataDrivenDegradation:
        """Create model from known parameters (no data files needed).

        Useful for testing or when NASA data isn't available at runtime.
        """
        fractions = np.linspace(0, 1, _CURVE_RESOLUTION)
        mean_curve = np.clip(1.0 - fractions ** alpha, 0, 1)
        model = TurbofanDegradationModel(
            n_engines=100,
            mean_lifetime_cycles=mean_lifetime,
            std_lifetime_cycles=mean_lifetime * 0.25,
            alpha=alpha,
            mean_curve=mean_curve,
            std_curve=np.zeros(_CURVE_RESOLUTION),
            curve_fractions=fractions,
        )
        return cls(model)

    @property
    def model(self) -> TurbofanDegradationModel:
        return self._model

    def predict_health(
        self,
        age_years: float,
        design_life_years: float = 50.0,
        use_parametric: bool = False,
        noise_std: float = 0.0,
        rng: np.random.Generator | None = None,
    ) -> float:
        """Predict equipment health given its age.

        Args:
            age_years: Current age of the equipment in years.
            design_life_years: Expected total lifetime in years.
            use_parametric: If True, use fitted h=1-t^alpha. If False, use
                lookup table from mean trajectory (higher fidelity).
            noise_std: Optional Gaussian noise (simulates unit-to-unit variation).
            rng: Random generator for reproducible noise.

        Returns:
            Health value in [0, 1]. 1.0 = new, 0.0 = failed.
        """
        # Map age to normalized fraction
        fraction = min(max(age_years / max(design_life_years, 1e-6), 0.0), 1.0)

        if use_parametric:
            health = 1.0 - fraction ** self._model.alpha
        else:
            # Lookup from mean curve
            health = float(np.interp(
                fraction,
                self._model.curve_fractions,
                self._model.mean_curve,
            ))

        # Add noise if requested
        if noise_std > 0 and rng is not None:
            health += rng.normal(0, noise_std)

        return float(np.clip(health, 0.0, 1.0))

    def predict_rul(
        self,
        current_health: float,
        design_life_years: float = 50.0,
        use_parametric: bool = False,
    ) -> float:
        """Predict remaining useful life given current health.

        Args:
            current_health: Current health in [0, 1].
            design_life_years: Expected total lifetime in years.
            use_parametric: If True, use parametric model inversion.

        Returns:
            Estimated remaining years until failure.
        """
        current_health = min(max(current_health, 0.0), 1.0)

        if use_parametric:
            # health = 1 - t^alpha → t = (1 - health)^(1/alpha)
            degradation = 1.0 - current_health
            if degradation <= 0:
                return design_life_years
            current_fraction = degradation ** (1.0 / self._model.alpha)
        else:
            # Invert lookup table: find fraction where mean_curve = current_health
            # Mean curve is non-increasing, so we can search directly
            curve = self._model.mean_curve
            fracs = self._model.curve_fractions

            if current_health >= curve[0]:
                current_fraction = 0.0
            elif current_health <= curve[-1]:
                current_fraction = 1.0
            else:
                # Find the fraction by interpolating the inverse
                # Flip both arrays since interp needs increasing x
                current_fraction = float(np.interp(
                    current_health,
                    curve[::-1],
                    fracs[::-1],
                ))

        remaining_fraction = max(1.0 - current_fraction, 0.0)
        return remaining_fraction * design_life_years

    def sample_trajectory(
        self,
        design_life_years: float = 50.0,
        n_points: int = 100,
        noise_std: float = 0.02,
        seed: int = 42,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Generate a realistic degradation trajectory for one equipment unit.

        Samples from the mean curve with noise drawn from the empirical
        standard deviation across the 100 turbofan engines.

        Returns:
            (times_years, health_values) arrays.
        """
        rng = np.random.default_rng(seed)
        times = np.linspace(0, design_life_years, n_points)
        fractions = times / max(design_life_years, 1e-6)

        # Interpolate mean and std from empirical data
        mean_h = np.interp(fractions, self._model.curve_fractions, self._model.mean_curve)
        std_h = np.interp(fractions, self._model.curve_fractions, self._model.std_curve)

        # Sample with combined empirical + additional noise
        total_std = np.sqrt(std_h**2 + noise_std**2)
        health = mean_h + rng.normal(0, total_std)

        # Enforce monotone non-increasing + clamp
        health = np.clip(health, 0.0, 1.0)
        for i in range(1, len(health)):
            if health[i] > health[i - 1]:
                health[i] = health[i - 1]

        return times, health

    def get_degradation_rate(
        self,
        age_years: float,
        design_life_years: float = 50.0,
    ) -> float:
        """Get instantaneous degradation rate (health loss per year).

        Useful for replacing fixed `health -= 0.003` with data-driven rate.
        """
        # Compute numerical derivative of the degradation curve
        dt = 0.5  # half-year step for finite difference
        h1 = self.predict_health(max(age_years - dt / 2, 0), design_life_years)
        h2 = self.predict_health(age_years + dt / 2, design_life_years)
        rate = (h1 - h2) / dt  # positive = health decreasing
        return max(rate, 0.0)


# ──────────────────────────────────────────────────────────────────────
# Equipment type scaling — maps generation ship subsystems to design lives
# ──────────────────────────────────────────────────────────────────────

# Design lifetimes in years for different generation ship equipment.
# These scale the universal degradation curve to each equipment type.
EQUIPMENT_DESIGN_LIVES: dict[str, float] = {
    # Structural
    "hull_panel": 200.0,
    "pressure_vessel": 150.0,
    "structural_beam": 300.0,
    # Mechanical
    "pump": 25.0,
    "valve": 30.0,
    "bearing": 15.0,
    "seal_gasket": 10.0,
    # Electrical
    "power_cable": 40.0,
    "capacitor": 20.0,
    "transformer": 50.0,
    # Life support
    "co2_scrubber": 20.0,
    "water_recycler": 30.0,
    "air_handler": 25.0,
    "algae_bioreactor": 15.0,
    # Manufacturing
    "fdm_printer": 15.0,
    "slm_printer": 12.0,
    "dlp_printer": 10.0,
    "ebm_printer": 12.0,
    "circuit_printer": 8.0,
    # Propulsion
    "fusion_reactor_component": 50.0,
    "magsail_coil": 100.0,
    "fuel_injector": 20.0,
    # Electronics
    "sensor": 15.0,
    "computer_board": 20.0,
    "communication_array": 30.0,
    # Default
    "generic": 30.0,
}


def real_degradation(
    equipment_type: str,
    age_years: float,
    seed: int = 42,
    _model_cache: dict[str, DataDrivenDegradation] = {},
) -> float:
    """Drop-in replacement for fake linear degradation.

    This function is designed to be called from generation_ship.py and
    other simulation modules. It replaces patterns like:
        health -= 0.003
    With:
        health = real_degradation("pump", age_years=15, seed=42)

    Uses a module-level cache so NASA data is parsed only once.

    Args:
        equipment_type: Key from EQUIPMENT_DESIGN_LIVES, or "generic".
        age_years: How old the equipment is in years.
        seed: For reproducible per-unit variation.

    Returns:
        Health value in [0, 1].
    """
    if "default" not in _model_cache:
        try:
            _model_cache["default"] = DataDrivenDegradation.from_nasa_data()
        except FileNotFoundError:
            # Fallback to parametric with typical turbofan alpha
            _model_cache["default"] = DataDrivenDegradation.from_precomputed(
                alpha=1.8, mean_lifetime=200.0
            )

    model = _model_cache["default"]
    design_life = EQUIPMENT_DESIGN_LIVES.get(equipment_type, 30.0)

    rng = np.random.default_rng(seed)
    # Per-unit variation: ±10% lifetime scatter
    life_scatter = rng.normal(1.0, 0.1)
    effective_life = design_life * max(life_scatter, 0.5)

    return model.predict_health(
        age_years=age_years,
        design_life_years=effective_life,
        noise_std=0.01,
        rng=rng,
    )


def algae_production_rate(
    day_of_year: float,
    bioreactor_age_days: float,
    total_cycle_days: float = 354.0,
    _algae_cache: dict[str, AlgaeGrowthModel] = {},
) -> dict[str, float]:
    """Get algae production metrics from real NASA spirulina data.

    Args:
        day_of_year: Current day within the growth cycle.
        bioreactor_age_days: Days since bioreactor started.
        total_cycle_days: Full cycle length (default 354 from NASA data).

    Returns:
        Dict with density_g_per_L, growth_rate_g_per_L_per_day,
        normalized_productivity (0-1).
    """
    if "default" not in _algae_cache:
        try:
            _algae_cache["default"] = parse_algae_data()
        except FileNotFoundError:
            # Return synthetic fallback
            return {
                "density_g_per_L": 0.5,
                "growth_rate_g_per_L_per_day": 0.01,
                "normalized_productivity": 0.5,
            }

    model = _algae_cache["default"]

    # Map bioreactor age to position in the growth curve
    cycle_pos = bioreactor_age_days % total_cycle_days
    cycle_pos = min(cycle_pos, model.time_days.max())

    density = float(np.interp(cycle_pos, model.time_days, model.mean_growth_curve))
    normalized = density / max(model.max_density, 1e-10)

    # Growth rate from finite difference
    dt = 1.0
    d1 = float(np.interp(max(cycle_pos - dt, 0), model.time_days, model.mean_growth_curve))
    d2 = float(np.interp(min(cycle_pos + dt, model.time_days.max()), model.time_days, model.mean_growth_curve))
    growth_rate = (d2 - d1) / (2 * dt)

    return {
        "density_g_per_L": density,
        "growth_rate_g_per_L_per_day": growth_rate,
        "normalized_productivity": float(np.clip(normalized, 0, 1)),
    }
