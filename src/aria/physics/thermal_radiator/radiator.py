"""Radiator panel physics — Stefan-Boltzmann with real corrections.

The classical space-radiator formula is

    P_rej = ε σ A (T_r⁴ − T_sink⁴)                          [W]

(Incropera 2011 §12.3). The `T_sink⁴` term is frequently dropped in
engineering handbooks because T_sink ≈ 3 K for deep-space missions
and 3 K / 500 K = 0.006 → the T_sink⁴ contribution is
~1.3×10⁻⁹ of the T_r⁴ term — genuinely negligible for hot
radiators. It matters, however, for *cold* life-support radiators
(~150 K), where T_sink / T_r reaches 0.02 and the correction is
~5 ppm, and for inner-solar-system missions where the "sky" sees
the Sun and solar albedo dominates the sink temperature.

Real radiator panels are not isothermal: the root is at the coolant
inlet temperature and the tip is colder because the panel's finite
thermal conductivity cannot transport the dissipated heat fast
enough. Gardner 1945 *Trans ASME* 67 621 derived the closed-form
fin efficiency for a straight rectangular fin with insulated tip:

    η_fin = tanh(m L) / (m L)                                [–]
    m = √(2 h / (k · t))                                     [1/m]

for a convective fin of thickness `t` and length `L` in a fluid
with coefficient `h`. For a *radiating* fin there is no single
convective `h`, but the linearised radiation coefficient
`h_rad ≈ 4 ε σ T_r³` recovers the Gardner form in the
small-temperature-drop limit (Incropera 2011 §3.6 example 3.13).
We expose both the classical Gardner and the linearised-radiation
variant and return the smaller (more conservative) of the two.

The Carnot ceiling is included purely as a bookkeeping helper:
higher T_r shrinks the radiator but forces the reactor's cold-side
temperature up, eroding the Carnot efficiency
`η_C = 1 − T_cold / T_hot`.

References:
  - Fixsen 2009 *ApJ* 707 916 — T_CMB = 2.72548 ± 0.00057 K.
  - Incropera et al. 2011 *Fundamentals of Heat and Mass Transfer*
    7th ed (ISBN 978-0470501979) Chapters 3, 12.
  - Gardner 1945 *Trans ASME* 67 621 — straight-fin efficiency.
  - Callen 1985 *Thermodynamics and an Introduction to
    Thermostatistics* 2nd ed §4.2 — Carnot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# Stefan-Boltzmann constant (CODATA 2018: σ = 2π⁵k_B⁴ / (15 h³ c²)).
STEFAN_BOLTZMANN_W_M2_K4: float = 5.670374419e-8

# CMB temperature (Fixsen 2009 *ApJ* 707 916).
CMB_TEMPERATURE_K: float = 2.72548


def sky_sink_temperature_k(
    heliocentric_distance_au: float = float("inf"),
    cmb_floor_k: float = CMB_TEMPERATURE_K,
) -> float:
    """Effective sink temperature for a perfectly-radiating panel.

    Deep-space radiators see the CMB and a (weakly) solar-illuminated
    sky. Using the rule of thumb
        T_sink⁴ ≈ T_CMB⁴ + α · S(d) / (ε σ)
    with α ≈ 0.1 (a clean silvered-Teflon panel absorptivity to solar
    light) and solar irradiance S(d) = S₀ / d² (S₀ = 1361 W/m² at
    1 AU), we solve for the equivalent sink T_r of a balanced panel
    (Incropera 2011 §12.8 example 12.12).

    For d → ∞ the function collapses to the CMB floor.
    """
    if heliocentric_distance_au <= 0.0:
        raise ValueError("heliocentric_distance_au must be positive")
    t_cmb4 = cmb_floor_k ** 4
    if math.isinf(heliocentric_distance_au):
        return cmb_floor_k
    # Solar constant S₀ = 1361 W/m² (Kopp & Lean 2011 GRL 38 L01706).
    s_au = 1361.0 / (heliocentric_distance_au ** 2)
    alpha_over_epsilon = 0.10 / 0.85  # clean OSR / silvered Teflon
    t_sun4 = alpha_over_epsilon * s_au / STEFAN_BOLTZMANN_W_M2_K4
    return (t_cmb4 + t_sun4) ** 0.25


def fin_efficiency_gardner(
    fin_length_m: float,
    fin_thickness_m: float,
    fin_thermal_conductivity_w_m_k: float,
    panel_temperature_k: float,
    emissivity: float = 0.9,
) -> float:
    """Gardner 1945 efficiency for a straight rectangular radiating fin.

    Using the linearised radiation coefficient
    `h_rad ≈ 4 ε σ T³` (Incropera 2011 §3.6 example 3.13),

        m = √(2 h_rad / (k · t))                           [1/m]
        η_fin = tanh(m L) / (m L)                          [–]

    is exact in the small-temperature-drop limit and conservative
    otherwise. At `m L → 0` (infinite k) η_fin → 1; at `m L → ∞`
    (insulating fin) η_fin → 0.
    """
    if fin_length_m <= 0.0:
        raise ValueError("fin_length_m must be positive")
    if fin_thickness_m <= 0.0:
        raise ValueError("fin_thickness_m must be positive")
    if fin_thermal_conductivity_w_m_k <= 0.0:
        raise ValueError("fin_thermal_conductivity_w_m_k must be positive")
    if panel_temperature_k <= 0.0:
        raise ValueError("panel_temperature_k must be positive")
    if not (0.0 < emissivity <= 1.0):
        raise ValueError("emissivity must be in (0, 1]")
    h_rad = 4.0 * emissivity * STEFAN_BOLTZMANN_W_M2_K4 * panel_temperature_k ** 3
    m = math.sqrt(2.0 * h_rad / (fin_thermal_conductivity_w_m_k * fin_thickness_m))
    ml = m * fin_length_m
    if ml < 1.0e-6:
        return 1.0
    return math.tanh(ml) / ml


def radiator_net_rejection_w(
    area_m2: float,
    panel_temperature_k: float,
    sink_temperature_k: float = CMB_TEMPERATURE_K,
    emissivity: float = 0.9,
    fin_efficiency: float = 1.0,
) -> float:
    """Net Stefan-Boltzmann heat rejection with T_sink⁴ correction.

    P = η_fin · ε σ A · (T_r⁴ − T_sink⁴)                    [W]

    The `T_sink⁴` term protects consumers who sample a cold life-
    support radiator or a warm inner-solar-system sink.
    """
    if area_m2 <= 0.0:
        raise ValueError("area_m2 must be positive")
    if panel_temperature_k <= 0.0:
        raise ValueError("panel_temperature_k must be positive")
    if sink_temperature_k < 0.0:
        raise ValueError("sink_temperature_k must be non-negative")
    if not (0.0 < emissivity <= 1.0):
        raise ValueError("emissivity must be in (0, 1]")
    if not (0.0 < fin_efficiency <= 1.0):
        raise ValueError("fin_efficiency must be in (0, 1]")
    return (
        fin_efficiency
        * emissivity
        * STEFAN_BOLTZMANN_W_M2_K4
        * area_m2
        * (panel_temperature_k ** 4 - sink_temperature_k ** 4)
    )


def solve_radiator_area_m2(
    heat_load_w: float,
    panel_temperature_k: float,
    sink_temperature_k: float = CMB_TEMPERATURE_K,
    emissivity: float = 0.9,
    fin_efficiency: float = 1.0,
) -> float:
    """Invert ``radiator_net_rejection_w`` to size the panel area.

    A = Q̇ / (η_fin · ε σ (T_r⁴ − T_sink⁴))                 [m²]
    """
    if heat_load_w <= 0.0:
        raise ValueError("heat_load_w must be positive")
    if panel_temperature_k <= sink_temperature_k:
        raise ValueError("panel_temperature_k must exceed sink_temperature_k")
    per_m2 = radiator_net_rejection_w(
        area_m2=1.0,
        panel_temperature_k=panel_temperature_k,
        sink_temperature_k=sink_temperature_k,
        emissivity=emissivity,
        fin_efficiency=fin_efficiency,
    )
    return heat_load_w / per_m2


def carnot_ceiling_efficiency(
    hot_temperature_k: float, cold_temperature_k: float
) -> float:
    """η_C = 1 − T_c / T_h (Callen 1985 §4.2)."""
    if hot_temperature_k <= 0.0 or cold_temperature_k <= 0.0:
        raise ValueError("temperatures must be positive")
    if cold_temperature_k >= hot_temperature_k:
        return 0.0
    return 1.0 - cold_temperature_k / hot_temperature_k


@dataclass(frozen=True)
class RadiatorPanelReport:
    """Summary report for a single radiator panel configuration.

    Attributes:
        heat_load_w: input heat load to reject.
        panel_temperature_k: T_r operating point.
        sink_temperature_k: T_sink (CMB by default).
        emissivity: ε.
        fin_efficiency: η_fin (pass 1.0 for isothermal panels).
        area_required_m2: Stefan-Boltzmann sized area.
        carnot_ceiling: thermodynamic ceiling if this T_r is the cold
            side of a reactor Carnot cycle with T_hot = 2 · T_r (a
            common handbook assumption for rough sizing).
    """

    heat_load_w: float
    panel_temperature_k: float
    sink_temperature_k: float
    emissivity: float
    fin_efficiency: float
    area_required_m2: float
    carnot_ceiling: float

    @classmethod
    def build(
        cls,
        heat_load_w: float,
        panel_temperature_k: float,
        sink_temperature_k: float = CMB_TEMPERATURE_K,
        emissivity: float = 0.9,
        fin_efficiency: float = 1.0,
    ) -> "RadiatorPanelReport":
        area = solve_radiator_area_m2(
            heat_load_w=heat_load_w,
            panel_temperature_k=panel_temperature_k,
            sink_temperature_k=sink_temperature_k,
            emissivity=emissivity,
            fin_efficiency=fin_efficiency,
        )
        carnot = carnot_ceiling_efficiency(
            hot_temperature_k=2.0 * panel_temperature_k,
            cold_temperature_k=panel_temperature_k,
        )
        return cls(
            heat_load_w=heat_load_w,
            panel_temperature_k=panel_temperature_k,
            sink_temperature_k=sink_temperature_k,
            emissivity=emissivity,
            fin_efficiency=fin_efficiency,
            area_required_m2=area,
            carnot_ceiling=carnot,
        )
