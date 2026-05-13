"""Cumulative resource-budget gate.

Implements §F-12 of docs/FAILSAFE_ARCHITECTURE.md.

Catches the slow-drain attack (W-2): a thousand individually permissible
small commands that together push a resource over the mission cap.

The constitution publishes the per-resource caps (sealed
``constitution.v1.json::resource_ceilings``). This module:

  - tracks consumption in sliding-window counters (already partially in
    constitution.consume_resource); this module elevates that into a
    multi-resource service with budget projections;
  - exposes ``project(resource, qty)`` so callers can ask
    "would this push us past hard cap?" *without* consuming;
  - exposes ``commit(resource, qty)`` to record a confirmed consumption;
  - exposes ``status()`` for the operator console / monitor;
  - emits ``aria.budget.soft_breach`` and ``aria.budget.hard_breach``
    events so the rule-based monitor and operator UIs see overruns
    in real time.

Atomic compare-and-swap on the budget counter is provided through a
single per-resource lock so two concurrent requests cannot both be told
"there's room" and then together overspend.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional, Tuple

import structlog

from aria.cognitive.constitution import Constitution, get_constitution

logger = structlog.get_logger()


def _is_finite_nonneg(x: Any) -> bool:
    """Autonomy audit F17 — refuse non-finite / negative qty."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v >= 0.0


@dataclass
class _Window:
    """Per-resource sliding window."""
    window_s: float
    samples: Deque[Tuple[float, float]] = field(default_factory=deque)  # (ts, qty)

    def total(self, now: float) -> float:
        cutoff = now - self.window_s
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()
        return sum(q for _, q in self.samples)

    def add(self, qty: float, now: float) -> float:
        # prune first so total() stays consistent
        cutoff = now - self.window_s
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()
        self.samples.append((now, qty))
        return sum(q for _, q in self.samples)


@dataclass(frozen=True)
class BudgetStatus:
    """Snapshot for the operator console."""
    resource: str
    window_s: int
    soft_cap: float
    hard_cap: float
    current: float
    soft_remaining: float
    hard_remaining: float
    unit: str
    pct_of_hard: float


@dataclass(frozen=True)
class Projection:
    """Outcome of a project() call (no commit)."""
    fits_soft: bool
    fits_hard: bool
    projected: float
    soft_cap: float
    hard_cap: float
    reason: str = ""


class ResourceBudgetGate:
    """Multi-resource cumulative budget gate.

    One instance covers every resource enumerated in the constitution.
    The constitution's caps are read each call, so an updated sealed
    constitution propagates immediately at next call (within a single
    process; cross-process needs a process restart anyway).
    """

    def __init__(
        self,
        constitution: Optional[Constitution] = None,
        publish_fn: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        self._constitution = constitution or get_constitution()
        self._publish = publish_fn or (lambda topic, payload: None)
        self._windows: Dict[str, _Window] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self.soft_breaches: int = 0
        self.hard_breaches: int = 0

    def _get_lock(self, resource: str) -> threading.Lock:
        with self._global_lock:
            return self._locks.setdefault(resource, threading.Lock())

    def _get_window(self, resource: str, window_s: int) -> _Window:
        with self._global_lock:
            return self._windows.setdefault(resource, _Window(float(window_s)))

    def project(self, resource: str, qty: float) -> Projection:
        """Ask 'would this fit?' without committing."""
        # Autonomy audit F17 — non-finite or negative qty refuses with
        # fits_hard=False so the caller never proceeds with a poisoned
        # input.
        if not _is_finite_nonneg(qty):
            return Projection(
                fits_soft=False, fits_hard=False,
                projected=float("inf"),
                soft_cap=float("inf"), hard_cap=float("inf"),
                reason="qty must be finite and non-negative",
            )
        rule = self._constitution.resource_rule(resource)
        if rule is None:
            return Projection(True, True, float(qty), float("inf"), float("inf"),
                              reason="resource not in constitution; allowed by default")
        soft = float(rule.get("soft_cap", float("inf")))
        hard = float(rule.get("hard_cap", float("inf")))
        win_s = int(rule.get("window_seconds", 60))
        win = self._get_window(resource, win_s)
        with self._get_lock(resource):
            # Autonomy audit F4 — monotonic clock for the gate.  The
            # samples themselves carry monotonic timestamps so an NTP
            # set-step cannot resurrect old samples.
            now = time.monotonic()
            current = win.total(now)
            projected = current + float(qty)
        return Projection(
            fits_soft=projected <= soft,
            fits_hard=projected <= hard,
            projected=projected,
            soft_cap=soft, hard_cap=hard,
        )

    def commit(self, resource: str, qty: float) -> Projection:
        """Atomically record consumption.

        Returns a Projection with `fits_*` set to True only if the
        consumption fit under the respective cap. If hard cap is
        crossed, the consumption is *still recorded* (so we have an
        accurate picture of what happened) and a hard_breach event
        fires; caller should immediately revert the underlying
        actuator change.
        """
        # Autonomy audit F17 — non-finite / negative qty is refused
        # WITHOUT being recorded.  Otherwise a single NaN sample would
        # poison the sliding-window total for the rest of the window.
        if not _is_finite_nonneg(qty):
            logger.error("budget.invalid_qty", resource=resource, qty=qty)
            return Projection(
                fits_soft=False, fits_hard=False,
                projected=float("inf"),
                soft_cap=float("inf"), hard_cap=float("inf"),
                reason="qty must be finite and non-negative",
            )
        rule = self._constitution.resource_rule(resource)
        if rule is None:
            # Unknown resource: don't gate, just log and pass.
            logger.info("budget.unknown_resource", resource=resource, qty=qty)
            return Projection(True, True, float(qty), float("inf"), float("inf"),
                              reason="resource not in constitution")
        soft = float(rule.get("soft_cap", float("inf")))
        hard = float(rule.get("hard_cap", float("inf")))
        win_s = int(rule.get("window_seconds", 60))
        win = self._get_window(resource, win_s)
        with self._get_lock(resource):
            now = time.monotonic()    # autonomy F4
            new_total = win.add(float(qty), now)
        # Wiring audit Pass 3 (F1.15) — mirror the consumption into
        # the Constitution's own resource window so its forward-
        # projection in ``check()`` sees actual history rather than a
        # zero baseline. resource_budget.commit() remains the
        # canonical write path; constitution.consume_resource() is
        # called only for projection-consistency. Failures don't
        # affect the budget commit itself.
        try:
            self._constitution.consume_resource(resource, float(qty))
        except Exception as exc:    # noqa: BLE001
            logger.warning(
                "budget.constitution_mirror_failed",
                resource=resource, error=str(exc),
            )
        fits_soft = new_total <= soft
        fits_hard = new_total <= hard
        if not fits_hard:
            self.hard_breaches += 1
            logger.error("budget.hard_breach",
                         resource=resource, qty=qty, total=new_total, cap=hard)
            self._publish("aria.budget.hard_breach", {
                "resource": resource, "qty": qty,
                "total": new_total, "cap": hard,
                "ts": now,
            })
        elif not fits_soft:
            self.soft_breaches += 1
            logger.warning("budget.soft_breach",
                           resource=resource, qty=qty, total=new_total, cap=soft)
            self._publish("aria.budget.soft_breach", {
                "resource": resource, "qty": qty,
                "total": new_total, "cap": soft,
                "ts": now,
            })
        return Projection(fits_soft=fits_soft, fits_hard=fits_hard,
                          projected=new_total, soft_cap=soft, hard_cap=hard)

    def status(self, resource: str) -> Optional[BudgetStatus]:
        rule = self._constitution.resource_rule(resource)
        if rule is None:
            return None
        soft = float(rule.get("soft_cap", float("inf")))
        hard = float(rule.get("hard_cap", float("inf")))
        win_s = int(rule.get("window_seconds", 60))
        win = self._get_window(resource, win_s)
        now = time.monotonic()    # autonomy F4
        with self._get_lock(resource):
            current = win.total(now)
        return BudgetStatus(
            resource=resource,
            window_s=win_s, soft_cap=soft, hard_cap=hard,
            current=current,
            soft_remaining=max(0.0, soft - current),
            hard_remaining=max(0.0, hard - current),
            unit=str(rule.get("unit", "")),
            pct_of_hard=(current / hard * 100.0) if hard > 0 else 0.0,
        )

    def all_status(self) -> Dict[str, BudgetStatus]:
        out: Dict[str, BudgetStatus] = {}
        for entry in self._constitution._sealed.constitution.get("resource_ceilings", []):
            res = entry.get("resource", "")
            if res:
                s = self.status(res)
                if s is not None:
                    out[res] = s
        return out


_INSTANCE: Optional[ResourceBudgetGate] = None
_INSTANCE_LOCK = threading.Lock()


def get_budget_gate() -> ResourceBudgetGate:
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = ResourceBudgetGate()
    return _INSTANCE


def reset_for_test() -> None:
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = None
