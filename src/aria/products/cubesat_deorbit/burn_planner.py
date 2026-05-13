"""Multi-impulse de-orbit burn planning.

The single-impulse Hohmann lower used in :mod:`advisor` is acceptable
for end-of-life CubeSats whose ΔV budget is large compared to the
required reduction.  Operators with a tighter propellant margin or a
need to control reentry timing more precisely use a *multi-impulse*
schedule:

  * **Two-impulse Hohmann lower** — one retrograde burn at apoapsis
    lowers periapsis below the original altitude; a second retrograde
    burn at the new periapsis circularises onto a lower orbit.  The
    spacecraft can dwell at the lower altitude for an arbitrary
    number of orbits before the entry burn.  Total ΔV is the same as
    a direct Hohmann transfer between the original and final
    altitudes — but the burns are smaller and the timing is decoupled.

  * **Three-impulse bi-elliptic** — useful when the *apoapsis* of the
    starting orbit needs to be raised before lowering periapsis (rare
    for de-orbit; common for raise-then-deorbit scenarios from MEO).

  * **N-impulse staged drop** — repeatedly lower periapsis in a few
    km steps so each individual burn never exceeds a per-burn
    propellant ceiling.  This is the pattern many smallsat
    EP (electric-propulsion) thrusters require because they can only
    sustain a few hundred metres-per-second of ΔV per maneuver
    window.

References:
  * Vallado, *Fundamentals of Astrodynamics and Applications*, 4th ed.,
    §9.2 (Hohmann), §9.3 (bi-elliptic).
  * Curtis, *Orbital Mechanics for Engineering Students*, 3rd ed.,
    §6.3 (multi-impulse plane-change ratio).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional


# WGS-84 + GM Earth — same constants as :mod:`advisor`.
R_EARTH_KM = 6378.137
MU_EARTH_KM3_S2 = 398_600.4418
G0 = 9.806_65


@dataclass(frozen=True)
class Impulse:
    """One leg of a multi-impulse burn plan."""
    sequence: int                              # 1, 2, 3, …
    epoch_utc: datetime
    delta_v_mps: float
    direction: str                             # "retrograde" / "prograde" / "radial+/-"
    propellant_kg: float
    perigee_after_km: float
    apogee_after_km: float
    notes: str = ""


@dataclass(frozen=True)
class MultiImpulsePlan:
    """A schedule of two or more impulses.  Same return shape as
    ``advisor.BurnPlan`` augmented with the impulse list."""
    impulses: List[Impulse]
    total_delta_v_mps: float
    total_propellant_kg: float
    propellant_margin_kg: float
    expected_reentry_utc: datetime
    notes: str = ""

    @property
    def n_impulses(self) -> int:
        return len(self.impulses)


# ── Helpers ────────────────────────────────────────────────────


def _mean_motion_period_s(a_km: float) -> float:
    return 2.0 * math.pi * math.sqrt(a_km ** 3 / MU_EARTH_KM3_S2)


def _v_circular_kmps(r_km: float) -> float:
    return math.sqrt(MU_EARTH_KM3_S2 / r_km)


def _v_at_radius(r_km: float, a_km: float) -> float:
    """Vis-viva: v² = μ(2/r − 1/a)."""
    return math.sqrt(MU_EARTH_KM3_S2 * (2.0 / r_km - 1.0 / a_km))


def _propellant_kg_for_dv(
    wet_mass_kg: float, dv_mps: float, isp_s: float,
) -> float:
    """Tsiolkovsky inverse: Δm = m·(1 − exp(−Δv/(Isp·g₀)))."""
    if wet_mass_kg <= 0.0 or dv_mps <= 0.0 or isp_s <= 0.0:
        return 0.0
    return wet_mass_kg * (1.0 - math.exp(-dv_mps / (isp_s * G0)))


# ── Two-impulse Hohmann lower ──────────────────────────────────


def plan_two_impulse_hohmann(
    *,
    start_alt_km: float,
    final_alt_km: float,
    epoch_utc: datetime,
    wet_mass_kg: float,
    propellant_kg: float,
    isp_s: float,
    dwell_orbits_at_final: int = 0,
) -> Optional[MultiImpulsePlan]:
    """Two-impulse Hohmann lower from ``start_alt_km`` to ``final_alt_km``.

    Both starting and ending orbits are circular.  The transfer
    ellipse has apogee at the starting radius and perigee at the
    final radius.  Burn-1 lowers the orbit to the transfer ellipse;
    burn-2 (a half-period later) circularises at the lower altitude.

    Returns ``None`` if propellant or ΔV is insufficient.
    """
    if final_alt_km >= start_alt_km:
        return None
    r1 = R_EARTH_KM + start_alt_km
    r2 = R_EARTH_KM + final_alt_km
    a_t = (r1 + r2) / 2.0

    v1 = _v_circular_kmps(r1)
    v_t_apo = _v_at_radius(r1, a_t)
    v_t_per = _v_at_radius(r2, a_t)
    v2 = _v_circular_kmps(r2)

    dv1_mps = (v1 - v_t_apo) * 1000.0
    dv2_mps = (v_t_per - v2) * 1000.0
    total_dv = dv1_mps + dv2_mps

    # Propellant (mass-after-burn-1 wet mass for burn-2).
    m_w1 = wet_mass_kg
    burn1_kg = _propellant_kg_for_dv(m_w1, dv1_mps, isp_s)
    m_w2 = m_w1 - burn1_kg
    burn2_kg = _propellant_kg_for_dv(m_w2, dv2_mps, isp_s)
    total_kg = burn1_kg + burn2_kg

    if total_kg > propellant_kg:
        return None

    half_period_s = _mean_motion_period_s(a_t) / 2.0
    epoch1 = epoch_utc
    epoch2 = epoch1 + timedelta(seconds=half_period_s)

    # Reentry: dwell + N orbits at lower circular, then natural
    # decay covers the rest.  We report ``epoch2`` as the
    # operational reentry-prep epoch — actual atmospheric reentry is
    # beyond the burn plan's scope.
    period_final_s = _mean_motion_period_s(r2)
    reentry_eta = epoch2 + timedelta(
        seconds=max(dwell_orbits_at_final, 0) * period_final_s,
    )

    impulses = [
        Impulse(
            sequence=1, epoch_utc=epoch1, delta_v_mps=dv1_mps,
            direction="retrograde", propellant_kg=burn1_kg,
            perigee_after_km=final_alt_km, apogee_after_km=start_alt_km,
            notes="Lower periapsis to transfer-orbit perigee.",
        ),
        Impulse(
            sequence=2, epoch_utc=epoch2, delta_v_mps=dv2_mps,
            direction="retrograde", propellant_kg=burn2_kg,
            perigee_after_km=final_alt_km, apogee_after_km=final_alt_km,
            notes="Circularise at the lower altitude.",
        ),
    ]
    return MultiImpulsePlan(
        impulses=impulses,
        total_delta_v_mps=total_dv,
        total_propellant_kg=total_kg,
        propellant_margin_kg=max(propellant_kg - total_kg, 0.0),
        expected_reentry_utc=reentry_eta,
        notes=(
            f"Two-impulse Hohmann {start_alt_km:.0f} → {final_alt_km:.0f} km; "
            f"transfer-orbit half-period {half_period_s:.1f} s."
        ),
    )


# ── N-impulse staged drop ──────────────────────────────────────


def plan_staged_drop(
    *,
    start_alt_km: float,
    final_alt_km: float,
    epoch_utc: datetime,
    wet_mass_kg: float,
    propellant_kg: float,
    isp_s: float,
    max_dv_per_burn_mps: float,
    coast_orbits_between_burns: int = 1,
) -> Optional[MultiImpulsePlan]:
    """Plan a staged drop — many small Hohmann lowerings — when the
    thruster can only deliver ``max_dv_per_burn_mps`` per maneuver.

    The full Hohmann ΔV from start→final is split evenly across
    N burns, where N = ceil(ΔV_total / max_dv_per_burn_mps).
    Each burn lowers the orbit by approximately
    ``(start_alt − final_alt) / N`` km.  This is a first-order
    plan suitable for EP missions; high-fidelity timing requires the
    operator's own astrodynamics flight software.
    """
    if final_alt_km >= start_alt_km or max_dv_per_burn_mps <= 0.0:
        return None
    full = plan_two_impulse_hohmann(
        start_alt_km=start_alt_km, final_alt_km=final_alt_km,
        epoch_utc=epoch_utc, wet_mass_kg=wet_mass_kg,
        propellant_kg=propellant_kg, isp_s=isp_s,
    )
    if full is None:
        return None
    n_burns = max(1, int(math.ceil(full.total_delta_v_mps / max_dv_per_burn_mps)))
    if n_burns == 1:
        return full

    drop_per = (start_alt_km - final_alt_km) / n_burns
    period_at_top_s = _mean_motion_period_s(R_EARTH_KM + start_alt_km)
    coast_per_burn_s = max(1, coast_orbits_between_burns) * period_at_top_s

    impulses: List[Impulse] = []
    cur_alt = start_alt_km
    cur_mass = wet_mass_kg
    cur_epoch = epoch_utc
    total_dv = 0.0
    total_prop = 0.0
    for k in range(1, n_burns + 1):
        next_alt = max(final_alt_km, cur_alt - drop_per)
        leg = plan_two_impulse_hohmann(
            start_alt_km=cur_alt, final_alt_km=next_alt,
            epoch_utc=cur_epoch, wet_mass_kg=cur_mass,
            propellant_kg=propellant_kg - total_prop, isp_s=isp_s,
        )
        if leg is None:
            return None
        for imp in leg.impulses:
            impulses.append(Impulse(
                sequence=len(impulses) + 1,
                epoch_utc=imp.epoch_utc,
                delta_v_mps=imp.delta_v_mps,
                direction=imp.direction,
                propellant_kg=imp.propellant_kg,
                perigee_after_km=imp.perigee_after_km,
                apogee_after_km=imp.apogee_after_km,
                notes=f"Stage {k}/{n_burns}: {imp.notes}",
            ))
        total_dv += leg.total_delta_v_mps
        total_prop += leg.total_propellant_kg
        cur_mass -= leg.total_propellant_kg
        cur_alt = next_alt
        cur_epoch = leg.expected_reentry_utc + timedelta(seconds=coast_per_burn_s)

    if total_prop > propellant_kg:
        return None

    return MultiImpulsePlan(
        impulses=impulses,
        total_delta_v_mps=total_dv,
        total_propellant_kg=total_prop,
        propellant_margin_kg=propellant_kg - total_prop,
        expected_reentry_utc=cur_epoch,
        notes=(
            f"{n_burns}-stage drop {start_alt_km:.0f} → {final_alt_km:.0f} km "
            f"with {max_dv_per_burn_mps:.0f} m/s per-burn ceiling."
        ),
    )
