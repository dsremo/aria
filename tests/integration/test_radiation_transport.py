"""Radiation-transport tests — analytical backend always-available;
GEANT4 backend conditional on geant4-pybind being installed."""

from __future__ import annotations

import math

import pytest

from aria.physics.radiation_transport import (
    AnalyticalBackend,
    DoseResult,
    Geant4Backend,
    available_backends,
    preferred_backend,
    simulate_dose,
)
from aria.physics.radiation_transport.analytical import (
    DENSITY_G_CM3,
    cucinotta_attenuation,
    proton_range_cm,
    proton_range_g_cm2,
)


# ── NIST PSTAR proton-range fit ─────────────────────────────────


class TestProtonRangeFit:
    def test_zero_energy_zero_range(self):
        assert proton_range_g_cm2(0.0) == 0.0

    def test_100mev_proton_in_aluminum_centimetres(self):
        # NIST PSTAR: 100 MeV proton in Al ≈ 9.7 g/cm² = 3.6 cm Al.
        # Our power-law fit gives:
        #   range_g_cm2 = 0.00203 × 100^1.79 ≈ 8.1 g/cm²
        # → 8.1 / 2.70 = 3.0 cm of Al.  Matches NIST within ~17%.
        cm = proton_range_cm("aluminum", 100.0)
        assert 2.5 <= cm <= 4.5  # acceptable for a screening fit

    def test_1gev_proton_in_polyethylene_metres_class(self):
        # NIST: 1 GeV proton range ≈ 305 g/cm² in water-equivalent.
        # In polyethylene (0.95 g/cm³): 305 / 0.95 ≈ 320 cm = 3.2 m.
        # Our fit: 0.00203 × 1000^1.79 ≈ 506 g/cm²; / 0.95 ≈ 533 cm.
        # Both are "metres-class", which is the operationally
        # important point for shielding-design.
        cm = proton_range_cm("polyethylene", 1000.0)
        assert 200 <= cm <= 800   # order-of-magnitude correct

    def test_unknown_material_rejected(self):
        with pytest.raises(ValueError, match="unknown material"):
            proton_range_cm("unobtainium", 100.0)


# ── Cucinotta GCR attenuation ───────────────────────────────────


class TestCucinottaAttenuation:
    def test_zero_thickness_no_attenuation(self):
        assert cucinotta_attenuation("aluminum", 0.0) == pytest.approx(1.0)

    def test_30g_cm2_aluminum_one_e_fold(self):
        # Cucinotta 2014 §6.4: λ_Al = 30 g/cm² → exp(-1) ≈ 0.368.
        assert cucinotta_attenuation("aluminum", 30.0) == pytest.approx(
            math.exp(-1.0), rel=0.01,
        )

    def test_polyethylene_better_than_aluminum_per_g_cm2(self):
        # PE has lower λ (18 g/cm²) than Al (30) → more attenuation
        # per g/cm² (PE is well-known as a better space-radiation
        # shield per unit mass than Al — Cucinotta 2014 §6.5).
        att_pe = cucinotta_attenuation("polyethylene", 30.0)
        att_al = cucinotta_attenuation("aluminum", 30.0)
        assert att_pe < att_al

    def test_negative_thickness_rejected(self):
        with pytest.raises(ValueError):
            cucinotta_attenuation("aluminum", -1.0)


# ── Analytical backend ──────────────────────────────────────────


class TestAnalyticalBackend:
    def test_always_available(self):
        assert AnalyticalBackend().is_available() is True

    def test_compute_dose_returns_DoseResult_shape(self):
        result = AnalyticalBackend().compute_dose(
            material="aluminum",
            thickness_cm=2.0,
            particle="proton",
            energy_mev=100.0,
            fluence_per_cm2=1e10,
        )
        assert isinstance(result, DoseResult)
        assert result.backend_name == "analytical"
        # ±20 % band:
        assert result.dose_mgy_low <= result.dose_mgy_central
        assert result.dose_mgy_central <= result.dose_mgy_high
        assert result.dose_mgy_low == pytest.approx(
            result.dose_mgy_central * 0.80, rel=0.001,
        )

    def test_thicker_shield_lower_dose(self):
        ana = AnalyticalBackend()
        thin = ana.compute_dose(
            material="aluminum", thickness_cm=1.0,
            particle="proton", energy_mev=200.0,
            fluence_per_cm2=1e10,
        )
        thick = ana.compute_dose(
            material="aluminum", thickness_cm=10.0,
            particle="proton", energy_mev=200.0,
            fluence_per_cm2=1e10,
        )
        assert thick.dose_mgy_central <= thin.dose_mgy_central

    def test_negative_thickness_rejected(self):
        with pytest.raises(ValueError):
            AnalyticalBackend().compute_dose(
                material="aluminum", thickness_cm=-1.0,
                particle="proton", energy_mev=100.0,
                fluence_per_cm2=1.0,
            )

    def test_zero_energy_rejected(self):
        with pytest.raises(ValueError):
            AnalyticalBackend().compute_dose(
                material="aluminum", thickness_cm=1.0,
                particle="proton", energy_mev=0.0,
                fluence_per_cm2=1.0,
            )

    def test_negative_fluence_rejected(self):
        with pytest.raises(ValueError):
            AnalyticalBackend().compute_dose(
                material="aluminum", thickness_cm=1.0,
                particle="proton", energy_mev=100.0,
                fluence_per_cm2=-1.0,
            )

    def test_alpha_particle_marked_out_of_validation(self):
        # Analytical backend only does protons; alpha returns a
        # zero-dose result with confidence = "OUT-OF-VALIDATION".
        result = AnalyticalBackend().compute_dose(
            material="aluminum", thickness_cm=1.0,
            particle="alpha", energy_mev=100.0,
            fluence_per_cm2=1e10,
        )
        assert result.dose_mgy_central == 0.0
        assert result.confidence == "OUT-OF-VALIDATION"


# ── GEANT4 backend (optional) ───────────────────────────────────


class TestGeant4Backend:
    def test_construction_does_not_raise_without_geant4(self):
        # Constructing the backend on a system without geant4-pybind
        # must not raise (the import is lazy).
        backend = Geant4Backend()
        assert backend.name == "geant4"

    def test_unavailable_when_geant4_pybind_missing(self):
        # CI does not install geant4-pybind, so this must report
        # not available.
        backend = Geant4Backend()
        # Note: if a future CI image ships GEANT4, this assertion
        # flips to True automatically — no test rewrite needed.
        if backend.is_available():
            pytest.skip(
                "geant4-pybind installed; skipping unavailable-path test"
            )
        assert backend.is_available() is False

    def test_compute_dose_raises_actionable_importerror_when_unavailable(self):
        backend = Geant4Backend()
        if backend.is_available():
            pytest.skip("geant4-pybind installed; skipping import-error test")
        with pytest.raises(ImportError, match="geant4-pybind"):
            backend.compute_dose(
                material="aluminum", thickness_cm=1.0,
                particle="proton", energy_mev=100.0,
                fluence_per_cm2=1e10,
            )


# ── API-layer auto-selection ────────────────────────────────────


class TestPublicApi:
    def test_available_backends_always_includes_analytical(self):
        backends = available_backends()
        assert "analytical" in backends

    def test_preferred_backend_falls_back_when_geant4_missing(self):
        # In the CI environment without geant4-pybind, preferred
        # should be analytical.
        if "geant4" in available_backends():
            pytest.skip("geant4 installed; preferred fallback path inactive")
        assert preferred_backend() == "analytical"

    def test_simulate_dose_auto_falls_back_to_analytical_when_geant4_missing(self):
        if "geant4" in available_backends():
            pytest.skip("geant4 installed; auto picks geant4 instead")
        result = simulate_dose(
            material="aluminum",
            thickness_cm=2.0,
            particle="proton",
            energy_mev=100.0,
            fluence_per_cm2=1e10,
            backend="auto",
        )
        assert result.backend_name == "analytical"

    def test_simulate_dose_analytical_explicit(self):
        result = simulate_dose(
            material="polyethylene",
            thickness_cm=5.0,
            particle="proton",
            energy_mev=200.0,
            fluence_per_cm2=1e9,
            backend="analytical",
        )
        assert result.backend_name == "analytical"
        assert result.confidence == "±20% screening"

    def test_simulate_dose_geant4_explicit_raises_when_missing(self):
        if "geant4" in available_backends():
            pytest.skip("geant4 installed; explicit-geant4 path active")
        with pytest.raises(ImportError, match="geant4-pybind"):
            simulate_dose(
                material="aluminum",
                thickness_cm=2.0,
                particle="proton",
                energy_mev=100.0,
                fluence_per_cm2=1e10,
                backend="geant4",
            )

    def test_invalid_backend_choice_rejected(self):
        with pytest.raises(ValueError, match="backend must be"):
            simulate_dose(
                material="aluminum",
                thickness_cm=1.0,
                particle="proton",
                energy_mev=100.0,
                fluence_per_cm2=1e9,
                backend="laplace",   # not a real choice
            )

    def test_dose_result_immutable(self):
        result = simulate_dose(
            material="aluminum", thickness_cm=2.0,
            particle="proton", energy_mev=100.0,
            fluence_per_cm2=1e10, backend="analytical",
        )
        # frozen dataclass — assigning fields raises FrozenInstanceError.
        with pytest.raises(Exception):
            result.dose_mgy_central = 1.0   # type: ignore[misc]


# ── Material density table ──────────────────────────────────────


class TestMaterialDensities:
    def test_aluminum_2700_kg_m3(self):
        # MMPDS-2025 §3.6: Al-6061-T6 density 2.70 g/cm³ = 2700 kg/m³.
        assert DENSITY_G_CM3["aluminum"] == pytest.approx(2.70)

    def test_polyethylene_lower_than_aluminum(self):
        assert DENSITY_G_CM3["polyethylene"] < DENSITY_G_CM3["aluminum"]

    def test_tungsten_higher_than_lead(self):
        assert DENSITY_G_CM3["tungsten"] > DENSITY_G_CM3["lead"]

    def test_water_equals_one(self):
        assert DENSITY_G_CM3["water"] == pytest.approx(1.00)
