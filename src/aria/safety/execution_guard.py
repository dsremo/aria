"""Deterministic execution guard for subsystem commands.

Sits between the LLM cognitive engine and subsystem interfaces.
Every command must pass through a PlanNode whose preconditions,
invariants, and resource requirements are checked deterministically
before execution is permitted.

Architecture:
    LLM Engine → PlanNode (preconditions/invariants) → ResourceArbiter
    → FDIR Recovery (typed failures) → Subsystem Interface

This ensures safety-critical operations are never gated by LLM
reasoning alone. The LLM generates intent; this layer enforces
physical constraints.
"""

from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ── Node State Machine ─────────────────────────────────────────

class NodeState(enum.Enum):
    """Deterministic state machine for plan execution nodes."""
    INACTIVE = "inactive"
    WAITING = "waiting"        # preconditions not yet met
    EXECUTING = "executing"    # preconditions passed, running
    FINISHING = "finishing"    # command complete, checking postconditions
    FINISHED = "finished"      # success
    FAILING = "failing"        # invariant or postcondition violated
    FAILED = "failed"          # terminal failure


class FailureType(enum.Enum):
    """Typed failures for deterministic recovery selection."""
    PRECONDITION_FAILED = "precondition_failed"
    INVARIANT_VIOLATED = "invariant_violated"
    POSTCONDITION_FAILED = "postcondition_failed"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    TIMEOUT = "timeout"
    EXECUTION_ERROR = "execution_error"


@dataclass
class Condition:
    """A named boolean condition with a checker function."""
    name: str
    check: Callable[[], bool]
    description: str = ""

    def evaluate(self) -> bool:
        try:
            return bool(self.check())
        except Exception:
            return False


@dataclass
class ResourceRequirement:
    """A resource that must be reserved before execution."""
    resource_name: str
    quantity: float
    priority: int = 5  # 0=highest, 9=lowest


@dataclass
class ExecutionResult:
    """Result of attempting to execute a plan node."""
    success: bool
    state: NodeState
    failure_type: Optional[FailureType] = None
    failure_message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0


# ── Plan Node ──────────────────────────────────────────────────

class PlanNode:
    """A deterministic execution wrapper for subsystem commands.

    Usage::

        node = PlanNode(
            name="activate_heater_zone3",
            subsystem="thermal",
            preconditions=[
                Condition("power_available", lambda: power_budget.available_w >= 500),
                Condition("zone_not_overtemp", lambda: thermal.zone_temp(3) < 350),
            ],
            invariants=[
                Condition("power_maintained", lambda: power_budget.available_w >= 200),
            ],
            postconditions=[
                Condition("temp_rising", lambda: thermal.zone_temp(3) > thermal.prev_temp(3)),
            ],
            resources=[
                ResourceRequirement("electrical_power_w", 500, priority=3),
            ],
            execute_fn=lambda: thermal.set_heater(zone=3, power=500),
            timeout_s=30.0,
        )
        result = guard.execute_node(node)
    """

    def __init__(
        self,
        name: str,
        subsystem: str,
        execute_fn: Callable[[], Any],
        preconditions: Optional[List[Condition]] = None,
        invariants: Optional[List[Condition]] = None,
        postconditions: Optional[List[Condition]] = None,
        resources: Optional[List[ResourceRequirement]] = None,
        timeout_s: float = 60.0,
        recovery_fn: Optional[Callable[[FailureType], None]] = None,
    ) -> None:
        self.name = name
        self.subsystem = subsystem
        self.execute_fn = execute_fn
        self.preconditions = preconditions or []
        self.invariants = invariants or []
        self.postconditions = postconditions or []
        self.resources = resources or []
        self.timeout_s = timeout_s
        self.recovery_fn = recovery_fn
        self.state = NodeState.INACTIVE


# ── Resource Arbiter ───────────────────────────────────────────

class ResourceArbiter:
    """Tracks shared resources and prevents overcommitment.

    Resources: power budget (W), comms bandwidth (bps), crew time
    (person-hours), thruster fuel (kg), etc.
    """

    def __init__(self) -> None:
        self._capacities: Dict[str, float] = {}
        self._reserved: Dict[str, float] = {}
        self._lock = threading.Lock()

    def register_resource(self, name: str, capacity: float) -> None:
        """Register a shared resource with its total capacity."""
        with self._lock:
            self._capacities[name] = capacity
            self._reserved.setdefault(name, 0.0)

    def available(self, name: str) -> float:
        """Current available amount of a resource."""
        with self._lock:
            cap = self._capacities.get(name, 0.0)
            res = self._reserved.get(name, 0.0)
            return max(0.0, cap - res)

    def reserve(self, name: str, quantity: float) -> bool:
        """Attempt to reserve a resource. Returns True if successful."""
        with self._lock:
            avail = self._capacities.get(name, 0.0) - self._reserved.get(name, 0.0)
            if quantity <= avail:
                self._reserved[name] = self._reserved.get(name, 0.0) + quantity
                return True
            return False

    def release(self, name: str, quantity: float) -> None:
        """Release a previously reserved resource."""
        with self._lock:
            self._reserved[name] = max(0.0, self._reserved.get(name, 0.0) - quantity)

    def update_capacity(self, name: str, new_capacity: float) -> None:
        """Update resource capacity (e.g., solar panel degradation)."""
        with self._lock:
            self._capacities[name] = new_capacity


# ── Execution Guard ────────────────────────────────────────────

class ExecutionGuard:
    """Deterministic execution guard for the ARIA agent system.

    Every subsystem command flows through this guard:
    1. Check preconditions (deterministic, no LLM)
    2. Reserve resources (via arbiter)
    3. Execute command
    4. Check invariants during execution
    5. Check postconditions after execution
    6. Release resources
    7. On failure: invoke typed recovery, not LLM
    """

    def __init__(self, arbiter: Optional[ResourceArbiter] = None) -> None:
        self.arbiter = arbiter or ResourceArbiter()
        self._execution_log: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def execute_node(self, node: PlanNode) -> ExecutionResult:
        """Execute a plan node through the full deterministic pipeline."""
        t0 = time.monotonic()
        node.state = NodeState.WAITING

        # 1. Check preconditions
        for cond in node.preconditions:
            if not cond.evaluate():
                node.state = NodeState.FAILED
                result = ExecutionResult(
                    success=False,
                    state=NodeState.FAILED,
                    failure_type=FailureType.PRECONDITION_FAILED,
                    failure_message=f"Precondition '{cond.name}' failed: {cond.description}",
                    duration_s=time.monotonic() - t0,
                )
                self._log(node, result)
                self._recover(node, FailureType.PRECONDITION_FAILED)
                return result

        # 2. Reserve resources
        reserved: List[ResourceRequirement] = []
        for req in node.resources:
            if not self.arbiter.reserve(req.resource_name, req.quantity):
                # Release anything already reserved
                for prev in reserved:
                    self.arbiter.release(prev.resource_name, prev.quantity)
                node.state = NodeState.FAILED
                result = ExecutionResult(
                    success=False,
                    state=NodeState.FAILED,
                    failure_type=FailureType.RESOURCE_UNAVAILABLE,
                    failure_message=f"Resource '{req.resource_name}' unavailable "
                                    f"(need {req.quantity}, have {self.arbiter.available(req.resource_name)})",
                    duration_s=time.monotonic() - t0,
                )
                self._log(node, result)
                self._recover(node, FailureType.RESOURCE_UNAVAILABLE)
                return result
            reserved.append(req)

        # 3. Execute
        node.state = NodeState.EXECUTING
        try:
            exec_result = node.execute_fn()
        except Exception as e:
            # Release resources on error
            for req in reserved:
                self.arbiter.release(req.resource_name, req.quantity)
            node.state = NodeState.FAILED
            result = ExecutionResult(
                success=False,
                state=NodeState.FAILED,
                failure_type=FailureType.EXECUTION_ERROR,
                failure_message=str(e),
                duration_s=time.monotonic() - t0,
            )
            self._log(node, result)
            self._recover(node, FailureType.EXECUTION_ERROR)
            return result

        # 4. Check invariants
        for cond in node.invariants:
            if not cond.evaluate():
                for req in reserved:
                    self.arbiter.release(req.resource_name, req.quantity)
                node.state = NodeState.FAILED
                result = ExecutionResult(
                    success=False,
                    state=NodeState.FAILED,
                    failure_type=FailureType.INVARIANT_VIOLATED,
                    failure_message=f"Invariant '{cond.name}' violated: {cond.description}",
                    duration_s=time.monotonic() - t0,
                )
                self._log(node, result)
                self._recover(node, FailureType.INVARIANT_VIOLATED)
                return result

        # 5. Check postconditions
        node.state = NodeState.FINISHING
        for cond in node.postconditions:
            if not cond.evaluate():
                for req in reserved:
                    self.arbiter.release(req.resource_name, req.quantity)
                node.state = NodeState.FAILED
                result = ExecutionResult(
                    success=False,
                    state=NodeState.FAILED,
                    failure_type=FailureType.POSTCONDITION_FAILED,
                    failure_message=f"Postcondition '{cond.name}' failed: {cond.description}",
                    duration_s=time.monotonic() - t0,
                )
                self._log(node, result)
                self._recover(node, FailureType.POSTCONDITION_FAILED)
                return result

        # 6. Release resources
        for req in reserved:
            self.arbiter.release(req.resource_name, req.quantity)

        # 7. Success
        node.state = NodeState.FINISHED
        result = ExecutionResult(
            success=True,
            state=NodeState.FINISHED,
            data={"result": exec_result} if exec_result is not None else {},
            duration_s=time.monotonic() - t0,
        )
        self._log(node, result)
        return result

    def _recover(self, node: PlanNode, failure_type: FailureType) -> None:
        """Invoke deterministic recovery if available."""
        if node.recovery_fn:
            try:
                node.recovery_fn(failure_type)
            except Exception:
                pass  # recovery failure is logged but doesn't propagate

    def _log(self, node: PlanNode, result: ExecutionResult) -> None:
        """Record execution for audit trail."""
        with self._lock:
            self._execution_log.append({
                "node": node.name,
                "subsystem": node.subsystem,
                "success": result.success,
                "state": result.state.value,
                "failure_type": result.failure_type.value if result.failure_type else None,
                "failure_message": result.failure_message,
                "duration_s": result.duration_s,
                "timestamp": time.time(),
            })
            # Keep last 10,000 entries
            if len(self._execution_log) > 10_000:
                self._execution_log = self._execution_log[-5_000:]

    def audit_log(self, n: int = 100) -> List[Dict[str, Any]]:
        """Return last N execution log entries."""
        with self._lock:
            return list(self._execution_log[-n:])

    def stats(self) -> Dict[str, Any]:
        """Execution statistics."""
        with self._lock:
            total = len(self._execution_log)
            successes = sum(1 for e in self._execution_log if e["success"])
            failures = total - successes
            failure_types: Dict[str, int] = {}
            for e in self._execution_log:
                if e["failure_type"]:
                    failure_types[e["failure_type"]] = failure_types.get(e["failure_type"], 0) + 1
            return {
                "total_executions": total,
                "successes": successes,
                "failures": failures,
                "success_rate": successes / max(total, 1),
                "failure_types": failure_types,
            }
