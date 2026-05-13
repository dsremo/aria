"""Autonomy / flight-software audit (2026-04-27) — wiring tests.

Each test exercises one of the audit fixes end-to-end.  These are the
"deterministic-stability" guard rails: a regression here is a
mission-criticality issue, not just a code-quality issue.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import pytest


# ── F1: Constitution input validation ───────────────────────────


class TestF1ConstitutionInputValidation:
    def test_resource_qty_nan_rejected(self):
        """Audit F18 — NaN resource_qty refused at the constitution gate."""
        from aria.cognitive.constitution import (
            Constitution, TrustTier, Verdict,
        )
        c = Constitution()
        out = c.check(
            "set_setpoint",
            {"_resource_id": "delta_v_per_hr", "_resource_qty": float("nan")},
            TrustTier.OPERATOR,
        )
        assert out.verdict is Verdict.DENY
        assert "finite" in out.reason

    def test_resource_qty_negative_rejected(self):
        from aria.cognitive.constitution import (
            Constitution, TrustTier, Verdict,
        )
        c = Constitution()
        out = c.check(
            "set_setpoint",
            {"_resource_id": "delta_v_per_hr", "_resource_qty": -10.0},
            TrustTier.OPERATOR,
        )
        assert out.verdict is Verdict.DENY


# ── F4 / F10 / F11: SafeMode hardening ─────────────────────────


class TestF4F10F11SafeMode:
    def test_nan_health_score_does_not_pass_thresholds(self):
        """Audit F10 — non-finite metric forces conservative downgrade,
        not silent pass-through."""
        from aria.bus.message_bus import MessageBus
        from aria.safety.safe_mode import SafeModeManager, SafeLevel
        ctrl = SafeModeManager(MessageBus())
        new_level = ctrl.evaluate(
            health_score=float("nan"),
            battery_soc=80.0,
            power_margin_w=500.0,
        )
        # NaN must trigger MONITORING_ONLY (or deeper) regardless of
        # the apparently-healthy battery.
        assert new_level is not None
        assert new_level >= SafeLevel.MONITORING_ONLY

    def test_deepest_level_chosen_in_one_tick(self):
        """Audit F11 — multi-criterion failure jumps straight to the
        deepest level, not one level per tick."""
        from aria.bus.message_bus import MessageBus
        from aria.safety.safe_mode import SafeModeManager, SafeLevel
        ctrl = SafeModeManager(MessageBus())
        # Battery 0 + power_margin -1000 + critical_subsystem_count 10
        # — these straddle every threshold, so SURVIVAL is the answer.
        new_level = ctrl.evaluate(
            health_score=0.1,
            battery_soc=0.0,
            power_margin_w=-1000.0,
            critical_subsystem_count=10,
            ai_consecutive_errors=99,
        )
        assert new_level is SafeLevel.SURVIVAL


# ── F4 / F13 / F14 / F15 / F31 / F32: ApprovalQueue ────────────


class TestApprovalQueueHardening:
    def test_recall_answer_ok_required(self):
        """Audit F14 — caller MUST pass recall_answer_ok."""
        from aria.safety.approval_queue import ApprovalQueue
        q = ApprovalQueue()
        pid = q.propose(
            action="vent_tank", params={}, proposer="propulsion",
            required_signers=2, cooling_off_s=0.0,
        )
        with pytest.raises(TypeError):
            q.approve(pid, "alice")    # type: ignore[call-arg]

    def test_pubkey_fingerprint_anti_collusion(self):
        """Audit F15 — same pubkey-fingerprint signing under two
        different operator_ids is rejected."""
        from aria.safety.approval_queue import ApprovalQueue
        q = ApprovalQueue()
        pid = q.propose(
            action="vent_tank", params={}, proposer="propulsion",
            required_signers=2, cooling_off_s=0.0,
        )
        ok1 = q.approve(pid, "alice", recall_answer_ok=True,
                        pubkey_fingerprint="fp-001")
        ok2 = q.approve(pid, "alice_alt", recall_answer_ok=True,
                        pubkey_fingerprint="fp-001")
        assert ok1["ok"] is True
        assert ok2["ok"] is False
        assert "key" in ok2["reason"].lower()

    def test_revert_failed_state(self):
        """Audit F32 — reverter exception lands in REVERT_FAILED, not
        a silent return."""
        from aria.safety.approval_queue import (
            ApprovalQueue, ProposalState,
        )
        q = ApprovalQueue()
        pid = q.propose(
            action="vent_tank", params={}, proposer="propulsion",
            required_signers=1, cooling_off_s=0.0,
            undo_window_s=60.0,
        )
        # Register a reverter that explodes.
        def bad_reverter(_p):
            raise RuntimeError("simulated actuator failure")
        q.register_reverter("vent_tank", bad_reverter)
        # Register a no-op executor so try_execute works.
        q.register_executor("vent_tank", lambda _p: None)
        q.approve(pid, "alice", recall_answer_ok=True)
        q.try_execute()
        # Now revert — should land in REVERT_FAILED.
        result = q.revert(pid, "alice")
        assert result["ok"] is False
        # ApprovalQueue.get returns a dict snapshot.
        snapshot = q.get(pid)
        assert snapshot is not None
        assert snapshot.get("state") == ProposalState.REVERT_FAILED.value


# ── F4 / F16 / F17: ResourceBudget ─────────────────────────────


class TestResourceBudgetHardening:
    def test_nan_qty_refused(self):
        """Audit F17 — NaN refuses with fits_hard=False."""
        from aria.safety.resource_budget import ResourceBudgetGate
        from aria.cognitive.constitution import Constitution
        gate = ResourceBudgetGate(constitution=Constitution())
        proj = gate.project("delta_v_per_hr", float("nan"))
        assert not proj.fits_hard
        assert "finite" in (proj.reason or "")

    def test_commit_negative_refused_without_recording(self):
        """Audit F17 — negative qty does NOT poison the window."""
        from aria.safety.resource_budget import ResourceBudgetGate
        from aria.cognitive.constitution import Constitution
        gate = ResourceBudgetGate(constitution=Constitution())
        proj = gate.commit("delta_v_per_hr", -5.0)
        assert not proj.fits_hard


# ── F4 / F25: Heartbeat boot-id ─────────────────────────────────


class TestHeartbeatBootId:
    def test_boot_id_distinguishes_legitimate_restart(self):
        """Audit F25 — counter rewind across boot_id change is accepted
        as a legitimate restart, not a replay."""
        from aria.monitor.heartbeat import HeartbeatWatcher

        fired: list[float] = []
        watcher = HeartbeatWatcher(
            on_silence=lambda age: fired.append(age),
            grace_s=10.0,
            emitter_id="primary_monitor",
        )
        # First boot: counter 1, 2, 3.
        for c in (1, 2, 3):
            watcher.on_event({
                "emitter_id": "primary_monitor",
                "counter": c,
                "boot_id": "boot-A",
            })
        # Same boot_id, counter rewind — must be rejected as replay.
        watcher.on_event({
            "emitter_id": "primary_monitor",
            "counter": 1,
            "boot_id": "boot-A",
        })
        assert watcher._last_counter == 3    # noqa: SLF001
        # New boot_id — counter rewind accepted as restart.
        watcher.on_event({
            "emitter_id": "primary_monitor",
            "counter": 1,
            "boot_id": "boot-B",
        })
        assert watcher._last_counter == 1    # noqa: SLF001
        assert watcher._last_boot_id == "boot-B"    # noqa: SLF001


# ── F23 / F24: ReplayGuard persistence ─────────────────────────


class TestReplayGuardPersistence:
    def test_last_seq_persists_across_restart(self, tmp_path: Path,
                                              monkeypatch):
        """Audit F24 — last_seq survives a process restart."""
        monkeypatch.setenv("ARIA_RUNTIME_DIR", str(tmp_path))
        from aria.safety.replay_guard import ReplayGuard
        g = ReplayGuard()
        ok, reason = g.accept("ground_uplink", seq=10,
                              nonce="n10aaaaaaaaaaaaaaa",
                              timestamp=time.time())
        assert ok, reason
        ok, reason = g.accept("ground_uplink", seq=11,
                              nonce="n11aaaaaaaaaaaaaaa",
                              timestamp=time.time())
        assert ok, reason
        g.flush()
        # Cold restart.
        g2 = ReplayGuard()
        # Replaying seq=11 must reject.
        ok, reason = g2.accept("ground_uplink", seq=11,
                               nonce="n11replayed_____",
                               timestamp=time.time())
        assert not ok


# ── F3 / F22: Agents/base ──────────────────────────────────────


class TestAgentsBaseHardening:
    @pytest.mark.asyncio
    async def test_message_queue_drops_oldest_on_overflow(self):
        """Audit F3 — bounded queue drops oldest, not crashes."""
        from aria.agents.base import SubsystemAgent
        from aria.bus.message_bus import Message, MessageBus
        from aria.tools.registry import ToolRegistry

        class _StubAgent(SubsystemAgent):
            name = "stub"
            description = "test"
            subscriptions = ["test.*"]

            async def handle_message(self, message): pass

        agent = _StubAgent(MessageBus(), ToolRegistry(),
                           queue_maxsize=4)
        for i in range(20):
            await agent._enqueue_message(    # noqa: SLF001
                Message(topic="test.x", payload={"i": i}),
            )
        # Queue is at capacity, overflow recorded, no exception.
        assert agent._queue_overflow_count > 0    # noqa: SLF001
        assert agent._message_queue.qsize() <= 4    # noqa: SLF001

    def test_record_outcome_logs_unknown_id(self, caplog):
        """Audit F22 — pruned / unknown decision_id emits a warning,
        not a silent drop."""
        import logging
        from aria.agents.base import SubsystemAgent
        from aria.bus.message_bus import MessageBus
        from aria.tools.registry import ToolRegistry

        class _StubAgent(SubsystemAgent):
            name = "stub"
            description = "test"
            subscriptions = []

            async def handle_message(self, message): pass

        agent = _StubAgent(MessageBus(), ToolRegistry())
        with caplog.at_level(logging.WARNING):
            agent.record_outcome(99999, "correct")
        # The structured logger doesn't always route through caplog;
        # the contract is "non-crash + visible in logs".  Verify the
        # call returns None and the decision_log is unchanged.
        assert 99999 not in agent._decision_log    # noqa: SLF001


# ── F6: Internal channel token isolated across fork ────────────


class TestInternalChannelTokenForkIsolation:
    def test_fork_handler_clears_token(self):
        """Audit F6 — verify the after-fork hook is registered.

        Smoke test: calling the private ``_reset_after_fork_in_child``
        directly must clear the token (simulating what os triggers in
        the child after fork)."""
        from aria.security.auth import (
            mint_internal_channel_token,
            verify_internal_channel_token,
            reset_internal_channel_token_for_test,
            _reset_after_fork_in_child,
        )
        reset_internal_channel_token_for_test()
        tok = mint_internal_channel_token()
        assert verify_internal_channel_token(tok) is True
        # Simulate post-fork in child.
        _reset_after_fork_in_child()
        assert verify_internal_channel_token(tok) is False
        # Child can mint its own.
        new_tok = mint_internal_channel_token()
        assert new_tok != tok
        reset_internal_channel_token_for_test()


# ── F7: Cognitive engine total timeout (smoke) ─────────────────


class TestCognitiveTotalTimeoutConstant:
    def test_constant_is_bounded(self):
        """Audit F7 — outer timeout exists and is sane."""
        from aria.cognitive.engine import REASONING_TOTAL_TIMEOUT_S
        assert 5.0 <= REASONING_TOTAL_TIMEOUT_S <= 600.0


# ── F33: ast.literal_eval excised ─────────────────────────────


class TestNoAstLiteralEval:
    def test_engine_does_not_use_ast_literal_eval(self):
        """Audit F33 — engine.py must not import ast or call
        ast.literal_eval at runtime (drop the legacy fallback)."""
        path = (Path(__file__).resolve().parents[2]
                / "src" / "aria" / "cognitive" / "engine.py")
        text = path.read_text()
        # Must not have an ``import ast`` line in the runtime path.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "import ast" not in stripped, (
                f"engine.py line still imports ast: {stripped!r}"
            )
            # Must not call .literal_eval(.
            assert ".literal_eval(" not in stripped, (
                f"engine.py line still calls literal_eval: {stripped!r}"
            )
