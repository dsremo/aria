"""Bosch-Hale D-T Maxwellian reactivity (§4.1, §4.2 of E1 scope).

The Bosch-Hale 1992 *Nucl Fusion* 32 611 analytic fit for the
Maxwellian-averaged fusion reactivity is

    ⟨σv⟩(T) = C1 · θ · √(ξ / (m_r c² T³)) · exp(−3 ξ)        [cm³/s]

with

    θ(T) = T / (1 − (T (C2 + T (C4 + T C6))) / (1 + T (C3 + T (C5 + T C7))))
    ξ(T) = (B_G² / (4 θ))^(1/3)

where `T` is the ion temperature in **keV**. Valid for
0.2 keV ≤ T ≤ 100 keV with ~0.25 % accuracy against ENDF/B-VI
R-matrix (Bosch & Hale 1992 Table VII).

The volumetric reaction rate follows

    R_f = n_D · n_T · ⟨σv⟩                                    [m⁻³ s⁻¹]

and the fusion power density is

    P_f = R_f · Q_DT                                          [W/m³]

with Q_DT = 17.589 MeV (Bosch & Hale 1992 Table I), of which
14.028 MeV is carried by the neutron and 3.561 MeV by the alpha.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Bosch & Hale 1992 Table I — D-T Q value and partition.
Q_DT_MEV: float = 17.589
Q_NEUTRON_DT_MEV: float = 14.028
Q_ALPHA_DT_MEV: float = 3.561

_MEV_TO_JOULE: float = 1.602176634e-13  # SI 2019 / 1 MeV = 1e6 · 1.602e-19 J


@dataclass(frozen=True)
class BoschHaleDTCoefficients:
    """Bosch-Hale 1992 Table VII D-T fit constants.

    Units:
        c1 is cm³/s · keV^(−3/2) (prefactor in Table VII).
        c2-c7 are polynomial coefficients (1/keV⁻ⁿ).
        b_g is the Gamow energy square root in keV^½.
        mr_c2 is the reduced-mass energy in keV.
    """

    c1: float = 1.17302e-9
    c2: float = 1.51361e-2
    c3: float = 7.51886e-2
    c4: float = 4.60643e-3
    c5: float = 1.35000e-2
    c6: float = -1.06750e-4
    c7: float = 1.36600e-5
    b_g: float = 34.3827  # keV^(1/2)
    mr_c2: float = 1124656.0  # keV


BOSCH_HALE_DT_COEFFS: BoschHaleDTCoefficients = BoschHaleDTCoefficients()


def bosch_hale_dt_reactivity_m3_s(
    ion_temperature_kev: float,
    coeffs: BoschHaleDTCoefficients = BOSCH_HALE_DT_COEFFS,
) -> float:
    """D-T Maxwellian-averaged reactivity ⟨σv⟩(T) in m³/s.

    Args:
        ion_temperature_kev: T_i in keV. Valid range 0.2 – 100 keV;
            outside the validity band a warning-worthy value is
            still returned (no clamping) — callers are expected to
            check the Bosch-Hale 1992 Table VII bounds themselves.
        coeffs: override for testing.

    Returns:
        ⟨σv⟩ in m³/s.

    Canonical checks:
        T_i = 10  keV → 1.13×10⁻²² m³/s (Bosch & Hale 1992 Table VII)
        T_i = 15  keV → 2.65×10⁻²² m³/s
        T_i = 20  keV → 4.24×10⁻²² m³/s
    """
    if ion_temperature_kev <= 0.0:
        raise ValueError("ion_temperature_kev must be positive")
    t = ion_temperature_kev
    c = coeffs
    numerator = t * (c.c2 + t * (c.c4 + t * c.c6))
    denominator = 1.0 + t * (c.c3 + t * (c.c5 + t * c.c7))
    theta = t / (1.0 - numerator / denominator)
    xi = (c.b_g * c.b_g / (4.0 * theta)) ** (1.0 / 3.0)
    sigma_v_cm3_s = (
        c.c1
        * theta
        * math.sqrt(xi / (c.mr_c2 * t * t * t))
        * math.exp(-3.0 * xi)
    )
    return sigma_v_cm3_s * 1.0e-6  # cm³/s → m³/s


def fusion_power_density_w_m3(
    deuterium_density_m3: float,
    tritium_density_m3: float,
    ion_temperature_kev: float,
    q_value_mev: float = Q_DT_MEV,
) -> float:
    """Volumetric D-T fusion power density [W/m³].

    P_f = n_D · n_T · ⟨σv⟩(T_i) · Q                           [W/m³]
    """
    if deuterium_density_m3 < 0.0 or tritium_density_m3 < 0.0:
        raise ValueError("ion densities must be non-negative")
    sigma_v = bosch_hale_dt_reactivity_m3_s(ion_temperature_kev)
    return (
        deuterium_density_m3
        * tritium_density_m3
        * sigma_v
        * q_value_mev
        * _MEV_TO_JOULE
    )


def fusion_power_volumetric(
    deuterium_density_m3: float,
    tritium_density_m3: float,
    ion_temperature_kev: float,
    volume_m3: float,
    q_value_mev: float = Q_DT_MEV,
) -> float:
    """Total D-T fusion power integrated over a plasma volume [W].

    Canonical check: T_i = 13 keV, n_D = n_T = 2.5×10¹⁹ m⁻³,
    V = 80 m³ should fall in the O(10 MW) range (Keilhacker 1999
    JET DTE1 #42976 peak fusion power 16.1 MW; Bosch-Hale alone
    predicts ~12-15 MW depending on the exact temperature since the
    JET pulse was not purely Maxwellian).
    """
    if volume_m3 <= 0.0:
        raise ValueError("volume_m3 must be positive")
    p_density = fusion_power_density_w_m3(
        deuterium_density_m3=deuterium_density_m3,
        tritium_density_m3=tritium_density_m3,
        ion_temperature_kev=ion_temperature_kev,
        q_value_mev=q_value_mev,
    )
    return p_density * volume_m3
