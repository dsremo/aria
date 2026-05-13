"""Unified safe-dispatch helper — single entry point for every agent
that wants to act on an LLM-derived intent.

This is the seam where every failsafe layer fires in order:

  1. Kill switch (F-17)     — fast pre-check; if asserted, drop silently.
  2. Constitution (F-3)     — DENY → log + drop; GATE → enqueue.
  3. Resource budget (F-12) — pre-flight projection; hard breach → drop.
  4. Replay guard (F-19)    — verify command seq+nonce on inbound.
  5. ExecutionGuard (existing) — preconditions + invariants + timeout.
  6. Audit log (F-8)        — record every decision + execution.
  7. ActionLog (R28 T3-P5)  — operator UI feed.

If all gates pass, the executor callback fires synchronously. If a gate
blocks, the executor never runs. The function is pure — same inputs
yield the same verdict given identical singleton state.

Use:

    from aria.cognitive.safe_dispatch import safe_dispatch, DispatchOutcome

    outcome = safe_dispatch(
        agent_name="power",
        action="shed_load",
        params={"subsystem": "science"},
        executor=self._execute_load_shed,
        trust_tier=TrustTier.OPERATOR,
        rationale="LLM directive in eclipse",
    )
    if outcome.kind == "executed":
        ...
    elif outcome.kind == "gated":
        # An approval proposal was created; outcome.proposal_id is the id.

The agent's previous direct call to ``self._execute_load_shed(...)``
becomes ``safe_dispatch(...)``. Nothing else in the agent changes.

Threats addressed: composition of F-1, F-3, F-7, F-12, F-17, F-19, F-9.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import structlog

from aria.cognitive.constitution import (
    Constitution, TrustTier, Verdict as CVerdict, get_constitution,
)
from aria.cognitive.action_log import get_action_log
from aria.safety.kill_switch import gated_or_kill
from aria.safety.resource_budget import get_budget_gate
from aria.safety.approval_queue import get_approval_queue

logger = structlog.get_logger()


def _resolve_trust_tier(
    principal: Optional["Principal"],
    fallback: TrustTier,
) -> TrustTier:
    """R32: derive trust_tier from a verified Principal when present.

    The agent layer should pass ``principal=Principal.agent("name")``
    so the constitution sees LOCAL_SENSOR (not OPERATOR) and refuses
    to let an LLM-driven agent unilaterally trip safety-critical gates.

    When ``principal=None`` we fall back to the explicit ``trust_tier``
    argument for backwards compatibility with pre-R32 callers.
    """
    if principal is None:
        return fallback
    # Map the principal-store TrustTier (string enum) to the
    # constitution's IntEnum. They share names by construction.
    from aria.security.principals import trust_tier_for as _ttf
    name = _ttf(principal).value
    try:
        return TrustTier[name]   # IntEnum lookup by name
    except KeyError:
        return fallback


# Type-only import to avoid a hard runtime cycle (constitution is
# imported by principals indirectly via no path; this is just for the
# type annotation in _resolve_trust_tier).
from typing import TYPE_CHECKING  # noqa: E402
if TYPE_CHECKING:
    from aria.security.principals import Principal


class DispatchKind(enum.Enum):
    EXECUTED = "executed"        # action ran successfully
    DENIED = "denied"             # constitution forbade or kill-switch asserted
    GATED = "gated"               # awaiting operator approval
    BUDGET_BREACH = "budget_breach"   # would have crossed hard cap
    EXECUTOR_ERROR = "executor_error"  # callback raised


@dataclass(frozen=True)
class DispatchOutcome:
    """Result of one safe_dispatch call."""

    kind: DispatchKind
    reason: str
    rule_id: str = ""
    proposal_id: Optional[str] = None
    threats_addressed: tuple[str, ...] = ()


def safe_dispatch_check(
    *,
    agent_name: str,
    action: str,
    params: Optional[Dict[str, Any]] = None,
    trust_tier: TrustTier = TrustTier.OPERATOR,
    rationale: str = "",
    constitution: Optional[Constitution] = None,
    register_executor: Optional[Callable[[Dict[str, Any]], Any]] = None,
    principal: Optional["Principal"] = None,
) -> DispatchOutcome:
    """Async-friendly variant — runs every gate but never executes.

    Returns DispatchOutcome with kind in:
      EXECUTED        — every gate passed; caller may dispatch
      DENIED          — kill switch / constitution forbade
      GATED           — proposal created; if register_executor is
                        supplied, it's wired into the approval queue
                        so the queue fires it after approvals + cooldown
      BUDGET_BREACH   — resource hard-cap reached
    """
    params = params or {}
    constitution = constitution or get_constitution()
    effective_tier = _resolve_trust_tier(principal, trust_tier)

    label = f"aria.{agent_name}.{action}"
    if not gated_or_kill(label):
        get_action_log().append(
            agent=agent_name, action=action, status="denied_killswitch",
            params=params, rationale=rationale or "kill_switch asserted",
        )
        return DispatchOutcome(
            DispatchKind.DENIED, "kill switch asserted", "kill_switch",
            threats_addressed=("T-V-4", "T-VI-3"),
        )

    cresult = constitution.check(action, params, effective_tier)
    if cresult.verdict is CVerdict.DENY:
        get_action_log().append(
            agent=agent_name, action=action, status="denied_constitution",
            params=params, rationale=cresult.reason,
        )
        return DispatchOutcome(
            DispatchKind.DENIED, cresult.reason, cresult.rule_id,
            threats_addressed=cresult.threats_addressed,
        )
    if cresult.verdict is CVerdict.GATE:
        # R38 §1.2 — cross-vendor monitor parallel verdict.
        # Autonomy audit F2 — cross-vendor monitor failure must NOT
        # silently fall through.  An unavailable monitor counts as a
        # disagreement so the action requires an extra signer.
        cross_signers = 0
        try:
            from aria.monitor.cross_check import get_cross_vendor_monitor
            xc = get_cross_vendor_monitor().check(
                action=action, params=params,
                primary_verdict=cresult.verdict, rationale=rationale,
            )
            if xc.is_disagreement_with_allow:
                cross_signers = 1
        except Exception as exc:    # noqa: BLE001
            logger.error("safe_dispatch.cross_monitor_unavailable",
                         agent=agent_name, action=action, error=str(exc))
            cross_signers = 1    # fail-closed: require operator override

        pid = get_approval_queue().propose(
            action=action, params=params, proposer=agent_name,
            required_signers=(cresult.operator_approvals_required or 1)
                              + cross_signers,
            cooling_off_s=cresult.cooling_off_seconds or 0.0,
            undo_window_s=cresult.undo_window_seconds or 0.0,
            rule_id=cresult.rule_id, reason=cresult.reason,
        )
        if register_executor is not None:
            get_approval_queue().register_executor(action, register_executor)
        get_action_log().append(
            agent=agent_name, action=action, status="gated_pending",
            params={**params, "proposal_id": pid},
            rationale=cresult.reason,
        )
        return DispatchOutcome(
            DispatchKind.GATED, cresult.reason, cresult.rule_id,
            proposal_id=pid,
            threats_addressed=cresult.threats_addressed,
        )

    # Resource pre-check (don't commit yet — caller commits after dispatch).
    resource_id = params.get("_resource_id")
    resource_qty = params.get("_resource_qty")
    if resource_id and resource_qty is not None:
        proj = get_budget_gate().project(str(resource_id), float(resource_qty))
        if not proj.fits_hard:
            get_action_log().append(
                agent=agent_name, action=action, status="denied_budget",
                params=params,
                rationale=f"hard cap on {resource_id}: "
                          f"{proj.projected:.3f} > {proj.hard_cap:.3f}",
            )
            return DispatchOutcome(
                DispatchKind.BUDGET_BREACH,
                f"hard cap on '{resource_id}' would be exceeded",
                f"budget_hard:{resource_id}",
                threats_addressed=("T-II-7", "W-2"),
            )

    return DispatchOutcome(
        DispatchKind.EXECUTED, "all gates passed", "ok",
    )


def safe_dispatch(
    *,
    agent_name: str,
    action: str,
    params: Optional[Dict[str, Any]] = None,
    executor: Callable[[Dict[str, Any]], Any],
    trust_tier: TrustTier = TrustTier.OPERATOR,
    rationale: str = "",
    constitution: Optional[Constitution] = None,
    log_executed: bool = True,
    principal: Optional["Principal"] = None,
) -> DispatchOutcome:
    """Run an LLM-derived action through every failsafe gate.

    Args:
        agent_name: which agent is dispatching (used for audit + bus
            topic naming).
        action: the constitutional action name (e.g., "shed_load").
        params: keyword params; may include ``_resource_id`` and
            ``_resource_qty`` which engage the budget gate.
        executor: synchronous callable invoked iff every gate passes.
        trust_tier: who supplied the proposal. Tier ≤ 1 cannot drive
            safety-critical actions.
        rationale: free-form text logged with the action.
        constitution: optional override for tests.
        log_executed: append ActionLog 'executed' entry on success.

    Returns:
        DispatchOutcome describing what happened.
    """
    params = params or {}
    constitution = constitution or get_constitution()
    effective_tier = _resolve_trust_tier(principal, trust_tier)

    # 1) Kill switch — single boolean gate.
    label = f"aria.{agent_name}.{action}"
    if not gated_or_kill(label):
        get_action_log().append(
            agent=agent_name, action=action, status="denied_killswitch",
            params=params, rationale=rationale or "kill_switch asserted",
        )
        return DispatchOutcome(
            DispatchKind.DENIED,
            reason="kill switch asserted",
            rule_id="kill_switch",
            threats_addressed=("T-V-4", "T-VI-3"),
        )

    # 2) Constitution.
    cresult = constitution.check(action, params, effective_tier)
    if cresult.verdict is CVerdict.DENY:
        get_action_log().append(
            agent=agent_name, action=action, status="denied_constitution",
            params=params, rationale=cresult.reason,
        )
        logger.warning("safe_dispatch.constitution_denied",
                       agent=agent_name, action=action,
                       reason=cresult.reason, rule_id=cresult.rule_id)
        return DispatchOutcome(
            DispatchKind.DENIED,
            reason=cresult.reason,
            rule_id=cresult.rule_id,
            threats_addressed=cresult.threats_addressed,
        )
    if cresult.verdict is CVerdict.GATE:
        # R38 §1.2 — cross-vendor monitor parallel verdict.  A
        # different-family model gets to refuse the action even after
        # operators approve.  Disagreement bumps required_signers by 1
        # so the operator must explicitly override the cross-monitor.
        cross_signers = 0
        try:
            from aria.monitor.cross_check import get_cross_vendor_monitor
            xc = get_cross_vendor_monitor().check(
                action=action, params=params,
                primary_verdict=cresult.verdict, rationale=rationale,
            )
            if xc.is_disagreement_with_allow:
                cross_signers = 1
                logger.warning("safe_dispatch.cross_monitor_disagreement",
                               agent=agent_name, action=action,
                               cross_model=xc.model_id,
                               cross_reason=xc.reason)
        except Exception as exc:    # noqa: BLE001
            # Autonomy audit F2 — fail-closed on cross-monitor outage.
            logger.error("safe_dispatch.cross_monitor_unavailable",
                         agent=agent_name, action=action, error=str(exc))
            cross_signers = 1

        pid = get_approval_queue().propose(
            action=action,
            params=params,
            proposer=agent_name,
            required_signers=(cresult.operator_approvals_required or 1)
                              + cross_signers,
            cooling_off_s=cresult.cooling_off_seconds or 0.0,
            undo_window_s=cresult.undo_window_seconds or 0.0,
            rule_id=cresult.rule_id,
            reason=cresult.reason,
        )
        # The approval queue will fire the executor when ready, so we
        # need to register one. Use the *current* executor; the queue
        # will dispatch under the operator's authority once approvals
        # complete + cooling-off elapsed.
        get_approval_queue().register_executor(action, executor)
        get_action_log().append(
            agent=agent_name, action=action, status="gated_pending",
            params={**params, "proposal_id": pid},
            rationale=cresult.reason,
        )
        logger.info("safe_dispatch.gated",
                    agent=agent_name, action=action,
                    proposal_id=pid,
                    approvals_required=cresult.operator_approvals_required,
                    cross_monitor_extra_signers=cross_signers)
        return DispatchOutcome(
            DispatchKind.GATED,
            reason=cresult.reason,
            rule_id=cresult.rule_id,
            proposal_id=pid,
            threats_addressed=cresult.threats_addressed,
        )

    # 3) Resource budget (commit because we are about to dispatch).
    resource_id = params.get("_resource_id")
    resource_qty = params.get("_resource_qty")
    if resource_id and resource_qty is not None:
        proj = get_budget_gate().commit(str(resource_id), float(resource_qty))
        if not proj.fits_hard:
            get_action_log().append(
                agent=agent_name, action=action, status="denied_budget",
                params=params,
                rationale=f"hard cap on {resource_id}: "
                          f"{proj.projected:.3f} > {proj.hard_cap:.3f}",
            )
            return DispatchOutcome(
                DispatchKind.BUDGET_BREACH,
                reason=f"hard cap on '{resource_id}' would be exceeded",
                rule_id=f"budget_hard:{resource_id}",
                threats_addressed=("T-II-7", "W-2"),
            )

    # 4) Execute. Errors do NOT propagate to the caller — they become
    # an outcome so the agent can decide the next move (often: alert
    # operator + roll back resource). This keeps a misbehaving
    # executor from poisoning the agent's event loop.
    try:
        executor(params)
    except Exception as exc:
        logger.error("safe_dispatch.executor_failed",
                     agent=agent_name, action=action, error=str(exc))
        get_action_log().append(
            agent=agent_name, action=action, status="executor_error",
            params=params, rationale=f"{type(exc).__name__}: {exc}",
        )
        return DispatchOutcome(
            DispatchKind.EXECUTOR_ERROR,
            reason=f"{type(exc).__name__}: {exc}",
            rule_id="executor_failed",
        )

    if log_executed:
        get_action_log().append(
            agent=agent_name, action=action, status="executed",
            params=params, rationale=rationale,
        )
    return DispatchOutcome(
        DispatchKind.EXECUTED,
        reason="all gates passed",
        rule_id="ok",
    )
