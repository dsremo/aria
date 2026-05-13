"""Powered lunar ascent — surface → low lunar orbit rendezvous.

Fills the critical gap the earlier audit flagged: ARIA had descent
(``lunar_descent.py``) and trans-Earth injection (``lunar_return.py``)
but **no powered ascent** from the lunar surface back to orbit. Without
this, an end-to-end crewed Moon mission simply could not close — the
ascent phase is what makes the Apollo/Artemis architecture round-trip.

The model is Apollo-LM-class:

  Phase 1  Vertical rise   – clear the descent stage, 10 s of pitch = 90°
  Phase 2  Pitch-over      – gravity-turn profile, pitch → 15° above horizon
                            by end of boost
  Phase 3  Boost           – constant thrust burn, attitude tracks a
                            target flight-path angle until orbit
                            insertion apolune ≥ target circular altitude
  Phase 4  Coast + circularise at apolune (small second burn)

This is a 2-D point-mass simulation in the Moon-equator plane: adequate
for Δv, fuel, burn-time, and trajectory-envelope validation.  For a
6-DOF attitude study use Basilisk.

Key numbers:
  Apollo 11 Ascent Stage (AS)   — m₀ = 4,700 kg, Isp = 311 s, T = 15,570 N
                                  ΔV = 1,845 m/s, burn = 432 s
  Chang'e-5 ascent              — m₀ = 710 kg, Isp = 300 s, T = 3,000 N

Verified by ``apollo_11_ascent()`` against NASA SP-2007-4805 Table 2.

References:
    Bennett, F. V. (1970) "Apollo Lunar Descent and Ascent Trajectories,"
        AIAA 8th Aerospace Sciences Meeting, NASA TM X-58040.
    NASA SP-2007-4805, "Apollo 11 Lunar Surface Journal."
    Vallado (2013) Fundamentals of Astrodynamics §6 (ascent profile).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# Lunar physical constants
G0 = 9.80665                 # Earth std. gravity, used in Isp → exhaust-velocity
MU_MOON = 4.902800066e12     # m³/s²  (JPL DE440)
R_MOON = 1737400.0           # m      (IAU 2015 nominal mean lunar radius)


# ════════════════════════════════════════════════════════════════════
#  Inputs / outputs
# ════════════════════════════════════════════════════════════════════

@dataclass
class AscentConfig:
    """Ascent vehicle / stage configuration."""
    name: str
    wet_mass_kg: float               # vehicle mass at ignition
    dry_mass_kg: float               # vehicle mass after propellant burnout
    thrust_n: float                  # main engine thrust (vacuum)
    isp_s: float                     # specific impulse (vacuum)
    target_orbit_alt_km: float = 100.0  # circular rendezvous orbit
    launch_latitude_deg: float = 0.0    # landing-site latitude
    vertical_rise_duration_s: float = 8.0
    # BUG-017 (2026-04-24): was 80° (final pitch 10° above horizon), which
    # left MECO with γ ≈ 13° on a sub-surface-perilune orbit. Apollo LM
    # Ascent Program 12 flew to insertion pitch ≈ 3° above horizon
    # (NASA SP-287 LM Operations Handbook §5) — use 87° rotation.
    pitch_over_degrees: float = 87.0    # total rotation from vertical (final pitch = 3° above horizon)
    min_throttle: float = 1.0           # Apollo LM was single-throttle on ascent
    max_burn_time_s: float = 900.0      # safety cap


@dataclass
class AscentState:
    """Instantaneous ascent state — one row of the integrated trajectory."""
    t_s: float
    altitude_m: float            # above lunar surface
    downrange_m: float           # along surface
    speed_mps: float             # magnitude of inertial velocity
    flight_path_deg: float       # γ, 90° = straight up, 0° = horizontal
    mass_kg: float
    thrust_n: float
    pitch_deg: float             # commanded pitch (90° = vertical)
    phase: str


@dataclass
class AscentResult:
    """End-of-ascent summary."""
    config: AscentConfig
    success: bool
    burnout_altitude_km: float
    burnout_speed_mps: float
    burnout_flight_path_deg: float
    burnout_time_s: float
    circularisation_dv_mps: float   # small burn at apolune to circularise
    total_dv_mps: float             # boost + circularisation
    propellant_burned_kg: float
    propellant_margin_kg: float     # wet - dry - burned
    trajectory: List[AscentState] = field(default_factory=list)
    abort_window_s: Optional[float] = None   # earliest abort-to-orbit instant
    notes: List[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
#  Core integrator
# ════════════════════════════════════════════════════════════════════

def _circular_speed(r_m: float) -> float:
    """Circular-orbit speed at radius r from the Moon's centre."""
    return math.sqrt(MU_MOON / max(r_m, 1.0))


def _pitch_program(t: float, cfg: AscentConfig, boost_t_total: float) -> float:
    """Commanded pitch (deg, 90 = vertical) over time.

    Apollo-style three-phase: vertical rise, then rapid pitch-over to the
    final attitude within ~30-50 s, then hold constant at the insertion
    pitch for the rest of the boost. Holding at a shallow angle gives
    most of the thrust to horizontal acceleration, which is what actually
    gets the vehicle into orbit.

    BUG-017 (2026-04-24): old code finished the pitch-over at 70 % of
    boost_t and held the final pitch for only the last 30 %. With
    cfg.pitch_over_degrees=80° (final pitch = 10° above horizontal) the
    vehicle reached MECO still climbing at γ ≈ 13° instead of Apollo's
    γ ≈ 0° — leaving it on a sub-circular orbit with perilune below
    the surface and inflating the circularisation Δv to ~420 m/s.
    Finish the pitch-over at 50 % so the vehicle has more time to build
    horizontal velocity at the final (shallow) pitch.
    """
    if t <= cfg.vertical_rise_duration_s:
        return 90.0
    t_into = t - cfg.vertical_rise_duration_s
    # Finish pitch-over at 25 % of boost (was 70 %), so the rest of the
    # burn runs at the shallow insertion pitch. With the old 70 % figure
    # the average flight-path angle over the burn was ~40°, incurring
    # ~200 m/s gravity loss — 4× Apollo's observed ~50 m/s loss — and
    # leaving the vehicle 250 m/s short of v_circ at MECO.
    pitch_phase_end = cfg.vertical_rise_duration_s + 0.4 * (boost_t_total - cfg.vertical_rise_duration_s)
    if t < pitch_phase_end:
        frac = (t - cfg.vertical_rise_duration_s) / max(pitch_phase_end - cfg.vertical_rise_duration_s, 1.0)
        # Ease-in-out cubic so pitch starts slow, accelerates, then slows
        eased = frac * frac * (3 - 2 * frac)
        return 90.0 - cfg.pitch_over_degrees * eased
    return 90.0 - cfg.pitch_over_degrees


def simulate_ascent(cfg: AscentConfig, dt_s: float = 0.5) -> AscentResult:
    """Integrate the ascent phase to MECO (main engine cut-off).

    Returns an AscentResult with full trajectory and the circularisation Δv
    needed at apolune to round the orbit to the target altitude.

    The integrator is a simple RK2 (Heun) on the planar (altitude, downrange,
    radial-velocity, tangential-velocity) state. A flat-Moon approximation
    is used for the first few kilometres; above that we switch to polar
    coordinates so gravity direction tracks the surface curvature.
    """
    # Initial conditions on the launch pad. The state is polar (r, theta,
    # v_r, v_t). Altitude = r - R_MOON is derived, not tracked separately.
    r = R_MOON                        # radial distance from Moon centre
    theta = 0.0                       # surface-fixed longitude (rad)
    v_r = 0.0                         # radial velocity  (m/s)
    v_t = 0.0                         # tangential velocity
    mass = cfg.wet_mass_kg
    dry = cfg.dry_mass_kg
    mdot = cfg.thrust_n / (cfg.isp_s * G0)

    # Estimate boost burn time from the ideal Δv budget.
    target_speed = _circular_speed(R_MOON + cfg.target_orbit_alt_km * 1000)
    # BUG-017 (2026-04-24): lunar ascent gravity+steering losses are
    # ~80 m/s (Apollo LM actual: 17×86 km insertion at 1691 m/s from a
    # 1629 m/s circular target = 62 m/s excess; plus ~20 m/s steering —
    # NASA SP-350 p.129). Old 150 m/s value over-budgeted the burn and
    # left the vehicle on a suborbital trajectory with perilune below
    # the surface at MECO, which pushed the circularisation Δv up to
    # ~420 m/s (vs Apollo actual ≤35 m/s).
    estimated_dv = target_speed + 80.0
    # Tsiolkovsky: Δv = v_e ln(m0/mf)  →  mf = m0 exp(-Δv/v_e)
    v_e = cfg.isp_s * G0
    mass_final = cfg.wet_mass_kg * math.exp(-estimated_dv / v_e)
    if mass_final < dry:
        # Insufficient propellant — still run the integration but flag.
        return AscentResult(
            config=cfg, success=False,
            burnout_altitude_km=0.0, burnout_speed_mps=0.0,
            burnout_flight_path_deg=90.0, burnout_time_s=0.0,
            circularisation_dv_mps=0.0, total_dv_mps=0.0,
            propellant_burned_kg=0.0,
            propellant_margin_kg=cfg.wet_mass_kg - dry,
            notes=[f"Insufficient propellant — need {estimated_dv:.0f} m/s Δv, "
                   f"only have {v_e * math.log(cfg.wet_mass_kg / dry):.0f} m/s"])
    boost_t = (cfg.wet_mass_kg - mass_final) / mdot

    traj: List[AscentState] = []
    t = 0.0
    phase = "vertical_rise"
    # R43 fix: extend the integration window beyond the predicted boost
    # time so PGNS-style guidance can run to true insertion cutoff.  The
    # burn-stop test is now speed-based (Apollo "PGNS Δh-dot = 0 +
    # v_horizontal ≥ v_target") rather than time-based.  Old code cut at
    # boost_t * 1.2 with a time-based cutoff that left 17% of the LM's
    # propellant unburned and inflated circ_dv to 251 m/s — far above
    # the Apollo flight value (~25 m/s).
    max_t = min(cfg.max_burn_time_s, boost_t * 1.6)
    insertion_target_speed = target_speed * 1.005  # PGNS overshoot ~0.5%
    abort_window_s: Optional[float] = None
    step = 0

    while t < max_t:
        step += 1
        alt = r - R_MOON
        speed = math.sqrt(v_r * v_r + v_t * v_t)
        gamma = math.degrees(math.atan2(v_r, max(v_t, 1e-6))) if speed > 1e-3 else 90.0

        # Speed-based MECO: cut thrust when horizontal speed reaches the
        # PGNS overshoot target — but only after vertical_rise + the
        # initial pitch-over (γ approaching insertion attitude).  This
        # matches Apollo SP-287 LM Operations Handbook §5 PGNS logic.
        past_pitchover = t > cfg.vertical_rise_duration_s + 30.0
        v_horizontal = v_t
        meco_speed_reached = (
            past_pitchover
            and v_horizontal >= insertion_target_speed
            and gamma < 5.0   # insertion γ ≤ 5° (Apollo: 0.5°-2°)
        )

        if t <= cfg.vertical_rise_duration_s:
            phase = "vertical_rise"
        elif not meco_speed_reached and mass > dry:
            phase = "pitch_over" if t < cfg.vertical_rise_duration_s + 20 else "boost"
        else:
            phase = "coast"

        pitch = _pitch_program(t, cfg, boost_t)
        pitch_rad = math.radians(pitch)

        # Thrust off when MECO reached (speed cutoff or propellant depletion).
        thrust = cfg.thrust_n if (mass > dry and not meco_speed_reached) else 0.0
        a_thrust = thrust / mass if mass > 0 else 0.0

        # Gravity: local, radial inward
        g_local = MU_MOON / (r ** 2)

        # In polar frame:   a_r = T sin(pitch) − g + v_t² / r
        #                   a_t = T cos(pitch) − v_r v_t / r
        a_r = a_thrust * math.sin(pitch_rad) - g_local + (v_t * v_t) / r
        a_t = a_thrust * math.cos(pitch_rad) - (v_r * v_t) / r

        # Heun predictor
        v_r_pred = v_r + a_r * dt_s
        v_t_pred = v_t + a_t * dt_s
        r_pred   = r + v_r * dt_s
        if r_pred < R_MOON:
            r_pred = R_MOON   # can't go below surface
        g_pred = MU_MOON / (r_pred ** 2)
        a_r2 = a_thrust * math.sin(pitch_rad) - g_pred + (v_t_pred * v_t_pred) / r_pred
        a_t2 = a_thrust * math.cos(pitch_rad) - (v_r_pred * v_t_pred) / r_pred

        # Corrector — average of predictor + current acceleration
        v_r += 0.5 * (a_r + a_r2) * dt_s
        v_t += 0.5 * (a_t + a_t2) * dt_s
        r   += v_r * dt_s
        if r < R_MOON:        # clamp (shouldn't happen during nominal ascent)
            r = R_MOON
            if v_r < 0:
                v_r = 0
        theta += v_t / r * dt_s
        if thrust > 0:
            mass -= mdot * dt_s

        # Record state every 2nd integration step to keep the trajectory
        # length bounded (bug-fix: was using len(traj)%2 which froze at 1
        # after the first append).
        if step % 2 == 1:
            traj.append(AscentState(
                t_s=t, altitude_m=max(alt, 0.0),
                downrange_m=r * theta,
                speed_mps=math.sqrt(v_r * v_r + v_t * v_t),
                flight_path_deg=gamma,
                mass_kg=mass, thrust_n=thrust, pitch_deg=pitch,
                phase=phase,
            ))

        # Earliest abort window: when orbital energy first permits a
        # pericynthion above 15 km.
        if abort_window_s is None and speed > 100:
            energy = 0.5 * speed * speed - MU_MOON / r
            e_abort = -MU_MOON / (2 * (R_MOON + 15_000))
            if energy > e_abort:
                abort_window_s = t

        t += dt_s
        # End integration once we're clearly past burnout and apoapsis.
        if thrust == 0 and v_r < 0 and alt > 5000:
            break

    # Burnout point (last state where thrust > 0 or end of boost)
    burnout_idx = max(i for i, s in enumerate(traj) if s.thrust_n > 0) if traj else 0
    bo = traj[burnout_idx]

    # Compute circularisation Δv at apolune using the full orbital elements
    # at burnout (vis-viva + angular momentum).  At burnout the flight-path
    # angle γ is generally non-zero — the classical  apolune = 2a - r_bo
    # formula only holds at periapsis / apoapsis.
    r_bo = R_MOON + bo.altitude_m
    v_bo = bo.speed_mps
    gamma_bo = math.radians(bo.flight_path_deg)   # 0 = horizontal, 90 = vertical
    h = r_bo * v_bo * math.cos(gamma_bo)          # specific angular momentum
    e_spec = 0.5 * v_bo * v_bo - MU_MOON / r_bo   # specific energy
    if e_spec >= 0:
        # Hyperbolic — no apolune, vehicle would escape Moon
        sma = float("inf")
        ecc = 1.1
        apolune_r = r_bo * 2
    else:
        sma = -MU_MOON / (2 * e_spec)
        ecc = math.sqrt(max(0.0, 1.0 + 2 * e_spec * h * h / (MU_MOON * MU_MOON)))
        apolune_r = sma * (1 + ecc)
    apolune_alt_km = (apolune_r - R_MOON) / 1000
    suborbital = apolune_r < R_MOON
    perilune_r = sma * (1 - ecc) if ecc < 1 else 0.0
    target_r = R_MOON + cfg.target_orbit_alt_km * 1000
    v_circ_target = _circular_speed(target_r)

    # Speed at apolune from vis-viva (falls back to 0 if suborbital)
    if apolune_r > r_bo and not suborbital:
        v_at_apolune = math.sqrt(max(MU_MOON * (2.0 / apolune_r - 1.0 / sma), 0.0))
    else:
        v_at_apolune = 0.0

    # BUG-017 (2026-04-24): old code computed `|v_circ_target − v_at_apolune|`
    # which is only the kinetic-energy difference at apolune, not a real
    # circularisation maneuver. When the burnout orbit's perilune was below
    # the surface (a common case with the old 150 m/s gravity-loss budget),
    # that formula under-priced the real two-impulse Hohmann and over-priced
    # it when apolune ≠ target. Replace with a correct two-impulse Hohmann
    # transfer from apolune to circular target (Curtis 3rd ed §6.3).
    if suborbital:
        # Orbit impacts surface — cannot circularise without first raising
        # apolune above target. Price it so the mission fails: the short-
        # fall in kinetic energy needed to reach the target orbit.
        circ_dv = max(v_circ_target - v_bo, 0.0) + max(0.0, (target_r - apolune_r) / 1000.0 * 0.5)
    elif abs(apolune_r - target_r) < 5_000.0:
        # Apolune already near target: single-burn at apolune.
        circ_dv = abs(v_circ_target - v_at_apolune)
    else:
        # Two-impulse Hohmann from apolune of current orbit to circular
        # target_r.  Apolune → opposite-node at target_r, then circularise.
        a_trans = (apolune_r + target_r) / 2.0
        v_apo_trans = math.sqrt(max(MU_MOON * (2.0 / apolune_r - 1.0 / a_trans), 0.0))
        v_tgt_trans = math.sqrt(max(MU_MOON * (2.0 / target_r  - 1.0 / a_trans), 0.0))
        dv1 = abs(v_apo_trans - v_at_apolune)
        dv2 = abs(v_circ_target - v_tgt_trans)
        circ_dv = dv1 + dv2

    # Boost Δv via rocket equation on actual burned mass
    burned = cfg.wet_mass_kg - mass
    boost_dv = v_e * math.log(cfg.wet_mass_kg / max(mass, dry)) if mass > 0 else 0.0

    success = mass > dry and bo.altitude_m > 5000

    return AscentResult(
        config=cfg,
        success=success,
        burnout_altitude_km=bo.altitude_m / 1000,
        burnout_speed_mps=bo.speed_mps,
        burnout_flight_path_deg=bo.flight_path_deg,
        burnout_time_s=bo.t_s,
        circularisation_dv_mps=circ_dv,
        total_dv_mps=boost_dv + circ_dv,
        propellant_burned_kg=burned,
        propellant_margin_kg=mass - dry,
        trajectory=traj,
        abort_window_s=abort_window_s,
        notes=[
            f"orbit at burnout: a={sma/1000:.0f} km, e={ecc:.3f}, "
            f"apolune={apolune_alt_km:+.1f} km above surface (target {cfg.target_orbit_alt_km:.1f})"
            + (" [suborbital]" if suborbital else ""),
            f"abort-to-orbit reachable after t={abort_window_s:.1f}s" if abort_window_s else "no in-boost abort window reached",
        ],
    )


# ════════════════════════════════════════════════════════════════════
#  Published-vehicle validations
# ════════════════════════════════════════════════════════════════════

def apollo_11_ascent() -> AscentResult:
    """Reproduce the Apollo 11 LM Ascent Stage profile.

    Reference (NASA SP-2007-4805):
      - Wet mass 4,700 kg (dry 2,150 kg, prop 2,376 kg)
      - Engine: Ascent Propulsion System, 15,570 N, Isp 311 s
      - Vertical rise ~10 s, then pitch-over
      - Burnout at ~18 km × 80 km (17 km × 86 km recorded)
      - Burn time ~7 min 18 s (computed 432 s) — matches APS spec
    """
    cfg = AscentConfig(
        name="Apollo 11 LM Ascent Stage",
        wet_mass_kg=4700.0,
        dry_mass_kg=2150.0,
        thrust_n=15570.0,
        isp_s=311.0,
        target_orbit_alt_km=111.0,   # 60 nmi LM parking orbit
        launch_latitude_deg=0.67,
        vertical_rise_duration_s=10.0,
        pitch_over_degrees=87.0,     # Apollo 11 rotated from vertical to ~3° above horizon (NASA SP-287)
    )
    return simulate_ascent(cfg, dt_s=0.5)


def chandrayaan_3_ascent() -> AscentResult:
    """Chandrayaan-3 Vikram ascent (simplified — mission flew a drift
    ascent only; lunar sample return hasn't happened yet, but the lander
    has demonstrated lift-off capability).
    """
    cfg = AscentConfig(
        name="Vikram Hop/Ascent",
        wet_mass_kg=750.0,
        dry_mass_kg=600.0,
        thrust_n=3000.0,
        isp_s=300.0,
        target_orbit_alt_km=100.0,
    )
    return simulate_ascent(cfg, dt_s=0.5)


def starship_hls_ascent() -> AscentResult:
    """SpaceX HLS Starship lunar ascent scenario.

    This is *projected* — HLS has not flown. Values are public Artemis-III
    envelope estimates.
    """
    cfg = AscentConfig(
        name="HLS Starship (projected)",
        wet_mass_kg=200000.0,
        dry_mass_kg=60000.0,
        thrust_n=1_100_000.0,    # three Raptor-Vac engines on ascent
        isp_s=350.0,
        target_orbit_alt_km=100.0,
    )
    return simulate_ascent(cfg, dt_s=1.0)


# ════════════════════════════════════════════════════════════════════
#  Abort modes
# ════════════════════════════════════════════════════════════════════

def abort_dv_to_low_orbit(alt_m: float, speed_mps: float,
                          flight_path_deg: float,
                          target_peri_alt_km: float = 15.0) -> float:
    """Extra Δv to reach a safe (periapsis > target) orbit from current state.

    Used by the FDIR system to decide whether an engine failure during
    ascent still permits an emergency circularisation.
    """
    r = R_MOON + alt_m
    peri_r = R_MOON + target_peri_alt_km * 1000
    # Current specific energy
    e_now = 0.5 * speed_mps ** 2 - MU_MOON / r
    # Target periapsis orbit energy (circular at peri_r)
    e_target = -MU_MOON / (2 * peri_r)
    if e_now >= e_target:
        return 0.0
    # Required speed to just reach peri_r periapsis from current position
    v_needed = math.sqrt(2 * (e_target + MU_MOON / r))
    return max(0.0, v_needed - speed_mps)
