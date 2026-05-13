"""Unit tests for aria.simulation.light_lag_comms."""
from __future__ import annotations

import math
import pytest

from aria.simulation.light_lag_comms import (
    C_M_S, LY_M,
    Command, CommandStatus, LightLagCommandQueue,
    boost_cruise_decel_distance, constant_cruise_distance,
)


# Speed-of-light delay helpers (years)
def _light_yr(distance_m: float) -> float:
    return (distance_m / C_M_S) / (365.25 * 24 * 3600)


# ── Distance helpers ─────────────────────────────────────────────────

class TestDistanceFns:
    def test_constant_cruise_zero_at_zero(self):
        d = constant_cruise_distance(0.1)
        assert d(0.0) == 0.0

    def test_constant_cruise_grows_linearly(self):
        d = constant_cruise_distance(0.1)
        # 0.1c × 1 yr = 0.1 ly
        assert d(1.0) == pytest.approx(0.1 * LY_M, rel=1e-6)

    def test_three_phase_profile(self):
        """1 yr boost + 8 yr cruise @ 0.1c + 1 yr decel."""
        d = boost_cruise_decel_distance(1.0, 8.0, 1.0, 0.1)
        # End of boost: average v = 0.05c → 0.05 ly
        assert d(1.0) == pytest.approx(0.05 * LY_M, rel=0.05)
        # End of cruise: 0.05 + 0.8 = 0.85 ly
        assert d(9.0) == pytest.approx(0.85 * LY_M, rel=0.01)
        # End of decel: 0.85 + 0.05 = 0.90 ly
        assert d(10.0) == pytest.approx(0.90 * LY_M, rel=0.05)
        # After arrival, distance frozen
        assert d(50.0) == pytest.approx(d(10.0), rel=1e-9)


# ── Round-trip latency ──────────────────────────────────────────────

class TestLatency:
    def test_alpha_centauri_round_trip(self):
        # Park the spacecraft at 4.24 ly (constant)
        q = LightLagCommandQueue(distance_at_yr=lambda yr: 4.24 * LY_M)
        rtt = q.round_trip_latency_yr()
        assert rtt == pytest.approx(8.48, rel=1e-3)

    def test_one_way_at_one_au(self):
        # 1 AU one-way ≈ 8.32 minutes ≈ 1.583e-5 yr
        from aria.simulation.light_lag_comms import AU_M
        q = LightLagCommandQueue(distance_at_yr=lambda yr: AU_M)
        rtt_yr = q.round_trip_latency_yr()
        rtt_min = rtt_yr * 365.25 * 24 * 60
        # 16.6 min round-trip
        assert rtt_min == pytest.approx(16.6, rel=0.05)


# ── Issue / advance / ack lifecycle ─────────────────────────────────

class TestLifecycle:
    def _q(self, d_m: float) -> LightLagCommandQueue:
        return LightLagCommandQueue(distance_at_yr=lambda yr: d_m)

    def test_issue_creates_pending_command(self):
        q = self._q(0.1 * LY_M)
        cmd = q.issue("ping", {})
        assert cmd.status is CommandStatus.PENDING
        assert q.in_flight() == [cmd]

    def test_command_arrives_after_one_light_time(self):
        d = 0.1 * LY_M
        q = self._q(d)
        cmd = q.issue("ping", {})
        # Half a light-time — command still in flight
        q.advance_earth_clock(_light_yr(d) / 2.0)
        assert cmd.status is CommandStatus.PENDING
        # Advance past arrival, but not past ACK return
        q.advance_earth_clock(_light_yr(d) * 1.01)
        # After arrival, status is DONE on spacecraft (not yet ACKED)
        assert cmd.status in (CommandStatus.DONE, CommandStatus.EXECUTING)

    def test_ack_returns_after_round_trip(self):
        d = 0.1 * LY_M
        q = self._q(d)
        cmd = q.issue("ping", {})
        rtt = 2.0 * _light_yr(d)
        q.advance_earth_clock(rtt * 1.01)
        assert cmd.status is CommandStatus.ACKED
        assert cmd.response == {"ok": True}
        assert cmd not in q.in_flight()

    def test_clock_cannot_run_backward(self):
        q = self._q(LY_M)
        q.advance_earth_clock(2.0)
        with pytest.raises(ValueError, match="cannot run backward"):
            q.advance_earth_clock(1.0)

    def test_autonomous_handler_executed(self):
        called = {}
        def handler(payload):
            called["seen"] = payload
            return {"echo": payload.get("data")}
        q = LightLagCommandQueue(
            distance_at_yr=lambda yr: 0.01 * LY_M,
            autonomous_handlers={"hello": handler},
        )
        cmd = q.issue("hello", {"data": 42})
        rtt = 2.0 * _light_yr(0.01 * LY_M)
        q.advance_earth_clock(rtt * 1.01)
        assert cmd.response == {"echo": 42}
        assert called["seen"]["data"] == 42

    def test_handler_failure_marks_failed(self):
        def bad(_p):
            raise RuntimeError("boom")
        q = LightLagCommandQueue(
            distance_at_yr=lambda yr: 0.01 * LY_M,
            autonomous_handlers={"oops": bad},
        )
        cmd = q.issue("oops", {})
        rtt = 2.0 * _light_yr(0.01 * LY_M)
        q.advance_earth_clock(rtt * 1.01)
        assert cmd.status is CommandStatus.FAILED
        assert "boom" in cmd.response.get("error", "")


# ── Real-world scenarios ────────────────────────────────────────────

class TestScenarios:
    def test_alpha_centauri_8_year_round_trip(self):
        """Issue a command at year 0; it shouldn't ACK until year ≥ 8.48."""
        q = LightLagCommandQueue(distance_at_yr=lambda yr: 4.24 * LY_M)
        cmd = q.issue("status", {})
        # Anything earlier than 8.4 yr is too early
        q.advance_earth_clock(7.0)
        assert cmd.status is not CommandStatus.ACKED
        # Advance past round-trip
        q.advance_earth_clock(9.0)
        assert cmd.status is CommandStatus.ACKED

    def test_in_flight_count_during_burst(self):
        """Issue 5 commands in quick succession — all 5 in flight until
        the first ACK returns."""
        q = LightLagCommandQueue(distance_at_yr=lambda yr: 0.5 * LY_M)
        for _ in range(5):
            q.issue("status", {})
        assert len(q.in_flight()) == 5
        # Advance halfway through the round-trip
        q.advance_earth_clock(0.5)
        # Still all in flight
        assert len(q.in_flight()) == 5

    def test_distance_changes_during_outbound(self):
        """If spacecraft is moving away, return latency is *longer* than
        outbound — the ACK has more distance to cross."""
        # Linear cruise at 0.1c
        q = LightLagCommandQueue(distance_at_yr=constant_cruise_distance(0.1))
        # Issue at year 1 (distance = 0.1 ly), so light-time out ≈ 0.1 yr
        q.advance_earth_clock(1.0)
        cmd = q.issue("ping", {})
        q.advance_earth_clock(2.0)            # past outbound + handler
        # Distance at arrival was somewhere near 0.11 ly, so return
        # latency is bigger than outbound — but command should ack by yr 1.5.
        assert cmd.response_at_yr is not None
        # ACK return must come AFTER outbound arrival
        assert cmd.response_at_yr > cmd.arrives_at_yr
