"""EVA radiation dose during solar-proton events and GCR background.

Surface EVAs on the Moon have no atmospheric or magnetospheric shielding.
A 500 g/cm² shielded habitat can absorb most of a severe SPE; a 0.3 g/cm²
space-suit gives almost none. During a class-X10 solar event like August
1972 (the "worst on record") an unshielded astronaut would accumulate
~1 Sv in 1-2 hours — mission-ending.

This module computes:
  1. GCR background dose rate during EVA (solar min / solar max)
  2. SPE dose rate given an observed proton flux spectrum (GOES-R SGPS)
  3. Suit + regolith shielding attenuation (proton Bragg-curve, NIST)
  4. Cumulative dose over an EVA plan, with abort-threshold flagging

References:
    Cucinotta, F. A. (2014) "Space Radiation Risks for Astronauts on
        Multiple International Space Station Missions." PLoS ONE 9(4).
    ICRP 123 (2013) "Assessment of Radiation Exposure of Astronauts in
        Space." Ann. ICRP 42(4).
    Kim, M.-H. Y. et al. (2011) "Evaluation of radiation shielding for
        lunar missions," NASA TP-2011-216118.
    NOAA SWPC GOES-R SGPS proton flux thresholds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


# ══════════════════════════════════════════════════════════════════
#  Dose-rate constants
# ══════════════════════════════════════════════════════════════════

# GCR dose equivalent rate (Cucinotta 2014 Table 3 — lunar surface, no shield)
_GCR_SOLAR_MIN_USV_H = 25.0          # µSv/hr, unshielded on Moon
_GCR_SOLAR_MAX_USV_H = 10.0          # µSv/hr (solar max suppresses GCR)
_SPE_BACKGROUND_USV_H = 0.5          # quiet-sun background (essentially GCR only)

# Typical suit shielding (Thomas & McMann 2006): ~0.3 g/cm² Al-equivalent
_SUIT_G_PER_CM2 = 0.3
_HABITAT_G_PER_CM2 = 10.0            # Artemis-class hab, 10 g/cm² Al equivalent
_REGOLITH_G_PER_CM2_1M = 150.0       # 1 m regolith burial ≈ 150 g/cm²

# Proton dose conversion: 1 pfu (#/cm²/s/sr at >10 MeV) × 4π × (LET × eff)
# For broad-spectrum SPE proton flux through 0.3 g/cm² Al, dose eq.
# ≈ 0.05 mSv/hr per pfu (Kim 2011 Fig 5 integrated over suit attenuation).
_DOSE_EQ_MSV_H_PER_PFU = 0.050


# ══════════════════════════════════════════════════════════════════
#  Suit-shield attenuation (simple exponential)
# ══════════════════════════════════════════════════════════════════

def shielding_attenuation(shield_g_cm2: float,
                          mean_energy_mev: float = 50.0) -> float:
    """Fraction of incident dose passing through a slab of Al-equivalent
    shielding. Based on Bragg-range formulae (NIST PSTAR) with a simple
    exponential approximation for space protons.

    Parameters
    ----------
    shield_g_cm2 : slab areal density (g/cm²)
    mean_energy_mev : mean proton energy in the incident spectrum (MeV)

    Returns the transmitted dose fraction (0..1).
    """
    if shield_g_cm2 <= 0:
        return 1.0
    # Half-thickness for 50 MeV protons in Al ≈ 5 g/cm² (NIST)
    # Effective thickness scales with energy^0.8 (Bragg range empirical)
    half_thickness_g_cm2 = 5.0 * (mean_energy_mev / 50.0) ** 0.8
    return float(math.pow(0.5, shield_g_cm2 / half_thickness_g_cm2))


# ══════════════════════════════════════════════════════════════════
#  Events
# ══════════════════════════════════════════════════════════════════

@dataclass
class SolarEvent:
    """Parameters of a solar particle event."""
    name: str = "quiet"
    peak_flux_pfu: float = 0.0         # >10 MeV pfu at Earth (or Moon)
    mean_energy_mev: float = 30.0       # spectrum softness proxy
    duration_hours: float = 24.0
    rise_time_hours: float = 2.0
    decay_time_hours: float = 24.0


# Historical reference events
AUGUST_1972_SPE = SolarEvent(
    name="August 1972 (Apollo-era)",
    peak_flux_pfu=46_000.0,            # NOAA archive peak
    mean_energy_mev=45.0,
    duration_hours=72.0,
    rise_time_hours=3.0,
    decay_time_hours=48.0,
)

OCTOBER_1989_SPE = SolarEvent(
    name="October 1989",
    peak_flux_pfu=40_000.0,
    mean_energy_mev=50.0,
    duration_hours=96.0,
)


# ══════════════════════════════════════════════════════════════════
#  Dose integrator over an EVA plan
# ══════════════════════════════════════════════════════════════════

@dataclass
class EVARadiationResult:
    plan_duration_h: float
    gcr_dose_msv: float
    spe_dose_msv: float
    total_dose_msv: float
    peak_rate_usv_h: float
    shielding_g_cm2: float
    abort_recommended: bool
    abort_reason: str = ""
    time_to_limit_h: Optional[float] = None


def spe_flux_profile(event: SolarEvent, t_h: float) -> float:
    """Proton-flux profile vs time: fast exponential rise, slow decay."""
    if event.peak_flux_pfu <= 0:
        return 0.0
    if t_h < 0:
        return 0.0
    if t_h <= event.rise_time_hours:
        # Exponential rise
        tau = event.rise_time_hours / 3.0
        return event.peak_flux_pfu * (1 - math.exp(-t_h / tau))
    # Exponential decay
    t_since_peak = t_h - event.rise_time_hours
    tau_d = event.decay_time_hours / 3.0
    return event.peak_flux_pfu * math.exp(-t_since_peak / tau_d)


def simulate_eva_dose(eva_duration_h: float,
                      start_offset_h: float = 0.0,
                      event: Optional[SolarEvent] = None,
                      shield_g_cm2: float = _SUIT_G_PER_CM2,
                      solar_max: bool = False,
                      dose_limit_msv: float = 50.0,
                      dt_h: float = 0.25) -> EVARadiationResult:
    """Integrate cumulative dose over an EVA given a background event.

    Parameters
    ----------
    eva_duration_h : planned EVA duration
    start_offset_h : time since event peak at EVA start (can be negative if EVA starts before SPE)
    event : SolarEvent, or None for quiet sun
    shield_g_cm2 : Al-equivalent shielding (suit only = 0.3, habitat ~10, regolith 1m = 150)
    solar_max : use solar-max GCR baseline if True
    dose_limit_msv : astronaut-career-fraction limit (NASA career limit ≈ 1000 mSv;
        per-mission typical 300; short EVA practical 50 mSv is common abort threshold)
    """
    gcr_rate = _GCR_SOLAR_MAX_USV_H if solar_max else _GCR_SOLAR_MIN_USV_H
    gcr_rate_msv = gcr_rate * 1e-3
    # GCR attenuation through shielding (less effective than proton — GCR is harder)
    gcr_att = max(0.5, shielding_attenuation(shield_g_cm2, mean_energy_mev=1000.0))
    gcr_effective = gcr_rate_msv * gcr_att

    total_dose = 0.0
    peak_rate = 0.0
    time_to_limit: Optional[float] = None
    t = 0.0
    while t < eva_duration_h:
        # SPE flux at current mission time
        if event is not None:
            t_event = t + start_offset_h
            flux_pfu = spe_flux_profile(event, t_event)
            spe_rate_msv = flux_pfu * _DOSE_EQ_MSV_H_PER_PFU
            # Apply shielding (proton energy dependent)
            spe_rate_msv *= shielding_attenuation(shield_g_cm2,
                                                   event.mean_energy_mev)
        else:
            spe_rate_msv = 0.0
        # Aggregate rate
        total_rate_msv = gcr_effective + spe_rate_msv
        peak_rate = max(peak_rate, total_rate_msv * 1000)   # µSv/hr
        # Integrate dose
        total_dose += total_rate_msv * dt_h
        if time_to_limit is None and total_dose >= dose_limit_msv:
            time_to_limit = t
        t += dt_h

    abort = total_dose >= dose_limit_msv
    reason = ""
    if abort:
        reason = f"cumulative dose {total_dose:.1f} mSv ≥ limit {dose_limit_msv:.0f} mSv"

    # GCR / SPE split for reporting
    gcr_dose = gcr_effective * eva_duration_h
    spe_dose = total_dose - gcr_dose

    return EVARadiationResult(
        plan_duration_h=eva_duration_h,
        gcr_dose_msv=gcr_dose,
        spe_dose_msv=max(0.0, spe_dose),
        total_dose_msv=total_dose,
        peak_rate_usv_h=peak_rate,
        shielding_g_cm2=shield_g_cm2,
        abort_recommended=abort,
        abort_reason=reason,
        time_to_limit_h=time_to_limit,
    )


def habitat_safe_haven_dose(event: SolarEvent,
                             shelter_g_cm2: float = _REGOLITH_G_PER_CM2_1M,
                             duration_h: float = 96.0) -> float:
    """Dose accumulated inside a 1-m-regolith shelter for the duration of an SPE.

    This is the "safe haven" calculation — how much does an astronaut
    receive if they shelter for the entire event inside a regolith-buried
    hab?  Target: < 50 mSv for the full event.
    """
    att = shielding_attenuation(shelter_g_cm2, event.mean_energy_mev)
    total = 0.0
    dt_h = 0.5
    t = -event.rise_time_hours
    while t < duration_h:
        flux = spe_flux_profile(event, t)
        total += flux * _DOSE_EQ_MSV_H_PER_PFU * att * dt_h
        t += dt_h
    return total
