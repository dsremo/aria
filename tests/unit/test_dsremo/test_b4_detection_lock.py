"""Tests for V3-B4: per-satellite asyncio lock around run_detection_cycle.

The production race: two ingestion tasks for the same satellite read the
same calibration state, compute updates, and both write back — one sample
is silently dropped from the reference distribution.

These tests verify:
 1. `_detection_lock_for(sat)` returns the same Lock for repeated calls.
 2. Two concurrent `run_detection_cycle` calls for the same satellite
    serialise — only one runs the body at a time.
 3. Different satellites run in parallel (no cross-contamination).
 4. The lock is released on exception, so a failing cycle does not
    deadlock subsequent cycles for the same satellite.
"""

from __future__ import annotations

import asyncio

import pytest

from aria.dsremo.detection import detector as det_mod


class TestLockRegistry:

    def test_same_lock_per_satellite(self):
        det_mod._detection_locks.clear()
        try:
            a1 = det_mod._detection_lock_for("SAT-A")
            a2 = det_mod._detection_lock_for("SAT-A")
            assert a1 is a2
        finally:
            det_mod._detection_locks.clear()

    def test_distinct_lock_per_satellite(self):
        det_mod._detection_locks.clear()
        try:
            a = det_mod._detection_lock_for("SAT-A")
            b = det_mod._detection_lock_for("SAT-B")
            assert a is not b
        finally:
            det_mod._detection_locks.clear()


class TestSerialisation:

    @pytest.mark.asyncio
    async def test_same_satellite_cycles_serialise(self, monkeypatch):
        """Two concurrent cycles for SAT-X must not overlap.  We monkey-patch
        the body to record concurrency — if serialisation is broken, the
        observed overlap count will be > 0."""
        det_mod._detection_locks.clear()

        in_flight = 0
        max_overlap = 0

        async def fake_body(satellite_id: str):
            nonlocal in_flight, max_overlap
            in_flight += 1
            max_overlap = max(max_overlap, in_flight)
            # Yield control so a concurrent task can interleave here if the
            # lock is not held.
            await asyncio.sleep(0.01)
            in_flight -= 1
            return []

        monkeypatch.setattr(det_mod, "_run_detection_cycle_body", fake_body)

        try:
            await asyncio.gather(
                det_mod.run_detection_cycle("SAT-X"),
                det_mod.run_detection_cycle("SAT-X"),
                det_mod.run_detection_cycle("SAT-X"),
            )
        finally:
            det_mod._detection_locks.clear()

        assert max_overlap == 1

    @pytest.mark.asyncio
    async def test_different_satellites_run_in_parallel(self, monkeypatch):
        """SAT-A and SAT-B have distinct locks — they should overlap."""
        det_mod._detection_locks.clear()

        overlaps_observed = 0
        in_flight_sats: set[str] = set()

        async def fake_body(satellite_id: str):
            nonlocal overlaps_observed
            in_flight_sats.add(satellite_id)
            if len(in_flight_sats) > 1:
                overlaps_observed += 1
            await asyncio.sleep(0.02)
            in_flight_sats.discard(satellite_id)
            return []

        monkeypatch.setattr(det_mod, "_run_detection_cycle_body", fake_body)

        try:
            await asyncio.gather(
                det_mod.run_detection_cycle("SAT-A"),
                det_mod.run_detection_cycle("SAT-B"),
            )
        finally:
            det_mod._detection_locks.clear()

        assert overlaps_observed > 0


class TestExceptionSafety:

    @pytest.mark.asyncio
    async def test_lock_released_on_exception(self, monkeypatch):
        """A failing cycle must not leave its satellite's lock permanently held."""
        det_mod._detection_locks.clear()
        calls = {"n": 0}

        async def fake_body(satellite_id: str):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom on first try")
            return []

        monkeypatch.setattr(det_mod, "_run_detection_cycle_body", fake_body)

        try:
            with pytest.raises(RuntimeError):
                await det_mod.run_detection_cycle("SAT-EXC")
            # If the lock stayed held, this second call would deadlock.
            result = await det_mod.run_detection_cycle("SAT-EXC")
            assert result == []
            assert calls["n"] == 2
        finally:
            det_mod._detection_locks.clear()
