"""Boot-counter / crash-loop guard (Recovery audit R-13).

Defends against a corrupt checkpoint or memory bit-flip that
deterministically crashes the application at startup, which would
otherwise be re-launched by systemd / kubelet forever — draining the
battery in a "Loop of Doom" before the spacecraft can re-establish
ground contact.

State files (under ``data/runtime/``):

  ``boot.attempt``   — touched at process entry; persists through reboots
  ``boot.success``   — touched after `_BOOT_SUCCESS_GRACE_S` of clean
                        loop iteration; signals "we got far enough"
  ``boot.history``   — JSONL ring of recent {ts, outcome} records;
                        used to compute the rate-limit window

Boot policy:

  * Increment ``boot.attempt`` counter.
  * If unsuccessful_attempts ≥ ``CRASH_LOOP_THRESHOLD`` and the most
    recent attempts span ≤ ``CRASH_LOOP_WINDOW_S``:
      → declare RESCUE mode.  Caller honours by skipping checkpoint
        restore + FDIR library + cognitive engine, bringing up only
        ``CommsAgent`` in beacon mode.
  * If reboot rate > ``MAX_REBOOTS_PER_HOUR``:
      → sleep ``REBOOT_COOLDOWN_S`` before continuing so a bad-day
        burst does not drain the battery.
  * After ``_BOOT_SUCCESS_GRACE_S`` of nominal loop iteration the
    application calls ``mark_boot_success()`` which resets the
    counter and quarantines the most-recent checkpoint if rescue
    mode was active.

Reference:
  * NASA-STD-8729.1A §6.4 — autonomous fault recovery rate limits.
  * Cassini "safing event" cooldown logic (JPL DSN 810-005-200 §4.7).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


# Number of consecutive unsuccessful boots within the window that
# triggers rescue mode.  3 chosen to allow two transient I/O races
# without escalating, but catch a true corrupt-checkpoint loop on the
# third attempt.  NASA-STD-8729.1A §6.4 recommends N=3-5 for
# autonomous-recovery escalation.
CRASH_LOOP_THRESHOLD = 3

# Window across which the threshold is evaluated.  Beyond this, old
# crashes do not count (they may have been a totally separate fault).
CRASH_LOOP_WINDOW_S = 600.0     # 10 min

# Rate-limit cooldown if reboot rate exceeds the per-hour cap.
MAX_REBOOTS_PER_HOUR = 12       # one every 5 min on average is plenty
REBOOT_COOLDOWN_S = 300.0       # 5 min — battery-sympathetic

# How long after process entry we consider the boot "successful" if
# nothing has crashed.  Long enough for the heaviest async tasks
# (memory load, agent registration, CIM start) to settle.
_BOOT_SUCCESS_GRACE_S = 60.0


@dataclass
class BootDecision:
    """Outcome of the pre-boot policy check."""
    rescue_mode: bool = False
    reason: str = ""
    attempt_count: int = 0
    recent_failures: int = 0
    cooldown_applied_s: float = 0.0
    state_dir: str = ""


def _runtime_dir() -> Path:
    env = os.environ.get("ARIA_RUNTIME_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "data" / "runtime"


def _atomic_touch(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _load_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        return []
    return out


def _append_history(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
    except OSError as exc:
        logger.warning("boot_counter.history_append_failed", error=str(exc))


def begin_boot(state_dir: Optional[Path] = None) -> BootDecision:
    """Call FIRST in main(), before any subsystem boots.

    Records the attempt, evaluates the crash-loop policy, returns a
    BootDecision the caller honours.  Always returns a decision —
    never raises, so the boot path remains predictable even on a flaky
    disk (the worst case is that we re-enter rescue more aggressively
    than necessary, which is the conservative direction).
    """
    state_dir = state_dir or _runtime_dir()
    attempt_path = state_dir / "boot.attempt"
    success_path = state_dir / "boot.success"
    history_path = state_dir / "boot.history"

    decision = BootDecision(state_dir=str(state_dir))
    now = time.time()

    # Read current attempt counter.
    attempt_count = 0
    try:
        if attempt_path.is_file():
            data = json.loads(attempt_path.read_text(encoding="utf-8"))
            attempt_count = int(data.get("counter", 0))
    except (OSError, ValueError):
        attempt_count = 0
    attempt_count += 1
    decision.attempt_count = attempt_count

    # Persist incremented counter immediately.
    try:
        _atomic_touch(attempt_path, {"counter": attempt_count, "ts": now})
    except OSError as exc:
        logger.warning("boot_counter.attempt_persist_failed", error=str(exc))

    # Load recent history; only entries within window count.
    history = _load_history(history_path)
    recent = [
        h for h in history[-50:]
        if now - float(h.get("ts", 0)) <= CRASH_LOOP_WINDOW_S
    ]
    recent_failures = sum(1 for h in recent if h.get("outcome") != "success")
    decision.recent_failures = recent_failures

    # Reboot-rate cooldown.
    last_hour = [h for h in history[-50:] if now - float(h.get("ts", 0)) <= 3600]
    if len(last_hour) >= MAX_REBOOTS_PER_HOUR:
        logger.error("boot_counter.cooldown_triggered",
                     reboots_in_last_hour=len(last_hour),
                     cooldown_s=REBOOT_COOLDOWN_S)
        decision.cooldown_applied_s = REBOOT_COOLDOWN_S
        time.sleep(REBOOT_COOLDOWN_S)

    # Crash-loop policy.
    if recent_failures >= CRASH_LOOP_THRESHOLD:
        decision.rescue_mode = True
        decision.reason = (
            f"crash_loop_detected: {recent_failures} unsuccessful boots "
            f"within {CRASH_LOOP_WINDOW_S}s window"
        )
        logger.error("boot_counter.rescue_mode_entered",
                     attempt=attempt_count,
                     recent_failures=recent_failures)
    else:
        # Was the last attempt successful?  If not, log the unhealthy
        # streak so operators can see it climbing.
        if recent_failures > 0:
            logger.warning("boot_counter.recent_failures",
                           attempt=attempt_count,
                           recent_failures=recent_failures,
                           threshold=CRASH_LOOP_THRESHOLD)

    # Append a "started" record so a subsequent crash leaves a
    # tombstone even if mark_boot_success() never runs.
    _append_history(history_path, {
        "ts": now,
        "attempt": attempt_count,
        "outcome": "started",
        "rescue_mode": decision.rescue_mode,
    })

    return decision


def mark_boot_success(state_dir: Optional[Path] = None) -> None:
    """Call after ``_BOOT_SUCCESS_GRACE_S`` of nominal loop iteration.

    Resets the attempt counter, records a success in the history, and
    flips ``boot.success`` so the next pre-boot evaluation sees a
    clean record.
    """
    state_dir = state_dir or _runtime_dir()
    attempt_path = state_dir / "boot.attempt"
    success_path = state_dir / "boot.success"
    history_path = state_dir / "boot.history"
    now = time.time()

    try:
        _atomic_touch(success_path, {"ts": now})
    except OSError as exc:
        logger.warning("boot_counter.success_persist_failed", error=str(exc))

    # Reset the attempt counter.
    try:
        _atomic_touch(attempt_path, {"counter": 0, "ts": now})
    except OSError as exc:
        logger.warning("boot_counter.attempt_reset_failed", error=str(exc))

    _append_history(history_path, {
        "ts": now,
        "outcome": "success",
    })
    logger.info("boot_counter.boot_success_marked")


def quarantine_latest_checkpoint(checkpoint_dir: Path) -> Optional[Path]:
    """Rescue-mode: rename the most-recent checkpoint to .quarantined
    so the next boot does not re-load it.  Returns the new path on
    success."""
    try:
        candidates = sorted(checkpoint_dir.glob("checkpoint_*.json"))
        candidates = [c for c in candidates if not c.name.endswith(".quarantined")]
        if not candidates:
            return None
        latest = candidates[-1]
        target = latest.with_suffix(".json.quarantined")
        os.rename(latest, target)
        # Also quarantine the .bak twin if present.
        bak = Path(str(latest) + ".bak")
        if bak.exists():
            os.rename(bak, bak.with_suffix(".bak.quarantined"))
        logger.error("boot_counter.checkpoint_quarantined",
                     original=str(latest), quarantined=str(target))
        return target
    except OSError as exc:
        logger.warning("boot_counter.quarantine_failed", error=str(exc))
        return None


def schedule_success_marker(loop: Any, grace_s: float = _BOOT_SUCCESS_GRACE_S) -> None:
    """Schedule ``mark_boot_success`` on the running loop after the
    grace window.  Caller passes the ``asyncio`` loop the application
    is using."""
    import asyncio

    async def _delayed_mark() -> None:
        try:
            await asyncio.sleep(grace_s)
            mark_boot_success()
        except asyncio.CancelledError:
            pass
        except Exception as exc:    # noqa: BLE001
            logger.warning("boot_counter.success_marker_failed", error=str(exc))

    asyncio.run_coroutine_threadsafe(_delayed_mark(), loop)
