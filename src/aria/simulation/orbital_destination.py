"""Orbital Mechanics at Destination & Coriolis Effects in Rotating Habitat.

Physics models for arrival at a target star system:

1. ORBITAL MECHANICS AT DESTINATION
   - Capture orbit calculation: v_circular = sqrt(GM/r)
   - Hohmann transfer between orbits in target system
   - Station-keeping delta-v budget per year
   - Lagrange point orbits (L1, L2 for planet observation)
   - Gravity assist from other bodies in system

2. CORIOLIS EFFECTS IN ROTATING HABITAT
   - Coriolis acceleration: a_c = -2ω × v
   - Effect on thrown objects, fluid flow, fire behavior, walking
   - Minimum radius for <10% Coriolis ratio
   - HVAC ducting deflection in rotating sections

3. GRAVITY GRADIENT STABILIZATION
   - Tidal forces on long structures in orbit
   - Gravity gradient torque for attitude control
   - Stable equilibria for prolate bodies

4. ATMOSPHERIC ENTRY (landing on target planet)
   - Entry velocity, heating rate, deceleration profile
   - TPS requirements for various atmospheric densities
   - Ballistic coefficient and drag deceleration

Constants use SI unless noted.  Equations are exact where possible.
Reference: Bate, Mueller & White "Fundamentals of Astrodynamics" (1971),
Vallado "Fundamentals of Astrodynamics and Applications" (4th ed, 2013),
O'Neill "The High Frontier" (1976), Johnson & Holbrow (1977).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# ══════════════════════════════════════════════════════════════════
# Physical Constants (SI)
# ══════════════════════════════════════════════════════════════════
G_CONST = 6.674_30e-11         # Gravitational constant [m³ kg⁻¹ s⁻²]
M_SUN = 1.989e30               # Solar mass [kg]
M_EARTH = 5.972e24             # Earth mass [kg]
R_EARTH = 6.371e6              # Earth radius [m]
AU_METERS = 1.496e11           # One AU [m]
YEAR_SECONDS = 365.25 * 86_400 # Julian year [s]
STEFAN_BOLTZMANN = 5.670_374e-8  # W m⁻² K⁻⁴
G0 = 9.80665                   # Standard gravity [m/s²]
R_GAS = 8.314                  # Universal gas constant [J/(mol·K)]


# ══════════════════════════════════════════════════════════════════
# Star System Definitions
# ══════════════════════════════════════════════════════════════════

@dataclass
class CelestialBody:
    """A body in the target star system."""
    name: str
    mass_kg: float
    radius_m: float
    orbit_radius_m: float = 0.0       # Distance from parent body
    orbital_period_s: float = 0.0
    has_atmosphere: bool = False
    atm_density_kg_m3: float = 0.0    # Surface atmospheric density [kg/m³]
    atm_scale_height_m: float = 0.0   # Atmospheric scale height [m]
    surface_gravity_m_s2: float = 0.0
    mean_molecular_mass: float = 44.0  # g/mol, default CO2 (CO2 M=44.01 g/mol, NIST WebBook)


@dataclass
class StarSystem:
    """Target star system with orbiting bodies."""
    star: CelestialBody
    planets: list[CelestialBody] = field(default_factory=list)
    distance_ly: float = 4.24   # Proxima Centauri: 4.243 ly (Gaia EDR3: Lindegren 2021 A&A 649 A2)

    @property
    def mu_star(self) -> float:
        """Gravitational parameter of the star [m³/s²]."""
        return G_CONST * self.star.mass_kg


def proxima_centauri_system() -> StarSystem:
    """Create Proxima Centauri system with known planets.

    Proxima Centauri: M = 0.122 M_sun, R ≈ 0.154 R_sun.
    Proxima b: ~1.17 M_earth, orbital distance ~0.0485 AU, period ~11.2 days.
    Proxima d: ~0.26 M_earth, orbital distance ~0.029 AU, period ~5.1 days.

    References:
      - Anglada-Escudé 2016 Nature 536 437 (Proxima b discovery: mass, period, orbit)
      - Faria 2022 A&A 658 A115 (Proxima d: mass 0.26 M_E, period 5.1 days)
      - Ségransan 2003 A&A 397 L5 (Proxima radius 0.154 R_sun; mass 0.122 M_sun)
      - van der Marel 2019 — Proxima distance 1.3012 pc = 4.244 ly (Hipparcos/Gaia)
    """
    # Proxima Centauri: 0.122 M_sun, 0.154 R_sun (Ségransan 2003 A&A 397 L5)
    star = CelestialBody(
        name="Proxima Centauri",
        mass_kg=0.122 * M_SUN,           # Ségransan 2003 A&A 397 L5
        radius_m=0.154 * 6.957e8,        # Ségransan 2003 A&A 397 L5 (R_sun = 6.957e8 m, IAU 2015 B3)
        orbit_radius_m=0.0,
    )

    # Proxima b: 1.17 M_E min, 0.0485 AU, 11.186 d (Anglada-Escudé 2016 Nature 536 437)
    proxima_b = CelestialBody(
        name="Proxima b",
        mass_kg=1.17 * M_EARTH,          # Anglada-Escudé 2016 Nature 536 437
        radius_m=1.08 * R_EARTH,         # ESTIMATE — rocky super-Earth radius from Chen & Kipping 2017
        orbit_radius_m=0.0485 * AU_METERS,   # Anglada-Escudé 2016 Nature 536 437
        orbital_period_s=11.186 * 86_400,    # Anglada-Escudé 2016 Nature 536 437
        has_atmosphere=True,
        atm_density_kg_m3=0.5,           # ESTIMATE — speculative thin CO₂ atmosphere
        atm_scale_height_m=8_000.0,      # ESTIMATE — CO₂ scale height at ~280 K
        surface_gravity_m_s2=9.81 * 1.17 / (1.08 ** 2),  # g × M/R² (derived)
        mean_molecular_mass=44.0,        # CO₂-dominated (ESTIMATE)
    )

    # Proxima d: 0.26 M_E, 0.029 AU, 5.122 d (Faria 2022 A&A 658 A115)
    proxima_d = CelestialBody(
        name="Proxima d",
        mass_kg=0.26 * M_EARTH,          # Faria 2022 A&A 658 A115
        radius_m=0.81 * R_EARTH,         # ESTIMATE — derived from mass using Chen & Kipping 2017
        orbit_radius_m=0.029 * AU_METERS, # Faria 2022 A&A 658 A115
        orbital_period_s=5.122 * 86_400,  # Faria 2022 A&A 658 A115
        has_atmosphere=False,
    )

    return StarSystem(
        star=star,
        planets=[proxima_b, proxima_d],
        distance_ly=4.24,  # van der Marel 2019 (Gaia parallax: 1.3012 pc = 4.244 ly)
    )


# ══════════════════════════════════════════════════════════════════
# 1. ORBITAL MECHANICS AT DESTINATION
# ══════════════════════════════════════════════════════════════════

def circular_orbit_velocity(mu: float, r: float) -> float:
    """Circular orbit velocity via the Pod A1 vis-viva primitive.

    Delegates to ``aria.physics.gravity.vis_viva_speed`` which
    evaluates `v = √(μ · (2/r − 1/a))` (Bate-Mueller-White §1.5,
    Vallado 2013 eq. 1-22). For a circular orbit r = a.
    """
    from aria.physics.gravity import vis_viva_speed

    if r <= 0:
        raise ValueError(f"Orbital radius must be positive, got {r}")
    return vis_viva_speed(
        gravitational_parameter_m3_s2=mu,
        radius_m=r,
        semi_major_axis_m=r,
    )


def orbital_period(mu: float, a: float) -> float:
    """Kepler's third law via the Pod A1 primitive."""
    from aria.physics.gravity import kepler_period

    if a <= 0:
        raise ValueError(f"Semi-major axis must be positive, got {a}")
    return kepler_period(semi_major_axis_m=a, gravitational_parameter_m3_s2=mu)


def escape_velocity(mu: float, r: float) -> float:
    """Escape velocity `v_esc = √(2μ/r)` — unbound-orbit limit.

    For a parabolic escape trajectory (ε = 0) the vis-viva equation
    gives v² = 2μ/r regardless of semi-major axis. Kept here as a
    closed-form wrapper rather than calling vis_viva_speed with
    a → ∞ (which would hit a guard).
    """
    if r <= 0:
        raise ValueError(f"Radius must be positive, got {r}")
    return math.sqrt(2.0 * mu / r)


def hohmann_transfer(mu: float, r1: float, r2: float) -> dict[str, float]:
    """Hohmann transfer via the Pod A1 primitive.

    Routes through ``aria.physics.gravity.hohmann_transfer_delta_v``
    (Curtis 2014 *Orbital Mechanics for Engineering Students* §6.3)
    for the Δv₁ / Δv₂ / transfer-time triplet, then adds the
    initial and final circular velocities the old code reported
    as convenience fields.
    """
    from aria.physics.gravity import hohmann_transfer_delta_v

    if r1 <= 0 or r2 <= 0:
        raise ValueError("Orbital radii must be positive")

    # Hohmann primitive requires r1 < r2. Flip and take absolute
    # values for the descending case (Curtis 2014 eq. 6.5 is
    # symmetric in |Δv|).
    if r1 < r2:
        dv1, dv2, dv_total, t_transfer = hohmann_transfer_delta_v(
            inner_radius_m=r1,
            outer_radius_m=r2,
            gravitational_parameter_m3_s2=mu,
        )
    else:
        dv1_raw, dv2_raw, dv_total, t_transfer = hohmann_transfer_delta_v(
            inner_radius_m=r2,
            outer_radius_m=r1,
            gravitational_parameter_m3_s2=mu,
        )
        dv1, dv2 = abs(dv2_raw), abs(dv1_raw)
    v1_circular = circular_orbit_velocity(mu, r1)
    v2_circular = circular_orbit_velocity(mu, r2)
    return {
        "delta_v1": abs(dv1),
        "delta_v2": abs(dv2),
        "total_delta_v": abs(dv1) + abs(dv2),
        "transfer_time": t_transfer,
        "semi_major_axis": (r1 + r2) / 2.0,
        "v1_circular": v1_circular,
        "v2_circular": v2_circular,
    }


def vis_viva(mu: float, r: float, a: float) -> float:
    """Vis-viva equation: v = sqrt(μ(2/r - 1/a)).

    Args:
        mu: Gravitational parameter [m³/s²].
        r: Current distance from central body [m].
        a: Semi-major axis of orbit [m].

    Returns:
        Orbital velocity at distance r [m/s].
    """
    return math.sqrt(mu * (2.0 / r - 1.0 / a))


def station_keeping_delta_v(
    mu: float,
    orbit_radius_m: float,
    perturbation_accel_m_s2: float = 1e-6,
    duration_s: float = YEAR_SECONDS,
) -> float:
    """Estimate station-keeping delta-v budget.

    For a circular orbit with a constant perturbation acceleration
    (from solar radiation pressure, gravity of other bodies, etc.),
    the delta-v needed per time period is approximately a * t.

    Typical low-orbit station-keeping: 10-50 m/s per year.
    Typical Lagrange point: 5-15 m/s per year.

    Args:
        mu: Gravitational parameter (for context, not directly used).
        orbit_radius_m: Orbital radius [m].
        perturbation_accel_m_s2: Net perturbation acceleration [m/s²].
        duration_s: Time period [s] (default 1 year).

    Returns:
        Station-keeping delta-v [m/s].
    """
    return perturbation_accel_m_s2 * duration_s


def lagrange_point_distance(mu_star: float, mu_planet: float,
                            orbit_radius_m: float,
                            point: str = "L1") -> float:
    """Distance of L1 or L2 from the planet.

    For L1 and L2 in the restricted three-body problem:
        r_L ≈ a * (M_planet / (3 * M_star))^(1/3)

    This is the Hill sphere approximation.

    Args:
        mu_star: GM of the star [m³/s²].
        mu_planet: GM of the planet [m³/s²].
        orbit_radius_m: Planet's orbital radius [m].
        point: "L1" or "L2".

    Returns:
        Distance from planet center to Lagrange point [m].
    """
    if point not in ("L1", "L2"):
        raise ValueError(f"Only L1 and L2 supported, got {point}")

    # Mass ratio
    mass_ratio = mu_planet / (3.0 * mu_star)
    r_hill = orbit_radius_m * mass_ratio ** (1.0 / 3.0)

    # L1 is sunward, L2 is anti-sunward; both at approximately r_hill
    return r_hill


def gravity_assist_delta_v(
    v_inf: float,
    body_mass_kg: float,
    closest_approach_m: float,
) -> dict[str, float]:
    """Maximum Δv from a planar retrograde gravitational slingshot.

    Scalar closed form from Vallado 2013 *Fundamentals of Astro-
    dynamics* 4th ed §6.3 eq. 6-38:

        δ = 2 · arcsin(1 / (1 + r_p · v_∞² / μ))
        Δv = 2 · v_∞ · sin(δ/2)

    For a full 3-D vector flyby (arbitrary trajectory plane) use
    ``aria.physics.gravity.slingshot_vector_delta_v`` which
    reduces to this scalar formula in the planar-retrograde
    degenerate case.
    """
    mu_body = G_CONST * body_mass_kg
    # Hyperbolic orbit eccentricity (Vallado 2013 eq. 2-51).
    e = 1.0 + closest_approach_m * v_inf ** 2 / mu_body
    # Full deflection 2δ.
    delta = 2.0 * math.asin(1.0 / e)
    dv = 2.0 * v_inf * math.sin(delta / 2.0)
    return {
        "turning_angle_rad": delta,
        "turning_angle_deg": math.degrees(delta),
        "delta_v": dv,
        "eccentricity": e,
    }


def sphere_of_influence(a_planet: float, m_planet: float,
                        m_star: float) -> float:
    """Sphere of influence radius (Laplace).

    r_SOI = a * (m_planet / m_star)^(2/5)

    Args:
        a_planet: Planet's semi-major axis [m].
        m_planet: Planet mass [kg].
        m_star: Star mass [kg].

    Returns:
        SOI radius [m].
    """
    return a_planet * (m_planet / m_star) ** (2.0 / 5.0)


def capture_delta_v(mu_planet: float, r_capture: float,
                    v_infinity: float) -> float:
    """Δv for orbital capture from a hyperbolic approach, via the
    Pod A1 primitive ``aria.physics.gravity.planetary_capture_delta_v``.

    Formula (Vallado 2013 §6.3; Curtis 2014 §8.10):
        Δv = √(v_∞² + 2μ/r) − √(μ/r)

    Args:
        mu_planet: Gravitational parameter of planet [m³/s²].
        r_capture: Desired capture orbit radius [m].
        v_infinity: Hyperbolic excess velocity [m/s].

    Returns:
        Required Δv for capture [m/s].
    """
    from aria.physics.gravity import planetary_capture_delta_v

    return planetary_capture_delta_v(
        v_infinity_m_s=v_infinity,
        periapsis_radius_m=r_capture,
        gravitational_parameter_m3_s2=mu_planet,
    )


# ══════════════════════════════════════════════════════════════════
# 2. CORIOLIS EFFECTS IN ROTATING HABITAT
# ══════════════════════════════════════════════════════════════════

def angular_velocity_from_rpm(rpm: float) -> float:
    """Convert rotation rate from RPM to rad/s.

    ω = 2π × RPM / 60

    Args:
        rpm: Revolutions per minute.

    Returns:
        Angular velocity [rad/s].
    """
    return 2.0 * math.pi * rpm / 60.0


def centripetal_gravity(omega: float, radius_m: float) -> float:
    """Artificial gravity from rotation via the Pod C1 rotating-
    frame primitive ``centrifugal_acceleration_scalar``.

    Formula: `a = ω² r` (Marion & Thornton 2004 *Classical Dynamics*
    5th ed §10.4 rotating-frame equivalence).
    """
    from aria.physics.rotating_frame import centrifugal_acceleration_scalar

    return centrifugal_acceleration_scalar(
        spin_rate_rad_s=abs(omega),
        radial_distance_m=radius_m,
    )


def rpm_for_gravity(target_g_fraction: float, radius_m: float) -> float:
    """Required RPM to achieve target gravity at given radius.

    g = ω²r  →  ω = sqrt(g/r)  →  RPM = 60ω/(2π)

    Args:
        target_g_fraction: Desired gravity as fraction of g0 (e.g. 0.56).
        radius_m: Habitat radius [m].

    Returns:
        Required RPM.
    """
    g_target = target_g_fraction * G0
    omega = math.sqrt(g_target / radius_m)
    return omega * 60.0 / (2.0 * math.pi)


def coriolis_acceleration(omega: float, v_radial: float) -> float:
    """Coriolis acceleration magnitude for radial motion in rotating frame.

    a_c = 2ωv (magnitude, perpendicular to both ω and v).

    For a person walking radially (toward/away from axis) in a rotating
    habitat, the Coriolis acceleration is tangential.

    Args:
        omega: Angular velocity [rad/s].
        v_radial: Radial component of velocity [m/s].

    Returns:
        Coriolis acceleration magnitude [m/s²].
    """
    return 2.0 * omega * abs(v_radial)


def coriolis_ratio(omega: float, v: float, radius_m: float) -> float:
    """Ratio of Coriolis acceleration to centripetal gravity.

    ratio = 2ωv / (ω²r) = 2v / (ωr)

    This ratio determines how "noticeable" Coriolis effects are.
    <10% is generally acceptable for human comfort.

    Args:
        omega: Angular velocity [rad/s].
        v: Velocity of moving object [m/s].
        radius_m: Habitat radius [m].

    Returns:
        Dimensionless Coriolis-to-gravity ratio.
    """
    if omega * radius_m == 0:
        return float("inf")
    return 2.0 * v / (omega * radius_m)


def minimum_radius_for_coriolis_limit(
    max_ratio: float,
    v_typical: float,
    target_g_fraction: float,
) -> float:
    """Minimum habitat radius so Coriolis ratio stays below a limit.

    From: ratio = 2v/(ωr) and g = ω²r
    Substituting ω = sqrt(g/r):
        ratio = 2v / (sqrt(g/r) * r) = 2v / sqrt(g*r)
        r = (2v / (ratio))² / g = 4v² / (ratio² * g)

    Args:
        max_ratio: Maximum acceptable Coriolis ratio (e.g. 0.10 for 10%).
        v_typical: Typical velocity of interest [m/s] (walking ~1.5 m/s).
        target_g_fraction: Desired gravity as fraction of g0.

    Returns:
        Minimum radius [m].
    """
    g_target = target_g_fraction * G0
    return 4.0 * v_typical ** 2 / (max_ratio ** 2 * g_target)


@dataclass
class CoriolisEffects:
    """Comprehensive Coriolis effect analysis for a rotating habitat."""
    radius_m: float = 500.0   # NASA SP-413 Table 4-1: 500 m O'Neill cylinder radius
    rpm: float = 1.0          # NASA SP-413 Table 4-1: 1 RPM rotation rate
    target_g: float = 0.56    # Derived: ω²r/g₀ = (2π/60)²×500/9.81 ≈ 0.56 g

    def __post_init__(self) -> None:
        self.omega = angular_velocity_from_rpm(self.rpm)
        self.actual_g = centripetal_gravity(self.omega, self.radius_m)
        self.actual_g_fraction = self.actual_g / G0

    def walking_coriolis(self, walk_speed: float = 1.5) -> dict[str, float]:
        """Coriolis effects on a walking person.

        Args:
            walk_speed: Walking speed [m/s] (default 1.5 m/s).

        Returns:
            Dictionary with acceleration and ratio values.
        """
        a_c = coriolis_acceleration(self.omega, walk_speed)
        ratio = coriolis_ratio(self.omega, walk_speed, self.radius_m)
        return {
            "coriolis_accel_m_s2": a_c,
            "gravity_accel_m_s2": self.actual_g,
            "ratio_percent": ratio * 100.0,
            "walk_speed_m_s": walk_speed,
            "deflection_noticeable": ratio > 0.10,
        }

    def thrown_object(self, v_throw: float = 10.0,
                      throw_direction: str = "radial") -> dict[str, float]:
        """Coriolis deflection of a thrown object.

        A ball thrown radially (toward or away from axis) deflects
        tangentially.  A ball thrown tangentially (along the rotation)
        deflects radially.

        Args:
            v_throw: Throw velocity [m/s].
            throw_direction: "radial" or "tangential".

        Returns:
            Deflection data.
        """
        a_c = coriolis_acceleration(self.omega, v_throw)
        # Time of flight for a ~10m throw in the habitat gravity
        flight_distance = 10.0  # meters
        t_flight = flight_distance / v_throw
        # Lateral deflection: d = 0.5 * a_c * t²
        deflection_m = 0.5 * a_c * t_flight ** 2

        return {
            "coriolis_accel_m_s2": a_c,
            "flight_time_s": t_flight,
            "lateral_deflection_m": deflection_m,
            "throw_speed_m_s": v_throw,
            "direction": throw_direction,
            "ratio_to_gravity": a_c / self.actual_g if self.actual_g > 0 else float("inf"),
        }

    def fluid_flow_deflection(self, flow_speed: float = 2.0,
                              pipe_length_m: float = 10.0) -> dict[str, float]:
        """Coriolis effect on fluid flow in pipes / HVAC ducts.

        Radial pipes in a rotating habitat experience tangential
        Coriolis forces on the fluid, creating pressure differentials
        and requiring asymmetric ducting.

        Args:
            flow_speed: Fluid velocity [m/s].
            pipe_length_m: Length of radial pipe section [m].

        Returns:
            Deflection and pressure data.
        """
        a_c = coriolis_acceleration(self.omega, flow_speed)
        transit_time = pipe_length_m / flow_speed
        # Tangential deflection of fluid parcel
        deflection_m = 0.5 * a_c * transit_time ** 2
        # Deflection angle
        deflection_angle_rad = math.atan2(deflection_m, pipe_length_m)
        deflection_angle_deg = math.degrees(deflection_angle_rad)

        # Pressure differential across pipe cross-section (ρ * a_c * D)
        # For air at ~1 atm, ρ ≈ 1.2 kg/m³, pipe diameter ~0.5m
        rho_air = 1.2
        pipe_diameter = 0.5
        pressure_diff_pa = rho_air * a_c * pipe_diameter

        return {
            "coriolis_accel_m_s2": a_c,
            "deflection_m": deflection_m,
            "deflection_angle_deg": deflection_angle_deg,
            "pressure_diff_pa": pressure_diff_pa,
            "flow_speed_m_s": flow_speed,
            "pipe_length_m": pipe_length_m,
        }

    def fire_behavior(self) -> dict[str, Any]:
        """Coriolis effects on fire behavior in rotating habitat.

        In a rotating frame, hot gas rising radially (toward axis)
        experiences Coriolis deflection, causing flames to tilt and
        smoke to spiral.  This affects fire detection and suppression
        system design.

        Returns:
            Fire behavior analysis.
        """
        # Hot gas rises at ~1-3 m/s in Earth gravity
        # In 0.56g, buoyancy-driven velocity is reduced
        gas_rise_speed = 2.0 * math.sqrt(self.actual_g_fraction)
        a_c = coriolis_acceleration(self.omega, gas_rise_speed)
        # Flame tilt angle from vertical
        tilt_angle_rad = math.atan2(a_c, self.actual_g) if self.actual_g > 0 else 0
        tilt_angle_deg = math.degrees(tilt_angle_rad)

        return {
            "gas_rise_speed_m_s": gas_rise_speed,
            "coriolis_accel_m_s2": a_c,
            "flame_tilt_deg": tilt_angle_deg,
            "smoke_spirals": True,  # Always true in rotating habitat
            "fire_suppression_note": (
                "Sprinkler coverage must account for tilted fire plume. "
                "Smoke detectors must be offset from directly above ignition."
            ),
        }

    def hvac_design_requirements(self) -> dict[str, Any]:
        """HVAC ducting requirements accounting for Coriolis.

        Returns:
            Design requirements for HVAC in rotating habitat.
        """
        # Typical HVAC air speed: 2-5 m/s
        flow_low = self.fluid_flow_deflection(flow_speed=2.0, pipe_length_m=20.0)
        flow_high = self.fluid_flow_deflection(flow_speed=5.0, pipe_length_m=20.0)

        return {
            "low_speed_deflection_deg": flow_low["deflection_angle_deg"],
            "high_speed_deflection_deg": flow_high["deflection_angle_deg"],
            "asymmetric_ducting_required": True,
            "vane_correction_needed": flow_high["deflection_angle_deg"] > 2.0,
            "recommendations": [
                "Install guide vanes in radial duct sections",
                "Offset return air grilles by Coriolis deflection angle",
                "Use CFD modeling for each deck level (different radius = different ω×r)",
                "Smoke extraction ducts must account for flame tilt",
            ],
        }


# ══════════════════════════════════════════════════════════════════
# 3. GRAVITY GRADIENT STABILIZATION
# ══════════════════════════════════════════════════════════════════

def gravity_gradient_torque(
    mu: float,
    r: float,
    i_z: float,
    i_x: float,
    theta_rad: float,
) -> float:
    """Gravity gradient torque on a body in orbit.

    T = (3μ / (2r³)) × (I_z - I_x) × sin(2θ)

    For a generation ship (long cylinder), I_z >> I_x along the
    orbital radial direction, producing a torque that stabilizes
    the ship pointing toward the planet.

    Args:
        mu: Gravitational parameter of central body [m³/s²].
        r: Orbital radius [m].
        i_z: Moment of inertia about the radial axis [kg·m²].
        i_x: Moment of inertia about the transverse axis [kg·m²].
        theta_rad: Angle from local vertical [rad].

    Returns:
        Gravity gradient torque [N·m].
    """
    return (3.0 * mu / (2.0 * r ** 3)) * (i_z - i_x) * math.sin(2.0 * theta_rad)


def gravity_gradient_libration_period(
    mu: float,
    r: float,
    i_z: float,
    i_x: float,
) -> float:
    """Period of small librations about gravity-gradient equilibrium.

    For small angles, T_lib = T_orbit / sqrt(3(I_z - I_x)/I_x)

    More precisely, the libration frequency is:
        ω_lib = n × sqrt(3(I_z - I_x)/I_x)
    where n = sqrt(μ/r³) is the mean motion.

    Args:
        mu: Gravitational parameter [m³/s²].
        r: Orbital radius [m].
        i_z: Moment of inertia about radial [kg·m²].
        i_x: Moment of inertia about transverse [kg·m²].

    Returns:
        Libration period [s], or inf if unstable.
    """
    if i_z <= i_x:
        return float("inf")  # Unstable — no restoring torque

    n = math.sqrt(mu / r ** 3)  # Mean motion
    omega_lib = n * math.sqrt(3.0 * (i_z - i_x) / i_x)
    return 2.0 * math.pi / omega_lib


def tidal_force_on_structure(
    mu: float,
    r: float,
    length_m: float,
    mass_kg: float,
) -> float:
    """Differential (tidal) force across a long structure in orbit.

    ΔF ≈ 2μ × m × L / r³

    For a generation ship (2km long, 10⁸ kg) in low planetary orbit,
    this can be significant for structural loads.

    Args:
        mu: Gravitational parameter of central body [m³/s²].
        r: Orbital radius [m].
        length_m: Length of the structure [m].
        mass_kg: Mass of the structure [kg].

    Returns:
        Tidal force [N].
    """
    return 2.0 * mu * mass_kg * length_m / r ** 3


# ══════════════════════════════════════════════════════════════════
# 4. ATMOSPHERIC ENTRY
# ══════════════════════════════════════════════════════════════════

def entry_velocity(mu_planet: float, r_planet: float,
                   orbit_altitude_m: float) -> float:
    """Velocity at atmospheric interface during de-orbit.

    Assuming de-orbit from circular orbit, the velocity at the
    atmospheric interface (~100 km altitude for Earth-like) is
    approximately the circular orbit velocity at that altitude.

    For a direct entry from hyperbolic approach, use vis-viva.

    Args:
        mu_planet: Gravitational parameter [m³/s²].
        r_planet: Planet radius [m].
        orbit_altitude_m: Altitude of atmospheric interface [m].

    Returns:
        Entry velocity [m/s].
    """
    r_entry = r_planet + orbit_altitude_m
    return circular_orbit_velocity(mu_planet, r_entry)


def stagnation_heating_rate(
    rho: float,
    v: float,
    nose_radius_m: float,
) -> float:
    """Convective stagnation-point heating rate (Sutton-Graves).

    q_dot = k × sqrt(ρ/r_n) × v³

    k ≈ 1.7415e-4 for Earth air (Sutton & Graves 1971).
    For CO2 atmospheres, k ≈ 1.9e-4.

    Args:
        rho: Atmospheric density at altitude [kg/m³].
        v: Vehicle velocity [m/s].
        nose_radius_m: Nose radius of the entry vehicle [m].

    Returns:
        Heating rate [W/m²].
    """
    k = 1.9e-4  # CO2-atmosphere constant
    return k * math.sqrt(rho / nose_radius_m) * v ** 3


def ballistic_deceleration(
    v: float,
    rho: float,
    cd: float,
    area_m2: float,
    mass_kg: float,
) -> float:
    """Instantaneous deceleration from aerodynamic drag.

    a = 0.5 × ρ × v² × Cd × A / m  (i.e., drag / mass)

    Args:
        v: Vehicle velocity [m/s].
        rho: Atmospheric density [kg/m³].
        cd: Drag coefficient (typically 1.0-1.5 for blunt body).
        area_m2: Reference cross-sectional area [m²].
        mass_kg: Vehicle mass [kg].

    Returns:
        Deceleration [m/s²] (positive value = opposing motion).
    """
    return 0.5 * rho * v ** 2 * cd * area_m2 / mass_kg


def atmospheric_density_exponential(
    rho_0: float,
    altitude_m: float,
    scale_height_m: float,
) -> float:
    """Exponential atmosphere model: ρ = ρ₀ exp(-h/H).

    Args:
        rho_0: Surface density [kg/m³].
        altitude_m: Altitude above surface [m].
        scale_height_m: Scale height [m].

    Returns:
        Atmospheric density at altitude [kg/m³].
    """
    return rho_0 * math.exp(-altitude_m / scale_height_m)


@dataclass
class EntryProfile:
    """Simulated atmospheric entry profile."""
    altitude_m: list[float] = field(default_factory=list)
    velocity_m_s: list[float] = field(default_factory=list)
    deceleration_g: list[float] = field(default_factory=list)
    heating_rate_w_m2: list[float] = field(default_factory=list)
    time_s: list[float] = field(default_factory=list)
    peak_decel_g: float = 0.0
    peak_heating_w_m2: float = 0.0
    total_heat_load_j_m2: float = 0.0


def simulate_atmospheric_entry(
    planet: CelestialBody,
    entry_speed_m_s: float,
    entry_angle_deg: float = -5.0,
    vehicle_mass_kg: float = 5000.0,   # ESTIMATE — shuttle-class lander (Shuttle: 100 t; 5 t lander)
    vehicle_area_m2: float = 10.0,     # ESTIMATE — 3.6 m diameter capsule (Orion: 10.2 m² base area)
    vehicle_cd: float = 1.2,           # ESTIMATE — blunt body Cd ~1.2-1.4 (Gnoffo 1999 NASA TP-1999-209796)
    nose_radius_m: float = 1.5,        # ESTIMATE — heat shield nose radius (Orion: 5 m diam; scaled 1.5 m)
    dt: float = 0.5,                   # ESTIMATE — numerical integration time step
) -> EntryProfile:
    """Simulate atmospheric entry trajectory.

    Simple 1D entry along the flight path with exponential atmosphere.

    Args:
        planet: Target planet with atmosphere data.
        entry_speed_m_s: Speed at atmospheric interface [m/s].
        entry_angle_deg: Flight path angle (negative = descending).
        vehicle_mass_kg: Entry vehicle mass [kg].
        vehicle_area_m2: Reference area [m²].
        vehicle_cd: Drag coefficient.
        nose_radius_m: Nose radius for heating calculation [m].
        dt: Time step [s].

    Returns:
        EntryProfile with trajectory data.
    """
    if not planet.has_atmosphere:
        raise ValueError(f"{planet.name} has no atmosphere for entry")

    profile = EntryProfile()
    gamma = math.radians(entry_angle_deg)  # Flight path angle
    v = entry_speed_m_s
    h = 100_000.0  # Start at 100 km altitude
    t = 0.0
    total_heat = 0.0
    peak_decel = 0.0
    peak_heat = 0.0

    mu_planet = G_CONST * planet.mass_kg

    while h > 0 and v > 50.0 and t < 2000.0:
        rho = atmospheric_density_exponential(
            planet.atm_density_kg_m3, h, planet.atm_scale_height_m
        )

        # Drag deceleration
        decel = ballistic_deceleration(v, rho, vehicle_cd, vehicle_area_m2, vehicle_mass_kg)
        # Gravity component along flight path
        g_local = mu_planet / (planet.radius_m + h) ** 2
        # Heating rate
        q_dot = stagnation_heating_rate(rho, v, nose_radius_m)

        # Record
        profile.altitude_m.append(h)
        profile.velocity_m_s.append(v)
        profile.deceleration_g.append(decel / G0)
        profile.heating_rate_w_m2.append(q_dot)
        profile.time_s.append(t)

        # Track peaks
        if decel > peak_decel:
            peak_decel = decel
        if q_dot > peak_heat:
            peak_heat = q_dot
        total_heat += q_dot * dt

        # Update state (simple Euler integration)
        # Along-track: drag decelerates, gravity component along path
        v -= (decel + g_local * math.sin(abs(gamma))) * dt
        h += v * math.sin(gamma) * dt  # gamma is negative for descent
        # Flight path angle evolution: gravity pulls nose up (toward
        # horizontal), but centripetal v²/r term pushes it down at
        # orbital speeds.  Net: dγ/dt = (g cos γ - v²cos γ/r) / v
        if v > 0:
            r_current = planet.radius_m + max(h, 0)
            centripetal = v * math.cos(gamma) / r_current
            gravity_pullup = g_local * math.cos(gamma) / v
            gamma += (gravity_pullup - centripetal) * dt
            gamma = max(gamma, math.radians(-90.0))
            gamma = min(gamma, math.radians(5.0))  # Prevent skip-out
        t += dt

        if v <= 0:
            break

    profile.peak_decel_g = peak_decel / G0
    profile.peak_heating_w_m2 = peak_heat
    profile.total_heat_load_j_m2 = total_heat

    return profile


# ══════════════════════════════════════════════════════════════════
# 5. INTEGRATED DESTINATION ARRIVAL SIMULATOR
# ══════════════════════════════════════════════════════════════════

@dataclass
class DestinationArrivalState:
    """State tracking for destination arrival orbital operations."""
    system: StarSystem | None = None
    capture_orbit_radius_m: float = 0.0
    capture_delta_v_m_s: float = 0.0
    current_orbit_radius_m: float = 0.0
    orbit_type: str = "NONE"  # NONE, CAPTURE, TRANSFER, STATION, LAGRANGE
    station_keeping_budget_m_s_yr: float = 0.0
    total_delta_v_spent_m_s: float = 0.0
    lagrange_point: str = ""  # L1, L2, or empty
    coriolis_analysis: dict = field(default_factory=dict)
    entry_profiles: list[EntryProfile] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


class DestinationArrivalSimulator:
    """Orchestrates orbital operations at the target star system.

    Handles capture orbit insertion, Hohmann transfers, Lagrange point
    station-keeping, Coriolis analysis for the rotating habitat, and
    atmospheric entry planning.
    """

    def __init__(
        self,
        system: StarSystem | None = None,
        ship_mass_kg: float = 1e8,
        ship_length_m: float = 2000.0,
        habitat_radius_m: float = 500.0,
        habitat_rpm: float = 1.0,
        approach_velocity_m_s: float = 5000.0,
    ) -> None:
        self.system = system or proxima_centauri_system()
        self.ship_mass_kg = ship_mass_kg
        self.ship_length_m = ship_length_m
        self.habitat_radius_m = habitat_radius_m
        self.habitat_rpm = habitat_rpm
        self.approach_velocity_m_s = approach_velocity_m_s

        self.state = DestinationArrivalState(system=self.system)
        self.coriolis = CoriolisEffects(
            radius_m=habitat_radius_m,
            rpm=habitat_rpm,
        )

        # Ship moments of inertia (cylinder approximation)
        # I_z (along length) = 0.5 * m * r²
        # I_x (transverse) = m/12 * (3r² + L²)
        r_ship = 50.0  # ESTIMATE — ship cross-section radius ~50 m (O'Neill cylinder: 500 m habitat, 50 m spine)
        self._i_z = 0.5 * ship_mass_kg * r_ship ** 2
        self._i_x = ship_mass_kg / 12.0 * (3.0 * r_ship ** 2 + ship_length_m ** 2)

    def execute_capture(self, target_planet_index: int = 0,
                        orbit_altitude_km: float = 500.0) -> dict[str, float]:
        """Execute orbital capture around a target planet.

        Args:
            target_planet_index: Index into system.planets.
            orbit_altitude_km: Desired orbit altitude [km].

        Returns:
            Capture parameters.
        """
        planet = self.system.planets[target_planet_index]
        mu_planet = G_CONST * planet.mass_kg
        r_capture = planet.radius_m + orbit_altitude_km * 1000.0

        dv = capture_delta_v(mu_planet, r_capture, self.approach_velocity_m_s)
        v_orbit = circular_orbit_velocity(mu_planet, r_capture)
        t_orbit = orbital_period(mu_planet, r_capture)

        self.state.capture_orbit_radius_m = r_capture
        self.state.capture_delta_v_m_s = dv
        self.state.current_orbit_radius_m = r_capture
        self.state.orbit_type = "CAPTURE"
        self.state.total_delta_v_spent_m_s += dv
        self.state.events.append(
            f"Captured into {orbit_altitude_km:.0f} km orbit around "
            f"{planet.name} (Δv = {dv:.1f} m/s)"
        )

        logger.info("orbital_capture",
                     planet=planet.name,
                     delta_v=dv,
                     orbit_v=v_orbit,
                     period_hours=t_orbit / 3600)

        return {
            "delta_v_m_s": dv,
            "orbit_velocity_m_s": v_orbit,
            "orbital_period_s": t_orbit,
            "orbital_period_hours": t_orbit / 3600.0,
            "capture_radius_m": r_capture,
            "planet": planet.name,
        }

    def transfer_to_lagrange(self, target_planet_index: int = 0,
                             point: str = "L2") -> dict[str, float]:
        """Transfer from planetary orbit to a Lagrange point.

        Args:
            target_planet_index: Index into system.planets.
            point: "L1" or "L2".

        Returns:
            Transfer parameters.
        """
        planet = self.system.planets[target_planet_index]
        mu_planet = G_CONST * planet.mass_kg
        mu_star = self.system.mu_star

        r_lagrange = lagrange_point_distance(
            mu_star, mu_planet, planet.orbit_radius_m, point
        )

        # Hohmann from current orbit to Lagrange point distance
        if self.state.current_orbit_radius_m > 0:
            transfer = hohmann_transfer(
                mu_planet,
                self.state.current_orbit_radius_m,
                r_lagrange,
            )
        else:
            transfer = {"total_delta_v": 0.0, "transfer_time": 0.0}

        # Station-keeping at Lagrange point: ~5-15 m/s per year
        sk_dv = station_keeping_delta_v(
            mu_star, planet.orbit_radius_m,
            perturbation_accel_m_s2=5e-7,
        )

        self.state.orbit_type = "LAGRANGE"
        self.state.lagrange_point = point
        self.state.station_keeping_budget_m_s_yr = sk_dv
        self.state.total_delta_v_spent_m_s += transfer.get("total_delta_v", 0.0)
        self.state.events.append(
            f"Transferred to {point} of {planet.name} "
            f"(Δv = {transfer.get('total_delta_v', 0):.1f} m/s, "
            f"station-keeping = {sk_dv:.1f} m/s/yr)"
        )

        return {
            "lagrange_distance_m": r_lagrange,
            "transfer_delta_v_m_s": transfer.get("total_delta_v", 0.0),
            "transfer_time_s": transfer.get("transfer_time", 0.0),
            "station_keeping_m_s_yr": sk_dv,
            "point": point,
        }

    def analyze_coriolis(self) -> dict[str, Any]:
        """Full Coriolis analysis for the rotating habitat.

        Returns:
            Comprehensive Coriolis effects dictionary.
        """
        analysis = {
            "habitat_radius_m": self.habitat_radius_m,
            "rotation_rpm": self.habitat_rpm,
            "omega_rad_s": self.coriolis.omega,
            "actual_gravity_g": self.coriolis.actual_g_fraction,
            "walking": self.coriolis.walking_coriolis(),
            "thrown_object_radial": self.coriolis.thrown_object(10.0, "radial"),
            "thrown_object_tangential": self.coriolis.thrown_object(10.0, "tangential"),
            "fire_behavior": self.coriolis.fire_behavior(),
            "hvac": self.coriolis.hvac_design_requirements(),
            "minimum_radius_10pct": minimum_radius_for_coriolis_limit(0.10, 1.5, 0.56),
        }
        self.state.coriolis_analysis = analysis
        self.state.events.append("Coriolis analysis completed for rotating habitat")
        return analysis

    def plan_atmospheric_entry(
        self,
        target_planet_index: int = 0,
        vehicle_mass_kg: float = 5000.0,
    ) -> EntryProfile:
        """Plan and simulate atmospheric entry to a target planet.

        Args:
            target_planet_index: Index into system.planets.
            vehicle_mass_kg: Landing vehicle mass [kg].

        Returns:
            Entry profile with trajectory data.
        """
        planet = self.system.planets[target_planet_index]
        mu_planet = G_CONST * planet.mass_kg

        # Entry speed from low orbit
        v_entry = entry_velocity(mu_planet, planet.radius_m, 100_000.0)

        profile = simulate_atmospheric_entry(
            planet=planet,
            entry_speed_m_s=v_entry,
            entry_angle_deg=-7.0,
            vehicle_mass_kg=vehicle_mass_kg,
        )

        self.state.entry_profiles.append(profile)
        self.state.events.append(
            f"Entry profile simulated for {planet.name}: "
            f"peak {profile.peak_decel_g:.1f}g, "
            f"peak heating {profile.peak_heating_w_m2:.0f} W/m²"
        )

        return profile

    def gravity_gradient_analysis(
        self,
        target_planet_index: int = 0,
    ) -> dict[str, float]:
        """Analyze gravity gradient effects on the ship in orbit.

        Args:
            target_planet_index: Index into system.planets.

        Returns:
            Gravity gradient analysis results.
        """
        planet = self.system.planets[target_planet_index]
        mu_planet = G_CONST * planet.mass_kg
        r = self.state.current_orbit_radius_m or (planet.radius_m + 500_000.0)

        # Torque at 10 degrees from vertical
        torque_10deg = gravity_gradient_torque(
            mu_planet, r, self._i_z, self._i_x, math.radians(10.0)
        )

        # Maximum torque (at 45 degrees)
        torque_max = gravity_gradient_torque(
            mu_planet, r, self._i_z, self._i_x, math.radians(45.0)
        )

        # Libration period
        lib_period = gravity_gradient_libration_period(
            mu_planet, r, self._i_z, self._i_x
        )

        # Tidal force across ship length
        tidal = tidal_force_on_structure(
            mu_planet, r, self.ship_length_m, self.ship_mass_kg
        )

        self.state.events.append(
            f"Gravity gradient: max torque {torque_max:.1f} N·m, "
            f"tidal force {tidal:.1f} N"
        )

        return {
            "torque_at_10deg_Nm": torque_10deg,
            "torque_max_Nm": torque_max,
            "libration_period_s": lib_period,
            "libration_period_min": lib_period / 60.0 if lib_period < float("inf") else float("inf"),
            "tidal_force_N": tidal,
            "i_z_kg_m2": self._i_z,
            "i_x_kg_m2": self._i_x,
            "orbit_radius_m": r,
        }

    def full_arrival_sequence(self) -> dict[str, Any]:
        """Execute the complete arrival sequence.

        1. Capture orbit insertion around Proxima b
        2. Coriolis analysis for habitat
        3. Transfer to L2 for observation
        4. Gravity gradient analysis
        5. Atmospheric entry planning (if planet has atmosphere)

        Returns:
            Complete arrival report.
        """
        capture = self.execute_capture(target_planet_index=0, orbit_altitude_km=500.0)
        coriolis = self.analyze_coriolis()
        lagrange = self.transfer_to_lagrange(target_planet_index=0, point="L2")
        gravity = self.gravity_gradient_analysis(target_planet_index=0)

        entry = None
        if self.system.planets[0].has_atmosphere:
            entry = self.plan_atmospheric_entry(target_planet_index=0)

        return {
            "capture": capture,
            "coriolis": coriolis,
            "lagrange": lagrange,
            "gravity_gradient": gravity,
            "entry_profile": entry,
            "total_delta_v_m_s": self.state.total_delta_v_spent_m_s,
            "events": self.state.events,
        }
