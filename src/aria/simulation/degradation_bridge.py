"""Bridge between NASA C-MAPSS degradation model and generation ship subsystems.

Maps ship subsystems (reactors, engines, life support, etc.) to degradation
profiles derived from real NASA turbofan run-to-failure data. Instead of
simplistic linear degradation (health -= constant), this uses the fitted
Weibull-like curve from 100 turbofan engines:

    health(t) = 1 - (t / RUL_max)^alpha

where alpha = 1.538 (fitted from C-MAPSS FD001 dataset).

This captures the empirically observed pattern: slow initial wear followed
by accelerating degradation as end-of-life approaches — a universal behavior
across rotating machinery, thermal systems, and electrochemical components.

Usage:
    from aria.simulation.degradation_bridge import get_degradation, get_rul

    health = get_degradation("fusion_reactor", age_hours=87600)  # 10 years
    rul_hrs = get_rul("co2_scrubber", current_health=0.7)
"""

from __future__ import annotations

import math
from typing import Any

import structlog

logger = structlog.get_logger()

# Fitted exponent from NASA C-MAPSS FD001 dataset (100 turbofan engines).
# Alpha > 1 means degradation accelerates over time (convex curve).
# Alpha = 1 would be linear; alpha = 2 would be quadratic.
CMAPSS_ALPHA: float = 1.538

# Hours per year for time conversions.
HOURS_PER_YEAR: float = 8766.0  # 365.25 days * 24 hours

# ──────────────────────────────────────────────────────────────────────
# Subsystem degradation profiles
# ──────────────────────────────────────────────────────────────────────
# Each entry maps a ship subsystem name to its expected design life in
# hours and an optional alpha override (defaults to CMAPSS_ALPHA).
#
# Design lives are drawn from aerospace reliability literature and
# scaled for generation-ship-class equipment where appropriate.
# ──────────────────────────────────────────────────────────────────────

_SubsystemProfile = dict[str, Any]

SUBSYSTEM_PROFILES: dict[str, _SubsystemProfile] = {
    # --- Propulsion & Power ---
    "fusion_reactor": {
        "design_life_hours": 50 * HOURS_PER_YEAR,     # 50-year reactor core
        "alpha": CMAPSS_ALPHA,
        "description": "Deuterium-Tritium fusion reactor core",
    },
    "magsail_coil": {
        "design_life_hours": 100 * HOURS_PER_YEAR,    # Superconducting coil
        "alpha": CMAPSS_ALPHA,
        "description": "Magnetic sail superconducting loop",
    },
    "fuel_injector": {
        "design_life_hours": 20 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Fusion fuel injection assembly",
    },

    # --- Life Support ---
    "co2_scrubber": {
        "design_life_hours": 20 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "CO2 removal (4-bed molecular sieve or amine swing)",
    },
    "tcc_scrubber": {
        "design_life_hours": 20 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Trace contaminant control (activated charcoal + catalytic)",
    },
    "water_recycler": {
        "design_life_hours": 30 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Water recovery & purification loop",
    },
    "air_handler": {
        "design_life_hours": 25 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Atmosphere revitalization fan/heat-exchanger assembly",
    },
    "algae_bioreactor": {
        "design_life_hours": 15 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Spirulina photobioreactor (food + O2 production)",
    },
    "grow_light": {
        "design_life_hours": 12 * HOURS_PER_YEAR,     # LED arrays degrade
        "alpha": 1.2,  # LEDs degrade more linearly (phosphor decay)
        "description": "Hydroponic LED grow light array",
    },

    # --- Structure ---
    "hull_panel": {
        "design_life_hours": 200 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Pressure hull composite panel",
    },

    # --- Electronics ---
    "electronics": {
        "design_life_hours": 30 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "General avionics and computing boards",
    },
    "sensor_suite": {
        "design_life_hours": 15 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Navigation and environmental sensor package",
    },

    # --- Manufacturing ---
    "printer_fdm": {
        "design_life_hours": 15 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Fused deposition modeling 3D printer",
    },
    "printer_slm": {
        "design_life_hours": 12 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Selective laser melting metal printer",
    },

    # --- Mechanical ---
    "pump": {
        "design_life_hours": 25 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Coolant / fluid transfer pump",
    },
    "bearing": {
        "design_life_hours": 15 * HOURS_PER_YEAR,
        "alpha": CMAPSS_ALPHA,
        "description": "Rotating machinery bearing",
    },
    "seal_gasket": {
        "design_life_hours": 10 * HOURS_PER_YEAR,
        "alpha": 1.3,  # Elastomer degradation is slightly more linear
        "description": "Pressure seal / gasket",
    },
}

# Alias mapping: allows callers to use the InterstellarState field names
# directly (e.g. "fusion_reactor_health" -> "fusion_reactor").
_ALIASES: dict[str, str] = {
    "fusion_reactor_health": "fusion_reactor",
    "electronics_health": "electronics",
    "tcc_scrubber_health": "tcc_scrubber",
    "algae_bioreactor_health": "algae_bioreactor",
    "grow_light_health": "grow_light",
    "printer_health": "printer_fdm",
    "hull_integrity": "hull_panel",
    # Short-form aliases
    "reactor": "fusion_reactor",
    "engine": "fusion_reactor",
    "life_support": "co2_scrubber",
    "scrubber": "co2_scrubber",
    "printer": "printer_fdm",
    "hull": "hull_panel",
}

# Default profile for unknown subsystems.
_DEFAULT_PROFILE: _SubsystemProfile = {
    "design_life_hours": 30 * HOURS_PER_YEAR,
    "alpha": CMAPSS_ALPHA,
    "description": "Generic subsystem (default profile)",
}


def _resolve_profile(subsystem: str) -> tuple[str, _SubsystemProfile]:
    """Resolve a subsystem name (or alias) to its profile.

    Returns:
        (canonical_name, profile_dict)
    """
    canonical = _ALIASES.get(subsystem, subsystem)
    profile = SUBSYSTEM_PROFILES.get(canonical, _DEFAULT_PROFILE)
    return canonical, profile


def get_degradation(subsystem: str, age_hours: int) -> float:
    """Return health fraction for a subsystem at a given age.

    Uses the NASA C-MAPSS fitted degradation curve:
        health = 1 - (t / design_life)^alpha

    Args:
        subsystem: Subsystem name or alias (see SUBSYSTEM_PROFILES).
        age_hours: Operating age in hours (must be >= 0).

    Returns:
        Health value in [0.0, 1.0]. 1.0 = new, 0.0 = end of design life.
    """
    if age_hours < 0:
        raise ValueError(f"age_hours must be non-negative, got {age_hours}")

    _, profile = _resolve_profile(subsystem)
    design_life = profile["design_life_hours"]
    alpha = profile.get("alpha", CMAPSS_ALPHA)

    # Normalized time fraction (clamped to [0, 1])
    t_frac = min(age_hours / design_life, 1.0)

    health = 1.0 - t_frac ** alpha
    return max(health, 0.0)


def get_degradation_years(subsystem: str, age_years: float) -> float:
    """Convenience wrapper: age in years instead of hours.

    Args:
        subsystem: Subsystem name or alias.
        age_years: Operating age in years.

    Returns:
        Health value in [0.0, 1.0].
    """
    age_hours = int(age_years * HOURS_PER_YEAR)
    return get_degradation(subsystem, age_hours)


def get_rul(subsystem: str, current_health: float) -> float:
    """Estimate remaining useful life (in hours) given current health.

    Inverts the degradation curve:
        t = design_life * (1 - health)^(1/alpha)
        RUL = design_life - t

    Args:
        subsystem: Subsystem name or alias.
        current_health: Current health in [0.0, 1.0].

    Returns:
        Estimated remaining hours until health reaches 0.
    """
    current_health = max(min(current_health, 1.0), 0.0)

    _, profile = _resolve_profile(subsystem)
    design_life = profile["design_life_hours"]
    alpha = profile.get("alpha", CMAPSS_ALPHA)

    if current_health >= 1.0:
        return design_life
    if current_health <= 0.0:
        return 0.0

    degradation = 1.0 - current_health
    # t_frac = degradation^(1/alpha)
    t_frac = degradation ** (1.0 / alpha)
    age_hours = t_frac * design_life
    return max(design_life - age_hours, 0.0)


def get_rul_years(subsystem: str, current_health: float) -> float:
    """Convenience wrapper: RUL in years instead of hours."""
    return get_rul(subsystem, current_health) / HOURS_PER_YEAR


def get_instantaneous_rate(subsystem: str, age_hours: int) -> float:
    """Return instantaneous health-loss rate (per hour) at a given age.

    Derivative of degradation curve:
        d(health)/dt = -alpha * t^(alpha-1) / design_life^alpha

    Useful for replacing fixed-rate patterns like ``health -= 0.005``.

    Args:
        subsystem: Subsystem name or alias.
        age_hours: Operating age in hours.

    Returns:
        Rate of health decrease per hour (positive value = health decreasing).
    """
    if age_hours < 0:
        raise ValueError(f"age_hours must be non-negative, got {age_hours}")

    _, profile = _resolve_profile(subsystem)
    design_life = profile["design_life_hours"]
    alpha = profile.get("alpha", CMAPSS_ALPHA)

    if age_hours == 0 and alpha > 1:
        return 0.0  # Derivative is 0 at t=0 for alpha > 1

    t = min(age_hours, design_life)
    # d(health)/dt = -alpha * t^(alpha-1) / design_life^alpha
    rate = alpha * (t ** (alpha - 1)) / (design_life ** alpha)
    return rate


def list_subsystems() -> list[str]:
    """Return all registered subsystem names (canonical, no aliases)."""
    return sorted(SUBSYSTEM_PROFILES.keys())


def get_profile(subsystem: str) -> dict[str, Any]:
    """Return the full profile dict for a subsystem (or default)."""
    _, profile = _resolve_profile(subsystem)
    return dict(profile)
