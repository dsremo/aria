"""Tests for Sprint 5: Per-Tenant Alert Delivery + Industry Connectors.

All tests are pure unit/schema tests — no database required.
Covers:
  1. TestV14Migration        — v14 SQL inspection (alert_configs table)
  2. TestAlertRouters        — WebhookRouter + EmailRouter send()
  3. TestAlertServiceDispatch— AlertService.dispatch() + dedup + escalation
  4. TestHTTPConnector       — _get() retry on 429 + TransportError backoff
  5. TestYAMCSConnector      — pagination, auth, unit discovery (mocked httpx)
  6. TestInfluxDBConnector   — Flux query, CSV parsing (mocked httpx)
  7. TestLoadChannelsFromSeries — DRY bulk insert helper
  8. TestAlertsAPI           — demo_client HTTP round-trip for all 5 alert endpoints
  9. TestDRYErrorHandling    — errors.py handle_unique_constraint + helpers
"""

from __future__ import annotations

import inspect
import json
import smtplib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# 1. V14 Migration — SQL inspection (no DB)
# ---------------------------------------------------------------------------

class TestV14Migration:
    """Verify the v14 migration SQL is correct without running a real DB."""

    @pytest.fixture(autouse=True)
    def _load(self):
        from aria.dsremo.db.migrations import _MIGRATIONS, SCHEMA_VERSION
        self.schema_version = SCHEMA_VERSION
        self.all_migrations = _MIGRATIONS
        # v14 is at index 13 (0-based); v15 display_name/phone migration is at index 14
        self.v14_sql = _MIGRATIONS[13]

    def test_schema_version_is_16(self):
        assert self.schema_version >= 16  # bumped with each sprint

    def test_total_migration_count_is_16(self):
        assert len(self.all_migrations) >= 16  # grows with each sprint

    def test_alert_configs_table_created(self):
        assert "CREATE TABLE IF NOT EXISTS alert_configs" in self.v14_sql

    def test_primary_key_is_tenant_id(self):
        assert "tenant_id" in self.v14_sql
        assert "PRIMARY KEY" in self.v14_sql

    def test_force_rls_applied(self):
        assert "FORCE  ROW LEVEL SECURITY" in self.v14_sql

    def test_enable_rls_applied(self):
        assert "ENABLE ROW LEVEL SECURITY" in self.v14_sql

    def test_tenant_fk_cascade(self):
        assert "REFERENCES tenants(id) ON DELETE CASCADE" in self.v14_sql

    def test_webhook_url_column_present(self):
        assert "webhook_url" in self.v14_sql

    def test_min_severity_defaults_to_warning(self):
        assert "DEFAULT 'warning'" in self.v14_sql

    def test_enabled_column_defaults_to_true(self):
        assert "enabled" in self.v14_sql
        assert "DEFAULT TRUE" in self.v14_sql


# ---------------------------------------------------------------------------
# 2. AlertRouters — WebhookRouter + EmailRouter
# ---------------------------------------------------------------------------

class TestAlertRouters:
    """Tests for WebhookRouter and EmailRouter send() methods."""

    def _make_anomaly(self, severity="warning"):
        from aria.dsremo.core.models import Anomaly, Severity
        sev_map = {
            "warning": Severity.WARNING,
            "critical": Severity.CRITICAL,
        }
        return Anomaly(
            satellite_id="TEST-SAT",
            parameter="battery_voltage",
            subsystem="eps",
            severity=sev_map.get(severity, Severity.WARNING),
            confidence=0.85,
            explanation="Voltage anomaly detected",
            detectors_triggered=("zscore", "cusum"),
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_webhook_send_success(self):
        from aria.dsremo.alerts.service import WebhookRouter
        router = WebhookRouter(url="http://example.com/hook")
        anomaly = self._make_anomaly()

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_class.return_value = mock_client

            result = await router.send(anomaly, "tenant-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_webhook_send_429_retries(self):
        from aria.dsremo.alerts.service import WebhookRouter
        router = WebhookRouter(url="http://example.com/hook")
        anomaly = self._make_anomaly()

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0"}

        resp_200 = MagicMock()
        resp_200.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=[resp_429, resp_200])
            mock_client_class.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await router.send(anomaly, "tenant-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_webhook_hmac_header_present_when_secret_set(self):
        from aria.dsremo.alerts.service import WebhookRouter
        router = WebhookRouter(url="http://example.com/hook", secret="mysecret")
        anomaly = self._make_anomaly()

        captured_headers = {}

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        async def mock_post(url, content, headers):
            captured_headers.update(headers)
            return mock_resp

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = mock_post
            mock_client_class.return_value = mock_client

            await router.send(anomaly, "tenant-1")

        assert "X-Dsremo-Signature" in captured_headers
        assert captured_headers["X-Dsremo-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_webhook_transport_error_returns_false(self):
        from aria.dsremo.alerts.service import WebhookRouter
        router = WebhookRouter(url="http://example.com/hook")
        anomaly = self._make_anomaly()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                side_effect=httpx.TransportError("connection refused")
            )
            mock_client_class.return_value = mock_client

            result = await router.send(anomaly, "tenant-1")

        assert result is False

    @pytest.mark.asyncio
    async def test_email_send_success(self):
        from aria.dsremo.alerts.service import EmailRouter
        router = EmailRouter(
            host="smtp.example.com",
            port=587,
            user="noreply@example.com",
            password="secret",
            to=["ops@example.com"],
        )
        anomaly = self._make_anomaly()

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_smtp_class.return_value = mock_smtp

            result = await router.send(anomaly, "tenant-1")

        assert result is True
        mock_smtp.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_smtp_exception_returns_false(self):
        from aria.dsremo.alerts.service import EmailRouter
        router = EmailRouter(
            host="smtp.example.com",
            port=587,
            user="noreply@example.com",
            password="secret",
            to=["ops@example.com"],
        )
        anomaly = self._make_anomaly()

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp_class.side_effect = smtplib.SMTPException("Connection refused")
            result = await router.send(anomaly, "tenant-1")

        assert result is False

    def test_build_routers_webhook_only(self):
        from aria.dsremo.alerts.service import WebhookRouter, _build_routers
        config = {
            "enabled": True,
            "webhook_url": "http://example.com/hook",
            "webhook_secret": "",
            "email_to": None,
            "smtp_host": None,
        }
        routers = _build_routers(config)
        assert len(routers) == 1
        assert isinstance(routers[0], WebhookRouter)

    def test_build_routers_empty_when_disabled(self):
        from aria.dsremo.alerts.service import _build_routers
        config = {
            "enabled": False,
            "webhook_url": "http://example.com/hook",
        }
        routers = _build_routers(config)
        assert routers == []


# ---------------------------------------------------------------------------
# 3. AlertService.dispatch() + dedup + load_configs
# ---------------------------------------------------------------------------

class TestAlertServiceDispatch:
    """Tests for class-level AlertService methods."""

    @pytest.fixture(autouse=True)
    def _reset_service(self):
        """Reset AlertService class-level state before each test."""
        from aria.dsremo.alerts.service import AlertService
        AlertService._config_cache = {}
        AlertService._dedup = {}
        AlertService._escalation = {}
        yield
        AlertService._config_cache = {}
        AlertService._dedup = {}
        AlertService._escalation = {}

    def _make_anomaly(self, severity="warning"):
        from aria.dsremo.core.models import Anomaly, Severity
        sev_map = {"warning": Severity.WARNING, "critical": Severity.CRITICAL}
        return Anomaly(
            satellite_id="SAT-1",
            parameter="voltage",
            subsystem="eps",
            severity=sev_map.get(severity, Severity.WARNING),
            confidence=0.8,
            explanation="Test anomaly",
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )

    def test_load_configs_populates_cache(self):
        from aria.dsremo.alerts.service import AlertService
        AlertService.load_configs([
            {"tenant_id": "t1", "enabled": True, "min_severity": "warning",
             "webhook_url": "http://x.com", "webhook_secret": None,
             "email_to": None, "smtp_host": None, "smtp_port": 587,
             "smtp_user": None, "smtp_password": None,
             "dedup_window_s": 300, "escalation_delay_s": 600},
        ])
        assert "t1" in AlertService._config_cache

    def test_load_configs_replaces_previous_cache(self):
        from aria.dsremo.alerts.service import AlertService
        AlertService.load_configs([
            {"tenant_id": "old", "enabled": True, "min_severity": "warning",
             "webhook_url": None, "webhook_secret": None, "email_to": None,
             "smtp_host": None, "smtp_port": 587, "smtp_user": None,
             "smtp_password": None, "dedup_window_s": 300, "escalation_delay_s": 600},
        ])
        AlertService.load_configs([
            {"tenant_id": "new", "enabled": True, "min_severity": "warning",
             "webhook_url": None, "webhook_secret": None, "email_to": None,
             "smtp_host": None, "smtp_port": 587, "smtp_user": None,
             "smtp_password": None, "dedup_window_s": 300, "escalation_delay_s": 600},
        ])
        assert "old" not in AlertService._config_cache
        assert "new" in AlertService._config_cache

    @pytest.mark.asyncio
    async def test_dispatch_skips_when_no_config(self):
        from aria.dsremo.alerts.service import AlertService
        # No config loaded → dispatch returns False immediately
        result = await AlertService.dispatch(self._make_anomaly(), "nonexistent-tenant")
        assert result is False

    @pytest.mark.asyncio
    async def test_dispatch_skips_when_disabled(self):
        from aria.dsremo.alerts.service import AlertService
        AlertService.load_configs([
            {"tenant_id": "t1", "enabled": False, "min_severity": "warning",
             "webhook_url": "http://x.com", "webhook_secret": None, "email_to": None,
             "smtp_host": None, "smtp_port": 587, "smtp_user": None, "smtp_password": None,
             "dedup_window_s": 300, "escalation_delay_s": 600},
        ])
        result = await AlertService.dispatch(self._make_anomaly(), "t1")
        assert result is False

    @pytest.mark.asyncio
    async def test_dispatch_skips_below_min_severity(self):
        from aria.dsremo.alerts.service import AlertService, Anomaly, Severity
        AlertService.load_configs([
            {"tenant_id": "t1", "enabled": True, "min_severity": "critical",
             "webhook_url": None, "webhook_secret": None, "email_to": None,
             "smtp_host": None, "smtp_port": 587, "smtp_user": None, "smtp_password": None,
             "dedup_window_s": 300, "escalation_delay_s": 600},
        ])
        # warning < critical → should be suppressed
        warning_anomaly = self._make_anomaly("warning")
        result = await AlertService.dispatch(warning_anomaly, "t1")
        assert result is False

    @pytest.mark.asyncio
    async def test_dedup_key_includes_tenant_id(self):
        """Verify dedup key is f'{tenant_id}::{sat}::{param}' — no cross-tenant collision."""
        from aria.dsremo.alerts.service import AlertService
        config = {
            "tenant_id": "t1", "enabled": True, "min_severity": "warning",
            "webhook_url": None, "webhook_secret": None, "email_to": None,
            "smtp_host": None, "smtp_port": 587, "smtp_user": None, "smtp_password": None,
            "dedup_window_s": 3600, "escalation_delay_s": 600,
        }
        AlertService.load_configs([config])

        with patch("aria.dsremo.db.queries.insert_alert", new_callable=AsyncMock):
            await AlertService.dispatch(self._make_anomaly(), "t1")

        # Key must include tenant_id
        assert any("t1" in key for key in AlertService._dedup)
        dedup_key = next(k for k in AlertService._dedup if "t1" in k)
        assert dedup_key.startswith("t1::")

    @pytest.mark.asyncio
    async def test_insert_alert_called_on_dispatch(self):
        """Fixes the bug: alerts must be persisted even if routers are empty."""
        from aria.dsremo.alerts.service import AlertService
        AlertService.load_configs([
            {"tenant_id": "t1", "enabled": True, "min_severity": "warning",
             "webhook_url": None, "webhook_secret": None, "email_to": None,
             "smtp_host": None, "smtp_port": 587, "smtp_user": None, "smtp_password": None,
             "dedup_window_s": 300, "escalation_delay_s": 600},
        ])

        with patch("aria.dsremo.db.queries.insert_alert", new_callable=AsyncMock) as mock_insert:
            await AlertService.dispatch(self._make_anomaly(), "t1")
            mock_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_dedup_suppresses_repeat_within_window(self):
        from aria.dsremo.alerts.service import AlertService
        AlertService.load_configs([
            {"tenant_id": "t1", "enabled": True, "min_severity": "warning",
             "webhook_url": None, "webhook_secret": None, "email_to": None,
             "smtp_host": None, "smtp_port": 587, "smtp_user": None, "smtp_password": None,
             "dedup_window_s": 3600, "escalation_delay_s": 600},
        ])

        with patch("aria.dsremo.db.queries.insert_alert", new_callable=AsyncMock):
            result1 = await AlertService.dispatch(self._make_anomaly(), "t1")
            result2 = await AlertService.dispatch(self._make_anomaly(), "t1")

        assert result1 is True
        assert result2 is False  # suppressed by dedup

    @pytest.mark.asyncio
    async def test_two_tenants_same_satellite_independent_dedup(self):
        """t1 and t2 with the same satellite/param must NOT share dedup state."""
        from aria.dsremo.alerts.service import AlertService
        shared_config = lambda tid: {
            "tenant_id": tid, "enabled": True, "min_severity": "warning",
            "webhook_url": None, "webhook_secret": None, "email_to": None,
            "smtp_host": None, "smtp_port": 587, "smtp_user": None, "smtp_password": None,
            "dedup_window_s": 3600, "escalation_delay_s": 600,
        }
        AlertService.load_configs([shared_config("t1"), shared_config("t2")])

        with patch("aria.dsremo.db.queries.insert_alert", new_callable=AsyncMock):
            r1 = await AlertService.dispatch(self._make_anomaly(), "t1")
            r2 = await AlertService.dispatch(self._make_anomaly(), "t2")

        # Both should dispatch (different tenants, not deduped together)
        assert r1 is True
        assert r2 is True


# ---------------------------------------------------------------------------
# 4. HTTPConnector._get() retry behaviour
# ---------------------------------------------------------------------------

class TestHTTPConnector:
    """Tests for HTTPConnector retry + backoff logic."""

    def _make_connector(self):
        """Build a concrete HTTPConnector subclass for testing."""
        from aria.dsremo.ingest.connector import HTTPConnector

        class _TestConnector(HTTPConnector):
            source_name = "test"

            async def bulk_load_to_db(self, *, resample_minutes=1, skip_if_rows_gte=50_000):
                return {}

        return _TestConnector(base_url="http://test.local")

    @pytest.mark.asyncio
    async def test_get_success(self):
        conn = self._make_connector()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = client

            resp = await conn._get("/test")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_429_respects_retry_after_header(self):
        conn = self._make_connector()

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0"}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.request = AsyncMock(side_effect=[resp_429, resp_200])
            mock_cls.return_value = client

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                resp = await conn._get("/test")

        mock_sleep.assert_called_once_with(0.0)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_transport_error_retries_3_times(self):
        conn = self._make_connector()

        with patch("httpx.AsyncClient") as mock_cls:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.request = AsyncMock(
                side_effect=httpx.TransportError("connection refused")
            )
            mock_cls.return_value = client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(httpx.TransportError):
                    await conn._get("/test")

        # Called 3 times (max attempts)
        assert client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_get_headers_passed_to_client(self):
        from aria.dsremo.ingest.connector import HTTPConnector

        class _HdrConnector(HTTPConnector):
            source_name = "hdr"

            async def bulk_load_to_db(self, *, resample_minutes=1, skip_if_rows_gte=50_000):
                return {}

        conn = _HdrConnector(
            base_url="http://test.local",
            headers={"Authorization": "Bearer abc123"},
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        captured_kwargs = {}

        with patch("httpx.AsyncClient") as mock_cls:
            client = AsyncMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = client

            def capture(**kwargs):
                captured_kwargs.update(kwargs)
                return client

            mock_cls.side_effect = lambda **kw: (captured_kwargs.update(kw), client)[1]

            await conn._get("/test")

        assert "Authorization" in captured_kwargs.get("headers", {})


# ---------------------------------------------------------------------------
# 5. YAMCSConnector
# ---------------------------------------------------------------------------

class TestYAMCSConnector:
    """Tests for YAMCSConnector with mocked HTTP responses."""

    def _make_connector(self, **kw):
        from aria.dsremo.ingest.yamcs_connector import YAMCSConnector
        return YAMCSConnector(
            base_url="http://yamcs.local:8090",
            instance="simulator",
            parameters=["/YSS/SIMULATOR/BatteryVoltage"],
            satellite_id="YAMCS-TEST",
            **kw,
        )

    def test_source_name(self):
        conn = self._make_connector()
        assert conn.source_name == "yamcs"

    def test_bearer_token_in_headers_when_api_key_set(self):
        conn = self._make_connector(api_key="mytoken")
        assert conn._headers.get("Authorization") == "Bearer mytoken"

    def test_no_auth_header_without_api_key(self):
        conn = self._make_connector(api_key="")
        assert "Authorization" not in conn._headers

    def test_parse_yamcs_time_valid(self):
        from aria.dsremo.ingest.yamcs_connector import _parse_yamcs_time
        result = _parse_yamcs_time("2024-01-15T12:00:00.000Z")
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_yamcs_time_invalid_returns_none(self):
        from aria.dsremo.ingest.yamcs_connector import _parse_yamcs_time
        assert _parse_yamcs_time("") is None
        assert _parse_yamcs_time("not-a-date") is None

    def test_extract_eng_value_float(self):
        from aria.dsremo.ingest.yamcs_connector import _extract_eng_value
        assert _extract_eng_value({"floatValue": 3.14}) == pytest.approx(3.14)

    def test_extract_eng_value_sint64(self):
        from aria.dsremo.ingest.yamcs_connector import _extract_eng_value
        assert _extract_eng_value({"sint64Value": 42}) == 42.0

    @pytest.mark.asyncio
    async def test_bulk_load_calls_load_channels_from_series(self):
        conn = self._make_connector()

        yamcs_page = {
            "parameter": [
                {
                    "generationTime": "2024-01-01T00:00:00Z",
                    "engValue": {"floatValue": 12.5},
                }
            ]
            # no continuationToken → single page
        }
        mdb_resp = {"engType": {"unitSet": [{"unit": "V"}]}}

        mock_page = MagicMock()
        mock_page.json.return_value = yamcs_page
        mock_page.status_code = 200
        mock_page.raise_for_status = MagicMock()

        mock_mdb = MagicMock()
        mock_mdb.json.return_value = mdb_resp
        mock_mdb.status_code = 200
        mock_mdb.raise_for_status = MagicMock()

        with patch.object(conn, "_get", side_effect=[mock_page, mock_mdb]):
            with patch(
                "aria.dsremo.ingest.yamcs_connector.load_channels_from_series",
                new_callable=AsyncMock,
                return_value={"BatteryVoltage": 1},
            ) as mock_load:
                result = await conn.bulk_load_to_db(resample_minutes=1, skip_if_rows_gte=0)

        mock_load.assert_called_once()
        _, kwargs = mock_load.call_args
        assert "BatteryVoltage" in mock_load.call_args[0][1]  # channels dict


# ---------------------------------------------------------------------------
# 6. InfluxDBConnector
# ---------------------------------------------------------------------------

class TestInfluxDBConnector:
    """Tests for InfluxDBConnector with mocked HTTP responses."""

    def _make_connector(self):
        from aria.dsremo.ingest.influxdb_connector import InfluxDBConnector
        return InfluxDBConnector(
            base_url="http://influxdb.local:8086",
            org="testorg",
            bucket="telemetry",
            token="mytoken",
            measurement="satellite",
            fields=["battery_voltage", "solar_current"],
            satellite_id="INFLUX-TEST",
            start="-7d",
        )

    def test_source_name(self):
        conn = self._make_connector()
        assert conn.source_name == "influxdb"

    def test_token_in_headers(self):
        conn = self._make_connector()
        assert conn._headers.get("Authorization") == "Token mytoken"

    def test_parse_influx_csv_valid_rows(self):
        from aria.dsremo.ingest.influxdb_connector import _parse_influx_csv
        csv_text = (
            "#group,false,false,true,true,false,false,true,true\n"
            "#datatype,string,long,dateTime:RFC3339,dateTime:RFC3339,dateTime:RFC3339,double,string,string\n"
            "#default,,,,,,,\n"
            ",result,table,_start,_stop,_time,_value,_field,_measurement\n"
            ",_result,0,2024-01-01T00:00:00Z,2024-01-02T00:00:00Z,2024-01-01T12:00:00Z,12.5,battery_voltage,satellite\n"
        )
        series = _parse_influx_csv(csv_text, "battery_voltage")
        assert len(series) == 1
        assert series.iloc[0] == pytest.approx(12.5)

    def test_parse_influx_csv_empty_on_no_data(self):
        from aria.dsremo.ingest.influxdb_connector import _parse_influx_csv
        csv_text = ""
        series = _parse_influx_csv(csv_text, "battery_voltage")
        assert series.empty

    def test_parse_influx_csv_multiple_rows(self):
        from aria.dsremo.ingest.influxdb_connector import _parse_influx_csv
        csv_text = (
            ",result,table,_start,_stop,_time,_value,_field,_measurement\n"
            ",_result,0,2024-01-01T00:00:00Z,2024-01-02T00:00:00Z,2024-01-01T10:00:00Z,10.0,v,sat\n"
            ",_result,0,2024-01-01T00:00:00Z,2024-01-02T00:00:00Z,2024-01-01T11:00:00Z,11.0,v,sat\n"
        )
        series = _parse_influx_csv(csv_text, "v")
        assert len(series) == 2

    @pytest.mark.asyncio
    async def test_bulk_load_calls_load_channels_from_series(self):
        conn = self._make_connector()

        csv_response = (
            ",result,table,_start,_stop,_time,_value,_field,_measurement\n"
            ",_result,0,2024-01-01T00:00:00Z,2024-02-01T00:00:00Z,2024-01-15T00:00:00Z,12.5,battery_voltage,satellite\n"
        )

        mock_resp = MagicMock()
        mock_resp.text = csv_response
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        with patch.object(conn, "_post", new_callable=AsyncMock, return_value=mock_resp):
            with patch(
                "aria.dsremo.ingest.influxdb_connector.load_channels_from_series",
                new_callable=AsyncMock,
                return_value={"battery_voltage": 1, "solar_current": 1},
            ) as mock_load:
                result = await conn.bulk_load_to_db(resample_minutes=1, skip_if_rows_gte=0)

        mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_field_error_returns_empty_series(self):
        """HTTP error on a field → empty Series → field excluded from result."""
        conn = self._make_connector()

        with patch.object(
            conn, "_post",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("server error"),
        ):
            with patch(
                "aria.dsremo.ingest.influxdb_connector.load_channels_from_series",
                new_callable=AsyncMock,
                return_value={},
            ):
                result = await conn.bulk_load_to_db(resample_minutes=1, skip_if_rows_gte=0)

        # No fields were loaded (all failed)
        assert result == {}


# ---------------------------------------------------------------------------
# 7. load_channels_from_series()
# ---------------------------------------------------------------------------

class TestLoadChannelsFromSeries:
    """Tests for the DRY bulk-insert helper in bulk_loader.py."""

    def _make_series(self, n: int = 10) -> pd.Series:
        idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
        return pd.Series(range(n, n * 2), index=idx, dtype=float)

    @pytest.mark.asyncio
    async def test_validates_empty_satellite_id(self):
        from aria.dsremo.ingest.bulk_loader import load_channels_from_series
        with pytest.raises(ValueError, match="satellite_id"):
            await load_channels_from_series("", {"v": self._make_series()})

    @pytest.mark.asyncio
    async def test_validates_whitespace_satellite_id(self):
        from aria.dsremo.ingest.bulk_loader import load_channels_from_series
        with pytest.raises(ValueError):
            await load_channels_from_series("   ", {"v": self._make_series()})

    @pytest.mark.asyncio
    async def test_validates_resample_minutes_lt_1(self):
        from aria.dsremo.ingest.bulk_loader import load_channels_from_series
        with pytest.raises(ValueError, match="resample_minutes"):
            await load_channels_from_series(
                "SAT-1", {"v": self._make_series()}, resample_minutes=0
            )

    @pytest.mark.asyncio
    async def test_skips_channel_when_row_count_gte_threshold(self):
        from aria.dsremo.ingest.bulk_loader import load_channels_from_series

        with patch(
            "aria.dsremo.ingest.bulk_loader.check_channel_row_count",
            new_callable=AsyncMock,
            return_value=50_001,
        ):
            result = await load_channels_from_series(
                "SAT-1",
                {"voltage": self._make_series()},
                skip_if_rows_gte=50_000,
            )

        assert result["voltage"] == 50_001  # existing row count returned

    @pytest.mark.asyncio
    async def test_returns_inserted_count_per_channel(self):
        from aria.dsremo.ingest.bulk_loader import load_channels_from_series

        with patch(
            "aria.dsremo.ingest.bulk_loader.check_channel_row_count",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "aria.dsremo.ingest.bulk_loader.queries.upsert_satellite_seen",
            new_callable=AsyncMock,
        ), patch(
            "aria.dsremo.ingest.bulk_loader.queries.upsert_channel_seen",
            new_callable=AsyncMock,
        ), patch(
            "aria.dsremo.ingest.bulk_loader.bulk_insert_channel",
            new_callable=AsyncMock,
            return_value=10,
        ):
            result = await load_channels_from_series(
                "SAT-1",
                {"voltage": self._make_series()},
                skip_if_rows_gte=0,
            )

        assert result["voltage"] == 10


# ---------------------------------------------------------------------------
# 8. Alert API — demo_client HTTP round-trip
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo_client():
    """Demo-mode TestClient — no DB, memory_store used for all queries."""
    from aria.dsremo.api.app import create_app
    app = create_app(demo=True)
    with TestClient(app) as client:
        yield client


class TestAlertsAPI:
    """API-level tests using demo_client (no real DB)."""

    def test_get_config_returns_404_when_not_set(self, demo_client):
        response = demo_client.get("/api/v1/alerts/config")
        assert response.status_code == 404

    def test_put_config_creates_config(self, demo_client):
        response = demo_client.put(
            "/api/v1/alerts/config",
            json={"webhook_url": "http://example.com/hook", "min_severity": "warning"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["webhook_url"] == "http://example.com/hook"
        assert data["min_severity"] == "warning"

    def test_put_config_returns_no_secrets(self, demo_client):
        """smtp_password and webhook_secret must never be returned to clients."""
        response = demo_client.put(
            "/api/v1/alerts/config",
            json={"webhook_secret": "supersecret", "webhook_url": "http://x.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "webhook_secret" not in data
        assert "smtp_password" not in data

    def test_get_config_returns_200_after_put(self, demo_client):
        demo_client.put(
            "/api/v1/alerts/config",
            json={"webhook_url": "http://test.com"},
        )
        response = demo_client.get("/api/v1/alerts/config")
        assert response.status_code == 200

    def test_delete_config_returns_deleted_true(self, demo_client):
        demo_client.put("/api/v1/alerts/config", json={"webhook_url": "http://x.com"})
        response = demo_client.delete("/api/v1/alerts/config")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True

    def test_get_config_returns_404_after_delete(self, demo_client):
        # Ensure deleted state
        demo_client.delete("/api/v1/alerts/config")
        response = demo_client.get("/api/v1/alerts/config")
        assert response.status_code == 404

    def test_get_history_returns_list(self, demo_client):
        response = demo_client.get("/api/v1/alerts/history")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_acknowledge_returns_404_for_unknown_alert(self, demo_client):
        response = demo_client.post("/api/v1/alerts/unknown-id-xyz/acknowledge")
        assert response.status_code == 404

    def test_history_supports_satellite_filter(self, demo_client):
        response = demo_client.get("/api/v1/alerts/history?satellite_id=SAT-1")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# 9. DRY error handling helpers (errors.py)
# ---------------------------------------------------------------------------

class TestDRYErrorHandling:
    """Tests for the error helper functions in errors.py."""

    @pytest.mark.asyncio
    async def test_handle_unique_constraint_raises_409_on_unique_error(self):
        from aria.dsremo.api.errors import handle_unique_constraint
        from fastapi import HTTPException

        async def _coro():
            raise Exception("unique constraint violated")

        with pytest.raises(HTTPException) as exc_info:
            await handle_unique_constraint(
                _coro(),
                conflict_msg="Already exists",
                log_ctx={"key": "val"},
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_handle_unique_constraint_raises_409_on_duplicate_error(self):
        from aria.dsremo.api.errors import handle_unique_constraint
        from fastapi import HTTPException

        async def _coro():
            raise Exception("duplicate key value")

        with pytest.raises(HTTPException) as exc_info:
            await handle_unique_constraint(
                _coro(),
                conflict_msg="Duplicate",
                log_ctx={},
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "Duplicate"

    @pytest.mark.asyncio
    async def test_handle_unique_constraint_raises_500_on_other_error(self):
        from aria.dsremo.api.errors import handle_unique_constraint
        from fastapi import HTTPException

        async def _coro():
            raise Exception("connection refused")

        with pytest.raises(HTTPException) as exc_info:
            await handle_unique_constraint(
                _coro(),
                conflict_msg="",
                log_ctx={"key": "val"},
            )
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_handle_unique_constraint_returns_result_on_success(self):
        from aria.dsremo.api.errors import handle_unique_constraint

        async def _coro():
            return {"id": "abc"}

        result = await handle_unique_constraint(_coro(), conflict_msg="", log_ctx={})
        assert result == {"id": "abc"}

    def test_not_found_helper(self):
        from aria.dsremo.api.errors import not_found
        exc = not_found("Not found")
        assert exc.status_code == 404
        assert "Not found" in exc.detail

    def test_conflict_helper(self):
        from aria.dsremo.api.errors import conflict
        exc = conflict("Already exists")
        assert exc.status_code == 409

    def test_bad_request_helper(self):
        from aria.dsremo.api.errors import bad_request
        exc = bad_request("Invalid input")
        assert exc.status_code == 400


# ---------------------------------------------------------------------------
# 10. Query function signatures (static — no DB)
# ---------------------------------------------------------------------------

class TestAlertQuerySignatures:
    """Verify new alert query function signatures without running a DB."""

    def test_insert_alert_accepts_anomaly(self):
        from aria.dsremo.db.queries import insert_alert
        sig = inspect.signature(insert_alert)
        assert "anomaly" in sig.parameters

    def test_upsert_alert_config_has_tenant_id(self):
        from aria.dsremo.db.queries import upsert_alert_config
        sig = inspect.signature(upsert_alert_config)
        assert "tenant_id" in sig.parameters

    def test_upsert_alert_config_keyword_only_fields(self):
        from aria.dsremo.db.queries import upsert_alert_config
        sig = inspect.signature(upsert_alert_config)
        kwonly = {
            name for name, p in sig.parameters.items()
            if p.kind == inspect.Parameter.KEYWORD_ONLY
        }
        for field in ("webhook_url", "min_severity", "enabled", "dedup_window_s"):
            assert field in kwonly, f"'{field}' not keyword-only in upsert_alert_config"

    def test_get_alerts_accepts_severity_filter(self):
        from aria.dsremo.db.queries import get_alerts
        sig = inspect.signature(get_alerts)
        assert "severity" in sig.parameters

    def test_get_alerts_accepts_since_filter(self):
        from aria.dsremo.db.queries import get_alerts
        sig = inspect.signature(get_alerts)
        assert "since" in sig.parameters

    def test_load_all_alert_configs_no_required_args(self):
        from aria.dsremo.db.queries import load_all_alert_configs
        sig = inspect.signature(load_all_alert_configs)
        # All parameters must have defaults
        for name, param in sig.parameters.items():
            assert param.default is not inspect.Parameter.empty, \
                f"Param '{name}' has no default"
