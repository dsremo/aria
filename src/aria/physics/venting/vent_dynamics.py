"""Vent dynamics — choked flow + isentropic exit velocity + thrust/torque.

The same equations cover three operational cases:
  1. **Commanded vent** (tank dump, pressurant safe-mode dump) — tank
     pressure is order-MPa, ambient is vacuum, so flow is always
     choked and exit is sonic at the throat.
  2. **Hull breach** (Soyuz 11) — cabin pressure ~100 kPa, ambient is
     vacuum, also choked.
  3. **Sublimator** — water flashed to vapour at low pressure; thrust
     contribution is small but non-zero (Apollo CSM water dump
     plumes were measurable at mm/s/orbit).

Reference equations
-------------------

Choked mass flow through an orifice (Anderson 2006 §3.5,
NASA-CR-1330 §III, Sutton-Biblarz §3.3):

    m_dot = C_d · A · P_0 / √(R · T_0) · √γ · ((γ+1)/2)^(-(γ+1)/(2(γ-1)))

where R is the *specific* gas constant (J/kg·K).

Isentropic exit velocity for a converging-diverging nozzle expanded
to vacuum back-pressure (Sutton-Biblarz §3.3.2 Eq 3-15b):

    v_e = √( 2γ/(γ-1) · R · T_0 · (1 − (P_e/P_0)^((γ-1)/γ)) )

For a *converging-only* orifice (most relief valves + hull holes),
exit is sonic, so v_e = √(γ R T_0 / (1 + (γ-1)/2)) = a_throat.  We
expose both forms so the caller picks the right one.

Thrust on the spacecraft is the reaction:

    F⃗ = − m_dot · v_e · n̂_exit

Torque on the spacecraft about the centre of mass:

    τ⃗ = r⃗_vent × F⃗

where r⃗_vent is the vent location in body coordinates measured from
the CoM.  This is the missing piece that left ARIA blind to
Cassini-class navigation drift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np

# Universal gas constant.  CODATA 2018 (Tiesinga et al. 2021,
# Rev. Mod. Phys. 93, 025010), J/(mol·K).
R_UNIVERSAL = 8.314_462_618


# Common gas properties used in spacecraft venting cases.  Each entry
# tagged with a peer-reviewed source so future editors can audit.
GAS_PROPERTIES = {
    # γ (heat-capacity ratio), M_w (kg/mol).
    "air":      (1.40, 28.97e-3),  # COESA-76 Std Atm Table I
    "n2":       (1.40, 28.013e-3),  # NIST WebBook
    "o2":       (1.395, 31.999e-3),  # NIST
    "h2":       (1.405, 2.016e-3),  # NIST
    "he":       (1.667, 4.003e-3),  # NIST monatomic
    "ar":       (1.667, 39.948e-3),  # NIST monatomic
    "h2o_vap":  (1.330, 18.015e-3),  # Water vapour, NIST
    "ch4":      (1.304, 16.04e-3),   # NIST
    "co2":      (1.289, 44.01e-3),   # NIST
    "nto":      (1.30, 92.011e-3),   # NTO ~N2O4, MIL-PRF-26539E
    "mmh":      (1.30, 46.07e-3),    # MIL-PRF-27404, Sutton-Biblarz Tab 7-2
    "xe":       (1.667, 131.293e-3),  # Hall-thruster propellant, NIST
}


# ── Dataclasses ──────────────────────────────────────────────────


@dataclass(frozen=True)
class GasState:
    """Stagnation state of the gas upstream of the vent."""
    pressure_pa: float
    temperature_k: float
    gas: str = "air"      # key into GAS_PROPERTIES

    @property
    def gamma(self) -> float:
        return GAS_PROPERTIES[self.gas][0]

    @property
    def molar_mass_kg_mol(self) -> float:
        return GAS_PROPERTIES[self.gas][1]

    @property
    def specific_R(self) -> float:
        return R_UNIVERSAL / self.molar_mass_kg_mol


@dataclass(frozen=True)
class VentGeometry:
    """Vent location + orientation in body coordinates.

    ``area_m2``      throat area (single hole; total for an array of
                     holes is the sum if they all see the same
                     stagnation state).
    ``location_m``   3-vector from spacecraft CoM to vent throat (m).
    ``normal``       3-vector unit normal pointing OUT of the vent
                     (i.e. direction the gas leaves).
    ``cd``           discharge coefficient.  Sharp-edged orifice ≈ 0.6,
                     converging-only nozzle ≈ 0.95, well-rounded
                     converging-diverging ≈ 0.98 (Sutton-Biblarz §3.3.4).
    """
    area_m2: float
    location_m: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    cd: float = 0.95

    def normal_unit(self) -> np.ndarray:
        n = np.asarray(self.normal, dtype=float)
        nn = float(np.linalg.norm(n))
        if nn == 0.0:
            raise ValueError("vent normal must be non-zero")
        return n / nn

    def location(self) -> np.ndarray:
        return np.asarray(self.location_m, dtype=float)


@dataclass(frozen=True)
class VentResult:
    """Output of a single vent-step calculation."""
    mass_flow_kg_s: float
    exit_velocity_m_s: float
    thrust_n: Tuple[float, float, float]
    torque_n_m: Tuple[float, float, float]
    is_choked: bool
    notes: str = ""

    @property
    def thrust_magnitude_n(self) -> float:
        return float(np.linalg.norm(self.thrust_n))

    @property
    def torque_magnitude_n_m(self) -> float:
        return float(np.linalg.norm(self.torque_n))


# ── Core equations ──────────────────────────────────────────────


def _critical_pressure_ratio(gamma: float) -> float:
    """P*/P_0 — at this pressure ratio flow becomes choked.

    Anderson 2006 Eq 3.20.
    """
    return (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))


def is_choked(p_upstream_pa: float, p_back_pa: float, gamma: float) -> bool:
    """True if back-pressure is below the critical pressure."""
    if p_upstream_pa <= 0.0:
        return False
    ratio = max(p_back_pa, 0.0) / p_upstream_pa
    return ratio <= _critical_pressure_ratio(gamma)


def choked_mass_flow(
    gas: GasState,
    geometry: VentGeometry,
) -> float:
    """Mass flow through a choked converging orifice.

    Sutton-Biblarz §3.3.4 Eq 3-24, Anderson 2006 Eq 4.8.
    Returns kg/s.
    """
    if gas.pressure_pa <= 0.0 or gas.temperature_k <= 0.0:
        return 0.0
    g = gas.gamma
    R_s = gas.specific_R
    coeff = math.sqrt(g) * (
        (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))
    )
    return (
        geometry.cd * geometry.area_m2 * gas.pressure_pa
        / math.sqrt(R_s * gas.temperature_k)
        * coeff
    )


def isentropic_exit_velocity(
    gas: GasState,
    p_exit_pa: float = 0.0,
    converging_only: bool = True,
) -> float:
    """Exit velocity (m/s).

    For a *converging-only* orifice (relief valve, hull breach,
    most simple vent ports) flow is sonic at the throat; v_e equals
    the throat speed of sound.  For a *converging-diverging* nozzle
    expanded to ``p_exit_pa`` (vacuum = 0 Pa for spacecraft venting),
    the isentropic Bernoulli result applies.
    """
    g = gas.gamma
    R_s = gas.specific_R
    T0 = gas.temperature_k
    if T0 <= 0.0 or gas.pressure_pa <= 0.0:
        return 0.0
    if converging_only:
        # Throat conditions: T_throat = 2*T0/(γ+1); a = √(γ R T_throat).
        T_throat = 2.0 * T0 / (g + 1.0)
        return math.sqrt(g * R_s * T_throat)
    # Isentropic CD-nozzle, expanded to p_exit_pa.
    pr = max(p_exit_pa, 0.0) / gas.pressure_pa
    if pr >= 1.0:
        return 0.0
    return math.sqrt(
        2.0 * g / (g - 1.0) * R_s * T0 * (1.0 - pr ** ((g - 1.0) / g))
    )


def vent_thrust_and_torque(
    gas: GasState,
    geometry: VentGeometry,
    p_back_pa: float = 0.0,
    converging_only: bool = True,
) -> VentResult:
    """Full vent → thrust + torque coupling.

    Returns a :class:`VentResult` whose thrust and torque are body-frame
    3-vectors, ready for the GNC integrator to add into Σ F and Σ τ.
    """
    if gas.pressure_pa <= max(p_back_pa, 0.0):
        # No flow — back pressure stalls the vent.
        return VentResult(
            mass_flow_kg_s=0.0, exit_velocity_m_s=0.0,
            thrust_n=(0.0, 0.0, 0.0), torque_n_m=(0.0, 0.0, 0.0),
            is_choked=False, notes="no flow: p_back ≥ p_upstream",
        )
    choked = is_choked(gas.pressure_pa, p_back_pa, gas.gamma)
    if choked:
        m_dot = choked_mass_flow(gas, geometry)
    else:
        # Subsonic-orifice mass flow (Sutton-Biblarz Eq 3-25).
        g = gas.gamma
        R_s = gas.specific_R
        pr = p_back_pa / gas.pressure_pa
        if pr >= 1.0 or gas.temperature_k <= 0.0:
            m_dot = 0.0
        else:
            inner = (
                pr ** (2.0 / g)
                - pr ** ((g + 1.0) / g)
            )
            inner = max(inner, 0.0)
            m_dot = (
                geometry.cd * geometry.area_m2 * gas.pressure_pa
                * math.sqrt(
                    2.0 * g / ((g - 1.0) * R_s * gas.temperature_k)
                    * inner
                )
            )
    v_e = isentropic_exit_velocity(
        gas, p_exit_pa=p_back_pa, converging_only=converging_only,
    )
    n = geometry.normal_unit()
    thrust = -m_dot * v_e * n   # reaction is opposite gas-exit direction
    r = geometry.location()
    torque = np.cross(r, thrust)
    return VentResult(
        mass_flow_kg_s=float(m_dot),
        exit_velocity_m_s=float(v_e),
        thrust_n=tuple(float(x) for x in thrust),
        torque_n_m=tuple(float(x) for x in torque),
        is_choked=bool(choked),
        notes=(
            f"gas={gas.gas} γ={gas.gamma:.3f} "
            f"mode={'choked' if choked else 'subsonic'} "
            f"v_e={v_e:.1f} m/s"
        ),
    )
