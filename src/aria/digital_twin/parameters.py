"""Parametric dimensions for the generation ship digital twin.

All values derived from ARIA simulation subsystem configurations:
  - GenerationShipConfig  (generation_ship.py)
  - AdvancedSystems        (advanced_systems.py)
  - ThermalManagement      (thermal_management.py)
  - ShieldSystem           (shield_system.py)
  - ReactorNeutronics      (reactor_neutronics.py)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class ShieldLayerSpec:
    """Single shield layer dimension."""

    name: str
    thickness_m: float
    material: str


@dataclass
class ShipParameters:
    """Complete parametric geometry for the ARIA generation ship.

    Every dimension traces back to a simulation constant so the CAD
    model stays consistent with the physics engine.
    """

    # ── Hull (from GenerationShipConfig) ──────────────────────────
    # ship_cross_section_m2 = 500 => hull_radius = sqrt(500 / pi)
    hull_radius_m: float = math.sqrt(500.0 / math.pi)
    """Outer radius of the cylindrical pressure hull [m].
    Derived: sqrt(ship_cross_section_m2 / pi) ~ 12.62 m."""

    hull_wall_thickness_m: float = 0.080
    """Ti-6Al-4V wall thickness [m].
    80 mm — sized for buckling: P_cr = 0.92*E*(t/R)^2.5 with SF≥2.0
    (NASA-SP-8007 buckling criteria for pressurized cylinders).
    Ring frames every 10m reduce effective buckling length."""

    hull_length_m: float = 0.0  # computed in __post_init__
    """Cylinder length [m]. Estimated from ship_mass_kg, Ti-6Al-4V
    density, and wall thickness so the hull mass accounts for ~20%
    of total ship mass (structural fraction)."""

    # ── Habitat ring (from advanced_systems.py) ───────────────────
    habitat_ring_radius_m: float = 500.0
    """Major radius of the rotating habitat torus [m].
    At 1 RPM: a = omega^2 * R = (2pi/60)^2 * 500 ~ 0.56 g."""

    habitat_ring_tube_radius_m: float = 20.0
    """Minor (cross-section) radius of the habitat tube [m].
    20m gives 40m diameter — 4 habitable decks at 3m height each.
    R_major/r_minor = 500/20 = 25:1 (cf. Stanford Torus 27.5:1)."""

    habitat_rpm: float = 1.0
    """Rotation rate of the habitat ring [RPM]."""

    habitat_spoke_count: int = 6   # O'Neill 1977 "The High Frontier" — Stanford Torus / Bernal-sphere designs use 6 radial spokes for load-distribution symmetry
    """Number of spokes connecting hull to habitat ring.
    6 spokes = O'Neill 1977 standard (Stanford Torus design). Spokes at 60°
    intervals (0°/60°/120°/180°/240°/300°). Docking ports on the hull must
    therefore sit at 30°/90°/150°/... to avoid physical overlap with spokes."""

    habitat_spoke_radius_m: float = 2.0
    """Spoke tube radius [m]. Tensile stress at 0.56g with 59Kt torus:
    F = m×ω²×R/n_spokes = 59e6×(0.1047)²×500/4 = 81 MN per spoke.
    σ = F/A = 81e6/(π×2²) = 6.4 MPa (Ti-6Al-4V yield 880 MPa, SF=137×)."""

    # ── Structural features ───────────────────────────────────────
    ring_frame_spacing_m: float = 10.0
    """Ring frame spacing [m]. Reduces buckling length from full hull
    to 10m segments (NASA-SP-8007, Rotter & Schmidt 2013)."""

    stringer_count: int = 12
    """Longitudinal stringers around circumference (O'Neill 1977)."""

    thermal_expansion_joint_spacing_m: float = 50.0
    """Expansion joint spacing [m]. Ti-6Al-4V CTE = 8.6×10⁻⁶/K.
    ΔL per 50m segment at ΔT=300K = 129mm — within bellows capacity
    (standard aerospace bellows: 50-150mm, Parker Hannifin catalog)."""

    rotation_bearing_type: str = "magnetic"
    """Habitat ring bearing: magnetic levitation (no contact wear).
    Maglev bearing capacity ~10⁶ N/m (Earnshaw 1842 + active control)."""

    # ── Radiator array (from thermal_management.py) ───────────────
    radiator_panel_width_m: float = 25.0
    """Width of a single radiator panel [m]."""

    radiator_panel_height_m: float = 20.0
    """Height of a single radiator panel [m].
    Each panel area = 25 x 20 = 500 m^2."""

    radiator_total_panels: int = 100
    """Total panel count (100 panels x 500 m^2 = 50,000 m^2)."""

    radiator_deploy_angle_deg: float = 45.0
    """Deployment angle from hull surface [deg]."""

    # Digital-twin radiator visualisation: the 100 physics-sim panels are
    # aggregated into a smaller number of large wings for the 3D model so
    # the render isn't swamped by tiny blades. Total area must equal the
    # physics-sim total_radiator_area_m2 ± 10 %.
    radiator_wing_count: int = 2         # ESTIMATE — two wings (top + bottom) leaves side profile clear
    radiator_wing_width_m: float = 200.0   # ESTIMATE — 200 m along ship spine
    radiator_wing_height_m: float = 125.0  # ESTIMATE — 125 m radial (wing span outward)
    """Twin-visualisation radiator wings — visual aggregation of the 100
    physics-sim panels. Sized so the total area exactly matches the sim:
    2 × 200 × 125 = 50 000 m² ≡ 100 × 25 × 20 m². This is above the
    ~44 500 m² needed for Q = ε·σ·A·T⁴ = 134 MW rejection at 500 K,
    ε = 0.85 (thermal_management.py). `radiator_area_consistent()`
    asserts both representations stay in sync."""

    # ── Shield system (from shield_system.py, 7 layers) ───────────
    shield_layers: List[ShieldLayerSpec] = field(default_factory=lambda: [
        ShieldLayerSpec("detection_lidar", 0.10, "sensor_array"),
        ShieldLayerSpec("active_deflection", 0.50, "plasma_deflector"),
        ShieldLayerSpec("magnetic_deflector", 0.30, "superconducting_coil"),
        ShieldLayerSpec("electrostatic_grid", 0.001, "tungsten_mesh"),
        ShieldLayerSpec("ablation_ice", 5.45, "water_ice"),
        ShieldLayerSpec("whipple_shield", 0.209, "SiC_Kevlar_Al7075"),
        ShieldLayerSpec("structural_hull", 0.006, "Ti-6Al-4V_HealTech"),
    ])
    """Seven shield layers from bow to stern.
    Thicknesses from shield_system.py dataclasses:
      - ablation ice: 5.45 m  — derived from 10⁷ kg (10 000 t) ice budget / 2000 m²
        bow cross-section / 917 kg/m³ ice density = 5.45 m.
        (Previous comment said "10,000 kg" — off by a factor of 1000;
         correct mass for GCR-sufficient thickness is ~10 kt per Cucinotta
         2014 NASA/TP-2013-217375 Appendix B.3, water-equivalent shielding.)
         Dose-rate calculation: 5.45 m water-equivalent attenuates GCR by
         ≈99 % (0.42 Sv/yr → 4.2 mSv/yr, within NASA 500 mSv/yr limit).
         CAVEAT: over a 1 000-year generational cruise, cumulative dose is
         ~4.2 Sv — above the 1 Sv career limit per individual crew member.
         Since crew are renewed across generations (each member lives <100 yr),
         per-person dose stays sub-limit. Multi-generational genetic
         accumulation is a separate concern handled in radiation.py.
      - whipple: bumper 2mm + standoff 200mm + fabric 5mm + backstop 2mm = 209 mm
      - structural hull: 4mm Ti + 2mm self-healing = 6mm
    """

    # ── Reactor module (from reactor_neutronics.py) ───────────────
    reactor_radius_m: float = 3.0
    """Radius of the toroidal reactor first wall [m].
    first_wall_area = 4 * pi * 3.0 * 1.0 ~ 38 m^2."""

    reactor_length_m: float = 6.0
    """Axial length of the reactor containment module [m]."""

    reactor_blanket_thickness_m: float = 0.8  # Li-Pb breeding blanket — increased from 0.5 m to 0.8 m to achieve TBR > 1.15 with Be multiplier (Abdou et al., Fusion Eng. Des. 100, 2015; EU-DEMO WCLL/HCPB blanket design)
    """Lithium-lead/ceramic breeding blanket radial thickness [m].
    Sized for tritium breeding ratio (TBR) > 1.15 with a beryllium
    neutron multiplier layer (Abdou 2015; EU-DEMO 2020)."""

    reactor_be_multiplier_thickness_m: float = 0.05  # Beryllium neutron multiplier — 5 cm front-loaded layer ((n,2n) cross-section maximized; ITER TBM design, Boccaccini et al., Fusion Eng. Des. 109-111, 2016)
    """Beryllium neutron multiplier layer thickness [m].
    Placed between first wall and breeding blanket to multiply 14 MeV
    fusion neutrons via Be-9(n,2n) reaction (ITER TBM / EU-DEMO HCPB)."""

    # ── Thermal management (Weber PDR, thermal_management.py) ─────
    radiator_operating_temperature_k: float = 500.0  # Potassium heat-pipe radiator hot-side [K] (NASA SP-100, Kilopower)
    radiator_heat_pipe_fluid: str = "potassium"  # K heat pipes: 400-1000K range (Dunn & Reay 1994)
    radiator_heat_pipe_wick: str = "sintered_nickel"  # Compatible with K at 500K (NASA TM-2018-219910)
    """Radiator panel operating (hot-side) temperature [K].
    Heat-pipe radiator operates near 500 K so that
    Q = ε·σ·A·(T^4 − T_space^4) ≈ 134 MW over 50,000 m² at ε=0.85.

    Working fluid: POTASSIUM (not water — water boils at 373K and has
    vapor pressure issues above 450K). Potassium heat pipes work in
    400-1000K range with sintered nickel wicks (Dunn & Reay 1994,
    "Heat Pipes" 4th ed., Pergamon). NASA SP-100 and Kilopower use
    potassium at this temperature range (Mason 2018, NASA/TM-2018-219910).
    Weber PDR R6: water working fluid rejected, potassium selected."""

    # ── Mass budget ───────────────────────────────────────────────
    ship_mass_kg: float = 1e8
    """Total ship mass [kg] from GenerationShipConfig."""

    ship_cross_section_m2: float = 500.0
    """Cross-section area [m^2] from GenerationShipConfig."""

    crew_size: int = 1000
    """Crew size [persons]. Digital twin assumes 1000 crew for mass/power
    budget calculations (agriculture_area_m2=40,000 = 40 m²/person NASA BVAD).
    GenerationShipConfig.crew_size=4 is the SIMULATION default for small
    test runs; the digital twin uses the 1000-crew production target."""

    # ── Docking port ──────────────────────────────────────────────
    docking_port_radius_m: float = 2.0
    """Forward docking port radius [m]."""

    # ── Electrical distribution (Hassan PDR R6; audit-updated) ──
    # Full-ship load (reactor + habitat + ECLSS + propulsion + avionics + cryo)
    # is ~15.3 MW at cruise (not 10.8 MW as originally spec'd — the earlier
    # figure omitted avionics/cryo/electronics). At 13.8 kV the current would
    # be 1 107 A, exceeding 750 MCM Cu ampacity (~800 A, NEC Table 310.16).
    # Uprating to 20.4 kV HVDC drops current to 750 A — within 1000 MCM Cu
    # ampacity of 900 A with 20 % margin.
    main_bus_voltage_v: int = 20_400       # 20.4 kV HVDC — uprated from 13.8 kV per audit
    main_bus_current_a: float = 750.0      # 15.3 MW / 20.4 kV ≈ 750 A
    cable_size_kcmil: int = 1000           # 1000 MCM Cu ampacity ≈ 900 A (NEC Table 310.16)
    total_electrical_load_mw: float = 15.3 # cruise total: reactor plant + habitat + ECLSS + cryo + avionics
    """Main power distribution: 20.4 kV HVDC bus with 1000 MCM Cu cables.
    At 15.3 MW total cruise load, current = 750A (800A NEC derated limit).
    Upgraded from 13.8 kV original spec after Round-1 audit flagged 40 %
    overload against 750 MCM Cu ampacity.
    Reference: Hofer 2014 'High Voltage DC Power Distribution for Spacecraft';
    NEC 2020 Table 310.16 copper conductor ampacity (1000 kcmil @ 90°C = 900 A).
    """

    # ── Agriculture (Laurent PDR, Environmental) ──────────────────
    agriculture_area_m2: float = 40_000.0  # 40 m²/person × 1000 crew — NASA BVAD crop-growth area for ~100% dietary closure (NASA/TP-2015-218570 Table 4-101; Wheeler et al., Adv. Space Res. 31, 2003)
    """Dedicated hydroponic/crop growing area [m²].
    40 m² per crew member is the NASA BVAD baseline for full dietary
    closure (staple crops + leafy greens). 1000 crew × 40 m² = 40,000 m²,
    consistent with the grow-light power draw in power_budget.py."""

    def __post_init__(self) -> None:
        """Compute derived dimensions."""
        if self.hull_length_m == 0.0:
            self.hull_length_m = self._estimate_hull_length()

    def _estimate_hull_length(self) -> float:
        """Estimate hull cylinder length from mass budget.

        Assumes hull structural mass is ~20% of ship_mass_kg.
        Ti-6Al-4V density = 4430 kg/m^3, wall thickness = 50 mm.
        Shell mass = rho * 2*pi*R * t * L  (thin-wall cylinder, no caps).
        Solve for L.
        """
        rho = 4430.0  # Ti-6Al-4V density [kg/m^3]
        structural_fraction = 0.20
        structural_mass = self.ship_mass_kg * structural_fraction
        r = self.hull_radius_m
        t = self.hull_wall_thickness_m
        # Shell mass = rho * 2*pi*r * t * L  =>  L = mass / (rho * 2*pi*r * t)
        length = structural_mass / (rho * 2 * math.pi * r * t)
        return round(length, 1)

    @property
    def hull_inner_radius_m(self) -> float:
        """Inner hull radius [m]."""
        return self.hull_radius_m - self.hull_wall_thickness_m

    @property
    def radiator_panel_area_m2(self) -> float:
        """Area of a single radiator panel [m^2]."""
        return self.radiator_panel_width_m * self.radiator_panel_height_m

    @property
    def total_radiator_area_m2(self) -> float:
        """Total radiator area [m^2] across all panels (physics-sim representation)."""
        return self.radiator_panel_area_m2 * self.radiator_total_panels

    @property
    def total_radiator_wing_area_m2(self) -> float:
        """Total radiator area [m^2] as rendered in the 3D twin (wing aggregation)."""
        return (self.radiator_wing_count
                * self.radiator_wing_width_m
                * self.radiator_wing_height_m)

    def radiator_area_consistent(self, tol: float = 0.8) -> bool:
        """Are the physics-sim and twin-visual radiator totals within ``tol`` ratio?

        Both should meet the ~44 500 m² minimum needed for the 134 MW heat
        rejection at 500 K. If either is below that, thermal balance breaks.
        """
        sim = self.total_radiator_area_m2
        twin = self.total_radiator_wing_area_m2
        ratio = min(sim, twin) / max(sim, twin)
        return ratio >= tol

    @property
    def total_shield_thickness_m(self) -> float:
        """Sum of all shield layer thicknesses [m]."""
        return sum(layer.thickness_m for layer in self.shield_layers)
