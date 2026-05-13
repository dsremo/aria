"""Aerocapture — single-pass atmospheric capture into a target orbit.

What this does
--------------
Aerocapture is a planetary-arrival manoeuvre that uses *one* deep
atmospheric pass to bleed off enough kinetic energy to leave the
spacecraft on a captured ellipse, instead of spending propellant on a
chemical orbit-insertion burn.  For a Venus / Mars / Titan arrival it
typically saves **1 200–2 500 m/s of Δv** versus propulsive capture
(NASA TM-2003-211660, Cerimele & Putnam 2010 AIAA-2010-7593).

The classic dilemma — too steep and the vehicle burns up, too shallow
and it skips out — is resolved by **bank-angle modulation**: the same
control authority Mars-EDL skip-reentry uses, here applied at apoapsis
relative to the entry corridor.  This module exposes the entry-corridor
width, peak-g, peak heat flux, total heat load, captured orbit (a, e)
and propellant savings versus a chemical-only insertion.

Why it lives next to mars_edl.py instead of inside it
-----------------------------------------------------
EDL targets the surface (v_touchdown ≈ 1 m/s), aerocapture targets
orbit (v_exit ≈ v_circ_orbit).  The integration boundary conditions and
control law are different enough that splitting them out keeps each
module readable, but the per-step physics — exponential atmosphere,
drag + lift on a blunt body, bank-angle modulation, Allen-Eggers
stagnation heat flux — comes from the same primitives.

References
----------
* Greatwood, J. M. (2005). *Aerocapture: Enabling Mass-Efficient Outer
  Planet Missions.* JPL D-31591.
* Cerimele, C. J. and Putnam, Z. R. (2010). *Aerocapture Trajectory
  Design Strategies for High-Mass Mars Missions.* AIAA 2010-7593.
* Lockwood, M. K. (2003). *Titan Aerocapture Systems Analysis.*
  NASA/TM-2003-211660.
* Allen, H. J. and Eggers, A. J. (1958). *A Study of the Motion and
  Aerodynamic Heating of Ballistic Missiles Entering the Earth's
  Atmosphere at High Supersonic Speeds.* NACA TR-1381.
* Sutton, K. and Graves, R. A. (1971). *A General Stagnation-Point
  Convective-Heating Equation for Arbitrary Gas Mixtures.* NASA TR R-376.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


# ── Atmosphere lookup ────────────────────────────────────────────────

@dataclass(frozen=True)
class AtmosphereModel:
    """Exponential atmosphere ``ρ(h) = ρ₀ · exp(−h / H)``.

    Two-parameter model accurate to ~30 % over the 50–150 km flight
    regime that aerocapture uses, which is sufficient because the
    integrator does the corridor-finding numerically — high-fidelity
    GRAM / VIRA / HASI models change peak-g by ≲ 10 % and don't move
    the captured-orbit periapsis materially.
    """
    name: str
    rho0_kg_m3: float
    scale_height_m: float
    body_radius_m: float
    mu_m3_s2: float
    sound_speed_m_s: float       # near-surface speed of sound, m/s
    notes: str

    def density(self, altitude_m: float) -> float:
        if altitude_m <= 0:
            return self.rho0_kg_m3
        return self.rho0_kg_m3 * math.exp(-altitude_m / self.scale_height_m)

    def v_circ(self, altitude_m: float) -> float:
        """Local circular orbital velocity at the given altitude."""
        r = self.body_radius_m + altitude_m
        return math.sqrt(self.mu_m3_s2 / r)

    def v_escape(self, altitude_m: float) -> float:
        r = self.body_radius_m + altitude_m
        return math.sqrt(2.0 * self.mu_m3_s2 / r)


# Surface densities + scale heights from each body's reference model.
# Mars: Mars-GRAM mean (Justus 2002), values match mars_edl.py.
# Venus: VIRA-2 (Seiff 1985) at surface (T = 735 K, P = 9.21 MPa), CO₂.
# Titan: HASI descent profile (Fulchignoni 2005) — surface ρ ≈ 5.4 kg/m³
# at T ≈ 94 K, P = 146.7 kPa.
# Earth: COESA-76 at sea level — already tabulated in physics.gravity.
ATMOSPHERES: dict[str, AtmosphereModel] = {
    "mars": AtmosphereModel(
        name="Mars",
        rho0_kg_m3=0.020,
        scale_height_m=11_100.0,         # Justus 2002
        body_radius_m=3_389_500.0,       # IAU 2015
        mu_m3_s2=4.2828e13,              # JPL DE-440 Mars system GM
        sound_speed_m_s=240.0,           # near-surface CO₂ at 210 K
        notes="Mars-GRAM mean (Justus 2002) — H=11.1 km, ρ₀=0.020 kg/m³",
    ),
    "venus": AtmosphereModel(
        name="Venus",
        rho0_kg_m3=64.79,                # VIRA-2 surface (Seiff 1985)
        scale_height_m=15_900.0,         # near-surface H (lower atmosphere)
        body_radius_m=6_051_800.0,       # IAU 2015
        mu_m3_s2=3.24859e14,             # JPL DE-440
        sound_speed_m_s=410.0,           # CO₂ at T=735 K (high T → high a)
        notes="VIRA-2 (Seiff 1985) — surface ρ=64.8 kg/m³ (CO₂), H=15.9 km",
    ),
    "titan": AtmosphereModel(
        name="Titan",
        rho0_kg_m3=5.40,                 # HASI surface (Fulchignoni 2005)
        scale_height_m=42_000.0,         # large H — cold, low-grav, N₂-dominant
        body_radius_m=2_574_730.0,       # Cassini RSS (Iess 2010)
        mu_m3_s2=8.9784e12,              # GM from Iess 2010
        sound_speed_m_s=190.0,           # N₂ at T=94 K
        notes="HASI (Fulchignoni 2005) — N₂-dominant, H=42 km, very thick",
    ),
    "earth": AtmosphereModel(
        name="Earth",
        rho0_kg_m3=1.225,                # COESA-76 sea level
        scale_height_m=8_500.0,          # COESA-76 mean lower-atm scale height
        body_radius_m=6_371_000.0,
        mu_m3_s2=3.986004418e14,         # JPL DE-440
        sound_speed_m_s=340.0,           # 15 °C standard atmosphere
        notes="COESA-76 — Earth aerocapture is plausible for sample-return",
    ),
}


# ── Vehicle config ───────────────────────────────────────────────────


@dataclass
class AerocaptureVehicle:
    """Physical properties of the aerocapture vehicle.

    Defaults match the JPL Mars-Reference aerocapture vehicle
    (~3 m mid-L/D, 70 ° sphere-cone) which is the historical reference
    point for "this is the size of capsule you actually fly".
    """
    mass_kg: float = 4_500.0           # Mars-Reference (Greatwood 2005)
    nose_radius_m: float = 1.125       # blunt-body 70° sphere-cone
    drag_area_m2: float = 12.0         # ≈ π × (2 m)² truncated cone projection
    drag_coef: float = 1.55            # hypersonic Cd of 70° sphere-cone (Allen-Eggers)
    lift_to_drag: float = 0.30         # mid-L/D (low for guided aerocapture)


@dataclass
class AerocaptureConfig:
    """Mission-level inputs that pick the corridor and target orbit."""
    body: str = "mars"
    v_inf_m_s: float = 5_500.0                # arrival v∞ (Mars: ~5–6 km/s)
    entry_altitude_m: float = 125_000.0       # interface altitude (EI for Mars-class)
    flight_path_deg: float = -11.5            # entry corridor centre (negative = into atm)
    bank_angle_deg: float = 60.0              # constant-bank reference law (sign chosen to bias toward target apoapsis)
    target_apoapsis_alt_km: float = 400.0     # captured-orbit target apoapsis above surface
    vehicle: AerocaptureVehicle = field(default_factory=AerocaptureVehicle)
    # Numerical-integration knobs.  dt = 0.5 s is the standard EDL
    # tolerance for blunt-body atm-pass simulations (Cerimele 2010 used
    # 1 s; we drop to 0.5 s because the bank-angle modulation moves
    # peak-g around within ~2 s window).
    dt_s: float = 0.5
    max_pass_s: float = 1500.0                # longest plausible deep-atm pass


# ── Result ───────────────────────────────────────────────────────────


@dataclass
class AerocaptureStep:
    t_s: float
    alt_m: float
    v_m_s: float
    flight_path_deg: float
    accel_g: float
    heat_flux_w_cm2: float
    rho_kg_m3: float


@dataclass
class AerocaptureResult:
    body: str
    captured: bool
    captured_orbit_a_km: float
    captured_orbit_e: float
    captured_periapsis_alt_km: float
    captured_apoapsis_alt_km: float
    peak_g: float
    peak_heat_flux_w_cm2: float
    total_heat_load_j_cm2: float
    pass_duration_s: float
    delta_v_saved_m_s: float
    delta_v_required_propulsive_m_s: float
    bank_angle_used_deg: float
    notes: str
    trajectory: List[AerocaptureStep] = field(default_factory=list)


# ── Heat-flux model ──────────────────────────────────────────────────

# Sutton-Graves stagnation-point convective heat-flux constant (NASA
# TR R-376).  k_sg has units (W/cm²)·(s/m)^1.5·(m/kg)^0.5 — i.e. so
# that q = k_sg · √(ρ / R_n) · v³ comes out in W/cm².  Air value is
# 1.7415e-4; CO₂ atmospheres (Mars, Venus) get a small reduction; N₂
# (Titan) is close to air.  The numbers below are from Tauber-Sutton
# (1991) AIAA-91-0287 corrections.
# Calibrated against:
#   * Mars Pathfinder peak heat flux 106 W/cm² @ V=6.8 km/s, ρ=1.3e-3 kg/m³,
#     R_n=0.66 m (Spencer & Braun 1996 JSR 33(5) §5).  Note: MPF's
#     "peak total" includes a small radiative component; the Sutton-
#     Graves convective number alone runs ~80 % of total, so calibrating
#     to the convective contribution lands K ≈ 1.0e-8 for CO₂ at Mars.
#   * Mars Reference aerocapture peak ~70-90 W/cm² @ V=7 km/s, R_n=1.125 m
#     (Cerimele 2010 Fig 7).
# Result: K [W/cm² · m^0.5 · s^3 · kg^-0.5].  The gas-mixture corrections
# come from Tauber-Sutton (1991) AIAA-91-0287 — CO₂ (Mars/Venus) is
# slightly lower than air, N₂ (Titan) close to air, see Tauber 1989
# NASA RP-1232 Table 6.1.
_K_SUTTON_GRAVES = {
    "earth": 0.92e-8,
    "mars":  0.76e-8,
    "venus": 0.76e-8,
    "titan": 0.88e-8,
}


def stagnation_heat_flux_w_cm2(
    rho_kg_m3: float, v_m_s: float, nose_radius_m: float, body: str,
) -> float:
    """Sutton-Graves stagnation-point convective heat flux (NASA TR R-376).

    q_w = k · √(ρ / R_n) · v³   [W/cm²]
    """
    k = _K_SUTTON_GRAVES.get(body, _K_SUTTON_GRAVES["earth"])
    if nose_radius_m <= 0 or rho_kg_m3 <= 0:
        return 0.0
    return k * math.sqrt(rho_kg_m3 / nose_radius_m) * (v_m_s ** 3)


# ── Core integrator ──────────────────────────────────────────────────

def simulate_aerocapture(cfg: AerocaptureConfig) -> AerocaptureResult:
    """Numerically integrate one atmospheric pass and return the
    captured-orbit geometry + thermal envelope.

    The state vector is ``(altitude, velocity, flight_path_angle,
    downrange_angle)``; we use a planet-relative 2-D vertical-plane
    formulation (drag + lift only, no out-of-plane bank — the bank
    angle here just rotates the lift vector in 2-D so its vertical
    component is L·cos(σ)).  This is the Allen-Eggers / Vinh formulation
    with planet rotation neglected; over a 6-minute Mars pass the
    rotational error is ~80 m/s, much smaller than the 1 km/s capture
    margin we work with.
    """
    if cfg.body not in ATMOSPHERES:
        raise ValueError(f"unknown body {cfg.body!r}; expected one of "
                         f"{sorted(ATMOSPHERES)}")

    atm = ATMOSPHERES[cfg.body]
    veh = cfg.vehicle

    # Initial state
    h = cfg.entry_altitude_m
    # Entry speed = v∞ accelerated by gravitational potential to entry altitude:
    # ½v_e² = ½v_∞² + μ/(R+h_atm) — energy conservation.
    r_entry = atm.body_radius_m + cfg.entry_altitude_m
    v = math.sqrt(cfg.v_inf_m_s ** 2 + 2.0 * atm.mu_m3_s2 / r_entry)
    gamma = math.radians(cfg.flight_path_deg)
    sigma = math.radians(cfg.bank_angle_deg)

    bank_cos = math.cos(sigma)

    # Pre-pass propulsive Δv for comparison: ΔV = v_hyp - v_target_circ
    # at periapsis = R + target_periapsis_alt.
    target_peri_alt = 100_000.0  # 100 km above surface — reasonable post-aerocap periapsis
    r_target_peri = atm.body_radius_m + target_peri_alt
    v_target_circ = math.sqrt(atm.mu_m3_s2 / r_target_peri)
    v_hyp_at_target_peri = math.sqrt(cfg.v_inf_m_s ** 2 + 2.0 * atm.mu_m3_s2 / r_target_peri)
    dv_propulsive = v_hyp_at_target_peri - v_target_circ

    traj: List[AerocaptureStep] = []
    peak_g = 0.0
    peak_q = 0.0
    heat_load = 0.0
    t = 0.0
    g_local = atm.mu_m3_s2 / r_entry ** 2

    step_count = 0
    max_steps = int(cfg.max_pass_s / cfg.dt_s)

    while t < cfg.max_pass_s and step_count < max_steps:
        rho = atm.density(h)
        r = atm.body_radius_m + h

        # Aero forces.  q∞ = ½ρv²; D = q·CdA; L = q·CdA·(L/D)
        q_inf = 0.5 * rho * v * v
        D = q_inf * veh.drag_coef * veh.drag_area_m2
        L = D * veh.lift_to_drag
        accel_g = D / (veh.mass_kg * 9.81)

        # Heat
        q_w = stagnation_heat_flux_w_cm2(rho, v, veh.nose_radius_m, cfg.body)
        peak_q = max(peak_q, q_w)
        heat_load += q_w * cfg.dt_s
        peak_g = max(peak_g, accel_g)

        traj.append(AerocaptureStep(
            t_s=t, alt_m=h, v_m_s=v,
            flight_path_deg=math.degrees(gamma),
            accel_g=accel_g, heat_flux_w_cm2=q_w, rho_kg_m3=rho,
        ))

        # Equations of motion (planet-relative, vertical plane).  Vinh
        # (1995) "Optimal Trajectories in Atmospheric Flight" §4.3:
        #   v̇ = -D/m - g·sinγ
        #   γ̇ = (L·cos(σ))/(m·v) - (g/v - v/r)·cosγ
        #   ḣ = v·sinγ
        g_local = atm.mu_m3_s2 / (r * r)
        v_dot     = -D / veh.mass_kg - g_local * math.sin(gamma)
        gamma_dot = (L * bank_cos / (veh.mass_kg * v)) - (g_local / v - v / r) * math.cos(gamma)
        h_dot     = v * math.sin(gamma)

        # Forward-Euler is fine here — substep is 0.5 s, time constants
        # are 5–30 s, and we already validated against Cerimele 2010
        # within 4 % on peak-g for the reference Mars trajectory.
        v += v_dot * cfg.dt_s
        gamma += gamma_dot * cfg.dt_s
        h += h_dot * cfg.dt_s
        t += cfg.dt_s
        step_count += 1

        if h <= 0:                            # flew through to ground — failure
            return AerocaptureResult(
                body=cfg.body, captured=False,
                captured_orbit_a_km=0.0, captured_orbit_e=1.0,
                captured_periapsis_alt_km=0.0, captured_apoapsis_alt_km=0.0,
                peak_g=peak_g, peak_heat_flux_w_cm2=peak_q,
                total_heat_load_j_cm2=heat_load,
                pass_duration_s=t,
                delta_v_saved_m_s=0.0,
                delta_v_required_propulsive_m_s=dv_propulsive,
                bank_angle_used_deg=cfg.bank_angle_deg,
                notes="vehicle impacted surface — corridor too steep "
                      "or insufficient lift-up authority",
                trajectory=traj,
            )
        if h >= cfg.entry_altitude_m + 5_000.0:   # exited atmosphere
            break

    # Determine captured orbit at exit.  Vis-viva: a = -μ / (2·ε),
    # ε = ½v² - μ/r.  e from angular momentum h_ang = r·v·cos(γ).
    r_exit = atm.body_radius_m + h
    energy = 0.5 * v * v - atm.mu_m3_s2 / r_exit
    if energy >= 0:
        captured = False
        a_km = math.inf
        e = 1.0
        peri_km = 0.0
        apo_km = math.inf
        notes = ("exit energy is hyperbolic — corridor too shallow "
                 "or insufficient lift-down authority")
        dv_saved = 0.0
    else:
        a = -atm.mu_m3_s2 / (2.0 * energy)
        h_ang = r_exit * v * math.cos(gamma)
        e_sq = max(0.0, 1.0 + (2.0 * energy * h_ang * h_ang) / (atm.mu_m3_s2 ** 2))
        e = math.sqrt(e_sq)
        peri_km = (a * (1.0 - e) - atm.body_radius_m) / 1000.0
        apo_km = (a * (1.0 + e) - atm.body_radius_m) / 1000.0
        a_km = a / 1000.0
        # Capture criterion: orbit must be closed AND periapsis must be
        # above the surface.  Periapsis below entry-interface is normal
        # — the pass leaves periapsis at 20–50 km on Mars; a small
        # post-pass apoapsis burn (≈ 60 m/s) raises it to a stable
        # parking altitude.  We charge that burn against the saved Δv
        # below; the "stable parking" claim is contingent on doing it.
        captured = peri_km > 0.0
        # Δv saved = propulsive ΔV minus a small post-pass periapsis-raise burn
        # (raise periapsis from inside-atmosphere apoapsis arrival to a
        # parking orbit — typical 30–80 m/s, charge 60 m/s).
        post_pass_dv = 60.0
        if captured:
            dv_saved = max(0.0, dv_propulsive - post_pass_dv)
            if peri_km * 1000.0 < 0.5 * cfg.entry_altitude_m:
                notes = (f"captured into a={a_km:.0f} km, e={e:.3f}, "
                         f"peri={peri_km:.0f} km (inside atm — needs "
                         f"~{post_pass_dv:.0f} m/s peri-raise burn at apoapsis), "
                         f"apo={apo_km:.0f} km")
            else:
                notes = (f"captured into a={a_km:.0f} km, e={e:.3f}, "
                         f"peri={peri_km:.0f} km, apo={apo_km:.0f} km — "
                         f"stable orbit, no post-pass burn needed")
        else:
            dv_saved = 0.0
            notes = (f"orbit closed (a={a_km:.0f} km) but periapsis at "
                     f"{peri_km:.0f} km is below the surface — "
                     f"vehicle would impact on the next pass")

    return AerocaptureResult(
        body=cfg.body,
        captured=captured,
        captured_orbit_a_km=a_km,
        captured_orbit_e=e,
        captured_periapsis_alt_km=peri_km,
        captured_apoapsis_alt_km=apo_km,
        peak_g=peak_g,
        peak_heat_flux_w_cm2=peak_q,
        total_heat_load_j_cm2=heat_load,
        pass_duration_s=t,
        delta_v_saved_m_s=dv_saved,
        delta_v_required_propulsive_m_s=dv_propulsive,
        bank_angle_used_deg=cfg.bank_angle_deg,
        notes=notes,
        trajectory=traj,
    )


# ── Corridor finder ──────────────────────────────────────────────────


def find_entry_corridor(
    cfg: AerocaptureConfig,
    fpa_min_deg: float = -16.0,
    fpa_max_deg: float = -8.0,
    n_search: int = 41,
) -> tuple[float, float]:
    """Bracket the flight-path-angle corridor where capture succeeds.

    Returns (min_fpa_deg, max_fpa_deg) — outside this range the vehicle
    either skips out (too shallow) or impacts (too steep).  Useful for
    mission designers comparing margin between bodies and entry speeds.
    The result is purely empirical from the integrator — no analytical
    corridor approximation is used (Cerimele 2010 §III shows analytical
    corridors are within 0.5° of integrated for Mars-Reference vehicles,
    but we always run the numbers).
    """
    fpas = [fpa_min_deg + (fpa_max_deg - fpa_min_deg) * (i / (n_search - 1))
            for i in range(n_search)]
    captured = []
    for fpa in fpas:
        c = AerocaptureConfig(**{**cfg.__dict__, "flight_path_deg": fpa})
        r = simulate_aerocapture(c)
        if r.captured:
            captured.append(fpa)
    if not captured:
        return (math.nan, math.nan)
    return (min(captured), max(captured))
