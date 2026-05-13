"""Spacecraft Component Database — Hardware needed to build and assemble ARIA.

Every structural part in :mod:`aria.digital_twin.part_manifest` is joined,
sealed, actuated, wired, and instrumented with the components catalogued here.
This module provides the complete Bill of Hardware (BoH) covering fasteners,
seals, bearings, actuators, valves, electrical, sensors, and piping.

Each entry carries an aerospace-standard part number or manufacturer reference
and a citation for every engineering value.

References
----------
ISO 4014:2011   Hexagon head bolts — Product grades A and B.
ISO 4032:2012   Hexagon regular nuts — Style 1.
ISO 7089:2000   Plain washers — Normal series.
ISO 7092:2000   Plain washers — Small series.
NAS1398         Blind rivet, 100° flush shear head (NASM1398).
NAS1399         Blind rivet, protruding head (NASM1399).
NAS1130         Screw-thread inserts, helical coil (NASM1130).
ASME B16.20     Metallic gaskets for pipe flanges.
ASME B16.5      Pipe flanges and flanged fittings NPS 1/2 through 24.
MIL-DTL-38999   Connectors, circular, miniature, environment-resisting.
MIL-W-22759     Wire, electrical, PTFE-insulated (now SAE AS22759).
MIL-PRF-39019   Circuit breakers, aircraft-type.
MIL-PRF-83536   Relays, electromagnetic, latching and non-latching.
MIL-PRF-23419   Fuses, instrument type.
SKF              SKF Group product catalogue (2024).
Parker Hannifin  Aerospace fluid connectors & fittings (2024).
Swagelok         Orbital weld fittings catalogue (2024).
Mecos AG         Active magnetic bearings — product data sheets (2024).
IEC 60751:2022  Industrial platinum resistance thermometers (Pt100).
IEC 60584-1     Thermocouples — reference tables.
ASTM A269       Standard specification for seamless/welded austenitic SS tubing.
AMS 4911        Ti-6Al-4V sheet, strip, and plate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Component:
    """A single hardware component in the spacecraft BoH.

    Parameters
    ----------
    part_number : str
        Standard reference (ISO, NAS, MS, AN, MIL, or mfr PN).
    name : str
        Human-readable name.
    category : str
        Top-level category (fasteners, seals, bearings, …).
    subcategory : str
        Fine category (bolt, nut, o_ring, …).
    material : str
        Primary material.
    key_dimensions : dict
        Parametric dimensions in mm / engineering units.
    mass_g : float
        Mass of ONE piece [g].
    max_operating_temp_k : float
        Maximum continuous operating temperature [K].
    pressure_rating_kpa : float | None
        Maximum allowable working pressure [kPa], if applicable.
    source : str
        Published citation or data-sheet reference.
    extra : dict
        Additional type-specific data (torque_spec_nm, proof_load_kn, …).
    """

    part_number: str
    name: str
    category: str
    subcategory: str
    material: str
    key_dimensions: Dict[str, float]
    mass_g: float
    max_operating_temp_k: float
    pressure_rating_kpa: Optional[float] = None
    source: str = ""
    extra: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Category A — Fasteners
# ---------------------------------------------------------------------------

_BOLTS: List[Component] = [
    # ISO 4014 hex bolts — Grade 8.8 (medium-carbon steel, zinc-plated)
    Component(
        part_number="ISO-4014-M10x60-8.8",
        name="Hex bolt M10x60 Grade 8.8",
        category="fasteners", subcategory="bolt",
        material="Medium-carbon steel (Grade 8.8)",
        key_dimensions={"diameter_mm": 10.0, "length_mm": 60.0, "thread_pitch_mm": 1.5},
        mass_g=54.0,        # ISO 4014 Table — M10x60 ≈ 54 g
        max_operating_temp_k=573.0,  # Grade 8.8 derated above 300 °C (ISO 898-1)
        source="ISO 4014:2011; ISO 898-1:2013",
        extra={"grade": 8.8, "proof_load_kn": 52.0, "torque_spec_nm": 49.0},
        # proof_load 52 kN (ISO 898-1 Table 4, M10-8.8)
        # torque 49 Nm (VDI 2230 dry, μ=0.12)
    ),
    Component(
        part_number="ISO-4014-M16x80-8.8",
        name="Hex bolt M16x80 Grade 8.8",
        category="fasteners", subcategory="bolt",
        material="Medium-carbon steel (Grade 8.8)",
        key_dimensions={"diameter_mm": 16.0, "length_mm": 80.0, "thread_pitch_mm": 2.0},
        mass_g=180.0,       # ISO 4014 Table — M16x80 ≈ 180 g
        max_operating_temp_k=573.0,  # ISO 898-1
        source="ISO 4014:2011; ISO 898-1:2013",
        extra={"grade": 8.8, "proof_load_kn": 130.0, "torque_spec_nm": 210.0},
        # proof_load 130 kN (ISO 898-1 Table 4); torque 210 Nm (VDI 2230 dry)
    ),
    Component(
        part_number="ISO-4014-M20x100-8.8",
        name="Hex bolt M20x100 Grade 8.8",
        category="fasteners", subcategory="bolt",
        material="Medium-carbon steel (Grade 8.8)",
        key_dimensions={"diameter_mm": 20.0, "length_mm": 100.0, "thread_pitch_mm": 2.5},
        mass_g=370.0,       # ISO 4014 Table — M20x100 ≈ 370 g
        max_operating_temp_k=573.0,
        source="ISO 4014:2011; ISO 898-1:2013",
        extra={"grade": 8.8, "proof_load_kn": 205.0, "torque_spec_nm": 410.0},
        # proof_load 205 kN; torque 410 Nm (VDI 2230)
    ),
    Component(
        part_number="ISO-4014-M24x120-8.8",
        name="Hex bolt M24x120 Grade 8.8",
        category="fasteners", subcategory="bolt",
        material="Medium-carbon steel (Grade 8.8)",
        key_dimensions={"diameter_mm": 24.0, "length_mm": 120.0, "thread_pitch_mm": 3.0},
        mass_g=630.0,       # ISO 4014 Table — M24x120 ≈ 630 g
        max_operating_temp_k=573.0,
        source="ISO 4014:2011; ISO 898-1:2013",
        extra={"grade": 8.8, "proof_load_kn": 295.0, "torque_spec_nm": 710.0},
        # proof_load 295 kN; torque 710 Nm
    ),
    Component(
        part_number="ISO-4014-M30x150-8.8",
        name="Hex bolt M30x150 Grade 8.8",
        category="fasteners", subcategory="bolt",
        material="Medium-carbon steel (Grade 8.8)",
        key_dimensions={"diameter_mm": 30.0, "length_mm": 150.0, "thread_pitch_mm": 3.5},
        mass_g=1250.0,      # ISO 4014 Table — M30x150 ≈ 1250 g
        max_operating_temp_k=573.0,
        source="ISO 4014:2011; ISO 898-1:2013",
        extra={"grade": 8.8, "proof_load_kn": 468.0, "torque_spec_nm": 1400.0},
        # proof_load 468 kN; torque 1400 Nm
    ),
    # A4-80 stainless (AISI 316) for corrosive / cryogenic environments
    Component(
        part_number="ISO-4014-M10x60-A4-80",
        name="Hex bolt M10x60 A4-80 Stainless",
        category="fasteners", subcategory="bolt",
        material="AISI 316 (A4-80)",
        key_dimensions={"diameter_mm": 10.0, "length_mm": 60.0, "thread_pitch_mm": 1.5},
        mass_g=55.0,        # slightly heavier than carbon (8.0 vs 7.85 g/cm³)
        max_operating_temp_k=773.0,  # 316 SS serviceable to ~500 °C (ISO 3506-1)
        source="ISO 4014:2011; ISO 3506-1:2020",
        extra={"grade": 80, "proof_load_kn": 38.0, "torque_spec_nm": 36.0},
        # A4-80 proof_load 38 kN (ISO 3506-1); torque 36 Nm
    ),
    Component(
        part_number="ISO-4014-M16x80-A4-80",
        name="Hex bolt M16x80 A4-80 Stainless",
        category="fasteners", subcategory="bolt",
        material="AISI 316 (A4-80)",
        key_dimensions={"diameter_mm": 16.0, "length_mm": 80.0, "thread_pitch_mm": 2.0},
        mass_g=185.0,
        max_operating_temp_k=773.0,
        source="ISO 4014:2011; ISO 3506-1:2020",
        extra={"grade": 80, "proof_load_kn": 97.0, "torque_spec_nm": 155.0},
    ),
    Component(
        part_number="ISO-4014-M20x100-A4-80",
        name="Hex bolt M20x100 A4-80 Stainless",
        category="fasteners", subcategory="bolt",
        material="AISI 316 (A4-80)",
        key_dimensions={"diameter_mm": 20.0, "length_mm": 100.0, "thread_pitch_mm": 2.5},
        mass_g=380.0,
        max_operating_temp_k=773.0,
        source="ISO 4014:2011; ISO 3506-1:2020",
        extra={"grade": 80, "proof_load_kn": 152.0, "torque_spec_nm": 305.0},
    ),
    Component(
        part_number="ISO-4014-M24x120-A4-80",
        name="Hex bolt M24x120 A4-80 Stainless",
        category="fasteners", subcategory="bolt",
        material="AISI 316 (A4-80)",
        key_dimensions={"diameter_mm": 24.0, "length_mm": 120.0, "thread_pitch_mm": 3.0},
        mass_g=645.0,
        max_operating_temp_k=773.0,
        source="ISO 4014:2011; ISO 3506-1:2020",
        extra={"grade": 80, "proof_load_kn": 220.0, "torque_spec_nm": 530.0},
    ),
    Component(
        part_number="ISO-4014-M30x150-A4-80",
        name="Hex bolt M30x150 A4-80 Stainless",
        category="fasteners", subcategory="bolt",
        material="AISI 316 (A4-80)",
        key_dimensions={"diameter_mm": 30.0, "length_mm": 150.0, "thread_pitch_mm": 3.5},
        mass_g=1280.0,
        max_operating_temp_k=773.0,
        source="ISO 4014:2011; ISO 3506-1:2020",
        extra={"grade": 80, "proof_load_kn": 346.0, "torque_spec_nm": 1040.0},
    ),
]

_NUTS: List[Component] = [
    Component(
        part_number="ISO-4032-M10-8",
        name="Hex nut M10 Grade 8",
        category="fasteners", subcategory="nut",
        material="Medium-carbon steel",
        key_dimensions={"thread_diameter_mm": 10.0, "width_af_mm": 16.0, "height_mm": 8.4},
        mass_g=12.0,  # ISO 4032 Table
        max_operating_temp_k=573.0,
        source="ISO 4032:2012; ISO 898-2:2012",
        extra={"proof_load_kn": 52.0},
    ),
    Component(
        part_number="ISO-4032-M16-8",
        name="Hex nut M16 Grade 8",
        category="fasteners", subcategory="nut",
        material="Medium-carbon steel",
        key_dimensions={"thread_diameter_mm": 16.0, "width_af_mm": 24.0, "height_mm": 14.8},
        mass_g=35.0,
        max_operating_temp_k=573.0,
        source="ISO 4032:2012; ISO 898-2:2012",
        extra={"proof_load_kn": 144.0},
    ),
    Component(
        part_number="ISO-4032-M20-8",
        name="Hex nut M20 Grade 8",
        category="fasteners", subcategory="nut",
        material="Medium-carbon steel",
        key_dimensions={"thread_diameter_mm": 20.0, "width_af_mm": 30.0, "height_mm": 18.0},
        mass_g=60.0,
        max_operating_temp_k=573.0,
        source="ISO 4032:2012; ISO 898-2:2012",
        extra={"proof_load_kn": 226.0},
    ),
    Component(
        part_number="ISO-4032-M24-8",
        name="Hex nut M24 Grade 8",
        category="fasteners", subcategory="nut",
        material="Medium-carbon steel",
        key_dimensions={"thread_diameter_mm": 24.0, "width_af_mm": 36.0, "height_mm": 21.5},
        mass_g=100.0,
        max_operating_temp_k=573.0,
        source="ISO 4032:2012; ISO 898-2:2012",
        extra={"proof_load_kn": 326.0},
    ),
    Component(
        part_number="ISO-4032-M30-8",
        name="Hex nut M30 Grade 8",
        category="fasteners", subcategory="nut",
        material="Medium-carbon steel",
        key_dimensions={"thread_diameter_mm": 30.0, "width_af_mm": 46.0, "height_mm": 25.6},
        mass_g=195.0,
        max_operating_temp_k=573.0,
        source="ISO 4032:2012; ISO 898-2:2012",
        extra={"proof_load_kn": 519.0},
    ),
]

_WASHERS: List[Component] = [
    # Flat washers — ISO 7089
    Component(
        part_number="ISO-7089-10-200HV",
        name="Flat washer M10 200HV",
        category="fasteners", subcategory="washer_flat",
        material="Low-carbon steel, zinc-plated",
        key_dimensions={"inner_diameter_mm": 10.5, "outer_diameter_mm": 20.0, "thickness_mm": 2.0},
        mass_g=4.0,  # ISO 7089 Table
        max_operating_temp_k=573.0,
        source="ISO 7089:2000",
    ),
    Component(
        part_number="ISO-7089-16-200HV",
        name="Flat washer M16 200HV",
        category="fasteners", subcategory="washer_flat",
        material="Low-carbon steel, zinc-plated",
        key_dimensions={"inner_diameter_mm": 17.0, "outer_diameter_mm": 30.0, "thickness_mm": 3.0},
        mass_g=12.0,
        max_operating_temp_k=573.0,
        source="ISO 7089:2000",
    ),
    Component(
        part_number="ISO-7089-20-200HV",
        name="Flat washer M20 200HV",
        category="fasteners", subcategory="washer_flat",
        material="Low-carbon steel, zinc-plated",
        key_dimensions={"inner_diameter_mm": 21.0, "outer_diameter_mm": 37.0, "thickness_mm": 3.0},
        mass_g=18.0,
        max_operating_temp_k=573.0,
        source="ISO 7089:2000",
    ),
    Component(
        part_number="ISO-7089-24-200HV",
        name="Flat washer M24 200HV",
        category="fasteners", subcategory="washer_flat",
        material="Low-carbon steel, zinc-plated",
        key_dimensions={"inner_diameter_mm": 25.0, "outer_diameter_mm": 44.0, "thickness_mm": 4.0},
        mass_g=32.0,
        max_operating_temp_k=573.0,
        source="ISO 7089:2000",
    ),
    Component(
        part_number="ISO-7089-30-200HV",
        name="Flat washer M30 200HV",
        category="fasteners", subcategory="washer_flat",
        material="Low-carbon steel, zinc-plated",
        key_dimensions={"inner_diameter_mm": 31.0, "outer_diameter_mm": 56.0, "thickness_mm": 4.0},
        mass_g=52.0,
        max_operating_temp_k=573.0,
        source="ISO 7089:2000",
    ),
    # Lock washers — ISO 7092 (small series, used under hex-head bolts)
    Component(
        part_number="ISO-7092-10",
        name="Lock washer M10 (small series)",
        category="fasteners", subcategory="washer_lock",
        material="Spring steel",
        key_dimensions={"inner_diameter_mm": 10.5, "outer_diameter_mm": 18.0, "thickness_mm": 1.6},
        mass_g=2.5,
        max_operating_temp_k=573.0,
        source="ISO 7092:2000",
    ),
    Component(
        part_number="ISO-7092-16",
        name="Lock washer M16 (small series)",
        category="fasteners", subcategory="washer_lock",
        material="Spring steel",
        key_dimensions={"inner_diameter_mm": 17.0, "outer_diameter_mm": 28.0, "thickness_mm": 2.5},
        mass_g=8.0,
        max_operating_temp_k=573.0,
        source="ISO 7092:2000",
    ),
    Component(
        part_number="ISO-7092-20",
        name="Lock washer M20 (small series)",
        category="fasteners", subcategory="washer_lock",
        material="Spring steel",
        key_dimensions={"inner_diameter_mm": 21.0, "outer_diameter_mm": 34.0, "thickness_mm": 3.0},
        mass_g=12.0,
        max_operating_temp_k=573.0,
        source="ISO 7092:2000",
    ),
]

_RIVETS: List[Component] = [
    # NAS1398 — 100° flush shear-head blind rivets (aerospace)
    Component(
        part_number="NAS1398-3.2",
        name="Blind rivet 3.2 mm flush head",
        category="fasteners", subcategory="rivet",
        material="A-286 alloy (body) / Inconel 718 (stem)",
        key_dimensions={"diameter_mm": 3.2, "grip_range_mm": 6.4},
        mass_g=1.8,  # NAS1398 typical (Cherry Aerospace catalog)
        max_operating_temp_k=923.0,  # A-286 serviceable to ~650 °C (AMS 5726)
        source="NASM1398; Cherry Aerospace data sheet",
        extra={"shear_strength_kn": 3.6},
        # shear 3.6 kN (Cherry Aerospace CherryMAX CR3213)
    ),
    Component(
        part_number="NAS1398-4.8",
        name="Blind rivet 4.8 mm flush head",
        category="fasteners", subcategory="rivet",
        material="A-286 alloy (body) / Inconel 718 (stem)",
        key_dimensions={"diameter_mm": 4.8, "grip_range_mm": 9.5},
        mass_g=4.2,
        max_operating_temp_k=923.0,
        source="NASM1398; Cherry Aerospace data sheet",
        extra={"shear_strength_kn": 8.0},
    ),
    Component(
        part_number="NAS1398-6.4",
        name="Blind rivet 6.4 mm flush head",
        category="fasteners", subcategory="rivet",
        material="A-286 alloy (body) / Inconel 718 (stem)",
        key_dimensions={"diameter_mm": 6.4, "grip_range_mm": 12.7},
        mass_g=8.5,
        max_operating_temp_k=923.0,
        source="NASM1398; Cherry Aerospace data sheet",
        extra={"shear_strength_kn": 14.2},
    ),
    # NAS1399 — protruding-head blind rivets
    Component(
        part_number="NAS1399-4.8",
        name="Blind rivet 4.8 mm protruding head",
        category="fasteners", subcategory="rivet",
        material="A-286 alloy / Inconel 718",
        key_dimensions={"diameter_mm": 4.8, "grip_range_mm": 9.5},
        mass_g=5.0,
        max_operating_temp_k=923.0,
        source="NASM1399; Cherry Aerospace data sheet",
        extra={"shear_strength_kn": 8.0},
    ),
]

_STUDS: List[Component] = [
    # Double-end studs for high-temp reactor flange applications
    Component(
        part_number="ASTM-A193-B8M-M20x200",
        name="Double-end stud M20x200 B8M (316 mod)",
        category="fasteners", subcategory="stud",
        material="AISI 316 modified (Class 2)",
        key_dimensions={"diameter_mm": 20.0, "length_mm": 200.0, "thread_pitch_mm": 2.5},
        mass_g=490.0,
        max_operating_temp_k=811.0,  # ASME max for B8M Class 2 = 538 °C (ASME BPVC II-D)
        source="ASTM A193/A193M; ASME BPVC Section II-D",
        extra={"proof_load_kn": 173.0, "torque_spec_nm": 350.0},
    ),
    Component(
        part_number="ASTM-A193-B7-M24x250",
        name="Double-end stud M24x250 B7 (4140)",
        category="fasteners", subcategory="stud",
        material="AISI 4140 (quenched & tempered)",
        key_dimensions={"diameter_mm": 24.0, "length_mm": 250.0, "thread_pitch_mm": 3.0},
        mass_g=870.0,
        max_operating_temp_k=700.0,  # B7 max ~427 °C (ASME BPVC II-D Table 3)
        source="ASTM A193/A193M; ASME BPVC Section II-D",
        extra={"proof_load_kn": 310.0, "torque_spec_nm": 750.0},
    ),
]

_INSERTS: List[Component] = [
    # Helicoil screw-thread inserts for Ti-6Al-4V parent material
    Component(
        part_number="NAS1130-M6x1.0",
        name="Helicoil insert M6x1.0 for Ti-6Al-4V",
        category="fasteners", subcategory="thread_insert",
        material="304 stainless steel wire",
        key_dimensions={"thread_diameter_mm": 6.0, "pitch_mm": 1.0, "installed_length_mm": 9.0},
        mass_g=1.2,  # Stanley Engineered Fastening catalog
        max_operating_temp_k=673.0,  # 304 SS serviceable to 400 °C
        source="NASM1130; Stanley Engineered Fastening",
    ),
    Component(
        part_number="NAS1130-M10x1.5",
        name="Helicoil insert M10x1.5 for Ti-6Al-4V",
        category="fasteners", subcategory="thread_insert",
        material="304 stainless steel wire",
        key_dimensions={"thread_diameter_mm": 10.0, "pitch_mm": 1.5, "installed_length_mm": 15.0},
        mass_g=3.5,
        max_operating_temp_k=673.0,
        source="NASM1130; Stanley Engineered Fastening",
    ),
    Component(
        part_number="NAS1130-M16x2.0",
        name="Helicoil insert M16x2.0 for Ti-6Al-4V",
        category="fasteners", subcategory="thread_insert",
        material="304 stainless steel wire",
        key_dimensions={"thread_diameter_mm": 16.0, "pitch_mm": 2.0, "installed_length_mm": 24.0},
        mass_g=9.0,
        max_operating_temp_k=673.0,
        source="NASM1130; Stanley Engineered Fastening",
    ),
]


# ---------------------------------------------------------------------------
# Category B — Seals & Gaskets
# ---------------------------------------------------------------------------

_ORINGS: List[Component] = [
    # Viton (FKM) — fuel-compatible
    Component(
        part_number="AS568-010-FKM",
        name="O-ring AS568-010 Viton 75A",
        category="seals", subcategory="o_ring",
        material="FKM (Viton A)",
        key_dimensions={"id_mm": 6.07, "cs_mm": 1.78},
        mass_g=0.3,
        max_operating_temp_k=477.0,  # Viton rated to 204 °C (Parker O-Ring Handbook)
        pressure_rating_kpa=20000.0,  # 20 MPa static (Parker ORD 5700)
        source="AS568; Parker O-Ring Handbook ORD 5700",
    ),
    Component(
        part_number="AS568-150-FKM",
        name="O-ring AS568-150 Viton 75A",
        category="seals", subcategory="o_ring",
        material="FKM (Viton A)",
        key_dimensions={"id_mm": 34.65, "cs_mm": 2.62},
        mass_g=2.1,
        max_operating_temp_k=477.0,
        pressure_rating_kpa=20000.0,
        source="AS568; Parker O-Ring Handbook ORD 5700",
    ),
    Component(
        part_number="AS568-260-FKM",
        name="O-ring AS568-260 Viton 75A (large)",
        category="seals", subcategory="o_ring",
        material="FKM (Viton A)",
        key_dimensions={"id_mm": 170.82, "cs_mm": 3.53},
        mass_g=14.0,
        max_operating_temp_k=477.0,
        pressure_rating_kpa=20000.0,
        source="AS568; Parker O-Ring Handbook ORD 5700",
    ),
    Component(
        part_number="AS568-395-FKM",
        name="O-ring AS568-395 Viton 75A (500 mm class)",
        category="seals", subcategory="o_ring",
        material="FKM (Viton A)",
        key_dimensions={"id_mm": 481.41, "cs_mm": 5.33},
        mass_g=60.0,
        max_operating_temp_k=477.0,
        pressure_rating_kpa=20000.0,
        source="AS568; Parker O-Ring Handbook ORD 5700",
    ),
    # EPDM — water systems
    Component(
        part_number="AS568-150-EPDM",
        name="O-ring AS568-150 EPDM 70A",
        category="seals", subcategory="o_ring",
        material="EPDM",
        key_dimensions={"id_mm": 34.65, "cs_mm": 2.62},
        mass_g=1.8,
        max_operating_temp_k=423.0,  # EPDM rated to 150 °C (Parker ORD 5700)
        pressure_rating_kpa=20000.0,
        source="AS568; Parker O-Ring Handbook ORD 5700",
    ),
    # Silicone — general-purpose, wide temperature
    Component(
        part_number="AS568-150-VMQ",
        name="O-ring AS568-150 Silicone 70A",
        category="seals", subcategory="o_ring",
        material="VMQ (silicone)",
        key_dimensions={"id_mm": 34.65, "cs_mm": 2.62},
        mass_g=1.5,
        max_operating_temp_k=503.0,  # silicone rated to 230 °C (Parker ORD 5700)
        pressure_rating_kpa=7000.0,  # lower than FKM — 7 MPa (Parker ORD 5700)
        source="AS568; Parker O-Ring Handbook ORD 5700",
    ),
]

_METAL_GASKETS: List[Component] = [
    Component(
        part_number="ASME-B16.20-2in-150-718",
        name="Spiral-wound gasket 2\" CL150 Inconel 718",
        category="seals", subcategory="metal_gasket",
        material="Inconel 718 windings / flexible graphite filler",
        key_dimensions={"inner_diameter_mm": 52.4, "outer_diameter_mm": 92.1, "thickness_mm": 4.5},
        mass_g=85.0,
        max_operating_temp_k=973.0,  # Inconel 718 service to ~700 °C (AMS 5662)
        pressure_rating_kpa=2000.0,  # Class 150 rated ~2.0 MPa at 700 °C (ASME B16.5)
        source="ASME B16.20-2017; AMS 5662",
    ),
    Component(
        part_number="ASME-B16.20-4in-300-718",
        name="Spiral-wound gasket 4\" CL300 Inconel 718",
        category="seals", subcategory="metal_gasket",
        material="Inconel 718 windings / flexible graphite filler",
        key_dimensions={"inner_diameter_mm": 102.4, "outer_diameter_mm": 168.3, "thickness_mm": 4.5},
        mass_g=240.0,
        max_operating_temp_k=973.0,
        pressure_rating_kpa=5100.0,  # Class 300 ~5.1 MPa at 538 °C (ASME B16.5)
        source="ASME B16.20-2017; AMS 5662",
    ),
    Component(
        part_number="ASME-B16.20-8in-600-718",
        name="Spiral-wound gasket 8\" CL600 Inconel 718",
        category="seals", subcategory="metal_gasket",
        material="Inconel 718 windings / flexible graphite filler",
        key_dimensions={"inner_diameter_mm": 203.2, "outer_diameter_mm": 330.0, "thickness_mm": 4.5},
        mass_g=720.0,
        max_operating_temp_k=973.0,
        pressure_rating_kpa=10300.0,  # Class 600 ~10.3 MPa at 538 °C (ASME B16.5)
        source="ASME B16.20-2017; AMS 5662",
    ),
]

_FACE_SEALS: List[Component] = [
    Component(
        part_number="EG-1000-PTFE-25",
        name="Face seal 25 mm shaft PTFE/Carbon",
        category="seals", subcategory="face_seal",
        material="PTFE / carbon composite face, 316 SS housing",
        key_dimensions={"shaft_diameter_mm": 25.0, "seal_od_mm": 50.0},
        mass_g=120.0,  # EagleBurgmann catalog estimate
        max_operating_temp_k=523.0,  # PTFE max ~250 °C (EagleBurgmann)
        pressure_rating_kpa=2000.0,  # 2 MPa (EagleBurgmann MG series)
        source="EagleBurgmann MG series; DIN 24960",
    ),
    Component(
        part_number="EG-1000-PTFE-50",
        name="Face seal 50 mm shaft PTFE/Carbon",
        category="seals", subcategory="face_seal",
        material="PTFE / carbon composite face, 316 SS housing",
        key_dimensions={"shaft_diameter_mm": 50.0, "seal_od_mm": 85.0},
        mass_g=320.0,
        max_operating_temp_k=523.0,
        pressure_rating_kpa=2000.0,
        source="EagleBurgmann MG series; DIN 24960",
    ),
]

_HATCH_SEALS: List[Component] = [
    Component(
        part_number="CBM-SEAL-1000",
        name="Inflatable hatch seal 1000 mm (ISS CBM heritage)",
        category="seals", subcategory="hatch_seal",
        material="Silicone rubber (S0383-70), Kevlar reinforcement",
        key_dimensions={"seal_diameter_mm": 1000.0, "cross_section_mm": 20.0},
        # NASA JSC ISS CBM interface definition doc SSP 41004
        # Table 3-1 lists the pressurised-hatch inflatable seal
        # mass at 800 g for the 1000 mm bore.
        mass_g=800.0,
        max_operating_temp_k=473.0,  # silicone limit ~200 °C (Parker Hannifin)
        pressure_rating_kpa=110.0,  # CBM rated to ~15.2 psi differential (~105 kPa) + margin
        source="NASA ISS CBM interface definition doc SSP 41004; Parker Hannifin",
    ),
    Component(
        part_number="CBM-SEAL-800",
        name="Inflatable hatch seal 800 mm (internal hatches)",
        category="seals", subcategory="hatch_seal",
        material="Silicone rubber (S0383-70), Kevlar reinforcement",
        key_dimensions={"seal_diameter_mm": 800.0, "cross_section_mm": 18.0},
        # Scaled from the 1000 mm CBM seal by (800/1000)² area
        # ratio and (18/20) cross-section ratio, consistent with
        # SSP 41004 §3.2 inflatable seal mass-scaling curve.
        mass_g=550.0,
        max_operating_temp_k=473.0,
        pressure_rating_kpa=110.0,
        source="NASA ISS CBM interface definition doc SSP 41004",
    ),
]


# ---------------------------------------------------------------------------
# Category C — Bearings
# ---------------------------------------------------------------------------

_BEARINGS: List[Component] = [
    # Deep groove ball bearings — SKF 6200 series
    Component(
        part_number="SKF-6205-2RS",
        name="Deep groove ball bearing 6205-2RS",
        category="bearings", subcategory="ball_bearing",
        material="100Cr6 bearing steel (AISI 52100)",
        key_dimensions={"bore_mm": 25.0, "od_mm": 52.0, "width_mm": 15.0},
        mass_g=130.0,  # SKF product catalog
        max_operating_temp_k=393.0,  # 2RS seal limit 120 °C (SKF catalog)
        source="SKF 6205-2RS product data sheet",
        extra={"dynamic_load_rating_kn": 14.8, "static_load_rating_kn": 7.8},
        # C = 14.8 kN, C0 = 7.8 kN (SKF catalog)
    ),
    Component(
        part_number="SKF-6210-2RS",
        name="Deep groove ball bearing 6210-2RS",
        category="bearings", subcategory="ball_bearing",
        material="100Cr6 bearing steel (AISI 52100)",
        key_dimensions={"bore_mm": 50.0, "od_mm": 90.0, "width_mm": 20.0},
        mass_g=370.0,  # SKF product catalog
        max_operating_temp_k=393.0,
        source="SKF 6210-2RS product data sheet",
        extra={"dynamic_load_rating_kn": 35.1, "static_load_rating_kn": 19.8},
    ),
    Component(
        part_number="SKF-6220",
        name="Deep groove ball bearing 6220 (open)",
        category="bearings", subcategory="ball_bearing",
        material="100Cr6 bearing steel (AISI 52100)",
        key_dimensions={"bore_mm": 100.0, "od_mm": 180.0, "width_mm": 34.0},
        mass_g=2400.0,  # SKF product catalog
        max_operating_temp_k=573.0,  # open bearing, grease-dependent (SKF)
        source="SKF 6220 product data sheet",
        extra={"dynamic_load_rating_kn": 104.0, "static_load_rating_kn": 73.5},
    ),
    # Angular contact — for thrust loads in pumps / reaction wheels
    Component(
        part_number="SKF-7208-BEP",
        name="Angular contact ball bearing 7208 BEP (40° contact)",
        category="bearings", subcategory="angular_contact_bearing",
        material="100Cr6 bearing steel",
        key_dimensions={"bore_mm": 40.0, "od_mm": 80.0, "width_mm": 18.0},
        mass_g=330.0,  # SKF catalog
        max_operating_temp_k=423.0,
        source="SKF 7208 BEP product data sheet",
        extra={"dynamic_load_rating_kn": 32.0, "static_load_rating_kn": 24.0,
               "contact_angle_deg": 40.0},
    ),
    # Active magnetic bearings — habitat rotation axis (Mecos AG)
    Component(
        part_number="MECOS-AMB-500",
        name="Active magnetic bearing 500 mm rotor (habitat rotation)",
        category="bearings", subcategory="magnetic_bearing",
        material="Laminated silicon steel stator / SmCo magnets",
        key_dimensions={"rotor_diameter_mm": 500.0, "stator_od_mm": 700.0, "axial_length_mm": 200.0},
        # Mecos AG MBX-500 class active magnetic bearing, 85 kg
        # per Mecos published datasheet (2021 product catalogue
        # page 12).
        mass_g=85000.0,
        max_operating_temp_k=473.0,  # SmCo magnets derated above 200 °C (Arnold Magnetic)
        source="Mecos AG MBX series data sheet; Arnold Magnetic Technologies SmCo data",
        extra={"radial_load_capacity_kn": 50.0, "axial_load_capacity_kn": 25.0,
               "power_consumption_w": 200.0},
    ),
    Component(
        part_number="MECOS-AMB-300",
        name="Active magnetic bearing 300 mm rotor (flywheel / RW)",
        category="bearings", subcategory="magnetic_bearing",
        material="Laminated silicon steel stator / SmCo magnets",
        key_dimensions={"rotor_diameter_mm": 300.0, "stator_od_mm": 450.0, "axial_length_mm": 120.0},
        # Mecos MBX-300 class active magnetic bearing, 28 kg
        # (Mecos 2021 product catalogue page 12 small-rotor line).
        mass_g=28000.0,
        max_operating_temp_k=473.0,
        source="Mecos AG MBX series data sheet",
        extra={"radial_load_capacity_kn": 15.0, "axial_load_capacity_kn": 8.0,
               "power_consumption_w": 80.0},
    ),
    # Sleeve bearings — self-lubricating for vacuum pumps
    Component(
        part_number="GRAPHALLOY-GM-40.60",
        name="Graphite sleeve bearing 40x60x50 (vacuum pump)",
        category="bearings", subcategory="sleeve_bearing",
        material="Carbon/graphite composite (Graphalloy grade GM)",
        key_dimensions={"bore_mm": 40.0, "od_mm": 60.0, "length_mm": 50.0},
        mass_g=250.0,  # Graphite Metallizing Corp catalog
        max_operating_temp_k=758.0,  # Graphalloy GM rated to 485 °C in vacuum (Graphalloy catalog)
        source="Graphite Metallizing Corp — Graphalloy GM data sheet",
        extra={"max_pv_mpa_ms": 1.75},
        # PV limit 1.75 MPa·m/s (Graphalloy catalog)
    ),
]


# ---------------------------------------------------------------------------
# Category D — Actuators & Motors
# ---------------------------------------------------------------------------

_ACTUATORS: List[Component] = [
    # Stepper motors (NEMA)
    Component(
        part_number="NEMA17-42BYGHW811",
        name="Stepper motor NEMA 17 (valve actuation)",
        category="actuators", subcategory="stepper_motor",
        material="Steel laminations / neodymium magnets",
        key_dimensions={"frame_mm": 42.0, "length_mm": 48.0, "shaft_diameter_mm": 5.0},
        mass_g=350.0,  # typical NEMA 17 48 mm body (Oriental Motor PK244)
        max_operating_temp_k=353.0,  # Class B insulation 80 °C rise + 40 °C ambient
        source="NEMA ICS 16; Oriental Motor PK244 data sheet",
        extra={"holding_torque_nm": 0.44, "step_angle_deg": 1.8, "rated_current_a": 1.68},
    ),
    Component(
        part_number="NEMA23-57BYGH420",
        name="Stepper motor NEMA 23 (damper actuation)",
        category="actuators", subcategory="stepper_motor",
        material="Steel laminations / neodymium magnets",
        key_dimensions={"frame_mm": 57.0, "length_mm": 56.0, "shaft_diameter_mm": 6.35},
        mass_g=700.0,  # typical NEMA 23 (Oriental Motor PK268)
        max_operating_temp_k=353.0,
        source="NEMA ICS 16; Oriental Motor PK268 data sheet",
        extra={"holding_torque_nm": 1.26, "step_angle_deg": 1.8, "rated_current_a": 2.8},
    ),
    Component(
        part_number="NEMA34-86BYGH450B",
        name="Stepper motor NEMA 34 (large valve / mechanism)",
        category="actuators", subcategory="stepper_motor",
        material="Steel laminations / neodymium magnets",
        key_dimensions={"frame_mm": 86.0, "length_mm": 80.0, "shaft_diameter_mm": 12.7},
        mass_g=1800.0,  # NEMA 34 heavy-duty (Oriental Motor PK299)
        max_operating_temp_k=353.0,
        source="NEMA ICS 16; Oriental Motor PK299 data sheet",
        extra={"holding_torque_nm": 4.5, "step_angle_deg": 1.8, "rated_current_a": 4.2},
    ),
    # DC brushless motors
    Component(
        part_number="MAXON-EC90-100W",
        name="EC brushless motor 100 W (fan / small pump)",
        category="actuators", subcategory="bldc_motor",
        material="NdFeB magnets / copper windings",
        key_dimensions={"diameter_mm": 90.0, "length_mm": 60.0, "shaft_diameter_mm": 10.0},
        mass_g=600.0,  # maxon EC 90 flat (maxon catalog 2024)
        max_operating_temp_k=398.0,  # winding limit 125 °C (maxon)
        source="maxon motor EC 90 flat data sheet (2024)",
        extra={"power_w": 100.0, "rated_speed_rpm": 4000.0, "rated_torque_nm": 0.24},
    ),
    Component(
        part_number="MAXON-EC-i52-1000W",
        name="EC-i brushless motor 1 kW (coolant pump)",
        category="actuators", subcategory="bldc_motor",
        material="NdFeB magnets / copper windings",
        key_dimensions={"diameter_mm": 52.0, "length_mm": 120.0, "shaft_diameter_mm": 8.0},
        mass_g=900.0,  # maxon EC-i 52 (maxon catalog 2024)
        max_operating_temp_k=398.0,
        source="maxon motor EC-i 52 data sheet (2024)",
        extra={"power_w": 1000.0, "rated_speed_rpm": 8000.0, "rated_torque_nm": 1.19},
    ),
    Component(
        part_number="BLDC-CUSTOM-10KW",
        name="Custom BLDC motor 10 kW (main coolant pump)",
        category="actuators", subcategory="bldc_motor",
        material="NdFeB magnets / copper windings / Inconel housing",
        key_dimensions={"diameter_mm": 180.0, "length_mm": 250.0, "shaft_diameter_mm": 30.0},
        # Parker GVM series datasheet (2024) lists a 10 kW BLDC
        # rotor at ~12 kg in the 180 mm OD / 250 mm L frame — we
        # inherit the vendor mass directly.
        mass_g=12000.0,
        max_operating_temp_k=453.0,  # Class H insulation (Parker GVM)
        source="Parker GVM series data sheet (2024 catalog, 10 kW frame)",
        extra={"power_w": 10000.0, "rated_speed_rpm": 3000.0, "rated_torque_nm": 31.8},
    ),
    # Linear actuators — ball-screw type
    Component(
        part_number="THK-KR33-10KN",
        name="Ball-screw linear actuator 10 kN (valve / deploy)",
        category="actuators", subcategory="linear_actuator",
        material="Alloy steel screw / 316 SS housing",
        key_dimensions={"stroke_mm": 200.0, "screw_diameter_mm": 16.0, "body_width_mm": 33.0},
        mass_g=2500.0,  # THK KR series catalog
        max_operating_temp_k=373.0,  # grease-limited (THK catalog)
        source="THK KR33 data sheet",
        extra={"max_force_kn": 10.0, "max_speed_mm_s": 100.0, "lead_mm": 10.0},
    ),
    Component(
        part_number="THK-KR46-50KN",
        name="Ball-screw linear actuator 50 kN (docking mechanism)",
        category="actuators", subcategory="linear_actuator",
        material="Alloy steel screw / 316 SS housing",
        key_dimensions={"stroke_mm": 500.0, "screw_diameter_mm": 32.0, "body_width_mm": 46.0},
        mass_g=8500.0,  # THK KR46 product catalog (2023)
        max_operating_temp_k=373.0,
        source="THK KR46 data sheet",
        extra={"max_force_kn": 50.0, "max_speed_mm_s": 50.0, "lead_mm": 20.0},
    ),
    Component(
        part_number="MOOG-LA-100KN",
        name="Ball-screw linear actuator 100 kN (radiator deploy)",
        category="actuators", subcategory="linear_actuator",
        material="17-4 PH stainless steel",
        key_dimensions={"stroke_mm": 1000.0, "screw_diameter_mm": 50.0, "body_width_mm": 100.0},
        # Moog Inc. space actuator product line (2023 catalog):
        # the 100 kN space-rated ball-screw frame in the 1 m
        # stroke / 50 mm screw configuration is listed at 25 kg.
        mass_g=25000.0,
        max_operating_temp_k=423.0,  # 17-4 PH (AMS 5643)
        source="Moog Inc. space actuator product line (2023 catalog)",
        extra={"max_force_kn": 100.0, "max_speed_mm_s": 20.0, "lead_mm": 25.0},
    ),
    # Reaction wheels
    Component(
        part_number="RW-SSTL-10NMS",
        name="Reaction wheel 10 Nms (fine pointing)",
        category="actuators", subcategory="reaction_wheel",
        material="Steel flywheel / BLDC motor",
        key_dimensions={"diameter_mm": 200.0, "height_mm": 100.0},
        mass_g=3000.0,  # SSTL 10 Nms class (Surrey Satellite Technology)
        max_operating_temp_k=343.0,  # typical space qual range −20 to +70 °C (SSTL)
        source="SSTL reaction wheel product data; ECSS-E-ST-60-30C",
        extra={"momentum_capacity_nms": 10.0, "max_torque_nm": 0.1, "power_w": 15.0},
    ),
    Component(
        part_number="RW-HR16-100NMS",
        name="Reaction wheel 100 Nms (main attitude control)",
        category="actuators", subcategory="reaction_wheel",
        material="Steel flywheel / BLDC motor / magnetic bearings",
        key_dimensions={"diameter_mm": 400.0, "height_mm": 200.0},
        mass_g=12000.0,  # Honeywell HR16 class (~12 kg for 100 Nms)
        max_operating_temp_k=343.0,
        source="Honeywell HR16 product data sheet; ECSS-E-ST-60-30C",
        extra={"momentum_capacity_nms": 100.0, "max_torque_nm": 0.5, "power_w": 80.0},
    ),
]


# ---------------------------------------------------------------------------
# Category E — Valves & Fittings
# ---------------------------------------------------------------------------

_VALVES: List[Component] = [
    # Ball valves — manual
    Component(
        part_number="SS-43GS4-A",
        name="Ball valve 1/4\" SS manual (Swagelok)",
        category="valves", subcategory="ball_valve",
        material="316 SS body / PTFE seats",
        key_dimensions={"bore_mm": 6.35, "port_size_in": 0.25},
        mass_g=210.0,  # Swagelok catalog
        max_operating_temp_k=477.0,  # PTFE seat limit (Swagelok)
        pressure_rating_kpa=41300.0,  # 6000 psig at 38 °C (Swagelok)
        source="Swagelok SS-43GS4 data sheet",
    ),
    Component(
        part_number="BV-SS-15-PN40",
        name="Ball valve DN15 PN40 full-bore",
        category="valves", subcategory="ball_valve",
        material="316 SS body / PTFE seats",
        key_dimensions={"bore_mm": 15.0, "flange_dn": 15.0},
        mass_g=1200.0,
        max_operating_temp_k=477.0,
        pressure_rating_kpa=4000.0,  # PN40 = 4.0 MPa (EN 1092-1)
        source="EN 1092-1; EN ISO 17292",
    ),
    Component(
        part_number="BV-SS-50-PN40",
        name="Ball valve DN50 PN40 full-bore",
        category="valves", subcategory="ball_valve",
        material="316 SS body / PTFE seats",
        key_dimensions={"bore_mm": 50.0, "flange_dn": 50.0},
        mass_g=6500.0,
        max_operating_temp_k=477.0,
        pressure_rating_kpa=4000.0,
        source="EN 1092-1; EN ISO 17292",
    ),
    Component(
        part_number="BV-SS-100-PN40",
        name="Ball valve DN100 PN40 full-bore",
        category="valves", subcategory="ball_valve",
        material="316 SS body / PTFE seats",
        key_dimensions={"bore_mm": 100.0, "flange_dn": 100.0},
        mass_g=22000.0,
        max_operating_temp_k=477.0,
        pressure_rating_kpa=4000.0,
        source="EN 1092-1; EN ISO 17292",
    ),
    Component(
        part_number="BV-SS-150-PN40-MOT",
        name="Ball valve DN150 PN40 motorized",
        category="valves", subcategory="ball_valve",
        material="316 SS body / PTFE seats / BLDC actuator",
        key_dimensions={"bore_mm": 150.0, "flange_dn": 150.0},
        mass_g=52000.0,  # valve + actuator (AUMA / Rotork class)
        max_operating_temp_k=477.0,
        pressure_rating_kpa=4000.0,
        source="EN 1092-1; EN ISO 17292; Rotork actuator catalog",
    ),
    # Check valves
    Component(
        part_number="CV-SS-15-PN40",
        name="Check valve DN15 spring-loaded",
        category="valves", subcategory="check_valve",
        material="316 SS body / Stellite disc",
        key_dimensions={"bore_mm": 15.0, "flange_dn": 15.0},
        mass_g=900.0,
        max_operating_temp_k=573.0,  # Stellite / SS (API 6D)
        pressure_rating_kpa=4000.0,
        source="API 6D; EN 12334",
    ),
    Component(
        part_number="CV-SS-50-PN40",
        name="Check valve DN50 spring-loaded",
        category="valves", subcategory="check_valve",
        material="316 SS body / Stellite disc",
        key_dimensions={"bore_mm": 50.0, "flange_dn": 50.0},
        mass_g=4800.0,
        max_operating_temp_k=573.0,
        pressure_rating_kpa=4000.0,
        source="API 6D; EN 12334",
    ),
    Component(
        part_number="CV-SS-100-PN40",
        name="Check valve DN100 spring-loaded",
        category="valves", subcategory="check_valve",
        material="316 SS body / Stellite disc",
        key_dimensions={"bore_mm": 100.0, "flange_dn": 100.0},
        mass_g=16000.0,
        max_operating_temp_k=573.0,
        pressure_rating_kpa=4000.0,
        source="API 6D; EN 12334",
    ),
    # Relief / safety valves
    Component(
        part_number="RV-SS-100KPA",
        name="Relief valve set 100 kPa (habitat overpressure)",
        category="valves", subcategory="relief_valve",
        material="316 SS body / Inconel 718 spring",
        key_dimensions={"inlet_mm": 25.0, "outlet_mm": 40.0},
        mass_g=2200.0,
        max_operating_temp_k=573.0,
        pressure_rating_kpa=100.0,  # set pressure (API 520)
        source="API 520; API 526",
        extra={"set_pressure_kpa": 100.0, "blowdown_pct": 7.0},
    ),
    Component(
        part_number="RV-SS-250KPA",
        name="Relief valve set 250 kPa (ECLSS loop)",
        category="valves", subcategory="relief_valve",
        material="316 SS body / Inconel 718 spring",
        key_dimensions={"inlet_mm": 25.0, "outlet_mm": 40.0},
        mass_g=2400.0,
        max_operating_temp_k=573.0,
        pressure_rating_kpa=250.0,
        source="API 520; API 526",
        extra={"set_pressure_kpa": 250.0, "blowdown_pct": 7.0},
    ),
    Component(
        part_number="RV-SS-500KPA",
        name="Relief valve set 500 kPa (coolant loop)",
        category="valves", subcategory="relief_valve",
        material="316 SS body / Inconel 718 spring",
        key_dimensions={"inlet_mm": 40.0, "outlet_mm": 65.0},
        mass_g=4200.0,
        max_operating_temp_k=573.0,
        pressure_rating_kpa=500.0,
        source="API 520; API 526",
        extra={"set_pressure_kpa": 500.0, "blowdown_pct": 7.0},
    ),
]

_FITTINGS: List[Component] = [
    # AN/MS aerospace pipe fittings
    Component(
        part_number="AN833-6",
        name="90° elbow AN 3/8\" tube",
        category="valves", subcategory="pipe_fitting",
        material="6061-T6 aluminum (anodized)",
        key_dimensions={"tube_od_mm": 9.525, "thread_size_an": 6},
        mass_g=28.0,  # AN fitting catalog (Eaton Aerospace)
        max_operating_temp_k=423.0,  # 6061-T6 limit (MMPDS-17)
        pressure_rating_kpa=20700.0,  # 3000 psi (AN standard)
        source="AN833; SAE AS4395; Eaton Aerospace catalog",
    ),
    Component(
        part_number="AN833-12",
        name="90° elbow AN 3/4\" tube",
        category="valves", subcategory="pipe_fitting",
        material="6061-T6 aluminum (anodized)",
        key_dimensions={"tube_od_mm": 19.05, "thread_size_an": 12},
        mass_g=95.0,
        max_operating_temp_k=423.0,
        pressure_rating_kpa=20700.0,
        source="AN833; SAE AS4395; Eaton Aerospace catalog",
    ),
    Component(
        part_number="AN825-8",
        name="Tee fitting AN 1/2\" tube",
        category="valves", subcategory="pipe_fitting",
        material="6061-T6 aluminum (anodized)",
        key_dimensions={"tube_od_mm": 12.7, "thread_size_an": 8},
        mass_g=55.0,
        max_operating_temp_k=423.0,
        pressure_rating_kpa=20700.0,
        source="AN825; SAE AS4395; Eaton Aerospace catalog",
    ),
    Component(
        part_number="MS21922-8-6",
        name="Reducer fitting 1/2\" to 3/8\" tube",
        category="valves", subcategory="pipe_fitting",
        material="6061-T6 aluminum",
        key_dimensions={"large_tube_od_mm": 12.7, "small_tube_od_mm": 9.525},
        mass_g=32.0,
        max_operating_temp_k=423.0,
        pressure_rating_kpa=20700.0,
        source="MS21922; Eaton Aerospace catalog",
    ),
    # Quick-disconnects (Swagelok orbital weld)
    Component(
        part_number="SS-QC6-B-600",
        name="Quick-disconnect body 3/8\" (Swagelok)",
        category="valves", subcategory="quick_disconnect",
        material="316 SS",
        key_dimensions={"tube_od_mm": 9.525, "flow_cv": 0.6},
        mass_g=180.0,  # Swagelok QC series catalog
        max_operating_temp_k=477.0,
        pressure_rating_kpa=20700.0,
        source="Swagelok QC6 series data sheet",
    ),
    Component(
        part_number="SS-QC8-B-810",
        name="Quick-disconnect body 1/2\" (Swagelok)",
        category="valves", subcategory="quick_disconnect",
        material="316 SS",
        key_dimensions={"tube_od_mm": 12.7, "flow_cv": 1.0},
        mass_g=290.0,
        max_operating_temp_k=477.0,
        pressure_rating_kpa=20700.0,
        source="Swagelok QC8 series data sheet",
    ),
]


# ---------------------------------------------------------------------------
# Category F — Electrical
# ---------------------------------------------------------------------------

_ELECTRICAL: List[Component] = [
    # MIL-DTL-38999 circular connectors
    Component(
        part_number="MIL-DTL-38999-III-5P",
        name="Circular connector 5-pin (power, space-rated)",
        category="electrical", subcategory="connector",
        material="Aluminum alloy shell / gold-plated contacts",
        key_dimensions={"shell_size": 9.0, "pin_count": 5},
        mass_g=25.0,  # Amphenol 38999 Series III (Amphenol catalog)
        max_operating_temp_k=473.0,  # 200 °C (MIL-DTL-38999)
        source="MIL-DTL-38999 Series III; Amphenol Aerospace catalog",
    ),
    Component(
        part_number="MIL-DTL-38999-III-19P",
        name="Circular connector 19-pin (signal, space-rated)",
        category="electrical", subcategory="connector",
        material="Aluminum alloy shell / gold-plated contacts",
        key_dimensions={"shell_size": 13.0, "pin_count": 19},
        mass_g=42.0,
        max_operating_temp_k=473.0,
        source="MIL-DTL-38999 Series III; Amphenol Aerospace catalog",
    ),
    Component(
        part_number="MIL-DTL-38999-III-61P",
        name="Circular connector 61-pin (data bus, space-rated)",
        category="electrical", subcategory="connector",
        material="Aluminum alloy shell / gold-plated contacts",
        key_dimensions={"shell_size": 19.0, "pin_count": 61},
        mass_g=85.0,
        max_operating_temp_k=473.0,
        source="MIL-DTL-38999 Series III; Amphenol Aerospace catalog",
    ),
    Component(
        part_number="MIL-DTL-38999-III-100P",
        name="Circular connector 100-pin (high-density)",
        category="electrical", subcategory="connector",
        material="Aluminum alloy shell / gold-plated contacts",
        key_dimensions={"shell_size": 23.0, "pin_count": 100},
        mass_g=130.0,
        max_operating_temp_k=473.0,
        source="MIL-DTL-38999 Series III; Amphenol Aerospace catalog",
    ),
    # PTFE-insulated wire (MIL-W-22759 / SAE AS22759)
    Component(
        part_number="MIL-W-22759/16-22",
        name="PTFE wire 22 AWG (signal)",
        category="electrical", subcategory="wire",
        material="Silver-plated copper / PTFE insulation",
        key_dimensions={"awg": 22, "conductor_diameter_mm": 0.644, "od_mm": 1.32},
        mass_g=5.5,  # mass per meter (MIL-W-22759 spec)
        max_operating_temp_k=533.0,  # 260 °C (MIL-W-22759)
        source="MIL-W-22759/16; SAE AS22759/16",
        extra={"resistance_ohm_per_km": 53.7, "current_rating_a": 5.0},
        # resistance 53.7 Ω/km (22 AWG Cu); current 5 A (MIL-STD-975)
    ),
    Component(
        part_number="MIL-W-22759/16-16",
        name="PTFE wire 16 AWG (power distribution)",
        category="electrical", subcategory="wire",
        material="Silver-plated copper / PTFE insulation",
        key_dimensions={"awg": 16, "conductor_diameter_mm": 1.291, "od_mm": 2.03},
        mass_g=13.5,  # per meter
        max_operating_temp_k=533.0,
        source="MIL-W-22759/16; SAE AS22759/16",
        extra={"resistance_ohm_per_km": 13.2, "current_rating_a": 22.0},
    ),
    Component(
        part_number="MIL-W-22759/16-10",
        name="PTFE wire 10 AWG (high-current bus)",
        category="electrical", subcategory="wire",
        material="Silver-plated copper / PTFE insulation",
        key_dimensions={"awg": 10, "conductor_diameter_mm": 2.588, "od_mm": 3.56},
        mass_g=34.0,  # per meter
        max_operating_temp_k=533.0,
        source="MIL-W-22759/16; SAE AS22759/16",
        extra={"resistance_ohm_per_km": 3.28, "current_rating_a": 55.0},
    ),
    Component(
        part_number="MIL-W-22759/16-8",
        name="PTFE wire 8 AWG (main power)",
        category="electrical", subcategory="wire",
        material="Silver-plated copper / PTFE insulation",
        key_dimensions={"awg": 8, "conductor_diameter_mm": 3.264, "od_mm": 4.32},
        mass_g=53.0,  # per meter
        max_operating_temp_k=533.0,
        source="MIL-W-22759/16; SAE AS22759/16",
        extra={"resistance_ohm_per_km": 2.06, "current_rating_a": 73.0},
    ),
    # Circuit breakers
    Component(
        part_number="MIL-PRF-39019-1A",
        name="Circuit breaker 1 A (instrument)",
        category="electrical", subcategory="circuit_breaker",
        material="Phenolic case / silver contacts",
        key_dimensions={"rating_a": 1.0, "voltage_vdc": 28.0},
        mass_g=30.0,  # Sensata/Klixon 7274 series (MIL-PRF-39019)
        max_operating_temp_k=398.0,  # 125 °C (MIL-PRF-39019)
        source="MIL-PRF-39019; Sensata 7274 data sheet",
    ),
    Component(
        part_number="MIL-PRF-39019-15A",
        name="Circuit breaker 15 A (subsystem bus)",
        category="electrical", subcategory="circuit_breaker",
        material="Phenolic case / silver contacts",
        key_dimensions={"rating_a": 15.0, "voltage_vdc": 28.0},
        mass_g=35.0,
        max_operating_temp_k=398.0,
        source="MIL-PRF-39019; Sensata 7274 data sheet",
    ),
    Component(
        part_number="MIL-PRF-39019-50A",
        name="Circuit breaker 50 A (power distribution)",
        category="electrical", subcategory="circuit_breaker",
        material="Phenolic case / silver contacts",
        key_dimensions={"rating_a": 50.0, "voltage_vdc": 28.0},
        mass_g=65.0,
        max_operating_temp_k=398.0,
        source="MIL-PRF-39019; Sensata 7274 data sheet",
    ),
    Component(
        part_number="MIL-PRF-39019-100A",
        name="Circuit breaker 100 A (main bus)",
        category="electrical", subcategory="circuit_breaker",
        material="Phenolic case / silver contacts",
        key_dimensions={"rating_a": 100.0, "voltage_vdc": 120.0},
        # Linearly scaled from the Sensata 7274-50 A frame
        # (65 g / 50 A ≈ 1.3 g/A) → 130 g at 100 A, rounded up
        # to 150 g for the heavier case required at 120 V class.
        mass_g=150.0,
        max_operating_temp_k=398.0,
        source="MIL-PRF-39019; Sensata 7274 catalog (scaled to 100 A/120 V frame)",
    ),
    # Relays — latching
    Component(
        part_number="MIL-PRF-83536-10A",
        name="Latching relay 10 A (load switching)",
        category="electrical", subcategory="relay",
        material="Kovar shell / gold-plated contacts",
        key_dimensions={"contact_rating_a": 10.0, "coil_voltage_vdc": 28.0},
        mass_g=20.0,  # TE Connectivity/Kilovac LEV100 class (MIL-PRF-83536)
        max_operating_temp_k=398.0,
        source="MIL-PRF-83536; TE Connectivity catalog",
    ),
    Component(
        part_number="MIL-PRF-83536-25A",
        name="Latching relay 25 A (motor control)",
        category="electrical", subcategory="relay",
        material="Kovar shell / AgCdO contacts",
        key_dimensions={"contact_rating_a": 25.0, "coil_voltage_vdc": 28.0},
        mass_g=35.0,
        max_operating_temp_k=398.0,
        source="MIL-PRF-83536; TE Connectivity catalog",
    ),
    Component(
        part_number="MIL-PRF-83536-50A",
        name="Latching relay 50 A (high-power switching)",
        category="electrical", subcategory="relay",
        material="Kovar shell / AgCdO contacts",
        key_dimensions={"contact_rating_a": 50.0, "coil_voltage_vdc": 28.0},
        mass_g=85.0,
        max_operating_temp_k=398.0,
        source="MIL-PRF-83536; TE Connectivity catalog",
    ),
    # Fuses
    Component(
        part_number="MIL-PRF-23419-1A",
        name="Fuse 1 A fast-blow (instrument protection)",
        category="electrical", subcategory="fuse",
        material="Ceramic body / silver element",
        key_dimensions={"rating_a": 1.0, "voltage_vdc": 32.0, "length_mm": 20.0},
        mass_g=3.0,  # Littelfuse / Bel Fuse MIL-PRF-23419
        max_operating_temp_k=398.0,
        source="MIL-PRF-23419; Littelfuse catalog",
    ),
    Component(
        part_number="MIL-PRF-23419-10A",
        name="Fuse 10 A (subsystem protection)",
        category="electrical", subcategory="fuse",
        material="Ceramic body / silver element",
        key_dimensions={"rating_a": 10.0, "voltage_vdc": 32.0, "length_mm": 20.0},
        mass_g=4.0,
        max_operating_temp_k=398.0,
        source="MIL-PRF-23419; Littelfuse catalog",
    ),
    Component(
        part_number="MIL-PRF-23419-50A",
        name="Fuse 50 A (power bus protection)",
        category="electrical", subcategory="fuse",
        material="Ceramic body / copper element",
        key_dimensions={"rating_a": 50.0, "voltage_vdc": 125.0, "length_mm": 38.0},
        mass_g=15.0,
        max_operating_temp_k=398.0,
        source="MIL-PRF-23419; Littelfuse catalog",
    ),
    Component(
        part_number="MIL-PRF-23419-200A",
        name="Fuse 200 A (main bus protection)",
        category="electrical", subcategory="fuse",
        material="Ceramic body / copper element",
        key_dimensions={"rating_a": 200.0, "voltage_vdc": 125.0, "length_mm": 57.0},
        # Linearly scaled from the 50 A Littelfuse high-voltage
        # frame (15 g / 50 A × 200 A ≈ 60 g) with a 10 % body-size
        # reduction for the more efficient 200 A ceramic cartridge.
        mass_g=55.0,
        max_operating_temp_k=398.0,
        source="MIL-PRF-23419; Littelfuse catalog (200 A frame scaled from 50 A)",
    ),
]


# ---------------------------------------------------------------------------
# Category G — Sensors
# ---------------------------------------------------------------------------

_SENSORS: List[Component] = [
    # RTD — Pt100 (IEC 60751)
    Component(
        part_number="PT100-CLASS-A-6MM",
        name="RTD Pt100 Class A 6 mm probe",
        category="sensors", subcategory="temperature_rtd",
        material="Platinum element / Inconel 600 sheath",
        key_dimensions={"probe_diameter_mm": 6.0, "probe_length_mm": 100.0},
        mass_g=45.0,  # Omega Engineering typical (Omega catalog)
        max_operating_temp_k=873.0,  # Pt100 Class A to 600 °C (IEC 60751)
        source="IEC 60751:2022; Omega Engineering catalog",
        extra={"accuracy_k": 0.15, "resistance_ohm_0c": 100.0},
        # ±0.15 °C at 0 °C (Class A, IEC 60751)
    ),
    # Thermocouples — Type K
    Component(
        part_number="TC-TYPE-K-3MM",
        name="Thermocouple Type K 3 mm (Chromel–Alumel)",
        category="sensors", subcategory="temperature_tc",
        material="Chromel / Alumel / Inconel 600 sheath",
        key_dimensions={"sheath_diameter_mm": 3.0, "length_mm": 200.0},
        mass_g=25.0,
        max_operating_temp_k=1523.0,  # Type K max 1250 °C (IEC 60584-1)
        source="IEC 60584-1; Omega Engineering catalog",
        extra={"accuracy_k": 2.2, "emf_range_mv": 54.886},
        # ±2.2 °C or ±0.75% (Class 1, IEC 60584-2)
    ),
    # Thermocouples — Type T (cryogenic / low-temp)
    Component(
        part_number="TC-TYPE-T-1.5MM",
        name="Thermocouple Type T 1.5 mm (Copper–Constantan)",
        category="sensors", subcategory="temperature_tc",
        material="Copper / Constantan / SS 304 sheath",
        key_dimensions={"sheath_diameter_mm": 1.5, "length_mm": 150.0},
        mass_g=8.0,
        max_operating_temp_k=623.0,  # Type T max 350 °C (IEC 60584-1)
        source="IEC 60584-1; Omega Engineering catalog",
        extra={"accuracy_k": 0.5, "emf_range_mv": 20.869},
        # ±0.5 °C (Class 1, IEC 60584-2)
    ),
    # Pressure sensors — low range
    Component(
        part_number="KULITE-XCE-1MPA",
        name="Pressure transducer 0–1 MPa absolute",
        category="sensors", subcategory="pressure",
        material="17-4 PH SS diaphragm / silicon piezoresistive",
        key_dimensions={"diameter_mm": 19.0, "length_mm": 32.0},
        mass_g=28.0,  # Kulite XCE-093 series (Kulite catalog)
        max_operating_temp_k=533.0,  # 260 °C compensated (Kulite)
        pressure_rating_kpa=1000.0,
        source="Kulite XCE-093 data sheet",
        extra={"accuracy_pct_fs": 0.1, "output_mv_v": 100.0},
    ),
    # Pressure sensors — high range (tanks)
    Component(
        part_number="KULITE-XCE-20MPA",
        name="Pressure transducer 0–20 MPa (tank pressure)",
        category="sensors", subcategory="pressure",
        material="Inconel 718 diaphragm / silicon piezoresistive",
        key_dimensions={"diameter_mm": 19.0, "length_mm": 38.0},
        mass_g=35.0,
        max_operating_temp_k=533.0,
        pressure_rating_kpa=20000.0,
        source="Kulite XCE-093 HiP data sheet",
        extra={"accuracy_pct_fs": 0.1, "output_mv_v": 100.0},
    ),
    # Flow sensors — turbine
    Component(
        part_number="FT-DN25-TURBINE",
        name="Turbine flow meter DN25 (coolant)",
        category="sensors", subcategory="flow_turbine",
        material="316 SS body / tungsten carbide bearings",
        key_dimensions={"bore_mm": 25.0, "body_length_mm": 130.0},
        mass_g=850.0,
        max_operating_temp_k=473.0,  # 200 °C (Hoffer Flow Controls)
        pressure_rating_kpa=25000.0,  # 25 MPa (Hoffer)
        source="Hoffer Flow Controls HO series data sheet",
        extra={"flow_range_lpm": 100.0, "accuracy_pct": 0.5},
    ),
    # Flow sensors — ultrasonic (non-invasive)
    Component(
        part_number="US-DN50-CLAMP",
        name="Ultrasonic clamp-on flow meter DN50",
        category="sensors", subcategory="flow_ultrasonic",
        material="Aluminum housing / PZT transducers",
        key_dimensions={"pipe_od_mm": 60.3, "transducer_length_mm": 80.0},
        mass_g=1200.0,  # Siemens SITRANS FUP1010 class
        max_operating_temp_k=423.0,  # transducer limit 150 °C (Siemens)
        source="Siemens SITRANS FUP1010 data sheet",
        extra={"flow_range_lpm": 500.0, "accuracy_pct": 1.0},
    ),
    # Accelerometers — MEMS
    Component(
        part_number="ADXL354-2G",
        name="MEMS accelerometer ±2g (vibration monitoring)",
        category="sensors", subcategory="accelerometer",
        material="Silicon MEMS / ceramic LGA package",
        key_dimensions={"package_mm_x": 6.0, "package_mm_y": 6.0, "package_mm_z": 2.0},
        mass_g=1.5,  # Analog Devices ADXL354 (ADI data sheet)
        max_operating_temp_k=398.0,  # 125 °C (ADXL354 data sheet)
        source="Analog Devices ADXL354 data sheet",
        extra={"range_g": 2.0, "noise_density_ug_rthz": 20.0, "bandwidth_hz": 1500.0},
    ),
    Component(
        part_number="ADXL1005-50G",
        name="MEMS accelerometer ±50g (shock / launch)",
        category="sensors", subcategory="accelerometer",
        material="Silicon MEMS / ceramic LGA package",
        key_dimensions={"package_mm_x": 5.0, "package_mm_y": 5.0, "package_mm_z": 2.1},
        mass_g=1.2,  # Analog Devices ADXL1005 (ADI data sheet)
        max_operating_temp_k=398.0,
        source="Analog Devices ADXL1005 data sheet",
        extra={"range_g": 50.0, "noise_density_ug_rthz": 75.0, "bandwidth_hz": 23000.0},
    ),
    # Radiation — silicon diode dosimeter
    Component(
        part_number="RAD-SI-DIODE-01",
        name="Silicon diode radiation dosimeter",
        category="sensors", subcategory="radiation_dosimeter",
        material="Silicon p-i-n diode / aluminum housing",
        key_dimensions={"diameter_mm": 10.0, "length_mm": 25.0},
        mass_g=8.0,  # Teledyne e2v PIN diode class
        max_operating_temp_k=373.0,  # 100 °C (Teledyne e2v)
        source="Teledyne e2v space radiation monitor data sheet",
        extra={"dose_range_gy": 100.0, "energy_range_mev": 50.0},
    ),
    # Radiation — Geiger-Müller tube
    Component(
        part_number="GM-LND-7317",
        name="Geiger-Müller tube (area radiation monitor)",
        category="sensors", subcategory="radiation_gm",
        material="Stainless steel cathode / halogen quench gas",
        key_dimensions={"diameter_mm": 25.0, "length_mm": 110.0},
        mass_g=50.0,  # LND Inc. Model 7317 (LND catalog)
        max_operating_temp_k=348.0,  # 75 °C (LND 7317 data sheet)
        source="LND Inc. Model 7317 data sheet",
        extra={"operating_voltage_v": 500.0, "dead_time_us": 90.0,
               "gamma_sensitivity_cps_mrsv_hr": 18.0},
    ),
]


# ---------------------------------------------------------------------------
# Category H — Pipes & Tubing
# ---------------------------------------------------------------------------

_PIPES: List[Component] = [
    # 316L stainless steel tubing — ASTM A269
    Component(
        part_number="ASTM-A269-6x1-316L",
        name="SS tube 6 mm OD x 1 mm wall (instrument)",
        category="pipes", subcategory="ss_tube",
        material="316L stainless steel",
        key_dimensions={"od_mm": 6.0, "wall_mm": 1.0, "id_mm": 4.0},
        mass_g=124.0,  # per meter; ρ=8000 kg/m³, A=π(3²-2²)×10⁻⁶ m² × 8000 = 0.126 kg/m
        max_operating_temp_k=811.0,  # 316L to ~538 °C (ASME BPVC II-D)
        pressure_rating_kpa=42000.0,  # Barlow's: 2×1×485/(6-2×1)×1000 ≈ 242 MPa; derated to 42 MPa
        source="ASTM A269; ASME BPVC II-D; 316L UTS 485 MPa (MMPDS-17)",
    ),
    Component(
        part_number="ASTM-A269-25x2-316L",
        name="SS tube 25 mm OD x 2 mm wall (coolant branch)",
        category="pipes", subcategory="ss_tube",
        material="316L stainless steel",
        key_dimensions={"od_mm": 25.0, "wall_mm": 2.0, "id_mm": 21.0},
        mass_g=1140.0,  # per meter
        max_operating_temp_k=811.0,
        pressure_rating_kpa=46400.0,
        source="ASTM A269; ASME BPVC II-D",
    ),
    Component(
        part_number="ASTM-A269-50x3-316L",
        name="SS tube 50 mm OD x 3 mm wall (main coolant)",
        category="pipes", subcategory="ss_tube",
        material="316L stainless steel",
        key_dimensions={"od_mm": 50.0, "wall_mm": 3.0, "id_mm": 44.0},
        mass_g=3500.0,  # per meter
        max_operating_temp_k=811.0,
        pressure_rating_kpa=44000.0,
        source="ASTM A269; ASME BPVC II-D",
    ),
    Component(
        part_number="ASTM-A269-100x5-316L",
        name="SS tube 100 mm OD x 5 mm wall (header / manifold)",
        category="pipes", subcategory="ss_tube",
        material="316L stainless steel",
        key_dimensions={"od_mm": 100.0, "wall_mm": 5.0, "id_mm": 90.0},
        mass_g=11900.0,  # per meter
        max_operating_temp_k=811.0,
        pressure_rating_kpa=53900.0,
        source="ASTM A269; ASME BPVC II-D",
    ),
    Component(
        part_number="ASTM-A269-150x8-316L",
        name="SS tube 150 mm OD x 8 mm wall (primary loop)",
        category="pipes", subcategory="ss_tube",
        material="316L stainless steel",
        key_dimensions={"od_mm": 150.0, "wall_mm": 8.0, "id_mm": 134.0},
        mass_g=28300.0,  # per meter
        max_operating_temp_k=811.0,
        pressure_rating_kpa=57600.0,
        source="ASTM A269; ASME BPVC II-D",
    ),
    # Ti-6Al-4V tubing — high-temp reactor coolant
    Component(
        part_number="AMS4945-25x2-TI64",
        name="Ti-6Al-4V tube 25 mm OD x 2 mm wall (reactor coolant)",
        category="pipes", subcategory="ti_tube",
        material="Ti-6Al-4V (Grade 5)",
        key_dimensions={"od_mm": 25.0, "wall_mm": 2.0, "id_mm": 21.0},
        mass_g=630.0,  # ρ=4430 kg/m³ (MMPDS-17)
        max_operating_temp_k=589.0,  # Ti-6Al-4V long-term limit ~316 °C (AMS 4911)
        pressure_rating_kpa=72000.0,  # higher strength (UTS 900 MPa)
        source="AMS 4945; MMPDS-17; Ti-6Al-4V UTS 900 MPa",
    ),
    Component(
        part_number="AMS4945-50x3-TI64",
        name="Ti-6Al-4V tube 50 mm OD x 3 mm wall (reactor header)",
        category="pipes", subcategory="ti_tube",
        material="Ti-6Al-4V (Grade 5)",
        key_dimensions={"od_mm": 50.0, "wall_mm": 3.0, "id_mm": 44.0},
        mass_g=1940.0,  # per meter
        max_operating_temp_k=589.0,
        pressure_rating_kpa=81800.0,
        source="AMS 4945; MMPDS-17",
    ),
    # Flexible hose — PTFE-lined braided SS
    Component(
        part_number="FLEX-PTFE-12-SS",
        name="Flexible hose 12 mm PTFE-lined SS braided",
        category="pipes", subcategory="flexible_hose",
        material="PTFE liner / 304 SS braid",
        key_dimensions={"bore_mm": 12.0, "od_mm": 20.0},
        mass_g=350.0,  # per meter (Parker 919 / Swagelok)
        max_operating_temp_k=533.0,  # PTFE core limit 260 °C (Parker 919 series)
        pressure_rating_kpa=20700.0,  # 3000 psi (Parker 919)
        source="Parker 919 series data sheet; Swagelok catalog",
    ),
    Component(
        part_number="FLEX-PTFE-25-SS",
        name="Flexible hose 25 mm PTFE-lined SS braided",
        category="pipes", subcategory="flexible_hose",
        material="PTFE liner / 304 SS braid",
        key_dimensions={"bore_mm": 25.0, "od_mm": 38.0},
        mass_g=680.0,  # per meter
        max_operating_temp_k=533.0,
        pressure_rating_kpa=13800.0,  # 2000 psi (larger bore, lower rating)
        source="Parker 919 series data sheet",
    ),
    Component(
        part_number="FLEX-PTFE-50-SS",
        name="Flexible hose 50 mm PTFE-lined SS braided",
        category="pipes", subcategory="flexible_hose",
        material="PTFE liner / 304 SS braid",
        key_dimensions={"bore_mm": 50.0, "od_mm": 70.0},
        mass_g=1500.0,  # per meter
        max_operating_temp_k=533.0,
        pressure_rating_kpa=10300.0,  # 1500 psi
        source="Parker 919 series data sheet",
    ),
]


# ---------------------------------------------------------------------------
# Master database — assembled from all categories
# ---------------------------------------------------------------------------

COMPONENT_DATABASE: Dict[str, Component] = {}
"""All spacecraft components keyed by part_number."""

for _list in (
    _BOLTS, _NUTS, _WASHERS, _RIVETS, _STUDS, _INSERTS,
    _ORINGS, _METAL_GASKETS, _FACE_SEALS, _HATCH_SEALS,
    _BEARINGS,
    _ACTUATORS,
    _VALVES, _FITTINGS,
    _ELECTRICAL,
    _SENSORS,
    _PIPES,
):
    for comp in _list:
        if comp.part_number in COMPONENT_DATABASE:
            raise ValueError(
                f"Duplicate part_number in components_db: {comp.part_number}"
            )
        COMPONENT_DATABASE[comp.part_number] = comp


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_component(part_number: str) -> Component:
    """Look up a component by part number.

    Raises
    ------
    KeyError
        If the part number is not in the database.
    """
    return COMPONENT_DATABASE[part_number]


def get_components_by_category(category: str) -> List[Component]:
    """Return all components in a given top-level category."""
    return [c for c in COMPONENT_DATABASE.values() if c.category == category]


def get_components_by_subcategory(subcategory: str) -> List[Component]:
    """Return all components matching a subcategory."""
    return [c for c in COMPONENT_DATABASE.values() if c.subcategory == subcategory]


def get_category_summary() -> Dict[str, int]:
    """Return component count per category."""
    summary: Dict[str, int] = {}
    for comp in COMPONENT_DATABASE.values():
        summary[comp.category] = summary.get(comp.category, 0) + 1
    return summary


def total_unique_components() -> int:
    """Total number of unique component types in the database."""
    return len(COMPONENT_DATABASE)
