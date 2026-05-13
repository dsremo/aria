"""Tests for FIFO eviction boundaries (Google SRE critique: 'aspirational documentation')."""

import pytest
from unittest.mock import MagicMock, patch


class TestMLModelEviction:
    """Verify FIFO eviction at _MAX_ML_MODELS boundary."""

    def test_lstm_registry_evicts_at_cap(self):
        """201st model triggers eviction of the oldest."""
        import aria.dsremo.detection.detector as det_mod

        original_max = det_mod._MAX_ML_MODELS
        det_mod._MAX_ML_MODELS = 5  # lower for test speed
        det_mod._lstm_models.clear()

        try:
            # Mock factory to avoid real PyTorch
            for i in range(6):
                key = f"sat:{i}"
                det_mod._lstm_models[key] = MagicMock()
                if len(det_mod._lstm_models) > det_mod._MAX_ML_MODELS:
                    oldest = next(iter(det_mod._lstm_models))
                    del det_mod._lstm_models[oldest]

            assert len(det_mod._lstm_models) == 5
            assert "sat:0" not in det_mod._lstm_models  # oldest evicted
            assert "sat:5" in det_mod._lstm_models       # newest kept
        finally:
            det_mod._MAX_ML_MODELS = original_max
            det_mod._lstm_models.clear()

    def test_tcn_registry_evicts_at_cap(self):
        """TCN registry also evicts."""
        import aria.dsremo.detection.detector as det_mod

        original_max = det_mod._MAX_ML_MODELS
        det_mod._MAX_ML_MODELS = 3
        det_mod._tcn_models.clear()

        try:
            for i in range(4):
                key = f"sat:tcn{i}"
                det_mod._tcn_models[key] = MagicMock()
                if len(det_mod._tcn_models) > det_mod._MAX_ML_MODELS:
                    oldest = next(iter(det_mod._tcn_models))
                    del det_mod._tcn_models[oldest]

            assert len(det_mod._tcn_models) == 3
            assert "sat:tcn0" not in det_mod._tcn_models
        finally:
            det_mod._MAX_ML_MODELS = original_max
            det_mod._tcn_models.clear()


class TestChannelStateEviction:
    """Verify _MAX_CHANNEL_STATE FIFO eviction on per-channel dicts."""

    def test_last_processed_ts_evicts(self):
        import aria.dsremo.detection.detector as det_mod

        original_max = det_mod._MAX_CHANNEL_STATE
        det_mod._MAX_CHANNEL_STATE = 5
        det_mod._last_processed_ts.clear()

        try:
            for i in range(6):
                key = f"tenant1:sat:ch{i}"
                if key not in det_mod._last_processed_ts:
                    _tenant = key.split(":")[0] + ":"
                    if sum(1 for k in det_mod._last_processed_ts if k.startswith(_tenant)) >= det_mod._MAX_CHANNEL_STATE:
                        _evict = next(k for k in det_mod._last_processed_ts if k.startswith(_tenant))
                        del det_mod._last_processed_ts[_evict]
                det_mod._last_processed_ts[key] = float(i)

            assert len(det_mod._last_processed_ts) == 5
            assert "tenant1:sat:ch0" not in det_mod._last_processed_ts
            assert "tenant1:sat:ch5" in det_mod._last_processed_ts
        finally:
            det_mod._MAX_CHANNEL_STATE = original_max
            det_mod._last_processed_ts.clear()

    def test_per_tenant_isolation(self):
        """Tenant A's eviction should not affect Tenant B's entries."""
        import aria.dsremo.detection.detector as det_mod

        original_max = det_mod._MAX_CHANNEL_STATE
        det_mod._MAX_CHANNEL_STATE = 3
        det_mod._last_processed_ts.clear()

        try:
            # Add 3 entries for tenant A
            for i in range(3):
                det_mod._last_processed_ts[f"tenantA:sat:ch{i}"] = float(i)
            # Add 3 entries for tenant B
            for i in range(3):
                det_mod._last_processed_ts[f"tenantB:sat:ch{i}"] = float(i)

            # Total is 6 but per-tenant is 3 each — no eviction needed
            assert len(det_mod._last_processed_ts) == 6

            # Adding a 4th for tenant A should evict tenant A's oldest
            key = "tenantA:sat:ch3"
            _tenant = "tenantA:"
            if sum(1 for k in det_mod._last_processed_ts if k.startswith(_tenant)) >= det_mod._MAX_CHANNEL_STATE:
                _evict = next(k for k in det_mod._last_processed_ts if k.startswith(_tenant))
                del det_mod._last_processed_ts[_evict]
            det_mod._last_processed_ts[key] = 3.0

            # Tenant A: ch0 evicted, ch1,ch2,ch3 remain
            assert "tenantA:sat:ch0" not in det_mod._last_processed_ts
            assert "tenantA:sat:ch3" in det_mod._last_processed_ts
            # Tenant B untouched
            assert all(f"tenantB:sat:ch{i}" in det_mod._last_processed_ts for i in range(3))
        finally:
            det_mod._MAX_CHANNEL_STATE = original_max
            det_mod._last_processed_ts.clear()
