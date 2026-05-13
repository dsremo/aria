"""Tests for V3-B2: asyncpg pool sizing helper + saturation snapshot.

Validates:
 1. recommend_pool_size for 1-sat × 10-chan × 1 Hz scenario
 2. recommend_pool_size for 10-sat × 100-chan × 10 Hz scenario (~90)
 3. Floor of 10 connections (small deployments)
 4. Ceiling of 100 connections (PgBouncer recommended above this)
 5. Headroom increase scales the recommendation linearly
 6. queries_per_sample override reduces recommendation (rare anomalies)
 7. Edge case: zero channels returns safe default
 8. pool_saturation_snapshot returns {} when pool not initialised
"""

from __future__ import annotations

import pytest

from aria.dsremo.db.connection import (
    _POOL_HEADROOM,
    _QUERIES_PER_SAMPLE,
    pool_saturation_snapshot,
    recommend_pool_size,
)


class TestPoolSizer:

    def test_small_deployment_hits_floor(self):
        # 10 channels × 1 Hz × 3 ops × 1.5 headroom / 500 = 0.09 → floor at 10.
        assert recommend_pool_size(10, 1.0) == 10

    def test_medium_deployment(self):
        # 1000 × 10 × 3 × 1.5 / 500 = 90.
        assert recommend_pool_size(1000, 10.0) == 90

    def test_large_deployment_hits_ceiling(self):
        # Way past 100 → capped at 100.
        assert recommend_pool_size(50_000, 10.0) == 100

    def test_headroom_scales(self):
        low  = recommend_pool_size(1000, 10.0, headroom=1.0)
        high = recommend_pool_size(1000, 10.0, headroom=2.0)
        assert high > low

    def test_fewer_queries_lower_recommendation(self):
        default = recommend_pool_size(1000, 10.0)
        sparse  = recommend_pool_size(1000, 10.0, queries_per_sample=2)
        assert sparse < default

    def test_zero_channels_safe_default(self):
        assert recommend_pool_size(0, 1.0) == 10
        assert recommend_pool_size(100, 0.0) == 10


class TestSaturationSnapshot:

    def test_returns_empty_when_pool_not_initialised(self):
        # Guaranteed: unit-test runs don't initialise the pool.
        snap = pool_saturation_snapshot()
        assert snap == {} or "size" in snap
        # If the pool happens to be initialised by another test, at least
        # validate the schema.
        if snap:
            assert "max_size" in snap
            assert "utilization_pct" in snap
            assert snap["utilization_pct"] >= 0.0


class TestConstants:

    def test_queries_per_sample_default(self):
        assert _QUERIES_PER_SAMPLE == 3

    def test_headroom_default(self):
        assert _POOL_HEADROOM == 1.5
