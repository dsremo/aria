from __future__ import annotations

import pytest

from aria.physics.bioregen.eden_iss_per_crop import (
    CROP_PROFILES,
    CropProfile,
    PerCropGreenhouse,
    water_closure_balance,
)


class TestCropProfiles:
    def test_six_profiles_present(self):
        assert len(CROP_PROFILES) >= 6
        names = {profile.name for profile in CROP_PROFILES}
        assert "lettuce" in names
        assert "cucumber" in names
        assert "tomato_dwarf" in names

    def test_growth_area_shares_sum_to_unity(self):
        total = sum(profile.growth_area_share for profile in CROP_PROFILES)
        assert abs(total - 1.0) < 0.01

    def test_each_profile_has_citation(self):
        for profile in CROP_PROFILES:
            assert profile.citation


class TestPerCropGreenhouse:
    def test_step_day_returns_active_crops(self):
        gh = PerCropGreenhouse()
        active = gh.step_day(sol=20)
        names = {point.crop for point in active}
        assert names

    def test_integrate_30_day_produces_yield(self):
        gh = PerCropGreenhouse()
        run = gh.integrate(duration_days=30)
        assert run.total_produce_kg() > 0
        assert run.total_o2_kg() > 0
        assert run.total_water_kg() > 0

    def test_microgravity_lowers_water(self):
        gh_1g = PerCropGreenhouse(microgravity=False)
        gh_0g = PerCropGreenhouse(microgravity=True)
        run_1g = gh_1g.integrate(duration_days=30)
        run_0g = gh_0g.integrate(duration_days=30)
        assert run_0g.total_water_kg() < run_1g.total_water_kg()

    def test_microgravity_lowers_gas_exchange(self):
        gh_1g = PerCropGreenhouse(microgravity=False)
        gh_0g = PerCropGreenhouse(microgravity=True)
        run_1g = gh_1g.integrate(duration_days=30)
        run_0g = gh_0g.integrate(duration_days=30)
        assert run_0g.total_o2_kg() < run_1g.total_o2_kg()


class TestWaterClosure:
    def test_high_recovery_closes(self):
        check = water_closure_balance(
            transpired_kg=510.0, recovery_efficiency=0.92,
        )
        assert check.closes
        assert 0.91 <= check.closure_pct <= 0.93

    def test_low_recovery_fails(self):
        check = water_closure_balance(
            transpired_kg=510.0, recovery_efficiency=0.50,
        )
        assert not check.closes

    def test_zero_transpiration_returns_unity(self):
        check = water_closure_balance(transpired_kg=0.0)
        assert check.closes


class TestEdenIssEnvelope:
    def test_281_day_total_in_published_envelope(self):
        gh = PerCropGreenhouse(microgravity=False)
        run = gh.integrate(duration_days=281)
        total = run.total_produce_kg()
        assert 150.0 <= total <= 500.0, (
            f"281-day total {total:.1f} kg outside EDEN ISS published "
            "envelope (~268 kg, allow ±50%)"
        )
