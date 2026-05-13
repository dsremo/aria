"""Constitutional layer — final word on whether a proposed action is allowed.

Implements §F-3 of docs/FAILSAFE_ARCHITECTURE.md.

Sits *above* the LLM and *above* ExecutionGuard. The flow is:

    LLM proposes action ─┐
                         ▼
    Constitution.check(action, params, trust_tier) ──┐
    │  ALLOW  ──────────────────────────────────────► ExecutionGuard
    │  GATE   ──► OperatorConsole (two-person rule, cooling-off) ──► Guard
    │  DENY   ──► refuse + audit + (optional) safe_mode trigger
    └─────────────────────────────────────────────────┘

Three rule classes (loaded from the sealed constitution.v1.json):

  forbidden_actions  — never allowed, regardless of who or how
  gated_actions      — allowed with operator confirmation + cooldown
  resource_ceilings  — cumulative hard caps; enforced via consume_resource

The constitution NEVER mutates the proposal. It returns a verdict.
Mutation is the planner's job.

This file imports the *sealed* constitution at first use; the data
travels through ``cognitive/sealed_prompt.SealedContent`` so a tampered
file blocks boot before this module ever runs.

Threats addressed:
  T-II-1 alignment-faking
  T-II-2 sandbagging          (constitution still rejects in prod)
  T-II-3 specification gaming (forbidden list is broad enough)
  T-IV-1 jealous operator     (gated + crew-life forbidden)
  T-IV-2 coerced operator     (two-person rule)
  T-VI-3 hardware tamper      (constitution is part of sealed manifest)
  W-1 LinkedIn-bio injection  (rejects the cascade target action)
  W-4 jealous operator        (forbidden_actions hard-bans)
"""

from __future__ import annotations

import enum
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import structlog

from aria.cognitive.sealed_prompt import SealedContent, get_sealed

logger = structlog.get_logger()


# Autonomy audit F1 — default-DENY for unmapped actions.
#
# When the sealed constitution exposes ``allowed_actions`` we treat any
# action not on that list, not on ``forbidden_actions``, and not on
# ``gated_actions`` as DENY (rather than the previous fail-open ALLOW).
# Existing test fixtures that ship without ``allowed_actions`` keep the
# legacy ALLOW behaviour, so widening the constitution remains a
# conscious sealed-release event.  Production deployments MUST add
# ``allowed_actions``.

# Autonomy audit F18 — numeric guard for caller-supplied resource_qty.
def _is_finite_nonneg(x: Any) -> bool:
    """True iff ``x`` coerces to a finite, non-negative float.  NaN /
    inf / negative are rejected so a single bad sensor value cannot
    poison a sliding-window resource accumulator."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v >= 0.0


class TrustTier(enum.IntEnum):
    """Minimum trust required to influence an action.

    Mirrors the constitution's trust_tiers map. Use IntEnum so
    comparisons are total order (OPERATOR > LOCAL_SENSOR > ...).
    """

    THIRD_PARTY_CONTENT = 0
    EXTERNAL_API = 1
    LOCAL_SENSOR = 2
    OPERATOR = 3


class Verdict(enum.Enum):
    """Constitutional verdict on a proposed action."""

    ALLOW = "allow"   # safe to dispatch directly
    GATE = "gate"     # requires operator(s) + cooling-off
    DENY = "deny"     # forbidden, never executable


@dataclass(frozen=True)
class CheckResult:
    """The constitutional layer's response to one proposal."""

    verdict: Verdict
    reason: str
    rule_id: str = ""
    operator_approvals_required: int = 0
    cooling_off_seconds: int = 0
    undo_window_seconds: int = 0
    threats_addressed: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW

    @property
    def denied(self) -> bool:
        return self.verdict is Verdict.DENY


# ── Resource budget tracking ──────────────────────────────────────


@dataclass
class _ResourceWindow:
    """Sliding window of resource consumption for one resource id."""

    window_seconds: int
    samples: list[tuple[float, float]] = field(default_factory=list)  # (ts, qty)

    def consume(self, qty: float, now: float) -> float:
        """Add a sample, prune old, return total within window."""
        self.samples.append((now, qty))
        cutoff = now - self.window_seconds
        # Prune in-place; cheaper than a deque for the small samples
        # we expect (<1k entries per window).
        self.samples = [(t, q) for (t, q) in self.samples if t >= cutoff]
        return sum(q for (_, q) in self.samples)

    def total(self, now: float) -> float:
        cutoff = now - self.window_seconds
        return sum(q for (t, q) in self.samples if t >= cutoff)


# ── Constitutional layer ──────────────────────────────────────────


class Constitution:
    """The constitutional layer. Process-wide singleton.

    Responsibilities:
      - Lazy-load the sealed content on first use.
      - Resolve `check(action, params, trust_tier)` → CheckResult.
      - Track cumulative resource consumption against ceilings.
      - Re-check on demand: every call hits the sealed data, no caches
        of mutable state. The sealed data itself is frozen, so callers
        cannot poison the rule set.
    """

    def __init__(self, sealed: SealedContent | None = None) -> None:
        self._sealed = sealed or get_sealed()
        # ResourceWindow per resource id. Created lazily on first use.
        self._budgets: dict[str, _ResourceWindow] = {}
        self._lock = threading.Lock()
        # Autonomy audit F19 — runtime tamper detection on safety-
        # critical sealed scalars.  Boot already verifies the manifest
        # hash; this catches in-memory bit-flips between boots.
        self._sealed_check_counter = 0
        self._sealed_check_interval = 256
        # Wiring audit Pass 3 (F6.8) — fail-closed flag set when the
        # sealed-config reverify itself fails. While set, ``check()``
        # returns DENY rather than evaluating against possibly-
        # tampered in-memory state. Cleared on next successful reload.
        self._reverify_failed = False

    def _runtime_reverify(self) -> None:
        """Autonomy audit F19 — periodically re-read the sealed scalar
        ``trust_tier_rules.min_tier_for_safety_critical`` from the
        on-disk sealed content and refuse to operate if the in-memory
        copy diverges.  Bit-flips on the cached structure trigger a
        re-load + audit event."""
        self._sealed_check_counter += 1
        if (self._sealed_check_counter % self._sealed_check_interval) != 0:
            return
        try:
            on_disk = get_sealed().constitution.get("trust_tier_rules", {})
            in_memory = self._sealed.constitution.get("trust_tier_rules", {})
            if (int(on_disk.get("min_tier_for_safety_critical", 3))
                    != int(in_memory.get("min_tier_for_safety_critical", 3))):
                logger.error(
                    "constitution.sealed_runtime_tamper",
                    note="min_tier_for_safety_critical drift; reloading from disk",
                )
                # Reload from disk; on-disk SealedContent is hash-checked at
                # boot, so this brings us back to a known-good state.
                self._sealed = get_sealed()
                # Successful reload — clear any prior fail-closed flag.
                self._reverify_failed = False
        except Exception as exc:    # noqa: BLE001
            # Wiring audit Pass 3 (F6.8) — fail-closed on reload
            # failure. The sealed-content invariant is hard; degrading
            # to "use the in-memory copy that may be tampered" defeats
            # the runtime-reverify purpose. We set ``_reverify_failed``
            # so subsequent ``check()`` calls return DENY rather than
            # ALLOWing on a possibly-tampered config.  The flag clears
            # on the next successful reload.
            self._reverify_failed = True
            logger.critical(
                "constitution.sealed_runtime_check_failed_fail_closed",
                error=f"{type(exc).__name__}: {exc}",
                impact="reverify of sealed constitution failed; "
                       "subsequent check() calls will return DENY until "
                       "the next successful reload",
            )

    # ── Frozen rule lookups ──────────────────────────────────────

    @property
    def constitution_version(self) -> int:
        return self._sealed.constitution_version

    def is_forbidden(self, action: str) -> bool:
        return action in self._sealed.forbidden_actions()

    def gated_rule(self, action: str) -> Mapping[str, Any] | None:
        return self._sealed.gated_action(action)

    # ── Post-condition predicates (TT&C audit C-5) ──────────────

    # Each forbidden physical end-state is encoded as a predicate over a
    # caller-supplied projected world-state dict.  When ``check`` (or
    # ``check_with_projection`` below) is given a projected post-state,
    # we refuse the action if any forbidden predicate evaluates True.
    # The predicates encode the physical hazards captured in
    # ``forbidden_actions`` so an attacker cannot compose three
    # individually-allowed actions into the same hazardous outcome
    # (the "Ghost Command" chain in the TT&C audit).
    _FORBIDDEN_POSTCONDITIONS: tuple[tuple[str, Callable[[Mapping[str, Any]], bool]], ...] = (
        (
            "vent_crew_quarters_postcondition",
            lambda projected: (
                bool(projected.get("crew_present", True))
                and float(projected.get("cabin_pressure_kpa", 101.0)) < 30.0
                # 30 kPa is the NASA-STD-3001 §3.7 EVA-prep depressurisation
                # floor — below that crew cannot survive without a suit.
            ),
        ),
        (
            "disable_eclss_postcondition",
            lambda projected: (
                bool(projected.get("crew_present", True))
                and bool(projected.get("eclss_active", True)) is False
            ),
        ),
        (
            "kill_switch_unreachable_postcondition",
            lambda projected: (
                bool(projected.get("kill_switch_reachable", True)) is False
            ),
        ),
        (
            "audit_disabled_postcondition",
            lambda projected: (
                bool(projected.get("audit_active", True)) is False
            ),
        ),
    )

    def check_postconditions(
        self, projected_state: Mapping[str, Any] | None,
    ) -> CheckResult | None:
        """Return DENY when ``projected_state`` matches any forbidden
        end-state predicate; ``None`` if all predicates pass or the
        caller did not supply a projection.
        """
        if not projected_state:
            return None
        for rule_id, predicate in self._FORBIDDEN_POSTCONDITIONS:
            try:
                if predicate(projected_state):
                    return CheckResult(
                        verdict=Verdict.DENY,
                        reason=(
                            f"projected post-state matches forbidden "
                            f"predicate '{rule_id}'"
                        ),
                        rule_id=f"forbidden_postcondition:{rule_id}",
                    )
            except Exception as exc:    # noqa: BLE001
                logger.error(
                    "constitution.postcondition_predicate_failed",
                    rule_id=rule_id, error=str(exc),
                )
                # Fail-safe: if the predicate raises, refuse.
                return CheckResult(
                    verdict=Verdict.DENY,
                    reason=f"postcondition predicate '{rule_id}' raised",
                    rule_id=f"forbidden_postcondition_error:{rule_id}",
                )
        return None

    def resource_rule(self, resource: str) -> Mapping[str, Any] | None:
        return self._sealed.resource_ceiling(resource)

    # ── Core gate ───────────────────────────────────────────────

    def check(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        trust_tier: TrustTier = TrustTier.OPERATOR,
    ) -> CheckResult:
        """Evaluate a proposed action against the sealed rules.

        Returns ALLOW (caller may dispatch directly), GATE (caller
        must collect approvals), or DENY (forbidden — caller refuses).

        Auditing is the caller's job; this method is intentionally
        side-effect-free so it can be invoked anywhere without
        polluting the audit chain. Wrap with a logging caller for
        full-trail decisions.
        """
        params = params or {}
        action = (action or "").strip()
        # Autonomy audit F19 — periodic runtime tamper-detection on
        # safety-critical sealed scalars.
        self._runtime_reverify()
        # Wiring audit Pass 3 (F6.8) — fail-closed if the reverify
        # itself failed (couldn't reload sealed config from disk).
        if self._reverify_failed:
            return CheckResult(
                verdict=Verdict.DENY,
                reason="constitution sealed-config reverify failed; "
                       "refusing all actions until next successful reload",
                rule_id="reverify_failed_fail_closed",
            )
        if not action:
            return CheckResult(
                verdict=Verdict.DENY, reason="empty action",
                rule_id="empty_action",
            )

        # 1) Forbidden list — short-circuit.
        for entry in self._sealed.constitution.get("forbidden_actions", []):
            if entry.get("action") == action:
                return CheckResult(
                    verdict=Verdict.DENY,
                    reason=str(entry.get("reason", "forbidden by constitution")),
                    rule_id=f"forbidden:{action}",
                    threats_addressed=tuple(entry.get("threats_addressed", ())),
                )

        # 1.5) TT&C audit C-5 — projected post-state must not match a
        # forbidden physical end-state.  Closes the chained-allowed
        # action bypass: an attacker cannot compose three individually
        # allowed commands into ``cabin_pressure_kpa = 0 + crew_present``.
        projected = params.get("_projected_state")
        if projected:
            post = self.check_postconditions(projected)
            if post is not None:
                return post

        # 2) Trust-tier rule for safety-critical actions. The
        # constitution enumerates safety-critical actions implicitly
        # via the gated_actions list — anything that needs operator
        # approval is by definition safety-critical.
        gated = self.gated_rule(action)
        rules = self._sealed.constitution.get("trust_tier_rules", {})
        min_tier_safety = int(rules.get("min_tier_for_safety_critical", 3))
        min_tier_resource = int(rules.get("min_tier_for_resource_consumption", 2))
        if gated and trust_tier < min_tier_safety:
            return CheckResult(
                verdict=Verdict.DENY,
                reason=(
                    f"action '{action}' requires trust tier ≥ {min_tier_safety}; "
                    f"caller is tier {int(trust_tier)} ({trust_tier.name})"
                ),
                rule_id=f"trust_tier:{action}",
            )

        # 3) Resource consumption pre-check (without consuming).
        resource_qty = params.get("_resource_qty")  # caller-supplied
        resource_id = params.get("_resource_id")
        if resource_id and resource_qty is not None:
            # Autonomy audit F18 — refuse non-finite / negative qty so a
            # NaN sensor sample cannot poison the sliding-window total.
            if not _is_finite_nonneg(resource_qty):
                return CheckResult(
                    verdict=Verdict.DENY,
                    reason=(
                        f"resource_qty must be finite and non-negative; "
                        f"got {resource_qty!r}"
                    ),
                    rule_id=f"resource_qty_invalid:{resource_id}",
                )
            r = self.resource_rule(str(resource_id))
            if r is None:
                # Unknown resource — allow but log.
                logger.warning("constitution.unknown_resource",
                               action=action, resource=resource_id)
            else:
                if trust_tier < min_tier_resource:
                    return CheckResult(
                        verdict=Verdict.DENY,
                        reason=(
                            f"resource consumption needs trust tier ≥ "
                            f"{min_tier_resource}"
                        ),
                        rule_id=f"trust_tier_resource:{resource_id}",
                    )
                with self._lock:
                    win = self._budgets.setdefault(
                        str(resource_id),
                        _ResourceWindow(int(r.get("window_seconds", 60))),
                    )
                    # Use monotonic-only consumption tracking.  Wall-clock
                    # is preserved on the sample tuples for forensic
                    # serialisation, but the comparison here is against
                    # ``time.time()`` for backwards-compat with the
                    # sealed sample format; F4 fix migrates the gating
                    # paths in resource_budget.py to monotonic.
                    projected = win.total(time.time()) + float(resource_qty)
                hard = float(r.get("hard_cap", float("inf")))
                soft = float(r.get("soft_cap", float("inf")))
                if projected > hard:
                    return CheckResult(
                        verdict=Verdict.DENY,
                        reason=(
                            f"would exceed hard cap on '{resource_id}': "
                            f"projected={projected:.3f} > hard={hard:.3f}"
                        ),
                        rule_id=f"resource_hard:{resource_id}",
                    )
                if projected > soft:
                    # Soft cap → gate on operator approval (two-person).
                    return CheckResult(
                        verdict=Verdict.GATE,
                        reason=(
                            f"would cross soft cap on '{resource_id}': "
                            f"projected={projected:.3f} > soft={soft:.3f}"
                        ),
                        rule_id=f"resource_soft:{resource_id}",
                        operator_approvals_required=2,
                        cooling_off_seconds=30,
                    )

        # 4) Gated rule — return GATE with the rule's terms.
        if gated:
            return CheckResult(
                verdict=Verdict.GATE,
                reason=str(gated.get("reason", "operator approval required")),
                rule_id=f"gated:{action}",
                operator_approvals_required=int(
                    gated.get("operator_approvals_required", 1)),
                cooling_off_seconds=int(gated.get("cooling_off_seconds", 0)),
                undo_window_seconds=int(gated.get("undo_window_seconds", 0)),
                threats_addressed=tuple(gated.get("threats_addressed", ())),
            )

        # 5) Default-DENY when the sealed constitution publishes an
        # explicit ``allowed_actions`` allow-list (autonomy audit F1).
        # Existing test fixtures that omit the list retain the legacy
        # default-ALLOW behaviour with a structured warning so the
        # operator can spot the soft mode in production.
        # SealedContent ``_deep_freeze`` turns the JSON list into a
        # tuple of MappingProxyType — accept either form.
        allowed = self._sealed.constitution.get("allowed_actions")
        if isinstance(allowed, (list, tuple)) and allowed:
            allowed_set = {
                str(entry.get("action") if isinstance(entry, Mapping) else entry)
                for entry in allowed
            }
            if action in allowed_set:
                return CheckResult(
                    verdict=Verdict.ALLOW,
                    reason="action explicitly allowed",
                    rule_id=f"allowed:{action}",
                )
            return CheckResult(
                verdict=Verdict.DENY,
                reason=(
                    f"action '{action}' is not on the sealed allowed_actions "
                    "list; default-DENY"
                ),
                rule_id="default_deny",
            )
        logger.warning(
            "constitution.default_allow_active",
            note="sealed constitution has no allowed_actions list; "
                 "running in legacy default-ALLOW mode",
            action=action,
        )
        return CheckResult(
            verdict=Verdict.ALLOW, reason="not gated", rule_id="default_allow_legacy",
        )

    # ── Resource consumption recording ──────────────────────────

    def consume_resource(self, resource_id: str, qty: float) -> bool:
        """Record consumption of a budgeted resource.

        Call this only AFTER an action has been ALLOWed and dispatched.
        Returns True if the consumption fit under the hard cap; False
        if it pushed the total over (the action should be reverted —
        caller's responsibility).
        """
        rule = self.resource_rule(resource_id)
        if rule is None:
            return True
        with self._lock:
            win = self._budgets.setdefault(
                resource_id,
                _ResourceWindow(int(rule.get("window_seconds", 60))),
            )
            total = win.consume(float(qty), time.time())
        hard = float(rule.get("hard_cap", float("inf")))
        if total > hard:
            logger.error("constitution.resource_overrun",
                         resource=resource_id, total=total, hard=hard)
            return False
        return True

    def current_consumption(self, resource_id: str) -> float:
        with self._lock:
            win = self._budgets.get(resource_id)
            return win.total(time.time()) if win is not None else 0.0


# Process-wide singleton accessor.
_INSTANCE: Constitution | None = None
_INSTANCE_LOCK = threading.Lock()


def get_constitution() -> Constitution:
    """Lazy singleton."""
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = Constitution()
    return _INSTANCE


def reset_for_test() -> None:
    """Drop the singleton — only for tests."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = None
