"""Operator approval queue — F-9 of FAILSAFE_ARCHITECTURE.md.

A gated action (constitution.Verdict.GATE) does not run directly.
Instead, the agent calls ``ApprovalQueue.propose(action, params,
required_signers, cooling_off_s, undo_window_s)`` and receives a
proposal id. The proposal lives until it has been:

  - approved by the required number of *distinct* operators,
  - past the cooling-off window since the *last* approval,
  - within the lifetime (default 5 minutes) — past that it expires,

at which point the queue invokes the registered execute callback.
After execute, the proposal enters an "undo window" during which an
operator can call ``revert(id)`` to fire a registered revert callback.

Crucial properties:
  * Two distinct operators required (anti-collusion best-effort: the
    queue records *who* signed; the operator console adds an off-shift
    flag).
  * Cooling-off applies after the *last* signature, not the first —
    defeats rapid-fire double-tap rubber stamping.
  * The signing identity flows through ``security/auth.py``; the queue
    does not invent its own crypto.
  * Each state transition publishes an audit-log entry.
  * The queue itself never decides whether a proposal is allowed —
    the constitution does that. The queue handles the *workflow*.

Threats addressed:
  T-IV-1 jealous operator       (two-person)
  T-IV-2 coerced operator       (two-person + stress recall)
  T-IV-3 operator typo          (cooling-off + undo window)
  T-IV-4 rubber-stamp HITL      (cooling-off bound + recall question)
  T-IV-5 single-person catastrophe (two-person)
  T-VII-2 stale-state approval (proposal expires after 5 min)
"""

from __future__ import annotations

import concurrent.futures
import contextvars
import enum
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

# Wiring audit Pass 1 (F4.2) — bounded executor pool so a hung
# downstream cannot wedge the approval-queue background loop.
# Executors are wrapped in a Future and time out at this deadline;
# the proposal is marked EXPIRED and the loop continues.
_EXECUTOR_TIMEOUT_S = 30.0
_EXECUTOR_POOL_SIZE = 4

import structlog

logger = structlog.get_logger()


class ProposalState(enum.Enum):
    PENDING = "pending"             # awaiting first / next signature
    READY = "ready"                  # has all signatures, in cooling-off
    EXECUTING = "executing"          # cooling-off elapsed, callback firing
    EXECUTED = "executed"            # ran; in undo window
    REVERTED = "reverted"            # operator pulled the undo trigger
    REVERT_FAILED = "revert_failed"  # autonomy F32 — reverter raised; manual
    EXPIRED = "expired"              # lifetime exceeded without approvals
    VETOED = "vetoed"                # operator declined


@dataclass
class _Approval:
    operator_id: str
    ts: float                      # wall-clock for forensics
    ts_monotonic: float            # autonomy F4 — monotonic for cooling-off
    recall_answer_ok: bool
    off_shift: bool
    pubkey_fingerprint: str = ""   # autonomy F15 — anti-collusion key id


@dataclass
class Proposal:
    """One pending gated action."""

    proposal_id: str
    action: str
    params: Dict[str, Any]
    proposer: str
    proposed_at: float
    required_signers: int
    cooling_off_s: float
    undo_window_s: float
    lifetime_s: float
    rule_id: str
    reason: str
    state: ProposalState = ProposalState.PENDING
    approvals: List[_Approval] = field(default_factory=list)
    veto: Optional[Dict[str, Any]] = None
    executed_at: float = 0.0
    reverted_at: float = 0.0
    # R35: trace_id captured at propose() time so the eventual
    # executor — which fires AFTER cooling-off in a different async
    # task — can be linked back to the original detection event.
    trace_id: str = ""
    # Wiring audit Pass 1 (F11.2) — anchor for cooling-off measured
    # against the original proposal time, not the latest approval.
    # Declared on the dataclass so a future @dataclass(slots=True)
    # refactor cannot silently drop the attribute.
    _first_proposed_monotonic: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "action": self.action,
            "params": dict(self.params),
            "proposer": self.proposer,
            "proposed_at": self.proposed_at,
            "required_signers": self.required_signers,
            "cooling_off_s": self.cooling_off_s,
            "undo_window_s": self.undo_window_s,
            "lifetime_s": self.lifetime_s,
            "rule_id": self.rule_id,
            "reason": self.reason,
            "state": self.state.value,
            "approvals_count": len(self.approvals),
            "approvers": [a.operator_id for a in self.approvals],
            "veto": dict(self.veto) if self.veto else None,
            "executed_at": self.executed_at,
            "reverted_at": self.reverted_at,
        }


class ApprovalQueue:
    """Process-wide approval workflow.

    The execute and revert callbacks are registered per-action. The
    agent calling propose() does not pass the callback — the queue
    routes by action name. This keeps the agent → queue interface
    free of closures that an attacker could redirect.
    """

    DEFAULT_LIFETIME_S = 300.0   # 5 min lifetime
    # Autonomy audit F31 — terminal-state proposals are GC'd after this
    # many seconds past their final transition.  Keeps memory bounded.
    TERMINAL_GC_S = 3600.0       # keep last hour of terminal records
    MAX_PROPOSALS = 10_000        # absolute cap

    # TT&C audit C-8 — content-hash repropose lockout window.  An
    # attacker who learnt to spam ``propose() → approve() → withdraw``
    # cycles to keep a cooling-off timer fresh would otherwise win.  We
    # remember the *first* proposed_at for any (action, sorted-params)
    # content-hash within ``REPROPOSE_LOCK_S`` and inherit it on every
    # subsequent repropose; cooling-off is measured against the first
    # propose, not the most recent.
    REPROPOSE_LOCK_S = 3600.0    # s — 1-hour content lockout

    def __init__(
        self,
        publish_fn: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        self._publish = publish_fn or (lambda topic, payload: None)
        self._proposals: Dict[str, Proposal] = {}
        self._executors: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._reverters: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._lock = threading.Lock()
        # Background expiry thread — bumps state to EXPIRED for
        # proposals past their lifetime.
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # TT&C audit C-8 — content-hash → (first_proposed_at, first_proposed_monotonic).
        self._first_proposed: Dict[str, tuple[float, float]] = {}
        # Wiring audit Pass 1 (F4.2) — bounded thread pool for
        # executor calls so a single hung executor cannot wedge the
        # try_execute / expire_old / gc_terminal loop.
        self._executor_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=_EXECUTOR_POOL_SIZE,
            thread_name_prefix="approval-exec",
        )

    # ── Registration ──────────────────────────────────────────

    def register_executor(
        self,
        action: str,
        fn: Callable[[Dict[str, Any]], None],
    ) -> None:
        with self._lock:
            self._executors[action] = fn
        logger.info("approval_queue.executor_registered", action=action)

    def register_reverter(
        self,
        action: str,
        fn: Callable[[Dict[str, Any]], None],
    ) -> None:
        with self._lock:
            self._reverters[action] = fn

    # ── Workflow ──────────────────────────────────────────────

    def propose(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        proposer: str = "",
        *,
        required_signers: int = 2,
        cooling_off_s: float = 30.0,
        undo_window_s: float = 60.0,
        lifetime_s: Optional[float] = None,
        rule_id: str = "",
        reason: str = "",
    ) -> str:
        """Create a proposal. Returns proposal_id."""
        pid = uuid.uuid4().hex[:16]
        # R35: capture the active trace_id so the executor (which fires
        # later, after cooling-off, on a different async task) can be
        # attributed back to the originating detection event.
        try:
            from aria.security.trace_context import current_trace_id
            captured_trace = current_trace_id(mint_if_absent=False)
        except Exception:
            captured_trace = ""

        normalised_params = dict(params or {})
        # TT&C audit C-8 — compute a stable content hash from
        # (action, normalised params).  Exclude transient bookkeeping
        # keys that the executor injects at fire-time (``_approvers``,
        # ``_proposal_id``, ``_trace_id``).
        content_hash = self._content_hash(action, normalised_params)
        wall_now = time.time()
        mono_now = time.monotonic()
        with self._lock:
            first = self._first_proposed.get(content_hash)
            if first is not None:
                first_wall, first_mono = first
                if mono_now - first_mono > self.REPROPOSE_LOCK_S:
                    # Lockout expired; this is a genuinely new proposal.
                    first_wall, first_mono = wall_now, mono_now
                    self._first_proposed[content_hash] = (first_wall, first_mono)
            else:
                first_wall, first_mono = wall_now, mono_now
                self._first_proposed[content_hash] = (first_wall, first_mono)

        p = Proposal(
            proposal_id=pid,
            action=action,
            params=normalised_params,
            proposer=proposer,
            # Inherit the original wall-clock proposed_at so the audit
            # log shows the *true* age of the action chain.
            proposed_at=first_wall,
            required_signers=max(1, int(required_signers)),
            cooling_off_s=max(0.0, float(cooling_off_s)),
            undo_window_s=max(0.0, float(undo_window_s)),
            lifetime_s=max(60.0, float(lifetime_s or self.DEFAULT_LIFETIME_S)),
            rule_id=rule_id,
            reason=reason,
            trace_id=captured_trace,
        )
        # Attach the original-monotonic anchor so try_execute can
        # measure cooling-off against it instead of "last approval".
        # Wiring audit Pass 1 (F11.2): the field is now declared on
        # the dataclass, so this assignment is a public-attribute set.
        p._first_proposed_monotonic = first_mono
        with self._lock:
            self._proposals[pid] = p
        self._publish("aria.approval.proposed", p.to_dict())
        logger.info("approval_queue.proposed",
                    proposal_id=pid, action=action,
                    required=required_signers,
                    cooling_off_s=cooling_off_s,
                    content_hash=content_hash[:12])
        return pid

    @staticmethod
    def _content_hash(action: str, params: Mapping[str, Any]) -> str:
        """Stable hash over (action, params).  TT&C audit C-8."""
        import hashlib
        import json as _json
        excluded = {"_approvers", "_proposal_id", "_trace_id"}
        sanitised = {
            key: value for key, value in params.items()
            if key not in excluded
        }
        canonical = _json.dumps(
            {"action": action, "params": sanitised},
            sort_keys=True, separators=(",", ":"), default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def approve(
        self,
        proposal_id: str,
        operator_id: str,
        *,
        recall_answer_ok: bool,
        off_shift: bool = False,
        pubkey_fingerprint: str = "",
    ) -> Dict[str, Any]:
        """Record one operator's signature.

        Autonomy audit F14 — ``recall_answer_ok`` is now a REQUIRED
        keyword argument; callers must explicitly populate it from the
        operator's recall answer.  No fail-open default.

        Autonomy audit F15 — ``pubkey_fingerprint`` should be the
        operator's hardware-key fingerprint (provided by the auth
        layer).  When two distinct ``operator_id`` strings share the
        same fingerprint we refuse the second signer so a single
        physical operator cannot satisfy the two-person rule with
        two principal IDs.
        """
        with self._lock:
            p = self._proposals.get(proposal_id)
            if p is None:
                return {"ok": False, "reason": "unknown proposal"}
            if p.state is not ProposalState.PENDING:
                return {"ok": False, "reason": f"proposal in state {p.state.value}"}
            # Anti-collusion v1: same operator_id can't sign twice.
            if any(a.operator_id == operator_id for a in p.approvals):
                return {"ok": False, "reason": "operator already approved"}
            # Autonomy audit F15 — anti-collusion v2: same hardware
            # fingerprint can't sign twice even with different IDs.
            if pubkey_fingerprint and any(
                a.pubkey_fingerprint == pubkey_fingerprint
                for a in p.approvals
            ):
                return {
                    "ok": False,
                    "reason": "operator already approved (different id, same key)",
                }
            if not recall_answer_ok:
                return {"ok": False, "reason": "recall question failed"}
            now_w = time.time()
            now_m = time.monotonic()
            p.approvals.append(_Approval(
                operator_id=operator_id,
                ts=now_w,
                ts_monotonic=now_m,
                recall_answer_ok=recall_answer_ok,
                off_shift=off_shift,
                pubkey_fingerprint=pubkey_fingerprint,
            ))
            if len(p.approvals) >= p.required_signers:
                p.state = ProposalState.READY
                logger.info("approval_queue.ready",
                            proposal_id=proposal_id,
                            approvers=[a.operator_id for a in p.approvals])
        self._publish("aria.approval.signed", {
            "proposal_id": proposal_id, "operator_id": operator_id,
            "off_shift": off_shift,
        })
        # Try to fire if cooling-off already elapsed by the time the
        # last signature arrives (cooling_off=0 case).
        self.try_execute()
        return {"ok": True, "state": p.state.value}

    def veto(
        self,
        proposal_id: str,
        operator_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            p = self._proposals.get(proposal_id)
            if p is None:
                return {"ok": False, "reason": "unknown proposal"}
            if p.state in (ProposalState.EXECUTED, ProposalState.REVERTED,
                           ProposalState.EXPIRED, ProposalState.VETOED):
                return {"ok": False, "reason": f"proposal in state {p.state.value}"}
            p.state = ProposalState.VETOED
            p.veto = {"operator_id": operator_id, "ts": time.time(),
                      "reason": reason}
        self._publish("aria.approval.vetoed", {
            "proposal_id": proposal_id, "operator_id": operator_id,
            "reason": reason,
        })
        logger.warning("approval_queue.vetoed",
                       proposal_id=proposal_id, operator_id=operator_id)
        return {"ok": True}

    def revert(
        self,
        proposal_id: str,
        operator_id: str,
    ) -> Dict[str, Any]:
        """Operator pulls the undo trigger within the undo window."""
        with self._lock:
            p = self._proposals.get(proposal_id)
            if p is None:
                return {"ok": False, "reason": "unknown proposal"}
            if p.state is not ProposalState.EXECUTED:
                return {"ok": False, "reason": f"not executed (state={p.state.value})"}
            if time.time() - p.executed_at > p.undo_window_s:
                return {"ok": False, "reason": "undo window elapsed"}
            reverter = self._reverters.get(p.action)
            p.state = ProposalState.REVERTED
            p.reverted_at = time.time()
        if reverter is not None:
            try:
                reverter(p.params)
            except Exception as exc:
                logger.error("approval_queue.revert_failed",
                             proposal_id=proposal_id, error=str(exc))
                # Autonomy audit F32 — keep the failure observable.
                with self._lock:
                    p.state = ProposalState.REVERT_FAILED
                self._publish("aria.approval.revert_failed", {
                    "proposal_id": proposal_id, "operator_id": operator_id,
                    "error_type": type(exc).__name__,
                })
                return {"ok": False, "reason": "reverter error",
                        "state": "revert_failed"}
        self._publish("aria.approval.reverted", {
            "proposal_id": proposal_id, "operator_id": operator_id,
        })
        return {"ok": True}

    def try_execute(self) -> List[str]:
        """Fire any READY proposals whose cooling-off has elapsed.

        Called periodically by the background thread *and* immediately
        after each approve(). Returns list of proposal_ids fired.

        Autonomy audit F4/F13 — cooling-off is measured against the
        monotonic clock so a forward NTP set-step cannot bypass it.

        R33: at fire time we inject ``_approvers`` (ordered list of
        operator_ids, oldest first) and ``_proposal_id`` into the
        params dict. Admin executors (security/admin.py) read these
        to attribute the principal-delta record to the actor +
        co-signer that completed the two-person flow.
        """
        fired: List[str] = []
        now_m = time.monotonic()
        with self._lock:
            ready = [p for p in self._proposals.values()
                     if p.state is ProposalState.READY]
        for p in ready:
            last_approval_m = max(a.ts_monotonic for a in p.approvals)
            if (now_m - last_approval_m) < p.cooling_off_s:
                continue
            executor = self._executors.get(p.action)
            with self._lock:
                p.state = ProposalState.EXECUTING
            if executor is None:
                logger.error("approval_queue.no_executor",
                             proposal_id=p.proposal_id, action=p.action)
                with self._lock:
                    p.state = ProposalState.EXPIRED
                continue
            fire_params = {
                **p.params,
                "_approvers": [a.operator_id for a in
                               sorted(p.approvals, key=lambda a: a.ts)],
                "_proposal_id": p.proposal_id,
                "_trace_id": p.trace_id,
            }
            # R35: restore the original trace_id into the ContextVar
            # for the duration of the executor call so downstream audit
            # / bus events propagate the trace back to the originator.
            trace_token = None
            if p.trace_id:
                try:
                    from aria.security.trace_context import set_trace_id
                    trace_token = set_trace_id(p.trace_id)
                except Exception:
                    trace_token = None
            # Wiring audit Pass 1 (F4.2) — submit to the bounded pool
            # and wait with a timeout so a hung executor cannot freeze
            # the queue's background loop. A timed-out proposal is
            # marked EXPIRED with a structured warning so operators
            # see the dropped action, not a silent stall.
            #
            # ContextVars (R35 trace_id) do not propagate into pool
            # workers automatically — we copy the current context so
            # the executor sees the same trace_id the calling thread
            # set above.
            ctx = contextvars.copy_context()
            future = self._executor_pool.submit(ctx.run, executor, fire_params)
            timed_out = False
            executor_exception: Optional[BaseException] = None
            try:
                future.result(timeout=_EXECUTOR_TIMEOUT_S)
            except concurrent.futures.TimeoutError:
                timed_out = True
                future.cancel()
            except Exception as exc:
                executor_exception = exc

            if timed_out or executor_exception is not None:
                if timed_out:
                    logger.error(
                        "approval_queue.executor_timeout",
                        proposal_id=p.proposal_id, action=p.action,
                        timeout_s=_EXECUTOR_TIMEOUT_S,
                    )
                else:
                    logger.error(
                        "approval_queue.executor_failed",
                        proposal_id=p.proposal_id,
                        error=str(executor_exception),
                    )
                with self._lock:
                    p.state = ProposalState.EXPIRED
                if trace_token is not None:
                    try:
                        from aria.security.trace_context import reset_trace_id
                        reset_trace_id(trace_token)
                    except Exception:
                        pass
                continue
            if trace_token is not None:
                try:
                    from aria.security.trace_context import reset_trace_id
                    reset_trace_id(trace_token)
                except Exception:
                    pass
            with self._lock:
                p.state = ProposalState.EXECUTED
                p.executed_at = time.time()
            fired.append(p.proposal_id)
            self._publish("aria.approval.executed", p.to_dict())
            logger.info("approval_queue.executed",
                        proposal_id=p.proposal_id, action=p.action)
        return fired

    def expire_old(self) -> List[str]:
        """Mark PENDING proposals past their lifetime as EXPIRED.

        Autonomy audit F4 — uses wall-clock here since ``proposed_at``
        is recorded as wall-clock; both sides shift together so a
        backward NTP step doesn't open a window, only forward steps
        expire pending proposals (which is the safe failure mode).
        """
        now = time.time()
        expired: List[str] = []
        with self._lock:
            for p in self._proposals.values():
                if p.state is ProposalState.PENDING and \
                        (now - p.proposed_at) > p.lifetime_s:
                    p.state = ProposalState.EXPIRED
                    expired.append(p.proposal_id)
        for pid in expired:
            self._publish("aria.approval.expired", {"proposal_id": pid})
            logger.info("approval_queue.expired", proposal_id=pid)
        return expired

    def gc_terminal(self) -> int:
        """Autonomy audit F31 — drop terminal-state proposals after
        ``TERMINAL_GC_S`` have elapsed since their last transition.
        Returns count dropped."""
        now = time.time()
        terminal = (
            ProposalState.EXECUTED, ProposalState.REVERTED,
            ProposalState.EXPIRED, ProposalState.VETOED,
            ProposalState.REVERT_FAILED,
        )
        with self._lock:
            drop = []
            for pid, p in self._proposals.items():
                if p.state not in terminal:
                    continue
                last_change = max(
                    p.executed_at or 0,
                    p.reverted_at or 0,
                    p.proposed_at or 0,
                    (p.veto or {}).get("ts", 0),
                )
                if last_change and (now - last_change) > self.TERMINAL_GC_S:
                    drop.append(pid)
            # Hard cap on total proposals (drop oldest by proposed_at).
            if len(self._proposals) > self.MAX_PROPOSALS:
                excess = len(self._proposals) - self.MAX_PROPOSALS
                oldest = sorted(self._proposals.items(),
                                key=lambda kv: kv[1].proposed_at)[:excess]
                drop.extend(pid for pid, _ in oldest)
            for pid in drop:
                self._proposals.pop(pid, None)
        return len(drop)

    def list_pending(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [p.to_dict() for p in self._proposals.values()
                    if p.state in (ProposalState.PENDING, ProposalState.READY,
                                   ProposalState.EXECUTED)]

    def get(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            p = self._proposals.get(proposal_id)
            return p.to_dict() if p else None

    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [p.to_dict() for p in self._proposals.values()]

    # ── Background ────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="approval-queue", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        # Wiring audit Pass 1 (F4.2) — release pool workers; pending
        # tasks are not waited on (they would extend shutdown beyond
        # the executor timeout we already enforced).
        self._executor_pool.shutdown(wait=False, cancel_futures=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.try_execute()
                self.expire_old()
                self.gc_terminal()
            except Exception as exc:    # noqa: BLE001
                logger.exception("approval_queue.loop_failed",
                                 error=str(exc))
            self._stop.wait(2.0)


_INSTANCE: Optional[ApprovalQueue] = None
_INSTANCE_LOCK = threading.Lock()


def get_approval_queue() -> ApprovalQueue:
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = ApprovalQueue()
    return _INSTANCE


def reset_for_test() -> None:
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = None
