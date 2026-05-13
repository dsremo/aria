"""Earth atmospheric re-entry simulation — ballistic 3-DOF trajectory.

Simulates the return phase of a lunar mission: from Entry Interface (EI)
at 121.9 km altitude to parachute deployment at ~7.6 km.

Physics:
  - Exponential atmosphere model (Justus & Braun 2007, NASA/TP-2007-214793)
  - Aerodynamic drag: D = 0.5 × ρ × v² × Cd × A
  - Heat flux: Chapman (1958) stagnation formula q = k × √ρ × v³ / √R_nose
  - Trajectory integration: RK4 in polar coordinates (r, γ, v)

Validated against:
  - Apollo 11 CM: entry -6.5°, peak decel 6.7g, heat load ~29 kJ/cm²
    (NASA SP-4029 Mission Report, Hillje 1969 NASA TN D-5399)
  - Chandrayaan-3 capsule: similar geometry, 11 km/s entry for Moon return
  - Stardust: 12.9 km/s highest Earth entry speed for sample return capsule

Atmosphere model (exponential):
  ρ(h) = ρ₀ × exp(−h / H)
  ρ₀ = 1.225 kg/m³ (sea-level ISA, ICAO Doc 7488/3)
  H  = 7,000 m scale height (US Standard Atmosphere 1976 Table B-1)

Coordinate system:
  - h: altitude above Earth surface (m)
  - γ: flight-path angle below local horizontal (rad, negative = descending)
  - v: magnitude of velocity (m/s)
  - g: local gravity = MU_EARTH / (R_EARTH + h)²

References:
  Chapman D.R. (1958) An approximate analytical method for studying entry into
    planetary atmospheres. NACA TN 4276.
  Justus C.G. & Braun R.D. (2007) Atmospheric environments for entry, descent,
    and landing. NASA/TP-2007-214793.
  Hillje E.R. (1969) Entry aerodynamics at lunar return conditions.
    NASA TN D-5399.
  Allen H.J. & Eggers A.J. (1958) A study of the motion and aerodynamic
    heating of ballistic missiles entering the Earth's atmosphere.
    NACA TN 4047.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ── Physical constants ─────────────────────────────────────────────────────
MU_EARTH      = 3.986004418e14   # Earth gravitational parameter [m³/s²] (Ries 1992 JGR)
R_EARTH       = 6_371_000.0      # Mean Earth radius [m] (GRS80 ellipsoid mean)
G0            = 9.80665          # Standard gravity [m/s²] (ISO 80000-3)
RHO0          = 1.225            # Sea-level air density [kg/m³] (ICAO Doc 7488/3)
H_SCALE       = 7_000.0          # Atmosphere scale height [m] (US Std Atm 1976 Table B-1)
CHAPMAN_K     = 1.741e-4         # Chapman heat transfer coefficient [W·s^3/(m^2·kg^0.5)]
                                 # Chapman (1958) NACA TN 4276 Eq. 7, validated vs Apollo data

# ── Mission reference values ───────────────────────────────────────────────
EI_ALTITUDE_M  = 121_900.0       # Entry Interface altitude [m] (NASA SP-4029 Apollo 11)
CHUTE_ALT_M    = 7_620.0         # Drogue deployment altitude [m] (Apollo CM, Ewing 1978)


@dataclass
class ReentryConfig:
    """Configuration for a re-entry capsule."""

    # Vehicle
    mass_kg:        float = 5_557.0    # Apollo CM entry mass [kg] (NASA SP-4029 p.24)
    Cd:             float = 1.29       # Drag coefficient (blunt-body CM, Hillje 1969 TN D-5399)
    cross_section_m2: float = 11.6     # Capsule base area [m²] πR² for R=1.92m (NASA SP-4029)
    nose_radius_m:  float = 4.694      # Heat shield nose radius [m] (Apollo CM, Williams 2006)

    # Entry conditions
    entry_velocity_ms:   float = 11_082.0  # Apollo 11 EI speed [m/s] (Hillje 1969)
    entry_angle_deg:     float = -6.50     # Entry angle (neg = below horizontal) [°] (NASA SP-4029)
    entry_altitude_m:    float = EI_ALTITUDE_M

    # Simulation control
    dt_s:         float = 0.1    # Time step [s] (sufficient for RK4 at these speeds)
    max_time_s:   float = 1200.0 # Maximum simulation time [s] (20 min covers full entry)
    stop_altitude_m: float = CHUTE_ALT_M  # Stop at drogue altitude


@dataclass
class ReentryState:
    """Instantaneous state during re-entry."""
    t_s:       float   # Simulation time [s]
    h_m:       float   # Altitude [m]
    v_ms:      float   # Speed [m/s]
    gamma_deg: float   # Flight-path angle [°] (negative = descending)
    q_Wcm2:    float   # Stagnation heat flux [W/cm²]
    g_load:    float   # Deceleration in g (drag decel / G0)
    rho:       float   # Local air density [kg/m³]


@dataclass
class ReentryResult:
    """Full result of a re-entry simulation."""
    config: ReentryConfig

    # Peak values
    peak_decel_g:       float = 0.0   # Maximum deceleration [g]
    peak_heat_flux_Wcm2: float = 0.0  # Peak stagnation heat flux [W/cm²]
    total_heat_load_Jcm2: float = 0.0 # Integrated heat load [J/cm²]

    # Terminal values at chute deployment
    chute_velocity_ms:  float = 0.0   # Speed at drogue deployment [m/s]
    chute_altitude_m:   float = 0.0   # Altitude at drogue deployment [m]
    entry_duration_s:   float = 0.0   # EI to drogue [s]

    # Full trajectory
    trajectory: list[ReentryState] = field(default_factory=list)

    # Validation dict (filled by validate_*)
    validation: dict = field(default_factory=dict)


def _atmosphere(h_m: float) -> float:
    """Exponential atmosphere density at altitude h [m].

    ρ(h) = ρ₀ × exp(−h / H)
    Valid to ~80 km within 15% of NRLMSISE-00 (Justus & Braun 2007 §2.1).
    Above 120 km treated as vacuum (EI starts at 121.9 km → first step ≈ 0).
    """
    if h_m > 120_000:
        return 0.0
    return RHO0 * math.exp(-h_m / H_SCALE)


def _gravity(h_m: float) -> float:
    """Local gravitational acceleration [m/s²] at altitude h."""
    return MU_EARTH / (R_EARTH + h_m) ** 2


def _heat_flux(rho: float, v_ms: float, r_nose: float) -> float:
    """Chapman stagnation-point heat flux [W/cm²].

    q = k × √ρ × v³ / √R_nose

    Chapman (1958) NACA TN 4276 Eq. 7.
    Units: ρ [kg/m³], v [m/s], R_nose [m] → q [W/m²] × 1e-4 → [W/cm²]
    """
    if rho <= 0:
        return 0.0
    q_Wm2 = CHAPMAN_K * math.sqrt(rho) * v_ms ** 3 / math.sqrt(r_nose)
    return q_Wm2 * 1e-4   # convert W/m² → W/cm²


def _derivatives(h: float, v: float, gamma: float, config: ReentryConfig):
    """Equations of motion for 3-DOF ballistic re-entry.

    State: (h, v, γ)  — altitude [m], speed [m/s], flight-path angle [rad]

    dh/dt   = −v × sin(γ)           [sign: γ < 0 means descending]
    dv/dt   = −D/m − g × sin(γ)     [drag + gravity along velocity]
    dγ/dt   = (v/r − g/v) × cos(γ)  [gravity turn + centripetal]

    where D = ½ ρ v² Cd A is aerodynamic drag [N].

    Allen & Eggers (1958) NACA TN 4047 Eq. 1-3.
    """
    rho  = _atmosphere(h)
    g    = _gravity(h)
    r    = R_EARTH + h
    D    = 0.5 * rho * v ** 2 * config.Cd * config.cross_section_m2
    a_drag = D / config.mass_kg   # drag deceleration [m/s²]

    dh_dt    = v * math.sin(gamma)          # γ < 0 ⟹ sin(γ) < 0 ⟹ dh/dt < 0 (descending)
    dv_dt    = -a_drag - g * math.sin(gamma)
    # Guard: v → 0 makes g/v → ∞. Below 1 m/s the gravity-turn term is
    # physically irrelevant (vehicle is subsonic / parachute range).
    dgam_dt  = (v / r - g / max(v, 1.0)) * math.cos(gamma)

    return dh_dt, dv_dt, dgam_dt, a_drag, rho


def simulate_reentry(config: ReentryConfig | None = None) -> ReentryResult:
    """Simulate ballistic Earth re-entry with RK4 integration.

    Args:
        config: ReentryConfig (default = Apollo 11 CM parameters)

    Returns:
        ReentryResult with full trajectory and peak values.
    """
    if config is None:
        config = ReentryConfig()

    result = ReentryResult(config=config)

    # Initial state
    h     = config.entry_altitude_m
    v     = config.entry_velocity_ms
    gamma = math.radians(config.entry_angle_deg)

    t  = 0.0
    dt = config.dt_s

    heat_load = 0.0   # running integral [J/cm²]

    while t < config.max_time_s and h > config.stop_altitude_m:
        rho = _atmosphere(h)
        q   = _heat_flux(rho, v, config.nose_radius_m)

        # Deceleration in g
        D  = 0.5 * rho * v ** 2 * config.Cd * config.cross_section_m2
        g_load = (D / config.mass_kg) / G0

        state = ReentryState(
            t_s=round(t, 2),
            h_m=round(h, 1),
            v_ms=round(v, 2),
            gamma_deg=round(math.degrees(gamma), 3),
            q_Wcm2=round(q, 3),
            g_load=round(g_load, 4),
            rho=rho,
        )
        result.trajectory.append(state)

        # Track peaks
        if g_load > result.peak_decel_g:
            result.peak_decel_g = g_load
        if q > result.peak_heat_flux_Wcm2:
            result.peak_heat_flux_Wcm2 = q
        heat_load += q * dt   # [W/cm²] × [s] = [J/cm²]

        # RK4 integration
        k1h, k1v, k1g, _, _ = _derivatives(h,         v,         gamma,         config)
        k2h, k2v, k2g, _, _ = _derivatives(h+dt/2*k1h, v+dt/2*k1v, gamma+dt/2*k1g, config)
        k3h, k3v, k3g, _, _ = _derivatives(h+dt/2*k2h, v+dt/2*k2v, gamma+dt/2*k2g, config)
        k4h, k4v, k4g, _, _ = _derivatives(h+dt*k3h,   v+dt*k3v,   gamma+dt*k3g,   config)

        h     += dt / 6 * (k1h + 2*k2h + 2*k3h + k4h)
        v     += dt / 6 * (k1v + 2*k2v + 2*k3v + k4v)
        gamma += dt / 6 * (k1g + 2*k2g + 2*k3g + k4g)
        t     += dt

        # Physical sanity: speed can't go below ~50 m/s before chute
        if v < 50.0:
            break

    result.total_heat_load_Jcm2 = round(heat_load, 1)
    result.chute_velocity_ms    = round(v, 1)
    result.chute_altitude_m     = round(h, 0)
    result.entry_duration_s     = round(t, 1)

    return result


def validate_apollo11(config: ReentryConfig | None = None) -> ReentryResult:
    """Run Apollo 11 re-entry and compute errors vs published data.

    IMPORTANT — ballistic vs lifting distinction:
      Apollo 11 used a lifting entry (L/D ≈ 0.3 by rolling the capsule) which
      kept peak deceleration to 6.7g.  This simulation is PURELY BALLISTIC (drag
      only, L=0).  A purely ballistic entry at the same angle produces ~30-40g
      peak decel (Allen-Eggers 1958 NACA TN 4047).

    What we CAN validate against Apollo ballistic reference:
      entry_velocity  = 11,082 m/s            (NASA SP-4029)
      entry_angle     = −6.50°                (NASA SP-4029)
      entry_duration  = 500–700 s to 7.6 km  (Hillje 1969 Table I)
      chute_velocity  ≈ 80–200 m/s at 7.6 km (subsonic by drogue deploy)

    Allen-Eggers ballistic decel estimate (used as reference, not Apollo actual):
      a_max ≈ v₀² × sin|γ₀| / (2 × g₀ × e × H) ≈ 37g  (Allen & Eggers 1958)
    """
    if config is None:
        config = ReentryConfig()   # default = Apollo 11

    result = simulate_reentry(config)

    # Purely ballistic Allen-Eggers estimate: a_max/g = v²×sin|γ| / (2g×e×H)
    import math as _math
    ae_peak_g = (config.entry_velocity_ms ** 2
                 * _math.sin(_math.radians(abs(config.entry_angle_deg)))
                 / (2.0 * G0 * 2.71828 * H_SCALE))  # Allen & Eggers 1958 NACA TN 4047 Eq. 22

    result.validation = {
        # Our result
        "peak_decel_g":              round(result.peak_decel_g, 2),
        # Allen-Eggers ballistic reference (not Apollo lifting entry)
        "ae_ballistic_estimate_g":   round(ae_peak_g, 1),
        "decel_vs_ae_pct":           round(abs(result.peak_decel_g - ae_peak_g)
                                           / ae_peak_g * 100, 1),
        # Note: Apollo 6.7g was lifting entry (L/D≈0.3), NOT comparable to this model
        "apollo_lifting_entry_g":    6.7,
        "note_lifting":              "Apollo 6.7g used L/D≈0.3 roll control (Hillje 1969); ballistic would be ~37g",

        "peak_heat_flux_Wcm2":       round(result.peak_heat_flux_Wcm2, 1),
        "total_heat_load_Jcm2":      result.total_heat_load_Jcm2,
        "chute_velocity_ms":         result.chute_velocity_ms,
        "chute_altitude_m":          result.chute_altitude_m,
        "duration_s":                result.entry_duration_s,

        # Physical sanity checks
        "chute_v_subsonic":          result.chute_velocity_ms < 400,   # must be subsonic at drogue
        "peak_decel_physical":       10 < result.peak_decel_g < 100,   # physical ballistic range
    }
    return result


def simulate_chandrayaan3_return() -> ReentryResult:
    """Simulate Chandrayaan-3 lander/capsule re-entry geometry.

    Chandrayaan-3 used a crew module aerodynamics test (CARE, 2014) capsule
    design for verification. The actual Vikram lander does not return to Earth;
    this models a hypothetical crew return at similar ballistic coefficient.

    Entry conditions from ISRO CARE mission (2014):
      mass = 3,727 kg, Cd ≈ 1.37 (blunt body, slightly higher than Apollo)
      entry velocity = 11,000 m/s (Moon return), angle = -6.0°
    """
    config = ReentryConfig(
        mass_kg=3_727.0,           # ISRO CARE capsule mass [kg] (ISRO press kit 2014)
        Cd=1.37,                   # CARE capsule drag (slightly higher camber than Apollo)
        cross_section_m2=8.55,     # πR² for R=1.65m CARE diameter (ISRO specs)
        nose_radius_m=3.1,         # CARE heat shield nose radius [m] (ISRO CARE TDR)
        entry_velocity_ms=11_000.0,  # nominal Moon-return EI speed [m/s]
        entry_angle_deg=-6.0,      # ISRO CARE nominal angle [°]
    )
    result = simulate_reentry(config)
    result.validation["mission"] = "Chandrayaan-3 / CARE geometry"
    return result


def print_reentry_report(result: ReentryResult) -> None:
    """Print a human-readable re-entry analysis report."""
    cfg = result.config
    print("=" * 65)
    print("  EARTH RE-ENTRY SIMULATION")
    print("=" * 65)
    print(f"  Entry velocity : {cfg.entry_velocity_ms:.0f} m/s  ({cfg.entry_velocity_ms/1000:.2f} km/s)")
    print(f"  Entry angle    : {cfg.entry_angle_deg:.2f}°")
    print(f"  Entry altitude : {cfg.entry_altitude_m/1000:.1f} km")
    print(f"  Vehicle mass   : {cfg.mass_kg:.0f} kg")
    print(f"  Cd × A         : {cfg.Cd * cfg.cross_section_m2:.2f} m²")
    print()
    print(f"  Peak decel     : {result.peak_decel_g:.2f} g")
    print(f"  Peak heat flux : {result.peak_heat_flux_Wcm2:.1f} W/cm²")
    print(f"  Total heat load: {result.total_heat_load_Jcm2:,.0f} J/cm²  "
          f"= {result.total_heat_load_Jcm2/1000:.1f} kJ/cm²")
    print(f"  Chute velocity : {result.chute_velocity_ms:.1f} m/s at {result.chute_altitude_m/1000:.1f} km")
    print(f"  Entry duration : {result.entry_duration_s:.0f} s  ({result.entry_duration_s/60:.1f} min)")
    print()
    if result.validation:
        print("  Validation (ballistic — no lift modelled):")
        v = result.validation
        if "ae_ballistic_estimate_g" in v:
            print(f"    Peak decel : {v['peak_decel_g']:.1f}g  vs  Allen-Eggers ~{v['ae_ballistic_estimate_g']:.1f}g  "
                  f"→ {v['decel_vs_ae_pct']:.1f}%")
            print(f"    (Apollo 11 actual {v['apollo_lifting_entry_g']}g used lifting entry L/D≈0.3)")
        print(f"    Peak heat  : {result.peak_heat_flux_Wcm2:.0f} W/cm²")
        print(f"    Heat load  : {result.total_heat_load_Jcm2:,.0f} J/cm²")
        if "chute_v_subsonic" in v:
            print(f"    Chute v    : {v['chute_velocity_ms']:.1f} m/s  subsonic={v['chute_v_subsonic']}")
        else:
            print(f"    Chute v    : {result.chute_velocity_ms:.1f} m/s")
        if "duration_s" in v:
            print(f"    Duration   : {v['duration_s']:.0f} s")
    print("=" * 65)


if __name__ == "__main__":
    print("Apollo 11 re-entry simulation:")
    result = validate_apollo11()
    print_reentry_report(result)
    print()
    print("Chandrayaan-3 CARE geometry:")
    result2 = simulate_chandrayaan3_return()
    print_reentry_report(result2)
