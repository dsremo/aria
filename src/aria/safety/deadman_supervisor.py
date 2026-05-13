"""External supervisor for ``DeadmanTimer.proof_of_life()``.

Autonomy audit F5 added a proof-of-life counter on the deadman thread
so an external supervisor can verify the daemon is still iterating,
not just check that the timer says "armed".  This module is the
supervisor.

Run as a separate process (preferred) or a separate thread inside the
main process:

    # As a process (preferred — survives main-process crash):
    python -m aria.safety.deadman_supervisor --pid-file /run/aria/main.pid \\
        --interval 30 --stall-threshold 60

    # As a thread inside main:
    from aria.safety.deadman_supervisor import start_in_thread
    start_in_thread(deadman, on_stall=lambda age: kill_main_process())

The supervisor polls ``deadman.proof_of_life()`` every ``interval``
seconds.  If the counter has not advanced in ``stall_threshold``
seconds AND the timer reports itself as armed, the supervisor
escalates: by default it logs ``deadman_supervisor.thread_died`` and
invokes ``on_stall(age_s)``.  Production deployments wire ``on_stall``
to assert the kill switch out-of-band (via an IPMI-style channel that
doesn't depend on the same Python process).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger()


DEFAULT_POLL_INTERVAL_S = 30.0
DEFAULT_STALL_THRESHOLD_S = 60.0


def _default_on_stall(age_s: float) -> None:
    """Recovery audit R-18: default behaviour upgraded from log-only
    to (1) tombstone, (2) kill-switch assert, (3) structured error.
    Production deploys can still override on_stall to add hardware
    out-of-band signalling, but the in-process default now actually
    halts autonomy.
    """
    logger.error("deadman_supervisor.thread_died",
                 stalled_for_s=round(age_s, 1))
    # (1) Tombstone for the next boot's diagnostics.
    try:
        runtime = (Path(os.environ.get("ARIA_RUNTIME_DIR"))
                   if os.environ.get("ARIA_RUNTIME_DIR")
                   else Path("data") / "runtime")
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "deadman_stall.tombstone").write_text(
            f"stalled_for_s={age_s:.1f}\nat={int(time.time())}\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    # (2) Kill switch — persisted (Recovery audit R-15) so it survives
    # the SIGTERM/restart cycle.
    try:
        from aria.safety.kill_switch import get_kill_switch
        get_kill_switch().assert_kill(
            source="deadman_supervisor",
            reason=f"thread stalled {age_s:.0f}s",
        )
    except Exception as exc:    # noqa: BLE001
        logger.error("deadman_supervisor.kill_switch_failed", error=str(exc))


def supervise(
    deadman: Any,
    *,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    stall_threshold_s: float = DEFAULT_STALL_THRESHOLD_S,
    on_stall: Optional[Callable[[float], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """Block the calling thread, polling the deadman.

    Returns when ``stop_event`` is set (or never, if not supplied).
    Calls ``on_stall(age_s)`` when the proof-of-life counter has not
    advanced in ``stall_threshold_s`` AND the timer reports armed.

    The default ``on_stall`` (recovery audit R-18) writes a tombstone
    AND asserts the persisted kill switch — so the demoted posture
    survives any subsequent restart, not just a log entry.
    """
    stop_event = stop_event or threading.Event()
    if on_stall is None:
        on_stall = _default_on_stall

    last_counter = -1
    last_advance_monotonic = time.monotonic()

    while not stop_event.is_set():
        try:
            counter = int(deadman.proof_of_life())
            # Wiring audit Pass 1 (F11.1) — use the public is_armed()
            # accessor rather than reaching into the private _thread.
            armed = bool(deadman.is_armed())
        except Exception as exc:    # noqa: BLE001
            logger.exception("deadman_supervisor.poll_error", error=str(exc))
            stop_event.wait(poll_interval_s)
            continue

        now_m = time.monotonic()
        if counter != last_counter:
            last_counter = counter
            last_advance_monotonic = now_m
        else:
            stall_age = now_m - last_advance_monotonic
            if armed and stall_age > stall_threshold_s:
                logger.error(
                    "deadman_supervisor.stall_detected",
                    counter=counter,
                    stall_age_s=round(stall_age, 1),
                    stall_threshold_s=stall_threshold_s,
                )
                try:
                    on_stall(stall_age)
                except Exception as exc:    # noqa: BLE001
                    logger.exception(
                        "deadman_supervisor.on_stall_failed",
                        error=str(exc),
                    )
                # Reset so we don't fire repeatedly while still stalled.
                last_advance_monotonic = now_m

        stop_event.wait(poll_interval_s)


def start_in_thread(
    deadman: Any,
    *,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    stall_threshold_s: float = DEFAULT_STALL_THRESHOLD_S,
    on_stall: Optional[Callable[[float], None]] = None,
) -> threading.Event:
    """Launch ``supervise`` in a daemon thread.  Returns a ``stop_event``
    the caller can ``.set()`` for graceful shutdown."""
    stop = threading.Event()

    def _runner() -> None:
        try:
            supervise(
                deadman,
                poll_interval_s=poll_interval_s,
                stall_threshold_s=stall_threshold_s,
                on_stall=on_stall,
                stop_event=stop,
            )
        except BaseException as exc:    # noqa: BLE001
            logger.exception("deadman_supervisor.thread_crashed",
                             error=f"{type(exc).__name__}: {exc}")

    t = threading.Thread(
        target=_runner, name="deadman-supervisor", daemon=True,
    )
    t.start()
    return stop


# ── CLI ─────────────────────────────────────────────────────────


def _parse_pid(pid_file: Path) -> int:
    try:
        return int(pid_file.read_text().strip())
    except Exception as exc:    # noqa: BLE001
        logger.error("deadman_supervisor.bad_pid_file",
                     pid_file=str(pid_file), error=str(exc))
        sys.exit(2)


def _on_stall_signal_main(main_pid: int) -> Callable[[float], None]:
    """Default on-stall handler when running as a separate process.

    Sends SIGTERM to the main process so the systemd / kubelet
    supervisor can restart it.  Production deploys wire this to a
    hardware kill-switch instead.
    """
    def _handler(age_s: float) -> None:
        logger.error("deadman_supervisor.signalling_main_process",
                     main_pid=main_pid, age_s=round(age_s, 1))
        try:
            os.kill(main_pid, signal.SIGTERM)
        except ProcessLookupError:
            logger.warning("deadman_supervisor.main_already_gone",
                           main_pid=main_pid)
    return _handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aria.safety.deadman_supervisor",
        description="External proof-of-life supervisor for the deadman thread.",
    )
    parser.add_argument(
        "--pid-file", type=Path, required=False,
        help="PID file of the main aria process (signals SIGTERM on stall).",
    )
    parser.add_argument(
        "--interval", type=float, default=DEFAULT_POLL_INTERVAL_S,
        help=f"Poll interval seconds (default {DEFAULT_POLL_INTERVAL_S}).",
    )
    parser.add_argument(
        "--stall-threshold", type=float, default=DEFAULT_STALL_THRESHOLD_S,
        help=(f"Stall threshold seconds (default "
              f"{DEFAULT_STALL_THRESHOLD_S})."),
    )
    args = parser.parse_args(argv)

    # The CLI form supervises the in-process singleton.  When run as a
    # separate process you also need an IPC channel to query the
    # remote deadman; the recommended pattern is to scrape the
    # heartbeat bus topic ``aria.monitor.heartbeat`` and / or the
    # systemd watchdog (``$NOTIFY_SOCKET``).  This script demonstrates
    # the in-process mode.
    from aria.safety.kill_switch import DeadmanTimer

    # Stand up a placeholder DeadmanTimer if we don't have one — the
    # CLI form is mainly for ops smoke-testing the supervisor itself.
    placeholder = DeadmanTimer(on_silence=lambda age: None, window_s=300.0)
    placeholder.start()

    on_stall = (
        _on_stall_signal_main(_parse_pid(args.pid_file))
        if args.pid_file is not None else None
    )
    try:
        supervise(
            placeholder,
            poll_interval_s=args.interval,
            stall_threshold_s=args.stall_threshold,
            on_stall=on_stall,
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":    # pragma: no cover
    sys.exit(main())
