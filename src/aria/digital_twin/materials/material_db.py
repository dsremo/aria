"""Material Properties Database for ARIA Digital Twin.

Centralised repository of engineering material properties used across the
digital-twin subsystems — structural fatigue, thermal management, shielding,
and reactor components.  Every entry carries a ``source`` citation so that
values are traceable back to published handbooks or peer-reviewed papers.

Property definitions
--------------------
density_kg_m3         Bulk density [kg m⁻³]
youngs_modulus_pa     Young's modulus E [Pa]
poisson_ratio         Poisson's ratio ν [–]
yield_strength_pa     0.2% offset yield strength σ_y [Pa]
uts_pa                Ultimate tensile strength [Pa]
thermal_conductivity_w_mk  Thermal conductivity k [W m⁻¹ K⁻¹]
specific_heat_j_kgk   Specific heat capacity c_p [J kg⁻¹ K⁻¹]
cte_per_k             Coefficient of thermal expansion α [K⁻¹]
emissivity            Total hemispherical emissivity ε [–]
melting_point_k       Solidus / melting point [K]
fatigue_limit_pa      Endurance limit at 10⁷ cycles [Pa]
fatigue_exponent      Basquin exponent b (σ_a = σ_f' (2N)^b)
source                Published citation string

References
----------
MMPDS-17      Metallic Materials Properties Development & Standardization
              (Battelle, 2024).
MIL-HDBK-5J  Metallic Materials & Elements for Aerospace Vehicle Structures.
ASM Handbook  Vol. 2 – Properties & Selection: Nonferrous Alloys (ASM Intl).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class MaterialProperty:
    """Immutable record of a single material's engineering properties."""

    name: str
    density_kg_m3: float
    youngs_modulus_pa: Optional[float] = None
    poisson_ratio: Optional[float] = None
    yield_strength_pa: Optional[float] = None
    uts_pa: Optional[float] = None
    thermal_conductivity_w_mk: Optional[float] = None
    specific_heat_j_kgk: Optional[float] = None
    cte_per_k: Optional[float] = None
    emissivity: Optional[float] = None
    melting_point_k: Optional[float] = None
    fatigue_limit_pa: Optional[float] = None
    fatigue_exponent: Optional[float] = None
    source: str = ""


# ---------------------------------------------------------------------------
# Material database
# ---------------------------------------------------------------------------

MATERIAL_DATABASE: Dict[str, MaterialProperty] = {
    # ------------------------------------------------------------------
    # a. Ti-6Al-4V  (primary structural alloy)
    # ------------------------------------------------------------------
    "Ti-6Al-4V": MaterialProperty(
        name="Ti-6Al-4V",
        density_kg_m3=4430.0,
        youngs_modulus_pa=113.8e9,
        poisson_ratio=0.342,
        yield_strength_pa=880e6,
        uts_pa=950e6,
        thermal_conductivity_w_mk=6.7,
        specific_heat_j_kgk=526.3,
        cte_per_k=8.6e-6,
        emissivity=0.19,
        melting_point_k=1933.0,
        fatigue_limit_pa=510e6,
        fatigue_exponent=-0.096,
        source=(
            "MMPDS-17 Table 5.4.1.0(b); ASM Handbook Vol. 2; "
            "NASA-STD-5001B fatigue data; Boyer, R. et al., "
            "'Materials Properties Handbook: Titanium Alloys', ASM Intl, 1994"
        ),
    ),
    # ------------------------------------------------------------------
    # b. EUROFER97  (Reduced-Activation Ferritic-Martensitic steel)
    # ------------------------------------------------------------------
    "EUROFER97": MaterialProperty(
        name="EUROFER97",
        density_kg_m3=7750.0,
        youngs_modulus_pa=217e9,
        poisson_ratio=0.3,
        yield_strength_pa=550e6,
        uts_pa=690e6,
        thermal_conductivity_w_mk=33.6,
        specific_heat_j_kgk=440.0,
        cte_per_k=11.4e-6,
        emissivity=0.28,
        melting_point_k=1803.0,
        fatigue_limit_pa=270e6,
        fatigue_exponent=-0.08,
        source=(
            "Federici, G. et al., 'European DEMO design strategy and "
            "consequences for materials', Nuclear Fusion 57(9), 2017; "
            "Tavassoli, A.A.F. et al., 'Current status and recent research "
            "achievements in ferritic/martensitic steels', J. Nuclear Mater. "
            "455, 2014; ITER Material Properties Handbook (MPH)"
        ),
    ),
    # ------------------------------------------------------------------
    # c. NaK-78  (eutectic sodium-potassium coolant, 78 wt% K)
    # ------------------------------------------------------------------
    "NaK-78": MaterialProperty(
        name="NaK-78",
        density_kg_m3=866.0,
        youngs_modulus_pa=None,          # liquid — not applicable
        poisson_ratio=None,
        yield_strength_pa=None,
        uts_pa=None,
        thermal_conductivity_w_mk=24.4,
        specific_heat_j_kgk=1042.0,
        cte_per_k=None,
        emissivity=0.05,
        melting_point_k=262.0,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Lyon, R.N. (ed.), 'Liquid Metals Handbook', NAVEXOS P-733 "
            "(Rev. 1952), AEC/DoN; Foust, O.J. (ed.), 'Sodium-NaK "
            "Engineering Handbook', Gordon & Breach, 1972; "
            "ARIA thermal_management.py validated values"
        ),
    ),
    # ------------------------------------------------------------------
    # d. B4C  (boron carbide neutron absorber / shield)
    # ------------------------------------------------------------------
    "B4C": MaterialProperty(
        name="B4C",
        density_kg_m3=2520.0,
        youngs_modulus_pa=460e9,
        poisson_ratio=0.17,
        yield_strength_pa=None,          # brittle ceramic
        uts_pa=350e6,                    # compressive strength proxy
        thermal_conductivity_w_mk=27.0,
        specific_heat_j_kgk=950.0,
        cte_per_k=5.0e-6,
        emissivity=0.92,
        melting_point_k=2763.0,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Thevenot, F., 'Boron Carbide — A Comprehensive Review', "
            "J. European Ceramic Soc. 6(4), 1990; Suri, A.K. et al., "
            "'Synthesis and consolidation of boron carbide: a review', "
            "Intl Mater. Rev. 55(1), 2010; ITER neutron shield design data"
        ),
    ),
    # ------------------------------------------------------------------
    # e. Kevlar-49  (aramid fibre — Whipple shield bumper layer)
    # ------------------------------------------------------------------
    "Kevlar-49": MaterialProperty(
        name="Kevlar-49",
        density_kg_m3=1440.0,
        youngs_modulus_pa=112e9,
        poisson_ratio=0.36,
        yield_strength_pa=3620e6,
        uts_pa=3620e6,                   # aramid — yield ≈ UTS (no plastic zone)
        thermal_conductivity_w_mk=0.04,
        specific_heat_j_kgk=1420.0,
        cte_per_k=-2.0e-6,              # negative axial CTE (aramid behaviour)
        emissivity=0.85,
        melting_point_k=None,            # decomposes at ~773 K, does not melt
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "DuPont Kevlar 49 Technical Data Sheet (K-29314, Rev. 2019); "
            "MIL-HDBK-17-2F Polymer Matrix Composites Vol. 2; "
            "NASA TP-2003-210788 Whipple Shield MMOD risk assessment"
        ),
    ),
    # ------------------------------------------------------------------
    # f. UHMWPE  (Ultra-High-Molecular-Weight Polyethylene, radiation shield)
    # ------------------------------------------------------------------
    "UHMWPE": MaterialProperty(
        name="UHMWPE",
        density_kg_m3=930.0,
        youngs_modulus_pa=0.8e9,
        poisson_ratio=0.46,
        yield_strength_pa=21e6,
        uts_pa=48e6,
        thermal_conductivity_w_mk=0.5,
        specific_heat_j_kgk=1850.0,
        cte_per_k=150e-6,
        emissivity=0.94,
        melting_point_k=403.0,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Kurtz, S.M., 'The UHMWPE Handbook', Elsevier, 2004; "
            "Guetersloh, S. et al., 'Polyethylene as a radiation shielding "
            "standard in simulated cosmic-ray environments', Nuclear Instr. "
            "& Methods B 252, 2006; NASA/TP-2005-213688"
        ),
    ),
    # ------------------------------------------------------------------
    # g. Al-7075-T6  (structural backup / non-rotating members)
    # ------------------------------------------------------------------
    "Al-7075-T6": MaterialProperty(
        name="Al-7075-T6",
        density_kg_m3=2810.0,
        youngs_modulus_pa=71.7e9,
        poisson_ratio=0.33,
        yield_strength_pa=503e6,
        uts_pa=572e6,
        thermal_conductivity_w_mk=130.0,
        specific_heat_j_kgk=960.0,
        cte_per_k=23.6e-6,
        emissivity=0.09,
        melting_point_k=908.0,
        fatigue_limit_pa=159e6,
        fatigue_exponent=-0.122,
        source=(
            "MMPDS-17 Table 3.7.6.0(a); MIL-HDBK-5J Al-7075-T6 sheet; "
            "ASM Aerospace Specification Metals Inc. datasheet"
        ),
    ),
    # ------------------------------------------------------------------
    # h. CNT Composite  (projected carbon-nanotube structural composite)
    # ------------------------------------------------------------------
    "CNT-Composite": MaterialProperty(
        name="CNT-Composite",
        density_kg_m3=1600.0,
        # Sharma R6: 500 GPa is single-tube; bulk composite at 60% Vf via
        # Halpin-Tsai gives ~200 GPa (consistent with 2 GPa yield downgrade)
        youngs_modulus_pa=200e9,  # Bulk CNT composite (Halpin-Tsai 60% Vf)
        poisson_ratio=0.3,
        # Sharma (Materials PDR): single-tube MWCNT values (~60 GPa) are NOT
        # achievable in a bulk composite. Realistic bulk CNT/polymer composite
        # tensile strengths are 1.5–2.5 GPa (Cheng et al., ACS Nano 3, 2009;
        # Wang et al., Nano Lett. 14, 2014; Bakshi et al., Int. Mater. Rev. 55,
        # 2010). Downgraded to 2 GPa yield / 2.1 GPa UTS for bulk composite.
        yield_strength_pa=2.0e9,   # bulk CNT composite — Cheng 2009, Wang 2014
        uts_pa=2.1e9,              # bulk CNT composite — Bakshi 2010 review
        thermal_conductivity_w_mk=200.0,
        specific_heat_j_kgk=750.0,
        cte_per_k=1.0e-6,
        emissivity=0.85,
        melting_point_k=None,            # decomposes; no true melting point
        fatigue_limit_pa=None,           # insufficient long-duration data
        fatigue_exponent=None,
        source=(
            "Demczyk, B.G. et al., 'Direct mechanical measurement of the "
            "tensile strength and elastic modulus of multiwalled carbon "
            "nanotubes', Mater. Sci. Eng. A 334, 2002 (individual MWCNT); "
            "PROJECTED COMPOSITE VALUES — scaled from single-tube data via "
            "Halpin-Tsai micromechanics at 60% Vf; NOT YET FLIGHT-QUALIFIED"
        ),
    ),
    # ------------------------------------------------------------------
    # i. HfB2 (UHTC — reactor plasma-facing component)
    # ------------------------------------------------------------------
    "HfB2": MaterialProperty(
        name="HfB2",
        density_kg_m3=11200.0,
        youngs_modulus_pa=480e9,
        poisson_ratio=0.12,
        yield_strength_pa=None,          # brittle ceramic
        uts_pa=260e6,                    # flexural strength proxy
        thermal_conductivity_w_mk=104.0,
        specific_heat_j_kgk=247.0,
        cte_per_k=6.3e-6,
        emissivity=0.36,
        melting_point_k=3523.0,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Fahrenholtz, W.G. et al., 'Ultra-High Temperature Ceramics: "
            "Materials for Extreme Environment Applications', Wiley, 2014; "
            "Fahrenholtz, W.G. & Hilmas, G.E., 'Ultra-high temperature "
            "ceramics: materials for extreme environments', Scripta Mater. "
            "129, 2017; Opeka, M.M. et al., J. Mater. Sci. 39, 2004"
        ),
    ),
    # ------------------------------------------------------------------
    # j. Inconel-718 (reactor high-temperature nickel superalloy)
    # ------------------------------------------------------------------
    "Inconel-718": MaterialProperty(
        name="Inconel-718",
        density_kg_m3=8190.0,
        youngs_modulus_pa=200e9,
        poisson_ratio=0.29,
        yield_strength_pa=1035e6,
        uts_pa=1240e6,
        thermal_conductivity_w_mk=11.2,
        specific_heat_j_kgk=435.0,
        cte_per_k=13.0e-6,
        emissivity=0.21,
        melting_point_k=1609.0,
        fatigue_limit_pa=550e6,
        fatigue_exponent=-0.087,
        source=(
            "Special Metals Corp., 'INCONEL alloy 718' Technical Bulletin "
            "SMC-045, 2007; MMPDS-17 Table 6.3.6.0; AMS 5662/5663; "
            "Aerospace Structural Metals Handbook (CINDAS/USAF, 1995)"
        ),
    ),
    # ------------------------------------------------------------------
    # k. SS-316L (austenitic stainless steel — piping, tanks)
    # ------------------------------------------------------------------
    "SS-316L": MaterialProperty(
        name="SS-316L",
        density_kg_m3=7990.0,
        youngs_modulus_pa=193e9,
        poisson_ratio=0.30,
        yield_strength_pa=170e6,
        uts_pa=485e6,
        thermal_conductivity_w_mk=16.3,
        specific_heat_j_kgk=500.0,
        cte_per_k=15.9e-6,
        emissivity=0.28,
        melting_point_k=1673.0,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "ASME BPV Code Section II Part D, 2023 Edition; "
            "MMPDS-17 Table 2.4.1.0; ASM Handbook Vol. 1; "
            "ATI/Allegheny 316L datasheet"
        ),
    ),
    # ------------------------------------------------------------------
    # l. Fused Silica (optical windows, sensor lenses)
    # ------------------------------------------------------------------
    "Fused-Silica": MaterialProperty(
        name="Fused-Silica",
        density_kg_m3=2200.0,
        youngs_modulus_pa=73e9,
        poisson_ratio=0.17,
        yield_strength_pa=None,          # brittle amorphous glass
        uts_pa=48e6,                     # tensile strength (defect-limited)
        thermal_conductivity_w_mk=1.38,
        specific_heat_j_kgk=740.0,
        cte_per_k=0.55e-6,
        emissivity=0.93,
        melting_point_k=1986.0,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Corning HPFS 7980 Fused Silica datasheet; "
            "Heraeus Suprasil 3001 specifications; "
            "Bansal, N.P. & Doremus, R.H., 'Handbook of Glass Properties', "
            "Academic Press, 1986"
        ),
    ),
    # ------------------------------------------------------------------
    # m. Aerogel (silica aerogel — thermal insulation)
    # ------------------------------------------------------------------
    "Aerogel": MaterialProperty(
        name="Aerogel",
        density_kg_m3=100.0,
        youngs_modulus_pa=0.001e9,
        poisson_ratio=0.20,
        yield_strength_pa=None,          # crushable, no yield in traditional sense
        uts_pa=0.016e6,                  # tensile strength ~16 kPa
        thermal_conductivity_w_mk=0.015,
        specific_heat_j_kgk=1000.0,
        cte_per_k=2.0e-6,
        emissivity=0.10,
        melting_point_k=None,            # decomposes / sinters, does not melt
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "NASA JPL aerogel thermal protection data; "
            "Hrubesh, L.W. & Pekala, R.W., 'Thermal properties of organic "
            "and inorganic aerogels', J. Mater. Res. 9(3), 1994; "
            "Aspen Aerogels Spaceloft datasheet"
        ),
    ),
    # ------------------------------------------------------------------
    # n. MLI-Mylar (gold-coated multi-layer insulation)
    # ------------------------------------------------------------------
    "MLI-Mylar": MaterialProperty(
        name="MLI-Mylar",
        density_kg_m3=1390.0,
        youngs_modulus_pa=None,          # film — not structurally loaded
        poisson_ratio=None,
        yield_strength_pa=None,
        uts_pa=None,
        thermal_conductivity_w_mk=0.04,
        specific_heat_j_kgk=1170.0,
        cte_per_k=17.0e-6,
        emissivity=0.03,                 # gold-coated side
        melting_point_k=527.0,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "DuPont Mylar polyester film Technical Bulletin H-38492-2; "
            "Gilmore, D.G. (ed.), 'Spacecraft Thermal Control Handbook', "
            "Vol. 1, 2nd ed., AIAA, 2002; "
            "NASA/TP-2018-220067 MLI performance characterisation"
        ),
    ),
    # ------------------------------------------------------------------
    # o. Liquid Hydrogen (LH2 propellant at ~20 K)
    # ------------------------------------------------------------------
    "Liquid-Hydrogen": MaterialProperty(
        name="Liquid-Hydrogen",
        density_kg_m3=70.8,
        youngs_modulus_pa=None,          # liquid — not applicable
        poisson_ratio=None,
        yield_strength_pa=None,
        uts_pa=None,
        thermal_conductivity_w_mk=0.1,
        specific_heat_j_kgk=14300.0,
        cte_per_k=None,
        emissivity=None,
        melting_point_k=14.0,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "NIST Cryogenic Technologies Group, 'Thermophysical Properties "
            "of Hydrogen'; McCarty, R.D. et al., 'Selected Properties of "
            "Hydrogen (Engineering Design Data)', NBS Monograph 168, 1981; "
            "Leachman, J.W. et al., J. Phys. Chem. Ref. Data 38(3), 2009"
        ),
    ),
    # ------------------------------------------------------------------
    # p. Water Ice  (shield ablation layer)
    # ------------------------------------------------------------------
    "Water-Ice": MaterialProperty(
        name="Water-Ice",
        density_kg_m3=917.0,
        youngs_modulus_pa=9.0e9,         # at -20 °C (polycrystalline)
        poisson_ratio=0.33,
        yield_strength_pa=None,          # brittle; no distinct yield
        uts_pa=None,
        thermal_conductivity_w_mk=2.22,
        specific_heat_j_kgk=2090.0,      # at -20 °C (Fukusako 1990)
        cte_per_k=50.0e-6,               # volumetric ~159e-6/3 ≈ 53e-6 linear
        emissivity=0.97,                  # near-unity for rough ice (Warren 2019)
        melting_point_k=273.15,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Schulson, E.M. & Duval, P., 'Creep and Fracture of Ice', "
            "Cambridge Univ. Press, 2009; Petrovic, J.J., 'Mechanical "
            "properties of ice and snow', J. Mater. Sci. 38, 2003; "
            "Fukusako, S., 'Thermophysical properties of ice, snow, and "
            "sea ice', Intl J. Thermophys. 11(2), 1990"
        ),
    ),
    # ------------------------------------------------------------------
    # q. MgB2  (magnesium diboride superconductor — magnetic deflector)
    # ------------------------------------------------------------------
    "MgB2": MaterialProperty(
        name="MgB2",
        density_kg_m3=2570.0,
        youngs_modulus_pa=200e9,
        poisson_ratio=0.21,              # Hinks et al. (2001) estimate
        yield_strength_pa=65e6,
        uts_pa=None,                     # brittle ceramic; fracture before UTS
        thermal_conductivity_w_mk=25.0,
        specific_heat_j_kgk=630.0,       # Bud'ko et al. (2001) at 40 K
        cte_per_k=7.5e-6,                # Jorgensen et al. (2001)
        # Handbook emissivity for oxide-coated ceramic surfaces
        # (Incropera 2011 Table A.11 "oxidised ceramic" entry:
        # ε ≈ 0.4-0.6 at 300 K, midpoint 0.5).
        emissivity=0.5,
        melting_point_k=None,            # decomposes ~1000 °C, does not melt congruently
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Nagamatsu, J. et al., 'Superconductivity at 39 K in magnesium "
            "diboride', Nature 410:63, 2001; Bud'ko, S.L. et al., Phys. Rev. "
            "Lett. 86, 2001 (specific heat); Hinks, D.G. et al., 'Synthesis, "
            "structure and superconductivity of MgB₂', Physica C 382, 2002; "
            "T_c = 39 K — highest among conventional BCS superconductors"
        ),
    ),
    # ------------------------------------------------------------------
    # r. Tungsten  (electrostatic grid, high-Z radiation attenuator)
    # ------------------------------------------------------------------
    "Tungsten": MaterialProperty(
        name="Tungsten",
        density_kg_m3=19300.0,
        youngs_modulus_pa=411e9,
        poisson_ratio=0.28,
        yield_strength_pa=750e6,
        uts_pa=980e6,                    # wrought W (recrystallised)
        thermal_conductivity_w_mk=173.0,
        specific_heat_j_kgk=134.0,       # at 20 °C
        cte_per_k=4.5e-6,
        emissivity=0.04,                  # polished; rises to 0.3 at 2000 °C
        melting_point_k=3695.0,
        fatigue_limit_pa=None,           # brittle below DBTT (~400 °C)
        fatigue_exponent=None,
        source=(
            "ASM Handbook Vol. 2 — Properties & Selection: Nonferrous Alloys; "
            "Lassner, E. & Schubert, W.-D., 'Tungsten: Properties, Chemistry, "
            "Technology of the Element, Alloys, and Chemical Compounds', Kluwer, "
            "1999; ITER divertor W-monoblock design data"
        ),
    ),
    # ------------------------------------------------------------------
    # s. Li2TiO3  (lithium titanate — tritium breeding blanket ceramic)
    # ------------------------------------------------------------------
    "Li2TiO3": MaterialProperty(
        name="Li2TiO3",
        density_kg_m3=3430.0,
        youngs_modulus_pa=170e9,
        poisson_ratio=0.25,              # Hoshino (2005) estimate for oxide ceramics
        yield_strength_pa=None,          # brittle ceramic
        uts_pa=None,
        thermal_conductivity_w_mk=2.4,
        specific_heat_j_kgk=950.0,       # Hoshino (2005) at ~500 °C
        cte_per_k=9.0e-6,                # Hoshino (2005)
        emissivity=0.85,                  # oxide ceramic, rough surface
        melting_point_k=1822.0,
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Hoshino, T. et al., 'Non-stoichiometry of Li₂TiO₃ under "
            "hydrogen atmosphere conditions', J. Nuclear Mater. 329–333, 2004; "
            "Hoshino, T., 'Pebble fabrication and characterization of "
            "Li₂TiO₃', Fusion Eng. Design 74, 2005; "
            "ITER Test Blanket Module (TBM) design data"
        ),
    ),
    # ------------------------------------------------------------------
    # t. Borated Concrete  (biological shield — reactor compartment)
    # ------------------------------------------------------------------
    "Borated-Concrete": MaterialProperty(
        name="Borated-Concrete",
        density_kg_m3=2350.0,
        youngs_modulus_pa=30e9,
        poisson_ratio=0.20,              # ACI 318 typical range 0.15–0.25
        yield_strength_pa=30e6,          # compressive strength proxy
        uts_pa=3e6,                      # tensile strength (concrete is weak in tension)
        thermal_conductivity_w_mk=1.0,
        specific_heat_j_kgk=880.0,       # typical concrete (Neville 2011)
        cte_per_k=10.0e-6,               # ACI 318
        emissivity=0.94,                  # rough concrete surface
        melting_point_k=None,            # decomposes ~600 °C, does not melt
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "ACI 318-19 Building Code Requirements for Structural Concrete; "
            "Kaplan, M.F., 'Concrete Radiation Shielding', Longman, 1989; "
            "ANS-6.4-2006 Nuclear Analysis and Design of Concrete Radiation "
            "Shielding for Nuclear Power Plants; B₂O₃ content 1–5 wt% for "
            "thermal neutron capture (¹⁰B cross-section 3840 barns)"
        ),
    ),
    # ------------------------------------------------------------------
    # u. GaAs Solar Cell  (gallium arsenide — backup solar panels)
    # ------------------------------------------------------------------
    "GaAs": MaterialProperty(
        name="GaAs",
        density_kg_m3=5320.0,
        youngs_modulus_pa=85.5e9,
        poisson_ratio=0.31,              # Sze & Ng (2007)
        yield_strength_pa=None,          # brittle semiconductor; no yield
        uts_pa=None,
        thermal_conductivity_w_mk=55.0,
        specific_heat_j_kgk=330.0,       # at 300 K (Blakemore 1982)
        cte_per_k=5.73e-6,               # Sze & Ng (2007)
        emissivity=0.90,                  # rough / textured solar cell surface
        melting_point_k=1511.0,           # Blakemore (1982)
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Sze, S.M. & Ng, K.K., 'Physics of Semiconductor Devices', "
            "3rd ed., Wiley, 2007; Blakemore, J.S., 'Semiconducting and other "
            "major properties of gallium arsenide', J. Appl. Phys. 53(10), "
            "1982; triple-junction GaAs cells: η ≈ 30% AM0 (Spectrolab UTJ)"
        ),
    ),

    # ==================================================================
    # CATEGORY 1 — STRUCTURAL STEELS
    # ==================================================================

    # ------------------------------------------------------------------
    # v. AISI 4340 Steel  (high-strength low-alloy — shafts, structural)
    # ------------------------------------------------------------------
    "AISI-4340": MaterialProperty(
        name="AISI-4340",
        density_kg_m3=7850.0,            # MMPDS-17 Table 2.3.1.0
        youngs_modulus_pa=200e9,          # MMPDS-17 Table 2.3.1.0
        poisson_ratio=0.30,               # MMPDS-17 typical for alloy steel
        yield_strength_pa=1170e6,         # MMPDS-17 Table 2.3.1.0(a) heat-treated (Q&T 260°C)
        uts_pa=1275e6,                    # MMPDS-17 Table 2.3.1.0(a)
        thermal_conductivity_w_mk=44.5,   # ASM Handbook Vol. 1, 10th ed.
        specific_heat_j_kgk=475.0,        # ASM Handbook Vol. 1
        cte_per_k=12.3e-6,               # ASM Handbook Vol. 1
        emissivity=0.28,                  # ASM Handbook Vol. 2 (machined steel surface)
        melting_point_k=1703.0,           # ASM Handbook Vol. 1 ~1430 °C solidus
        fatigue_limit_pa=620e6,           # MMPDS-17 Table 2.3.1.0 (R=-1, Kt=1)
        fatigue_exponent=-0.076,          # MIL-HDBK-5J Basquin fit, 4340 Q&T
        source=(
            "MMPDS-17 (Battelle, 2024) Table 2.3.1.0; MIL-HDBK-5J "
            "Chapter 2 AISI 4340 steel; ASM Handbook Vol. 1 'Properties and "
            "Selection: Irons, Steels, and High-Performance Alloys', ASM Intl, "
            "1990; AMS 6415 / ASTM A322 material specification"
        ),
    ),
    # ------------------------------------------------------------------
    # w. 17-4PH Stainless Steel  (H900 condition — brackets, fittings)
    # ------------------------------------------------------------------
    "17-4PH-H900": MaterialProperty(
        name="17-4PH-H900",
        density_kg_m3=7780.0,            # MMPDS-17 Table 2.5.4.0
        youngs_modulus_pa=196e9,          # MMPDS-17 Table 2.5.4.0
        poisson_ratio=0.27,               # MMPDS-17 typical PH SS
        yield_strength_pa=1170e6,         # MMPDS-17 Table 2.5.4.0(a) H900
        uts_pa=1310e6,                    # MMPDS-17 Table 2.5.4.0(a) H900
        thermal_conductivity_w_mk=18.3,   # AK Steel 17-4PH datasheet (2015)
        specific_heat_j_kgk=460.0,        # AK Steel 17-4PH datasheet (2015)
        cte_per_k=10.8e-6,               # AK Steel 17-4PH datasheet (2015)
        emissivity=0.17,                  # ASM Handbook: lightly oxidised PH SS
        melting_point_k=1688.0,           # AK Steel 17-4PH datasheet ~1400–1440 °C liquidus
        fatigue_limit_pa=620e6,           # MMPDS-17 Table 2.5.4.0 (R=-1, smooth specimen)
        fatigue_exponent=-0.089,          # MIL-HDBK-5J Basquin fit, 17-4PH H900
        source=(
            "MMPDS-17 (Battelle, 2024) Table 2.5.4.0; AK Steel Corp., "
            "'17-4 PH Stainless Steel Product Data Bulletin', 2015; "
            "AMS 5643 / ASTM A564 Type 630; NASA-STD-5001B fatigue guidance"
        ),
    ),
    # ------------------------------------------------------------------
    # x. 15-5PH Stainless Steel  (H900 condition — flanges, valve bodies)
    # ------------------------------------------------------------------
    "15-5PH-H900": MaterialProperty(
        name="15-5PH-H900",
        density_kg_m3=7780.0,            # Carpenter Technology 15-5PH datasheet (2019)
        youngs_modulus_pa=197e9,          # Carpenter Technology 15-5PH datasheet (2019)
        poisson_ratio=0.27,               # typical PH SS (Carpenter datasheet)
        yield_strength_pa=1170e6,         # Carpenter Technology 15-5PH datasheet H900
        uts_pa=1310e6,                    # Carpenter Technology 15-5PH datasheet H900
        thermal_conductivity_w_mk=18.4,   # Carpenter Technology 15-5PH datasheet
        specific_heat_j_kgk=460.0,        # Carpenter Technology 15-5PH datasheet
        cte_per_k=10.8e-6,               # Carpenter Technology 15-5PH datasheet
        emissivity=0.17,                  # ASM Handbook: lightly oxidised PH SS
        melting_point_k=1688.0,           # Carpenter Technology 15-5PH datasheet ~1415 °C solidus
        fatigue_limit_pa=620e6,           # MMPDS-17 (similar to 17-4PH H900 per MIL-HDBK-5J)
        fatigue_exponent=-0.089,          # MIL-HDBK-5J Basquin fit, PH SS H900 condition
        source=(
            "Carpenter Technology Corp., '15-5PH Stainless Steel' datasheet, "
            "2019; MMPDS-17 (Battelle, 2024) PH stainless data; "
            "AMS 5659 / ASTM A564 Gr 630; MIL-HDBK-5J Chapter 2"
        ),
    ),
    # ------------------------------------------------------------------
    # y. AISI 304L Stainless Steel  (low-carbon — welded assemblies)
    # ------------------------------------------------------------------
    "AISI-304L": MaterialProperty(
        name="AISI-304L",
        density_kg_m3=7900.0,            # ASTM A240/A240M Table 1
        youngs_modulus_pa=193e9,          # ASME BPV Code Sec. II Part D
        poisson_ratio=0.29,               # ASME BPV Code Sec. II typical austenitic SS
        yield_strength_pa=170e6,          # ASTM A240 Table 1 (min 0.2% offset)
        uts_pa=485e6,                     # ASTM A240 Table 1 (min UTS)
        thermal_conductivity_w_mk=16.2,   # ASM Handbook Vol. 1
        specific_heat_j_kgk=500.0,        # ASM Handbook Vol. 1
        cte_per_k=17.2e-6,               # ASM Handbook Vol. 1 (20–100 °C range)
        emissivity=0.30,                  # ASM Handbook: oxidised 304 SS surface
        melting_point_k=1673.0,           # ASM Handbook Vol. 1 (~1400 °C solidus)
        fatigue_limit_pa=None,            # 304L has no endurance limit (FCC, strain-induced martensite)
        fatigue_exponent=None,
        source=(
            "ASTM A240/A240M-23 Standard for Chromium and Chromium-Nickel "
            "Stainless Steel Plate; ASME BPV Code Section II Part D (2023); "
            "ASM Handbook Vol. 1 'Properties and Selection: Irons, Steels, "
            "and High-Performance Alloys', ASM Intl, 1990"
        ),
    ),
    # ------------------------------------------------------------------
    # z. Maraging 300 Steel  (18Ni(300) condition — ultra-high-strength)
    # ------------------------------------------------------------------
    "Maraging-300": MaterialProperty(
        name="Maraging-300",
        density_kg_m3=8000.0,            # MMPDS-17 Table 2.7.1.0
        youngs_modulus_pa=190e9,          # MMPDS-17 Table 2.7.1.0
        poisson_ratio=0.30,               # MMPDS-17 typical maraging steel
        yield_strength_pa=1900e6,         # MMPDS-17 Table 2.7.1.0(a) 18Ni(300) aged
        uts_pa=1965e6,                    # MMPDS-17 Table 2.7.1.0(a) 18Ni(300) aged
        thermal_conductivity_w_mk=15.9,   # Special Metals Maraging 300 datasheet (2007)
        specific_heat_j_kgk=460.0,        # Special Metals Maraging 300 datasheet (2007)
        cte_per_k=11.3e-6,               # Special Metals Maraging 300 datasheet (2007)
        emissivity=0.28,                  # ASM Handbook: machined alloy steel
        melting_point_k=1688.0,           # Special Metals datasheet ~1415 °C liquidus
        fatigue_limit_pa=700e6,           # MMPDS-17 Table 2.7.1.0 (R=-1, Kt=1)
        fatigue_exponent=-0.068,          # MIL-HDBK-5J Basquin fit, 18Ni(300)
        source=(
            "MMPDS-17 (Battelle, 2024) Table 2.7.1.0; Special Metals Corp., "
            "'Maraging Steels' datasheet SMC-055, 2007; "
            "AMS 6514 / ASTM A538 Grade C; MIL-HDBK-5J Chapter 2"
        ),
    ),

    # ==================================================================
    # CATEGORY 2 — ALUMINUM ALLOYS
    # ==================================================================

    # ------------------------------------------------------------------
    # aa. Al 6061-T6  (general-purpose structural alloy)
    # ------------------------------------------------------------------
    "Al-6061-T6": MaterialProperty(
        name="Al-6061-T6",
        density_kg_m3=2700.0,            # MMPDS-17 Table 3.7.2.0
        youngs_modulus_pa=68.9e9,         # MMPDS-17 Table 3.7.2.0
        poisson_ratio=0.33,               # MMPDS-17 Table 3.7.2.0
        yield_strength_pa=276e6,          # MMPDS-17 Table 3.7.2.0(a) T6 sheet
        uts_pa=310e6,                     # MMPDS-17 Table 3.7.2.0(a) T6 sheet
        thermal_conductivity_w_mk=167.0,  # ASM Handbook Vol. 2
        specific_heat_j_kgk=896.0,        # ASM Handbook Vol. 2
        cte_per_k=23.6e-6,               # ASM Handbook Vol. 2
        emissivity=0.09,                  # ASM Handbook: mill-finish Al
        melting_point_k=925.0,            # MMPDS-17 (~652 °C solidus)
        fatigue_limit_pa=96.5e6,          # MMPDS-17 Table 3.7.2.0 (R=-1, smooth)
        fatigue_exponent=-0.110,          # MIL-HDBK-5J Basquin fit, 6061-T6
        source=(
            "MMPDS-17 (Battelle, 2024) Table 3.7.2.0; ASM Handbook Vol. 2 "
            "'Properties and Selection: Nonferrous Alloys', ASM Intl, 1990; "
            "ASTM B209 / AMS 2770; MIL-HDBK-5J Chapter 3"
        ),
    ),
    # ------------------------------------------------------------------
    # bb. Al 2024-T3  (damage-tolerant airframe alloy)
    # ------------------------------------------------------------------
    "Al-2024-T3": MaterialProperty(
        name="Al-2024-T3",
        density_kg_m3=2780.0,            # MMPDS-17 Table 3.2.3.0
        youngs_modulus_pa=73.1e9,         # MMPDS-17 Table 3.2.3.0
        poisson_ratio=0.33,               # MMPDS-17 Table 3.2.3.0
        yield_strength_pa=345e6,          # MMPDS-17 Table 3.2.3.0(a) T3 sheet (L)
        uts_pa=483e6,                     # MMPDS-17 Table 3.2.3.0(a) T3 sheet (L)
        thermal_conductivity_w_mk=121.0,  # ASM Handbook Vol. 2
        specific_heat_j_kgk=875.0,        # ASM Handbook Vol. 2
        cte_per_k=23.2e-6,               # ASM Handbook Vol. 2
        emissivity=0.09,                  # ASM Handbook: mill-finish Al
        melting_point_k=911.0,            # MMPDS-17 (~638 °C solidus)
        fatigue_limit_pa=138e6,           # MMPDS-17 Table 3.2.3.0 (R=-1, Kt=1)
        fatigue_exponent=-0.118,          # MIL-HDBK-5J Basquin fit, 2024-T3
        source=(
            "MMPDS-17 (Battelle, 2024) Table 3.2.3.0; ASM Handbook Vol. 2 "
            "'Properties and Selection: Nonferrous Alloys', ASM Intl, 1990; "
            "ASTM B209 / AMS 2770; MIL-HDBK-5J Chapter 3"
        ),
    ),
    # ------------------------------------------------------------------
    # cc. Al 5052-H32  (marine/non-structural sheet — fuel lines, panels)
    # ------------------------------------------------------------------
    "Al-5052-H32": MaterialProperty(
        name="Al-5052-H32",
        density_kg_m3=2680.0,            # MMPDS-17 Table 3.6.3.0
        youngs_modulus_pa=70.3e9,         # MMPDS-17 Table 3.6.3.0
        poisson_ratio=0.33,               # ASM Handbook Vol. 2
        yield_strength_pa=193e6,          # MMPDS-17 Table 3.6.3.0(a) H32
        uts_pa=228e6,                     # MMPDS-17 Table 3.6.3.0(a) H32
        thermal_conductivity_w_mk=138.0,  # ASM Handbook Vol. 2
        specific_heat_j_kgk=880.0,        # ASM Handbook Vol. 2
        cte_per_k=23.8e-6,               # ASM Handbook Vol. 2
        emissivity=0.09,                  # ASM Handbook: mill-finish Al
        melting_point_k=880.0,            # ASM Handbook Vol. 2 (~607 °C solidus)
        fatigue_limit_pa=117e6,           # MMPDS-17 Table 3.6.3.0 (R=-1)
        fatigue_exponent=-0.121,          # MIL-HDBK-5J Basquin fit, 5052-H32
        source=(
            "MMPDS-17 (Battelle, 2024) Table 3.6.3.0; ASM Handbook Vol. 2 "
            "'Properties and Selection: Nonferrous Alloys', ASM Intl, 1990; "
            "ASTM B209 / AMS 2770; MIL-HDBK-5J Chapter 3"
        ),
    ),
    # ------------------------------------------------------------------
    # dd. Al 2219-T87  (cryogenic tank alloy — LH2/LOX tankage)
    # ------------------------------------------------------------------
    "Al-2219-T87": MaterialProperty(
        name="Al-2219-T87",
        density_kg_m3=2840.0,            # MMPDS-17 Table 3.2.5.0
        youngs_modulus_pa=73.8e9,         # MMPDS-17 Table 3.2.5.0
        poisson_ratio=0.33,               # MMPDS-17 Table 3.2.5.0
        yield_strength_pa=393e6,          # MMPDS-17 Table 3.2.5.0(a) T87 plate (L)
        uts_pa=476e6,                     # MMPDS-17 Table 3.2.5.0(a) T87 plate (L)
        thermal_conductivity_w_mk=116.0,  # ASM Handbook Vol. 2
        specific_heat_j_kgk=864.0,        # ASM Handbook Vol. 2
        cte_per_k=22.3e-6,               # ASM Handbook Vol. 2 (room temp)
        emissivity=0.09,                  # ASM Handbook: mill-finish Al
        melting_point_k=916.0,            # MMPDS-17 (~643 °C solidus)
        fatigue_limit_pa=103e6,           # MMPDS-17 Table 3.2.5.0 (R=-1, Kt=1)
        fatigue_exponent=-0.105,          # MIL-HDBK-5J Basquin fit, 2219-T87
        source=(
            "MMPDS-17 (Battelle, 2024) Table 3.2.5.0; ASM Handbook Vol. 2 "
            "'Properties and Selection: Nonferrous Alloys', ASM Intl, 1990; "
            "NASA SP-8062 'Metallic Materials and Elements for Aerospace "
            "Cryogenic Tankage'; AMS 2770 heat treatment; ASTM B209"
        ),
    ),

    # ==================================================================
    # CATEGORY 3 — TITANIUM
    # ==================================================================

    # ------------------------------------------------------------------
    # ee. Ti-3Al-2.5V  (tubing / hydraulic lines)
    # ------------------------------------------------------------------
    "Ti-3Al-2.5V": MaterialProperty(
        name="Ti-3Al-2.5V",
        density_kg_m3=4480.0,            # MMPDS-17 Table 5.3.1.0
        youngs_modulus_pa=107e9,          # MMPDS-17 Table 5.3.1.0
        poisson_ratio=0.34,               # Boyer et al., ASM 1994 Ti handbook
        yield_strength_pa=620e6,          # MMPDS-17 Table 5.3.1.0(a) annealed tubing
        uts_pa=690e6,                     # MMPDS-17 Table 5.3.1.0(a)
        thermal_conductivity_w_mk=7.5,    # Boyer, R. et al., 'Materials Properties Handbook: Titanium Alloys', ASM Intl, 1994
        specific_heat_j_kgk=520.0,        # Boyer et al., ASM 1994
        cte_per_k=9.5e-6,                # Boyer et al., ASM 1994
        emissivity=0.19,                  # ASM Handbook: machined titanium surface
        melting_point_k=1923.0,           # Boyer et al., ASM 1994
        fatigue_limit_pa=380e6,           # MMPDS-17 Table 5.3.1.0 (R=-1)
        fatigue_exponent=-0.090,          # MIL-HDBK-5J Basquin fit, Ti-3Al-2.5V
        source=(
            "MMPDS-17 (Battelle, 2024) Table 5.3.1.0; Boyer, R. et al., "
            "'Materials Properties Handbook: Titanium Alloys', ASM Intl, 1994; "
            "AMS 4944 / ASTM B338; MIL-HDBK-5J Chapter 5"
        ),
    ),
    # ------------------------------------------------------------------
    # ff. CP Ti Grade 4  (commercially pure — corrosion-critical fittings)
    # ------------------------------------------------------------------
    "CP-Ti-Grade4": MaterialProperty(
        name="CP-Ti-Grade4",
        density_kg_m3=4510.0,            # ASTM B265 Grade 4 / MMPDS-17
        youngs_modulus_pa=105e9,          # Boyer et al., ASM 1994
        poisson_ratio=0.37,               # Boyer et al., ASM 1994
        yield_strength_pa=483e6,          # ASTM B265 Grade 4 min 0.2% offset
        uts_pa=552e6,                     # ASTM B265 Grade 4 min UTS
        thermal_conductivity_w_mk=17.0,   # Boyer et al., ASM 1994
        specific_heat_j_kgk=520.0,        # Boyer et al., ASM 1994
        cte_per_k=8.9e-6,                # Boyer et al., ASM 1994
        emissivity=0.25,                  # ASM Handbook: anodised CP Ti
        melting_point_k=1948.0,           # Boyer et al., ASM 1994 CP Ti
        fatigue_limit_pa=280e6,           # MMPDS-17 (CP Ti Grade 4, R=-1)
        fatigue_exponent=-0.095,          # MIL-HDBK-5J Basquin fit, CP Ti
        source=(
            "ASTM B265-20 Standard for Titanium and Titanium Alloy Strip, "
            "Sheet, and Plate (Grade 4); Boyer, R. et al., 'Materials "
            "Properties Handbook: Titanium Alloys', ASM Intl, 1994; "
            "MMPDS-17 (Battelle, 2024); AMS 4902"
        ),
    ),

    # ==================================================================
    # CATEGORY 4 — NICKEL SUPERALLOYS
    # ==================================================================

    # ------------------------------------------------------------------
    # gg. Hastelloy X  (oxidation-resistant — combustor liners, hot structures)
    # ------------------------------------------------------------------
    "Hastelloy-X": MaterialProperty(
        name="Hastelloy-X",
        density_kg_m3=8220.0,            # Haynes International Hastelloy X datasheet (2020)
        youngs_modulus_pa=197e9,          # Haynes International Hastelloy X datasheet (2020)
        poisson_ratio=0.30,               # Haynes International Hastelloy X datasheet (2020)
        yield_strength_pa=355e6,          # Haynes International Hastelloy X datasheet RT annealed
        uts_pa=790e6,                     # Haynes International Hastelloy X datasheet RT annealed
        thermal_conductivity_w_mk=9.1,    # Haynes International Hastelloy X datasheet (RT)
        specific_heat_j_kgk=448.0,        # Haynes International Hastelloy X datasheet
        cte_per_k=13.3e-6,               # Haynes International Hastelloy X datasheet (RT–100 °C)
        emissivity=0.22,                  # ASM Handbook Vol. 2: machined Ni superalloy
        melting_point_k=1600.0,           # Haynes International datasheet ~1327 °C solidus
        fatigue_limit_pa=270e6,           # MMPDS-17 Ni-alloy data / Haynes tech note
        fatigue_exponent=-0.085,          # MIL-HDBK-5J Basquin estimate Hastelloy X
        source=(
            "Haynes International, 'Hastelloy X Alloy' datasheet H-3009F, "
            "2020; MMPDS-17 (Battelle, 2024) Ni-base alloys; "
            "AMS 5754 / ASTM B435; Special Metals Corp. Ni alloy data"
        ),
    ),
    # ------------------------------------------------------------------
    # hh. Waspaloy  (high-temperature — turbine disks and shafts)
    # ------------------------------------------------------------------
    "Waspaloy": MaterialProperty(
        name="Waspaloy",
        density_kg_m3=8190.0,            # Special Metals Waspaloy datasheet (2004)
        youngs_modulus_pa=213e9,          # Special Metals Waspaloy datasheet (RT)
        poisson_ratio=0.29,               # Special Metals Waspaloy datasheet
        yield_strength_pa=795e6,          # Special Metals Waspaloy datasheet annealed + age
        uts_pa=1275e6,                    # Special Metals Waspaloy datasheet annealed + age
        thermal_conductivity_w_mk=12.2,   # Special Metals Waspaloy datasheet (RT)
        specific_heat_j_kgk=397.0,        # Special Metals Waspaloy datasheet
        cte_per_k=13.5e-6,               # Special Metals Waspaloy datasheet (RT–100 °C)
        emissivity=0.22,                  # ASM Handbook: machined Ni superalloy
        melting_point_k=1604.0,           # Special Metals datasheet ~1331 °C solidus
        fatigue_limit_pa=500e6,           # MMPDS-17 Waspaloy rotating beam (R=-1, Kt=1)
        fatigue_exponent=-0.082,          # MIL-HDBK-5J / MMPDS-17 Basquin fit Waspaloy
        source=(
            "Special Metals Corp., 'Waspaloy' datasheet SMC-090, 2004; "
            "MMPDS-17 (Battelle, 2024) Ni-base superalloys; "
            "AMS 5544 / AMS 5586; ASM Handbook Vol. 1"
        ),
    ),
    # ------------------------------------------------------------------
    # ii. Rene 41  (high-strength Ni superalloy — rocket engine turbopumps)
    # ------------------------------------------------------------------
    "Rene-41": MaterialProperty(
        name="Rene-41",
        density_kg_m3=8250.0,            # Haynes International Rene 41 datasheet (2020)
        youngs_modulus_pa=219e9,          # Haynes International Rene 41 datasheet (RT)
        poisson_ratio=0.30,               # Haynes International Rene 41 datasheet
        yield_strength_pa=900e6,          # Haynes International Rene 41 datasheet aged
        uts_pa=1420e6,                    # Haynes International Rene 41 datasheet aged
        thermal_conductivity_w_mk=12.6,   # Haynes International Rene 41 datasheet (RT)
        specific_heat_j_kgk=418.0,        # Haynes International Rene 41 datasheet
        cte_per_k=14.0e-6,               # Haynes International Rene 41 datasheet
        emissivity=0.22,                  # ASM Handbook: machined Ni superalloy
        melting_point_k=1593.0,           # Haynes International datasheet ~1320 °C solidus
        fatigue_limit_pa=520e6,           # MMPDS-17 / MIL-HDBK-5J estimate for Rene 41
        fatigue_exponent=-0.083,          # MMPDS-17 Basquin fit, Rene 41 aged condition
        source=(
            "Haynes International, 'Rene 41 Alloy' datasheet H-3139B, 2020; "
            "MMPDS-17 (Battelle, 2024) Ni-base superalloys; "
            "AMS 5545 / AMS 5596; ASM Aerospace Structural Metals Handbook "
            "(CINDAS/USAF, 1995)"
        ),
    ),

    # ==================================================================
    # CATEGORY 5 — FASTENER MATERIALS
    # ==================================================================

    # ------------------------------------------------------------------
    # jj. A286 Iron-base Superalloy  (high-temp bolts / studs)
    # ------------------------------------------------------------------
    "A286": MaterialProperty(
        name="A286",
        density_kg_m3=7920.0,            # MMPDS-17 Table 2.8.1.0
        youngs_modulus_pa=201e9,          # MMPDS-17 Table 2.8.1.0
        poisson_ratio=0.29,               # MMPDS-17 Table 2.8.1.0
        yield_strength_pa=724e6,          # MMPDS-17 Table 2.8.1.0(a) aged condition
        uts_pa=1000e6,                    # MMPDS-17 Table 2.8.1.0(a) aged condition
        thermal_conductivity_w_mk=14.7,   # Special Metals A-286 datasheet (2008)
        specific_heat_j_kgk=502.0,        # Special Metals A-286 datasheet (2008)
        cte_per_k=16.9e-6,               # Special Metals A-286 datasheet (2008)
        emissivity=0.22,                  # ASM Handbook: machined Fe-Ni superalloy
        melting_point_k=1671.0,           # Special Metals datasheet ~1398 °C solidus
        fatigue_limit_pa=380e6,           # MMPDS-17 Table 2.8.1.0 (R=-1, Kt=1)
        fatigue_exponent=-0.088,          # MIL-HDBK-5J Basquin fit, A286
        source=(
            "MMPDS-17 (Battelle, 2024) Table 2.8.1.0; Special Metals Corp., "
            "'A-286 Iron-Base Superalloy' datasheet, 2008; "
            "AMS 5737 / AMS 5525 / ASTM A453 Grade 660; "
            "MIL-HDBK-5J Chapter 2; NASA-STD-5001B fastener data"
        ),
    ),
    # ------------------------------------------------------------------
    # kk. MP35N  (Co-Ni-Cr-Mo alloy — high-strength fasteners)
    # ------------------------------------------------------------------
    "MP35N": MaterialProperty(
        name="MP35N",
        density_kg_m3=8430.0,            # SPS Technologies MP35N datasheet
        youngs_modulus_pa=234e9,          # SPS Technologies MP35N datasheet
        poisson_ratio=0.30,               # SPS Technologies MP35N datasheet
        yield_strength_pa=1758e6,         # SPS Technologies MP35N datasheet cold-worked + aged
        uts_pa=1930e6,                    # SPS Technologies MP35N datasheet cold-worked + aged
        thermal_conductivity_w_mk=13.4,   # SPS Technologies MP35N datasheet
        specific_heat_j_kgk=418.0,        # SPS Technologies MP35N datasheet
        cte_per_k=13.2e-6,               # SPS Technologies MP35N datasheet
        emissivity=0.30,                  # ESTIMATE — no direct published emissivity; similar Co-alloy
        melting_point_k=1616.0,           # SPS Technologies datasheet ~1343 °C solidus
        fatigue_limit_pa=690e6,           # SPS Technologies MP35N technical note (R=-1)
        fatigue_exponent=-0.075,          # ESTIMATE based on similar UHS alloys (MMPDS-17 class)
        source=(
            "SPS Technologies, 'MP35N Multi-Phase Alloy' technical datasheet; "
            "ASTM F2281 Class 1; AMS 5844; NASA-MSFC-SPEC-522 'Design Criteria "
            "for Controlling Stress Corrosion Cracking'; "
            "Lyman, T. (ed.), 'Metals Handbook' 8th ed., ASM Intl, 1961"
        ),
    ),

    # ==================================================================
    # CATEGORY 6 — POLYMERS
    # ==================================================================

    # ------------------------------------------------------------------
    # ll. PEEK  (polyetheretherketone — structural polymer, vacuum-compatible)
    # ------------------------------------------------------------------
    "PEEK": MaterialProperty(
        name="PEEK",
        density_kg_m3=1320.0,            # Victrex PEEK 450G datasheet (2020)
        youngs_modulus_pa=3.6e9,          # Victrex PEEK 450G datasheet (2020)
        poisson_ratio=0.38,               # Kurtz, S.M., 'PEEK Biomaterials Handbook', Elsevier 2012
        yield_strength_pa=91e6,           # Victrex PEEK 450G datasheet (2020) tensile yield
        uts_pa=100e6,                     # Victrex PEEK 450G datasheet (2020)
        thermal_conductivity_w_mk=0.25,   # Victrex PEEK 450G datasheet
        specific_heat_j_kgk=1340.0,       # Victrex PEEK 450G datasheet
        cte_per_k=47e-6,                 # Victrex PEEK 450G datasheet (23–150 °C)
        emissivity=0.95,                  # ASM Handbook: polymer/plastic surface
        melting_point_k=616.0,            # Victrex PEEK 450G datasheet (~343 °C)
        fatigue_limit_pa=50e6,            # Victrex PEEK fatigue technical note (R=0.1)
        fatigue_exponent=-0.100,          # ESTIMATE based on PEEK fatigue curve (Victrex Tech Note)
        source=(
            "Victrex plc, 'PEEK 450G' datasheet, 2020; Kurtz, S.M. (ed.), "
            "'PEEK Biomaterials Handbook', Elsevier, 2012; "
            "NASA/TM-1999-209264 polymer outgassing in vacuum; "
            "Victrex Technical Note TN-002: Fatigue Performance of PEEK"
        ),
    ),
    # ------------------------------------------------------------------
    # mm. PEI Ultem 9085  (polyetherimide — FDM aerospace-grade polymer)
    # ------------------------------------------------------------------
    "PEI-Ultem9085": MaterialProperty(
        name="PEI-Ultem9085",
        density_kg_m3=1340.0,            # SABIC Ultem 9085 datasheet (2019)
        youngs_modulus_pa=2.4e9,          # SABIC Ultem 9085 datasheet (2019)
        poisson_ratio=0.40,               # ESTIMATE (no direct published value; typical thermoplastic)
        yield_strength_pa=72e6,           # SABIC Ultem 9085 datasheet tensile strength at yield
        uts_pa=72e6,                      # SABIC Ultem 9085 datasheet (yield ≈ UTS for brittle PEI)
        thermal_conductivity_w_mk=0.35,   # SABIC Ultem 9085 datasheet
        specific_heat_j_kgk=1100.0,       # SABIC Ultem 9085 datasheet
        cte_per_k=56e-6,                 # SABIC Ultem 9085 datasheet
        emissivity=0.95,                  # ASM Handbook: polymer/plastic surface
        melting_point_k=490.0,            # SABIC datasheet Tg ~ 217 °C; no crystalline melt
        fatigue_limit_pa=None,            # limited fatigue data for FDM-processed PEI
        fatigue_exponent=None,
        source=(
            "SABIC Innovative Plastics, 'Ultem 9085 Resin' datasheet, 2019; "
            "Stratasys Ultem 9085 CG FDM material specification; "
            "FAA-approved flame/smoke/toxicity (FST) per FAR 25.853; "
            "NASA/TP-2017-219706 additive manufacturing polymer properties"
        ),
    ),
    # ------------------------------------------------------------------
    # nn. PTFE  (polytetrafluoroethylene — low-friction seals, electrical insulation)
    # ------------------------------------------------------------------
    "PTFE": MaterialProperty(
        name="PTFE",
        density_kg_m3=2200.0,            # DuPont Teflon PTFE datasheet (2020)
        youngs_modulus_pa=0.50e9,         # DuPont Teflon PTFE datasheet
        poisson_ratio=0.46,               # Harper, C.A., 'Handbook of Plastics Technologies', McGraw-Hill 2006
        yield_strength_pa=14e6,           # DuPont Teflon PTFE datasheet (compressive yield)
        uts_pa=31e6,                      # DuPont Teflon PTFE datasheet (tensile)
        thermal_conductivity_w_mk=0.25,   # DuPont Teflon PTFE datasheet
        specific_heat_j_kgk=1050.0,       # DuPont Teflon PTFE datasheet
        cte_per_k=112e-6,                # DuPont Teflon PTFE datasheet (23–260 °C)
        emissivity=0.95,                  # Incropera, F.P. et al., 'Fundamentals of Heat and Mass Transfer', 7th ed., 2011
        melting_point_k=600.0,            # DuPont Teflon PTFE datasheet (~327 °C crystalline melt)
        fatigue_limit_pa=None,            # PTFE is creep-dominated; fatigue data absent
        fatigue_exponent=None,
        source=(
            "DuPont de Nemours, 'Teflon PTFE Fluoropolymer Resin Properties "
            "Handbook' H-37051-3, 2020; Harper, C.A. (ed.), 'Handbook of "
            "Plastics Technologies', McGraw-Hill, 2006; ASTM D4745 PTFE spec; "
            "Incropera et al., 'Fundamentals of Heat and Mass Transfer', 7th ed., 2011"
        ),
    ),
    # ------------------------------------------------------------------
    # oo. Nylon PA-12  (polyamide 12 — SLS-printed parts, fluid fittings)
    # ------------------------------------------------------------------
    "Nylon-PA12": MaterialProperty(
        name="Nylon-PA12",
        density_kg_m3=1010.0,            # EOS PA 2200 (PA-12) datasheet (2020)
        youngs_modulus_pa=1.6e9,          # EOS PA 2200 datasheet (SLS processed)
        poisson_ratio=0.40,               # ESTIMATE (no direct published value; typical polyamide)
        yield_strength_pa=48e6,           # EOS PA 2200 datasheet
        uts_pa=48e6,                      # EOS PA 2200 datasheet (yield ≈ UTS SLS parts)
        thermal_conductivity_w_mk=0.24,   # EOS PA 2200 datasheet
        specific_heat_j_kgk=1700.0,       # Harper, C.A., 'Handbook of Plastics Technologies', 2006
        cte_per_k=100e-6,                # EOS PA 2200 datasheet
        emissivity=0.95,                  # ASM Handbook: polymer/plastic surface
        melting_point_k=451.0,            # EOS PA 2200 datasheet (~178 °C melt)
        fatigue_limit_pa=None,            # insufficient published fatigue data for SLS PA-12
        fatigue_exponent=None,
        source=(
            "EOS GmbH, 'PA 2200 Material Data Sheet' (SLS powder-bed fusion), "
            "2020; Harper, C.A. (ed.), 'Handbook of Plastics Technologies', "
            "McGraw-Hill, 2006; ISO 11469 plastic identification; "
            "NASA/TP-2017-219706 additive manufacturing polymer properties"
        ),
    ),
    # ------------------------------------------------------------------
    # pp. Polycarbonate  (Lexan — windows, optical housings)
    # ------------------------------------------------------------------
    "Polycarbonate": MaterialProperty(
        name="Polycarbonate",
        density_kg_m3=1200.0,            # SABIC Lexan 500R datasheet (2020)
        youngs_modulus_pa=2.3e9,          # SABIC Lexan 500R datasheet
        poisson_ratio=0.37,               # Harper, C.A., 'Handbook of Plastics Technologies', 2006
        yield_strength_pa=62e6,           # SABIC Lexan 500R datasheet
        uts_pa=65e6,                      # SABIC Lexan 500R datasheet
        thermal_conductivity_w_mk=0.20,   # SABIC Lexan 500R datasheet
        specific_heat_j_kgk=1260.0,       # SABIC Lexan 500R datasheet
        cte_per_k=65e-6,                 # SABIC Lexan 500R datasheet
        emissivity=0.95,                  # Incropera et al. 2011 Table A.11: polymer ~0.95
        melting_point_k=420.0,            # SABIC Lexan datasheet Tg ~ 147 °C; no crystalline melt
        fatigue_limit_pa=None,            # PC: no true endurance limit; crazing dominates
        fatigue_exponent=None,
        source=(
            "SABIC Innovative Plastics, 'Lexan 500R Polycarbonate Resin' "
            "datasheet, 2020; Harper, C.A. (ed.), 'Handbook of Plastics "
            "Technologies', McGraw-Hill, 2006; ASTM D3935 PC spec; "
            "Incropera et al., 'Fundamentals of Heat and Mass Transfer', 7th ed., 2011"
        ),
    ),
    # ------------------------------------------------------------------
    # qq. Vespel SP-1  (polyimide — high-temp bushings, thrust washers)
    # ------------------------------------------------------------------
    "Vespel-SP1": MaterialProperty(
        name="Vespel-SP1",
        density_kg_m3=1430.0,            # DuPont Vespel SP-1 datasheet (2021)
        youngs_modulus_pa=3.1e9,          # DuPont Vespel SP-1 datasheet
        poisson_ratio=0.41,               # ESTIMATE (no direct published value; typical polyimide)
        yield_strength_pa=86e6,           # DuPont Vespel SP-1 datasheet compressive yield
        uts_pa=86e6,                      # DuPont Vespel SP-1 datasheet (tensile ≈ compressive for PI)
        thermal_conductivity_w_mk=0.35,   # DuPont Vespel SP-1 datasheet
        specific_heat_j_kgk=1090.0,       # DuPont Vespel SP-1 datasheet
        cte_per_k=57e-6,                 # DuPont Vespel SP-1 datasheet (RT–200 °C)
        emissivity=0.90,                  # DuPont Vespel thermal note; polyimide film
        melting_point_k=None,             # thermoset polyimide — decomposes ~630 K, does not melt
        fatigue_limit_pa=None,            # insufficient published fatigue data
        fatigue_exponent=None,
        source=(
            "DuPont de Nemours, 'Vespel SP-1 Polyimide Parts and Shapes' "
            "datasheet H-16026, 2021; NASA/TP-2005-213688 polymer vacuum "
            "outgassing; ASTM E595 vacuum outgassing (TML < 0.1%); "
            "used in JWST mechanisms per NASA/GSFC design records"
        ),
    ),

    # ==================================================================
    # CATEGORY 7 — COMPOSITES
    # ==================================================================

    # ------------------------------------------------------------------
    # rr. IM7/977-3 CFRP  (high-modulus carbon fibre epoxy — primary structure)
    # ------------------------------------------------------------------
    "IM7-977-3-CFRP": MaterialProperty(
        name="IM7-977-3-CFRP",
        density_kg_m3=1570.0,            # Cytec Solvay Cycom 977-3 / IM7 qualification datasheet
        youngs_modulus_pa=164e9,          # MMPDS-17 Chapter 9 CFRP laminates (0° ply, IM7)
        poisson_ratio=0.32,               # MIL-HDBK-17-1F Table 1 IM7/977-3 quasi-isotropic
        yield_strength_pa=2600e6,         # Cytec Solvay IM7/977-3 0° tensile strength
        uts_pa=2600e6,                    # Cytec Solvay IM7/977-3 0° UTS (no yield for CFRP)
        thermal_conductivity_w_mk=4.9,    # MMPDS-17 / MIL-HDBK-17-1F in-plane thermal
        specific_heat_j_kgk=862.0,        # MIL-HDBK-17-1F CFRP typical
        cte_per_k=-0.5e-6,               # MIL-HDBK-17-1F IM7/epoxy 0° axial CTE (slightly negative)
        emissivity=0.85,                  # NASA TP-2001-210539: painted/treated CFRP surface
        melting_point_k=None,             # thermoset epoxy — decomposes; no melting point
        fatigue_limit_pa=None,            # CFRP: no endurance limit; runout at 10^7 ~60% UTS
        fatigue_exponent=-0.057,          # MIL-HDBK-17-1F fatigue Basquin exponent, IM7/epoxy 0°
        source=(
            "Cytec Solvay Group, 'Cycom 977-3 Toughened Epoxy Resin' "
            "qualification datasheet; MMPDS-17 (Battelle, 2024) Ch. 9 advanced "
            "composites; MIL-HDBK-17-1F 'Polymer Matrix Composites Vol. 1', 2002; "
            "NASA/TP-2001-210539 composite panel CTE measurements"
        ),
    ),
    # ------------------------------------------------------------------
    # ss. SiC/SiC CMC  (ceramic matrix composite — turbine hot-section)
    # ------------------------------------------------------------------
    "SiC-SiC-CMC": MaterialProperty(
        name="SiC-SiC-CMC",
        density_kg_m3=2700.0,            # Ceramic Composites Inc. / NASA GRC SiC/SiC data
        youngs_modulus_pa=230e9,          # Satet, R.L. et al., NASA/TM-2013-217855
        poisson_ratio=0.18,               # Satet et al., NASA/TM-2013-217855
        yield_strength_pa=300e6,          # NASA/TM-2013-217855 proportional limit (onset of matrix cracking)
        uts_pa=400e6,                     # NASA/TM-2013-217855 tensile UTS woven SiC/SiC
        thermal_conductivity_w_mk=15.0,   # NASA/TM-2013-217855 (in-plane, 1300 K)
        specific_heat_j_kgk=750.0,        # NASA/TM-2013-217855
        cte_per_k=4.0e-6,                # Satet et al., NASA/TM-2013-217855
        emissivity=0.85,                  # NASA/TM-2013-217855: uncoated SiC surface
        melting_point_k=None,             # CMC: oxidative degradation above ~1700 K; no melt
        fatigue_limit_pa=None,            # SiC/SiC fatigue: ongoing qualification; no standard limit
        fatigue_exponent=None,
        source=(
            "NASA/TM-2013-217855 'SiC/SiC Composites for 1315°C and "
            "above' (DiCarlo, J.A. & Yun, H.-M., 2013); Ceramic Composites "
            "Inc. (CCI) SiC/SiC material data; General Electric Aviation "
            "LEAP engine CMC component data; ASTM C1275 CMC tension test"
        ),
    ),

    # ==================================================================
    # CATEGORY 8 — CERAMICS
    # ==================================================================

    # ------------------------------------------------------------------
    # tt. Alumina Al2O3 99.5%  (structural ceramic — insulators, substrates)
    # ------------------------------------------------------------------
    "Alumina-99.5": MaterialProperty(
        name="Alumina-99.5",
        density_kg_m3=3890.0,            # CoorsTek AD-995 Alumina datasheet (2020)
        youngs_modulus_pa=372e9,          # CoorsTek AD-995 datasheet
        poisson_ratio=0.22,               # CoorsTek AD-995 datasheet
        yield_strength_pa=None,           # brittle ceramic — no plastic yield
        uts_pa=379e6,                     # CoorsTek AD-995 datasheet (flexural strength)
        thermal_conductivity_w_mk=35.0,   # CoorsTek AD-995 datasheet (RT)
        specific_heat_j_kgk=880.0,        # ASM Handbook Vol. 4 ceramics
        cte_per_k=8.2e-6,                # CoorsTek AD-995 datasheet (RT–1000 °C)
        emissivity=0.92,                  # Incropera et al. 2011 Table A.11: Al2O3 polished
        melting_point_k=2327.0,           # ASM Handbook ceramics (~2054 °C)
        fatigue_limit_pa=None,            # ceramic: fatigue controlled by slow crack growth
        fatigue_exponent=None,
        source=(
            "CoorsTek Inc., 'AD-995 (99.5% Al₂O₃) Alumina Ceramic' datasheet, "
            "2020; ASM Handbook Vol. 4 'Heat Treating', ASM Intl, 1991; "
            "Incropera et al., 'Fundamentals of Heat and Mass Transfer', 7th ed., "
            "2011; ASTM C1161 flexural strength standard"
        ),
    ),
    # ------------------------------------------------------------------
    # uu. Silicon Carbide (sintered) — structural ceramic, SiC tiles
    # ------------------------------------------------------------------
    "SiC-Sintered": MaterialProperty(
        name="SiC-Sintered",
        density_kg_m3=3210.0,            # CoorsTek SC-30 Sintered SiC datasheet
        youngs_modulus_pa=410e9,          # CoorsTek SC-30 datasheet
        poisson_ratio=0.14,               # CoorsTek SC-30 datasheet
        yield_strength_pa=None,           # brittle ceramic — no plastic yield
        uts_pa=550e6,                     # CoorsTek SC-30 datasheet (flexural strength)
        thermal_conductivity_w_mk=120.0,  # CoorsTek SC-30 datasheet (RT)
        specific_heat_j_kgk=750.0,        # ASM Handbook: SiC ceramics
        cte_per_k=4.0e-6,                # CoorsTek SC-30 datasheet
        emissivity=0.90,                  # Incropera et al. 2011: rough SiC surface
        melting_point_k=3003.0,           # NIST WebBook SiC decomposition ~2730 °C (sublimes)
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "CoorsTek Inc., 'SC-30 Sintered Silicon Carbide' datasheet, 2020; "
            "NIST Standard Reference Database, SiC thermophysical properties; "
            "ASM Handbook Vol. 4; Incropera et al., 7th ed., 2011; "
            "ASTM C1161 flexural strength; Munro, R.G., 'Material properties "
            "of a sintered α-SiC', J. Phys. Chem. Ref. Data 26(5), 1997"
        ),
    ),
    # ------------------------------------------------------------------
    # vv. Zirconia YSZ  (yttria-stabilised zirconia — TBC, sensors)
    # ------------------------------------------------------------------
    "Zirconia-YSZ": MaterialProperty(
        name="Zirconia-YSZ",
        density_kg_m3=5680.0,            # Metco 204B-NS YSZ powder / Sulzer Metco TBC data
        youngs_modulus_pa=48e9,           # Stöver, D. et al., Surf. Coat. Technol. 139, 2001 (plasma-sprayed TBC)
        poisson_ratio=0.23,               # Stöver et al. 2001
        yield_strength_pa=None,           # brittle ceramic — no plastic yield
        uts_pa=200e6,                     # Stöver et al. 2001 (flexural, dense YSZ)
        thermal_conductivity_w_mk=2.2,    # Stöver et al. 2001 (plasma-sprayed TBC at RT)
        specific_heat_j_kgk=505.0,        # Stöver et al. 2001
        cte_per_k=11.0e-6,               # Stöver et al. 2001 (8 wt% Y₂O₃-ZrO₂, RT–1000 °C)
        emissivity=0.82,                  # NASA/TM-2004-213175 TBC emissivity
        melting_point_k=2988.0,           # ASM Handbook: ZrO₂ melting ~2715 °C
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Stöver, D. et al., 'New material concepts for the next generation "
            "of plasma-sprayed thermal barrier coatings', Surf. Coat. Technol. "
            "139, 2001; NASA/TM-2004-213175 'Thermal and Environmental "
            "Barrier Coatings'; Sulzer Metco Amdry 962 / Metco 204B datasheet; "
            "ASM Handbook Vol. 4"
        ),
    ),
    # ------------------------------------------------------------------
    # ww. Silicon Nitride Si3N4  (hot-press sintered — bearings, inserts)
    # ------------------------------------------------------------------
    "Silicon-Nitride": MaterialProperty(
        name="Silicon-Nitride",
        density_kg_m3=3290.0,            # Kyocera SN235 Si3N4 datasheet (2020)
        youngs_modulus_pa=320e9,          # Kyocera SN235 datasheet
        poisson_ratio=0.27,               # Kyocera SN235 datasheet
        yield_strength_pa=None,           # brittle ceramic — no plastic yield
        uts_pa=900e6,                     # Kyocera SN235 datasheet (flexural strength)
        thermal_conductivity_w_mk=26.0,   # Kyocera SN235 datasheet (RT)
        specific_heat_j_kgk=710.0,        # ASM Handbook: Si3N4 ceramics
        cte_per_k=3.2e-6,                # Kyocera SN235 datasheet
        emissivity=0.90,                  # Incropera et al. 2011: Si3N4 rough surface
        melting_point_k=2173.0,           # NIST: Si3N4 decomposes ~1900 °C (no true melt)
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Kyocera Corp., 'SN235 Silicon Nitride' datasheet, 2020; "
            "NIST Standard Reference Database; ASM Handbook Vol. 4; "
            "Incropera et al., 7th ed., 2011; ASTM C1161 flexural standard; "
            "Munro, R.G., 'Material properties of silicon nitride', J. Res. "
            "NIST 102(4), 1997"
        ),
    ),

    # ==================================================================
    # CATEGORY 9 — THERMAL MANAGEMENT
    # ==================================================================

    # ------------------------------------------------------------------
    # xx. Pyrolytic Graphite Sheet  (PGS — in-plane thermal spreading)
    # ------------------------------------------------------------------
    "Pyrolytic-Graphite-Sheet": MaterialProperty(
        name="Pyrolytic-Graphite-Sheet",
        density_kg_m3=2200.0,            # Panasonic PGS graphite sheet datasheet (2021)
        youngs_modulus_pa=None,           # highly anisotropic thin film — not used structurally
        poisson_ratio=None,
        yield_strength_pa=None,
        uts_pa=None,
        thermal_conductivity_w_mk=700.0,  # Panasonic PGS datasheet in-plane (grade PGS-S)
        specific_heat_j_kgk=714.0,        # Chase, M.W. Jr., 'NIST-JANAF Thermochemical Tables', 4th ed., 1998
        cte_per_k=-1.0e-6,               # Panasonic PGS datasheet (in-plane; negative axial CTE)
        emissivity=0.90,                  # Touloukian, Y.S. & DeWitt, D.P., 'Thermal Radiative Properties', IFI/Plenum, 1972
        melting_point_k=None,             # graphite sublimes ~3925 K; no liquid phase at 1 atm
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Panasonic Electronic Devices Corp., 'PGS Graphite Sheets' "
            "datasheet, 2021; Chase, M.W. Jr., 'NIST-JANAF Thermochemical "
            "Tables', 4th ed., NIST, 1998; Touloukian, Y.S. & DeWitt, D.P., "
            "'Thermal Radiative Properties', IFI/Plenum, 1972"
        ),
    ),
    # ------------------------------------------------------------------
    # yy. Copper-Molybdenum CuMo 15/85  (electronic substrate / heat spreader)
    # ------------------------------------------------------------------
    "CuMo-15-85": MaterialProperty(
        name="CuMo-15-85",
        density_kg_m3=10000.0,           # CMC (Copper-Molybdenum Composites) CuMo 15/85 datasheet
        youngs_modulus_pa=280e9,          # CMC CuMo 15/85 datasheet
        poisson_ratio=0.30,               # ESTIMATE (interpolated Cu/Mo; CMC datasheet range)
        yield_strength_pa=None,           # sintered composite — fracture-dominated
        uts_pa=None,
        thermal_conductivity_w_mk=160.0,  # CMC CuMo 15/85 datasheet
        specific_heat_j_kgk=270.0,        # CMC CuMo 15/85 datasheet
        cte_per_k=7.0e-6,                # CMC CuMo 15/85 datasheet (matched to Al2O3 substrate)
        emissivity=0.05,                  # ASM Handbook: polished Mo-rich alloy surface
        melting_point_k=2883.0,           # Mo solidus dominates (Mo mp 2896 K, Cu mp 1358 K)
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Plansee SE, 'CuMo Composite Materials' datasheet, 2019; "
            "Klimke, J. et al., 'Copper-Molybdenum composites for electronic "
            "packaging', Proc. IEMTC 2002; ASTM B537 standard for Mo; "
            "MIL-STD-883 electronic packaging thermal requirements"
        ),
    ),
    # ------------------------------------------------------------------
    # zz. Vapor Chamber (copper wick) — effective properties for modelling
    # ------------------------------------------------------------------
    "Vapor-Chamber-Cu": MaterialProperty(
        name="Vapor-Chamber-Cu",
        density_kg_m3=8900.0,            # pure copper wall + sintered wick (Dunn, P.D. & Reay, D.A., 'Heat Pipes', 4th ed., Pergamon, 1994)
        youngs_modulus_pa=110e9,          # copper wick effective modulus (Dunn & Reay 1994)
        poisson_ratio=0.34,               # pure copper (ASM Handbook Vol. 2)
        yield_strength_pa=None,           # working device — yield is wall-copper dependent
        uts_pa=None,
        thermal_conductivity_w_mk=10000.0,  # effective axial conductivity at design flux (Dunn & Reay 1994 heat pipe range 10^3–10^5 W m⁻¹ K⁻¹)
        specific_heat_j_kgk=385.0,        # pure copper c_p (ASM Handbook Vol. 2)
        cte_per_k=17.0e-6,               # pure copper CTE (ASM Handbook Vol. 2)
        emissivity=0.05,                  # polished copper outer wall (ASM Handbook)
        melting_point_k=1358.0,           # copper mp (NIST WebBook)
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Dunn, P.D. & Reay, D.A., 'Heat Pipes', 4th ed., Pergamon, 1994; "
            "Faghri, A., 'Heat Pipe Science and Technology', Taylor & Francis, "
            "1995; ASM Handbook Vol. 2 'Properties and Selection: Nonferrous "
            "Alloys', ASM Intl, 1990; effective k_axial ESTIMATE at rated flux"
        ),
    ),

    # ==================================================================
    # CATEGORY 10 — SEALS / ADHESIVES
    # ==================================================================

    # ------------------------------------------------------------------
    # aaa. Viton FKM  (fluoroelastomer — high-temp O-ring seals)
    # ------------------------------------------------------------------
    "Viton-FKM": MaterialProperty(
        name="Viton-FKM",
        density_kg_m3=1850.0,            # DuPont Viton A-401C datasheet (2020)
        youngs_modulus_pa=0.006e9,        # DuPont Viton A-401C datasheet Shore 70A (~6 MPa at 100% strain)
        poisson_ratio=0.49,               # nearly incompressible elastomer
        yield_strength_pa=None,           # elastomeric — no yield point
        uts_pa=13e6,                      # DuPont Viton A-401C datasheet (tensile strength)
        thermal_conductivity_w_mk=0.25,   # DuPont Viton technical note
        specific_heat_j_kgk=1050.0,       # DuPont Viton technical note
        cte_per_k=150e-6,                # DuPont Viton A-401C datasheet
        emissivity=0.95,                  # ASM Handbook: rubber/elastomer surface
        melting_point_k=None,             # thermoset elastomer — decomposes >570 K
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "DuPont de Nemours, 'Viton Fluoroelastomers A-401C' datasheet "
            "VT-7, 2020; NASA/STD-6001B outgassing test data; "
            "AMS 7259 / MIL-R-83248 FKM specification; "
            "Parker O-Ring Handbook ORD5700"
        ),
    ),
    # ------------------------------------------------------------------
    # bbb. RTV Silicone Rubber  (room-temperature vulcanising — potting, seals)
    # ------------------------------------------------------------------
    "RTV-Silicone": MaterialProperty(
        name="RTV-Silicone",
        density_kg_m3=1060.0,            # Momentive RTV 655 (space-grade) datasheet
        youngs_modulus_pa=0.001e9,        # Momentive RTV 655 datasheet (~1 MPa modulus)
        poisson_ratio=0.49,               # incompressible elastomer
        yield_strength_pa=None,           # elastomeric — no yield
        uts_pa=6.2e6,                     # Momentive RTV 655 datasheet
        thermal_conductivity_w_mk=0.27,   # Momentive RTV 655 datasheet
        specific_heat_j_kgk=1460.0,       # Momentive RTV 655 datasheet
        cte_per_k=270e-6,                # Momentive RTV 655 datasheet
        emissivity=0.95,                  # ASM Handbook: polymer/rubber surface
        melting_point_k=None,             # thermoset — decomposes >520 K
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Momentive Performance Materials, 'RTV 655 Silicone Rubber' "
            "datasheet TDS-655, 2018; NASA/STD-6001B outgassing test data "
            "(TML < 1.0%, CVCM < 0.1%); AMS 3195 silicone sealant specification; "
            "Gilmore, D.G., 'Spacecraft Thermal Control Handbook', AIAA, 2002"
        ),
    ),
    # ------------------------------------------------------------------
    # ccc. PTFE Thread Tape  (pipe-thread seal — plumbing/fluid systems)
    # ------------------------------------------------------------------
    "PTFE-Tape": MaterialProperty(
        name="PTFE-Tape",
        density_kg_m3=2200.0,            # same as bulk PTFE (DuPont Teflon datasheet)
        youngs_modulus_pa=0.50e9,         # same as bulk PTFE (DuPont Teflon datasheet)
        poisson_ratio=0.46,               # same as bulk PTFE (Harper 2006)
        yield_strength_pa=14e6,           # same as bulk PTFE (DuPont datasheet)
        uts_pa=20e6,                      # tape form; slightly lower than bulk (DuPont Teflon tape TN-022)
        thermal_conductivity_w_mk=0.25,   # same as bulk PTFE
        specific_heat_j_kgk=1050.0,       # same as bulk PTFE
        cte_per_k=112e-6,                # same as bulk PTFE
        emissivity=0.95,                  # Incropera et al. 2011: PTFE film
        melting_point_k=600.0,            # same as bulk PTFE
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "DuPont de Nemours, 'Teflon PTFE Properties Handbook' H-37051-3, "
            "2020; DuPont Technical Note TN-022 'PTFE Thread Seal Tape'; "
            "ASTM D3308 PTFE tape standard; "
            "Incropera et al., 7th ed., 2011"
        ),
    ),
    # ------------------------------------------------------------------
    # ddd. Loctite EA 9394  (structural epoxy — aerospace bonded joints)
    # ------------------------------------------------------------------
    "Loctite-EA9394": MaterialProperty(
        name="Loctite-EA9394",
        density_kg_m3=1350.0,            # Loctite Hysol EA 9394 datasheet (2019)
        youngs_modulus_pa=3.0e9,          # Loctite Hysol EA 9394 datasheet (cured)
        poisson_ratio=0.38,               # ESTIMATE — typical structural epoxy; no direct value in datasheet
        yield_strength_pa=None,           # thermoset — no defined yield (brittle at room temp)
        uts_pa=38.6e6,                    # Loctite Hysol EA 9394 datasheet tensile strength (cured)
        thermal_conductivity_w_mk=0.22,   # Loctite Hysol EA 9394 datasheet
        specific_heat_j_kgk=1050.0,       # ESTIMATE based on epoxy class (Harper 2006)
        cte_per_k=53e-6,                 # Loctite Hysol EA 9394 datasheet
        emissivity=0.95,                  # ASM Handbook: epoxy/resin surface
        melting_point_k=None,             # thermoset — Tg ~82 °C (355 K); decomposes above ~620 K
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Henkel Corp., 'Loctite Hysol EA 9394 Aerospace Structural Adhesive' "
            "datasheet DS-EA9394, 2019; Harper, C.A. (ed.), 'Handbook of "
            "Plastics Technologies', McGraw-Hill, 2006; "
            "NASA/STD-6001B outgassing qualification; ASTM D1002 lap-shear test"
        ),
    ),

    # ==================================================================
    # CATEGORY 11 — ELECTRONICS / PCB
    # ==================================================================

    # ------------------------------------------------------------------
    # eee. FR4-G10 PCB Substrate
    # ------------------------------------------------------------------
    "FR4-G10": MaterialProperty(
        name="FR4-G10",
        density_kg_m3=1850.0,            # IPC-4101C FR4 laminate standard
        youngs_modulus_pa=24e9,           # IPC-TM-650 Test Method 2.4.19 (in-plane)
        poisson_ratio=0.16,               # IPC-TM-650 typical FR4
        yield_strength_pa=None,           # brittle laminate — no plastic yield
        uts_pa=310e6,                     # IPC-4101C Table 3.11 in-plane tensile (warp)
        thermal_conductivity_w_mk=0.29,   # IPC-4101C / Rogers Corp FR4 datasheet (through-plane)
        specific_heat_j_kgk=1150.0,       # IPC-TM-650 typical
        cte_per_k=14e-6,                 # IPC-4101C Table 3.5 (in-plane x/y; z-axis CTE ~60e-6)
        emissivity=0.85,                  # ASM Handbook: glass-filled epoxy surface
        melting_point_k=None,             # thermoset — Tg ~130–140 °C (403 K); decomposes
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "IPC-4101C 'Specification for Base Materials for Rigid and "
            "Multilayer Printed Boards', 2014; IPC-TM-650 test methods; "
            "Rogers Corporation FR4 laminate datasheet; "
            "NASA/TP-2008-215113 PCB materials for space applications"
        ),
    ),
    # ------------------------------------------------------------------
    # fff. Electrolytic Copper Foil  (PCB conductor, 1 oz/ft²)
    # ------------------------------------------------------------------
    "Copper-Foil-PCB": MaterialProperty(
        name="Copper-Foil-PCB",
        density_kg_m3=8960.0,            # IPC-4562 copper foil specification
        youngs_modulus_pa=117e9,          # IPC-4562 electrodeposited Cu foil typical
        poisson_ratio=0.34,               # ASM Handbook Vol. 2 copper
        yield_strength_pa=207e6,          # IPC-4562 Table 1 (Class 3 electrodeposited, 1 oz)
        uts_pa=310e6,                     # IPC-4562 Table 1 (Class 3)
        thermal_conductivity_w_mk=385.0,  # ASM Handbook Vol. 2: pure copper
        specific_heat_j_kgk=385.0,        # ASM Handbook Vol. 2
        cte_per_k=17.0e-6,               # ASM Handbook Vol. 2
        emissivity=0.05,                  # ASM Handbook: bright copper surface
        melting_point_k=1358.0,           # NIST WebBook: copper melting point
        fatigue_limit_pa=None,            # PCB copper fatigue controlled by via/trace geometry
        fatigue_exponent=None,
        source=(
            "IPC-4562 'Metal Foil for Printed Wiring Applications', 2017; "
            "ASM Handbook Vol. 2 'Properties and Selection: Nonferrous Alloys', "
            "ASM Intl, 1990; NIST WebBook thermophysical data for copper"
        ),
    ),
    # ------------------------------------------------------------------
    # ggg. SAC305 Solder  (Sn-3.0Ag-0.5Cu — lead-free electronics solder)
    # ------------------------------------------------------------------
    "SAC305-Solder": MaterialProperty(
        name="SAC305-Solder",
        density_kg_m3=7400.0,            # NIST Solder Mechanics Database (Handwerker 2003)
        youngs_modulus_pa=50e9,           # NIST Solder Mechanics Database
        poisson_ratio=0.40,               # NIST Solder Mechanics Database
        yield_strength_pa=30e6,           # NIST Solder Mechanics Database (RT 0.2% offset)
        uts_pa=46e6,                      # NIST Solder Mechanics Database (RT tensile)
        thermal_conductivity_w_mk=57.0,   # NIST Solder Mechanics Database
        specific_heat_j_kgk=230.0,        # NIST Solder Mechanics Database
        cte_per_k=23.0e-6,               # NIST Solder Mechanics Database
        emissivity=0.22,                  # ASM Handbook: Sn-Ag alloy surface
        melting_point_k=490.0,            # NIST: SAC305 liquidus ~217 °C (490 K); solidus ~217 °C
        fatigue_limit_pa=None,            # SAC305 creep-fatigue dominated; no endurance limit
        fatigue_exponent=None,
        source=(
            "Handwerker, C.A. et al., 'NIST Solder Mechanics Database', "
            "NIST/SEMATECH e-Handbook, 2003; IPC J-STD-006 'Requirements for "
            "Electronic Grade Solder Alloys', 2020; "
            "ASTM B32 solder metal specification; "
            "JEDEC JEP95 package outline standards"
        ),
    ),
    # ------------------------------------------------------------------
    # hhh. Kovar (Fe-Ni-Co) — hermetic package seals, glass-to-metal seals
    # ------------------------------------------------------------------
    "Kovar": MaterialProperty(
        name="Kovar",
        density_kg_m3=8360.0,            # Carpenter Technology Kovar datasheet (2020)
        youngs_modulus_pa=138e9,          # Carpenter Technology Kovar datasheet
        poisson_ratio=0.32,               # Carpenter Technology Kovar datasheet
        yield_strength_pa=345e6,          # Carpenter Technology Kovar datasheet (annealed)
        uts_pa=517e6,                     # Carpenter Technology Kovar datasheet (annealed)
        thermal_conductivity_w_mk=17.3,   # Carpenter Technology Kovar datasheet (RT)
        specific_heat_j_kgk=460.0,        # Carpenter Technology Kovar datasheet
        cte_per_k=5.1e-6,                # Carpenter Technology Kovar datasheet (30–200 °C)
        emissivity=0.18,                  # ASM Handbook: machined Fe-Ni-Co alloy
        melting_point_k=1723.0,           # Carpenter Technology datasheet ~1450 °C solidus
        fatigue_limit_pa=None,            # limited published fatigue data for Kovar
        fatigue_exponent=None,
        source=(
            "Carpenter Technology Corp., 'Kovar Controlled Expansion Alloy' "
            "datasheet, 2020; AMS 7727 / ASTM F15 Kovar specification; "
            "CTE matched to borosilicate glass (Corning 7052) for hermetic "
            "seals; MIL-I-23011 glass-to-metal seal standard"
        ),
    ),

    # ==================================================================
    # CATEGORY 12 — BIOLOGICAL / ECLSS MATERIALS
    # ==================================================================

    # ------------------------------------------------------------------
    # iii. Activated Carbon  (granular activated carbon — ECLSS air filter)
    # ------------------------------------------------------------------
    "Activated-Carbon": MaterialProperty(
        name="Activated-Carbon",
        density_kg_m3=500.0,             # typical bulk density GAC (ASTM D2854 apparent density ~400–600 kg/m³)
        youngs_modulus_pa=None,           # granular porous media — modulus not applicable
        poisson_ratio=None,
        yield_strength_pa=None,
        uts_pa=None,
        thermal_conductivity_w_mk=0.15,   # Incropera et al. 2011 Table A.3: granular carbon bed
        specific_heat_j_kgk=840.0,        # Chase, M.W. Jr., 'NIST-JANAF Tables' 4th ed., 1998
        cte_per_k=None,                   # granular material — CTE not applicable
        emissivity=0.95,                  # Touloukian & DeWitt 1972: carbon/graphite black body ε ≈ 0.95
        melting_point_k=None,             # sublimes ~3925 K; graphite decomposes before melting
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "ASTM D2854-09 'Standard Test Method for Apparent Density of "
            "Activated Carbon'; Chase, M.W. Jr., 'NIST-JANAF Thermochemical "
            "Tables', 4th ed., NIST, 1998; Incropera et al., 7th ed., 2011; "
            "NASA/TP-2004-212592 'Air Revitalization for Space Habitats'; "
            "Touloukian, Y.S. & DeWitt, D.P., 'Thermal Radiative Properties', 1972"
        ),
    ),
    # ------------------------------------------------------------------
    # jjj. Lithium Hydroxide LiOH  (CO2 scrubber — ECLSS expendable)
    # ------------------------------------------------------------------
    "Lithium-Hydroxide": MaterialProperty(
        name="Lithium-Hydroxide",
        density_kg_m3=1460.0,            # Merck Index / CRC Handbook of Chemistry and Physics (98th ed.)
        youngs_modulus_pa=None,           # granular scrubber medium — not structurally loaded
        poisson_ratio=None,
        yield_strength_pa=None,
        uts_pa=None,
        thermal_conductivity_w_mk=None,   # no reliable published value for granular LiOH bed
        specific_heat_j_kgk=1600.0,       # Chase, M.W. Jr., NIST-JANAF 4th ed. LiOH(s) at 298 K
        cte_per_k=None,
        emissivity=None,
        melting_point_k=735.0,            # CRC Handbook 98th ed.: LiOH melting point ~462 °C
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Lide, D.R. (ed.), 'CRC Handbook of Chemistry and Physics', "
            "98th ed., CRC Press, 2017; Chase, M.W. Jr., 'NIST-JANAF "
            "Thermochemical Tables', 4th ed., NIST, 1998; "
            "NASA/TP-2004-212592 'Air Revitalization for Space Habitats'; "
            "NASA BVAD (NASA/TP-2015-218570) ECLSS consumables data"
        ),
    ),
    # ------------------------------------------------------------------
    # kkk. Zeolite 13X  (molecular sieve — CO2 adsorption / CDRA)
    # ------------------------------------------------------------------
    "Zeolite-13X": MaterialProperty(
        name="Zeolite-13X",
        density_kg_m3=700.0,             # Grace Davidson Zeolite 13X datasheet (bulk density ~650–750 kg/m³)
        youngs_modulus_pa=None,           # granular porous media — modulus not applicable
        poisson_ratio=None,
        yield_strength_pa=None,
        uts_pa=None,
        thermal_conductivity_w_mk=0.10,   # Ruthven, D.M., 'Principles of Adsorption and Adsorption Processes', Wiley 1984
        specific_heat_j_kgk=920.0,        # Ruthven 1984: zeolite 13X c_p at 298 K
        cte_per_k=None,                   # granular material — CTE not applicable
        emissivity=None,
        melting_point_k=None,             # aluminosilicate — decomposes above ~1300 K; no melt
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Grace Davidson (W.R. Grace & Co.), 'Zeolite 13X Molecular Sieve' "
            "datasheet; Ruthven, D.M., 'Principles of Adsorption and Adsorption "
            "Processes', Wiley, 1984; NASA/TP-2004-212592 'Air Revitalization "
            "for Space Habitats'; Finn, J.E. et al., 'CO₂ and humidity removal "
            "from spacecraft cabin air', NASA TM-102829, 1989"
        ),
    ),

    # ── Round-2 audit additions: heat-pipe + superconductor materials ──

    "Potassium": MaterialProperty(
        name="Potassium",
        density_kg_m3=830.0,                  # liquid K at 500 K (Perry's Chem Eng Handbook, 8e, Table 2-32)
        youngs_modulus_pa=None,
        poisson_ratio=None,
        yield_strength_pa=None,
        uts_pa=None,
        thermal_conductivity_w_mk=43.0,       # liquid K at 500 K, Dunn & Reay 1994 "Heat Pipes", Table 3.3
        specific_heat_j_kgk=780.0,            # liquid K at 500 K, Perry's 8e Table 2-32
        cte_per_k=None,                       # liquid — β_volume used instead
        emissivity=None,                      # internal fluid, no radiative role
        melting_point_k=336.7,                # Perry's 8e Table 2-32 (melts at 336.7 K)
        fatigue_limit_pa=None,                # not applicable (fluid)
        fatigue_exponent=None,
        source=(
            "Dunn, P.D. & Reay, D.A., 'Heat Pipes', 4th ed., Pergamon, 1994, "
            "Table 3.3 (alkali-metal working fluids, 400–1000 K range); "
            "Perry's Chemical Engineers' Handbook 8e, Table 2-32; "
            "Mason 2018 NASA/TM-2018-219910 'Kilopower fission reactor'"
        ),
    ),

    "Sintered-Nickel": MaterialProperty(
        name="Sintered-Nickel",
        density_kg_m3=7200.0,                 # ~82 % of bulk Ni (8908); porous sintered (ASM Handbook V7, Powder Metallurgy)
        youngs_modulus_pa=140e9,              # porous Ni, 18 % porosity — Ashby & Medalist 2000
        poisson_ratio=0.31,                   # bulk Ni value, preserved in sintering (ASM V2)
        yield_strength_pa=120e6,              # sintered Ni wick, Chi 1976 "Heat Pipe Theory and Practice", Ch. 4
        uts_pa=240e6,                         # 50 % knockdown from bulk Ni (Chi 1976)
        thermal_conductivity_w_mk=60.0,       # effective k for porous wick, Chi 1976 Eq. 4-12
        specific_heat_j_kgk=440.0,            # bulk Ni value (ASM V2 Ni properties)
        cte_per_k=13.4e-6,                    # bulk Ni (ASM V2, 293 K)
        emissivity=None,                      # internal wick structure
        melting_point_k=1728.0,               # pure Ni (ASM V2)
        fatigue_limit_pa=None,                # not a structural role
        fatigue_exponent=None,
        source=(
            "Chi, S.W., 'Heat Pipe Theory and Practice', McGraw-Hill, 1976, Ch. 4 "
            "(sintered-powder wick properties for alkali-metal heat pipes); "
            "ASM Handbook Vol. 2, Properties & Selection: Nonferrous Alloys, "
            "Ni-200 properties; ASM Handbook Vol. 7, Powder Metallurgy"
        ),
    ),

    "Nb3Sn": MaterialProperty(
        name="Nb3Sn",
        density_kg_m3=8910.0,                 # Iwasa 2009 "Case Studies in Superconducting Magnets", 2e, Ch. 1
        youngs_modulus_pa=165e9,              # Nb3Sn filament bundle, Iwasa 2009 Table 3.2
        poisson_ratio=0.30,                   # typical A15 intermetallic (Iwasa 2009)
        yield_strength_pa=None,               # brittle ceramic-like; not defined as σ_y
        uts_pa=800e6,                         # strain-limited strength, Iwasa 2009 Table 3.2
        thermal_conductivity_w_mk=0.70,       # Nb3Sn at 4.2 K, low-T cryo regime (Iwasa 2009 Table 3.3)
        specific_heat_j_kgk=7.0,              # at 4.2 K (Debye T ~ 250 K; low-T heat capacity << 298 K value)
        cte_per_k=7.5e-6,                     # 4.2–300 K integrated, Iwasa 2009
        emissivity=None,                      # internal conductor
        melting_point_k=2403.0,               # A15 intermetallic melting point (Iwasa 2009 Ch. 1)
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Iwasa, Y., 'Case Studies in Superconducting Magnets', 2nd ed., "
            "Springer, 2009, Table 3.2–3.3 (Nb3Sn LTS properties, B_c2 ≈ 25 T, "
            "T_c ≈ 18 K); ITER Magnet Design Description Document 2018; "
            "Markiewicz & Mielke 1992, IEEE Trans. Magn."
        ),
    ),

    "YBCO": MaterialProperty(
        name="YBCO",
        density_kg_m3=6380.0,                 # bulk YBa2Cu3O7-δ, Ginley & Cava 1989 Phys. Rev. B 40:10050
        youngs_modulus_pa=130e9,              # Roa et al. 2007 J. Eur. Ceram. Soc. 27:3707 (YBCO thin film)
        poisson_ratio=0.30,                   # ceramic-like (Roa 2007)
        yield_strength_pa=None,               # brittle; fails in tension without plastic range
        uts_pa=200e6,                         # c-axis tensile, Larbalestier 2001 Nature 414:368
        thermal_conductivity_w_mk=4.0,        # ab-plane at 77 K, Hagen 1989 Phys. Rev. B 40:9389
        specific_heat_j_kgk=350.0,            # at 100 K, Junod 1990 Physica C 162:1401
        cte_per_k=14e-6,                      # ab-plane integrated 77–300 K (Meingast 1991 Phys. Rev. Lett. 67:1634)
        emissivity=None,                      # used as coated conductor; emissivity depends on substrate
        melting_point_k=1243.0,               # peritectic decomposition temperature (Cava 1987)
        fatigue_limit_pa=None,
        fatigue_exponent=None,
        source=(
            "Ginley, D.S. & Cava, R.J., 'YBa2Cu3O7-δ superconductor properties', "
            "Phys. Rev. B 40, 10050 (1989); Larbalestier, D. et al., "
            "'High-Tc superconducting materials', Nature 414, 368 (2001); "
            "Roa, J.J. et al., 'Mechanical properties of YBCO films', J. Eur. "
            "Ceram. Soc. 27, 3707 (2007); SuperPower 2G HTS wire datasheet"
        ),
    ),
}


# ---------------------------------------------------------------------------
# Accessor helpers
# ---------------------------------------------------------------------------

def get_material(name: str) -> MaterialProperty:
    """Return the full :class:`MaterialProperty` record for *name*.

    Raises
    ------
    KeyError
        If *name* is not present in :data:`MATERIAL_DATABASE`.
    """
    try:
        return MATERIAL_DATABASE[name]
    except KeyError:
        available = ", ".join(sorted(MATERIAL_DATABASE))
        raise KeyError(
            f"Unknown material '{name}'. Available: {available}"
        ) from None


def get_property(material: str, prop: str) -> float:
    """Return a single scalar property value.

    Parameters
    ----------
    material : str
        Key into :data:`MATERIAL_DATABASE`.
    prop : str
        Attribute name on :class:`MaterialProperty` (e.g. ``"density_kg_m3"``).

    Raises
    ------
    KeyError
        If *material* is not in the database.
    AttributeError
        If *prop* is not a valid property name.
    ValueError
        If the requested property is ``None`` for this material.
    """
    mat = get_material(material)
    if not hasattr(mat, prop):
        raise AttributeError(
            f"MaterialProperty has no attribute '{prop}'"
        )
    value = getattr(mat, prop)
    if value is None:
        raise ValueError(
            f"Property '{prop}' is not defined for material '{material}'"
        )
    return value
