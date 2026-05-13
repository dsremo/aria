"""Tests for V3-B3: hot/cold calibration DB split (memory store fallback).

These tests exercise the public query API via the memory-store fallback
so they run without a live PostgreSQL connection.  A follow-up
integration test will exercise the real migration v22 + RLS; that
requires the db-integration test harness.
"""

from __future__ import annotations

import asyncio

import pytest

from aria.dsremo.core.tenant import set_tenant
from aria.dsremo.db import memory_store


SAT = "SAT-B3-01"


@pytest.fixture(autouse=True)
def _clear_stores():
    memory_store._calibration_hot.clear()
    memory_store._calibration_cold.clear()
    set_tenant("default")
    yield
    memory_store._calibration_hot.clear()
    memory_store._calibration_cold.clear()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestHotUpsert:

    def test_initial_insert(self):
        row = _run(memory_store.upsert_calibration_hot(
            SAT, "bat_v",
            running_sum=12.4,
            running_sumsq=78.3,
            sample_count=5,
            last_value=3.1, last_value_epoch=1_700_000_001.0,
        ))
        assert row["running_sum"] == pytest.approx(12.4)
        assert row["sample_count"] == 5

    def test_upsert_overwrites(self):
        _run(memory_store.upsert_calibration_hot(
            SAT, "bat_v", running_sum=1.0, running_sumsq=1.0, sample_count=1,
        ))
        _run(memory_store.upsert_calibration_hot(
            SAT, "bat_v", running_sum=2.0, running_sumsq=4.0, sample_count=2,
        ))
        row = _run(memory_store.get_calibration_hot(SAT, "bat_v"))
        assert row["sample_count"] == 2
        assert row["running_sum"] == pytest.approx(2.0)

    def test_get_returns_none_when_absent(self):
        assert _run(memory_store.get_calibration_hot(SAT, "nope")) is None

    def test_rejects_negative_sample_count(self):
        with pytest.raises(ValueError):
            _run(memory_store.upsert_calibration_hot(
                SAT, "bat_v",
                running_sum=0.0, running_sumsq=0.0, sample_count=-1,
            ))

    def test_per_tenant_isolation(self):
        set_tenant("alpha")
        _run(memory_store.upsert_calibration_hot(
            SAT, "bat_v", running_sum=7.0, running_sumsq=49.0, sample_count=7,
        ))
        set_tenant("beta")
        assert _run(memory_store.get_calibration_hot(SAT, "bat_v")) is None
        # Put a different row for beta
        _run(memory_store.upsert_calibration_hot(
            SAT, "bat_v", running_sum=1.5, running_sumsq=2.25, sample_count=1,
        ))
        # Switch back and verify alpha's row unchanged
        set_tenant("alpha")
        alpha_row = _run(memory_store.get_calibration_hot(SAT, "bat_v"))
        assert alpha_row["sample_count"] == 7


class TestColdSidecar:

    def test_upsert_and_get_json(self):
        payload = {
            "ar1_phi":  0.73,
            "gmm": {"weights": [0.6, 0.4], "means": [7.4, 7.5], "stds": [0.02, 0.015]},
            "bocpd": {"max_run": 300, "alpha": 1.0},
        }
        _run(memory_store.upsert_calibration_cold(SAT, "bat_v", payload))
        got = _run(memory_store.get_calibration_cold(SAT, "bat_v"))
        assert got == payload

    def test_cold_get_returns_none_when_absent(self):
        assert _run(memory_store.get_calibration_cold(SAT, "nope")) is None

    def test_cold_is_deep_copied(self):
        payload = {"ar1_phi": 0.5}
        _run(memory_store.upsert_calibration_cold(SAT, "bat_v", payload))
        payload["ar1_phi"] = 99.0
        got = _run(memory_store.get_calibration_cold(SAT, "bat_v"))
        assert got["ar1_phi"] == pytest.approx(0.5)

    def test_cold_per_tenant_isolation(self):
        set_tenant("alpha")
        _run(memory_store.upsert_calibration_cold(SAT, "bat_v", {"ar1_phi": 0.8}))
        set_tenant("beta")
        assert _run(memory_store.get_calibration_cold(SAT, "bat_v")) is None


class TestMigrationVersion:

    def test_schema_version_bumped_to_22(self):
        from aria.dsremo.db import migrations as mig
        assert mig.SCHEMA_VERSION == 22
        # Migration list length = SCHEMA_VERSION
        assert len(mig._MIGRATIONS) == 22

    def test_v22_contains_calibration_hot(self):
        from aria.dsremo.db import migrations as mig
        v22_sql = mig._MIGRATIONS[21]
        assert "CREATE TABLE IF NOT EXISTS calibration_hot" in v22_sql
        assert "DOUBLE PRECISION" in v22_sql
        assert "FORCE  ROW LEVEL SECURITY" in v22_sql or "FORCE ROW LEVEL SECURITY" in v22_sql
        assert "ADD COLUMN IF NOT EXISTS cold_params JSONB" in v22_sql

    def test_v22_hot_has_typed_columns_not_jsonb(self):
        from aria.dsremo.db import migrations as mig
        v22_sql = mig._MIGRATIONS[21]
        # Extract JUST the CREATE TABLE calibration_hot column block.
        start = v22_sql.find("CREATE TABLE IF NOT EXISTS calibration_hot")
        assert start >= 0
        # Grab to the closing ");" of the CREATE TABLE.
        open_paren = v22_sql.find("(", start)
        depth = 1
        idx = open_paren + 1
        while idx < len(v22_sql) and depth > 0:
            c = v22_sql[idx]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            idx += 1
        hot_block = v22_sql[open_paren: idx]
        # Typed columns live inside the block; no JSONB column allowed there.
        assert "running_sum       DOUBLE PRECISION" in hot_block
        assert "running_sumsq     DOUBLE PRECISION" in hot_block
        assert "sample_count      BIGINT" in hot_block
        assert "JSONB" not in hot_block
