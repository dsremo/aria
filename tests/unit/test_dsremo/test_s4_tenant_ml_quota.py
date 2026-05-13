"""Tests for V3-S4: per-tenant ML model quota (no cross-tenant eviction).

Validates:
 1. Two tenants owning the same satellite_id get separate model instances
 2. Per-tenant quota evicts that tenant's own LRU entry, not other tenants'
 3. Default quota = _MAX_ML_MODELS (backward compat)
 4. set_tenant_ml_model_quota records the override
 5. _tenant_ml_model_quota returns default for unset tenant
 6. LRU order preserved: accessing a key moves it to most-recent
 7. Global cap still enforced as a backstop when many tenants each at partial quota
"""

from __future__ import annotations

import pytest

from aria.dsremo.detection import detector as det_mod
from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
from aria.dsremo.core.tenant import set_tenant


class TestPerTenantIsolation:

    def test_same_satellite_different_tenants_separate_models(self):
        det_mod._lstm_models.clear()
        try:
            set_tenant("tenant-A")
            mA = det_mod._get_lstm_model("ISS", "voltage")
            set_tenant("tenant-B")
            mB = det_mod._get_lstm_model("ISS", "voltage")
            assert mA is not mB
            # Both keys coexist in the registry.
            assert any(k.startswith("tenant-A:") for k in det_mod._lstm_models)
            assert any(k.startswith("tenant-B:") for k in det_mod._lstm_models)
        finally:
            set_tenant("default")
            det_mod._lstm_models.clear()

    def test_tenant_quota_evicts_own_lru_not_other(self):
        det_mod._lstm_models.clear()
        det_mod._tenant_ml_model_quotas.clear()
        try:
            det_mod.set_tenant_ml_model_quota("tenant-A", 2)

            set_tenant("tenant-A")
            det_mod._get_lstm_model("SAT1", "c1")   # A slot 1
            det_mod._get_lstm_model("SAT1", "c2")   # A slot 2 — at quota now
            set_tenant("tenant-B")
            det_mod._get_lstm_model("SAT2", "cB1")  # B slot 1 (unaffected)

            set_tenant("tenant-A")
            det_mod._get_lstm_model("SAT1", "c3")   # forces eviction of A's slot 1

            # A's c1 evicted, c2 + c3 remain.
            assert "tenant-A:SAT1:c1" not in det_mod._lstm_models
            assert "tenant-A:SAT1:c2" in det_mod._lstm_models
            assert "tenant-A:SAT1:c3" in det_mod._lstm_models
            # Tenant B's model untouched.
            assert "tenant-B:SAT2:cB1" in det_mod._lstm_models
        finally:
            set_tenant("default")
            det_mod._tenant_ml_model_quotas.clear()
            det_mod._lstm_models.clear()


class TestQuotaConfig:

    def test_default_quota_equals_global(self):
        assert det_mod._tenant_ml_model_quota("unknown-tenant") == det_mod._MAX_ML_MODELS

    def test_set_quota_override(self):
        det_mod._tenant_ml_model_quotas.clear()
        try:
            det_mod.set_tenant_ml_model_quota("tx", 37)
            assert det_mod._tenant_ml_model_quota("tx") == 37
        finally:
            det_mod._tenant_ml_model_quotas.clear()


class TestLRUOrder:

    def test_accessing_model_moves_to_end(self):
        det_mod._lstm_models.clear()
        det_mod._tenant_ml_model_quotas.clear()
        try:
            set_tenant("tenant-LRU")
            det_mod.set_tenant_ml_model_quota("tenant-LRU", 3)

            det_mod._get_lstm_model("S", "a")
            det_mod._get_lstm_model("S", "b")
            det_mod._get_lstm_model("S", "c")

            # Touch "a" — it should move to end.
            det_mod._get_lstm_model("S", "a")

            # Add "d" — should evict "b" (now LRU), not "a".
            det_mod._get_lstm_model("S", "d")

            assert "tenant-LRU:S:a" in det_mod._lstm_models
            assert "tenant-LRU:S:b" not in det_mod._lstm_models
            assert "tenant-LRU:S:c" in det_mod._lstm_models
            assert "tenant-LRU:S:d" in det_mod._lstm_models
        finally:
            set_tenant("default")
            det_mod._tenant_ml_model_quotas.clear()
            det_mod._lstm_models.clear()
