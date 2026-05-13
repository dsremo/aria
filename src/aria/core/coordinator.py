"""ARIA Core Coordinator — the brain that orchestrates all agents.

  - Main thread = Coordinator (communicates with Captain, synthesizes)
  - Workers = SubsystemAgents (research, monitor, execute)
  - Coordinator NEVER delegates understanding — it synthesizes all agent results

The Coordinator owns:
  - Tool registry (all tools)
  - Agent registry (all agents)
  - Message bus (communication backbone)
  - State manager (shared state)
  - Decision engine (route decisions by authority)
  - Health scorer + safe mode manager (system resilience)
  - Checkpoint manager (state persistence)
  - Metrics collector (observability)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from aria.agents.base import SubsystemAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.config import AriaConfig
from aria.core.conflict import ConflictResolver
from aria.core.decision_engine import Decision, DecisionEngine
from aria.core.types import AgentStatus, EventPriority, MissionPhase, PHASE_CONFIG, Severity
from aria.integrations.dsremo.correlator import AnomalyCorrelator
from aria.metrics.collector import MetricsCollector
from aria.metrics.event_log import EventLogger
from aria.safety.checkpoint import CheckpointManager
from aria.safety.fdir import FDIRManager
from aria.safety.health import HealthScorer
from aria.safety.safe_mode import SafeLevel, SafeModeManager
from aria.state.manager import StateManager
from aria.state.scratchpad import SharedScratchpad
from aria.tools.registry import ToolRegistry

logger = structlog.get_logger()


@dataclass
class AgentRecord:
    """Registry entry for a managed agent."""

    agent: SubsystemAgent
    restart_count: int = 0
    registered_at: datetime | None = None
    last_failed_at: float = 0.0    # Recovery audit R-4 — for cooldown decay


class AriaCoordinator:
    """The central coordinator for ARIA.

    This is the main entry point. It:
      1. Initializes all subsystems (bus, state, tools, agents)
      2. Starts agents and monitors their health
      3. Routes events to appropriate agents
      4. Handles escalation to Captain
      5. Manages graceful degradation via HealthScorer + SafeModeManager
      6. Persists state via CheckpointManager
      7. Tracks all metrics via MetricsCollector

    Usage:
        config = AriaConfig.from_yaml("configs/aria.yaml")
        coordinator = AriaCoordinator(config)
        await coordinator.start()
        # ... ARIA is now running ...
        await coordinator.stop()
    """

    def __init__(self, config: AriaConfig) -> None:
        self.config = config
        self.bus = MessageBus(max_history=config.bus.max_history)
        self.state = StateManager(persist_path="data/aria_state.json")
        self.metrics = MetricsCollector()
        self.tools = ToolRegistry(metrics=self.metrics)
        self.health_scorer = HealthScorer()
        self.safe_mode = SafeModeManager(self.bus)
        self.checkpoint = CheckpointManager(
            persist_dir="data/checkpoints",
            interval_s=config.safety.checkpoint_interval_s,
        )
        self.correlator = AnomalyCorrelator(self.bus, window_s=30.0)
        self.decision_engine = DecisionEngine(self.bus)
        self.conflict_resolver = ConflictResolver(self.bus)
        self.fdir = FDIRManager(self.bus)

        # Deterministic execution guard — validates all agent commands
        # against preconditions and resource constraints before execution.
        # LLM generates intent → ExecutionGuard validates deterministically.
        from aria.safety.execution_guard import ExecutionGuard, ResourceArbiter
        self.resource_arbiter = ResourceArbiter()
        self.execution_guard = ExecutionGuard(self.resource_arbiter)

        # Command sequence tracker — ensures every command gets a response.
        # Wiring audit Pass 1 (F1.3 + F10.3): pass the live bus so
        # dispatch / check_timeouts publish observable Messages instead
        # of silently dropping the publish branch.
        from aria.safety.command_tracker import CommandTracker
        self.command_tracker = CommandTracker(bus=self.bus, default_timeout_s=60.0)

        # Fault management with acknowledge/shelve lifecycle.
        # Wiring audit Pass 1 (F1.2 + F10.2): pass the live bus so
        # `fault.<subsystem>.<sev>` events from agent.report_fault()
        # actually reach EventLogger and the operator UI.
        # (F5.1): persist active fault set so a process bounce does
        # not silently clear an operator-acknowledged set of faults.
        from aria.safety.fault_manager import FaultManager
        self.fault_manager = FaultManager(
            bus=self.bus,
            persist_path="data/runtime/fault_manager.json",
        )

        # Ping-based health monitor for stuck agent detection.
        # Wiring audit Pass 1 (F1.1 + F10.1): pass the live bus so
        # health.warning / health.fatal events fire when a subsystem
        # crosses warn_cycles / fatal_cycles.
        from aria.safety.health_monitor import HealthMonitor
        self.health_monitor = HealthMonitor(bus=self.bus)
        self.event_log = EventLogger(self.bus)
        self.scratchpad = SharedScratchpad()
        self._agents: dict[str, AgentRecord] = {}
        self._running = False
        self._monitor_task: asyncio.Task[Any] | None = None
        self._checkpoint_task: asyncio.Task[Any] | None = None
        # Anomaly rate tracking for auto-safe-mode.
        # Wiring audit Pass 7 (F5.4) — wall-clock timestamps so they
        # persist meaningfully across restart. An attacker who has
        # accumulated 9 CRITICAL events in 4 minutes regains a fresh
        # budget on restart unless we re-load the window.
        self._recent_critical_timestamps: list[float] = []
        self._anomaly_storm_threshold = 10  # > 10 CRITICAL in 5 minutes
        self._anomaly_storm_window_s = 300.0
        self._load_anomaly_storm_state()

        # Wire checkpoint to pull system state.
        # Wiring audit Pass 1 (F11.3): use the public setter so a
        # future rename of the private attribute cannot silently
        # detach the provider.
        self.checkpoint.set_state_provider(self._build_checkpoint_state)

        # Cognitive engine — created lazily, wired to self.tools so the LLM
        # can call any registered tool during a reasoning request. Agents
        # emit `aria.agent.reasoning_request` events; `_on_reasoning_request`
        # routes them into `engine.reason()` and publishes the resulting
        # decision back on `aria.agent.reasoning_response.{agent}`.
        self._cognitive_engine: Any | None = None
        # AI decision trace ring buffer for the /api/ai/decisions UI.
        self._ai_decision_log: list[dict[str, Any]] = []
        self._AI_DECISION_LOG_MAX = 200

        # Recovery audit R-3: track consecutive cognitive-engine
        # failures so safe_mode.evaluate() can demote to
        # REDUCED_AUTONOMY at the configured threshold.
        self._ai_consecutive_errors: int = 0

        # Recovery audit R-11: progress proof for the health-monitor
        # loop.  External supervisor / hardware watchdog reads this to
        # confirm the loop is iterating.
        self._last_health_eval_monotonic: float = 0.0

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def is_running(self) -> bool:
        return self._running

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start ARIA — initialize bus, register tools, start agents."""
        logger.info("aria.starting", mission=self.config.mission_name)
        self.metrics.increment("aria.starts")

        # Step 0: Register shared resources for the execution guard
        self.resource_arbiter.register_resource("electrical_power_w", 45e6)  # 45 MWe reactor
        self.resource_arbiter.register_resource("thruster_fuel_kg", 5000.0)
        self.resource_arbiter.register_resource("comms_bandwidth_bps", 1e6)
        self.resource_arbiter.register_resource("crew_hours", 100.0)  # per tick cycle

        # Step 1: Start message bus
        await self.bus.start()

        # Step 2: Subscribe to system events
        self.bus.subscribe("aria.agent.*.heartbeat", self._on_agent_heartbeat)
        self.bus.subscribe("aria.anomaly.*", self._on_anomaly)
        # Wiring audit Pass 1 (F7.8) — `aria.thermal.sensor_failed` is
        # a P1_CRITICAL hardware-failure event published by ThermalAgent
        # when a thermistor crosses its warning band; previously it had
        # no FDIR / safe-mode subscriber. Route it through the same
        # anomaly handler so the recovery library + safe-mode evaluator
        # see it.
        self.bus.subscribe("aria.thermal.sensor_failed", self._on_anomaly)
        self.bus.subscribe("aria.emergency.*", self._on_emergency)
        self.bus.subscribe("aria.anomaly.correlation", self._on_correlation)
        self.bus.subscribe("aria.agent.reasoning_request", self._on_reasoning_request)
        # R38 — CIM / attestation / cross-monitor integrity faults request
        # safe-mode through a single topic. Honour it without polling.
        self.bus.subscribe("aria.safety.request_safe_mode", self._on_safe_mode_request)
        # Recovery audit R-8: physically enforce SURVIVAL on entry —
        # forces sun-pointing attitude, sheds non-critical loads, and
        # overrides heater min-on settings.  Without this subscriber,
        # SafeLevel.SURVIVAL is a label change with no actuator effect.
        self.bus.subscribe("aria.safety.mode_change", self._on_mode_change_actuators)

        # Start anomaly correlator, FDIR, and event logger
        await self.correlator.start()
        await self.fdir.start()
        await self.event_log.start()

        # Step 3: Restore last checkpoint if available.
        # Recovery audit R-9 + R-10: previously the restored dict was
        # logged then thrown away.  Now we apply mission_phase,
        # safe_mode_level, and per-agent restart_counts so the spacecraft
        # comes up in the same posture it crashed from.
        restored = self.checkpoint.restore_latest()
        if restored:
            logger.info("aria.checkpoint_restored", keys=list(restored.keys()))
            self.metrics.increment("aria.checkpoint_restores")
            self._apply_restored_state(restored)

        # Recovery audit R-4: load persisted restart counts BEFORE
        # starting agents so an agent that exhausted its budget last
        # session does not get fresh attempts on reboot.
        self._load_restart_state()

        # Step 4: Set initial state
        self.state.set("aria.status", "STARTING", updated_by="coordinator")
        self.state.set("aria.mission_phase", self.config.mission_phase, updated_by="coordinator")

        # Step 5: Start all registered agents
        for name, record in self._agents.items():
            try:
                await record.agent.start()
                record.registered_at = datetime.now(timezone.utc)
                logger.info("aria.agent_started", agent=name)
                self.metrics.increment("aria.agent_starts")
            except Exception as exc:
                logger.error("aria.agent_start_failed", agent=name, error=str(exc))
                self.metrics.increment("aria.agent_start_failures")

        # Step 6: Start background tasks
        self._running = True
        self._monitor_task = asyncio.create_task(self._health_monitor_loop())
        self._checkpoint_task = asyncio.create_task(self._checkpoint_loop())

        # Step 7: Failsafe-layer background services (F-13).
        # SafetyReplay runs the sealed test set every 6 h; drift fires
        # an emergency event the safety chain converts to safe-mode.
        #
        # Wiring audit Pass 7 (F10.6 + F12.1) — three compounding bugs
        # closed in this block:
        #   (a) the publish call used the simulator EventBus shape
        #       ``publish(topic=..., payload=..., priority=...)``
        #       against ``MessageBus.publish(message: Message)``
        #       (R-5 pattern reproduced — single positional Message);
        #   (b) ``asyncio.create_task`` was called from SafetyReplay's
        #       *daemon thread* (run_loop runs synchronous) which has
        #       no running event loop → RuntimeError (R-2 reproduced);
        #   (c) both errors were swallowed by the broad except, so the
        #       6-hourly drift alarm has been silently dropped since
        #       Pass 1 R-25 landed the public setter.
        # Capture the loop at start() and dispatch via
        # ``run_coroutine_threadsafe``, matching the R-1 / R-5
        # cross-thread publish pattern used elsewhere.
        try:
            _aria_loop = asyncio.get_running_loop()
        except RuntimeError:
            _aria_loop = None

        try:
            from aria.safety.safety_replay import get_safety_replay
            sr = get_safety_replay()

            def _on_drift(report: Any) -> None:
                logger.error("aria.safety_replay.drift_alarm",
                             fail_pct=report.fail_pct,
                             failures_count=len(report.failures))
                # Publish on the safety-emergency topic so anyone
                # subscribed (FDIR, safe-mode controller, kill switch
                # operator UI) sees it. Never raise out of the alarm.
                msg = Message(
                    topic="aria.emergency.safety_replay_drift",
                    payload={
                        "fail_pct": report.fail_pct,
                        "failures": list(report.failures)[:10],
                    },
                    priority=EventPriority.P0_EMERGENCY,
                    source_agent="coordinator",
                )
                try:
                    if _aria_loop is not None and _aria_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.bus.publish(msg), _aria_loop,
                        )
                    else:
                        # Fallback: try the running loop in this thread
                        # (only valid if _on_drift is called from the
                        # primary loop, e.g. in tests).
                        try:
                            asyncio.get_running_loop().create_task(
                                self.bus.publish(msg)
                            )
                        except RuntimeError:
                            logger.error(
                                "aria.safety_replay.no_loop_for_drift",
                                impact="drift alarm dropped — no loop captured",
                            )
                except Exception as exc:
                    logger.warning(
                        "aria.safety_replay.publish_failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )

            # Recovery audit R-25: use the public setter instead of
            # touching the leading-underscore attribute directly.
            sr.set_on_drift(_on_drift)
            sr.start(interval_s=6 * 60 * 60, run_immediately=False)
            logger.info("aria.failsafe.safety_replay_started")
        except Exception as exc:
            logger.warning("aria.failsafe.safety_replay_unavailable",
                           error=str(exc))

        self.state.set("aria.status", "RUNNING", updated_by="coordinator")
        logger.info(
            "aria.started",
            agents=list(self._agents.keys()),
            tools=self.tools.count,
        )

    async def stop(self) -> None:
        """Gracefully stop ARIA."""
        logger.info("aria.stopping")
        self._running = False

        # Stop failsafe background services started in start().
        try:
            from aria.safety.safety_replay import get_safety_replay
            get_safety_replay().stop()
        except Exception:
            pass

        # Final checkpoint before shutdown
        try:
            await self.checkpoint.save_now()
            logger.info("aria.final_checkpoint_saved")
        except Exception as exc:
            logger.error("aria.final_checkpoint_failed", error=str(exc))

        # Stop background tasks
        for task in [self._monitor_task, self._checkpoint_task]:
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        # Stop event logger, FDIR, and anomaly correlator
        await self.event_log.stop()
        await self.fdir.stop()
        await self.correlator.stop()

        # Stop agents in reverse order
        for name in reversed(list(self._agents.keys())):
            try:
                await self._agents[name].agent.stop()
            except Exception as exc:
                logger.error("aria.agent_stop_failed", agent=name, error=str(exc))

        # Stop bus
        await self.bus.stop()

        self.state.set("aria.status", "STOPPED", updated_by="coordinator")
        logger.info("aria.stopped")

    # --- Agent Management ---

    def register_agent(self, agent: SubsystemAgent) -> None:
        """Register an agent with the coordinator.

        Also wires the agent to the deterministic safety layer so it can
        report faults, dispatch tracked commands, and respond to health
        monitor pings. See SubsystemAgent.set_safety_context().
        """
        if agent.name in self._agents:
            raise ValueError(f"Agent '{agent.name}' already registered")

        # Inject safety modules into the agent
        try:
            agent.set_safety_context(
                fault_manager=self.fault_manager,
                command_tracker=self.command_tracker,
                execution_guard=self.execution_guard,
                health_monitor=self.health_monitor,
            )
        except AttributeError:
            # Older agents without set_safety_context — skip
            pass

        self._agents[agent.name] = AgentRecord(agent=agent)
        logger.info("aria.agent_registered", agent=agent.name)

    def get_agent(self, name: str) -> SubsystemAgent | None:
        """Get an agent by name."""
        record = self._agents.get(name)
        return record.agent if record else None

    async def restart_agent(self, name: str) -> bool:
        """Restart a failed agent."""
        record = self._agents.get(name)
        if not record:
            return False

        max_restarts = self.config.agent.max_restart_attempts
        if record.restart_count >= max_restarts:
            logger.error(
                "aria.agent_restart_exhausted",
                agent=name,
                attempts=record.restart_count,
            )
            self.metrics.increment("aria.agent_restart_exhausted")
            # Recovery audit R-4 + R-21: when an agent exhausts its
            # restart budget, request safe-mode demotion so the broader
            # system reflects the loss.  Without this, the agent
            # silently stays dead and health-score drift is the only
            # signal.
            await self.bus.publish(Message(
                topic="aria.safety.request_safe_mode",
                payload={
                    "reason": f"agent_restart_exhausted:{name}",
                    "target_level": "REDUCED_AUTONOMY",
                },
                priority=EventPriority.P0_EMERGENCY,
                source_agent="coordinator",
            ))
            return False

        logger.info("aria.agent_restarting", agent=name, attempt=record.restart_count + 1)
        self.metrics.increment("aria.agent_restarts")
        try:
            await record.agent.stop()
        except Exception as exc:
            # R65 (2026-04-24): was `except: pass` — swallowing stop()
            # failures silently left dangling tasks/sockets.  Now logged so
            # a broken agent stop surfaces in the metrics and log stream.
            logger.warning("aria.agent_stop_failed_before_restart",
                           agent=name, error=f"{type(exc).__name__}: {exc}")
            self.metrics.increment("aria.agent_stop_failed")

        # Recovery audit R-4: exponential backoff so a flapping agent
        # does not consume the budget in milliseconds.
        backoff = self.config.agent.restart_backoff_s * (2 ** record.restart_count)
        await asyncio.sleep(min(backoff, 60.0))

        try:
            await record.agent.start()
            record.restart_count += 1
            record.last_failed_at = time.time()
            self._save_restart_state()
            return True
        except Exception as exc:
            logger.error("aria.agent_restart_failed", agent=name, error=str(exc))
            record.restart_count += 1
            record.last_failed_at = time.time()
            self._save_restart_state()
            return False

    # --- Mission Phase Transition ---

    async def transition_phase(self, new_phase: str) -> bool:
        """Transition to a new mission phase.

        Updates authority level, logs the transition, and publishes event.
        Returns True if transition succeeded.
        """
        phase_config = PHASE_CONFIG.get(new_phase)
        if not phase_config:
            logger.error("aria.invalid_phase", phase=new_phase)
            return False

        old_phase = self.config.mission_phase
        if old_phase == new_phase:
            return True  # Already in this phase

        self.config.mission_phase = new_phase
        self.state.set("aria.mission_phase", new_phase, updated_by="coordinator")

        # Log transition
        self.event_log.log(
            category="STATE",
            severity="WARNING",
            source="coordinator",
            summary=f"Mission phase: {old_phase} → {new_phase}",
            payload={
                "old_phase": old_phase,
                "new_phase": new_phase,
                "authority": phase_config["authority"],
                "autonomy_level": phase_config["autonomy_level"],
                "active_agents": phase_config["active_agents"],
            },
        )

        # Publish event
        await self.bus.publish(
            Message(
                topic="aria.mission.phase_change",
                payload={
                    "old_phase": old_phase,
                    "new_phase": new_phase,
                    "authority": phase_config["authority"],
                    "description": phase_config.get("description", ""),
                },
                priority=EventPriority.P1_CRITICAL,
                source_agent="coordinator",
            )
        )

        logger.info(
            "aria.phase_transition",
            old=old_phase,
            new=new_phase,
            authority=phase_config["authority"],
        )

        return True

    # --- Event Handlers ---

    async def _on_agent_heartbeat(self, message: Message) -> None:
        """Process agent heartbeat — update state, track liveness."""
        agent_name = message.payload.get("name", "")
        if agent_name:
            self.state.set(
                f"aria.agents.{agent_name}.status",
                message.payload.get("status", "UNKNOWN"),
                updated_by="heartbeat",
            )
            self.state.set(
                f"aria.agents.{agent_name}.last_heartbeat",
                message.timestamp or "",
                updated_by="heartbeat",
            )
            self.metrics.increment("aria.heartbeats")

    async def _on_anomaly(self, message: Message) -> None:
        """Process anomaly events — classify and potentially escalate."""
        self.metrics.increment("aria.anomalies_received")

        severity_str = message.payload.get("severity", "NOMINAL")
        try:
            severity = Severity[severity_str]
        except KeyError:
            severity = Severity.NOMINAL

        # Log anomaly to state
        self.state.set(
            "aria.last_anomaly",
            {
                "severity": severity.name,
                "source": message.source_agent,
                "payload": message.payload,
                "timestamp": message.timestamp,
            },
            updated_by="coordinator",
        )

        # Track anomaly count per severity
        self.metrics.increment(f"aria.anomalies.{severity.name.lower()}")

        # Track CRITICAL+ anomaly rate for storm detection
        if severity.value >= Severity.CRITICAL.value:
            import time as _time
            now = _time.time()
            self._recent_critical_timestamps.append(now)
            cutoff = now - self._anomaly_storm_window_s
            self._recent_critical_timestamps = [
                t for t in self._recent_critical_timestamps if t >= cutoff
            ]
            # Wiring audit Pass 7 (F5.4) — persist so a process
            # bounce cannot reset the storm window.
            self._save_anomaly_storm_state()
            if len(self._recent_critical_timestamps) > self._anomaly_storm_threshold:
                logger.critical(
                    "coordinator.anomaly_storm",
                    count=len(self._recent_critical_timestamps),
                    window_s=self._anomaly_storm_window_s,
                )
                # Auto-escalate to safe mode
                new_level = self.safe_mode.evaluate(health_score=30.0)
                if new_level is not None:
                    await self.safe_mode.transition(new_level)

        # Escalate anomalies directly to captain (informational alerts, no approval needed).
        # The decision engine is used for actual decisions (maneuvers, load shedding)
        # that may need captain approval.
        if severity.value >= Severity.WARNING.value:
            await self.bus.publish(
                Message(
                    topic="aria.captain.alert",
                    payload={
                        "severity": severity.name,
                        "message": message.payload.get("message", "Anomaly detected"),
                        "source": message.source_agent,
                        "details": message.payload,
                    },
                    priority=EventPriority.P1_CRITICAL if severity == Severity.CRITICAL else EventPriority.P2_WARNING,
                    source_agent="coordinator",
                )
            )

    async def _on_correlation(self, message: Message) -> None:
        """Handle cross-channel correlation — high confidence root cause identified."""
        self.metrics.increment("aria.correlations")
        payload = message.payload
        root_cause = payload.get("root_cause", "UNKNOWN")
        severity = payload.get("severity", "WARNING")
        confidence = payload.get("confidence", 0.0)

        logger.warning(
            "coordinator.root_cause",
            root_cause=root_cause,
            severity=severity,
            confidence=confidence,
            channels=payload.get("involved_channels", []),
        )

        # Escalate high-confidence correlations to captain
        if confidence >= 0.80:
            await self.bus.publish(
                Message(
                    topic="aria.captain.alert",
                    payload={
                        "severity": severity,
                        "message": f"Root cause identified: {root_cause} (confidence={confidence:.0%})",
                        "description": payload.get("description", ""),
                        "recommendation": payload.get("recommendation", ""),
                        "involved_channels": payload.get("involved_channels", []),
                        "type": "root_cause_correlation",
                    },
                    priority=EventPriority.P1_CRITICAL if severity in ("CRITICAL", "EMERGENCY") else EventPriority.P2_WARNING,
                    source_agent="coordinator",
                )
            )

    def _get_cognitive_engine(self) -> Any:
        """Lazy-build the cognitive engine. Separate so tests can mock it."""
        if self._cognitive_engine is not None:
            return self._cognitive_engine
        try:
            from aria.cognitive.engine import CognitiveEngine, RuleBasedFallback, CloudLlmBackend
            import os
            backend = None
            # Prefer cloud LLM if an API key is present; fall back to rules.
            if os.environ.get("ANTHROPIC_API_KEY"):
                try:
                    backend = CloudLlmBackend()
                except Exception as exc:
                    logger.warning("cognitive.cloud_llm_init_failed", err=str(exc)[:120])
                    backend = RuleBasedFallback()
            else:
                backend = RuleBasedFallback()
            self._cognitive_engine = CognitiveEngine(
                tool_registry=self.tools,
                memory_store=None,
                llm_backend=backend,
                scratchpad=self.scratchpad,
            )
            logger.info("cognitive.engine_ready", backend=type(backend).__name__)
        except Exception as exc:
            logger.warning("cognitive.engine_unavailable", err=str(exc)[:200])
            self._cognitive_engine = None
        return self._cognitive_engine

    async def _on_reasoning_request(self, message: Message) -> None:
        """Agent reasoning request → CognitiveEngine → response published back.

        This is the real LLM decision loop. When an agent detects something
        complex (power anomaly under unknown cause, thermal runaway candidate,
        etc.) it publishes `aria.agent.reasoning_request` with its question and
        local context. The coordinator:

          1. Calls `engine.reason()` which runs the the LLM tool-use loop,
             calling any registered tool (get_power_budget, simulate_trajectory,
             get_hull_damage, …) and feeding the results back to the LLM.
          2. Publishes the final decision back on
             `aria.agent.reasoning_response.{agent_name}` so the requesting
             agent can act on it.
          3. Appends a trace summary to `_ai_decision_log` so the AI Decisions
             UI tab can show the full closed loop: question → tools called →
             response → agent that requested it.
        """
        self.metrics.increment("aria.reasoning_requests")
        agent_name = message.payload.get("agent", "unknown")
        question = message.payload.get("question", "")
        ctx_data = message.payload.get("context", {}) or {}

        # F-11 eval-vs-prod marker. The marker lives in this Python
        # frame and never enters the LLM context; the LLM cannot read
        # it, so it cannot deliberately behave differently in eval vs
        # prod. The kind is decided here based on whether the upstream
        # caller flagged this as eval traffic (e.g., the safety-replay
        # scheduler).
        try:
            from aria.cognitive.eval_marker import (
                mark_traffic, TrafficKind, get_sandbagging_detector,
            )
            is_eval = bool(ctx_data.get("_eval", False)) if isinstance(ctx_data, dict) else False
            _eval_mark = mark_traffic(TrafficKind.EVAL if is_eval else TrafficKind.PROD)
            _sandbagging = get_sandbagging_detector()
        except Exception:
            _eval_mark = None
            _sandbagging = None

        logger.info(
            "coordinator.reasoning_request",
            agent=agent_name,
            question=question[:100],
        )
        self.event_log.log(
            category="REASONING",
            severity="WARNING",
            source=agent_name,
            summary=f"Reasoning request: {question[:200]}",
            payload=message.payload,
        )

        engine = self._get_cognitive_engine()
        if engine is None:
            # No LLM available — ack the request so the caller isn't blocked.
            await self.bus.publish(Message(
                topic=f"aria.agent.reasoning_response.{agent_name}",
                payload={
                    "agent": agent_name,
                    "question": question,
                    "response": "Cognitive engine unavailable — continue rule-based fallback.",
                    "source": "none",
                    "tools_used": [],
                },
                priority=EventPriority.P3_ROUTINE,
                source_agent="coordinator",
            ))
            return

        # Build a ReasoningContext from the agent's payload. Authority defaults
        # to AGENT_RECOMMEND so tool invocations pass through the execution
        # guard rather than autonomously mutating shared state.
        try:
            from aria.cognitive.engine import ReasoningContext
            from aria.core.types import AuthorityLevel
            rctx = ReasoningContext(
                authority=AuthorityLevel.ADVISORY,
                active_alerts=ctx_data.get("alerts", []) if isinstance(ctx_data, dict) else [],
                system_state=ctx_data if isinstance(ctx_data, dict) else {},
                # Wiring audit Pass 3 (F1.14 full closure) — thread
                # the requesting agent through to the engine so the
                # capability-token mint can derive a real Principal.
                requesting_agent=agent_name or "",
            )
        except Exception:
            rctx = None

        # Run the LLM tool-use loop. The engine will call registered tools,
        # feed results back, and eventually return a text response.
        try:
            final_text = await engine.reason(
                input_text=question,
                context=rctx,
                trigger=f"agent:{agent_name}",
            )
            # Recovery audit R-3: success — reset the AI-error counter.
            self._ai_consecutive_errors = 0
        except Exception as exc:
            logger.error("coordinator.reasoning_failed",
                         agent=agent_name, err=str(exc)[:200])
            final_text = f"[reasoning failed: {type(exc).__name__}]"
            # Recovery audit R-3: count toward the demote-to-REDUCED_AUTONOMY
            # threshold (5).  evaluate() reads it next cycle.
            self._ai_consecutive_errors += 1

        trace = engine.traces[-1] if engine.traces else None
        tools_used = trace.tools_used if trace else []
        steps = len(trace.steps) if trace else 0

        # F-11 sandbagging observation — record (eval-marker, response,
        # parsed actions). The detector keeps rolling distributions and
        # publishes aria.safety.sandbagging_suspected when refusal-rate /
        # length / action-overlap diverges between eval and prod.
        if _eval_mark is not None and _sandbagging is not None:
            try:
                from aria.cognitive.action_executor import parse_recommendation
                actions = tuple(
                    i.action for i in parse_recommendation(final_text or "")
                )
                _sandbagging.observe(_eval_mark, final_text or "", actions)
                _sandbagging.maybe_publish_alert()
            except Exception as exc:
                logger.warning("coordinator.sandbagging_observe_failed",
                               error=str(exc))

        # Publish the decision back to the requesting agent. The agent's
        # reasoning_response handler (subscribed in base.py) will act on it.
        await self.bus.publish(Message(
            topic=f"aria.agent.reasoning_response.{agent_name}",
            payload={
                "agent": agent_name,
                "question": question,
                "response": final_text,
                "tools_used": tools_used,
                "steps": steps,
                "trace_id": trace.trace_id if trace else None,
                "source": "llm" if tools_used else "direct",
            },
            priority=EventPriority.P2_WARNING,
            source_agent="coordinator",
        ))

        # Append to the coordinator-local log …
        self._ai_decision_log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent_name,
            "question": question,
            "response": final_text,
            "tools_used": tools_used,
            "steps": steps,
            "trace_id": trace.trace_id if trace else None,
        })
        if len(self._ai_decision_log) > self._AI_DECISION_LOG_MAX:
            self._ai_decision_log = self._ai_decision_log[-self._AI_DECISION_LOG_MAX:]

        # … and also to the process-wide decision log consumed by the UI
        # `/api/ai/decisions` endpoint. The two are kept in sync so tests can
        # inspect the coordinator-local copy while the dashboard reads the
        # singleton.
        try:
            from aria.cognitive.decision_log import get_decision_log
            get_decision_log().append(
                source="agent",
                agent=agent_name,
                question=question,
                response=final_text,
                tools_used=tools_used,
                steps=steps,
                backend="llm" if tools_used else "rule",
                trace_id=trace.trace_id if trace else None,
            )
        except Exception:
            pass

        logger.info("coordinator.reasoning_complete",
                    agent=agent_name, steps=steps, tools=tools_used)

    def ai_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent AI decision traces (for /api/ai/decisions)."""
        return list(self._ai_decision_log[-limit:])

    async def _on_emergency(self, message: Message) -> None:
        """Handle emergency events — auto-transition to EMERGENCY phase."""
        self.metrics.increment("aria.emergencies")
        logger.critical(
            "aria.emergency_event",
            topic=message.topic,
            payload=message.payload,
        )

        # Auto-transition to EMERGENCY phase if not already there
        if self.config.mission_phase != "EMERGENCY":
            await self.transition_phase("EMERGENCY")

        # Force health re-evaluation immediately
        await self._evaluate_system_health()

    async def _on_mode_change_actuators(self, message: Message) -> None:
        """Recovery audit R-8: translate a SafeMode transition into
        the *physical* postures the level requires.  Previously
        ``transition()`` only updated state and published the event;
        no agent subscribed to physically enforce it, so SURVIVAL was
        a description-only state.
        """
        payload = message.payload or {}
        to_level = str(payload.get("to_level", ""))
        if to_level in ("MONITORING_ONLY", "SURVIVAL"):
            # Force sun-pointing attitude (CommsAgent + NavigationAgent).
            try:
                await self.bus.publish(Message(
                    topic="aria.command.gnc.safe_attitude",
                    payload={"target": "sun_point",
                             "reason": f"safe_mode_entry:{to_level}"},
                    priority=EventPriority.P0_EMERGENCY,
                    source_agent="coordinator",
                ))
            except Exception as exc:
                logger.warning("aria.mode_change.attitude_publish_failed",
                               error=str(exc))
            # Force load-shed to crit-only.
            try:
                await self.bus.publish(Message(
                    topic="aria.command.power.shed_loads",
                    payload={"level": 4 if to_level == "SURVIVAL" else 2,
                             "reason": f"safe_mode_entry:{to_level}",
                             "_envelope": {"verified": True,
                                           "source": "coordinator"}},
                    priority=EventPriority.P0_EMERGENCY,
                    source_agent="coordinator",
                ))
            except Exception as exc:
                logger.warning("aria.mode_change.shed_publish_failed",
                               error=str(exc))

    async def _on_safe_mode_request(self, message: Message) -> None:
        """R38 — honour an explicit safe-mode request from a security
        subsystem (CIM mismatch, attestation mismatch, cross-monitor
        disagreement, etc.).  Bypasses the health-score evaluator: the
        caller is asserting a tamper / integrity event has been
        detected, not a gradual degradation."""
        payload = message.payload or {}
        target = str(payload.get("target_level", "MONITORING_ONLY")).upper()
        try:
            level = SafeLevel[target]
        except KeyError:
            level = SafeLevel.MONITORING_ONLY
        reason = str(payload.get("reason", "request_safe_mode"))
        if level <= self.safe_mode.current_level:
            logger.info("aria.safe_mode_request_noop",
                        current=self.safe_mode.current_level.name,
                        requested=level.name)
            return
        logger.critical("aria.safe_mode_request",
                        target=level.name, reason=reason,
                        details=payload)
        await self.safe_mode.transition(level, reason=reason)

    # --- Health Monitoring ---

    async def _health_monitor_loop(self) -> None:
        """Periodic health check of all agents and system state.

        Recovery audit R-11: advance ``_last_health_eval_monotonic``
        every iteration so an external watchdog (and the systemd
        WatchdogSec=30 socket if configured) can detect a hung loop.
        Wraps the evaluator in ``asyncio.wait_for`` so a blocked
        downstream (e.g. tools health report) cannot freeze the
        coordinator's degradation monitor indefinitely.
        """
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                try:
                    await asyncio.wait_for(
                        self._evaluate_system_health(),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    logger.error("aria.health_monitor.eval_timeout",
                                 last_eval_monotonic=self._last_health_eval_monotonic)
                    self.metrics.increment("aria.health_monitor.timeouts")
                self._last_health_eval_monotonic = time.monotonic()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("aria.health_monitor_error", error=str(exc))

    async def _evaluate_system_health(self) -> None:
        """Compute health score, check safe mode, restart failed agents."""
        # Recovery audit R-22: run the ping-based health monitor so
        # stuck agents (deadlocked thread, infinite loop) escalate
        # through HealthMonitor.fatal_cycles → restart_agent → safe-mode.
        try:
            ping_results = self.health_monitor.check_all()
            fatal_subsystems = [
                name for name, state in ping_results.items()
                if state == "fatal"
            ]
            for name in fatal_subsystems:
                logger.error("aria.health_monitor.fatal", subsystem=name)
                await self.restart_agent(name)
        except Exception as exc:
            logger.warning("aria.health_monitor.check_failed", error=str(exc))

        # Collect agent statuses
        agent_statuses = {
            name: record.agent.status.name for name, record in self._agents.items()
        }

        # Restart any failed agents
        for name, record in list(self._agents.items()):
            if record.agent.status in (AgentStatus.ERROR, AgentStatus.STOPPED):
                logger.warning("aria.agent_unhealthy", agent=name, status=record.agent.status.name)
                await self.restart_agent(name)

        # Compute health report
        tool_health = self.tools.health_report()
        report = self.health_scorer.compute(
            agent_statuses=agent_statuses,
            tool_health=tool_health,
        )

        # Track health score as gauge
        self.metrics.gauge("aria.health_score", report.overall_score)

        # Update state with health report
        self.state.set("aria.health.score", report.overall_score, updated_by="health_monitor")
        self.state.set("aria.health.degraded", report.degraded_subsystems, updated_by="health_monitor")
        self.state.set("aria.health.critical", report.critical_subsystems, updated_by="health_monitor")
        self.state.set("aria.agents.statuses", agent_statuses, updated_by="health_monitor")
        self.state.set("aria.tools.health", tool_health, updated_by="health_monitor")

        # Get battery SoC from state (populated by PowerAgent)
        battery_soc = self.state.get("aria.power.battery_soc", 100.0)

        # Evaluate safe mode.  Recovery audit R-3 + R-21 — feed both
        # the consecutive-AI-error counter (so a dead cognitive engine
        # demotes to REDUCED_AUTONOMY) and the active-FDIR-fault count
        # (so the system tracks fault-storm severity, not just health
        # score).
        new_level = self.safe_mode.evaluate(
            health_score=report.overall_score,
            battery_soc=battery_soc,
            critical_subsystem_count=len(report.critical_subsystems),
            ai_consecutive_errors=self._ai_consecutive_errors,
            active_fdir_count=len(self.fdir.active_faults),
        )
        if new_level is not None:
            await self.safe_mode.transition(new_level)
            self.metrics.increment(f"aria.safe_mode.{new_level.name.lower()}")
            logger.warning(
                "aria.safe_mode_changed",
                level=new_level.name,
                health=report.overall_score,
                battery=battery_soc,
            )

            # Publish alert to captain
            await self.bus.publish(
                Message(
                    topic="aria.captain.alert",
                    payload={
                        "severity": "CRITICAL" if new_level >= SafeLevel.MONITORING_ONLY else "WARNING",
                        "message": f"Safe mode changed to {new_level.name}",
                        "health_score": report.overall_score,
                        "recommendation": report.recommendation,
                        "active_agents": list(self.safe_mode.config.active_agents),
                    },
                    priority=EventPriority.P1_CRITICAL,
                    source_agent="coordinator",
                )
            )

    # --- Checkpoint ---

    async def _checkpoint_loop(self) -> None:
        """Periodic state checkpointing."""
        # Wiring audit Pass 7 (F11.7) — use the public property; the
        # prior ``getattr(self.checkpoint, "_interval_s", 300)`` was a
        # double-bug: it reached into a private attribute, AND the
        # actual attribute is ``_interval`` (not ``_interval_s``), so
        # the loop ran at the 300s fallback regardless of configured
        # value.
        interval = self.checkpoint.interval_s
        while self._running:
            try:
                await asyncio.sleep(interval)
                cp = await self.checkpoint.save_now()
                self.metrics.increment("aria.checkpoints_saved")
                logger.debug("aria.checkpoint_saved", checkpoint_id=cp.checkpoint_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("aria.checkpoint_error", error=str(exc))

    def _build_checkpoint_state(self) -> dict[str, Any]:
        """Snapshot system state for checkpointing.

        Recovery audit R-10: schema previously held only six fields, so
        a restart lost FDIR history, kill-switch state, restart counts,
        AI-error counter, and dead-component list.  Expanded here.

        Wiring audit Pass 7 (F2.1) — the field set is intentionally
        ASYMMETRIC with ``_apply_restored_state``: the canonical store
        for these values is the sibling persistence files
        (``fault_manager.json``, ``agent_restart_state.json``,
        ``kill_switch.json``, ``fdir_history.jsonl``), which are loaded
        by their respective subsystems on construction and override
        anything in the checkpoint.  The fields below are FORENSIC —
        they let an operator inspect "what was the spacecraft doing
        when it last checkpointed" without crawling six files. The
        only fields ``_apply_restored_state`` re-applies are
        ``safe_mode_level``, ``mission_phase``, and
        ``ai_consecutive_errors``, because those have no sibling
        persistence path.
        """
        # Wiring audit Pass 7 (F6.14) — narrow the broad except so a
        # genuine kill_switch import failure surfaces rather than
        # silently recording ``{}`` for the most safety-critical
        # field. Only ``ImportError`` and ``OSError`` are recoverable
        # ("module not loaded", "state file missing"); anything else
        # is a programming bug we want to see.
        try:
            ks_state = self._kill_switch_snapshot()
        except (ImportError, OSError) as exc:
            logger.warning(
                "aria.checkpoint.kill_switch_snapshot_unavailable",
                error=f"{type(exc).__name__}: {exc}",
            )
            ks_state = {}
        return {
            "schema_version": 2,
            "saved_at": time.time(),
            "status": self.state.get("aria.status"),
            "mission_phase": self.state.get("aria.mission_phase"),
            "safe_mode_level": self.safe_mode.current_level.name,
            "health_score": self.state.get("aria.health.score"),
            "agent_statuses": {
                name: record.agent.status.name for name, record in self._agents.items()
            },
            "agent_restart_counts": {
                name: record.restart_count for name, record in self._agents.items()
            },
            "ai_consecutive_errors": self._ai_consecutive_errors,
            "fdir_active_faults": [
                {"fault_type": f.fault_type, "subsystem": f.subsystem,
                 "severity": f.severity, "detected_at": f.detected_at}
                for f in self.fdir.active_faults
            ],
            "kill_switch": ks_state,
            "metrics": self.metrics.snapshot(),
        }

    def _kill_switch_snapshot(self) -> dict[str, Any]:
        """Recovery audit R-15 helper: snapshot kill-switch state."""
        from aria.safety.kill_switch import get_kill_switch
        return get_kill_switch().to_dict()

    def _apply_restored_state(self, restored: dict[str, Any]) -> None:
        """Recovery audit R-9: re-enter the posture the spacecraft was
        in when the prior process exited.  Called BEFORE agents start
        so the safe-mode level (and therefore the active-agent list)
        is correctly applied on entry."""
        try:
            level_name = str(restored.get("safe_mode_level", "NOMINAL"))
            level = SafeLevel[level_name]
            if level != self.safe_mode.current_level:
                self.safe_mode.force_level(
                    level, reason="checkpoint_restore",
                )
                logger.warning("aria.checkpoint.safe_mode_restored",
                               level=level.name)
        except (KeyError, ValueError) as exc:
            logger.warning("aria.checkpoint.safe_mode_restore_failed",
                           error=str(exc))
        try:
            phase = str(restored.get("mission_phase", ""))
            if phase:
                self.config.mission_phase = phase
                self.state.set("aria.mission_phase", phase,
                               updated_by="checkpoint_restore")
        # Wiring audit Pass 7 (F6.15) — narrow the broad except. The
        # phase value comes from a JSON-deserialised string; the only
        # recoverable failure modes are dataclass / enum validation
        # (TypeError / ValueError) and the state-set call's possible
        # OSError. Anything else is a programming bug we want to see.
        except (TypeError, ValueError, OSError) as exc:
            logger.warning("aria.checkpoint.phase_restore_failed",
                           error=f"{type(exc).__name__}: {exc}")
        try:
            self._ai_consecutive_errors = int(
                restored.get("ai_consecutive_errors", 0),
            )
        except (TypeError, ValueError):
            self._ai_consecutive_errors = 0

    # ── Restart-count persistence (Recovery audit R-4) ──────────────

    def _restart_state_path(self) -> Path:
        env = os.environ.get("ARIA_RUNTIME_DIR")
        base = Path(env) if env else Path("data/runtime")
        return base / "agent_restart_state.json"

    def _load_restart_state(self) -> None:
        path = self._restart_state_path()
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("aria.restart_state.load_failed", error=str(exc))
            return
        # Decay: if last_failed_at is older than 1 h of clean uptime we
        # forgive the count so a one-off bad day doesn't shelve an agent
        # forever.
        now = time.time()
        for name, record in self._agents.items():
            entry = data.get(name) or {}
            last_failed = float(entry.get("last_failed_at", 0))
            count = int(entry.get("count", 0))
            if last_failed and now - last_failed > 3600:
                count = 0
            record.restart_count = count
            record.last_failed_at = last_failed

    # ── Anomaly-storm window persistence (F5.4) ─────────────────────

    def _anomaly_storm_state_path(self) -> Path:
        env = os.environ.get("ARIA_RUNTIME_DIR")
        base = Path(env) if env else Path("data/runtime")
        return base / "anomaly_storm_state.json"

    def _load_anomaly_storm_state(self) -> None:
        """Wiring audit Pass 7 (F5.4) — restore CRITICAL+ anomaly
        timestamps so the storm-window count survives restart."""
        path = self._anomaly_storm_state_path()
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("aria.anomaly_storm.load_failed", error=str(exc))
            return
        now = time.time()
        cutoff = now - self._anomaly_storm_window_s
        self._recent_critical_timestamps = [
            float(ts) for ts in data.get("timestamps", [])
            if isinstance(ts, (int, float)) and float(ts) >= cutoff
        ]

    def _save_anomaly_storm_state(self) -> None:
        path = self._anomaly_storm_state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            payload = {
                "timestamps": list(self._recent_critical_timestamps),
                "window_s": self._anomaly_storm_window_s,
                "threshold": self._anomaly_storm_threshold,
            }
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(payload, fp)
                fp.flush()
                try:
                    os.fsync(fp.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("aria.anomaly_storm.save_failed", error=str(exc))

    def _save_restart_state(self) -> None:
        path = self._restart_state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            payload = {
                name: {
                    "count": record.restart_count,
                    "last_failed_at": record.last_failed_at,
                }
                for name, record in self._agents.items()
            }
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
        except OSError as exc:
            logger.warning("aria.restart_state.save_failed", error=str(exc))

    # --- Public API ---

    def system_status(self) -> dict[str, Any]:
        """Complete system status for the Captain's console."""
        return {
            "status": self.state.get("aria.status", "UNKNOWN"),
            "mission": self.config.mission_name,
            "phase": self.config.mission_phase,
            "health_score": self.state.get("aria.health.score", 100.0),
            "safe_mode": self.safe_mode.current_level.name,
            "agents": {
                name: record.agent.stats for name, record in self._agents.items()
            },
            "tools": self.tools.health_report(),
            "bus": self.bus.stats,
            "metrics": self.metrics.snapshot(),
            "last_anomaly": self.state.get("aria.last_anomaly"),
            "event_log": self.event_log.summary(),
            "scratchpad_size": self.scratchpad.size,
            "fdir": {
                "active_faults": len(self.fdir.active_faults),
                "history_count": len(self.fdir.fault_history),
            },
            "correlator_events": len(self.correlator.get_recent_events()),
            "conflict_history": len(self.conflict_resolver.history),
            "pending_decisions": len(self.decision_engine.get_pending()),
        }

    def readiness_check(self) -> dict[str, Any]:
        """System readiness assessment — are we go for operations?"""
        agent_statuses = {
            name: record.agent.status.name for name, record in self._agents.items()
        }
        ready_agents = sum(1 for s in agent_statuses.values() if s == "READY")
        total = len(agent_statuses)
        tool_health = self.tools.health_report()

        issues: list[str] = []
        if ready_agents < total:
            not_ready = [n for n, s in agent_statuses.items() if s != "READY"]
            issues.append(f"Agents not ready: {not_ready}")
        if tool_health.get("circuit_breakers_open"):
            issues.append(f"Tools with open circuit breakers: {tool_health['circuit_breakers_open']}")
        if self.fdir.active_faults:
            issues.append(f"Active FDIR faults: {[f.fault_type for f in self.fdir.active_faults]}")

        go = len(issues) == 0
        return {
            "go_for_operations": go,
            "agents_ready": f"{ready_agents}/{total}",
            "issues": issues,
            "safe_mode": self.safe_mode.current_level.name,
            "health_score": self.state.get("aria.health.score", 100.0),
        }

    def diagnostics(self) -> dict[str, Any]:
        """Detailed diagnostics for system health verification."""
        agent_details = {}
        for name, record in self._agents.items():
            agent_details[name] = {
                "status": record.agent.status.name,
                "restart_count": record.restart_count,
                "registered_at": record.registered_at.isoformat() if record.registered_at else None,
                "heartbeat_interval_s": record.agent.heartbeat_interval_s,
                "messages_processed": record.agent._messages_processed,
            }

        return {
            "status": self.state.get("aria.status", "UNKNOWN"),
            "uptime_components": {
                "bus": self.bus.stats,
                "agents": agent_details,
                "tools": self.tools.health_report(),
                "fdir_active_faults": len(self.fdir.active_faults),
                "fdir_history_count": len(self.fdir.fault_history),
                "correlator_recent_events": len(self.correlator.get_recent_events()),
                "event_log_total": self.event_log.event_count,
                "scratchpad_entries": self.scratchpad.size,
                "conflict_history": len(self.conflict_resolver.history),
                "decision_pending": len(self.decision_engine.get_pending()),
            },
            "health": {
                "score": self.state.get("aria.health.score", 100.0),
                "safe_mode": self.safe_mode.current_level.name,
                "degraded": self.state.get("aria.health.degraded", []),
                "critical": self.state.get("aria.health.critical", []),
            },
        }
