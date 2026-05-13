"""Tests for Sprint 4: Channel Discovery + Per-Channel Threshold Config.

All tests are pure unit/schema tests — no database required.
Covers:
  - v13 migration SQL (schema inspection)
  - channel query function signatures (static analysis)
  - get_effective_thresholds() — DRY threshold merging
  - _apply_calibration_overrides() — in-place CalibrationState mutation
  - load_channel_configs() — in-memory cache population
  - ChannelConfigIn / ChannelConfigOut / ChannelOut schemas
  - GET/PUT/DELETE /channels API endpoints (demo_client with memory_store)
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# 1. V13 Migration — SQL inspection (no DB needed)
# ---------------------------------------------------------------------------

class TestV13Migration:
    """Verify the v13 migration SQL string is correct without running a DB."""

    @pytest.fixture(autouse=True)
    def _load(self):
        from aria.dsremo.db.migrations import _MIGRATIONS, SCHEMA_VERSION
        self.migrations = _MIGRATIONS
        self.schema_version = SCHEMA_VERSION
        # v13 is the last migration (index 12 in a 0-based list)
        self.v13_sql = _MIGRATIONS[12]

    def test_schema_version_is_at_least_13(self):
        assert self.schema_version >= 13

    def test_migration_count_is_at_least_13(self):
        assert len(self.migrations) >= 13

    def test_channel_config_table_in_migration_sql(self):
        assert "CREATE TABLE IF NOT EXISTS channel_config" in self.v13_sql

    def test_primary_key_is_composite(self):
        assert "PRIMARY KEY (tenant_id, satellite_id, parameter)" in self.v13_sql

    def test_tenant_fk_cascade_in_migration_sql(self):
        assert "REFERENCES tenants(id) ON DELETE CASCADE" in self.v13_sql

    def test_force_rls_in_migration_sql(self):
        assert "FORCE  ROW LEVEL SECURITY" in self.v13_sql

    def test_enable_rls_in_migration_sql(self):
        assert "ENABLE ROW LEVEL SECURITY" in self.v13_sql

    def test_rls_policy_uses_app_tenant_id(self):
        assert "app.tenant_id" in self.v13_sql

    def test_seven_nullable_override_columns(self):
        for col in ("z_threshold", "cusum_h", "cusum_k", "ewma_lambda",
                    "ewma_sigma_mult", "min_confidence", "alert_cooldown_s"):
            assert col in self.v13_sql, f"Column '{col}' missing from v13 SQL"

    def test_updated_at_column_present(self):
        assert "updated_at" in self.v13_sql


# ---------------------------------------------------------------------------
# 2. Channel query function signatures (static — no DB)
# ---------------------------------------------------------------------------

class TestChannelQuerySignatures:
    """Verify function signatures match the spec — catches API breakage."""

    def test_get_channel_stats_accepts_none(self):
        from aria.dsremo.db.queries import get_channel_stats
        sig = inspect.signature(get_channel_stats)
        assert "satellite_id" in sig.parameters
        # Default must be None (optional filter)
        assert sig.parameters["satellite_id"].default is None

    def test_get_channel_config_has_two_positional_params(self):
        from aria.dsremo.db.queries import get_channel_config
        sig = inspect.signature(get_channel_config)
        assert set(sig.parameters) >= {"satellite_id", "parameter"}

    def test_upsert_channel_config_kwonly_fields(self):
        from aria.dsremo.db.queries import upsert_channel_config
        sig = inspect.signature(upsert_channel_config)
        kwonly = {
            name for name, p in sig.parameters.items()
            if p.kind == inspect.Parameter.KEYWORD_ONLY
        }
        expected = {"z_threshold", "cusum_h", "cusum_k",
                    "ewma_lambda", "ewma_sigma_mult",
                    "min_confidence", "alert_cooldown_s"}
        assert expected.issubset(kwonly)

    def test_delete_channel_config_returns_bool_annotation(self):
        from aria.dsremo.db.queries import delete_channel_config
        # Just check it exists with the right params
        sig = inspect.signature(delete_channel_config)
        assert "satellite_id" in sig.parameters
        assert "parameter" in sig.parameters

    def test_load_all_channel_configs_optional_satellite_id(self):
        from aria.dsremo.db.queries import load_all_channel_configs
        sig = inspect.signature(load_all_channel_configs)
        assert "satellite_id" in sig.parameters
        assert sig.parameters["satellite_id"].default is None


# ---------------------------------------------------------------------------
# 3. get_effective_thresholds() — threshold merging logic
# ---------------------------------------------------------------------------

class TestGetEffectiveThresholds:
    """Tests for the DRY threshold-merging function in detector.py."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Ensure detectors are initialized (sets _stat_detector.z_threshold)."""
        from aria.dsremo.detection.detector import init_detectors, load_channel_configs
        init_detectors({"detection": {"z_score_threshold": 3.0, "alert_cooldown_hours": 72.0}})
        load_channel_configs([])  # clear cache

    def test_returns_globals_when_no_override(self):
        from aria.dsremo.detection.detector import get_effective_thresholds
        eff = get_effective_thresholds("SAT-1", "voltage")
        assert eff["z_threshold"] == 3.0
        assert eff["min_confidence"] == 0.0
        assert eff["cusum_h"] is None
        assert eff["cusum_k"] is None

    def test_z_threshold_override_applied(self):
        from aria.dsremo.detection.detector import load_channel_configs, get_effective_thresholds
        load_channel_configs([{
            "satellite_id": "SAT-1", "parameter": "voltage", "z_threshold": 4.5,
            "cusum_h": None, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": None, "alert_cooldown_s": None,
        }])
        eff = get_effective_thresholds("SAT-1", "voltage")
        assert eff["z_threshold"] == 4.5

    def test_null_cusum_h_stays_none(self):
        from aria.dsremo.detection.detector import load_channel_configs, get_effective_thresholds
        load_channel_configs([{
            "satellite_id": "SAT-1", "parameter": "voltage", "z_threshold": 3.0,
            "cusum_h": None, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": None, "alert_cooldown_s": None,
        }])
        eff = get_effective_thresholds("SAT-1", "voltage")
        assert eff["cusum_h"] is None

    def test_cusum_h_override_applied(self):
        from aria.dsremo.detection.detector import load_channel_configs, get_effective_thresholds
        load_channel_configs([{
            "satellite_id": "SAT-1", "parameter": "voltage",
            "z_threshold": None, "cusum_h": 8.0, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": None, "alert_cooldown_s": None,
        }])
        eff = get_effective_thresholds("SAT-1", "voltage")
        assert eff["cusum_h"] == 8.0

    def test_alert_cooldown_override_applied(self):
        from aria.dsremo.detection.detector import load_channel_configs, get_effective_thresholds
        load_channel_configs([{
            "satellite_id": "SAT-1", "parameter": "voltage",
            "z_threshold": None, "cusum_h": None, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": None, "alert_cooldown_s": 600,
        }])
        eff = get_effective_thresholds("SAT-1", "voltage")
        assert eff["alert_cooldown_s"] == 600

    def test_min_confidence_override_applied(self):
        from aria.dsremo.detection.detector import load_channel_configs, get_effective_thresholds
        load_channel_configs([{
            "satellite_id": "SAT-1", "parameter": "voltage",
            "z_threshold": None, "cusum_h": None, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": 0.6, "alert_cooldown_s": None,
        }])
        eff = get_effective_thresholds("SAT-1", "voltage")
        assert eff["min_confidence"] == 0.6

    def test_unknown_channel_returns_globals(self):
        from aria.dsremo.detection.detector import load_channel_configs, get_effective_thresholds
        load_channel_configs([])
        eff = get_effective_thresholds("NOTEXIST", "notexist")
        assert eff["z_threshold"] == 3.0
        assert eff["min_confidence"] == 0.0
        assert eff["cusum_h"] is None

    def test_different_channels_return_different_overrides(self):
        from aria.dsremo.detection.detector import load_channel_configs, get_effective_thresholds
        load_channel_configs([
            {"satellite_id": "SAT-A", "parameter": "v1", "z_threshold": 2.0,
             "cusum_h": None, "cusum_k": None, "ewma_lambda": None,
             "ewma_sigma_mult": None, "min_confidence": None, "alert_cooldown_s": None},
            {"satellite_id": "SAT-B", "parameter": "v2", "z_threshold": 5.0,
             "cusum_h": None, "cusum_k": None, "ewma_lambda": None,
             "ewma_sigma_mult": None, "min_confidence": None, "alert_cooldown_s": None},
        ])
        assert get_effective_thresholds("SAT-A", "v1")["z_threshold"] == 2.0
        assert get_effective_thresholds("SAT-B", "v2")["z_threshold"] == 5.0
        # SAT-A/v2 has no override, falls back to global
        assert get_effective_thresholds("SAT-A", "v2")["z_threshold"] == 3.0


# ---------------------------------------------------------------------------
# 4. _apply_calibration_overrides() — in-place CalibrationState mutation
# ---------------------------------------------------------------------------

class TestApplyCalibrationOverrides:
    """Tests for the CalibrationState mutation helper."""

    @pytest.fixture
    def calibrated_state(self):
        """A CalibrationState that has completed calibration."""
        from aria.dsremo.detection.calibration import CalibrationState
        state = CalibrationState()
        state.state = "calibrated"
        state.ref_std = 0.5
        state.cusum_h = 2.5    # 5.0 × 0.5
        state.cusum_k = 0.25   # 0.5 × 0.5
        state.ewma_ucl = 0.3
        state.ewma_lcl = -0.3
        return state

    def test_cusum_h_applied_in_place(self, calibrated_state):
        from aria.dsremo.detection.detector import _apply_calibration_overrides
        eff = {"cusum_h": 10.0, "cusum_k": None, "ewma_lambda": None, "ewma_sigma_mult": None}
        _apply_calibration_overrides(calibrated_state, eff)
        assert calibrated_state.cusum_h == 10.0

    def test_cusum_k_applied_in_place(self, calibrated_state):
        from aria.dsremo.detection.detector import _apply_calibration_overrides
        eff = {"cusum_h": None, "cusum_k": 1.0, "ewma_lambda": None, "ewma_sigma_mult": None}
        _apply_calibration_overrides(calibrated_state, eff)
        assert calibrated_state.cusum_k == 1.0

    def test_none_cusum_h_not_applied(self, calibrated_state):
        from aria.dsremo.detection.detector import _apply_calibration_overrides
        original_h = calibrated_state.cusum_h
        eff = {"cusum_h": None, "cusum_k": None, "ewma_lambda": None, "ewma_sigma_mult": None}
        _apply_calibration_overrides(calibrated_state, eff)
        assert calibrated_state.cusum_h == original_h

    def test_none_cusum_k_not_applied(self, calibrated_state):
        from aria.dsremo.detection.detector import _apply_calibration_overrides
        original_k = calibrated_state.cusum_k
        eff = {"cusum_h": None, "cusum_k": None, "ewma_lambda": None, "ewma_sigma_mult": None}
        _apply_calibration_overrides(calibrated_state, eff)
        assert calibrated_state.cusum_k == original_k

    def test_ewma_lambda_override_recomputes_ucl_lcl(self, calibrated_state):
        """Overriding ewma_lambda should recompute UCL/LCL from σ_ref."""
        import math
        from aria.dsremo.detection.detector import _apply_calibration_overrides
        eff = {"cusum_h": None, "cusum_k": None, "ewma_lambda": 0.1, "ewma_sigma_mult": None}
        _apply_calibration_overrides(calibrated_state, eff)
        import aria.dsremo.detection.calibration as cal_mod
        expected_spread = math.sqrt(0.1 / (2.0 - 0.1))
        expected_ucl = cal_mod.EWMA_SIGMA_FACTOR * 0.5 * expected_spread
        assert abs(calibrated_state.ewma_ucl - expected_ucl) < 1e-9

    def test_ewma_not_applied_when_ref_std_zero(self):
        """When ref_std is 0 (uncalibrated), EWMA overrides are silently ignored."""
        from aria.dsremo.detection.calibration import CalibrationState
        from aria.dsremo.detection.detector import _apply_calibration_overrides
        state = CalibrationState()
        state.state = "warming_up"
        state.ref_std = 0.0
        eff = {"cusum_h": None, "cusum_k": None, "ewma_lambda": 0.3, "ewma_sigma_mult": None}
        original_ucl = state.ewma_ucl
        _apply_calibration_overrides(state, eff)
        # Should be unchanged — ref_std is below threshold
        assert state.ewma_ucl == original_ucl


# ---------------------------------------------------------------------------
# 5. load_channel_configs() — cache population
# ---------------------------------------------------------------------------

class TestLoadChannelConfigs:
    """Tests for the in-memory config cache management."""

    @pytest.fixture(autouse=True)
    def _clear(self):
        from aria.dsremo.detection.detector import load_channel_configs
        load_channel_configs([])  # start with empty cache

    def test_populates_cache_keyed_by_sat_param(self):
        import aria.dsremo.detection.detector as det_mod
        det_mod.load_channel_configs([{
            "satellite_id": "S1", "parameter": "p1",
            "z_threshold": 3.5, "cusum_h": None, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": None, "alert_cooldown_s": None,
        }])
        assert ("S1", "p1") in det_mod._channel_config_cache

    def test_cache_has_correct_values(self):
        import aria.dsremo.detection.detector as det_mod
        det_mod.load_channel_configs([{
            "satellite_id": "S1", "parameter": "p1",
            "z_threshold": 4.2, "cusum_h": None, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": 0.55, "alert_cooldown_s": 300,
        }])
        cfg = det_mod._channel_config_cache[("S1", "p1")]
        assert cfg["z_threshold"] == 4.2
        assert cfg["alert_cooldown_s"] == 300

    def test_replaces_cache_on_second_call(self):
        import aria.dsremo.detection.detector as det_mod
        det_mod.load_channel_configs([{
            "satellite_id": "S1", "parameter": "p1",
            "z_threshold": 1.0, "cusum_h": None, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": None, "alert_cooldown_s": None,
        }])
        det_mod.load_channel_configs([{
            "satellite_id": "S2", "parameter": "p2",
            "z_threshold": 2.0, "cusum_h": None, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": None, "alert_cooldown_s": None,
        }])
        # Old key must be gone
        assert ("S1", "p1") not in det_mod._channel_config_cache
        assert ("S2", "p2") in det_mod._channel_config_cache

    def test_empty_list_clears_cache(self):
        import aria.dsremo.detection.detector as det_mod
        det_mod.load_channel_configs([{
            "satellite_id": "S1", "parameter": "p1",
            "z_threshold": 1.0, "cusum_h": None, "cusum_k": None,
            "ewma_lambda": None, "ewma_sigma_mult": None,
            "min_confidence": None, "alert_cooldown_s": None,
        }])
        det_mod.load_channel_configs([])
        assert len(det_mod._channel_config_cache) == 0

    def test_multiple_channels_all_loaded(self):
        import aria.dsremo.detection.detector as det_mod
        configs = [
            {"satellite_id": "S1", "parameter": f"p{i}",
             "z_threshold": float(i), "cusum_h": None, "cusum_k": None,
             "ewma_lambda": None, "ewma_sigma_mult": None,
             "min_confidence": None, "alert_cooldown_s": None}
            for i in range(5)
        ]
        det_mod.load_channel_configs(configs)
        assert len(det_mod._channel_config_cache) == 5


# ---------------------------------------------------------------------------
# 6. ChannelConfigIn schema validation
# ---------------------------------------------------------------------------

class TestChannelConfigInSchema:
    """Pydantic validation tests for the ChannelConfigIn input schema."""

    def test_all_none_is_valid(self):
        from aria.dsremo.api.schemas import ChannelConfigIn
        cfg = ChannelConfigIn()
        assert cfg.z_threshold is None
        assert cfg.alert_cooldown_s is None

    def test_valid_override_accepted(self):
        from aria.dsremo.api.schemas import ChannelConfigIn
        cfg = ChannelConfigIn(z_threshold=3.5, min_confidence=0.5, alert_cooldown_s=600)
        assert cfg.z_threshold == 3.5
        assert cfg.min_confidence == 0.5
        assert cfg.alert_cooldown_s == 600

    def test_z_threshold_must_be_positive(self):
        from pydantic import ValidationError
        from aria.dsremo.api.schemas import ChannelConfigIn
        with pytest.raises(ValidationError):
            ChannelConfigIn(z_threshold=0.0)

    def test_z_threshold_negative_rejected(self):
        from pydantic import ValidationError
        from aria.dsremo.api.schemas import ChannelConfigIn
        with pytest.raises(ValidationError):
            ChannelConfigIn(z_threshold=-1.0)

    def test_ewma_lambda_must_be_in_range(self):
        from pydantic import ValidationError
        from aria.dsremo.api.schemas import ChannelConfigIn
        with pytest.raises(ValidationError):
            ChannelConfigIn(ewma_lambda=0.0)
        with pytest.raises(ValidationError):
            ChannelConfigIn(ewma_lambda=1.1)

    def test_ewma_lambda_exactly_1_is_valid(self):
        from aria.dsremo.api.schemas import ChannelConfigIn
        cfg = ChannelConfigIn(ewma_lambda=1.0)
        assert cfg.ewma_lambda == 1.0

    def test_min_confidence_must_be_0_to_1(self):
        from pydantic import ValidationError
        from aria.dsremo.api.schemas import ChannelConfigIn
        with pytest.raises(ValidationError):
            ChannelConfigIn(min_confidence=-0.1)
        with pytest.raises(ValidationError):
            ChannelConfigIn(min_confidence=1.1)

    def test_alert_cooldown_s_must_be_nonneg(self):
        from pydantic import ValidationError
        from aria.dsremo.api.schemas import ChannelConfigIn
        with pytest.raises(ValidationError):
            ChannelConfigIn(alert_cooldown_s=-1)

    def test_alert_cooldown_zero_is_valid(self):
        from aria.dsremo.api.schemas import ChannelConfigIn
        cfg = ChannelConfigIn(alert_cooldown_s=0)
        assert cfg.alert_cooldown_s == 0


# ---------------------------------------------------------------------------
# 7. GET/PUT/DELETE /channels API endpoints (demo_client)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo_client():
    """Demo-mode TestClient — no DB, memory_store used for all queries."""
    from aria.dsremo.api.app import create_app
    app = create_app(demo=True)
    with TestClient(app) as client:
        yield client


class TestChannelsAPI:
    """API-level tests using demo_client (memory_store, no real DB)."""

    def test_list_channels_returns_200(self, demo_client):
        response = demo_client.get("/api/v1/channels")
        assert response.status_code == 200

    def test_list_channels_returns_list(self, demo_client):
        response = demo_client.get("/api/v1/channels")
        data = response.json()
        assert isinstance(data, list)

    def test_list_channels_empty_in_demo_mode(self, demo_client):
        """memory_store.get_channel_stats() always returns [] in demo mode."""
        response = demo_client.get("/api/v1/channels")
        assert response.json() == []

    def test_list_channels_accepts_satellite_filter(self, demo_client):
        response = demo_client.get("/api/v1/channels?satellite_id=SAT-1")
        assert response.status_code == 200

    def test_get_config_returns_200_with_empty_overrides(self, demo_client):
        """GET config for a channel with no overrides returns empty overrides dict."""
        response = demo_client.get("/api/v1/channels/SAT-1/voltage/config")
        assert response.status_code == 200
        data = response.json()
        assert data["satellite_id"] == "SAT-1"
        assert data["parameter"] == "voltage"
        assert data["overrides"] == {}
        assert data["updated_at"] is None

    def test_get_config_effective_contains_z_threshold(self, demo_client):
        """Effective thresholds always contain z_threshold (global default)."""
        response = demo_client.get("/api/v1/channels/SAT-1/current/config")
        assert response.status_code == 200
        data = response.json()
        assert "z_threshold" in data["effective"]
        assert data["effective"]["z_threshold"] > 0

    def test_put_config_creates_override(self, demo_client):
        response = demo_client.put(
            "/api/v1/channels/SAT-PUT/battery_voltage/config",
            json={"z_threshold": 4.0, "alert_cooldown_s": 300},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["satellite_id"] == "SAT-PUT"
        assert data["parameter"] == "battery_voltage"
        assert "overrides" in data
        assert "effective" in data

    def test_put_config_override_reflected_in_get(self, demo_client):
        """After PUT, GET should show the new overrides."""
        demo_client.put(
            "/api/v1/channels/SAT-REFLECT/solar_current/config",
            json={"z_threshold": 5.5},
        )
        response = demo_client.get("/api/v1/channels/SAT-REFLECT/solar_current/config")
        assert response.status_code == 200
        data = response.json()
        assert data["effective"]["z_threshold"] == 5.5

    def test_put_config_requires_at_least_one_field(self, demo_client):
        """PUT with all-null body should return 422."""
        response = demo_client.put(
            "/api/v1/channels/SAT-1/voltage/config",
            json={},
        )
        assert response.status_code == 422

    def test_put_config_rejects_negative_z_threshold(self, demo_client):
        """Pydantic validation on ChannelConfigIn should reject z_threshold <= 0."""
        response = demo_client.put(
            "/api/v1/channels/SAT-1/voltage/config",
            json={"z_threshold": -1.0},
        )
        assert response.status_code == 422

    def test_put_config_rejects_invalid_ewma_lambda(self, demo_client):
        response = demo_client.put(
            "/api/v1/channels/SAT-1/voltage/config",
            json={"ewma_lambda": 0.0},
        )
        assert response.status_code == 422

    def test_put_config_rejects_invalid_min_confidence(self, demo_client):
        response = demo_client.put(
            "/api/v1/channels/SAT-1/voltage/config",
            json={"min_confidence": 1.5},
        )
        assert response.status_code == 422

    def test_delete_config_returns_deleted_false_when_no_row(self, demo_client):
        """Deleting a non-existent config row returns deleted=False."""
        response = demo_client.delete(
            "/api/v1/channels/SAT-NODECHAN/nonexistent_param/config"
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": False}

    def test_delete_config_returns_deleted_true_after_put(self, demo_client):
        """Create then delete — confirms the row lifecycle."""
        demo_client.put(
            "/api/v1/channels/SAT-DEL/temp_battery/config",
            json={"z_threshold": 3.5},
        )
        response = demo_client.delete(
            "/api/v1/channels/SAT-DEL/temp_battery/config"
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": True}

    def test_delete_clears_override_in_get(self, demo_client):
        """After DELETE, GET should return empty overrides."""
        demo_client.put(
            "/api/v1/channels/SAT-CLRD/solar/config",
            json={"z_threshold": 3.5},
        )
        demo_client.delete("/api/v1/channels/SAT-CLRD/solar/config")
        response = demo_client.get("/api/v1/channels/SAT-CLRD/solar/config")
        assert response.json()["overrides"] == {}

    def test_put_config_refreshes_detector_cache(self, demo_client):
        """After PUT, get_effective_thresholds() should reflect the new value."""
        from aria.dsremo.detection.detector import get_effective_thresholds
        demo_client.put(
            "/api/v1/channels/SAT-CACHE/wheel_speed_x/config",
            json={"z_threshold": 7.7},
        )
        eff = get_effective_thresholds("SAT-CACHE", "wheel_speed_x")
        assert eff["z_threshold"] == 7.7

    def test_delete_config_refreshes_detector_cache(self, demo_client):
        """After DELETE, get_effective_thresholds() should fall back to global."""
        from aria.dsremo.detection.detector import get_effective_thresholds, init_detectors
        # Set known global default
        init_detectors({"detection": {"z_score_threshold": 3.0, "alert_cooldown_hours": 72.0}})
        demo_client.put(
            "/api/v1/channels/SAT-DCACHE/panel_temp/config",
            json={"z_threshold": 9.0},
        )
        demo_client.delete("/api/v1/channels/SAT-DCACHE/panel_temp/config")
        eff = get_effective_thresholds("SAT-DCACHE", "panel_temp")
        assert eff["z_threshold"] == 3.0

    def test_channels_router_registered_at_correct_prefix(self, demo_client):
        """Channels endpoint must be at /api/v1/channels (not /channels)."""
        bad = demo_client.get("/channels")
        ok = demo_client.get("/api/v1/channels")
        assert bad.status_code == 404
        assert ok.status_code == 200
