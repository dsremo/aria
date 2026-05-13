"""Tests for relativistic.py — special relativity for interstellar travel."""

import math
import pytest

from aria.simulation.relativistic_physics import (
    C, LY_METERS as LY_M, G0,
    lorentz_gamma, beta_from_gamma,
    time_dilation, earth_time_from_proper,
    length_contraction,
    relativistic_rocket_equation as relativistic_rocket_velocity,
    relativistic_mass_ratio,
    plan_journey, doppler_shift,
    InterstellarJourney,
)


class TestLorentzGamma:

    def test_gamma_at_rest(self):
        assert lorentz_gamma(0.0) == pytest.approx(1.0)

    def test_gamma_at_half_c(self):
        """γ at 0.5c = 1/sqrt(1-0.25) = 1/sqrt(0.75) ≈ 1.1547."""
        assert lorentz_gamma(0.5 * C) == pytest.approx(1.1547, rel=0.001)

    def test_gamma_at_09c(self):
        """γ at 0.9c ≈ 2.294."""
        assert lorentz_gamma(0.9 * C) == pytest.approx(2.294, rel=0.001)

    def test_gamma_at_099c(self):
        """γ at 0.99c ≈ 7.089."""
        assert lorentz_gamma(0.99 * C) == pytest.approx(7.089, rel=0.001)

    def test_gamma_exceeds_c_raises(self):
        with pytest.raises(ValueError):
            lorentz_gamma(C)

    def test_gamma_always_ge_one(self):
        for beta in [0.0, 0.01, 0.1, 0.5, 0.9, 0.99]:
            assert lorentz_gamma(beta * C) >= 1.0


class TestTimeDilation:

    def test_no_dilation_at_rest(self):
        assert time_dilation(100.0, 0.0) == pytest.approx(100.0)

    def test_ship_time_less_than_earth_time(self):
        """Ship time should always be ≤ Earth time."""
        for beta in [0.1, 0.5, 0.9]:
            tau = time_dilation(1000.0, beta * C)
            assert tau <= 1000.0

    def test_round_trip_consistency(self):
        """earth_time_from_proper should invert time_dilation."""
        t_earth = 1000.0
        v = 0.6 * C
        tau = time_dilation(t_earth, v)
        t_back = earth_time_from_proper(tau, v)
        assert t_back == pytest.approx(t_earth, rel=1e-9)

    def test_09c_dilation(self):
        """At 0.9c, ship experiences 43.6% of Earth time."""
        tau = time_dilation(100.0, 0.9 * C)
        assert tau == pytest.approx(43.6, rel=0.01)


class TestLengthContraction:

    def test_no_contraction_at_rest(self):
        assert length_contraction(100.0, 0.0) == pytest.approx(100.0)

    def test_contracted_at_speed(self):
        L = length_contraction(100.0, 0.9 * C)
        assert L < 100.0

    def test_09c_contraction(self):
        """At 0.9c, lengths contract to ~43.6%."""
        L = length_contraction(100.0, 0.9 * C)
        assert L == pytest.approx(43.6, rel=0.01)


class TestRelativisticRocket:

    def test_newtonian_limit(self):
        """At low exhaust velocity, should match Tsiolkovsky."""
        v_e = 4400.0  # chemical
        R = 3.0
        v_rel = relativistic_rocket_velocity(v_e, R)
        v_newt = v_e * math.log(R)
        assert v_rel == pytest.approx(v_newt, rel=0.01)

    def test_speed_below_c(self):
        """Even with extreme mass ratio, speed must be < c."""
        v = relativistic_rocket_velocity(0.1 * C, 1000.0)
        assert v < C

    def test_higher_ratio_higher_speed(self):
        v1 = relativistic_rocket_velocity(0.1 * C, 5.0)
        v2 = relativistic_rocket_velocity(0.1 * C, 50.0)
        assert v2 > v1

    def test_unit_ratio_raises(self):
        """Mass ratio = 1.0 means no propellant — should raise ValueError."""
        with pytest.raises(ValueError):
            relativistic_rocket_velocity(0.1 * C, 1.0)

    def test_fusion_to_significant_fraction_of_c(self):
        """Fusion (v_e=0.1c) with mass ratio 10: v = c*tanh(0.1*ln10) ≈ 0.226c."""
        v = relativistic_rocket_velocity(0.1 * C, 10.0)
        assert 0.15 * C < v < 0.35 * C


class TestMassRatio:

    def test_inverse_of_velocity(self):
        """mass_ratio should be inverse of rocket_velocity."""
        v_e = 0.1 * C
        R = 10.0
        v = relativistic_rocket_velocity(v_e, R)
        R_back = relativistic_mass_ratio(v, v_e)
        assert R_back == pytest.approx(R, rel=0.01)

    def test_chemical_interstellar_infeasible(self):
        """Chemical propulsion to 0.1c requires infinite mass ratio."""
        R = relativistic_mass_ratio(0.1 * C, 4400.0)
        assert R == float('inf')

    def test_fusion_interstellar_feasible(self):
        """Fusion at v_e=30,000 km/s to 0.1c should be feasible (R < 100)."""
        R = relativistic_mass_ratio(0.1 * C, 30_000_000.0)
        assert R < 100


class TestJourneyPlanner:

    def test_alpha_centauri_at_01c(self):
        j = plan_journey("Alpha Centauri", 4.37, 0.1)
        assert j.earth_time_yr == pytest.approx(43.7, rel=0.01)
        assert j.ship_time_yr < j.earth_time_yr

    def test_ship_time_less_at_higher_speed(self):
        j1 = plan_journey("AC", 4.37, 0.1)
        j2 = plan_journey("AC", 4.37, 0.9)
        assert j2.ship_time_yr < j1.ship_time_yr

    def test_signal_delay_equals_distance(self):
        j = plan_journey("AC", 4.37, 0.5)
        assert j.one_way_signal_yr == pytest.approx(4.37)

    def test_returns_journey(self):
        j = plan_journey("AC", 4.37, 0.1)
        assert isinstance(j, InterstellarJourney)


class TestDoppler:

    def test_approaching_blueshift(self):
        """Approaching source should blueshift (higher frequency)."""
        f_obs = doppler_shift(1.0, 0.5, forward=True)
        assert f_obs > 1.0

    def test_receding_redshift(self):
        """Receding source should redshift (lower frequency)."""
        f_obs = doppler_shift(1.0, 0.5, forward=False)
        assert f_obs < 1.0

    def test_symmetric(self):
        """Approaching and receding shifts should be reciprocals."""
        f_app = doppler_shift(1.0, 0.3, forward=True)
        f_rec = doppler_shift(1.0, 0.3, forward=False)
        assert f_app * f_rec == pytest.approx(1.0, rel=1e-9)

    def test_exceeds_c_raises(self):
        with pytest.raises(ValueError):
            doppler_shift(1.0, 1.0)
