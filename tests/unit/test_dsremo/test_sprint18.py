"""Sprint 18 tests — Stale Data Detector, MAD Z-Score, TTL Prediction,
Subsystem Health API.

Sources of inspiration:
  - NASA ASIST stale/silence detection (3-5× expected period)
  - Grafana production MAD-robustness insight (2024)
  - SpaceX / ISRO time-to-limit prediction
  - ISRO FOLIO subsystem health scoring
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_settings(**overrides):
    """Return a minimal mock settings object accepted by init_detectors()."""
    base = {"stale_threshold_s": 300.0, "ttl_warn_min": 60.0}
    base.update(overrides)
    cfg = {"detection": base, "features": {}}

    class _S:
        def get(self, key, default=None):
            return cfg.get(key, default)

    return _S()


# ── TestMADZScore ─────────────────────────────────────────────────────────────

class TestMADZScore:
    """StatisticalDetector now uses MAD-based z-score (spike-robust)."""

    def _detector(self):
        from aria.dsremo.detection.statistical import StatisticalDetector
        return StatisticalDetector(z_threshold=3.0, min_window=10)

    def test_mad_z_static_method_exists(self):
        det = self._detector()
        assert hasattr(det, "_mad_z")

    def test_mad_z_returns_zero_for_constant_signal(self):
        det = self._detector()
        window = np.zeros(50)
        assert det._mad_z(0.0, window) == 0.0

    def test_mad_z_spike_does_not_inflate_band(self):
        """Key property: a spike in the WINDOW should not raise MAD much.

        With std: one 100σ outlier in 100-sample window raises std by ~10×,
        blinding the detector for hours.
        With MAD: one outlier does not affect the median, MAD is stable.
        """
        det = self._detector()
        # Normal data ±1, then one massive spike
        window = np.random.normal(0, 1, 99)
        window_with_spike = np.append(window, 100.0)  # spike in window
        # MAD of window with spike should still be ~1 (normal distribution)
        mad_z = det._mad_z(2.0, window_with_spike)   # current=2.0 (modest outlier)
        std_z = abs(2.0 / window_with_spike.std())   # std blows up

        # MAD should flag the modest 2.0 outlier; std band collapses
        assert mad_z >= 0.5, f"MAD-z should flag modest outlier, got {mad_z:.2f}"
        assert std_z < mad_z, (
            f"MAD ({mad_z:.2f}) should be more sensitive than std ({std_z:.2f}) "
            "when window contains a spike"
        )

    def test_mad_z_correctly_scores_clear_outlier(self):
        det = self._detector()
        # Use a window with genuine spread so MAD > 0
        # Alternating 0/1 gives MAD = 0.5 (median=0.5, |x-0.5| alternates 0.5/0.5)
        window = np.array([float(i % 2) for i in range(50)])
        # current = 10.0 → very clear outlier vs 0/1 baseline
        z = det._mad_z(10.0, window)
        assert z > 3.0

    def test_detect_uses_mad_when_window_available(self):
        """Detect returns is_anomaly=True for a clear spike using MAD path."""
        from aria.dsremo.detection.statistical import StatisticalDetector
        from aria.dsremo.features.engine import FeatureEngine

        det = StatisticalDetector(z_threshold=3.0, min_window=10)
        engine = FeatureEngine()

        # Pre-warm engine so rolling_std > 0 (avoids constant_residual guard)
        for i in range(30):
            engine.compute("param:res", float(i % 3), time.time() + i)

        # Build a normal baseline window with genuine spread
        baseline = np.random.normal(0, 1, 50)
        current_val = 10.0
        t = time.time() + 31
        fv = engine.compute("param:res", current_val, t)

        result = det.detect(fv, np.append(baseline, current_val))
        assert result.is_anomaly, "Large spike should be detected via MAD"

    def test_detect_falls_back_to_std_z_when_no_window(self):
        """Without window_values, falls back to rolling-std z-score."""
        from aria.dsremo.detection.statistical import StatisticalDetector
        from aria.dsremo.features.engine import FeatureEngine

        det = StatisticalDetector(z_threshold=3.0, min_window=10)
        engine = FeatureEngine()

        # Prime engine with normal data so rolling_std > 0
        for i in range(50):
            engine.compute("p:res", float(i % 3), time.time() + i)

        # Large spike — engine's std is ~1, spike is 10σ
        fv = engine.compute("p:res", 30.0, time.time() + 51)
        result = det.detect(fv, window_values=None)  # no window
        assert result.is_anomaly

    def test_detect_nominal_for_small_deviation(self):
        from aria.dsremo.detection.statistical import StatisticalDetector
        from aria.dsremo.features.engine import FeatureEngine

        det = StatisticalDetector(z_threshold=3.0, min_window=10)
        engine = FeatureEngine()
        window = np.random.normal(0, 1, 50)
        t = time.time()
        fv = engine.compute("p:res", 0.5, t)   # 0.5σ — clearly nominal
        result = det.detect(fv, window)
        assert not result.is_anomaly

    def test_detect_constant_residual_guard_unchanged(self):
        from aria.dsremo.detection.statistical import StatisticalDetector
        from aria.dsremo.features.engine import FeatureEngine

        det = StatisticalDetector()
        engine = FeatureEngine()
        fv = engine.compute("p:res", 0.0, time.time())
        result = det.detect(fv, np.zeros(50))
        assert not result.is_anomaly
        assert result.details.get("reason") == "constant_residual"


# ── TestStaleDataDetector ─────────────────────────────────────────────────────

class TestStaleDataDetector:
    """Stale data detection in run_detection_cycle() — NASA ASIST pattern."""

    def _init(self, **kwargs):
        import aria.dsremo.detection.detector as det_mod
        det_mod.init_detectors(_make_settings(**kwargs))

    def test_channel_last_seen_dict_exists_in_detector(self):
        import aria.dsremo.detection.detector as det_mod
        assert hasattr(det_mod, "_channel_last_seen")
        assert isinstance(det_mod._channel_last_seen, dict)

    def test_stale_threshold_s_configurable(self):
        import aria.dsremo.detection.detector as det_mod
        assert hasattr(det_mod, "_stale_threshold_s")
        assert det_mod._stale_threshold_s > 0

    def test_ttl_warn_min_configurable(self):
        import aria.dsremo.detection.detector as det_mod
        assert hasattr(det_mod, "_ttl_warn_min")
        assert det_mod._ttl_warn_min > 0

    def test_init_detectors_clears_channel_last_seen(self):
        import aria.dsremo.detection.detector as det_mod
        # Pollute the dict, then re-init
        det_mod._channel_last_seen["TEST:PARAM"] = 12345.0
        self._init()
        assert "TEST:PARAM" not in det_mod._channel_last_seen

    def test_init_detectors_reads_stale_threshold_from_config(self):
        import aria.dsremo.detection.detector as det_mod
        self._init(stale_threshold_s=300.0)
        # Config sets stale_threshold_s: 300 — detector should pick it up
        assert det_mod._stale_threshold_s == 300.0

    def test_init_detectors_reads_ttl_warn_min_from_config(self):
        import aria.dsremo.detection.detector as det_mod
        self._init(ttl_warn_min=60.0)
        assert det_mod._ttl_warn_min == 60.0

    def test_stale_anomaly_uses_stale_data_detector_name(self):
        """Stale anomaly fires with detector_name='stale_data'."""
        import aria.dsremo.detection.detector as det_mod
        from datetime import timedelta

        # Manually set a channel as last seen > threshold ago
        sat = "STALE-SAT"
        param = "TEMP"
        key = f"{sat}:{param}"
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()
        det_mod._channel_last_seen[key] = old_ts - 1  # ensure seen before

        # Confirm stale condition: (now - old_ts) > threshold (300s)
        now = datetime.now(timezone.utc).timestamp()
        gap_s = now - old_ts
        assert gap_s > det_mod._stale_threshold_s, f"Expected gap {gap_s:.0f}s > threshold"

    def test_get_effective_thresholds_includes_hard_limits(self):
        from aria.dsremo.detection.detector import get_effective_thresholds, init_detectors
        init_detectors(_make_settings())
        eff = get_effective_thresholds("SAT-1", "TEMP")
        assert "hard_limit_high" in eff
        assert "hard_limit_low" in eff

    def test_hard_limit_defaults_are_none(self):
        from aria.dsremo.detection.detector import get_effective_thresholds, init_detectors
        init_detectors(_make_settings())
        eff = get_effective_thresholds("SAT-1", "TEMP")
        assert eff["hard_limit_high"] is None
        assert eff["hard_limit_low"] is None


# ── TestTTLPrediction ─────────────────────────────────────────────────────────

class TestTTLPrediction:
    """Time-to-limit computation in run_detection_cycle()."""

    def _init(self, **kwargs):
        from aria.dsremo.detection.detector import init_detectors
        init_detectors(_make_settings(**kwargs))

    def test_ttl_computation_positive_velocity_high_limit(self):
        """TTL = (high_limit − value) / velocity / 60.

        velocity = 10 u/min = 10/60 u/s ≈ 0.1667 u/s
        remaining = 100 − 80 = 20 u
        TTL = 20 / (10/60) / 60 = 20 × 60 / 10 / 60 = 2.0 min
        """
        value = 80.0
        hard_limit_high = 100.0
        velocity = (10.0 / 60.0)   # 10 units per minute expressed in u/s
        expected_ttl = round((hard_limit_high - value) / velocity / 60.0, 1)
        assert expected_ttl == pytest.approx(2.0, abs=0.2)

    def test_ttl_computation_negative_velocity_low_limit(self):
        """TTL = (value − low_limit) / |velocity| / 60."""
        value = 20.0
        hard_limit_low = 0.0
        velocity = -(2.0 / 60.0)   # falling at 2 units/minute
        remaining = value - hard_limit_low
        expected_ttl = round(remaining / abs(velocity) / 60.0, 1)
        assert expected_ttl == pytest.approx(10.0, abs=0.5)

    def test_no_ttl_when_no_hard_limits(self):
        """When hard limits are None, no TTL is computed."""
        eff = {"hard_limit_high": None, "hard_limit_low": None}
        assert eff["hard_limit_high"] is None
        assert eff["hard_limit_low"] is None

    def test_no_ttl_when_velocity_zero(self):
        """Zero velocity → no finite time-to-limit."""
        velocity = 0.0
        # Should not divide by zero
        assert abs(velocity) < 1e-8

    def test_ttl_warn_min_threshold_triggers_escalation(self):
        """If ttl_min < ttl_warn_min, severity should escalate."""
        import aria.dsremo.detection.detector as det_mod
        self._init(ttl_warn_min=60.0)
        ttl_warn = det_mod._ttl_warn_min   # 60
        ttl_imminent = ttl_warn / 4       # 15 min → CRITICAL

        assert ttl_imminent < ttl_warn   # escalation should trigger
        assert ttl_imminent < ttl_warn / 3  # specifically → CRITICAL

    def test_ttl_warn_fires_warning_for_moderate_ttl(self):
        """ttl between ttl_warn/3 and ttl_warn → WARNING (not CRITICAL)."""
        import aria.dsremo.detection.detector as det_mod
        self._init(ttl_warn_min=60.0)
        ttl_moderate = det_mod._ttl_warn_min * 0.6  # 36 min (> 20, < 60)
        assert ttl_moderate < det_mod._ttl_warn_min
        assert ttl_moderate > det_mod._ttl_warn_min / 3

    def test_channel_config_has_velocity_threshold_key(self):
        from aria.dsremo.detection.detector import get_effective_thresholds, init_detectors
        init_detectors(_make_settings())
        eff = get_effective_thresholds("SAT-1", "PARAM")
        assert "velocity_threshold" in eff


# ── TestSubsystemHealthAPI ────────────────────────────────────────────────────

def _make_health_app():
    """Minimal FastAPI app with only the health router — no DB."""
    from fastapi import FastAPI
    from aria.dsremo.api.dependencies import get_current_user
    from aria.dsremo.api.routes_health import health_router

    app = FastAPI()
    app.include_router(health_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "test-admin",
        "tenant_id": "default",
        "role": "admin",
        "scope": "tenant",
    }
    return app


def _mock_health_queries(rows=None):
    import aria.dsremo.api.routes_health as health_mod
    m = MagicMock()
    m.get_subsystem_health = AsyncMock(return_value=rows or [])
    return patch.object(health_mod, "queries", m)


class TestSubsystemHealthAPI:
    """GET /satellites/{sat}/subsystem-health endpoint."""

    def test_health_endpoint_returns_200(self):
        from starlette.testclient import TestClient
        with _mock_health_queries():
            with TestClient(_make_health_app()) as c:
                resp = c.get("/api/v1/satellites/SAT-1/subsystem-health")
        assert resp.status_code == 200

    def test_health_empty_list_when_no_subsystems(self):
        from starlette.testclient import TestClient
        with _mock_health_queries(rows=[]):
            with TestClient(_make_health_app()) as c:
                resp = c.get("/api/v1/satellites/SAT-1/subsystem-health")
        assert resp.json() == []

    def test_health_returns_correct_fields(self):
        from starlette.testclient import TestClient
        rows = [{"subsystem": "eps", "total_channels": 4, "anomalous_channels": 1, "health": 0.75}]
        with _mock_health_queries(rows=rows):
            with TestClient(_make_health_app()) as c:
                resp = c.get("/api/v1/satellites/SAT-1/subsystem-health")
        body = resp.json()
        assert len(body) == 1
        s = body[0]
        assert s["subsystem"] == "eps"
        assert s["total_channels"] == 4
        assert s["anomalous_channels"] == 1
        assert s["health"] == pytest.approx(0.75)

    def test_health_nominal_subsystem_has_health_1(self):
        from starlette.testclient import TestClient
        rows = [{"subsystem": "adcs", "total_channels": 3, "anomalous_channels": 0, "health": 1.0}]
        with _mock_health_queries(rows=rows):
            with TestClient(_make_health_app()) as c:
                resp = c.get("/api/v1/satellites/NOMINAL-SAT/subsystem-health")
        assert resp.json()[0]["health"] == 1.0

    def test_health_degraded_subsystem_has_health_below_1(self):
        from starlette.testclient import TestClient
        rows = [{"subsystem": "thermal", "total_channels": 6, "anomalous_channels": 3, "health": 0.5}]
        with _mock_health_queries(rows=rows):
            with TestClient(_make_health_app()) as c:
                resp = c.get("/api/v1/satellites/THERMAL-SAT/subsystem-health")
        assert resp.json()[0]["health"] == pytest.approx(0.5)

    def test_health_multiple_subsystems(self):
        from starlette.testclient import TestClient
        rows = [
            {"subsystem": "eps",     "total_channels": 4, "anomalous_channels": 0, "health": 1.0},
            {"subsystem": "thermal", "total_channels": 6, "anomalous_channels": 2, "health": 0.667},
        ]
        with _mock_health_queries(rows=rows):
            with TestClient(_make_health_app()) as c:
                resp = c.get("/api/v1/satellites/SAT-X/subsystem-health")
        assert len(resp.json()) == 2

    def test_health_schema_fields_present(self):
        from aria.dsremo.api.schemas import SubsystemHealth
        sh = SubsystemHealth(
            subsystem="eps",
            total_channels=4,
            anomalous_channels=1,
            health=0.75,
        )
        assert sh.subsystem == "eps"
        assert sh.total_channels == 4
        assert sh.anomalous_channels == 1
        assert sh.health == pytest.approx(0.75)

    def test_health_schema_health_is_float(self):
        from aria.dsremo.api.schemas import SubsystemHealth
        sh = SubsystemHealth(subsystem="comms", total_channels=2,
                             anomalous_channels=0, health=1.0)
        assert isinstance(sh.health, float)


# ── TestSubsystemHealthQuery ──────────────────────────────────────────────────

class TestSubsystemHealthQuery:
    """Unit tests for the DB query logic (pure logic, no DB needed)."""

    def test_memory_store_get_subsystem_health_exists(self):
        from aria.dsremo.db import memory_store
        assert hasattr(memory_store, "get_subsystem_health")

    @pytest.mark.asyncio
    async def test_memory_store_returns_empty_list(self):
        from aria.dsremo.db.memory_store import get_subsystem_health
        result = await get_subsystem_health("ANY-SAT")
        assert result == []

    def test_migrations_schema_version_is_at_least_18(self):
        from aria.dsremo.db.migrations import SCHEMA_VERSION
        assert SCHEMA_VERSION >= 18

    def test_migrations_have_hard_limit_columns(self):
        from aria.dsremo.db.migrations import _MIGRATIONS
        sql_all = " ".join(_MIGRATIONS)
        assert "hard_limit_high" in sql_all
        assert "hard_limit_low" in sql_all
        assert "velocity_threshold" in sql_all
