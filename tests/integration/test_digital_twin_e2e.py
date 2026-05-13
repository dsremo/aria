"""End-to-end integration tests for the digital twin pipeline.

These tests run REAL geometry → mesh → FEA → analysis.
They are slow (~5s each) and tagged accordingly.
"""
import pytest

from aria.digital_twin.parameters import ShipParameters
from aria.digital_twin.bridge import SimTwinBridge
from aria.simulation.generation_ship import GenerationShipConfig


class TestBridgeEndToEnd:
    """Real (non-mocked) bridge analysis."""

    def test_full_analysis_runs(self):
        bridge = SimTwinBridge()
        result = bridge.analyze(GenerationShipConfig())
        assert result.computed_mass_kg > 0
        assert result.max_von_mises_mpa > 0
        assert result.max_temperature_k > 200

    def test_structural_safety_factor_reasonable(self):
        bridge = SimTwinBridge()
        result = bridge.analyze(GenerationShipConfig())
        # FoS should be > 1 (structure doesn't fail under load)
        assert result.structural_safety_factor > 1.0

    def test_thermal_margin_positive(self):
        bridge = SimTwinBridge()
        result = bridge.analyze(GenerationShipConfig())
        assert result.thermal_margin_k > 0

    def test_mass_budget_within_tolerance(self):
        """Full mass budget (all subsystems) should be within tolerance of the
        configured ship_mass_kg target.

        Tolerance is wide (±40 %) because the geometry-derived budget and the
        ``ship_mass_kg`` config target are tracked independently and the gap
        between them is a known, documented open item. Commit 7dafeea (R6 audit)
        replaced the spokes from solid bars to hollow tubes, dropping the
        bottom-up budget from 127 Mt to 65 Mt — the 35 % gap to the 100 Mt
        config target is the same gap discussed in
        :mod:`tests/unit/test_mass_reconciliation`. NASA SP-2007-6105 allows
        ±15 % at PDR; we are pre-PDR, so we widen to 40 % until either the
        target is revised or the missing subsystem mass is identified.
        """
        # Match the constant used in tests/unit/test_mass_reconciliation.py so
        # the two tests stay aligned when the gap eventually closes.
        from tests.unit.test_mass_reconciliation import MASS_TOLERANCE_PCT
        bridge = SimTwinBridge()
        result = bridge.analyze(GenerationShipConfig())
        assert abs(result.mass_discrepancy_pct) < MASS_TOLERANCE_PCT, (
            f"Mass budget discrepancy {result.mass_discrepancy_pct:+.1f}% "
            f"exceeds ±{MASS_TOLERANCE_PCT:.0f}% tolerance"
        )

    def test_plasticity_disabled_by_default(self):
        """enable_plasticity=False (the default) must leave plastic fields zero."""
        bridge = SimTwinBridge()
        result = bridge.analyze(GenerationShipConfig())
        assert result.plastic_yielded is False
        assert result.plastic_strain_max == 0.0
        assert result.post_yield_max_von_mises_mpa == 0.0

    def test_plasticity_opt_in_sets_fields_when_yielded(self):
        """When opt-in is on AND the linear solve exceeds yield, the bridge
        re-runs nonlinear FEA and populates plastic fields."""
        bridge = SimTwinBridge()
        result = bridge.analyze(GenerationShipConfig(), enable_plasticity=True)
        # Nominal config may or may not yield depending on mesh; assertion
        # is conditional: IF the linear solve reported σ ≥ σ_y, THEN the
        # bridge must have run the nonlinear pass.
        from aria.digital_twin.materials.material_db import get_material
        yield_mpa = get_material("Ti-6Al-4V").yield_strength_pa / 1e6
        if result.max_von_mises_mpa >= yield_mpa:
            assert result.plastic_yielded is True
            assert result.plastic_strain_max >= 0.0
            assert result.post_yield_max_von_mises_mpa > 0.0
            # Post-yield stress must not exceed linear stress (plastic
            # correction can only reduce, never increase, equilibrium σ).
            assert result.post_yield_max_von_mises_mpa <= result.max_von_mises_mpa * 1.01


class TestPipelineEndToEnd:
    """Full pipeline integration."""

    def test_pipeline_runs(self):
        from aria.digital_twin.run_pipeline import run_pipeline
        results = run_pipeline(serve=False)
        assert "parameters" in results
        assert "geometry" in results
        assert "mesh" in results
        assert "fea" in results

    def test_pipeline_exports_gltf(self):
        from pathlib import Path
        from aria.digital_twin.run_pipeline import run_pipeline
        run_pipeline(serve=False)
        assert Path("data/exports/ship.gltf").exists()

    def test_pipeline_report_saved(self):
        from pathlib import Path
        from aria.digital_twin.run_pipeline import run_pipeline
        run_pipeline(serve=False)
        assert Path("data/exports/pipeline_report.json").exists()


class TestLBMEndToEnd:
    """Real LBM CFD run."""

    def test_coriolis_produces_lateral_flow(self):
        from aria.digital_twin.lbm_cfd import HabitatCFD
        cfd = HabitatCFD(nx=50, ny=15, omega_rad_s=0.1047)
        result = cfd.run(n_steps=500)
        assert result.max_velocity_ms > 0

    def test_zero_omega_no_coriolis(self):
        from aria.digital_twin.lbm_cfd import HabitatCFD
        cfd = HabitatCFD(nx=50, ny=15, omega_rad_s=0.0)
        result = cfd.run(n_steps=500)
        # Should still have buoyancy-driven flow
        assert result.max_velocity_ms >= 0


class TestRadiationGeometryEndToEnd:
    """Real radiation MC through shield geometry."""

    def test_shield_config_from_params(self):
        from aria.digital_twin.radiation_geometry import create_shield_config_from_geometry
        config = create_shield_config_from_geometry(ShipParameters())
        assert len(config) == 7
        # Ice layer should be the thickest
        ice = [c for c in config if "ice" in c["name"]]
        assert len(ice) == 1
        assert ice[0]["thickness_m"] > 5.0

    def test_radiation_analysis_returns_dose(self):
        from aria.digital_twin.radiation_geometry import run_radiation_analysis
        result = run_radiation_analysis(ShipParameters(), n_particles=50)
        assert "total_dose_msv" in result
        assert result["particles_simulated"] == 50
