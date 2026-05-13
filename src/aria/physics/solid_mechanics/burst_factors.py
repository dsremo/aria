"""R42 §2.3 — pressure-vessel burst-factor classifier.

Pressure-vessel margins follow standardised multipliers on top of the
Maximum Expected Operating Pressure (MEOP):

    proof  = MEOP × proof_factor
    burst  = MEOP × burst_factor

NASA-STD-5019B §6.5 and ASME BPVC §VIII Div 2 prescribe the multipliers.
This module gives the rule + a programmatic check so a new tank design
gets a Pass/Fail without an engineer reading the standards table.

Authoritative tables
--------------------

Composite Overwrap Pressure Vessels (COPV):
    proof  = 1.5 × MEOP   (qualification)
    burst  = 4.0 × MEOP   (NASA-STD-5019B §6.5.2.1)

Metallic pressure vessels:
    proof  = 1.5 × MEOP
    burst  = 2.5 × MEOP   (ASME BPVC §VIII Div 2 Pt 5; ECSS-E-ST-32-02)

Inflatable / soft-goods (ECSS-E-ST-32-21):
    proof  = 2.0 × MEOP
    burst  = 4.0 × MEOP

Reusable / man-rated propellant tanks:
    proof  = 1.5 × MEOP
    burst  = 1.5 × MEOP × ultimate_safety_factor (≥ 2.0)

Reference:
    NASA-STD-5019B (Fracture Control Requirements for Spaceflight Hardware);
    ASME BPVC §VIII Div 2 Pt 5; ECSS-E-ST-32-02C (composite); -32-21
    (inflatable structures).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class VesselClass(str, Enum):
    COPV = "copv"
    METALLIC = "metallic"
    INFLATABLE = "inflatable"
    REUSABLE_MANRATED = "reusable_manrated"


VESSEL_FACTORS: Dict[VesselClass, Dict[str, float]] = {
    VesselClass.COPV: {
        "proof": 1.5, "burst": 4.0,
        "standard": "NASA-STD-5019B §6.5.2.1",
    },
    VesselClass.METALLIC: {
        "proof": 1.5, "burst": 2.5,
        "standard": "ASME BPVC §VIII Div 2 Pt 5",
    },
    VesselClass.INFLATABLE: {
        "proof": 2.0, "burst": 4.0,
        "standard": "ECSS-E-ST-32-21",
    },
    VesselClass.REUSABLE_MANRATED: {
        "proof": 1.5, "burst": 3.0,    # 1.5 × 2.0 ultimate factor
        "standard": "NASA-STD-5012 + NASA-STD-5019B",
    },
}


# ── Classify ────────────────────────────────────────────────────


@dataclass(frozen=True)
class BurstClassification:
    vessel_class: VesselClass
    meop_kpa: float
    measured_burst_kpa: float
    required_proof_kpa: float
    required_burst_kpa: float
    margin_proof_pct: float
    margin_burst_pct: float
    passes: bool
    standard: str
    reason: str = ""


def classify(
    vessel_class: VesselClass,
    meop_kpa: float,
    measured_burst_kpa: float,
    measured_proof_kpa: float = 0.0,
) -> BurstClassification:
    """Pass/Fail per the standard's required burst factor.

    Margin is reported in %; a positive value indicates the vessel
    burst above its required pressure (good).  ``measured_proof_kpa``
    is optional — when zero, only the burst factor is checked.
    """
    if vessel_class not in VESSEL_FACTORS:
        raise ValueError(f"unknown vessel_class: {vessel_class}")
    pf = VESSEL_FACTORS[vessel_class]
    req_proof = meop_kpa * pf["proof"]
    req_burst = meop_kpa * pf["burst"]
    margin_burst = (measured_burst_kpa - req_burst) / req_burst * 100.0
    margin_proof = (
        (measured_proof_kpa - req_proof) / req_proof * 100.0
        if measured_proof_kpa > 0 else float("nan")
    )
    fails: list[str] = []
    if measured_burst_kpa < req_burst:
        fails.append(
            f"burst {measured_burst_kpa:.1f} kPa < required "
            f"{req_burst:.1f} kPa ({pf['burst']}× MEOP)"
        )
    if measured_proof_kpa > 0 and measured_proof_kpa < req_proof:
        fails.append(
            f"proof {measured_proof_kpa:.1f} kPa < required "
            f"{req_proof:.1f} kPa ({pf['proof']}× MEOP)"
        )
    return BurstClassification(
        vessel_class=vessel_class,
        meop_kpa=meop_kpa,
        measured_burst_kpa=measured_burst_kpa,
        required_proof_kpa=req_proof,
        required_burst_kpa=req_burst,
        margin_proof_pct=margin_proof,
        margin_burst_pct=margin_burst,
        passes=not fails,
        standard=pf["standard"],
        reason=" + ".join(fails) if fails else "all factors satisfied",
    )


def required_burst_kpa(vessel_class: VesselClass, meop_kpa: float) -> float:
    return meop_kpa * VESSEL_FACTORS[vessel_class]["burst"]


def required_proof_kpa(vessel_class: VesselClass, meop_kpa: float) -> float:
    return meop_kpa * VESSEL_FACTORS[vessel_class]["proof"]
