"""Full digital twin pipeline: geometry → mesh → FEA → glTF → report.

Usage:
    python -m aria.digital_twin.run_pipeline
    python -m aria.digital_twin.run_pipeline --serve  # Also start web viewer
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import structlog

logger = structlog.get_logger()


def run_pipeline(serve: bool = False) -> dict:
    """Run the complete digital twin pipeline."""
    t0 = time.time()
    results = {}

    print("=" * 60)
    print("  ARIA Digital Twin Pipeline")
    print("=" * 60)

    # ── Step 1: Parameters ──
    print("\n[1/6] Deriving ship parameters from config...")
    from aria.digital_twin.parameters import ShipParameters
    params = ShipParameters()
    print(f"  Hull: R={params.hull_radius_m:.1f}m, L={params.hull_length_m:.0f}m, "
          f"t={params.hull_wall_thickness_m*1000:.0f}mm")
    print(f"  Habitat ring: R={params.habitat_ring_radius_m:.0f}m")
    print(f"  Radiators: {params.radiator_total_panels} × "
          f"{params.radiator_panel_area_m2:.0f}m²")
    results["parameters"] = {
        "hull_radius_m": params.hull_radius_m,
        "hull_length_m": params.hull_length_m,
        "total_radiator_area_m2": params.total_radiator_area_m2,
    }

    # ── Step 2: Geometry ──
    print("\n[2/6] Creating CadQuery geometry (7 subsystems)...")
    from aria.digital_twin.geometry.assembly import assemble_ship
    assembly = assemble_ship(params)
    print(f"  Assembly created with {len(assembly.objects)} subsystems")
    results["geometry"] = {"subsystems": len(assembly.objects)}

    # ── Step 3: Mesh ──
    print("\n[3/6] Generating Gmsh tetrahedral mesh...")
    from aria.digital_twin.mesher import mesh_cylinder
    mesh = mesh_cylinder(
        radius=params.hull_radius_m,
        length=min(params.hull_length_m, 50.0),
        thickness=params.hull_wall_thickness_m,
        element_size=2.0,
    )
    n_nodes = len(mesh.points)
    n_elements = len(mesh.cells[0].data)
    print(f"  Mesh: {n_nodes} nodes, {n_elements} tetrahedra")
    results["mesh"] = {"nodes": n_nodes, "elements": n_elements}

    # ── Step 4: FEA ──
    print("\n[4/6] Running structural + thermal FEA...")
    from aria.digital_twin.bridge import SimTwinBridge
    from aria.simulation.generation_ship import GenerationShipConfig
    bridge = SimTwinBridge()
    config = GenerationShipConfig()
    twin_result = bridge.analyze(config)
    print(f"  Mass: {twin_result.computed_mass_kg:,.0f} kg "
          f"(config: {config.ship_mass_kg:,.0f} kg, "
          f"Δ={twin_result.mass_discrepancy_pct:+.0f}%)")
    print(f"  Max stress: {twin_result.max_von_mises_mpa:.2f} MPa "
          f"(yield: 880 MPa, FoS: {twin_result.structural_safety_factor:.0f}x)")
    print(f"  Temperature: {twin_result.min_temperature_k:.0f}K — "
          f"{twin_result.max_temperature_k:.0f}K "
          f"(margin: {twin_result.thermal_margin_k:.0f}K)")
    results["fea"] = bridge.get_report()

    # ── Step 4b: Hull-thickness sweep — honest mass trade-off ──
    # Shows hull shell mass vs stress, AND the full-ship mass impact
    # (which is counter-intuitive: thinning the hull grows its auto-
    # derived length to keep structural mass fraction constant, so
    # ancillary subsystem masses (stringers, cabling) RISE faster
    # than shell mass falls — net +10% ship mass at t=5 mm).
    if twin_result.structural_safety_factor > 6.0:
        print(f"\n[4b] Safety factor {twin_result.structural_safety_factor:.0f}× >> 4× target — "
              f"sweeping hull_wall_thickness...")
        import math as _math, copy as _copy
        from aria.digital_twin.parameters import ShipParameters as _SP
        from aria.digital_twin.mass_budget import compute_mass_budget as _cmb
        base_hull_mass_kg = (4430.0   # Ti-6Al-4V density (MMPDS-17)
                             * 2 * _math.pi
                             * params.hull_radius_m
                             * params.hull_wall_thickness_m
                             * params.hull_length_m)
        base_t_mm = params.hull_wall_thickness_m * 1000
        base_total_mass = _cmb(params=params).total_mass_kg
        allowable_mpa = 220.0   # yield 880 MPa / FoS 4× (NASA-STD-5017A)
        print(f"  Baseline at t={base_t_mm:.0f} mm: hull shell {base_hull_mass_kg:,.0f} kg, "
              f"full ship {base_total_mass:,.0f} kg, σ_VM={twin_result.max_von_mises_mpa:.1f} MPa")
        thicknesses_mm = [60, 40, 20, 15, 10, 8, 7]
        sigma_base = twin_result.max_von_mises_mpa
        print(f"  {'t':>4s} {'σ':>7s} {'FoS':>5s} {'shell':>12s} {'full':>12s} {'Δfull':>7s}")
        for t_mm in thicknesses_mm:
            sigma_mpa = sigma_base * (base_t_mm / t_mm)
            shell_kg  = base_hull_mass_kg * (t_mm / base_t_mm)
            # Re-derive full-ship mass at this thickness:
            p = _SP()
            p.hull_wall_thickness_m = t_mm / 1000.0
            p.hull_length_m = 0.0
            p.__post_init__()
            full_kg = _cmb(params=p).total_mass_kg
            ok = "✓" if sigma_mpa <= allowable_mpa else "✗"
            delta_full = (full_kg - base_total_mass) / base_total_mass * 100
            print(f"  {t_mm:>3d}mm {sigma_mpa:>6.1f} {880/sigma_mpa:>4.1f}x "
                  f"{shell_kg:>11,.0f} {full_kg:>11,.0f} {delta_full:>+6.1f}% {ok}")
        print(f"  (Full-ship mass rises as t shrinks because auto-derived hull "
              f"length compensates; ancillary subsystem masses grow faster than "
              f"shell mass falls. Optimisation should pin hull_length if targeting "
              f"shell-mass savings specifically.)")

    # ── Step 4c: ECLSS physical constraints from geometry ──
    print("\n[4c] Computing ECLSS constraints from hull geometry...")
    try:
        from aria.digital_twin.eclss_bridge import compute_eclss_constraints
        eclss = compute_eclss_constraints(
            params.hull_radius_m - params.hull_wall_thickness_m,
            params.hull_length_m,
            crew_size=100,
            habitat_ring_radius_m=params.habitat_ring_radius_m,
            habitat_tube_radius_m=params.habitat_ring_tube_radius_m,
        )
        print(f"  Agriculture area: {eclss.crop_area_m2:.0f} m²")
        print(f"  Food production:  {eclss.max_food_production_kg_day:.1f} kg/day "
              f"(demand: {eclss.crew_food_demand_kg_day:.0f} kg/day)")
        print(f"  Self-sufficiency: {eclss.food_self_sufficiency_pct:.1f}%")
        print(f"  Water reserve:    {eclss.water_reserve_days:.0f} days")
        print(f"  CO2 buffer:       {eclss.co2_buffer_hours:.0f} hours")
        if eclss.food_self_sufficiency_pct < 50:
            print(f"  ⚠ FOOD SHORTFALL: need {eclss.crew_food_demand_kg_day - eclss.max_food_production_kg_day:.0f} kg/day more")
        results["eclss"] = {
            "food_self_sufficiency_pct": eclss.food_self_sufficiency_pct,
            "water_reserve_days": eclss.water_reserve_days,
            "co2_buffer_hours": eclss.co2_buffer_hours,
        }
    except Exception as e:
        print(f"  ECLSS bridge failed: {e}")

    # ── Step 5: glTF export ──
    print("\n[5/6] Exporting glTF for 3D viewer...")
    export_dir = Path("data/exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    gltf_path = export_dir / "ship.gltf"
    from aria.digital_twin.export_gltf import export_gltf
    export_gltf(str(gltf_path))
    size_kb = gltf_path.stat().st_size / 1024
    print(f"  Exported: {gltf_path} ({size_kb:.0f} KB)")
    results["export"] = {"gltf_path": str(gltf_path), "size_kb": size_kb}

    # ── Step 6: Radiation analysis ──
    print("\n[6/6] Running radiation Monte Carlo through shield geometry...")
    from aria.digital_twin.radiation_geometry import run_radiation_analysis
    rad = run_radiation_analysis(params, velocity_c=0.1, n_particles=500)
    print(f"  Annual dose: {rad.get('total_dose_msv', 0):.1f} mSv "
          f"(limit: 500 mSv/yr)")
    print(f"  Particles stopped: {rad.get('particles_stopped', 0)}/{rad.get('particles_simulated', 0)}")
    print(f"  Shield layers: {len(rad.get('shield_config', []))}")
    results["radiation"] = rad

    # ── Summary ──
    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete in {elapsed:.1f}s")
    # Collect all warnings
    all_warnings = list(twin_result.warnings) if twin_result.warnings else []
    if twin_result.structural_safety_factor > 10:
        all_warnings.append(f"Hull overdesigned: FoS {twin_result.structural_safety_factor:.0f}× (target 4×)")
    if twin_result.mass_discrepancy_pct > 5:
        all_warnings.append(f"Mass overrun: {twin_result.mass_discrepancy_pct:.0f}% over config target")
    if results.get("eclss", {}).get("food_self_sufficiency_pct", 100) < 50:
        all_warnings.append(f"Food shortfall: {results['eclss']['food_self_sufficiency_pct']:.0f}% self-sufficient")

    if all_warnings:
        print(f"  ⚠ {len(all_warnings)} issue(s) found:")
        for w in all_warnings:
            print(f"    - {w}")
    else:
        print(f"  ✓ All constraints satisfied")
    print(f"{'=' * 60}")

    # Save report
    report_path = export_dir / "pipeline_report.json"
    with open(report_path, "w") as f:
        # Filter non-serializable values
        clean = {}
        for k, v in results.items():
            if isinstance(v, dict):
                clean[k] = {kk: vv for kk, vv in v.items()
                            if isinstance(vv, (int, float, str, bool, list, type(None)))}
            else:
                clean[k] = v
        json.dump(clean, f, indent=2, default=str)
    print(f"  Report saved: {report_path}")

    # ── Optional: serve viewer ──
    if serve:
        print(f"\n  Starting web dashboard on http://localhost:8080/viewer ...")
        import asyncio
        from aria.simulator.web_dashboard import start_dashboard
        asyncio.run(start_dashboard(port=8080))

    return results


def main():
    serve = "--serve" in sys.argv
    run_pipeline(serve=serve)


if __name__ == "__main__":
    main()
