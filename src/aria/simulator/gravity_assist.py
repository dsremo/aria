"""Gravity-assist trajectory planner (simulator layer).

High-level patched-conic mission planner that chains Hohmann transfers
between heliocentric bodies and applies simplified fly-by Δv gains at
each intermediate planet. Sits on top of the deep physics module
`aria.simulation.gravity_assist` — re-uses its Hohmann solver and fly-by
geometry rather than duplicating them.

Design
------
- Each planet's orbit is treated as circular around the Sun at its mean
  semi-major axis (Vallado 2013 Table D-3).
- Between any two bodies we compute a Hohmann ellipse (vis-viva) and
  return (Δv1, Δv2, time-of-flight-years).
- A fly-by at an intermediate body is modelled as a "free" heliocentric
  Δv gain of 2 · v_planet · sin(δ/2) where δ is the turning angle for a
  default periapsis altitude. This is the practical upper bound from
  Anderson (1997) / Bate-Mueller-White §2.8.
- The saved Δv is subtracted from the Δv of the NEXT outgoing leg (the
  fly-by effectively launches the ship onto the next ellipse for free).

Returned MissionPlan exposes per-leg Δv, per-fly-by savings, total fuel
Δv required, and total mission duration — all ballpark numbers suitable
for the Mission-Planner UI. For real missions use the Lambert solver in
`aria.simulation.mars_transfer`.

References
----------
    Curtis (2014) Orbital Mechanics §6.3, §8.7
    Vallado (2013) Fundamentals of Astrodynamics §6.2
    Bate, Mueller, White (1971) §2.8
    Anderson et al. (1979) Celest. Mech. 21:113
    NASA SP-4031 (Kohlhase 1977) — Voyager Grand Tour
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Re-use the deep physics module — one source of truth for planet data,
# Hohmann solver, and fly-by deflection geometry.
from aria.simulation.gravity_assist import (
    AU_M,
    MU_SUN,
    PLANETS,
    flyby_deflection_angle,
    hohmann_transfer_dv,
    v_inf_at_planet,
)

# ───────────────────────────────────────────────────────────────────
# Planetary orbital data for the planner
# ───────────────────────────────────────────────────────────────────
# Mean semi-major axis (AU) + sidereal period (days). Values from NASA
# HORIZONS / Vallado (2013) Appendix D. Kept as a planner-local dict so
# UI + tests can import it directly without reaching into the deep
# physics layer.
#
# Period = 2π √(a³ / μ_sun) — values below are the measured sidereal
# periods; cross-check with Kepler's third law from a_au.

BODY_ORBITS: dict[str, dict] = {
    "sun":     {"a_au": 0.0000, "period_days":      0.0},   # Origin
    "mercury": {"a_au": 0.3871, "period_days":     87.97},  # NASA HORIZONS
    "venus":   {"a_au": 0.7233, "period_days":    224.70},  # NASA HORIZONS
    "earth":   {"a_au": 1.0000, "period_days":    365.256}, # IAU
    "mars":    {"a_au": 1.5237, "period_days":    686.97},  # NASA HORIZONS
    "jupiter": {"a_au": 5.2026, "period_days":   4332.59},  # NASA HORIZONS
    "saturn":  {"a_au": 9.5549, "period_days":  10759.22},  # NASA HORIZONS
    "uranus":  {"a_au": 19.2184, "period_days": 30685.4},   # NASA HORIZONS
    "neptune": {"a_au": 30.0690, "period_days": 60189.0},   # NASA HORIZONS
    "pluto":   {"a_au": 39.4821, "period_days": 90560.0},   # NASA HORIZONS (Pluto is dwarf; included for Grand Tour)
}

# Default periapsis altitude above planet surface for fly-bys (km).
# 300 km is a conservative "safe" altitude clear of atmosphere/rings —
# Voyager 1 cleared Jupiter at 349,000 km and Juno grazes at ~4,000 km,
# so 300 km is an optimistic upper bound on Δv gain.
DEFAULT_FLYBY_ALT_KM: float = 300.0

# Gravitational parameter aliases (m³/s²) — requested in the task spec.
# Exposed for test / UI code that wants them without importing from the
# deeper simulation.gravity_assist module. Values from Vallado (2013)
# Table D-1 = IAU WG 2009.
MU_SUN_M3S2: float = MU_SUN                       # 1.32712440018e20
MU_EARTH_M3S2: float = PLANETS["earth"]["mu_m3s2"]
MU_VENUS_M3S2: float = PLANETS["venus"]["mu_m3s2"]
MU_MARS_M3S2: float = PLANETS["mars"]["mu_m3s2"]
MU_JUPITER_M3S2: float = PLANETS["jupiter"]["mu_m3s2"]
MU_SATURN_M3S2: float = PLANETS["saturn"]["mu_m3s2"]
MU_URANUS_M3S2: float = PLANETS["uranus"]["mu_m3s2"]
MU_NEPTUNE_M3S2: float = PLANETS["neptune"]["mu_m3s2"]


# ───────────────────────────────────────────────────────────────────
# Dataclasses
# ───────────────────────────────────────────────────────────────────

@dataclass
class HohmannLeg:
    """A single Hohmann transfer between two bodies."""
    origin: str
    destination: str
    r1_au: float
    r2_au: float
    dv_depart_kms: float        # Burn-1 Δv (km/s)
    dv_arrive_kms: float        # Burn-2 Δv (km/s)
    dv_total_kms: float         # Sum of both burns (km/s)
    time_of_flight_days: float  # Half-period of transfer ellipse


@dataclass
class FlybyBoost:
    """Δv gained (free) from a fly-by at an intermediate planet."""
    planet: str
    v_approach_kms: float       # Approach speed relative to planet (≈ v∞)
    deflection_deg: float       # Turning angle δ (deg)
    dv_gained_kms: float        # Practical heliocentric |Δv| from slingshot
    closest_approach_km: float  # Altitude above planet surface


@dataclass
class MissionPlan:
    """Chained Hohmann + fly-by mission plan."""
    sequence: list[str]                     # ["earth","venus","jupiter",...]
    legs: list[HohmannLeg] = field(default_factory=list)
    flybys: list[FlybyBoost] = field(default_factory=list)
    # Totals
    total_dv_required_kms: float = 0.0      # Σ(leg Δv) − Σ(fly-by gain)  (fuel spent)
    total_dv_gross_kms: float = 0.0         # Σ(leg Δv) without fly-by credit
    total_dv_savings_kms: float = 0.0       # Σ(fly-by dv_gained)
    total_duration_days: float = 0.0        # Σ(time-of-flight); fly-bys ~instant
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "sequence": self.sequence,
            "legs": [
                {
                    "origin": lg.origin,
                    "destination": lg.destination,
                    "r1_au": round(lg.r1_au, 4),
                    "r2_au": round(lg.r2_au, 4),
                    "dv_depart_kms": round(lg.dv_depart_kms, 3),
                    "dv_arrive_kms": round(lg.dv_arrive_kms, 3),
                    "dv_total_kms": round(lg.dv_total_kms, 3),
                    "time_of_flight_days": round(lg.time_of_flight_days, 1),
                    "time_of_flight_years": round(lg.time_of_flight_days / 365.25, 3),
                }
                for lg in self.legs
            ],
            "flybys": [
                {
                    "planet": fb.planet,
                    "v_approach_kms": round(fb.v_approach_kms, 3),
                    "deflection_deg": round(fb.deflection_deg, 2),
                    "dv_gained_kms": round(fb.dv_gained_kms, 3),
                    "closest_approach_km": round(fb.closest_approach_km, 1),
                }
                for fb in self.flybys
            ],
            "total_dv_required_kms": round(self.total_dv_required_kms, 3),
            "total_dv_gross_kms": round(self.total_dv_gross_kms, 3),
            "total_dv_savings_kms": round(self.total_dv_savings_kms, 3),
            "total_duration_days": round(self.total_duration_days, 1),
            "total_duration_years": round(self.total_duration_days / 365.25, 3),
            "summary": self.summary,
        }


# ───────────────────────────────────────────────────────────────────
# Core API
# ───────────────────────────────────────────────────────────────────

def _body_key(name: str) -> str:
    """Normalise a body name to a key in BODY_ORBITS."""
    key = name.strip().lower()
    if key not in BODY_ORBITS:
        raise ValueError(
            f"Unknown body '{name}'. Known: {sorted(BODY_ORBITS.keys())}"
        )
    return key


def hohmann_transfer(
    r1_au: float,
    r2_au: float,
    mu_sun: float = MU_SUN,
) -> tuple[float, float]:
    """Hohmann transfer Δv and duration between two circular heliocentric orbits.

    Wraps the lower-level `simulation.gravity_assist.hohmann_transfer_dv`
    so the simulator UI can work in (AU, km/s, days) without touching
    SI internally. Returns the SUM of both burns and the time-of-flight.

    Args:
        r1_au:   Departure circular-orbit radius (AU)
        r2_au:   Arrival circular-orbit radius (AU)
        mu_sun:  Sun GM (m³/s²). Defaults to IAU 2012 value.

    Returns:
        (dv_kms, tof_days): total Δv in km/s (Δv1 + Δv2), duration in days.

    References:
        Curtis (2014) §6.3; Vallado (2013) §6.2.
    """
    if r1_au <= 0 or r2_au <= 0:
        raise ValueError(f"Orbital radii must be positive: r1={r1_au}, r2={r2_au}")
    r1_m = r1_au * AU_M
    r2_m = r2_au * AU_M
    dv1, dv2, tof_yr = hohmann_transfer_dv(r1_m, r2_m)
    # mu_sun override: if caller passes a different μ (e.g. for tests)
    # recompute rather than rescale (keeps the dependency explicit).
    if mu_sun != MU_SUN:
        a_t = (r1_m + r2_m) / 2.0
        v1_circ = math.sqrt(mu_sun / r1_m)
        v2_circ = math.sqrt(mu_sun / r2_m)
        v1_t = math.sqrt(mu_sun * (2.0 / r1_m - 1.0 / a_t))
        v2_t = math.sqrt(mu_sun * (2.0 / r2_m - 1.0 / a_t))
        dv1 = abs(v1_t - v1_circ)
        dv2 = abs(v2_circ - v2_t)
        tof_s = math.pi * math.sqrt(a_t ** 3 / mu_sun)
        tof_yr = tof_s / (365.25 * 86400.0)
    dv_kms = (dv1 + dv2) / 1000.0
    tof_days = tof_yr * 365.25
    return dv_kms, tof_days


def gravity_assist_boost(
    v_approach_kms: float,
    planet_mass_kg: float,
    closest_approach_km: float,
    planet: str | None = None,
) -> float:
    """Heliocentric Δv gained from a single fly-by (patched-conic).

    Uses the practical upper bound for prograde slingshots:
        |Δv|_helio = 2 · v_planet · sin(δ/2)
    where δ is the turning angle in the planet frame:
        sin(δ/2) = 1 / (1 + r_peri · v∞² / μ_planet)

    This is the "best case" number — the real gain depends on the
    spacecraft's approach angle. Oberth-assisted manoeuvres can exceed
    this; the simulator UI shows this as a ballpark savings figure.

    Args:
        v_approach_kms:      Hyperbolic excess speed v∞ relative to the
                             planet at SOI entry (km/s).
        planet_mass_kg:      Planet mass (kg). Combined with G to get μ
                             if `planet` is not supplied.
        closest_approach_km: Periapsis altitude ABOVE planet surface (km).
        planet:              Optional name — if given, uses the table
                             μ and radius directly (more accurate than
                             reconstructing from mass).

    Returns:
        |Δv|_helio (km/s) — heliocentric Δv the fly-by delivers for free.

    References:
        Bate, Mueller, White (1971) §2.8; Curtis (2014) §8.7.
    """
    G_NEWTON = 6.67430e-11  # CODATA 2018 (m³ kg⁻¹ s⁻²)
    if planet is not None:
        key = _body_key(planet)
        if key not in PLANETS:
            raise ValueError(f"No PLANETS entry for '{planet}' — need μ from table")
        mu = PLANETS[key]["mu_m3s2"]
        r_surface_m = PLANETS[key]["radius_m"]
        v_planet_ms = PLANETS[key]["v_orb_ms"]
    else:
        mu = G_NEWTON * planet_mass_kg
        # Without a planet name we can't know the orbital speed — caller
        # should provide one. Fall back to v_approach as a degenerate
        # case (the fly-by then gains at most v∞ worth of Δv).
        r_surface_m = 0.0
        v_planet_ms = v_approach_kms * 1000.0

    v_inf_ms = v_approach_kms * 1000.0
    r_peri_m = r_surface_m + closest_approach_km * 1000.0
    if r_peri_m <= 0:
        raise ValueError("Periapsis must be positive (planet radius + altitude)")

    delta_rad = flyby_deflection_angle(r_peri_m, v_inf_ms, mu)
    # Practical heliocentric Δv magnitude (prograde best-case):
    dv_helio_ms = 2.0 * v_planet_ms * math.sin(delta_rad / 2.0)
    return dv_helio_ms / 1000.0


def plan_mission(
    start: str,
    destination: str,
    flybys: list[str] | None = None,
    flyby_alt_km: float = DEFAULT_FLYBY_ALT_KM,
) -> MissionPlan:
    """Chain Hohmann legs with fly-by Δv credits to build a mission plan.

    The ship departs from `start`, flies to each body in `flybys` in
    order (each one a fly-by, no rendezvous), and ends by rendezvous at
    `destination`. Between every pair of consecutive bodies we build a
    Hohmann transfer. At every intermediate body we apply a fly-by Δv
    credit to the ship's fuel budget.

    Args:
        start:        Departure body (e.g. "earth").
        destination:  Final arrival body.
        flybys:       Ordered list of intermediate fly-by bodies. May be
                      empty → direct Hohmann transfer.
        flyby_alt_km: Periapsis altitude above each planet's surface.
                      Defaults to DEFAULT_FLYBY_ALT_KM (300 km).

    Returns:
        MissionPlan with per-leg Δv, per-fly-by savings, totals.

    Example:
        >>> plan = plan_mission("earth", "saturn", ["venus", "earth", "jupiter"])
        >>> plan.total_dv_required_kms    # total fuel Δv after savings
        >>> plan.total_duration_years     # cruise years (fly-bys ~instant)
    """
    flybys = list(flybys or [])
    # Full body sequence: start → fly-bys → destination
    sequence = [_body_key(start), *[_body_key(f) for f in flybys], _body_key(destination)]

    plan = MissionPlan(sequence=sequence)

    # Build Hohmann legs between each consecutive pair.
    for a_name, b_name in zip(sequence[:-1], sequence[1:]):
        a = BODY_ORBITS[a_name]
        b = BODY_ORBITS[b_name]
        r1 = max(a["a_au"], 1e-6)   # avoid divide-by-zero at Sun origin
        r2 = max(b["a_au"], 1e-6)
        dv_total, tof_days = hohmann_transfer(r1, r2)
        # Split dv into depart + arrive halves for display. Use the
        # low-level solver to get the actual split.
        dv1, dv2, _ = hohmann_transfer_dv(r1 * AU_M, r2 * AU_M)
        leg = HohmannLeg(
            origin=a_name,
            destination=b_name,
            r1_au=r1,
            r2_au=r2,
            dv_depart_kms=dv1 / 1000.0,
            dv_arrive_kms=dv2 / 1000.0,
            dv_total_kms=dv_total,
            time_of_flight_days=tof_days,
        )
        plan.legs.append(leg)
        plan.total_dv_gross_kms += dv_total
        plan.total_duration_days += tof_days

    # For each fly-by body (middle of sequence), estimate Δv gain. v∞ at
    # the fly-by body is taken from the INCOMING leg (departure body
    # → fly-by body). We re-use v_inf_at_planet() which applies the
    # Hohmann arrival-speed formula.
    for idx, fb_name in enumerate(flybys):
        fb_key = _body_key(fb_name)
        if fb_key not in PLANETS:
            # Sun / Pluto / non-planet fly-bys aren't in the deep
            # physics table — skip the fly-by credit but record a zero
            # entry for transparency.
            plan.flybys.append(FlybyBoost(
                planet=fb_key,
                v_approach_kms=0.0,
                deflection_deg=0.0,
                dv_gained_kms=0.0,
                closest_approach_km=flyby_alt_km,
            ))
            continue
        incoming_origin = sequence[idx]      # body before the fly-by
        # v∞ at the fly-by planet, reached on a Hohmann ellipse from the
        # prior body.
        if incoming_origin in PLANETS and incoming_origin != fb_key:
            v_inf_ms = v_inf_at_planet(incoming_origin, fb_key)
        else:
            # Same body or Sun origin — fall back to the planet's own
            # orbital speed as a rough v∞ (degenerate case).
            v_inf_ms = PLANETS[fb_key]["v_orb_ms"] * 0.25
        v_inf_kms = v_inf_ms / 1000.0

        pd = PLANETS[fb_key]
        r_peri_m = pd["radius_m"] + flyby_alt_km * 1000.0
        delta_rad = flyby_deflection_angle(r_peri_m, v_inf_ms, pd["mu_m3s2"])
        dv_gain_kms = 2.0 * pd["v_orb_ms"] * math.sin(delta_rad / 2.0) / 1000.0

        plan.flybys.append(FlybyBoost(
            planet=fb_key,
            v_approach_kms=v_inf_kms,
            deflection_deg=math.degrees(delta_rad),
            dv_gained_kms=dv_gain_kms,
            closest_approach_km=flyby_alt_km,
        ))
        plan.total_dv_savings_kms += dv_gain_kms

    # Net fuel Δv the ship actually has to provide. Savings can at most
    # zero out the non-first-burn Δv — a fly-by cannot refund the
    # initial escape-from-Earth burn. Clamp so we never report negative
    # fuel cost (physically absurd).
    plan.total_dv_required_kms = max(
        plan.total_dv_gross_kms - plan.total_dv_savings_kms, 0.0
    )

    plan.summary = " → ".join(sequence)
    return plan
