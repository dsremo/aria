"""Wiring tests for the autonomy-audit operator follow-up items.

Covers:
1. Sealed constitution publishes ``allowed_actions`` and unmapped
   actions DENY at the constitution gate.
2. ``aria.main`` graceful shutdown flushes both ``SessionStore``
   counters and ``ReplayGuard`` last_seq.
3. ``aria.security.worker_init.boot_worker`` mints a fresh
   internal-channel token per worker process.
4. ``aria.safety.deadman_supervisor`` detects a stalled
   ``DeadmanTimer`` and fires ``on_stall``.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest


# ── 1. Sealed constitution publishes allowed_actions ───────────


class TestSealedConstitutionAllowedActions:
    def test_sealed_file_includes_allowed_actions(self):
        """The shipped sealed constitution must carry the allow-list
        so production deployments are default-DENY for unmapped actions."""
        import json
        sealed_dir = (Path(__file__).resolve().parents[2]
                      / "data" / "sealed")
        path = sealed_dir / "constitution.v1.json"
        d = json.loads(path.read_text())
        assert "allowed_actions" in d, (
            "sealed constitution must publish allowed_actions; "
            "see autonomy audit F1"
        )
        actions = {entry["action"] for entry in d["allowed_actions"]}
        # The 9 agent-driven actions must all be on the allow-list.
        for required in (
            "attitude_hold", "boost_scrubber", "pressurize_cabin",
            "safe_mode", "set_setpoint", "shed_load", "switch_antenna",
            "monitor", "alert_crew",
        ):
            assert required in actions, (
                f"expected allowed_action {required!r} not in "
                f"sealed constitution"
            )

    def test_constitution_runtime_denies_unmapped(self):
        from aria.cognitive import sealed_prompt as _sp
        from aria.cognitive.constitution import (
            get_constitution, Verdict, reset_for_test as _reset_c,
        )
        _sp.reset_for_test()
        _reset_c()
        out = get_constitution().check("totally_unlisted_action_xyz")
        assert out.verdict is Verdict.DENY
        assert out.rule_id == "default_deny"

    def test_constitution_runtime_allows_listed(self):
        from aria.cognitive import sealed_prompt as _sp
        from aria.cognitive.constitution import (
            get_constitution, Verdict, reset_for_test as _reset_c,
        )
        _sp.reset_for_test()
        _reset_c()
        for action in ("set_setpoint", "shed_load", "switch_antenna"):
            out = get_constitution().check(action)
            assert out.verdict is Verdict.ALLOW, (
                f"action {action!r} should ALLOW under the published "
                f"allow-list, got {out.verdict}"
            )


# ── 2. aria.main shutdown flush ────────────────────────────────


class TestMainShutdownFlushIntegration:
    def test_main_module_calls_flush_counters_and_replay_flush(self):
        """Statically verify the shutdown path imports the helpers."""
        path = (Path(__file__).resolve().parents[2]
                / "src" / "aria" / "main.py")
        text = path.read_text()
        assert "get_session_store().flush_counters()" in text, (
            "aria.main shutdown path must flush session counters"
        )
        assert "get_replay_guard().flush()" in text, (
            "aria.main shutdown path must flush replay guard"
        )


# ── 3. worker_init.boot_worker ────────────────────────────────


class TestWorkerInitBootWorker:
    def test_boot_worker_mints_fresh_token(self):
        """Each worker mint produces a token distinct from any
        pre-existing parent token; the call is idempotent within a
        single worker thanks to the test reset."""
        from aria.security.auth import (
            mint_internal_channel_token,
            verify_internal_channel_token,
            reset_internal_channel_token_for_test,
        )
        from aria.security.worker_init import boot_worker

        reset_internal_channel_token_for_test()
        # Simulate the parent.
        parent_tok = mint_internal_channel_token()
        # Simulate the post-fork hook.
        from aria.security.auth import _reset_after_fork_in_child
        _reset_after_fork_in_child()
        # Worker boots and mints its own.
        worker_tok = boot_worker(reseed_heartbeat=False)
        assert worker_tok is not None
        assert worker_tok != parent_tok
        assert verify_internal_channel_token(worker_tok)
        # Parent token no longer accepted.
        assert not verify_internal_channel_token(parent_tok)
        reset_internal_channel_token_for_test()

    def test_gunicorn_post_fork_callable(self):
        """Smoke: the gunicorn hook signature is import-safe."""
        from aria.security.worker_init import gunicorn_post_fork
        # Stand up dummy server / worker objects; gunicorn passes the
        # real ones at runtime.
        class _Stub:
            age = 0
        from aria.security.auth import reset_internal_channel_token_for_test
        reset_internal_channel_token_for_test()
        gunicorn_post_fork(_Stub(), _Stub())
        reset_internal_channel_token_for_test()


# ── 4. deadman_supervisor stall detection ─────────────────────


class TestDeadmanSupervisor:
    def test_detects_stalled_proof_of_life(self):
        """When the proof-of-life counter doesn't advance, on_stall fires."""
        from aria.safety.deadman_supervisor import supervise

        class _StuckDeadman:
            """Counter never advances and the thread reports armed."""
            def __init__(self):
                self._thread = threading.Thread(
                    target=lambda: time.sleep(0.5),
                    name="stub", daemon=True,
                )
                self._thread.start()

            def proof_of_life(self) -> int:
                return 42    # never advances

            def is_armed(self) -> bool:
                # Wiring audit Pass 1 (F11.1) — the supervisor reads
                # the armed state through the public accessor now.
                return self._thread.is_alive()

        fired: list[float] = []
        stop = threading.Event()

        def _runner():
            supervise(
                _StuckDeadman(),
                poll_interval_s=0.05,
                stall_threshold_s=0.15,
                on_stall=lambda age: fired.append(age),
                stop_event=stop,
            )

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        # Give the supervisor a chance to log the stall.
        time.sleep(0.6)
        stop.set()
        t.join(timeout=1.0)

        assert fired, "supervisor should have fired on_stall at least once"
        assert all(age >= 0 for age in fired)

    def test_does_not_fire_when_counter_advances(self):
        from aria.safety.deadman_supervisor import supervise

        counter = {"v": 0}

        class _LiveDeadman:
            def __init__(self):
                self._thread = threading.Thread(
                    target=lambda: time.sleep(0.5),
                    name="live", daemon=True,
                )
                self._thread.start()

            def proof_of_life(self) -> int:
                counter["v"] += 1
                return counter["v"]

        fired: list[float] = []
        stop = threading.Event()

        def _runner():
            supervise(
                _LiveDeadman(),
                poll_interval_s=0.05,
                stall_threshold_s=0.15,
                on_stall=lambda age: fired.append(age),
                stop_event=stop,
            )

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        time.sleep(0.5)
        stop.set()
        t.join(timeout=1.0)

        assert not fired, (
            "supervisor must not fire on_stall when counter is advancing"
        )

    def test_start_in_thread_returns_stop_event(self):
        from aria.safety.deadman_supervisor import start_in_thread

        class _Stub:
            _thread = None

            def proof_of_life(self) -> int:
                return 0

        stop = start_in_thread(
            _Stub(), poll_interval_s=0.05, stall_threshold_s=0.15,
        )
        assert isinstance(stop, threading.Event)
        time.sleep(0.05)
        stop.set()
