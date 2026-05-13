"""SubsystemAgent base class — the autonomous unit of ARIA.

Each subsystem (telemetry, navigation, power, ECLSS, etc.) has an agent.
Agents:
  - Subscribe to relevant message bus topics
  - Own a set of tools for their domain
  - Run an async event loop processing messages
  - Report health via heartbeat
  - Can be started, stopped, and restarted by the Coordinator

Coordinator (orchestrates workers, synthesizes results).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus
# Wiring audit Pass 2 (F6.5) — promoted from a wrapped per-call import
# inside ``on_reasoning_response`` to module level. Previously a missing
# / renamed ``parse_recommendation`` silently turned every LLM advisory
# loop into a no-op (returned ``intents=[]``); now an ImportError at
# boot is loud and catastrophic, which is the correct posture for the
# default LLM advisory dispatcher.
from aria.cognitive.action_executor import parse_recommendation
from aria.cognitive.action_log import get_action_log
from aria.core.types import AgentStatus, EventPriority
from aria.tools.registry import ToolRegistry

logger = structlog.get_logger()


# Autonomy audit F3 — bound the per-agent message queue so a flood on
# a high-rate topic cannot OOM the runtime.
_DEFAULT_QUEUE_MAXSIZE = 1024
# Autonomy audit F27 — wrap each handle_message in a timeout so a stuck
# subclass handler doesn't block all subsequent messages.
_HANDLE_MESSAGE_TIMEOUT_S = 30.0


class SubsystemAgent(ABC):
    """Base class for all ARIA subsystem agents.

    Lifecycle: __init__ -> start() -> [running] -> stop()

    During [running], the agent:
      1. Processes messages from its subscribed topics
      2. Runs periodic tasks (health checks, trend analysis)
      3. Publishes events (anomalies, alerts, status updates)
      4. Responds to coordinator requests
    """

    name: str = ""
    description: str = ""
    subscriptions: list[str] = []  # Topic patterns this agent listens to
    heartbeat_interval_s: float = 10.0
    # Autonomy audit F27 — subclasses can override.
    handle_message_timeout_s: float = _HANDLE_MESSAGE_TIMEOUT_S

    def __init__(self, bus: MessageBus, tool_registry: ToolRegistry, **kwargs: Any) -> None:
        self._bus = bus
        self._tools = tool_registry
        self._scratchpad = kwargs.get("scratchpad")
        self._status = AgentStatus.INITIALIZING
        # Autonomy audit F3 — bounded queue + drop-oldest counter.
        self._message_queue: asyncio.Queue[Message] = asyncio.Queue(
            maxsize=int(kwargs.get("queue_maxsize", _DEFAULT_QUEUE_MAXSIZE)),
        )
        self._queue_overflow_count: int = 0
        self._tasks: list[asyncio.Task[Any]] = []
        self._last_heartbeat: datetime | None = None
        self._messages_processed: int = 0
        # Wiring audit Pass 2 (F9.3) — track the messages_processed
        # value at the previous ping so handle_ping can detect a
        # wedged process loop.  Without this, a stuck handle_message
        # leaves the agent appearing healthy to HealthMonitor while
        # the queue grows unbounded.
        self._last_ping_messages_processed: int = 0

        # Last cognitive-engine reasoning response delivered to this agent.
        # Populated by `on_reasoning_response()` and surfaced via `.stats`
        # so the UI / tests can confirm the closed loop is working.
        self._last_reasoning_response: dict[str, Any] | None = None

        # Decision learning: track outcomes to adjust confidence thresholds.
        # Autonomy audit F21/F22 — stable monotonic decision IDs (never
        # re-mapped) + dict-keyed storage so callers holding old IDs
        # mutate the right record after pruning.
        self._decision_log: dict[int, dict[str, Any]] = {}
        self._next_decision_id: int = 0
        self._false_alarm_count: int = 0   # alerts that were false positives
        self._missed_alarm_count: int = 0  # real anomalies that were missed
        self._correct_alert_count: int = 0 # alerts that were confirmed true
        self._alert_threshold_adjustment: float = 0.0  # adaptive threshold shift

        # Coordinator-injected safety modules (optional — set by coordinator
        # via set_safety_context after instantiation). Allows agents to:
        #   - report faults via FaultManager (ack/shelve/resolve workflow)
        #   - dispatch commands via CommandTracker (sequence + timeout)
        #   - validate commands via ExecutionGuard (preconditions + resources)
        #   - respond to ping health checks from HealthMonitor
        self._fault_mgr: Any = None
        self._cmd_tracker: Any = None
        self._exec_guard: Any = None
        self._health_monitor: Any = None

    @property
    def status(self) -> AgentStatus:
        return self._status

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self._status.name,
            "messages_processed": self._messages_processed,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "queue_size": self._message_queue.qsize(),
            # Wiring audit Pass 2 (F1.8) — surface cumulative queue
            # drops so operators can see message-loss history, not
            # just current depth.
            "queue_overflow_count": self._queue_overflow_count,
            "last_reasoning_response": self._last_reasoning_response,
        }

    async def start(self) -> None:
        """Start the agent's event loop and subscriptions."""
        logger.info("agent.starting", agent=self.name)

        # Subscribe to topics
        for pattern in self.subscriptions:
            self._bus.subscribe(pattern, self._enqueue_message)

        # Subscribe to reasoning responses addressed specifically to this agent
        # — the coordinator publishes on this topic after the CognitiveEngine
        # finishes reasoning about a `request_reasoning()` call.
        self._bus.subscribe(
            f"aria.agent.reasoning_response.{self.name}",
            self._enqueue_message,
        )

        # Initialize subclass
        await self.on_start()

        self._status = AgentStatus.READY

        # Start background tasks
        self._tasks.append(asyncio.create_task(self._process_loop()))
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))

        logger.info("agent.started", agent=self.name)

    async def stop(self) -> None:
        """Gracefully stop the agent."""
        logger.info("agent.stopping", agent=self.name)
        self._status = AgentStatus.SHUTTING_DOWN

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Unsubscribe
        for pattern in self.subscriptions:
            self._bus.unsubscribe(pattern, self._enqueue_message)
        self._bus.unsubscribe(
            f"aria.agent.reasoning_response.{self.name}",
            self._enqueue_message,
        )

        await self.on_stop()
        self._status = AgentStatus.STOPPED
        logger.info("agent.stopped", agent=self.name, messages_processed=self._messages_processed)

    # --- Subclass hooks ---

    async def on_start(self) -> None:
        """Called during start(). Override to initialize resources."""

    async def on_stop(self) -> None:
        """Called during stop(). Override to cleanup resources."""

    @abstractmethod
    async def handle_message(self, message: Message) -> None:
        """Process a single message. Subclass must implement."""
        ...

    async def periodic_task(self) -> None:
        """Override for periodic work (e.g. trend analysis every 60s).

        Called from the process loop between message handling.
        Default: no-op.
        """

    # --- Safety module integration ---

    def set_safety_context(
        self,
        fault_manager: Any = None,
        command_tracker: Any = None,
        execution_guard: Any = None,
        health_monitor: Any = None,
    ) -> None:
        """Inject safety modules from the coordinator.

        Called once after agent instantiation to wire in the deterministic
        safety layer. Agents can then use:
          - self.report_fault() for structured fault reporting
          - self.dispatch_command() for tracked commands with timeouts
          - self.safe_execute() for precondition/resource validated actions
          - self.handle_ping() for health monitor responses
        """
        self._fault_mgr = fault_manager
        self._cmd_tracker = command_tracker
        self._exec_guard = execution_guard
        self._health_monitor = health_monitor

        # Register ourselves with the health monitor for ping-based monitoring
        if health_monitor is not None:
            health_monitor.register(
                self.name,
                ping_fn=self.handle_ping,
                warn_cycles=3,
                fatal_cycles=10,
            )

    def handle_ping(self, key: int) -> int:
        """Respond to a health monitor ping.

        Wiring audit Pass 2 (F9.3) — the original implementation just
        echoed ``key`` back, which proved nothing about the process
        loop.  A handle_message stuck in a hung tool / IO call left
        the agent appearing healthy while its queue grew unbounded.

        We now treat the ping as a *liveness* check:

          * If ``messages_processed`` has advanced since the previous
            ping, the loop is making progress → echo.
          * If it has not advanced AND there are pending messages in
            the queue, the loop is wedged → raise ``RuntimeError``
            so HealthMonitor counts a missed cycle.

        An idle agent with an empty queue legitimately doesn't
        advance the counter; that case is treated as alive (echo).
        """
        current = self._messages_processed
        last = self._last_ping_messages_processed
        self._last_ping_messages_processed = current
        if current == last and self._message_queue.qsize() > 0:
            raise RuntimeError(
                f"agent.{self.name}.process_loop_stalled "
                f"(messages_processed={current}, queue_depth="
                f"{self._message_queue.qsize()})"
            )
        return key

    def report_fault(
        self,
        message: str,
        severity: str = "warning",
        sim_time_yr: float = 0.0,
    ) -> str | None:
        """Report a fault via the fault manager.

        Returns fault ID if the fault manager is available, else None.
        Severity: "watch", "warning", or "critical".

        Wiring audit Pass 2 (F6.4) — narrowed the broad except. The
        FaultManager bus dispatch + persist write (Pass 1 wiring) can
        raise OSError / RuntimeError; previously those were swallowed
        and the caller had no signal that the structured fault path
        had failed. Now ValueError on the enum is caught silently
        (bad severity string from the caller — recoverable), but any
        other exception is logged structurally so SREs see breakage.
        """
        if self._fault_mgr is None:
            return None
        try:
            from aria.safety.fault_manager import FaultSeverity
            sev = FaultSeverity(severity)
        except ValueError:
            return None
        try:
            return self._fault_mgr.report(self.name, sev, message, sim_time_yr)
        except Exception as exc:    # noqa: BLE001
            logger.warning(
                "agent.report_fault_failed",
                agent=self.name,
                error=f"{type(exc).__name__}: {exc}",
                severity=severity,
            )
            return None

    def dispatch_command(
        self,
        topic: str,
        params: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
        preconditions: list | None = None,
        resources: list | None = None,
    ) -> int | None:
        """Dispatch a command, routing through ExecutionGuard when available.

        When an ExecutionGuard is injected (by the coordinator via
        set_safety_context), the command is wrapped in a PlanNode and
        validated against ``preconditions`` and ``resources`` before
        being handed to the CommandTracker.  This ensures every agent
        command passes through the deterministic safety layer.

        If no guard is available, falls back to direct tracker dispatch
        (backward-compatible, e.g. during unit tests).

        Args:
            topic:         Bus topic / command identifier.
            params:        Command parameters.
            timeout_s:     Timeout for CommandTracker bookkeeping.
            preconditions: Optional list of ``Condition`` objects that
                           must be true for the command to execute.
            resources:     Optional list of ``ResourceRequirement``
                           objects the command will consume.

        Returns:
            Command sequence number, or None if unavailable / blocked.
        """
        if self._cmd_tracker is None:
            return None

        if self._exec_guard is None:
            # No guard available — direct dispatch (test or bootstrap path)
            return self._cmd_tracker.dispatch(
                topic=topic, params=params, timeout_s=timeout_s,
                source=self.name,
            )

        # --- Guarded path: wrap in a PlanNode and validate ---
        from aria.safety.execution_guard import PlanNode

        seq_holder: list[int | None] = [None]

        def _execute_fn() -> int | None:
            seq = self._cmd_tracker.dispatch(
                topic=topic, params=params, timeout_s=timeout_s,
                source=self.name,
            )
            seq_holder[0] = seq
            return seq

        node = PlanNode(
            name=topic,
            subsystem=self.name,
            execute_fn=_execute_fn,
            preconditions=preconditions or [],
            resources=resources or [],
            timeout_s=timeout_s,
        )
        result = self._exec_guard.execute_node(node)
        if result.success:
            return seq_holder[0]
        # Guard blocked the command — log and return None
        import structlog as _sl
        _sl.get_logger().warning(
            "agent.command_blocked",
            agent=self.name, topic=topic,
            reason=result.failure_message,
        )
        return None

    def complete_command(self, seq: int, success: bool = True) -> bool:
        """Mark a dispatched command as completed."""
        if self._cmd_tracker is None:
            return False
        return self._cmd_tracker.complete(seq, success=success)

    # --- Publishing ---

    async def request_reasoning(self, question: str, context: dict[str, Any] | None = None) -> None:
        """Request AI reasoning from the cognitive engine for complex situations.

        The agent publishes a reasoning request on the bus. The coordinator
        (`_on_reasoning_request`) dispatches it to the CognitiveEngine, which
        runs the the LLM tool-use loop (tools can read any registered subsystem
        state), then publishes the final decision back on
        `aria.agent.reasoning_response.{self.name}`. The response is enqueued
        to this agent via its `_enqueue_message` subscription and delivered
        through `handle_message()`. Subclasses can override
        `on_reasoning_response()` to act on the recommendation.
        """
        await self.publish(
            topic="aria.agent.reasoning_request",
            payload={
                "agent": self.name,
                "question": question,
                "context": context or {},
            },
            priority=EventPriority.P2_WARNING,
        )

    async def on_reasoning_response(self, payload: dict[str, Any]) -> None:
        """Default handler for a cognitive-engine reasoning response.

        Records the response *and* surfaces any parsed action intents as
        advisory events on the bus. Concrete agents (PowerAgent, etc.)
        override this to actually mutate state for the actions they own;
        the default keeps the loop visible to operators by publishing
        ``aria.{agent}.llm_action.advisory`` for each parsed intent so it
        shows up in the AI Decisions panel without silently disappearing.
        """
        self._last_reasoning_response = {
            "question": payload.get("question", ""),
            "response": payload.get("response", ""),
            "tools_used": payload.get("tools_used", []),
            "steps": payload.get("steps", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(
            "agent.reasoning_response",
            agent=self.name,
            steps=payload.get("steps", 0),
            tools=payload.get("tools_used", []),
        )

        # Surface parsed actions on the bus so operators see the advisory
        # even when no agent owns this action. Subclasses that *do* own
        # the action override this method to act and short-circuit before
        # the advisory publish.
        # Wiring audit Pass 2 (F6.5) — imports promoted to module-level;
        # only PARSE failures are caught here (malformed LLM output is a
        # legitimate runtime case), not import errors.
        try:
            intents = parse_recommendation(payload.get("response", "") or "")
        except (ValueError, TypeError, AttributeError) as exc:
            logger.warning(
                "agent.parse_recommendation_failed",
                agent=self.name,
                error=f"{type(exc).__name__}: {exc}",
            )
            intents = []
        for intent in intents:
            # Wiring audit Pass 2 (F6.5/F6.6) — `get_action_log` is now
            # imported at module-load (F6.5), so the previous
            # ``if get_action_log is not None`` guard was dead. The
            # try/except still wraps the append() call body for
            # disk/permission failures (F6.6).
            try:
                get_action_log().append(
                    agent=self.name,
                    action=intent.action,
                    status="advisory",
                    params=intent.params,
                    rationale=intent.rationale or "llm_recommendation",
                )
            except Exception as exc:    # noqa: BLE001
                logger.warning(
                    "agent.action_log_advisory_failed",
                    agent=self.name,
                    action=intent.action,
                    error=f"{type(exc).__name__}: {exc}",
                )
            await self.publish(
                topic=f"aria.{self.name}.llm_action.advisory",
                payload={
                    "action": intent.action,
                    "params": intent.params,
                    "agent": self.name,
                    "rationale": intent.rationale or "llm_recommendation",
                },
                priority=EventPriority.P3_ROUTINE,
            )

    def _log_action_executed(self, action: str, params: dict[str, Any] | None = None,
                              rationale: str = "") -> None:
        """Helper for concrete on_reasoning_response overrides — record
        a dispatched action so it shows up alongside advisories in the
        AI Actions panel. Failures are swallowed so action-log glitches
        can't take an agent offline.
        """
        # Wiring audit Pass 2 (F6.5) — get_action_log promoted to
        # module-level import; only the call body is wrapped.
        try:
            get_action_log().append(
                agent=self.name,
                action=action,
                status="executed",
                params=params or {},
                rationale=rationale,
            )
        except Exception as exc:    # noqa: BLE001
            # Wiring audit Pass 2 (F6.6) — see comment in
            # on_reasoning_response.
            logger.warning(
                "agent.action_log_executed_failed",
                agent=self.name,
                action=action,
                error=f"{type(exc).__name__}: {exc}",
            )

    # --- Decision Learning ---

    def log_decision(self, action: str, context: dict[str, Any] | None = None) -> int:
        """Log a decision for later outcome tracking.

        Autonomy audit F21 — returns a stable monotonic ID; pruning
        drops oldest IDs but never re-maps existing ones, so callers
        holding old IDs still mutate the right record (or get a clean
        miss in record_outcome).
        """
        decision_id = self._next_decision_id
        self._next_decision_id += 1
        self._decision_log[decision_id] = {
            "id": decision_id,
            "action": action,
            "context": context or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "outcome": None,
        }
        # Bound memory: keep most recent _MAX_DECISION_LOG records.
        _MAX_DECISION_LOG = 500
        if len(self._decision_log) > _MAX_DECISION_LOG * 2:
            # Drop oldest by ID.
            keep = sorted(self._decision_log.keys())[-_MAX_DECISION_LOG:]
            self._decision_log = {k: self._decision_log[k] for k in keep}
        return decision_id

    def record_outcome(self, decision_id: int, outcome: str) -> None:
        """Record the outcome of a previous decision.

        Autonomy audit F22 — unknown / pruned IDs emit a structured
        warning rather than silently dropping the outcome.
        """
        rec = self._decision_log.get(decision_id)
        if rec is not None:
            rec["outcome"] = outcome
        else:
            logger.warning(
                "agent.record_outcome.unknown_id",
                agent=self.name, decision_id=decision_id, outcome=outcome,
            )

        if outcome == "false_alarm":
            self._false_alarm_count += 1
        elif outcome == "missed":
            self._missed_alarm_count += 1
        elif outcome == "correct":
            self._correct_alert_count += 1

        # Adaptive threshold: shift based on false alarm vs missed ratio
        # This is a simple exponential moving average adjustment.
        # Positive shift → higher threshold (fewer alerts)
        # Negative shift → lower threshold (more alerts)
        total = self._false_alarm_count + self._missed_alarm_count + self._correct_alert_count
        if total > 5:  # need minimum history before adjusting
            fa_rate = self._false_alarm_count / total
            miss_rate = self._missed_alarm_count / total
            # Target: equal false alarm and miss rates
            # If fa_rate > miss_rate → too many false alarms → raise threshold
            # Clamp to ±0.05 to prevent runaway oscillation from noisy early data
            raw = 0.1 * (fa_rate - miss_rate)
            self._alert_threshold_adjustment = max(-0.05, min(0.05, raw))

        logger.info(
            "agent.learning",
            agent=self.name,
            outcome=outcome,
            false_alarms=self._false_alarm_count,
            misses=self._missed_alarm_count,
            correct=self._correct_alert_count,
            threshold_adj=self._alert_threshold_adjustment,
        )

    @property
    def alert_threshold_offset(self) -> float:
        """Current adaptive threshold offset for alert decisions.

        Agents should add this to their base threshold when deciding
        whether to raise an alert. Positive = less sensitive (fewer alerts),
        negative = more sensitive (more alerts).
        """
        return self._alert_threshold_adjustment

    @property
    def decision_stats(self) -> dict[str, Any]:
        """Summary of decision learning statistics."""
        total = self._false_alarm_count + self._missed_alarm_count + self._correct_alert_count
        return {
            "total_decisions": len(self._decision_log),
            "correct_alerts": self._correct_alert_count,
            "false_alarms": self._false_alarm_count,
            "missed_anomalies": self._missed_alarm_count,
            "precision": self._correct_alert_count / max(1, self._correct_alert_count + self._false_alarm_count),
            "threshold_adjustment": self._alert_threshold_adjustment,
        }

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        priority: EventPriority = EventPriority.P3_ROUTINE,
        correlation_id: str = "",
    ) -> None:
        """Publish a message on the bus from this agent."""
        msg = Message(
            topic=topic,
            payload=payload,
            priority=priority,
            source_agent=self.name,
            correlation_id=correlation_id,
        )
        await self._bus.publish(msg)

    # --- Internal ---

    async def _enqueue_message(self, message: Message) -> None:
        """Callback from bus subscription — enqueues for processing.

        Autonomy audit F3 — bounded queue.  When full we drop the
        OLDEST message (FIFO eviction) so the most recent — most
        relevant — telemetry survives a flood.  Each drop emits a
        structured event so the operator console can flag overflow.
        """
        try:
            self._message_queue.put_nowait(message)
            return
        except asyncio.QueueFull:
            pass
        # Drop oldest, retry once.
        try:
            dropped = self._message_queue.get_nowait()
            self._message_queue.task_done()
            self._queue_overflow_count += 1
            logger.warning(
                "agent.queue_overflow",
                agent=self.name,
                dropped_topic=getattr(dropped, "topic", "?"),
                drop_total=self._queue_overflow_count,
            )
        except asyncio.QueueEmpty:
            pass
        try:
            self._message_queue.put_nowait(message)
        except asyncio.QueueFull:
            # Even after eviction the queue is full — give up; the
            # incoming message is dropped.
            self._queue_overflow_count += 1

    async def _process_loop(self) -> None:
        """Main message processing loop.

        Autonomy audit F27 — every ``handle_message`` invocation is
        bounded by ``handle_message_timeout_s``.  A stuck handler
        promotes the agent to ERROR and frees the queue for the next
        message rather than starving every subsequent telemetry sample.
        """
        self._status = AgentStatus.READY
        while self._status not in (AgentStatus.SHUTTING_DOWN, AgentStatus.STOPPED):
            try:
                message = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                self._status = AgentStatus.BUSY
                try:
                    # Intercept cognitive-engine replies addressed to this
                    # agent before the subclass handler sees them. The
                    # subclass is still free to override handle_message()
                    # to intercept these too — we just guarantee the base
                    # recording hook always runs.
                    if message.topic == f"aria.agent.reasoning_response.{self.name}":
                        await asyncio.wait_for(
                            self.on_reasoning_response(message.payload or {}),
                            timeout=self.handle_message_timeout_s,
                        )
                    else:
                        await asyncio.wait_for(
                            self.handle_message(message),
                            timeout=self.handle_message_timeout_s,
                        )
                    self._messages_processed += 1
                except asyncio.TimeoutError:
                    logger.error(
                        "agent.message_timeout",
                        agent=self.name,
                        topic=getattr(message, "topic", "?"),
                        timeout_s=self.handle_message_timeout_s,
                    )
                    self._status = AgentStatus.ERROR
                except Exception as exc:    # noqa: BLE001
                    logger.error(
                        "agent.message_error",
                        agent=self.name,
                        topic=message.topic,
                        error=str(exc),
                    )
                    self._status = AgentStatus.ERROR
                finally:
                    if self._status == AgentStatus.BUSY:
                        self._status = AgentStatus.READY
            except asyncio.TimeoutError:
                # No message — run periodic task
                try:
                    await self.periodic_task()
                except Exception as exc:    # noqa: BLE001
                    logger.error("agent.periodic_error", agent=self.name, error=str(exc))
            except asyncio.CancelledError:
                break

    async def _heartbeat_loop(self) -> None:
        """Publish periodic heartbeat for health monitoring."""
        while self._status not in (AgentStatus.SHUTTING_DOWN, AgentStatus.STOPPED):
            try:
                await asyncio.sleep(self.heartbeat_interval_s)
                self._last_heartbeat = datetime.now(timezone.utc)
                await self.publish(
                    topic=f"aria.agent.{self.name}.heartbeat",
                    payload=self.stats,
                    priority=EventPriority.P5_BACKGROUND,
                )
            except asyncio.CancelledError:
                break
