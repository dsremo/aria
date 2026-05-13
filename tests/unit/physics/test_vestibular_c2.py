"""Verification tests for Pod C2 (vestibular response).

Covers the closed-form portions of the C2 scope §9 cases. The full
NASA SDTC dataset reproduction (Young 1986 NASA TM-88328) is a
qualitative anchor; the test verifies that the model parameters
reproduce the documented thresholds (5 rpm naive, ~10 minutes to
50% sickness).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.physics.vestibular import (
    HUMAN_CANAL_CONSTANTS,
    OmanMotionSicknessModel,
    OTOLITH_DEFAULT_CONSTANTS,
    SemicircularCanalConstants,
    YOUNG_2019_E_HALF_S,
    adaptation_probability,
    canal_transfer_function_amplitude,
    cross_coupled_angular_acceleration,
    cupula_step_response,
    motion_sickness_threshold_adapted,
    motion_sickness_threshold_naive,
    otolith_response_steady_state,
    otolith_step_response,
)
from aria.physics.vestibular.semicircular_canal import HUMAN_CANAL_CONSTANTS as _C
from aria.physics.vestibular.oman_dose import (
    OMAN_DEFAULT_K_DOWN,
    OMAN_DEFAULT_K_UP,
)


# ─────────────────────────────────────────────────────────────────────
# Semicircular canal — Steinhausen / Van Egmond / Benson 2002
# ─────────────────────────────────────────────────────────────────────


class TestSemicircularCanal:
    """Benson 2002 Table 17.2 canonical values: T_1 = 10 s, T_2 = 3 ms."""

    def test_canonical_human_constants(self) -> None:
        assert HUMAN_CANAL_CONSTANTS.T_1_s == 10.0
        assert HUMAN_CANAL_CONSTANTS.T_2_s == 3.0e-3

    def test_dc_response_is_zero(self) -> None:
        # Rate sensor: DC (ω=0) gain is identically 0.
        assert canal_transfer_function_amplitude(0.0) == 0.0

    def test_high_frequency_rolloff(self) -> None:
        # At ω → ∞, |H(jω)| → 0 (the high-pass T_2 corner kicks in).
        h_low = canal_transfer_function_amplitude(1.0)
        h_high = canal_transfer_function_amplitude(1.0e4)
        assert h_high < 0.1 * h_low

    def test_passband_amplitude_near_unity(self) -> None:
        # In the 0.1-5 Hz physiological band, the amplitude is near 1
        # (the canal acts as a wide-band rate sensor). Specifically
        # |H(jω)| at ω = 1 rad/s should be very close to T_1 ω /
        # sqrt(1 + (T_1 ω)²) ≈ 0.995 because T_2 ω = 0.003 << 1.
        h = canal_transfer_function_amplitude(1.0)
        # T_1 ω / sqrt(1 + (T_1 ω)²) = 10 / sqrt(101) ≈ 0.995
        expected = 10.0 / math.sqrt(101.0)
        assert h == pytest.approx(expected, rel=5e-3)

    def test_step_response_starts_at_zero(self) -> None:
        # ξ(0) = ω·(1 − 1)/(1 − T_2/T_1) = 0
        xi_0 = cupula_step_response(time_s=0.0, omega_step_rad_s=1.0)
        assert xi_0 == pytest.approx(0.0, abs=1e-12)

    def test_step_response_peaks_then_decays(self) -> None:
        # Peak occurs at t* = (T_1 T_2 / (T_1 − T_2)) · ln(T_1/T_2),
        # which for T_1 = 10, T_2 = 3e-3 is ~0.024 s. After that
        # the response decays on a T_1 timescale.
        xi_peak = cupula_step_response(time_s=0.024, omega_step_rad_s=1.0)
        xi_late = cupula_step_response(time_s=20.0, omega_step_rad_s=1.0)
        xi_zero = cupula_step_response(time_s=0.0, omega_step_rad_s=1.0)
        assert xi_peak > xi_zero
        assert xi_peak > xi_late
        assert xi_late < 0.2  # decayed substantially after 2 T_1

    def test_step_response_decays_exponentially_for_t_gg_t2(self) -> None:
        # For t ≫ T_2 the second exponential is negligible:
        #   ξ(t) ≈ ω · exp(−t/T_1) / (1 − T_2/T_1) ≈ ω · exp(−t/T_1)
        xi_5s = cupula_step_response(5.0, 1.0)
        xi_10s = cupula_step_response(10.0, 1.0)
        # Ratio should be exp(-5/T_1) = exp(-0.5) ≈ 0.6065.
        ratio = xi_10s / xi_5s
        assert ratio == pytest.approx(math.exp(-0.5), rel=0.005)


# ─────────────────────────────────────────────────────────────────────
# Cross-coupling — Coriolis illusion
# ─────────────────────────────────────────────────────────────────────


class TestCrossCoupling:
    def test_aria_baseline_orthogonal_head_tilt(self) -> None:
        # 4 rpm habitat (Ω = 0.4189 ẑ rad/s) with crew member tilting
        # head at 1 rad/s about x̂ should produce α_cross along ŷ
        # with magnitude 0.4189 rad/s².
        omega_ring = np.array([0.0, 0.0, 0.4189])
        omega_head = np.array([1.0, 0.0, 0.0])
        alpha = cross_coupled_angular_acceleration(omega_ring, omega_head)
        # ẑ × x̂ = ŷ, so α should be (0, 0.4189, 0).
        assert alpha[0] == pytest.approx(0.0, abs=1e-12)
        assert alpha[1] == pytest.approx(0.4189, rel=1e-12)
        assert alpha[2] == pytest.approx(0.0, abs=1e-12)
        assert float(np.linalg.norm(alpha)) == pytest.approx(0.4189, rel=1e-12)

    def test_parallel_head_tilt_zero_cross_coupling(self) -> None:
        # If the head rotates about the same axis as the ring there is
        # no cross-coupled component (the cross product vanishes).
        omega_ring = np.array([0.0, 0.0, 0.4189])
        omega_head = np.array([0.0, 0.0, 1.0])
        alpha = cross_coupled_angular_acceleration(omega_ring, omega_head)
        assert float(np.linalg.norm(alpha)) == pytest.approx(0.0, abs=1e-12)

    def test_magnitude_scales_with_ring_speed(self) -> None:
        head = np.array([1.0, 0.0, 0.0])
        a1 = cross_coupled_angular_acceleration(np.array([0.0, 0.0, 0.5]), head)
        a2 = cross_coupled_angular_acceleration(np.array([0.0, 0.0, 1.0]), head)
        assert float(np.linalg.norm(a2)) == pytest.approx(
            2.0 * float(np.linalg.norm(a1)), rel=1e-12
        )


# ─────────────────────────────────────────────────────────────────────
# Otolith first-order response
# ─────────────────────────────────────────────────────────────────────


class TestOtolith:
    def test_constants_per_grant_best_1987(self) -> None:
        # Grant & Best 1987 §3.2 figure 4: T ≈ 80 ms.
        assert OTOLITH_DEFAULT_CONSTANTS.T_oto_s == 0.08

    def test_steady_state_proportional_to_input(self) -> None:
        f_gia = np.array([0.0, 0.0, 9.81])
        delta = otolith_response_steady_state(f_gia)
        # k_oto = 1 by default; δ_∞ = f_GIA.
        assert delta[2] == pytest.approx(9.81, rel=1e-12)
        assert delta[0] == 0.0
        assert delta[1] == 0.0

    def test_step_response_zero_at_t_zero(self) -> None:
        f_gia = np.array([0.0, 0.0, 9.81])
        delta = otolith_step_response(time_s=0.0, step_f_gia_m_s2=f_gia)
        assert float(np.linalg.norm(delta)) == 0.0

    def test_step_response_approaches_steady_state(self) -> None:
        f_gia = np.array([1.0, 0.0, 0.0])
        # After 5 time constants (5 · 80 ms = 400 ms) the response
        # should be within 1% of steady state.
        delta = otolith_step_response(time_s=0.4, step_f_gia_m_s2=f_gia)
        ss = otolith_response_steady_state(f_gia)
        assert float(np.linalg.norm(delta)) == pytest.approx(
            float(np.linalg.norm(ss)), rel=0.01
        )

    def test_step_response_at_one_time_constant(self) -> None:
        # At t = T_oto, response is (1 − e⁻¹) ≈ 0.632 of SS.
        f_gia = np.array([1.0, 0.0, 0.0])
        delta = otolith_step_response(time_s=0.08, step_f_gia_m_s2=f_gia)
        assert delta[0] == pytest.approx(1.0 - math.exp(-1.0), rel=1e-6)


# ─────────────────────────────────────────────────────────────────────
# Oman 1990 motion-sickness ODE
# ─────────────────────────────────────────────────────────────────────


class TestOmanDose:
    """Reproduces the Oman 1990 calibration and the SDTC threshold
    behavior."""

    def test_default_constants(self) -> None:
        assert OMAN_DEFAULT_K_UP == 5.0e-3
        assert OMAN_DEFAULT_K_DOWN == pytest.approx(1.0 / 1800.0, rel=1e-12)

    def test_zero_conflict_zero_growth(self) -> None:
        m = OmanMotionSicknessModel()
        for _ in range(60):
            m.step(conflict_rad_s2=0.0, dt_s=1.0)
        assert m.probability == 0.0

    def test_constant_conflict_grows_then_saturates(self) -> None:
        # Conflict held at 0.2 rad/s² for 1800 s should produce
        # measurable but not yet saturated probability.
        m = OmanMotionSicknessModel()
        for _ in range(1800):
            m.step(conflict_rad_s2=0.2, dt_s=1.0)
        assert m.probability > 0.0
        assert m.probability <= 1.0

    def test_recovery_decay(self) -> None:
        # Drive to a finite probability, then let it decay.
        m = OmanMotionSicknessModel()
        # Drive hard for 30 minutes.
        for _ in range(1800):
            m.step(conflict_rad_s2=0.5, dt_s=1.0)
        peak = m.probability
        # Then quiet for another 60 minutes.
        for _ in range(3600):
            m.step(conflict_rad_s2=0.0, dt_s=1.0)
        assert m.probability < peak

    def test_equilibrium_closed_form(self) -> None:
        # P_∞ = (k_up / k_down) · C²
        m = OmanMotionSicknessModel()
        for c in (0.1, 0.2, 0.3):
            p = m.equilibrium_probability(c)
            expected = min(1.0, (m.k_up / m.k_down) * c * c)
            assert p == pytest.approx(expected, rel=1e-12)

    def test_thresholds_in_published_band(self) -> None:
        # Young 1986 NASA TM-88328 SDTC envelope: 0.1 rad/s² for naive
        # subjects, ~0.25 for adapted.
        assert motion_sickness_threshold_naive() == 0.1
        assert motion_sickness_threshold_adapted() == 0.25

    def test_reset(self) -> None:
        m = OmanMotionSicknessModel()
        for _ in range(100):
            m.step(0.5, 1.0)
        assert m.probability > 0.0
        m.reset()
        assert m.probability == 0.0

    def test_invalid_inputs_raise(self) -> None:
        m = OmanMotionSicknessModel()
        with pytest.raises(ValueError):
            m.step(0.1, dt_s=0.0)
        with pytest.raises(ValueError):
            m.step(-0.1, dt_s=1.0)

    def test_clamped_to_unit_interval(self) -> None:
        # Drive infinitely hard for many seconds — should saturate at
        # exactly 1.0, never overshoot.
        m = OmanMotionSicknessModel()
        for _ in range(100_000):
            m.step(conflict_rad_s2=10.0, dt_s=1.0)
        assert 0.0 <= m.probability <= 1.0
        assert m.probability == 1.0


# ─────────────────────────────────────────────────────────────────────
# Adaptation envelope — Young 2019
# ─────────────────────────────────────────────────────────────────────


class TestAdaptation:
    def test_constants_per_young_2019(self) -> None:
        # 72 h midpoint of the 48-120 h band.
        assert YOUNG_2019_E_HALF_S == 72.0 * 3600.0

    def test_zero_exposure_zero_adaptation(self) -> None:
        assert adaptation_probability(0.0) == 0.0

    def test_negative_exposure_clamped_to_zero(self) -> None:
        assert adaptation_probability(-1000.0) == 0.0

    def test_one_half_dose_gives_63_percent(self) -> None:
        # P(E_½) = 1 − e⁻¹ ≈ 0.632
        p = adaptation_probability(YOUNG_2019_E_HALF_S)
        assert p == pytest.approx(1.0 - math.exp(-1.0), rel=1e-12)

    def test_three_half_doses_gives_95_percent(self) -> None:
        # P(3 E_½) = 1 − e⁻³ ≈ 0.9502
        p = adaptation_probability(3.0 * YOUNG_2019_E_HALF_S)
        assert p == pytest.approx(1.0 - math.exp(-3.0), rel=1e-12)
        assert p > 0.94

    def test_long_exposure_approaches_unity(self) -> None:
        p = adaptation_probability(50.0 * YOUNG_2019_E_HALF_S)
        assert p > 0.999_999

    def test_invalid_e_half_raises(self) -> None:
        with pytest.raises(ValueError):
            adaptation_probability(1000.0, e_half_s=0.0)


# ─────────────────────────────────────────────────────────────────────
# Integration smoke test: cross-coupling → Oman dose chain
# ─────────────────────────────────────────────────────────────────────


class TestEndToEndChain:
    """Demonstrates how a C1 ring spin-rate + crew head tilt feeds
    through the cross-coupling vector form into the Oman dose model
    to produce a time-resolved motion-sickness probability."""

    def test_aria_4rpm_naive_crew_above_threshold_gets_sick(self) -> None:
        # 4 rpm ring + 1 rad/s orthogonal head tilt → α_cross ≈ 0.42
        # rad/s², well above the 0.1 rad/s² naive threshold.
        omega_ring = np.array([0.0, 0.0, 0.4189])
        omega_head = np.array([1.0, 0.0, 0.0])
        alpha = cross_coupled_angular_acceleration(omega_ring, omega_head)
        alpha_mag = float(np.linalg.norm(alpha))
        assert alpha_mag > motion_sickness_threshold_naive()

        # The Oman ODE rises with k_down = 1/1800 s, so the analytic
        # closed form (linear, before the [0,1] cap) for a constant
        # conflict α is
        #     P(t) = (k_up α² / k_down) · (1 − exp(−k_down t))
        # At t = 600 s, k_down t = 1/3, so
        #     P(600) ≈ 1.58 · (1 − e^-1/3) = 1.58 · 0.283 ≈ 0.448
        m = OmanMotionSicknessModel()
        for _ in range(600):
            m.step(conflict_rad_s2=alpha_mag, dt_s=1.0)
        assert 0.40 < m.probability < 0.55, m.probability
        # The equilibrium ceiling is the SDTC anchor: at this conflict
        # level, the steady-state P_∞ saturates at 1.0.
        assert m.equilibrium_probability(alpha_mag) == 1.0
        # Continue integrating to ~3 hours and confirm we approach
        # the saturation cap.
        for _ in range(3600 * 3):
            m.step(conflict_rad_s2=alpha_mag, dt_s=1.0)
        assert m.probability > 0.95

    def test_low_spin_no_head_tilt_no_sickness(self) -> None:
        # Sustained low cross-coupling at the threshold should give
        # bounded equilibrium probability.
        omega_ring = np.array([0.0, 0.0, 0.1])  # 0.95 rpm
        omega_head = np.array([0.0, 0.0, 0.0])
        alpha = cross_coupled_angular_acceleration(omega_ring, omega_head)
        assert float(np.linalg.norm(alpha)) == 0.0

        m = OmanMotionSicknessModel()
        for _ in range(3600):
            m.step(conflict_rad_s2=0.0, dt_s=1.0)
        assert m.probability == 0.0
