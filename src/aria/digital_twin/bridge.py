"""Bidirectional bridge between ARIA simulation engine and digital twin.

Direction 1: Simulation → Twin (boundary conditions)
  GenerationShipConfig/State → geometry parameters, material assignments,
  load cases (pressure, temperature, radiation flux)

Direction 2: Twin → Simulation (validated parameters)
  FEA results → actual mass (from geometry × density), stress margins,
  thermal limits, radiation dose maps → feed back into GenerationShipConfig

This closes the loop: instead of hand-tuned config values, the simulation
uses geometry-derived values that are physically consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()


@dataclass
class TwinAnalysisResult:
    """Results from a full digital twin analysis cycle."""
    # From geometry
    computed_mass_kg: float = 0.0
    hull_volume_m3: float = 0.0
    total_radiator_area_m2: float = 0.0
    shield_total_thickness_m: float = 0.0

    # From structural FEA
    max_von_mises_mpa: float = 0.0
    max_displacement_mm: float = 0.0
    structural_safety_factor: float = 0.0
    element_stresses_mpa: list[float] = field(default_factory=list)

    # From thermal FEA
    max_temperature_k: float = 0.0
    min_temperature_k: float = 0.0
    thermal_margin_k: float = 0.0  # Material limit - max temp

    # From nonlinear (elastoplastic) FEA — only populated when
    # `analyze(enable_plasticity=True)` triggers a yielded-element pass
    plastic_yielded: bool = False
    plastic_strain_max: float = 0.0           # Simo-Hughes p̄ = Σ √(2/3)·Δγ
    post_yield_max_von_mises_mpa: float = 0.0 # after radial-return correction

    # Recommendations
    mass_discrepancy_pct: float = 0.0  # vs config.ship_mass_kg
    warnings: list[str] = field(default_factory=list)


class SimTwinBridge:
    """Connects the ARIA simulation to the digital twin.

    Usage:
        bridge = SimTwinBridge()
        result = bridge.analyze(config)  # Full analysis cycle
        updated_config = bridge.update_config(config, result)  # Feed back
    """

    def __init__(self) -> None:
        self._last_result: TwinAnalysisResult | None = None

    def analyze(
        self,
        config: Any,
        params: Any = None,
        enable_plasticity: bool = False,
    ) -> TwinAnalysisResult:
        """Run full digital twin analysis from a GenerationShipConfig.

        Steps:
        1. Derive geometry parameters from config (or use provided params)
        2. Create CadQuery geometry
        3. Mesh with Gmsh
        4. Solve structural FEA (pressure + rotation)
        5. If `enable_plasticity` is True AND the linear solve shows
           max_σ_VM ≥ σ_y, re-run a Newton-Raphson nonlinear solve with
           J2 radial-return (via `aria.physics.solid_mechanics.plasticity`)
           to get the post-yield saturated stress and accumulated plastic
           strain. Linear FEA alone reports a misleadingly large stress
           when the material has actually yielded.
        6. Solve thermal FEA (reactor heat + radiation)
        7. Compare computed values against config assumptions

        Args:
            config: GenerationShipConfig (or any object with ship_mass_kg, habitat_rpm).
            params: Optional ShipParameters override. If provided, these are used
                    directly instead of creating defaults. This is how the optimizer
                    passes modified geometry (e.g., thinner hull) for evaluation.
            enable_plasticity: If True, run nonlinear FEA when linear solve
                    indicates yielding. Adds ~1 min per call; keep False for
                    optimizer inner loop. Default False.
        """
        result = TwinAnalysisResult()

        try:
            if params is None:
                from aria.digital_twin.parameters import ShipParameters
                params = ShipParameters()

                # Override from config if available
                if hasattr(config, 'ship_mass_kg'):
                    pass  # Parameters already derive from standard config
                if hasattr(config, 'habitat_rpm'):
                    params.habitat_rpm = config.habitat_rpm
                # Round 11 fix: propagate crew_size from simulation config
                if hasattr(config, 'crew_size') and config.crew_size > 0:
                    params.crew_size = config.crew_size

        except Exception as e:
            logger.error("bridge.params_failed", error=str(e))
            return result

        # ── Step 1: Geometry mass computation ──
        try:
            from aria.digital_twin.materials.material_db import get_material
            import math

            ti = get_material("Ti-6Al-4V")
            # Hull mass: cylinder shell volume × density
            r_outer = params.hull_radius_m
            r_inner = r_outer - params.hull_wall_thickness_m
            hull_vol = math.pi * (r_outer**2 - r_inner**2) * params.hull_length_m
            hull_mass = hull_vol * ti.density_kg_m3

            result.hull_volume_m3 = math.pi * r_outer**2 * params.hull_length_m
            result.total_radiator_area_m2 = params.total_radiator_area_m2

            # Shield mass estimate (ice ablation layer dominates)
            shield_vol = math.pi * r_outer**2 * params.total_shield_thickness_m
            shield_mass = shield_vol * 917  # ice density approximation

            # Use full mass budget (all subsystems), not hull+shield only.
            # hull+shield = 23M kg; full ship (propellant, habitat, ECLSS, etc) = 106M kg.
            from aria.digital_twin.mass_budget import compute_mass_budget
            mb = compute_mass_budget(params=params, config=config)
            result.computed_mass_kg = mb.total_mass_kg
            # Compare with config
            if hasattr(config, 'ship_mass_kg') and config.ship_mass_kg > 0:
                result.mass_discrepancy_pct = mb.discrepancy_pct
                if abs(result.mass_discrepancy_pct) > 20:
                    result.warnings.append(
                        f"Mass discrepancy {result.mass_discrepancy_pct:+.0f}%: "
                        f"budget={result.computed_mass_kg:.0f} kg vs "
                        f"config={config.ship_mass_kg:.0f} kg"
                    )

            logger.info("bridge.geometry", hull_mass_kg=hull_mass,
                        shield_mass_kg=shield_mass, total_kg=result.computed_mass_kg)

        except Exception as e:
            logger.error("bridge.geometry_failed", error=str(e))

        # ── Step 2: Structural FEA ──
        try:
            from aria.digital_twin.mesher import mesh_cylinder
            from aria.digital_twin.solver import FEASolver, MaterialProperty

            # Mesh a representative section (full ship too large)
            mesh = mesh_cylinder(
                radius=params.hull_radius_m,
                length=min(params.hull_length_m, 50.0),  # 50m section
                thickness=params.hull_wall_thickness_m,
                element_size=2.0,  # Coarse for speed
            )

            mat = MaterialProperty(
                name="Ti-6Al-4V",
                E=ti.youngs_modulus_pa,
                nu=ti.poisson_ratio,
                density=ti.density_kg_m3,
            )

            solver = FEASolver(mesh, mat)

            # Apply 1 atm internal pressure (101,325 Pa — NASA-STD-3001 Vol 1 Rev C §4.2).
            # Pressure goes on the INNER surface only. The hollow-cylinder mesh has
            # inner radius `params.hull_radius_m - hull_wall_thickness_m`; filter
            # nodes by radial distance so `_apply_pressure_lumped` only picks up
            # inner-surface triangular faces. (Passing all nodes previously caused
            # pressure to be applied to outer AND caps too, inflating σ ~10×.)
            # mesher.mesh_cylinder takes `radius=params.hull_radius_m` as the
            # INNER radius of the mesh and adds `thickness` outward. So the
            # mesh inner surface sits at r = params.hull_radius_m and the outer
            # surface at r = params.hull_radius_m + hull_wall_thickness_m.
            inner_r_mesh = params.hull_radius_m
            pts = mesh.points
            import numpy as _np
            radial = _np.sqrt(pts[:, 0] ** 2 + pts[:, 1] ** 2)
            # Wall is only 80 mm thick — filter tolerance must be << thickness/2
            # or we pick up the outer surface too (and cancel the inward load).
            # Node-radius tolerance: thickness × 0.25 keeps the filter
            # inside the inner half of the wall (stays away from the
            # outer surface at thickness×1.0). ESTIMATE — chosen because
            # Gmsh places at least one node layer inside each surface
            # band, and 0.25 is the largest value that robustly excludes
            # the outer layer given typical element_size ~ 2 m.
            tol = params.hull_wall_thickness_m * 0.25   # ESTIMATE — inner-half filter
            inner_nodes = [int(i) for i, r in enumerate(radial) if abs(r - inner_r_mesh) < tol]
            # Cap-edge exclusion: drop nodes within `cap_tol` of either
            # axial end so axial-facing faces on the end-ring annulus
            # aren't pressurised as radial. 0.1 m floor + 2 × thickness
            # covers most element sizes; ESTIMATE calibrated by eye on
            # the 50 m hull section and validated by the pR/t match.
            z = pts[:, 2]
            z_min, z_max = float(z.min()), float(z.max())
            cap_tol = max(0.1, params.hull_wall_thickness_m * 2)  # ESTIMATE — end-ring exclusion
            inner_nodes = [i for i in inner_nodes
                           if (z[i] > z_min + cap_tol) and (z[i] < z_max - cap_tol)]
            # Guard: an empty filter would silently apply zero pressure
            # and return a bogus "massive FoS" result. Require at least a
            # handful of inner-surface nodes before calling FEA trustworthy.
            if len(inner_nodes) < 10:
                raise RuntimeError(
                    f"Inner-surface node filter matched only {len(inner_nodes)} "
                    f"nodes at R={inner_r_mesh:.3f}m, tol={tol:.4f}m — cannot "
                    f"apply pressure. Check element_size vs hull thickness."
                )
            # Call the lumped-face helper directly — apply_pressure() auto-detects
            # "list length divisible by 3" as "consecutive triangle triplets",
            # which would misinterpret a node-ID set as arbitrary triangles.
            solver._apply_pressure_lumped(inner_nodes, 101_325.0)  # 1 atm — NASA-STD-3001

            # NOTE: the hull is NOT rotating — only the habitat ring spins at 1 RPM.
            # Previous code applied a 5.5 m/s² body force on the hull section which
            # is incorrect. The hull sees only pressure + axial thrust loads.
            # Fix one end (cantilever BC) to kill rigid-body modes.
            solver.fix_nodes([0, 1, 2, 3])

            fea_result = solver.solve()
            result.max_von_mises_mpa = fea_result.max_stress / 1e6
            result.max_displacement_mm = float(np.max(np.abs(fea_result.displacements))) * 1000
            result.element_stresses_mpa = (fea_result.von_mises_stress / 1e6).tolist()

            yield_mpa = ti.yield_strength_pa / 1e6
            result.structural_safety_factor = yield_mpa / max(result.max_von_mises_mpa, 0.001)

            if result.structural_safety_factor < 2.0:
                result.warnings.append(
                    f"Structural safety factor {result.structural_safety_factor:.1f}x "
                    f"below NASA minimum 2.0x (max stress {result.max_von_mises_mpa:.0f} MPa)"
                )

            logger.info("bridge.structural_fea",
                        max_stress_mpa=result.max_von_mises_mpa,
                        safety_factor=result.structural_safety_factor)

            # ── Step 2b: Nonlinear (elastoplastic) re-solve ──
            # Triggered only if linear solve exceeds yield AND caller opts in.
            # Linear FEA overstates stress in a yielded element; radial return
            # gives the true saturated value and the plastic strain history.
            if enable_plasticity and result.max_von_mises_mpa >= yield_mpa:
                # Tangent modulus ~E/100 is a representative engineering
                # figure for Ti-6Al-4V work-hardening slope (MMPDS-17,
                # ASM Handbook vol. 19 S-N slope tables). Real tangent
                # slope varies with plastic strain but a single-value
                # H is adequate for bridge-level reporting.
                H_pa = ti.youngs_modulus_pa / 100.0  # Ti-6Al-4V (MMPDS-17)
                nl = solver.solve_nonlinear(
                    yield_stress=ti.yield_strength_pa,
                    hardening_modulus=H_pa,
                    n_load_steps=6,
                    max_iter=40,
                    tol=1e-4,
                )
                result.plastic_yielded = bool(nl.yield_reached)
                result.plastic_strain_max = float(nl.plastic_strain.max())
                result.post_yield_max_von_mises_mpa = float(nl.max_stress) / 1e6
                # Safety factor after plastic correction is more honest:
                # use the post-yield saturated stress, not the linear overshoot.
                result.structural_safety_factor = (
                    yield_mpa / max(result.post_yield_max_von_mises_mpa, 0.001)
                )
                result.warnings.append(
                    f"Hull yielded (linear σ={result.max_von_mises_mpa:.0f} MPa "
                    f"> σ_y={yield_mpa:.0f} MPa). Post-yield σ_VM="
                    f"{result.post_yield_max_von_mises_mpa:.0f} MPa, "
                    f"peak p̄={result.plastic_strain_max:.3e}."
                )
                logger.info("bridge.plastic_fea",
                            plastic_yielded=result.plastic_yielded,
                            plastic_strain_max=result.plastic_strain_max,
                            post_yield_stress_mpa=result.post_yield_max_von_mises_mpa)

        except Exception as e:
            logger.error("bridge.fea_failed", error=str(e))

        # ── Step 3: Thermal FEA ──
        try:
            from aria.digital_twin.thermal_solver import ThermalSolver, ThermalMaterial

            # Simple thermal: reactor end hot, radiator end cold
            thermal_mat = ThermalMaterial(
                name="Ti-6Al-4V",
                conductivity_w_mk=6.7,
            )
            thermal_solver = ThermalSolver(mesh, thermal_mat)

            # BCs: reactor end (z=0) at 500K, radiator end (z=max) at 300K
            z_coords = mesh.points[:, 2]
            z_min = z_coords.min()
            z_max = z_coords.max()
            hot_nodes = [i for i, z in enumerate(z_coords) if z < z_min + 1.0]
            cold_nodes = [i for i, z in enumerate(z_coords) if z > z_max - 1.0]

            thermal_solver.fix_temperature(hot_nodes, temp_k=500.0)
            thermal_solver.fix_temperature(cold_nodes, temp_k=300.0)

            thermal_result = thermal_solver.solve()
            result.max_temperature_k = thermal_result.max_temp_k
            result.min_temperature_k = thermal_result.min_temp_k

            # Ti-6Al-4V max service temp ~600K
            result.thermal_margin_k = 600.0 - result.max_temperature_k
            if result.thermal_margin_k < 50:
                result.warnings.append(
                    f"Thermal margin only {result.thermal_margin_k:.0f}K "
                    f"(max {result.max_temperature_k:.0f}K, limit 600K)"
                )

            logger.info("bridge.thermal_fea",
                        max_temp_k=result.max_temperature_k,
                        thermal_margin_k=result.thermal_margin_k)

        except Exception as e:
            logger.error("bridge.thermal_failed", error=str(e))

        self._last_result = result
        return result

    def update_config(self, config: Any, result: TwinAnalysisResult) -> Any:
        """Feed twin results back into GenerationShipConfig.

        Updates config fields that were previously hand-tuned to use
        geometry-derived values.
        """
        if result.computed_mass_kg > 0:
            # Update ship mass to match actual geometry
            config.ship_mass_kg = result.computed_mass_kg
            logger.info("bridge.config_updated",
                        ship_mass_kg=result.computed_mass_kg)

        # Cross-section is a derived property of ShipParameters (π × r²),
        # no need to overwrite it here.

        return config

    def get_report(self) -> dict[str, Any]:
        """Get a human-readable report of the last analysis."""
        r = self._last_result
        if r is None:
            return {"status": "no analysis run yet"}

        return {
            "geometry": {
                "computed_mass_kg": r.computed_mass_kg,
                "hull_volume_m3": r.hull_volume_m3,
                "total_radiator_area_m2": r.total_radiator_area_m2,
                "mass_discrepancy_pct": r.mass_discrepancy_pct,
            },
            "structural": {
                "max_von_mises_mpa": r.max_von_mises_mpa,
                "max_displacement_mm": r.max_displacement_mm,
                "safety_factor": r.structural_safety_factor,
            },
            "thermal": {
                "max_temperature_k": r.max_temperature_k,
                "min_temperature_k": r.min_temperature_k,
                "thermal_margin_k": r.thermal_margin_k,
            },
            "warnings": r.warnings,
        }
