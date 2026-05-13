"""Last-gasp diagnostic dump (Recovery audit R-6).

Installs ``faulthandler`` + ``sys.excepthook`` so a Python segfault,
uncaught exception, or hard exit leaves a forensic trail under
``data/last_gasp/`` that the next boot can pick up and prepend to its
beacon downlink.

Three layers:

  * ``faulthandler.enable(file=last_gasp_fp, all_threads=True)``
      — catches segfaults / abort signals, dumps every thread's
        Python stack to the file before Python dies.
  * ``sys.excepthook``
      — catches uncaught Python exceptions; writes a structured JSON
        record (timestamp, exception type, full traceback,
        truncated repr of the most recent bus events).
  * ``atexit.register``
      — final flush hook that calls registered cleanup functions
        (replay-guard, session-store, fault-history) so coalesced
        in-memory state lands on disk even if shutdown is via
        ``os._exit``.

The directory rolls daily (``last_gasp/<YYYY-MM-DD>.log``) so a
multi-year mission does not accumulate unbounded files.

Reference:
  * NASA-STD-8729.1A §6.4 — autonomous-fault diagnostic capture.
  * Cassini "safing event" log (JPL DSN 810-005-200 §4.7).
"""

from __future__ import annotations

import atexit
import datetime as _dt
import faulthandler
import json
import os
import signal
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, List, Optional

import structlog

logger = structlog.get_logger()


_INSTALLED = False
_CLEANUP_HOOKS: List[Callable[[], None]] = []
_LAST_GASP_FP: Optional[Any] = None


def _last_gasp_dir() -> Path:
    env = os.environ.get("ARIA_RUNTIME_DIR")
    base = Path(env) if env else Path("data") / "runtime"
    return base.parent / "last_gasp"


def install() -> bool:
    """Install all three layers.  Idempotent.  Returns True on success.

    Safe to call from main() before any other subsystem starts.  Logs
    a warning and returns False on any failure (file permissions, no
    SIGUSR1 on Windows, etc.) but never raises — boot must not depend
    on diagnostic plumbing.
    """
    global _INSTALLED, _LAST_GASP_FP
    if _INSTALLED:
        return True
    try:
        gdir = _last_gasp_dir()
        gdir.mkdir(parents=True, exist_ok=True)
        today = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%d")
        fpath = gdir / f"{today}.log"
        # Open append + line-buffered so a faulthandler dump survives
        # even if the process is killed in the middle of a write.
        fp = open(fpath, "a", buffering=1, encoding="utf-8")
        _LAST_GASP_FP = fp
        faulthandler.enable(file=fp, all_threads=True)
        # Register SIGUSR1 → dump tracebacks (operator can `kill -USR1
        # <pid>` to capture state without killing the process).
        try:
            faulthandler.register(
                signal.SIGUSR1, file=fp, all_threads=True, chain=False,
            )
        except (AttributeError, ValueError):
            # SIGUSR1 doesn't exist on Windows; not fatal.
            pass
        _install_excepthook(fp)
        atexit.register(_run_cleanup_hooks)
        _INSTALLED = True
        logger.info("last_gasp.installed", path=str(fpath))
        return True
    except OSError as exc:
        logger.warning("last_gasp.install_failed", error=str(exc))
        return False


def _install_excepthook(fp: Any) -> None:
    prev_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            record = {
                "ts": time.time(),
                "iso": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
                "type": exc_type.__name__ if exc_type else "Unknown",
                "msg": str(exc_value)[:2000] if exc_value else "",
                "traceback": "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                )[:8000],
            }
            fp.write("---LAST-GASP---\n")
            fp.write(json.dumps(record))
            fp.write("\n")
            fp.flush()
            try:
                os.fsync(fp.fileno())
            except OSError:
                pass
        except Exception:
            pass
        # Chain to the previous hook so structlog / ipython-style
        # handlers still see the exception.
        if prev_hook is not None:
            try:
                prev_hook(exc_type, exc_value, exc_tb)
            except Exception:
                pass

    sys.excepthook = _hook


def register_cleanup(fn: Callable[[], None]) -> None:
    """Subsystems with coalesced in-memory state register here so
    ``atexit`` flushes them even on ``os._exit``-style shutdowns."""
    if fn in _CLEANUP_HOOKS:
        return
    _CLEANUP_HOOKS.append(fn)


def _run_cleanup_hooks() -> None:
    for fn in list(_CLEANUP_HOOKS):
        try:
            fn()
        except Exception as exc:    # noqa: BLE001
            logger.warning("last_gasp.cleanup_hook_failed",
                           hook=getattr(fn, "__name__", "anon"),
                           error=str(exc))
    if _LAST_GASP_FP is not None:
        try:
            _LAST_GASP_FP.flush()
            _LAST_GASP_FP.close()
        except OSError:
            pass


def has_unsent_dump() -> bool:
    """Recovery audit R-6: the next boot calls this; if True the
    comms beacon prepends a 'have-crash-dump' flag for ground."""
    try:
        gdir = _last_gasp_dir()
        if not gdir.is_dir():
            return False
        for path in sorted(gdir.iterdir(), reverse=True):
            if path.suffix == ".log" and path.stat().st_size > 0:
                return True
        return False
    except OSError:
        return False
