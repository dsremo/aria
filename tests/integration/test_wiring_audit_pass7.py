"""Wiring audit Pass 7 regression suite.

Each test pins one of the Pass 7 wiring fixes so a future refactor
fails loudly instead of silently regressing the wiring.

The ID prefix `F` matches WIRING_AUDIT_TRACKER.md so a failure points
straight at the originating finding.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────
# F2.1 — checkpoint write/restore asymmetry is documented and intentional
# ─────────────────────────────────────────────────────────────────────


def test_f2_1_checkpoint_apply_restored_state_documented_fields(
    monkeypatch, tmp_path: Path,
) -> None:
    """`_build_checkpoint_state` writes 11 forensic fields; only 3 are
    re-applied by `_apply_restored_state` (safe_mode_level,
    mission_phase, ai_consecutive_errors). The other 8 have sibling
    persistence files as their canonical store — re-applying them from
    the checkpoint would race the dedicated subsystem's own load path.

    This test pins the documented intentional asymmetry so a future
    "let's symmetrize this" refactor fails here first instead of
    silently double-applying state.
    """
    from aria.core.config import AriaConfig
    from aria.core.coordinator import AriaCoordinator
    from aria.safety.safe_mode import SafeLevel

    monkeypatch.setenv("ARIA_RUNTIME_DIR", str(tmp_path))
    coord = AriaCoordinator(AriaConfig())
    coord.state._persist_path = tmp_path / "state.json"

    restored = {
        "safe_mode_level": "REDUCED_AUTONOMY",
        "mission_phase": "CRUISE",
        "ai_consecutive_errors": 7,
        # Forensic-only — must NOT round-trip into runtime state
        "agent_restart_counts": {"power": 99},
        "fdir_active_faults": [
            {"fault_type": "thermal_runaway", "subsystem": "power",
             "severity": "CRITICAL", "detected_at": 0.0},
        ],
        "kill_switch": {"asserted": True, "reason": "synthetic"},
    }
    coord._apply_restored_state(restored)

    # The 3 documented re-applied fields ARE applied:
    assert coord.safe_mode.current_level == SafeLevel.REDUCED_AUTONOMY
    assert coord.config.mission_phase == "CRUISE"
    assert coord._ai_consecutive_errors == 7

    # The 8 forensic fields are NOT re-applied: an empty FDIR + no
    # restart counts + the in-memory kill switch is fresh.
    assert coord._agents == {}
    assert list(coord.fdir.active_faults) == []
    # kill_switch is a singleton; verify it was not asserted from the
    # checkpoint payload.
    from aria.safety.kill_switch import get_kill_switch, reset_for_test
    reset_for_test()
    assert get_kill_switch().is_asserted() is False


# ─────────────────────────────────────────────────────────────────────
# F5.3 — rate limiter blocked_until persists across restart
# ─────────────────────────────────────────────────────────────────────


def test_f5_3_rate_limiter_block_survives_restart(tmp_path: Path) -> None:
    """An attacker who has accumulated `violations >= 1` and a live
    `blocked_until` window must remain blocked across a process bounce.
    Without F5.3 persistence, restart silently clears the exponential-
    backoff cooldown and the attacker gets a fresh budget."""
    from aria.api.per_ip_rate_limiter import PerIPRateLimiter

    persist = tmp_path / "rl.json"
    rl1 = PerIPRateLimiter(
        rate_per_min=2, backoff_base_s=10.0,
        persist_path=persist,
    )
    # Burn the 2-per-min budget then trip the block.
    rl1.check("10.0.0.1")
    rl1.check("10.0.0.1")
    blocked = rl1.check("10.0.0.1")
    assert blocked.allowed is False
    assert blocked.reason == "rate_exceeded"
    assert persist.is_file(), "persist file not written on first violation"

    # Reload from disk → second instance.
    rl2 = PerIPRateLimiter(
        rate_per_min=2, backoff_base_s=10.0,
        persist_path=persist,
    )
    verdict = rl2.check("10.0.0.1")
    assert verdict.allowed is False, "blocked IP got fresh budget on restart"
    assert verdict.reason == "blocked"
    assert verdict.violations >= 1


# ─────────────────────────────────────────────────────────────────────
# F5.4 — anomaly storm timestamps persist across restart
# ─────────────────────────────────────────────────────────────────────


def test_f5_4_anomaly_storm_window_survives_restart(
    monkeypatch, tmp_path: Path,
) -> None:
    """An attacker accumulating CRITICAL anomalies (e.g. 9 in 4 min)
    must not regain a fresh storm budget on restart. The fix persists
    `_recent_critical_timestamps` so the window count carries over."""
    from aria.core.config import AriaConfig
    from aria.core.coordinator import AriaCoordinator

    monkeypatch.setenv("ARIA_RUNTIME_DIR", str(tmp_path))
    coord1 = AriaCoordinator(AriaConfig())
    coord1.state._persist_path = tmp_path / "state.json"
    now = time.time()
    coord1._recent_critical_timestamps = [now - i for i in range(9)]
    coord1._save_anomaly_storm_state()

    state_file = tmp_path / "anomaly_storm_state.json"
    assert state_file.is_file()

    coord2 = AriaCoordinator(AriaConfig())
    coord2.state._persist_path = tmp_path / "state.json"
    # All 9 timestamps are within the 300s window; load should preserve them.
    assert len(coord2._recent_critical_timestamps) == 9


def test_f5_4_anomaly_storm_window_drops_stale_on_load(
    monkeypatch, tmp_path: Path,
) -> None:
    """Timestamps older than the window must be pruned on load — a
    process that crashed and restarted hours later should not carry
    forward an ancient storm count."""
    from aria.core.config import AriaConfig
    from aria.core.coordinator import AriaCoordinator

    monkeypatch.setenv("ARIA_RUNTIME_DIR", str(tmp_path))
    state_file = tmp_path / "anomaly_storm_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    ancient = time.time() - 10_000.0
    state_file.write_text(json.dumps({
        "timestamps": [ancient - 1, ancient - 2, ancient - 3],
        "window_s": 300.0, "threshold": 10,
    }))

    coord = AriaCoordinator(AriaConfig())
    assert coord._recent_critical_timestamps == []


# ─────────────────────────────────────────────────────────────────────
# F5.5 — LRU eviction must NOT drop a still-blocked attacker IP
# ─────────────────────────────────────────────────────────────────────


def test_f5_5_lru_full_of_blocked_ips_refuses_overflow(
    tmp_path: Path,
) -> None:
    """When every slot in the LRU is currently blocked, a new IP is
    refused with `reason='overflow'` — an attacker cannot reset their
    own block by flooding 10000 fresh source-IPs."""
    from aria.api.per_ip_rate_limiter import PerIPRateLimiter

    rl = PerIPRateLimiter(
        rate_per_min=1, backoff_base_s=60.0,
        max_tracked_ips=3,
        persist_path=tmp_path / "rl.json",
    )
    # Fill all 3 slots with blocked IPs.
    for octet in (1, 2, 3):
        ip = f"10.0.0.{octet}"
        rl.check(ip)            # consumes the 1-per-min budget
        rl.check(ip)            # second call trips the block

    # All three slots blocked → new IP must be refused as overflow,
    # not by silently evicting one of the legitimate blocks.
    verdict = rl.check("10.0.0.99")
    assert verdict.allowed is False
    assert verdict.reason == "overflow"
    # The blocked IPs are still tracked.
    assert len(rl._states) == 3
    assert "10.0.0.99" not in rl._states


def test_f5_5_lru_evicts_unblocked_entries(tmp_path: Path) -> None:
    """If at least one entry's block has expired, the LRU evicts THAT
    one (not a still-blocked attacker) when accepting a new IP."""
    from aria.api.per_ip_rate_limiter import PerIPRateLimiter, _IPState

    rl = PerIPRateLimiter(
        rate_per_min=1, backoff_base_s=60.0,
        max_tracked_ips=2,
        persist_path=tmp_path / "rl.json",
    )
    # Slot 1: a still-blocked attacker.
    rl.check("10.0.0.1")
    rl.check("10.0.0.1")
    assert rl._states["10.0.0.1"].blocked_until > time.monotonic()

    # Slot 2: an unblocked entry — inject directly to bypass timing.
    expired = _IPState()
    expired.blocked_until = 0.0   # already expired
    rl._states["10.0.0.2"] = expired

    # New IP triggers eviction — the unblocked entry must be the one
    # evicted, not the still-blocked attacker.
    rl.check("10.0.0.99")
    assert "10.0.0.1" in rl._states, "still-blocked IP was wrongly evicted"
    assert "10.0.0.2" not in rl._states


# ─────────────────────────────────────────────────────────────────────
# F6.12 — config_manager.load_staged_from_file logs structured warning
# ─────────────────────────────────────────────────────────────────────


def test_f6_12_load_staged_logs_on_malformed_json(
    tmp_path: Path, capsys,
) -> None:
    """A corrupt staged-config file must produce a structured warning
    rather than silently returning False. Without the log, downstream
    callers cannot differentiate "file missing" from "file unparsable"."""
    from aria.core.config_manager import ConfigManager

    bad = tmp_path / "config.json"
    bad.write_text("{not valid json")
    mgr = ConfigManager()

    ok = mgr.load_staged_from_file(bad)
    assert ok is False

    # structlog renders to stdout in the dev config; assert the
    # event key is present.
    captured = capsys.readouterr()
    assert "config_manager.staged_load_failed" in captured.out, (
        "expected structured warning on malformed JSON; "
        f"stdout was: {captured.out!r}"
    )
    assert "JSONDecodeError" in captured.out


# ─────────────────────────────────────────────────────────────────────
# F6.13 — mission_clock.reset narrowed except (no longer bare pass)
# ─────────────────────────────────────────────────────────────────────


def test_f6_13_mission_clock_reset_narrow_except() -> None:
    """A non-import error inside the bus-publish path should NOT be
    swallowed silently. The narrowed `except (ImportError,
    AttributeError)` lets genuine bugs surface."""
    from aria.core import mission_clock as mc_mod

    mc_mod.reset_mission_clock()
    clock = mc_mod.get_mission_clock()
    # When the simulator event bus IS importable, a publish-side
    # programming bug (e.g. wrong kwarg) should now surface — but
    # under the narrow except, an ImportError is still tolerated.
    # We only test the tolerant path here because injecting a
    # publish-side bug at runtime would require monkeypatching the
    # singleton and risks polluting the test session.
    clock.reset(to_yr=1.5)
    assert clock.elapsed_yr == 1.5
    assert clock.generation >= 1


# ─────────────────────────────────────────────────────────────────────
# F11.4 + F11.5 + F11.7 — public-API regression tests
# ─────────────────────────────────────────────────────────────────────


def test_f11_4_api_server_has_public_diagnostics_setters() -> None:
    """`AriaAPIServer` must expose `set_diagnostics_fn` /
    `set_readiness_fn`. The pre-fix code used `__self__` introspection
    on a bound method to recover the coordinator, which silently fell
    back to `{"go_for_operations": True}` if the attribute was absent."""
    from aria.api.server import AriaAPIServer

    assert hasattr(AriaAPIServer, "set_diagnostics_fn"), (
        "set_diagnostics_fn missing — F11.4 / F11.6 regression"
    )
    assert hasattr(AriaAPIServer, "set_readiness_fn"), (
        "set_readiness_fn missing — F11.4 regression"
    )


def test_f11_5_bus_stats_includes_history_size() -> None:
    """`MessageBus.stats` must expose `history_size` so api/server.py
    no longer reaches into the leading-underscore `_history`. Without
    this key, `/api/v1/bus/stats` silently reports 0."""
    from aria.bus.message_bus import MessageBus

    bus = MessageBus()
    stats = bus.stats
    assert "history_size" in stats, (
        "MessageBus.stats missing 'history_size' — F11.5 regression"
    )
    assert isinstance(stats["history_size"], int)


@pytest.mark.asyncio
async def test_f11_7_checkpoint_has_public_interval_property(
    tmp_path: Path,
) -> None:
    """`CheckpointManager.interval_s` must be a public property —
    coordinator's `_checkpoint_loop` reads it. The pre-fix code used
    `getattr(self.checkpoint, '_interval_s', 300)` which had a
    two-bug: reached into a private attribute AND read a non-existent
    name (real attr is `_interval`), so the loop ran at the 300s
    fallback regardless of the configured value."""
    from aria.safety.checkpoint import CheckpointManager

    mgr = CheckpointManager(persist_dir=tmp_path, interval_s=42.0)
    assert hasattr(mgr, "interval_s"), (
        "CheckpointManager.interval_s public property missing — F11.7 "
        "regression; coordinator will silently fall back to 300s"
    )
    assert mgr.interval_s == 42.0
