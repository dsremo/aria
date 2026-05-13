"""Tests for cabin humidity, dew point, and condensation risk models.

Validates:
1.  saturation_vapour_pressure_kPa: known value at 100°C = 101.325 kPa.
2.  saturation_vapour_pressure_kPa: at 0°C ≈ 0.611 kPa.
3.  saturation_vapour_pressure_kPa: monotonically increasing.
4.  dew_point_K: round-trip (sat pressure → dew point → temp).
5.  dew_point_K: returns 0 at zero vapour pressure.
6.  dew_point_K: T_dew < T_air when RH < 100%.
7.  dew_point_K: T_dew = T_air at RH = 100%.
8.  relative_humidity: 1.0 when vapour_pressure == saturation pressure.
9.  relative_humidity: clamped to [0, 1].
10. relative_humidity: ~0.50 at half saturation pressure.
11. vapour_pressure_from_rh_kPa: inverse of relative_humidity.
12. specific_humidity_kg_per_kg: positive at nominal conditions.
13. specific_humidity_kg_per_kg: increases with RH at constant T.
14. condensation_rate_kg_m2_s: zero when surface warmer than dew point.
15. condensation_rate_kg_m2_s: positive when surface below dew point.
16. condensation_rate_kg_m2_s: increases as surface gets colder.
17. is_condensation_risk: False when surface above dew point.
18. is_condensation_risk: True when surface below dew point.
19. comfort_assessment: 'comfortable' at 45% RH.
20. comfort_assessment: 'dry' below 30%, 'humid' at 65%, 'mold_risk' at 75%.
21. ISS nominal: 40–60% RH at 295 K → dew point ≈ 280–287 K.
22. Cold avionics panel (270 K) at nominal humidity → condensation risk True.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.life_support.humidity import (
    RH_COMFORT_MAX,
    RH_COMFORT_MIN,
    RH_MOLD_THRESHOLD,
    comfort_assessment,
    condensation_rate_kg_m2_s,
    dew_point_K,
    is_condensation_risk,
    relative_humidity,
    saturation_vapour_pressure_kPa,
    specific_humidity_kg_per_kg,
    vapour_pressure_from_rh_kPa,
)


class TestSaturationVapourPressure:

    def test_at_0C(self):
        # e_s(0°C) ≈ 0.611 kPa (Alduchov 1996)
        e = saturation_vapour_pressure_kPa(273.15)
        assert abs(e - 0.611) < 0.005

    def test_at_100C_approximately_101_kPa(self):
        # Water boils at 100°C → e_s ≈ 101.325 kPa at sea level
        e = saturation_vapour_pressure_kPa(373.15)
        assert 90 < e < 115, f"e_s(100°C) = {e:.1f} kPa"

    def test_at_20C(self):
        # e_s(20°C) ≈ 2.34 kPa (standard reference)
        e = saturation_vapour_pressure_kPa(293.15)
        assert 2.0 < e < 2.7, f"e_s(20°C) = {e:.3f} kPa"

    def test_monotonically_increasing(self):
        temps = [250, 270, 293, 320, 350]
        pressures = [saturation_vapour_pressure_kPa(T) for T in temps]
        assert all(pressures[i] < pressures[i+1] for i in range(len(pressures)-1))

    def test_positive_always(self):
        for T in [230.0, 260.0, 300.0, 340.0]:
            assert saturation_vapour_pressure_kPa(T) > 0.0


class TestDewPoint:

    def test_round_trip(self):
        T = 295.0
        e_sat = saturation_vapour_pressure_kPa(T)
        T_dew = dew_point_K(e_sat)
        assert abs(T_dew - T) < 0.1  # round-trip to 0.1 K

    def test_zero_at_zero_vapour_pressure(self):
        assert dew_point_K(0.0) == 0.0

    def test_dew_below_air_temperature_when_not_saturated(self):
        T_air = 295.0
        rh = 0.60
        e = vapour_pressure_from_rh_kPa(T_air, rh)
        T_dew = dew_point_K(e)
        assert T_dew < T_air

    def test_dew_equals_air_at_saturation(self):
        T = 295.0
        e_sat = saturation_vapour_pressure_kPa(T)
        T_dew = dew_point_K(e_sat)
        assert abs(T_dew - T) < 0.1

    def test_known_value_20c_50pct_rh(self):
        # At 20°C, 50% RH: dew point ≈ 9.3°C = 282.45 K
        T = 293.15
        e = vapour_pressure_from_rh_kPa(T, 0.50)
        T_dew = dew_point_K(e)
        assert 280.0 < T_dew < 285.0, f"T_dew(20°C, 50% RH) = {T_dew - 273.15:.1f}°C"


class TestRelativeHumidity:

    def test_unity_at_saturation(self):
        T = 295.0
        e_sat = saturation_vapour_pressure_kPa(T)
        rh = relative_humidity(T, e_sat)
        assert abs(rh - 1.0) < 1e-9

    def test_half_at_half_saturation(self):
        T = 295.0
        e_sat = saturation_vapour_pressure_kPa(T)
        rh = relative_humidity(T, 0.5 * e_sat)
        assert abs(rh - 0.5) < 1e-9

    def test_clamped_above_one(self):
        T = 295.0
        e_sat = saturation_vapour_pressure_kPa(T)
        rh = relative_humidity(T, 2.0 * e_sat)
        assert rh == 1.0

    def test_clamped_below_zero(self):
        assert relative_humidity(295.0, -1.0) == 0.0

    def test_zero_at_zero_vapour(self):
        assert relative_humidity(295.0, 0.0) == 0.0


class TestVapourPressureFromRH:

    def test_inverse_of_relative_humidity(self):
        T = 295.0
        rh = 0.55
        e = vapour_pressure_from_rh_kPa(T, rh)
        rh_back = relative_humidity(T, e)
        assert abs(rh_back - rh) < 1e-9

    def test_zero_at_zero_rh(self):
        assert vapour_pressure_from_rh_kPa(295.0, 0.0) == 0.0

    def test_equals_saturation_at_100_pct(self):
        T = 295.0
        e_sat = saturation_vapour_pressure_kPa(T)
        e = vapour_pressure_from_rh_kPa(T, 1.0)
        assert abs(e - e_sat) < 1e-9


class TestSpecificHumidity:

    def test_positive_at_nominal(self):
        q = specific_humidity_kg_per_kg(295.0, 101.325, 0.50)
        assert q > 0.0

    def test_increases_with_rh(self):
        q_low = specific_humidity_kg_per_kg(295.0, 101.325, 0.30)
        q_high = specific_humidity_kg_per_kg(295.0, 101.325, 0.70)
        assert q_high > q_low

    def test_zero_at_zero_rh(self):
        q = specific_humidity_kg_per_kg(295.0, 101.325, 0.0)
        assert q == 0.0

    def test_bounded_below_one(self):
        q = specific_humidity_kg_per_kg(295.0, 101.325, 1.0)
        assert 0.0 < q < 1.0


class TestCondensation:

    def test_zero_when_surface_warm(self):
        T_air = 295.0
        rh = 0.60
        e = vapour_pressure_from_rh_kPa(T_air, rh)
        T_dew = dew_point_K(e)
        rate = condensation_rate_kg_m2_s(T_dew, T_dew + 5.0)  # surface above dew point
        assert rate == 0.0

    def test_positive_when_surface_cold(self):
        T_dew = 282.0  # ~9°C
        T_surface = 270.0  # cold avionics panel
        rate = condensation_rate_kg_m2_s(T_dew, T_surface)
        assert rate > 0.0

    def test_increases_as_surface_gets_colder(self):
        T_dew = 285.0
        rate1 = condensation_rate_kg_m2_s(T_dew, 283.0)  # 2K below dew
        rate2 = condensation_rate_kg_m2_s(T_dew, 275.0)  # 10K below dew
        assert rate2 > rate1

    def test_proportional_to_delta_T(self):
        T_dew = 285.0
        rate1 = condensation_rate_kg_m2_s(T_dew, 283.0, air_density_kg_m3=1.2)
        rate2 = condensation_rate_kg_m2_s(T_dew, 281.0, air_density_kg_m3=1.2)
        assert abs(rate2 / rate1 - 2.0) < 0.01


class TestCondensationRisk:

    def test_no_risk_warm_surface(self):
        assert not is_condensation_risk(295.0, 0.60, 290.0)

    def test_risk_cold_avionics(self):
        # ISS: cabin 295 K, 50% RH → dew ≈ 282 K; cold panel at 270 K
        assert is_condensation_risk(295.0, 0.50, 270.0)

    def test_no_risk_at_low_humidity(self):
        # Very dry air: dew point very low
        assert not is_condensation_risk(295.0, 0.10, 280.0)


class TestComfortAssessment:

    def test_dry(self):
        assert comfort_assessment(0.20) == "dry"

    def test_comfortable_low(self):
        assert comfort_assessment(RH_COMFORT_MIN) == "comfortable"

    def test_comfortable_mid(self):
        assert comfort_assessment(0.45) == "comfortable"

    def test_comfortable_high(self):
        assert comfort_assessment(RH_COMFORT_MAX) == "comfortable"

    def test_humid(self):
        assert comfort_assessment(0.65) == "humid"

    def test_mold_risk(self):
        assert comfort_assessment(RH_MOLD_THRESHOLD + 0.01) == "mold_risk"


class TestIssScenario:

    def test_iss_nominal_dew_point_range(self):
        """ISS nominal: 295 K, 40–60% RH → dew point in 281–287 K range."""
        for rh in [0.40, 0.50, 0.60]:
            e = vapour_pressure_from_rh_kPa(295.0, rh)
            T_dew = dew_point_K(e)
            assert 278.0 < T_dew < 290.0, (
                f"T_dew at RH={rh:.0%}: {T_dew - 273.15:.1f}°C"
            )

    def test_cold_panel_condensation(self):
        """Cold avionics at 270 K in 50% RH cabin → condensation."""
        assert is_condensation_risk(295.0, 0.50, 270.0)

    def test_comfortable_habitat(self):
        assert comfort_assessment(0.50) == "comfortable"
