"""MELiSSA compartments C-I through C-IV-B.

Each compartment is parameterised from published MELiSSA pilot-plant
performance data. Steady-state mass-balance only — no transient
microbial-population dynamics, no nutrient micronutrient balance,
no atmospheric trace contaminants. See ``__init__.py`` for the full
list of "what this module does NOT do".

The compartment model is **flow-based**: each one accepts an input
flux per day and produces an output flux per day, with cited
efficiency / yield coefficients.
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Compartment I: Liquefying ──────────────────────────────────


# C-I uses Thermoanaerobacterium thermosaccharolyticum at 55 °C in
# strict anaerobic conditions. Liquefies fecal + food waste into
# volatile fatty acids (VFAs — acetate, butyrate, propionate).
#
# Lasseur 2010 Table 2: ~70-75 % of input organic matter is
# liquefied to VFAs; the remaining ~25-30 % stays as recalcitrant
# bio-solids. Hendrickx 2006 §3.1 concurs.
DEFAULT_C1_LIQUEFACTION_FRACTION: float = 0.72   # Lasseur 2010 Table 2

# Yield: per kg of organic input dry, ~0.5 kg of VFAs produced
# (the rest is CO2 + cell biomass + recalcitrants).
DEFAULT_C1_VFA_YIELD: float = 0.50               # Hendrickx 2006 §3.1


@dataclass(frozen=True)
class CompartmentI:
    """Liquefying compartment — anaerobic thermophilic fermentation."""

    liquefaction_fraction: float = DEFAULT_C1_LIQUEFACTION_FRACTION
    vfa_yield_per_kg_input: float = DEFAULT_C1_VFA_YIELD
    operating_temperature_c: float = 55.0           # Hendrickx 2006

    def vfa_output_kg_day(self, organic_input_dry_kg_day: float) -> float:
        """Mass of VFAs produced per kg of dry organic input."""
        return (
            organic_input_dry_kg_day
            * self.liquefaction_fraction
            * self.vfa_yield_per_kg_input
        )

    def residual_solids_kg_day(self, organic_input_dry_kg_day: float) -> float:
        """Recalcitrant bio-solids that bypass liquefaction."""
        return (
            organic_input_dry_kg_day * (1.0 - self.liquefaction_fraction)
        )


# ── Compartment II: Photoheterotrophic (Rhodospirillum rubrum) ──


# C-II consumes VFAs from C-I in light, producing NH4 (mineralised
# nitrogen), CO2, and bacterial biomass. Godia 2002 §3.2 + Hendrickx
# 2006 §3.2.
#
# Per kg of VFA input: ~0.18 kg N as NH4 produced; ~0.6 kg CO2 produced
# (carbon mineralised); the remaining ~0.22 kg is R. rubrum cell mass.
DEFAULT_C2_NH4_YIELD: float = 0.18              # Godia 2002 §3.2
DEFAULT_C2_CO2_YIELD: float = 0.60              # Godia 2002 §3.2
DEFAULT_C2_BIOMASS_YIELD: float = 0.22          # Hendrickx 2006 §3.2

DEFAULT_C2_LIGHT_PPFD_UMOL_M2_S: float = 100.0  # photosynthetic photon flux
DEFAULT_C2_REACTOR_VOLUME_L: float = 8.0        # MELiSSA pilot reactor


@dataclass(frozen=True)
class CompartmentII:
    """Photoheterotrophic compartment — Rhodospirillum rubrum."""

    nh4_yield_per_kg_vfa: float = DEFAULT_C2_NH4_YIELD
    co2_yield_per_kg_vfa: float = DEFAULT_C2_CO2_YIELD
    biomass_yield_per_kg_vfa: float = DEFAULT_C2_BIOMASS_YIELD
    light_ppfd_umol_m2_s: float = DEFAULT_C2_LIGHT_PPFD_UMOL_M2_S
    reactor_volume_l: float = DEFAULT_C2_REACTOR_VOLUME_L
    operating_temperature_c: float = 30.0           # Godia 2002

    def nh4_output_kg_day(self, vfa_input_kg_day: float) -> float:
        return vfa_input_kg_day * self.nh4_yield_per_kg_vfa

    def co2_output_kg_day(self, vfa_input_kg_day: float) -> float:
        return vfa_input_kg_day * self.co2_yield_per_kg_vfa

    def edible_biomass_kg_day(self, vfa_input_kg_day: float) -> float:
        # R. rubrum biomass IS edible (single-cell protein) but dose-
        # limited per FDA / EFSA guidance to ~10-20 % of dietary
        # protein because of nucleic-acid load.
        return vfa_input_kg_day * self.biomass_yield_per_kg_vfa


# ── Compartment III: Nitrification ─────────────────────────────


# C-III oxidises NH4 → NO3 via Nitrosomonas (NH4 → NO2) and
# Nitrobacter (NO2 → NO3). Lasseur 2010 §3 reports steady-state
# conversion efficiency of 0.95 (95 % of NH4-N reaches NO3-N).
DEFAULT_C3_CONVERSION_EFFICIENCY: float = 0.95   # Lasseur 2010 §3


@dataclass(frozen=True)
class CompartmentIII:
    """Nitrification compartment — Nitrosomonas + Nitrobacter."""

    conversion_efficiency: float = DEFAULT_C3_CONVERSION_EFFICIENCY
    operating_temperature_c: float = 28.0           # MELiSSA pilot
    reactor_volume_l: float = 5.0

    def nitrate_output_kg_day(self, nh4_input_kg_day: float) -> float:
        # N is conserved; mass of NO3 ion is 62 g/mol vs NH4 18 g/mol.
        # Per kg NH4-N → 4.43 kg NO3-N at 100 %; per kg NH4 ion → 3.44
        # kg NO3 ion at 100 % (this returns mass-as-nitrogen).
        # We track N mass (not ionic mass) for simplicity.
        return nh4_input_kg_day * self.conversion_efficiency

    def nh4_residual_kg_day(self, nh4_input_kg_day: float) -> float:
        return nh4_input_kg_day * (1.0 - self.conversion_efficiency)


# ── Compartment IV-A: Higher plants ────────────────────────────


# Higher-plant production with NO3 + CO2 + light → O2 + edible biomass.
# MELiSSA pilot uses lettuce, beet, wheat in hydroponic NFT trays.
#
# Wheeler 2017 'Crop production for advanced life support systems' Table 1:
#   Lettuce: 30 g dry biomass / m²·day at 600 PPFD and 18 h photoperiod
#   Wheat:   34 g dry biomass / m²·day
#   Soybean: 22 g dry biomass / m²·day
# O2 production scales with photosynthesis: ~50 g O2 / m²·day
# CO2 uptake: ~70 g CO2 / m²·day
# Transpiration: ~3.5 kg H2O / m²·day (mostly evapotranspiration,
#   condensable and recoverable as potable water).
DEFAULT_C4A_BIOMASS_G_M2_DAY: float = 30.0       # lettuce avg, Wheeler 2017
DEFAULT_C4A_O2_G_M2_DAY: float = 50.0            # at canopy steady state
DEFAULT_C4A_CO2_G_M2_DAY: float = 70.0           # CO2 uptake
DEFAULT_C4A_TRANSPIRATION_KG_M2_DAY: float = 3.5  # Wheeler 2017
DEFAULT_C4A_NO3_G_M2_DAY: float = 1.5            # N uptake at this productivity


@dataclass(frozen=True)
class CompartmentIVA:
    """Higher-plant photoautotrophic compartment.

    Sized by ``area_m2`` (planting bed area). Real MELiSSA pilot has
    ~5 m² for ~1-person partial closure.
    """

    area_m2: float
    biomass_g_m2_day: float = DEFAULT_C4A_BIOMASS_G_M2_DAY
    o2_g_m2_day: float = DEFAULT_C4A_O2_G_M2_DAY
    co2_uptake_g_m2_day: float = DEFAULT_C4A_CO2_G_M2_DAY
    transpiration_kg_m2_day: float = DEFAULT_C4A_TRANSPIRATION_KG_M2_DAY
    no3_uptake_g_m2_day: float = DEFAULT_C4A_NO3_G_M2_DAY

    def __post_init__(self) -> None:
        if self.area_m2 < 0:
            raise ValueError(
                f"area_m2 must be >= 0, got {self.area_m2}"
            )

    @property
    def edible_biomass_kg_day(self) -> float:
        return self.area_m2 * self.biomass_g_m2_day / 1000.0

    @property
    def o2_output_kg_day(self) -> float:
        return self.area_m2 * self.o2_g_m2_day / 1000.0

    @property
    def co2_uptake_kg_day(self) -> float:
        return self.area_m2 * self.co2_uptake_g_m2_day / 1000.0

    @property
    def potable_water_recovered_kg_day(self) -> float:
        # Transpiration condenses on chamber heat exchangers; assume
        # 95 % capture per Wheeler 2017 (the rest stays in plant tissue
        # or is lost to substrate).
        return self.area_m2 * self.transpiration_kg_m2_day * 0.95

    @property
    def no3_uptake_kg_day(self) -> float:
        return self.area_m2 * self.no3_uptake_g_m2_day / 1000.0


# ── Compartment IV-B: Spirulina (Arthrospira platensis) ────────


# Spirulina is grown in shallow open or photobioreactor cultures.
# At MELiSSA scale (1-3 person), production of ~2-5 g dry biomass /
# L·day at 200-400 PPFD; converting to per-area equivalent ~10 g/m²·day
# of dry biomass, ~25 g O2/m²·day, ~35 g CO2 uptake/m²·day.
# Cornet 1992 + Cogne 2003 (MELiSSA C-IV-B characterisation).
DEFAULT_C4B_BIOMASS_G_M2_DAY: float = 10.0       # Cornet 1992
DEFAULT_C4B_O2_G_M2_DAY: float = 25.0            # Cogne 2003
DEFAULT_C4B_CO2_G_M2_DAY: float = 35.0
DEFAULT_C4B_NO3_G_M2_DAY: float = 0.6


@dataclass(frozen=True)
class CompartmentIVB:
    """Spirulina photoautotrophic compartment.

    Smaller volumetric footprint than higher plants per unit O2,
    but produces algae rather than diversified food. MELiSSA roadmap
    treats C-IV-A + C-IV-B as complementary, not mutually exclusive.
    """

    area_m2: float
    biomass_g_m2_day: float = DEFAULT_C4B_BIOMASS_G_M2_DAY
    o2_g_m2_day: float = DEFAULT_C4B_O2_G_M2_DAY
    co2_uptake_g_m2_day: float = DEFAULT_C4B_CO2_G_M2_DAY
    no3_uptake_g_m2_day: float = DEFAULT_C4B_NO3_G_M2_DAY

    def __post_init__(self) -> None:
        if self.area_m2 < 0:
            raise ValueError(
                f"area_m2 must be >= 0, got {self.area_m2}"
            )

    @property
    def edible_biomass_kg_day(self) -> float:
        return self.area_m2 * self.biomass_g_m2_day / 1000.0

    @property
    def o2_output_kg_day(self) -> float:
        return self.area_m2 * self.o2_g_m2_day / 1000.0

    @property
    def co2_uptake_kg_day(self) -> float:
        return self.area_m2 * self.co2_uptake_g_m2_day / 1000.0

    @property
    def no3_uptake_kg_day(self) -> float:
        return self.area_m2 * self.no3_uptake_g_m2_day / 1000.0
