"""Tests for V3-M5: reaction-wheel bearing-stress proxy."""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.dsremo.detection.rw_bearing_proxy import (
    MIN_BASELINE_SAMPLES,
    RWBearingProxyMonitor,
    ball_pass_frequency_inner,
    ball_pass_frequency_outer,
    fundamental_train_frequency,
)


SAT = "SAT-M5-01"
WHEEL = "rw_x"


# ── Bearing geometry formulas (Harris & Kotzalas 2007 §5.4) ─────────────────


class TestBearingFormulas:

    def test_ftf_zero_contact_angle(self):
        # Standard RW bearing: 8 balls, D_b=6 mm, D_p=30 mm, 6000 RPM.
        ftf = fundamental_train_frequency(
            rpm_shaft=6000, n_balls=8, ball_diameter=6, pitch_diameter=30,
        )
        rps = 100.0
        expected = 0.5 * rps * (1.0 - 6.0 / 30.0)
        assert ftf == pytest.approx(expected, rel=1e-6)

    def test_bpfo_is_n_times_ftf(self):
        # BPFO should equal n_balls × FTF at zero contact angle
        args = dict(rpm_shaft=6000, n_balls=8, ball_diameter=6, pitch_diameter=30)
        ftf = fundamental_train_frequency(**args)
        bpfo = ball_pass_frequency_outer(**args)
        assert bpfo == pytest.approx(8 * ftf, rel=1e-6)

    def test_bpfi_greater_than_bpfo(self):
        args = dict(rpm_shaft=6000, n_balls=8, ball_diameter=6, pitch_diameter=30)
        bpfo = ball_pass_frequency_outer(**args)
        bpfi = ball_pass_frequency_inner(**args)
        assert bpfi > bpfo

    def test_contact_angle_reduces_bpfo(self):
        args0 = dict(rpm_shaft=6000, n_balls=8, ball_diameter=6, pitch_diameter=30,
                     contact_angle_rad=0.0)
        args15 = dict(args0, contact_angle_rad=math.radians(15))
        bpfo_0  = ball_pass_frequency_outer(**args0)
        bpfo_15 = ball_pass_frequency_outer(**args15)
        assert bpfo_15 > bpfo_0  # cos(α) < 1 → (1 − D/p·cosα) increases

    @pytest.mark.parametrize("bad_args", [
        dict(rpm_shaft=6000, n_balls=0,  ball_diameter=6, pitch_diameter=30),
        dict(rpm_shaft=6000, n_balls=8,  ball_diameter=0, pitch_diameter=30),
        dict(rpm_shaft=6000, n_balls=8,  ball_diameter=6, pitch_diameter=0),
        dict(rpm_shaft=6000, n_balls=8,  ball_diameter=30, pitch_diameter=30),
    ])
    def test_formula_validation(self, bad_args):
        with pytest.raises(ValueError):
            fundamental_train_frequency(**bad_args)
        with pytest.raises(ValueError):
            ball_pass_frequency_inner(**bad_args)


# ── Monitor construction ────────────────────────────────────────────────────


class TestMonitorConfig:

    def test_rejects_bad_min_baseline(self):
        with pytest.raises(ValueError):
            RWBearingProxyMonitor(min_baseline_samples=8)

    def test_rejects_thresholds_below_one(self):
        with pytest.raises(ValueError):
            RWBearingProxyMonitor(rms_ratio_watch=0.9)

    def test_rejects_non_monotonic_thresholds(self):
        with pytest.raises(ValueError):
            RWBearingProxyMonitor(rms_ratio_watch=2.5, rms_ratio_warning=1.5)


# ── Fit + evaluate (happy paths) ────────────────────────────────────────────


class TestFitAndEvaluate:

    def _nominal_stream(self, n: int, seed: int = 0):
        rng = np.random.default_rng(seed)
        rpm = rng.uniform(1000, 5000, n)
        tau = 1.2e-5 * rpm + 1e-3 + rng.normal(0.0, 5e-4, n)
        return rpm, tau

    def test_fit_baseline_fits_linear_curve(self):
        mon = RWBearingProxyMonitor()
        rpm, tau = self._nominal_stream(128)
        for r, t in zip(rpm, tau):
            mon.record_sample(SAT, WHEEL, rpm=r, torque=t, epoch=None)
        mon.fit_baseline(SAT, WHEEL)
        st = mon._states[(SAT, WHEEL)]
        assert st.fitted
        assert abs(st.slope - 1.2e-5) < 1e-6
        assert st.baseline_rms > 0.0

    def test_fit_baseline_insufficient_samples_raises(self):
        mon = RWBearingProxyMonitor()
        rpm, tau = self._nominal_stream(16)
        for r, t in zip(rpm, tau):
            mon.record_sample(SAT, WHEEL, rpm=r, torque=t)
        with pytest.raises(ValueError):
            mon.fit_baseline(SAT, WHEEL)

    def test_fit_baseline_unknown_wheel_raises(self):
        mon = RWBearingProxyMonitor()
        with pytest.raises(KeyError):
            mon.fit_baseline(SAT, "unknown_wheel")

    def test_nominal_runtime_stays_nominal(self):
        mon = RWBearingProxyMonitor()
        rpm, tau = self._nominal_stream(128, seed=0)
        for r, t in zip(rpm, tau):
            mon.record_sample(SAT, WHEEL, rpm=r, torque=t)
        mon.fit_baseline(SAT, WHEEL)

        rpm2, tau2 = self._nominal_stream(200, seed=1)
        for i, (r, t) in enumerate(zip(rpm2, tau2)):
            mon.record_sample(SAT, WHEEL, rpm=r, torque=t, epoch=float(i))
        report = mon.evaluate(SAT, WHEEL)
        assert report is not None
        assert report.tier == "NOMINAL"
        assert 0.5 < report.rms_ratio < 2.0

    def test_degraded_stream_escalates(self):
        mon = RWBearingProxyMonitor()
        rpm, tau = self._nominal_stream(128, seed=0)
        for r, t in zip(rpm, tau):
            mon.record_sample(SAT, WHEEL, rpm=r, torque=t)
        mon.fit_baseline(SAT, WHEEL)

        # Inject bearing degradation — increased torque noise.
        rng = np.random.default_rng(5)
        rpm2 = rng.uniform(1000, 5000, 200)
        tau2 = 1.2e-5 * rpm2 + 1e-3 + rng.normal(0.0, 5e-3, 200)   # 10× σ
        for i, (r, t) in enumerate(zip(rpm2, tau2)):
            mon.record_sample(SAT, WHEEL, rpm=r, torque=t, epoch=float(i))
        report = mon.evaluate(SAT, WHEEL)
        assert report is not None
        assert report.tier in {"WATCH", "WARNING", "CRITICAL"}
        assert report.rms_ratio > 2.0

    def test_evaluate_returns_none_before_fit(self):
        mon = RWBearingProxyMonitor()
        rpm, tau = self._nominal_stream(30)
        for r, t in zip(rpm, tau):
            mon.record_sample(SAT, WHEEL, rpm=r, torque=t, epoch=0.0)
        assert mon.evaluate(SAT, WHEEL) is None

    def test_evaluate_returns_none_with_insufficient_history(self):
        mon = RWBearingProxyMonitor()
        rpm, tau = self._nominal_stream(128)
        for r, t in zip(rpm, tau):
            mon.record_sample(SAT, WHEEL, rpm=r, torque=t)
        mon.fit_baseline(SAT, WHEEL)
        # Only 2 post-fit samples — not enough for rolling RMS history.
        mon.record_sample(SAT, WHEEL, rpm=2000, torque=0.03, epoch=1.0)
        mon.record_sample(SAT, WHEEL, rpm=2000, torque=0.03, epoch=2.0)
        assert mon.evaluate(SAT, WHEEL) is None


# ── Housekeeping ────────────────────────────────────────────────────────────


class TestReset:

    def test_reset_sat_scope(self):
        mon = RWBearingProxyMonitor()
        mon.record_sample(SAT, WHEEL, rpm=1000, torque=0.02)
        mon.record_sample("SAT-OTHER", WHEEL, rpm=1000, torque=0.02)
        mon.reset(SAT)
        assert (SAT, WHEEL) not in mon._states
        assert ("SAT-OTHER", WHEEL) in mon._states

    def test_reset_all(self):
        mon = RWBearingProxyMonitor()
        mon.record_sample(SAT, WHEEL, rpm=1000, torque=0.02)
        mon.reset()
        assert mon._states == {}


# ── Report serialization ────────────────────────────────────────────────────


class TestReportToDict:

    def test_to_dict_json_clean(self):
        import json
        mon = RWBearingProxyMonitor()
        rng = np.random.default_rng(0)
        rpm = rng.uniform(1000, 5000, 128)
        tau = 1.2e-5 * rpm + 1e-3 + rng.normal(0.0, 5e-4, 128)
        for r, t in zip(rpm, tau):
            mon.record_sample(SAT, WHEEL, rpm=r, torque=t)
        mon.fit_baseline(SAT, WHEEL)
        for i in range(64):
            mon.record_sample(SAT, WHEEL, rpm=2000, torque=0.03, epoch=float(i))
        report = mon.evaluate(SAT, WHEEL)
        d = report.to_dict()
        # Assertion: JSON-encodable.
        json.dumps(d)
        assert d["tier"] in {"NOMINAL", "WATCH", "WARNING", "CRITICAL"}
