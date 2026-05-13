"""Integration tests: V3-V4 cross-channel attention, V3-M5 RW bearing
proxy, and V3-S2 WideTCN ensemble enablers wired into `detector`.
"""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.detection import detector as det_mod
from aria.dsremo.detection.rw_bearing_proxy import RWBearingProxyMonitor
from aria.dsremo.detection.temporal_cross_attention import TemporalCrossAttention


@pytest.fixture(autouse=True)
def _reset():
    det_mod.register_cross_channel_attn(None)
    det_mod.register_rw_bearing_proxy(None)
    # Snapshot + restore the global WEIGHTS so enable_* side-effects
    # don't leak across tests.
    orig = dict(det_mod.WEIGHTS)
    orig_grp = dict(det_mod._GROUP_WEIGHTS)
    yield
    det_mod.register_cross_channel_attn(None)
    det_mod.register_rw_bearing_proxy(None)
    det_mod.WEIGHTS.clear()
    det_mod.WEIGHTS.update(orig)
    det_mod._GROUP_WEIGHTS.clear()
    det_mod._GROUP_WEIGHTS.update(orig_grp)


# ── Registry wiring ─────────────────────────────────────────────────────────

class TestRegistryAndWeights:

    def test_default_weights_include_new_keys_with_zero(self):
        assert det_mod.WEIGHTS["wide_tcn"] == 0.0
        assert det_mod.WEIGHTS["cross_channel_attn"] == 0.0
        assert det_mod.WEIGHTS["rw_bearing_proxy"] == 0.0

    def test_enable_wide_tcn_sets_weight(self):
        det_mod.enable_wide_tcn(weight=0.0473, group_weight=0.05)
        assert det_mod.WEIGHTS["wide_tcn"] == pytest.approx(0.0473)

    def test_enable_cross_channel_attn(self):
        det_mod.enable_cross_channel_attn(weight=0.05)
        assert det_mod.WEIGHTS["cross_channel_attn"] == pytest.approx(0.05)
        assert det_mod._GROUP_WEIGHTS["cross_subsystem"] >= 0.05

    def test_enable_rw_bearing_proxy(self):
        det_mod.enable_rw_bearing_proxy(weight=0.04)
        assert det_mod.WEIGHTS["rw_bearing_proxy"] == pytest.approx(0.04)

    def test_register_cross_attn_none_clears(self):
        mon = TemporalCrossAttention()
        det_mod.register_cross_channel_attn(mon)
        assert det_mod._cross_channel_attn is mon
        det_mod.register_cross_channel_attn(None)
        assert det_mod._cross_channel_attn is None

    def test_register_rw_bearing_proxy_none_clears(self):
        mon = RWBearingProxyMonitor()
        det_mod.register_rw_bearing_proxy(mon)
        assert det_mod._rw_bearing_proxy is mon
        det_mod.register_rw_bearing_proxy(None)
        assert det_mod._rw_bearing_proxy is None

    def test_detector_groups_include_new_keys(self):
        assert det_mod._DETECTOR_GROUPS["wide_tcn"] == "ml_temporal"
        assert det_mod._DETECTOR_GROUPS["cross_channel_attn"] == "cross_subsystem"
        assert det_mod._DETECTOR_GROUPS["rw_bearing_proxy"] == "physical_wear"

    def test_wide_tcn_factory_returns_correct_type(self):
        from aria.dsremo.detection.wide_tcn_detector import WideTCNDetector
        m = det_mod._get_wide_tcn_model("SAT-A", "bat_v")
        assert isinstance(m, WideTCNDetector)


# ── Optional-detector results helper ───────────────────────────────────────

class TestOptionalV3DetectorResults:

    def test_empty_when_nothing_registered(self):
        out = det_mod._optional_v3_detector_results("SAT-A", subsystem="eps")
        assert out == []

    def test_cross_attn_score_when_registered(self):
        mon = TemporalCrossAttention(window_size=32, threshold_frobenius=2.5)
        rng = np.random.default_rng(2)
        # Correlated baseline streams (same pattern as V-4 unit tests)
        n = 400
        t = np.arange(n + 8)
        base = np.sin(2 * np.pi * t / 40.0) + rng.normal(0, 0.05, n + 8)
        mon.fit_baseline("SAT-A", "eps", {
            "a": base[8:], "b": base[:n], "c": 0.5 * base[8:] + rng.normal(0, 0.05, n),
        })
        # Drive a continuation through update()
        for k in range(64):
            mon.update("SAT-A", "eps", {
                "a": float(base[k + 8]), "b": float(base[k]),
                "c": float(0.5 * base[k + 8]),
            })
        det_mod.register_cross_channel_attn(mon)
        out = det_mod._optional_v3_detector_results("SAT-A", subsystem="eps")
        # One DetectorResult expected from the cross-channel attention.
        names = {r.detector_name for r in out}
        assert "cross_channel_attn" in names

    def test_cross_attn_silent_when_subsystem_empty(self):
        mon = TemporalCrossAttention()
        det_mod.register_cross_channel_attn(mon)
        out = det_mod._optional_v3_detector_results("SAT-A", subsystem=None)
        assert out == []

    def test_bearing_proxy_score_when_registered_and_wheel_id(self):
        mon = RWBearingProxyMonitor()
        rng = np.random.default_rng(0)
        # Calibrate a wheel
        for _ in range(128):
            r = float(rng.uniform(1000, 5000))
            t = 1.2e-5 * r + 1e-3 + float(rng.normal(0, 5e-4))
            mon.record_sample("SAT-A", "reaction_wheel_x", rpm=r, torque=t)
        mon.fit_baseline("SAT-A", "reaction_wheel_x")
        # Drive enough runtime samples to populate rms_history
        for i in range(64):
            mon.record_sample(
                "SAT-A", "reaction_wheel_x",
                rpm=float(rng.uniform(1000, 5000)),
                torque=float(1.2e-5 * 2000 + 1e-3 + rng.normal(0, 5e-4)),
                epoch=float(i),
            )
        det_mod.register_rw_bearing_proxy(mon)
        out = det_mod._optional_v3_detector_results(
            "SAT-A", subsystem="adcs", wheel_id="reaction_wheel_x",
        )
        names = {r.detector_name for r in out}
        assert "rw_bearing_proxy" in names

    def test_bearing_proxy_skipped_without_wheel_id(self):
        mon = RWBearingProxyMonitor()
        det_mod.register_rw_bearing_proxy(mon)
        out = det_mod._optional_v3_detector_results(
            "SAT-A", subsystem="adcs", wheel_id=None,
        )
        assert out == []

    def test_cross_attn_exception_returns_no_entry(self):
        """A misbehaving monitor shouldn't break the ensemble — it should
        just contribute no DetectorResult."""
        class _BoomMon:
            def score(self, *_a, **_kw):
                raise RuntimeError("boom")
        det_mod.register_cross_channel_attn(_BoomMon())
        out = det_mod._optional_v3_detector_results("SAT-A", subsystem="eps")
        assert out == []
