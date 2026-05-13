"""Dielectric materials database (§5 of D2 scope).

Values from NASA-HDBK-4002A 2011 Tables 5-2/5-3 and NASCAP-2K materials
database (Davis et al. 2011 NASA/TM-2011-217206). Every row carries a
per-field citation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dielectric:
    """Charging-relevant properties of a dielectric material.

    Attributes:
        name: identifier.
        relative_permittivity: ε_r (dimensionless).
        dark_conductivity_s_m: σ_0 (S/m) at 300 K, no radiation.
        breakdown_field_v_m: E_BD intrinsic dielectric strength (V/m).
        density_kg_m3: ρ (kg/m³).
        se_yield_max: δ_max peak secondary-electron yield (dimensionless).
        se_energy_max_ev: E_max primary energy of the yield peak (eV).
        source: citation string.
    """

    name: str
    relative_permittivity: float
    dark_conductivity_s_m: float
    breakdown_field_v_m: float
    density_kg_m3: float
    se_yield_max: float
    se_energy_max_ev: float
    source: str


# ──────────────────────────────────────────────────────────────────────
#  Kapton-H — reference polyimide for deep-dielectric charging.
# ──────────────────────────────────────────────────────────────────────
KAPTON = Dielectric(
    name="Kapton-H",
    relative_permittivity=3.5,  # NASA-HDBK-4002A Table 5-2
    dark_conductivity_s_m=1.0e-18,  # NASA-HDBK-4002A Table 5-2
    breakdown_field_v_m=2.5e8,  # NASA-HDBK-4002A Table 5-3 (Kapton-H @ RT)
    density_kg_m3=1420.0,  # NASA-HDBK-4002A Table 5-2; DuPont datasheet
    se_yield_max=2.1,  # NASCAP-2K DB (Davis 2011 NASA/TM-2011-217206)
    se_energy_max_ev=150.0,  # NASCAP-2K DB (Davis 2011)
    source=(
        "NASA-HDBK-4002A (2011) Tables 5-2/5-3; "
        "Davis et al. 2011 NASA/TM-2011-217206 NASCAP-2K materials DB"
    ),
)


# ──────────────────────────────────────────────────────────────────────
#  PTFE / Teflon
# ──────────────────────────────────────────────────────────────────────
TEFLON = Dielectric(
    name="Teflon-FEP",
    relative_permittivity=2.1,  # NASA-HDBK-4002A Table 5-2
    dark_conductivity_s_m=1.0e-18,  # NASA-HDBK-4002A Table 5-2
    breakdown_field_v_m=1.8e8,  # NASA-HDBK-4002A Table 5-3
    density_kg_m3=2150.0,  # NASA-HDBK-4002A Table 5-2
    se_yield_max=3.0,  # NASCAP-2K DB (Davis 2011)
    se_energy_max_ev=300.0,  # NASCAP-2K DB (Davis 2011)
    source="NASA-HDBK-4002A (2011) Tables 5-2/5-3; NASCAP-2K DB",
)


# ──────────────────────────────────────────────────────────────────────
#  High-density polyethylene — a reference baseline for ESD handbooks.
# ──────────────────────────────────────────────────────────────────────
POLYETHYLENE = Dielectric(
    name="HDPE",
    relative_permittivity=2.3,  # NASA-HDBK-4002A Table 5-2
    dark_conductivity_s_m=1.0e-17,  # NASA-HDBK-4002A Table 5-2
    breakdown_field_v_m=2.2e8,  # NASA-HDBK-4002A Table 5-3
    density_kg_m3=950.0,  # NASA-HDBK-4002A Table 5-2
    se_yield_max=2.4,  # NASCAP-2K DB (Davis 2011)
    se_energy_max_ev=250.0,  # NASCAP-2K DB (Davis 2011)
    source="NASA-HDBK-4002A (2011) Tables 5-2/5-3; NASCAP-2K DB",
)


DIELECTRIC_TABLE: dict[str, Dielectric] = {
    "Kapton-H": KAPTON,
    "Teflon-FEP": TEFLON,
    "HDPE": POLYETHYLENE,
}


def get_dielectric(name: str) -> Dielectric:
    """Look up a dielectric by name."""
    try:
        return DIELECTRIC_TABLE[name]
    except KeyError as e:
        raise KeyError(
            f"Unknown dielectric {name!r}. Known: {sorted(DIELECTRIC_TABLE.keys())}"
        ) from e
