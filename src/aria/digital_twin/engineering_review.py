"""Engineering Design Review — comprehensive ship assessment.

Pulls together ALL digital twin analyses into a single review document.
This is what a review board would evaluate before approving the design.

Covers:
  1. Mass budget (all subsystems)
  2. Power budget (generation vs consumption)
  3. Delta-v budget (mission trajectory)
  4. Structural analysis (FEA stress margins)
  5. Thermal analysis (heat balance)
  6. Radiation analysis (crew dose)
  7. Key findings and design actions

Usage:
    python -m aria.digital_twin.engineering_review
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


def run_engineering_review() -> dict[str, Any]:
    """Run complete engineering design review."""
    t0 = time.time()
    review: dict[str, Any] = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    findings: list[str] = []
    actions: list[str] = []

    print("=" * 70)
    print("  ARIA GENERATION SHIP — ENGINEERING DESIGN REVIEW")
    print("=" * 70)

    # ── 1. Mass Budget ──
    print("\n1. MASS BUDGET")
    print("-" * 70)
    from aria.digital_twin.mass_budget import compute_mass_budget
    mb = compute_mass_budget()
    print(mb.summary())
    review["mass_budget"] = {
        "total_kg": mb.total_mass_kg,
        "config_target_kg": mb.config_mass_kg,
        "discrepancy_pct": mb.discrepancy_pct,
    }
    if mb.discrepancy_pct > 20:
        findings.append(f"MASS: Ship is {mb.discrepancy_pct:+.0f}% over target. "
                        f"Habitat ring = {131968575/mb.total_mass_kg*100:.0f}% of mass.")
        actions.append("Consider CNT composite (ρ=1600 vs Ti ρ=4430) for habitat ring walls")
    elif mb.discrepancy_pct < -20:
        findings.append(f"MASS: Ship is {mb.discrepancy_pct:+.0f}% under target — mass margin available")

    # ── 2. Power Budget ──
    print("\n2. POWER BUDGET")
    print("-" * 70)
    from aria.digital_twin.power_budget import compute_power_budget
    pb = compute_power_budget()
    print(pb.summary())
    review["power_budget"] = {
        "total_consumption_kw": pb.total_consumption_kw,
        "total_generation_kw": pb.total_generation_kw,
        "margin_pct": pb.margin_pct,
    }
    if pb.margin_pct > 80:
        findings.append(f"POWER: {pb.margin_pct:.0f}% margin — reactor oversized for electrical loads")
        actions.append(f"Consider reducing reactor to {pb.total_consumption_kw*2/1000:.0f} MWe "
                       "(2× consumption for margin)")

    # ── 3. Delta-V Budget ──
    print("\n3. DELTA-V BUDGET")
    print("-" * 70)
    from aria.digital_twin.deltav_budget import compute_deltav_budget
    from aria.simulation.generation_ship import GenerationShipConfig
    dv = compute_deltav_budget()
    print(dv.summary())
    review["deltav_budget"] = {
        "total_deltav_km_s": dv.total_delta_v_ms / 1000,
        "total_propellant_kg": dv.total_propellant_kg,
        "mass_ratio": dv.mass_ratio,
        "propellant_fraction": dv.propellant_fraction,
    }
    config_propellant_kg = GenerationShipConfig().propellant_kg
    if dv.total_propellant_kg > config_propellant_kg * 1.05:  # 5% tolerance
        findings.append(
            f"PROPELLANT: Delta-v budget requires {dv.total_propellant_kg/1000:,.0f}t "
            f"but config has {config_propellant_kg/1000:,.0f}t"
        )
        actions.append(
            f"Increase propellant_kg in GenerationShipConfig to "
            f"{dv.total_propellant_kg/1000:,.0f}t"
        )

    # ── 4. Structural Analysis ──
    print("\n4. STRUCTURAL ANALYSIS (FEA)")
    print("-" * 70)
    from aria.digital_twin.bridge import SimTwinBridge
    from aria.simulation.generation_ship import GenerationShipConfig
    bridge = SimTwinBridge()
    twin_result = bridge.analyze(GenerationShipConfig())
    report = bridge.get_report()
    print(f"  Max von Mises stress: {twin_result.max_von_mises_mpa:.2f} MPa")
    print(f"  Yield strength:       880 MPa (Ti-6Al-4V)")
    print(f"  Safety factor:        {twin_result.structural_safety_factor:.0f}×")
    print(f"  Max displacement:     {twin_result.max_displacement_mm:.3f} mm")
    review["structural"] = report.get("structural", {})
    if twin_result.structural_safety_factor < 4:
        findings.append(f"STRUCTURAL: Safety factor {twin_result.structural_safety_factor:.1f}× "
                        "below NASA minimum 4.0×")
        actions.append("Increase hull wall thickness or use higher-strength alloy")
    elif twin_result.structural_safety_factor > 10:
        findings.append(f"OVERDESIGNED: Safety factor {twin_result.structural_safety_factor:.0f}× "
                        f"far exceeds 4.0× target — hull is {twin_result.structural_safety_factor/4:.0f}× "
                        "heavier than needed. Run optimizer to reduce wall thickness.")
        actions.append("Run: python -m aria.digital_twin.run_pipeline (optimizer auto-triggers at FoS > 6)")
    if twin_result.mass_discrepancy_pct > 5:
        findings.append(f"MASS OVERRUN: Geometry-derived mass exceeds config by "
                        f"{twin_result.mass_discrepancy_pct:.0f}%. "
                        f"({twin_result.computed_mass_kg:,.0f} kg vs target)")
        actions.append("Reduce structural mass fraction or increase ship_mass_kg in config")

    # ── 5. Thermal Analysis ──
    print("\n5. THERMAL ANALYSIS")
    print("-" * 70)
    print(f"  Max temperature:    {twin_result.max_temperature_k:.0f} K")
    print(f"  Min temperature:    {twin_result.min_temperature_k:.0f} K")
    print(f"  Material limit:     600 K (Ti-6Al-4V)")
    print(f"  Thermal margin:     {twin_result.thermal_margin_k:.0f} K")
    review["thermal"] = report.get("thermal", {})
    if twin_result.thermal_margin_k < 50:
        findings.append(f"THERMAL: Margin only {twin_result.thermal_margin_k:.0f}K")
        actions.append("Increase radiator area or switch to Inconel-718 (limit 1609K)")

    # ── 6. Radiation ──
    print("\n6. RADIATION ANALYSIS")
    print("-" * 70)
    from aria.digital_twin.radiation_geometry import run_radiation_analysis
    from aria.digital_twin.parameters import ShipParameters
    rad = run_radiation_analysis(ShipParameters(), velocity_c=0.1, n_particles=200)
    dose = rad.get("total_dose_msv", 0)
    print(f"  Annual crew dose:   {dose:.1f} mSv")
    print(f"  NASA limit:         500 mSv/yr (career: 1000 mSv)")
    print(f"  Shield layers:      {len(rad.get('shield_config', []))}")
    review["radiation"] = {"annual_dose_msv": dose, "limit_msv": 500}
    if dose > 500:
        findings.append(f"RADIATION: Annual dose {dose:.0f} mSv exceeds 500 mSv limit")
        actions.append("Increase water/polyethylene shielding thickness")

    # ── 7. ECLSS / Life Support ──
    print("\n7. ECLSS ANALYSIS")
    print("-" * 70)
    try:
        from aria.digital_twin.eclss_bridge import compute_eclss_constraints
        _p = ShipParameters()
        eclss = compute_eclss_constraints(
            _p.hull_radius_m - _p.hull_wall_thickness_m,
            _p.hull_length_m,
            crew_size=_p.crew_size,
            habitat_ring_radius_m=_p.habitat_ring_radius_m,
            habitat_tube_radius_m=_p.habitat_ring_tube_radius_m,
        )
        print(f"  Food self-sufficiency: {eclss.food_self_sufficiency_pct:.1f}%")
        print(f"  Water reserve:         {eclss.water_reserve_days:.0f} days")
        print(f"  CO2 buffer:            {eclss.co2_buffer_hours:.0f} hours")
        review["eclss"] = {
            "food_self_sufficiency_pct": eclss.food_self_sufficiency_pct,
            "water_reserve_days": eclss.water_reserve_days,
            "co2_buffer_hours": eclss.co2_buffer_hours,
        }
        if eclss.food_self_sufficiency_pct < 50:
            findings.append(f"FOOD SHORTFALL: Only {eclss.food_self_sufficiency_pct:.0f}% self-sufficient. "
                            f"Need {eclss.crew_food_demand_kg_day - eclss.max_food_production_kg_day:.0f} "
                            "kg/day more food production capacity.")
            actions.append("Increase agriculture zone length or add more growing levels (currently 3)")
        if eclss.water_reserve_days < 30:
            findings.append(f"WATER CRITICAL: Only {eclss.water_reserve_days:.0f} days reserve")
            actions.append("Increase water tank volume allocation (currently 2% of habitat)")
    except Exception as e:
        print(f"  ECLSS analysis failed: {e}")

    # ── 8. Summary ──
    elapsed = time.time() - t0
    print(f"\n{'=' * 70}")
    print("  FINDINGS")
    print(f"{'=' * 70}")
    for i, f in enumerate(findings, 1):
        print(f"  {i}. {f}")
    print(f"\n  RECOMMENDED ACTIONS")
    for i, a in enumerate(actions, 1):
        print(f"  {i}. {a}")
    print(f"\n  Review completed in {elapsed:.1f}s")
    print(f"{'=' * 70}")

    review["findings"] = findings
    review["actions"] = actions
    review["elapsed_s"] = elapsed

    # Save
    export_dir = Path("data/exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    report_path = export_dir / "engineering_review.json"
    with open(report_path, "w") as fp:
        json.dump(review, fp, indent=2, default=str)
    print(f"  Report saved: {report_path}")

    return review


if __name__ == "__main__":
    run_engineering_review()
