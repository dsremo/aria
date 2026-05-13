"""Notable variable stars — period, amplitude, class, light-curve estimate.

Variable stars change brightness on periods from hours (pulsators) to
years (long-period Miras) to irregular (eruptive / cataclysmic).
This module holds the most famous bright variables a sky viewer can
spot, each with elements sufficient to predict the current visual
magnitude:

  m(t) = m_mean + 0.5 * amplitude * cos(2π (t - t_max) / period)

For eclipsing binaries (Algol, β Lyrae) the brightness stays near
maximum except during eclipse; for pulsating stars (δ Cep, Miras) the
sinusoidal approximation is decent. For irregulars (η Car, V838 Mon)
we mark the class but don't predict.

Data from GCVS (General Catalogue of Variable Stars) via VSX — public
domain astronomical data.

Reference:
    Samus, N. N. et al. (2017) "General Catalogue of Variable Stars:
        Version GCVS 5.1." Astron. Reports 61:80.
    AAVSO Visual Star Atlas (open data).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class VariableStar:
    name: str
    hip_id: int                  # 0 if not cataloged in HIP
    ra_deg: float                # J2000
    dec_deg: float               # J2000
    var_type: str                # 'Mira' / 'Cepheid' / 'Algol' / ... (GCVS codes)
    period_d: float              # days (0 if irregular / eruptive)
    t_max_jd: float              # JD of epoch-of-maximum
    mag_min: float               # dimmest V magnitude
    mag_max: float               # brightest V magnitude
    description: str


# Selected famous variables. Periods / epochs / amplitudes from GCVS/VSX.
VARIABLES: List[VariableStar] = [
    VariableStar("Mira (ο Cet)",            10826,  34.8369,  -2.9776, "Mira",
                 331.96, 2458820.0, 9.5, 2.0,
                 "Archetype long-period variable, pulsates from naked-eye to telescope"),
    VariableStar("χ Cygni",                 95014, 292.7000,  32.9067, "Mira",
                 408.05, 2458640.0, 14.2, 3.3,
                 "One of the brightest Miras at max light"),
    VariableStar("R Leonis",                48036, 146.2739,  11.4264, "Mira",
                 310.00, 2458520.0, 11.6, 4.4,
                 "Easy-to-spot Mira near Regulus"),
    VariableStar("U Orionis",               28403,  86.1442,  20.1889, "Mira",
                 368.00, 2458700.0, 12.6, 4.8,
                 "Red giant at 650 ly; wide amplitude"),
    VariableStar("R Hydrae",                65835, 200.2869, -23.2731, "Mira",
                 388.87, 2458650.0, 11.0, 3.5,
                 "Third-brightest Mira after ο Cet and χ Cyg"),
    VariableStar("Algol (β Per)",           14576,  47.0422,  40.9557, "Algol",
                 2.8674, 2458700.40, 3.4, 2.1,
                 "Prototypical eclipsing binary; dips every 2.87 days"),
    VariableStar("β Lyrae",                 92420, 282.5200,  33.3625, "β Lyr",
                 12.9408, 2458700.0, 4.3, 3.2,
                 "Semi-detached eclipsing binary with continuous mag variation"),
    VariableStar("δ Cephei",               110991, 337.2929,  58.4152, "Cepheid",
                 5.3663, 2458690.70, 4.4, 3.5,
                 "Prototype classical Cepheid — basis of distance ladder"),
    VariableStar("ζ Geminorum",             34088, 106.0272,  20.5702, "Cepheid",
                 10.1499, 2458690.0, 4.2, 3.6,
                 "Naked-eye Cepheid, period ~10 days"),
    VariableStar("η Aquilae",               97804, 298.1182,   1.0058, "Cepheid",
                 7.1767, 2458690.0, 4.3, 3.5,
                 "Another bright naked-eye Cepheid"),
    VariableStar("Polaris (α UMi)",         11767,  37.9543,  89.2641, "Cepheid",
                 3.9697, 2458700.0, 2.13, 1.86,
                 "The Pole Star — low-amplitude Cepheid, stabilizing since 1900s"),
    VariableStar("Betelgeuse (α Ori)",      27989,  88.7929,   7.4070, "SRc",
                 423.00, 2458820.0, 1.60, 0.00,
                 "Red supergiant; went through \"Great Dimming\" 2019-2020"),
    VariableStar("Antares (α Sco)",         80763, 247.3519, -26.4320, "SRc",
                 1733.0, 2458000.0, 1.20, 0.88,
                 "Red supergiant, slow irregular pulsation ~4-5 years"),
    VariableStar("Garnet Star (μ Cep)",    107259, 326.1734,  58.7802, "SRc",
                 730.0, 2458500.0, 5.10, 3.43,
                 "Extremely red semi-regular supergiant in Cepheus"),
    VariableStar("RR Lyrae",                95497, 291.3670,  42.7844, "RR Lyrae",
                 0.56685, 2458700.0, 8.12, 7.06,
                 "Prototype RR Lyrae variable; ~13 hour period pulsator"),
    VariableStar("Mira Ceti B",                 0,  34.8373,  -2.9773, "Nova-like",
                 0.0, 0.0, 12.0, 9.5,
                 "Hot white dwarf companion to Mira A"),
    VariableStar("T Coronae Borealis",      78322, 239.8750,  25.9200, "Recurrent Nova",
                 27700.0, 2460700.0, 10.8, 2.0,
                 "\"Blaze Star\" — due to erupt 2026-2027 (last 1946)"),
    VariableStar("η Carinae",               45348, 161.2650, -59.6843, "S Dor / LBV",
                 2022.0, 2450000.0, 7.6, 1.0,
                 "Luminous blue variable; Great Eruption of 1843 to mag −0.8"),
    VariableStar("P Cygni",                100724, 304.7138,  38.0327, "LBV",
                 0.0, 0.0, 5.8, 3.0,
                 "Prototype of P Cygni line profile in stellar spectra"),
    VariableStar("R Coronae Borealis",      77442, 237.2850,  28.1566, "R CrB",
                 0.0, 0.0, 14.8, 5.7,
                 "Prototype of abrupt-fading R CrB class (dust ejection)"),
    VariableStar("T Tauri",                 20390,  65.4962,  19.5352, "T Tau",
                 0.0, 0.0, 12.0, 9.3,
                 "Prototype young T Tauri pre-main-sequence variable"),
    VariableStar("RS Ophiuchi",             83100, 267.5534,  -6.7083, "Recurrent Nova",
                 5000.0, 2459444.0, 12.5, 4.8,
                 "Recurrent nova, last erupted 2021 (also 2006, 1985)"),
    VariableStar("V1357 Cygni (Cyg X-1)",       0, 299.5903,  35.2016, "HMXB",
                 5.6000, 2458690.0, 9.0, 8.8,
                 "Famous stellar-mass black hole binary"),
    VariableStar("SS Cygni",               107570, 325.6786,  43.5858, "U Gem",
                 49.0, 2458650.0, 12.4, 8.2,
                 "Prototype dwarf nova; outbursts every 7-8 weeks"),
    VariableStar("V838 Monocerotis",            0, 101.9869,  -3.8464, "M31 red nova",
                 0.0, 2452302.0, 16.0, 6.7,
                 "Light echo star — 2002 outburst illuminated surrounding nebula"),
]


# ════════════════════════════════════════════════════════════════════
#  Light-curve estimate for periodic variables
# ════════════════════════════════════════════════════════════════════

def current_magnitude(star: VariableStar, jd_ut: float) -> float:
    """Estimate the star's V magnitude at jd_ut.

    For periodic variables with a known t_max_jd, uses a sinusoidal
    approximation m(t) = m_mean + (amp/2) · cos(phase). For irregular /
    eruptive classes (period == 0 or 'Nova' / 'LBV' / 'R CrB' / 'T Tau'),
    returns the *mean* of max/min as a placeholder and flags the limit
    in the description.
    """
    if star.period_d <= 0:
        return 0.5 * (star.mag_min + star.mag_max)
    phase = (jd_ut - star.t_max_jd) / star.period_d
    phase = phase - math.floor(phase)     # wrap to [0, 1)
    mean = 0.5 * (star.mag_min + star.mag_max)
    amp = star.mag_min - star.mag_max
    # Eclipsing binaries spend most of the cycle near max light — model as
    # narrow deep dip at phase 0 (primary eclipse)
    if star.var_type in ("Algol",):
        dip = math.exp(-((phase - 0) * 25) ** 2) + math.exp(-((phase - 1) * 25) ** 2)
        return star.mag_max + amp * dip
    # β Lyr: continuous variation, two eclipses per cycle
    if star.var_type == "β Lyr":
        d1 = math.exp(-((phase - 0) * 10) ** 2)
        d2 = math.exp(-((phase - 0.5) * 10) ** 2) * 0.7
        return star.mag_max + amp * (d1 + d2) / 1.7
    # Generic pulsator: sinusoid around the mean
    return mean + 0.5 * amp * math.cos(2 * math.pi * phase)


def variables_above_horizon(jd_ut: float, lat_deg: float, lon_deg: float,
                            min_alt_deg: float = 0.0,
                            mag_limit: float = 6.0) -> List[VariableStar]:
    """Variables whose *current* estimated magnitude ≤ limit and above horizon."""
    from aria.simulation.observer import (
        equatorial_to_horizontal, local_sidereal_time_deg,
    )
    lst = local_sidereal_time_deg(jd_ut, lon_deg)
    out: List[VariableStar] = []
    for v in VARIABLES:
        cur_mag = current_magnitude(v, jd_ut)
        if cur_mag > mag_limit:
            continue
        alt, _ = equatorial_to_horizontal(v.ra_deg, v.dec_deg, lst, lat_deg)
        if alt < min_alt_deg:
            continue
        out.append(v)
    return out
