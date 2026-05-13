"""Recovery audit (R-1 .. R-25) regression suite.

Each test pins one of the 25 recovery-audit findings.  When a future
refactor regresses the wiring, the test fails loudly instead of the
behaviour silently breaking.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────
# R-1 + R-2: Ground-silence handler
# ─────────────────────────────────────────────────────────────────────


def test_r1_force_level_exists_on_safe_mode_manager() -> None:
    """Recovery audit R-1: SafeModeManager must expose
    ``force_level`` so the ground-deadman watchdog (running in a
    thread) can demote synchronously."""
    from aria.safety.safe_mode import SafeModeManager
    assert hasattr(SafeModeManager, "force_level"), (
        "SafeModeManager.force_level missing — ground-deadman demote "
        "path is broken; see audit finding R-1."
    )


def test_r1_singleton_register_and_retrieve() -> None:
    """Recovery audit R-1: get_safe_mode_singleton round-trip."""
    from aria.bus.message_bus import MessageBus
    from aria.safety.safe_mode import (
        SafeModeManager, get_safe_mode_singleton, set_safe_mode_singleton,
    )
    bus = MessageBus()
    sm = SafeModeManager(bus)
    set_safe_mode_singleton(sm)
    assert get_safe_mode_singleton() is sm


def test_r1_force_level_actually_demotes() -> None:
    """Recovery audit R-1: force_level must mutate current_level
    synchronously (so off-loop callers see the change immediately)."""
    from aria.bus.message_bus import MessageBus
    from aria.safety.safe_mode import SafeModeManager, SafeLevel
    bus = MessageBus()
    sm = SafeModeManager(bus)
    sm.force_level(SafeLevel.MONITORING_ONLY, reason="test")
    assert sm.current_level == SafeLevel.MONITORING_ONLY


# ─────────────────────────────────────────────────────────────────────
# R-5: FDIR recovery library publishes correctly
# ─────────────────────────────────────────────────────────────────────


def test_r5_dispatcher_supports_message_bus_signature() -> None:
    """Recovery audit R-5: build_standard_library accepts an asyncio
    loop kwarg + the dispatcher distinguishes MessageBus from
    EventBus."""
    from aria.safety.fdir_recovery_plans import build_standard_library
    import inspect
    sig = inspect.signature(build_standard_library)
    assert "asyncio_loop" in sig.parameters, (
        "build_standard_library must accept asyncio_loop for "
        "thread-safe publish; see R-5."
    )


def test_r5_critical_steps_marked_critical() -> None:
    """Recovery audit R-5: at least one safety-critical step in each
    plan must be marked critical=True so a wiring failure aborts the
    plan rather than silently continuing."""
    from aria.safety.fdir_recovery_plans import build_standard_library

    class _FakeBus:
        def __init__(self) -> None:
            self.calls: list = []

        def publish(self, *a, **kw) -> None:    # EventBus shape
            self.calls.append((a, kw))

    bus = _FakeBus()
    lib = build_standard_library(event_bus=bus)
    plan = lib.find_matching_plan("undervoltage", "warning", "power")
    assert plan is not None
    critical_steps = [s for s in plan.steps if s.critical]
    assert critical_steps, (
        "power_undervoltage_recovery has no critical=True step — a "
        "TypeError in dispatch would have silently continued.  See R-5."
    )


# ─────────────────────────────────────────────────────────────────────
# R-7: emergency_safe_mode tool actually demotes
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_r7_emergency_safe_mode_tool_actually_demotes() -> None:
    """Recovery audit R-7: the LLM-callable tool must publish a
    request_safe_mode (or call force_level) so the SafeModeManager
    actually transitions."""
    from aria.bus.message_bus import MessageBus
    from aria.integrations.control_tools import EmergencySafeMode
    from aria.safety.safe_mode import (
        SafeModeManager, SafeLevel, set_safe_mode_singleton,
    )

    bus = MessageBus()
    sm = SafeModeManager(bus)
    set_safe_mode_singleton(sm)
    tool = EmergencySafeMode()
    result = await tool.execute({
        "level": 3, "reason": "test", "auto_recovery": False,
    })
    assert result.success
    assert sm.current_level == SafeLevel.MONITORING_ONLY


# ─────────────────────────────────────────────────────────────────────
# R-13: Boot-counter / crash-loop guard
# ─────────────────────────────────────────────────────────────────────


def test_r13_begin_boot_increments_counter(tmp_path: Path) -> None:
    """Recovery audit R-13: each begin_boot() call increments the
    persisted counter."""
    from aria.safety.boot_counter import begin_boot
    d1 = begin_boot(state_dir=tmp_path)
    d2 = begin_boot(state_dir=tmp_path)
    assert d2.attempt_count == d1.attempt_count + 1


def test_r13_crash_loop_triggers_rescue_mode(tmp_path: Path) -> None:
    """Recovery audit R-13: ≥ CRASH_LOOP_THRESHOLD recent failures
    flips rescue_mode."""
    from aria.safety.boot_counter import (
        begin_boot, CRASH_LOOP_THRESHOLD, _append_history,
    )
    history_path = tmp_path / "boot.history"
    now = time.time()
    for i in range(CRASH_LOOP_THRESHOLD):
        _append_history(history_path, {
            "ts": now - i, "attempt": i, "outcome": "started",
        })
    decision = begin_boot(state_dir=tmp_path)
    assert decision.rescue_mode
    assert "crash_loop_detected" in decision.reason


# ─────────────────────────────────────────────────────────────────────
# R-19: Rescue manifest path
# ─────────────────────────────────────────────────────────────────────


def test_r19_rescue_manifest_helpers_exist() -> None:
    """Recovery audit R-19: rescue manifest API is wired."""
    from aria.boot.verify import (
        _default_rescue_manifest_path,
        is_rescue_mode_active,
    )
    # Helpers exist and don't raise on dev tree (no manifest present).
    _default_rescue_manifest_path()
    is_rescue_mode_active()


# ─────────────────────────────────────────────────────────────────────
# R-3, R-4, R-9, R-10, R-11, R-21: Coordinator wiring
# ─────────────────────────────────────────────────────────────────────


def test_r3_evaluate_accepts_ai_consecutive_errors() -> None:
    """Recovery audit R-3: the evaluator parameter exists AND a value
    of 5 demotes to REDUCED_AUTONOMY."""
    from aria.bus.message_bus import MessageBus
    from aria.safety.safe_mode import SafeModeManager, SafeLevel
    sm = SafeModeManager(MessageBus())
    new_level = sm.evaluate(
        health_score=100.0, ai_consecutive_errors=5,
    )
    assert new_level == SafeLevel.REDUCED_AUTONOMY


def test_r21_evaluate_accepts_active_fdir_count() -> None:
    """Recovery audit R-21: active_fdir_count parameter exists AND a
    value of 6 demotes to MONITORING_ONLY."""
    from aria.bus.message_bus import MessageBus
    from aria.safety.safe_mode import SafeModeManager, SafeLevel
    sm = SafeModeManager(MessageBus())
    new_level = sm.evaluate(
        health_score=100.0, active_fdir_count=6,
    )
    assert new_level == SafeLevel.MONITORING_ONLY


# ─────────────────────────────────────────────────────────────────────
# R-15: Kill switch persistence
# ─────────────────────────────────────────────────────────────────────


def test_r15_kill_switch_persists_assertion(tmp_path: Path, monkeypatch) -> None:
    """Recovery audit R-15: assert → simulate process bounce → state
    survives.

    A real process restart preserves the state file but throws away
    the singleton.  ``reset_for_test()`` is the test-only helper that
    wipes both, so we simulate the bounce manually: clear the
    singleton via direct module-state mutation but keep the file.
    """
    monkeypatch.setenv("ARIA_RUNTIME_DIR", str(tmp_path))
    from aria.safety import kill_switch as ks_mod
    ks_mod.reset_for_test()
    ks = ks_mod.get_kill_switch()
    ks.assert_kill(source="test", reason="r15-test")
    # Simulate process bounce — drop the singleton but leave the
    # persisted file intact.
    with ks_mod._KILL_LOCK:
        ks_mod._KILL = None
    ks2 = ks_mod.get_kill_switch()
    assert ks2.is_asserted()
    assert "r15-test" in ks2.reason
    # Cleanup so subsequent tests start clean.
    ks_mod.reset_for_test()


# ─────────────────────────────────────────────────────────────────────
# R-23: Dead-component registry
# ─────────────────────────────────────────────────────────────────────


def test_r23_dead_component_round_trip(tmp_path: Path, monkeypatch) -> None:
    """Recovery audit R-23: mark dead → persisted → loaded fresh."""
    monkeypatch.setenv("ARIA_RUNTIME_DIR", str(tmp_path))
    from aria.safety import dead_component_registry as reg_mod
    reg_mod.reset_for_test()
    reg = reg_mod.get_dead_component_registry()
    reg.mark_dead("thruster_a", "stuck-open after 3 retries")
    assert reg.is_dead("thruster_a")
    reg_mod.reset_for_test()
    reg2 = reg_mod.get_dead_component_registry()
    assert reg2.is_dead("thruster_a")


# ─────────────────────────────────────────────────────────────────────
# R-25: SafetyReplay public set_on_drift
# ─────────────────────────────────────────────────────────────────────


def test_r25_set_on_drift_is_public() -> None:
    """Recovery audit R-25: the public hook replaces the private
    _on_drift attribute touch."""
    from aria.safety.safety_replay import SafetyReplay
    sr = SafetyReplay()
    called = {"v": False}

    def cb(report):
        called["v"] = True

    sr.set_on_drift(cb)
    assert sr._on_drift is cb    # internal verification only


# ─────────────────────────────────────────────────────────────────────
# Wiring audit Pass 7 — silent-drift-alarm triad (F6.14 + F10.6 + F12.1)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drift_alarm_publishes_from_daemon_thread(
    monkeypatch, tmp_path: Path,
) -> None:
    """The 6-hourly SafetyReplay drift alarm must reach subscribers
    even though SafetyReplay invokes ``_on_drift`` from its daemon
    ``_run_loop`` thread.

    The coordinator's ``_on_drift`` closure had three compounding
    bugs that silently dropped this alarm for the entire R-25 era:

      * F10.6 — wrong publish signature (EventBus shape vs Message)
      * F12.1 — ``asyncio.create_task`` from a thread with no loop
      * F6.14 — broad ``except Exception`` swallowed both errors

    This test pins the fix: bus.publish must be dispatched via
    ``run_coroutine_threadsafe`` against the captured loop, the
    payload must be a ``Message`` instance, and a subscriber on
    ``aria.emergency.safety_replay_drift`` must receive it.
    """
    import threading

    from aria.bus.message_bus import Message
    from aria.core.config import AriaConfig
    from aria.core.coordinator import AriaCoordinator
    from aria.safety import safety_replay as sr_mod

    # Isolate persistence so this test does not pollute shared state.
    monkeypatch.setenv("ARIA_RUNTIME_DIR", str(tmp_path))
    sr_mod.reset_for_test()

    cfg = AriaConfig()
    coord = AriaCoordinator(cfg)
    coord.state._persist_path = tmp_path / "state.json"
    coord.checkpoint._persist_dir = tmp_path / "checkpoints"

    received: list[Message] = []

    async def _capture(message: Message) -> None:
        received.append(message)

    await coord.start()
    try:
        coord.bus.subscribe(
            "aria.emergency.safety_replay_drift", _capture,
        )

        sr = sr_mod.get_safety_replay()
        installed = sr._on_drift
        assert installed is not None, (
            "coordinator.start() did not install the drift callback"
        )

        # Build a degraded report: fail_pct=20% trips drift_alarm
        # (threshold is DRIFT_FAIL_PCT=1.0%).
        report = sr_mod.ReplayReport(
            ts=time.time(), n_total=10, n_pass=8, n_fail=2,
            failures=tuple(
                {"scenario_id": f"f-{idx}", "action": "x",
                 "expected": "ALLOW", "got": "DENY", "rule_id": "r"}
                for idx in range(2)
            ),
        )
        assert report.drift_alarm is True

        # Mirror SafetyReplay._run_loop: invoke the callback from a
        # FRESH daemon thread that owns no asyncio loop. This is the
        # exact context the F12.1 bug fired in.
        def _fire() -> None:
            installed(report)

        worker = threading.Thread(target=_fire, daemon=True)
        worker.start()
        worker.join(timeout=2.0)
        assert not worker.is_alive(), "drift callback wedged"

        # Allow run_coroutine_threadsafe → bus.publish → subscribers.
        deadline = asyncio.get_event_loop().time() + 2.0
        while asyncio.get_event_loop().time() < deadline and not received:
            await asyncio.sleep(0.02)

        assert received, (
            "drift alarm did not reach subscribers — F10.6/F12.1/F6.14 "
            "regression: check coordinator._on_drift uses Message(...) "
            "and run_coroutine_threadsafe(_aria_loop)"
        )
        msg = received[0]
        assert msg.topic == "aria.emergency.safety_replay_drift"
        assert msg.payload["fail_pct"] == pytest.approx(20.0)
        assert len(msg.payload["failures"]) == 2
    finally:
        await coord.stop()
        sr_mod.reset_for_test()


# ─────────────────────────────────────────────────────────────────────
# R-12 + R-14: Atomic checkpoint write + verified backup restore
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_r12_atomic_checkpoint_write(tmp_path: Path) -> None:
    """Recovery audit R-12: primary + backup are independent files
    and both verifiable."""
    from aria.safety.checkpoint import CheckpointManager
    mgr = CheckpointManager(persist_dir=tmp_path, interval_s=3600)
    state = {"a": 1, "b": "two"}
    await mgr.start(state_provider=lambda: state)
    cp = await mgr.save_now()
    await mgr.stop()
    primary = tmp_path / f"checkpoint_{cp.checkpoint_id:06d}.json"
    backup = tmp_path / f"checkpoint_{cp.checkpoint_id:06d}.json.bak"
    assert primary.is_file() and backup.is_file()
    p = json.loads(primary.read_text())
    b = json.loads(backup.read_text())
    assert p["state"] == state == b["state"]
    assert p["checksum"] == b["checksum"]


# ─────────────────────────────────────────────────────────────────────
# R-6: Last-gasp installer
# ─────────────────────────────────────────────────────────────────────


def test_r6_last_gasp_installer_runs() -> None:
    """Recovery audit R-6: install() returns True on the dev tree."""
    from aria.safety.last_gasp import install
    assert install() is True


# ─────────────────────────────────────────────────────────────────────
# R-16: FDIR fault history persistence
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_r16_fdir_history_persisted_on_resolve(tmp_path: Path, monkeypatch) -> None:
    """Recovery audit R-16: resolve_fault appends a JSONL record."""
    monkeypatch.setenv("ARIA_RUNTIME_DIR", str(tmp_path))
    from aria.bus.message_bus import MessageBus
    from aria.safety.fdir import FDIRManager, FaultRecord, FDIRLevel
    bus = MessageBus()
    await bus.start()
    mgr = FDIRManager(bus)
    fault = FaultRecord(
        fault_id="FDIR-TEST-1",
        fault_type="TEST_FAULT",
        subsystem="test",
        fdir_level=FDIRLevel.SYSTEM,
        severity="WARNING",
        description="r16-test",
    )
    mgr._active_faults["TEST_FAULT"] = [fault]
    await mgr.resolve_fault("TEST_FAULT", recovery_method="test")
    history_file = tmp_path / "fdir_history.jsonl"
    assert history_file.is_file()
    line = history_file.read_text().strip()
    record = json.loads(line)
    assert record["fault_id"] == "FDIR-TEST-1"
    assert record["recovery_method"] == "test"
    await bus.stop()
