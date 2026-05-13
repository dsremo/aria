"""FDIR recovery plan library — deterministic responses to known faults.

Provides pre-authored recovery plans for common subsystem faults. When
a fault is detected, FDIR first checks this library for a matching
recovery plan. If found, the plan executes deterministically without
consulting the LLM. If no match, escalate to LLM cognitive engine.

This keeps safety-critical recovery paths:
- Deterministic (same response to same fault, every time)
- Auditable (plan source is visible in code review)
- Fast (no LLM latency)
- Reliable (no hallucinations)

Pattern studied from NASA FDIR literature and Ames SMART-FAIL:
    Mar Morente, L. et al. (2010). "Model-Based Fault Detection,
    Identification and Recovery." NASA TP-2010-216413.

    SMART-FAIL decision trees used on ISS (NASA JSC).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RecoveryStep:
    """A single step in a recovery plan."""
    description: str
    action: Callable[[], Any]                 # executable action (no args)
    verify: Optional[Callable[[], bool]] = None  # optional verification
    timeout_s: float = 10.0
    critical: bool = False                     # abort plan on failure


@dataclass
class RecoveryPlan:
    """A pre-authored recovery procedure for a specific fault pattern."""
    name: str
    fault_pattern: str                        # matches fault_id or fault name
    severity: str = "warning"                 # minimum severity to trigger
    subsystem: str = ""                       # subsystem match (empty = any)
    steps: List[RecoveryStep] = field(default_factory=list)
    description: str = ""
    estimated_duration_s: float = 60.0


@dataclass
class RecoveryResult:
    """Outcome of executing a recovery plan."""
    plan_name: str
    success: bool
    steps_completed: int
    total_steps: int
    failed_step: Optional[str] = None
    error: str = ""
    duration_s: float = 0.0
    # Wiring audit Pass 1 (F6.3) — collect per-step failure details
    # for non-critical steps so operators see "completed 3/5 with
    # errors on steps 2,4" rather than an unconditional success=True.
    step_errors: List[str] = field(default_factory=list)


class RecoveryPlanLibrary:
    """Registry of FDIR recovery plans.

    Usage:
        lib = RecoveryPlanLibrary()
        lib.register(power_undervoltage_recovery())
        lib.register(thermal_zone_overtemp_recovery())

        # When FDIR detects a fault:
        plan = lib.find_matching_plan(fault_name="thermal.overtemp",
                                      severity="critical",
                                      subsystem="thermal")
        if plan:
            result = lib.execute(plan)
    """

    def __init__(self) -> None:
        self._plans: List[RecoveryPlan] = []
        self._history: List[RecoveryResult] = []

    def register(self, plan: RecoveryPlan) -> None:
        """Add a recovery plan to the library."""
        self._plans.append(plan)

    def find_matching_plan(
        self,
        fault_name: str,
        severity: str = "warning",
        subsystem: str = "",
    ) -> Optional[RecoveryPlan]:
        """Find the first matching recovery plan.

        Matching is by: fault_pattern substring in fault_name,
        subsystem equality (if plan has one set), and severity threshold.
        """
        sev_rank = {"watch": 1, "warning": 2, "critical": 3}
        requested_rank = sev_rank.get(severity, 2)

        for plan in self._plans:
            if plan.fault_pattern not in fault_name:
                continue
            if plan.subsystem and plan.subsystem != subsystem:
                continue
            if sev_rank.get(plan.severity, 2) > requested_rank:
                continue
            return plan
        return None

    def execute(self, plan: RecoveryPlan) -> RecoveryResult:
        """Execute a recovery plan step-by-step.

        Stops on the first critical failure.  Wiring audit Pass 1
        (F6.3) — non-critical steps that raise or fail verification
        no longer go silent: we record them in ``step_errors`` and
        the final result is ``success=False`` if anything went wrong,
        even when the plan ran to completion.
        """
        import time
        t0 = time.monotonic()
        step_errors: List[str] = []
        completed = 0

        for step_index, step in enumerate(plan.steps):
            try:
                step.action()

                # Optional verification
                if step.verify is not None and not step.verify():
                    if step.critical:
                        result = RecoveryResult(
                            plan_name=plan.name,
                            success=False,
                            steps_completed=step_index,
                            total_steps=len(plan.steps),
                            failed_step=step.description,
                            error="verification failed",
                            duration_s=time.monotonic() - t0,
                            step_errors=step_errors,
                        )
                        self._history.append(result)
                        return result
                    step_errors.append(
                        f"step {step_index} ({step.description}): verification failed"
                    )
                    continue

                completed += 1
            except Exception as exc:
                if step.critical:
                    result = RecoveryResult(
                        plan_name=plan.name,
                        success=False,
                        steps_completed=step_index,
                        total_steps=len(plan.steps),
                        failed_step=step.description,
                        error=str(exc),
                        duration_s=time.monotonic() - t0,
                        step_errors=step_errors,
                    )
                    self._history.append(result)
                    return result
                step_errors.append(
                    f"step {step_index} ({step.description}): {type(exc).__name__}: {exc}"
                )

        result = RecoveryResult(
            plan_name=plan.name,
            success=not step_errors,
            steps_completed=completed,
            total_steps=len(plan.steps),
            error="" if not step_errors else f"{len(step_errors)} non-critical step(s) failed",
            duration_s=time.monotonic() - t0,
            step_errors=step_errors,
        )
        self._history.append(result)
        return result

    def stats(self) -> Dict[str, Any]:
        """Recovery execution statistics."""
        total = len(self._history)
        successes = sum(1 for r in self._history if r.success)
        return {
            "plans_registered": len(self._plans),
            "total_executions": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": successes / max(total, 1),
        }


# ══════════════════════════════════════════════════════════════════
#  Built-in recovery plans for common spacecraft faults
# ══════════════════════════════════════════════════════════════════

def build_standard_library(
    command_tracker: Any = None,
    event_bus: Any = None,
    asyncio_loop: Any = None,
) -> RecoveryPlanLibrary:
    """Construct a library of standard recovery plans.

    Recovery audit R-5: previously the dispatcher called
    ``event_bus.publish(topic, severity=..., payload=...)`` which
    matched the simulator's ``EventBus`` signature, NOT the production
    ``MessageBus.publish(message: Message)``.  Every recovery step
    raised TypeError silently swallowed by the executor, so the FDIR
    plan reported "executed" while no actuator command ever fired.

    The dispatcher now distinguishes:
      * ``command_tracker`` — preferred path (fully-tracked dispatch)
      * ``MessageBus``      — async; we wrap each call in
                              ``run_coroutine_threadsafe`` against
                              ``asyncio_loop`` so the call works from
                              any thread.
      * sync ``EventBus``   — kwargs path (simulator compatibility).
    """
    lib = RecoveryPlanLibrary()

    # Detect the bus shape once at build time.
    _is_message_bus = (
        event_bus is not None
        and hasattr(event_bus, "publish")
        and getattr(event_bus.publish, "__code__", None) is not None
        # MessageBus.publish is `async def publish(self, message)` so
        # only takes one positional after self.  EventBus.publish has
        # `topic` + kwargs.
        and event_bus.publish.__code__.co_argcount <= 2
    )

    def _dispatch(topic: str, params: dict | None = None):
        """Helper: dispatch via command tracker or publish to bus.

        Returns True on successful submission so the recovery executor
        can mark the step as having actually fired.  Raises on
        unrecoverable wiring failure so a critical=True step aborts
        the plan (which is the safe default).
        """
        if command_tracker is not None:
            command_tracker.dispatch(topic, params=params, timeout_s=30)
            return True
        if event_bus is None:
            raise RuntimeError("fdir_recovery._dispatch: no bus configured")
        if _is_message_bus:
            # Lazy import to avoid hard dependency in the simulator path.
            from aria.bus.message_bus import Message
            from aria.core.types import EventPriority
            import asyncio as _asyncio
            msg = Message(
                topic=topic,
                payload=dict(params or {}),
                priority=EventPriority.P1_CRITICAL,
                source_agent="fdir_recovery",
            )
            loop = asyncio_loop
            if loop is None:
                try:
                    loop = _asyncio.get_event_loop()
                except RuntimeError:
                    loop = None
            if loop is not None and loop.is_running():
                _asyncio.run_coroutine_threadsafe(event_bus.publish(msg), loop)
            else:
                # Fall back to a fresh ad-hoc loop so the recovery still
                # fires even if the main loop is wedged.  This is the
                # last-gasp path; the actuator will usually be a
                # different process / hardware bus.
                _asyncio.run(event_bus.publish(msg))
            return True
        # Synchronous EventBus (simulator).
        event_bus.publish(topic, severity="info",
                          source="fdir_recovery",
                          payload=params or {})
        return True

    # ── Power undervoltage ──
    lib.register(RecoveryPlan(
        name="power_undervoltage_recovery",
        fault_pattern="undervoltage",
        severity="warning",
        subsystem="power",
        description="Shed non-critical loads, route battery to essentials",
        estimated_duration_s=30.0,
        steps=[
            RecoveryStep(
                description="Broadcast load-shed request to non-critical loads",
                action=lambda: _dispatch("power.load_shed",
                                         {"level": 1, "reason": "undervoltage"}),
                critical=True,    # Recovery audit R-5: must actually fire.
            ),
            RecoveryStep(
                description="Switch to battery backup for critical buses",
                action=lambda: _dispatch("power.battery_switchover",
                                         {"buses": ["critical"]}),
                critical=True,
            ),
            RecoveryStep(
                description="Alert crew of power anomaly",
                action=lambda: _dispatch("notify.crew",
                                         {"priority": "warning",
                                          "message": "Power system entering safe mode"}),
            ),
        ],
    ))

    # ── Thermal zone overtemperature ──
    lib.register(RecoveryPlan(
        name="thermal_overtemp_recovery",
        fault_pattern="overtemp",
        severity="warning",
        subsystem="thermal",
        description="Reduce heat input, increase radiator flow, alert crew",
        estimated_duration_s=60.0,
        steps=[
            RecoveryStep(
                description="Turn off heater in affected zone",
                action=lambda: _dispatch("thermal.heater_off"),
            ),
            RecoveryStep(
                description="Increase radiator coolant flow rate",
                action=lambda: _dispatch("thermal.radiator_max"),
            ),
            RecoveryStep(
                description="Reduce power draw of high-heat subsystems",
                action=lambda: _dispatch("power.reduce_high_heat"),
            ),
        ],
    ))

    # ── ECLSS CO2 buildup ──
    lib.register(RecoveryPlan(
        name="eclss_co2_recovery",
        fault_pattern="co2",
        severity="warning",
        subsystem="eclss",
        description="Activate backup scrubber, increase ventilation",
        estimated_duration_s=120.0,
        steps=[
            RecoveryStep(
                description="Activate secondary CO2 scrubber",
                action=lambda: _dispatch("eclss.scrubber_backup_on"),
                critical=True,
            ),
            RecoveryStep(
                description="Increase cabin ventilation fan speed",
                action=lambda: _dispatch("eclss.fan_speed",
                                         {"level": "high"}),
            ),
            RecoveryStep(
                description="Reduce crew exertion level advisory",
                action=lambda: _dispatch("notify.crew",
                                         {"priority": "warning",
                                          "message": "Reduce activity until CO2 normalizes"}),
            ),
        ],
    ))

    # ── Comms signal loss ──
    lib.register(RecoveryPlan(
        name="comms_loss_recovery",
        fault_pattern="comms_loss",
        severity="warning",
        subsystem="comms",
        description="Switch to backup antenna, start beacon, log to FIFO",
        estimated_duration_s=45.0,
        steps=[
            RecoveryStep(
                description="Switch to omnidirectional backup antenna",
                action=lambda: _dispatch("comms.antenna_backup"),
            ),
            RecoveryStep(
                description="Activate emergency beacon",
                action=lambda: _dispatch("comms.beacon_on"),
            ),
            RecoveryStep(
                description="Buffer telemetry to store-and-forward FIFO",
                action=lambda: _dispatch("comms.store_forward_enable"),
            ),
        ],
    ))

    # ── SEU event (memory flip detected) ──
    lib.register(RecoveryPlan(
        name="seu_recovery",
        fault_pattern="seu",
        severity="warning",
        subsystem="avionics",
        description="Trigger memory scrub, verify TMR consensus",
        estimated_duration_s=10.0,
        steps=[
            RecoveryStep(
                description="Trigger full memory scrub cycle",
                action=lambda: _dispatch("avionics.memory_scrub"),
            ),
            RecoveryStep(
                description="Verify TMR voting consensus",
                action=lambda: _dispatch("avionics.tmr_verify"),
                critical=True,
            ),
        ],
    ))

    # ── Attitude loss (rate exceeded) ──
    lib.register(RecoveryPlan(
        name="attitude_tumble_recovery",
        fault_pattern="tumble",
        severity="critical",
        subsystem="navigation",
        description="Safe mode: point solar panels to sun, detumble",
        estimated_duration_s=180.0,
        steps=[
            RecoveryStep(
                description="Enter safe mode (coarse sun pointing)",
                action=lambda: _dispatch("gnc.safe_mode",
                                         {"target": "sun_point"}),
                critical=True,
            ),
            RecoveryStep(
                description="Activate detumble controller (B-dot)",
                action=lambda: _dispatch("gnc.detumble_on"),
            ),
            RecoveryStep(
                description="Disable science operations until stable",
                action=lambda: _dispatch("science.pause"),
            ),
        ],
    ))

    # ── Fuel leak detected ──
    lib.register(RecoveryPlan(
        name="fuel_leak_recovery",
        fault_pattern="leak",
        severity="critical",
        subsystem="propulsion",
        description="Isolate leaking tank, recompute mission dv",
        estimated_duration_s=15.0,
        steps=[
            RecoveryStep(
                description="Close isolation valves on affected tank",
                action=lambda: _dispatch("propulsion.tank_isolate"),
                critical=True,
            ),
            RecoveryStep(
                description="Recompute mission dv budget with reduced fuel",
                action=lambda: _dispatch("mission.recompute_dv_budget"),
            ),
            RecoveryStep(
                description="Alert mission planner of new constraints",
                action=lambda: _dispatch("notify.crew",
                                         {"priority": "critical",
                                          "message": "Fuel leak isolated — review trajectory"}),
            ),
        ],
    ))

    return lib
