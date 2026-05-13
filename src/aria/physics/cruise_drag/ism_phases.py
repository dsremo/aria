"""Interstellar-medium phase table.

Ferrière 2001 *Rev Mod Phys* 73 1031 identifies five canonical
phases of the ISM. ARIA tracks the three that matter at cruise
scales: the Local Bubble (the tenuous hot plasma around the Sun),
the warm neutral medium (WNM, filling most of the galactic disk),
and the cold neutral medium (CNM, in denser diffuse clouds). The
Local Interstellar Cloud (LIC) parameters come from Redfield &
Linsky 2008 *ApJ* 673 283.

Units:
  - number_density_m3: hydrogen nuclei per m³.
  - temperature_k: kinetic temperature (K).
  - mean_particle_mass_kg: mass-weighted mean particle mass,
    including He (1.4 · m_H for neutral gas, 0.61 · m_H for
    fully-ionized H+He).
"""

from __future__ import annotations

from dataclasses import dataclass

# CODATA 2018 / SI 2019.
_M_H_KG: float = 1.6735575e-27  # neutral H atom
_MU_NEUTRAL: float = 1.4  # H + 10 % He by number
_MU_IONIZED: float = 0.61  # fully ionized H + 10 % He


@dataclass(frozen=True)
class ISMPhase:
    """One ISM phase with cruise-drag-relevant parameters.

    Attributes:
        name: identifier.
        number_density_m3: hydrogen nuclei per m³.
        temperature_k: kinetic T (K).
        mean_particle_mass_kg: μ · m_H averaged over composition.
        source: citation.
    """

    name: str
    number_density_m3: float
    temperature_k: float
    mean_particle_mass_kg: float
    source: str

    @property
    def mass_density_kg_m3(self) -> float:
        """ρ = n · μ · m_H                                       [kg/m³]."""
        return self.number_density_m3 * self.mean_particle_mass_kg


# ──────────────────────────────────────────────────────────────────────
#  Local Interstellar Cloud — partially ionized warm cloud the Sun
#  is currently traversing (Redfield & Linsky 2008 ApJ 673 283).
# ──────────────────────────────────────────────────────────────────────
LOCAL_INTERSTELLAR_CLOUD: ISMPhase = ISMPhase(
    name="Local Interstellar Cloud (LIC)",
    number_density_m3=2.2e5,  # Redfield & Linsky 2008 (n_H ≈ 0.22 /cm³)
    temperature_k=7500.0,  # Redfield & Linsky 2008
    mean_particle_mass_kg=_MU_NEUTRAL * _M_H_KG,
    source="Redfield & Linsky 2008 ApJ 673 283",
)


# ──────────────────────────────────────────────────────────────────────
#  Local Bubble — hot low-density plasma surrounding the LIC.
# ──────────────────────────────────────────────────────────────────────
LOCAL_BUBBLE: ISMPhase = ISMPhase(
    name="Local Bubble",
    number_density_m3=5.0e3,  # Ferrière 2001 Table 1 (n ≈ 0.005/cm³)
    temperature_k=1.0e6,  # Ferrière 2001 Table 1
    mean_particle_mass_kg=_MU_IONIZED * _M_H_KG,
    source="Ferrière 2001 Rev Mod Phys 73 1031 Table 1",
)


# ──────────────────────────────────────────────────────────────────────
#  Warm Neutral Medium — volume-filling ISM phase.
# ──────────────────────────────────────────────────────────────────────
WARM_NEUTRAL_MEDIUM: ISMPhase = ISMPhase(
    name="Warm Neutral Medium (WNM)",
    number_density_m3=4.0e5,  # Ferrière 2001 (n ≈ 0.4 /cm³)
    temperature_k=6.0e3,  # Ferrière 2001
    mean_particle_mass_kg=_MU_NEUTRAL * _M_H_KG,
    source="Ferrière 2001 Rev Mod Phys 73 1031",
)


# ──────────────────────────────────────────────────────────────────────
#  Cold Neutral Medium — dense diffuse clouds along the galactic
#  plane, hit during deep spiral-arm transits.
# ──────────────────────────────────────────────────────────────────────
COLD_NEUTRAL_MEDIUM: ISMPhase = ISMPhase(
    name="Cold Neutral Medium (CNM)",
    number_density_m3=3.0e7,  # Ferrière 2001 (n ≈ 30 /cm³)
    temperature_k=80.0,  # Ferrière 2001
    mean_particle_mass_kg=_MU_NEUTRAL * _M_H_KG,
    source="Ferrière 2001 Rev Mod Phys 73 1031",
)


_ISM_TABLE: dict[str, ISMPhase] = {
    "LIC": LOCAL_INTERSTELLAR_CLOUD,
    "LocalBubble": LOCAL_BUBBLE,
    "WNM": WARM_NEUTRAL_MEDIUM,
    "CNM": COLD_NEUTRAL_MEDIUM,
}


def get_ism_phase(name: str) -> ISMPhase:
    """Look up an ISM phase by short name (`LIC`, `WNM`, `CNM`, `LocalBubble`)."""
    try:
        return _ISM_TABLE[name]
    except KeyError as e:
        raise KeyError(
            f"Unknown ISM phase {name!r}. Known: {sorted(_ISM_TABLE.keys())}"
        ) from e
