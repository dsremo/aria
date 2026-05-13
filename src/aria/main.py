"""ARIA Main Entry Point — wire up and launch the entire system.

Usage:
    python -m aria.main
    python -m aria.main --config configs/aria.yaml
    python -m aria.main --simulate          # Run with sensor simulator (dev mode)
    python -m aria.main --config ... --simulate
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path

import structlog

from aria.api.server import AriaAPIServer
from aria.agents.comms import CommsAgent
from aria.agents.eclss import EclssAgent
from aria.agents.medical import MedicalAgent
from aria.agents.navigation import NavigationAgent
from aria.agents.power import PowerAgent
from aria.agents.propulsion import PropulsionAgent
from aria.agents.science import ScienceAgent
from aria.agents.telemetry import TelemetryAgent
from aria.agents.thermal import ThermalAgent
from aria.cognitive.engine import CloudLlmBackend, CognitiveEngine, ReasoningContext
from aria.bus.message_bus import Message
from aria.core.types import EventPriority, MissionPhase
from aria.core.config import AriaConfig
from aria.core.console import CaptainConsole
from aria.core.coordinator import AriaCoordinator
from aria.core.simulator import SensorSimulator
from aria.integrations.conjunction_watch.tools import (
    ConjunctionWatchGetHighRisk,
    ConjunctionWatchPlanManeuver,
    ConjunctionWatchRunScreening,
)
from aria.integrations.dsremo.websocket_tool import DsremoWebSocketSubscribe, DsremoWebSocketUnsubscribe
from aria.integrations.dsremo.tools import (
    DsremoGetAnomalyScore,
    DsremoGetChannelHealth,
    DsremoGetChannels,
    DsremoIngestBatch,
    DsremoIngestTelemetry,
    DsremoQueryAnomalies,
)
from aria.integrations.control_tools import ALL_CONTROL_TOOLS
from aria.integrations.extended_tools import ALL_EXTENDED_TOOLS
from aria.integrations.genastra.tools import (
    GenAstraAnalyzeBiosignature,
    GenAstraCrewRadiationDose,
)
from aria.knowledge.procedures import load_default_procedures
from aria.memory.store import MemoryStore

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger()

BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║     █████╗ ██████╗ ██╗ █████╗                                    ║
║    ██╔══██╗██╔══██╗██║██╔══██╗                                   ║
║    ███████║██████╔╝██║███████║                                    ║
║    ██╔══██║██╔══██╗██║██╔══██║                                    ║
║    ██║  ██║██║  ██║██║██║  ██║                                    ║
║    ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═╝                                    ║
║                                                                  ║
║    Autonomous Reasoning & Integration Architecture               ║
║    Central AI for SpaceAi Spacecraft Platform                    ║
║    v0.4.0  |  Phases 1-4 Complete                               ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""


async def run(config_path: str = "configs/aria.yaml", simulate: bool = False) -> None:
    """Initialize and run ARIA."""
    print(BANNER)

    # ── Configuration ──────────────────────────────────────────────────────
    try:
        config = AriaConfig.from_yaml(config_path)
        logger.info("aria.config_loaded", path=config_path)
    except FileNotFoundError:
        logger.warning("config.not_found", path=config_path, msg="Using defaults")
        config = AriaConfig()

    # Ensure data directories exist
    Path("data/checkpoints").mkdir(parents=True, exist_ok=True)
    Path("data/memory").mkdir(parents=True, exist_ok=True)

    # ── Core Systems ───────────────────────────────────────────────────────
    coordinator = AriaCoordinator(config)

    # Memory and knowledge
    memory = MemoryStore(persist_dir="data/memory")
    proc_count = load_default_procedures(memory)
    logger.info("aria.procedures_loaded", count=proc_count)

    # Cognitive engine — activates when ANTHROPIC_API_KEY is set (otherwise rule-based)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    llm_backend = CloudLlmBackend(api_key=api_key) if api_key else None
    cognitive = CognitiveEngine(
        tool_registry=coordinator.tools,
        memory_store=memory,
        llm_backend=llm_backend,
        system_status_fn=coordinator.system_status,
        scratchpad=coordinator.scratchpad,
    )

    # ── Tools ──────────────────────────────────────────────────────────────
    # Dsremo anomaly detection
    dsremo_url = config.dsremo.base_url
    dsremo_key = config.dsremo.api_key
    coordinator.tools.register(DsremoQueryAnomalies(base_url=dsremo_url, api_key=dsremo_key))
    coordinator.tools.register(DsremoIngestTelemetry(base_url=dsremo_url, api_key=dsremo_key))
    coordinator.tools.register(DsremoGetChannels(base_url=dsremo_url, api_key=dsremo_key))
    coordinator.tools.register(DsremoIngestBatch(base_url=dsremo_url, api_key=dsremo_key))
    coordinator.tools.register(DsremoGetChannelHealth(base_url=dsremo_url, api_key=dsremo_key))
    coordinator.tools.register(DsremoGetAnomalyScore(base_url=dsremo_url, api_key=dsremo_key))
    coordinator.tools.register(DsremoWebSocketSubscribe(ws_url=config.dsremo.websocket_url))
    coordinator.tools.register(DsremoWebSocketUnsubscribe())

    # ConjunctionWatch orbital collision avoidance
    coordinator.tools.register(ConjunctionWatchRunScreening())
    coordinator.tools.register(ConjunctionWatchGetHighRisk())
    coordinator.tools.register(ConjunctionWatchPlanManeuver())

    # GenAstra astrobiology + radiation
    genastra_url = config.genastra.base_url
    coordinator.tools.register(GenAstraCrewRadiationDose(base_url=genastra_url))
    coordinator.tools.register(GenAstraAnalyzeBiosignature(base_url=genastra_url))

    # Control, emergency, diagnostic, planning, crew tools
    for tool_cls in ALL_CONTROL_TOOLS:
        coordinator.tools.register(tool_cls())

    # Extended tools (navigation, science, learning, planning)
    for tool_cls in ALL_EXTENDED_TOOLS:
        coordinator.tools.register(tool_cls())

    logger.info("aria.tools_registered", total=coordinator.tools.count)

    # ── Agents ─────────────────────────────────────────────────────────────
    sp = coordinator.scratchpad
    telemetry_agent = TelemetryAgent(bus=coordinator.bus, tool_registry=coordinator.tools, scratchpad=sp)
    power_agent = PowerAgent(bus=coordinator.bus, tool_registry=coordinator.tools, scratchpad=sp)
    nav_agent = NavigationAgent(bus=coordinator.bus, tool_registry=coordinator.tools, scratchpad=sp)
    thermal_agent = ThermalAgent(bus=coordinator.bus, tool_registry=coordinator.tools, scratchpad=sp)
    eclss_agent = EclssAgent(bus=coordinator.bus, tool_registry=coordinator.tools, scratchpad=sp)
    propulsion_agent = PropulsionAgent(bus=coordinator.bus, tool_registry=coordinator.tools, scratchpad=sp)
    comms_agent = CommsAgent(bus=coordinator.bus, tool_registry=coordinator.tools, scratchpad=sp)
    science_agent = ScienceAgent(bus=coordinator.bus, tool_registry=coordinator.tools, scratchpad=sp)
    medical_agent = MedicalAgent(bus=coordinator.bus, tool_registry=coordinator.tools, scratchpad=sp)

    coordinator.register_agent(telemetry_agent)
    coordinator.register_agent(power_agent)
    coordinator.register_agent(nav_agent)
    coordinator.register_agent(thermal_agent)
    coordinator.register_agent(eclss_agent)
    coordinator.register_agent(propulsion_agent)
    coordinator.register_agent(comms_agent)
    coordinator.register_agent(science_agent)
    coordinator.register_agent(medical_agent)

    # ── Simulator (dev mode) ───────────────────────────────────────────────
    simulator: SensorSimulator | None = None
    if simulate:
        simulator = SensorSimulator(coordinator.bus)
        simulator.add_default_sensors()
        logger.info("aria.simulator_enabled", sensors=len(simulator._sensors))

    # ── Captain's Console ──────────────────────────────────────────────────
    # R65 (2026-04-24) B-1: if ARIA_SHARED_SECRET is missing, generate a
    # per-process random secret and WARN loudly — we never silently
    # accept the old placeholder "aria-spacecraft-secret-change-me"
    # because that was trivially guessable.  Production must set the env
    # var; a dev can still run without one, they just lose cross-restart
    # session continuity.
    shared_secret = os.environ.get("ARIA_SHARED_SECRET", "").strip()
    # TT&C audit M-2 — production mode refuses to auto-generate a
    # secret.  Operators must set ARIA_SHARED_SECRET explicitly so
    # multi-process deploys and post-restart reconnects share the
    # same key.  Dev / test still autogen with a loud warning.
    _is_production = (
        os.environ.get("ARIA_ENVIRONMENT", "").lower() == "production"
    )
    if not shared_secret:
        if _is_production:
            raise SystemExit(
                "aria.shared_secret_missing — ARIA_ENVIRONMENT=production "
                "requires ARIA_SHARED_SECRET to be set explicitly "
                "(>= 32 bytes; not on the banned-defaults list)"
            )
        import secrets as _secrets
        shared_secret = _secrets.token_urlsafe(48)
        logger.warning(
            "aria.shared_secret_autogen",
            impact="ARIA_SHARED_SECRET env var unset — generated a random per-process secret; set it explicitly for production",
        )
    console = CaptainConsole(
        bus=coordinator.bus,
        system_status_fn=coordinator.system_status,
        shared_secret=shared_secret,
    )

    # ── API Server (web dashboard) ────────────────────────────────────────
    # R65 (2026-04-24) B-3: validate port bounds so a typo'd env var
    # doesn't let the server bind to port 0 (any port — unreliable) or
    # a negative value that crashes at bind time with a confusing error.
    def _parse_port(env_name: str, default: int) -> int:
        raw = os.environ.get(env_name)
        if raw is None:
            return default
        try:
            n = int(raw)
        except ValueError:
            raise SystemExit(f"{env_name}={raw!r} is not an integer")
        if not 1024 <= n <= 65535:
            raise SystemExit(f"{env_name}={n} out of range (must be 1024-65535)")
        return n

    api_host = os.environ.get("ARIA_API_HOST", config.api.host)
    api_http_port = _parse_port("ARIA_API_HTTP_PORT", config.api.http_port)
    api_ws_port   = _parse_port("ARIA_API_WS_PORT",   config.api.ws_port)
    # TT&C audit C-3 / L-1 / L-2 — production mode flips the API into
    # mandatory-envelope authentication and enforces the Origin allow-list.
    _allowed_ws_origins = {
        origin.strip()
        for origin in os.environ.get("ARIA_API_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    } or None
    api_server = AriaAPIServer(
        bus=coordinator.bus,
        system_status_fn=coordinator.system_status,
        shared_secret=shared_secret,
        host=api_host,
        http_port=api_http_port,
        ws_port=api_ws_port,
        event_log=coordinator.event_log,
        scratchpad=coordinator.scratchpad,
        production_mode=_is_production,
        legacy_bearer_only=not _is_production,
        allowed_origins=_allowed_ws_origins,
    )

    # ── Ground dead-man watchdog (TT&C audit D-3) ────────────────────────
    from aria.safety.ground_deadman import (
        GroundDeadmanWatchdog,
        PHASE_SILENCE_THRESHOLDS_S,
        DEFAULT_SILENCE_THRESHOLD_S,
    )
    from aria.safety.safe_mode import (
        SafeLevel,
        get_safe_mode_singleton,
        set_safe_mode_singleton,
    )
    _silence_threshold = PHASE_SILENCE_THRESHOLDS_S.get(
        config.mission_phase, DEFAULT_SILENCE_THRESHOLD_S,
    )

    # Recovery audit R-1: register the coordinator's SafeModeManager so
    # off-loop threads can reach it.
    set_safe_mode_singleton(coordinator.safe_mode)

    # Capture the running loop now so threaded watchdogs can
    # ``run_coroutine_threadsafe`` onto it (Recovery audit R-2).
    _aria_loop = asyncio.get_running_loop()

    def _on_ground_silence(age_s: float) -> None:
        sm = get_safe_mode_singleton()
        if sm is None:
            logger.error("ground_silence.no_safe_mode_singleton")
            return
        try:
            sm.force_level(SafeLevel.MONITORING_ONLY,
                           reason=f"ground_silence:{age_s:.0f}s")
        except Exception as exc:    # noqa: BLE001
            logger.error("ground_silence.force_safe_failed", error=str(exc))

    def _ground_deadman_publish(topic: str, payload: dict) -> None:
        # Recovery audit R-2: watchdog runs on a daemon thread; schedule
        # the async publish on the captured event loop instead of
        # ``asyncio.create_task`` (which raises in non-loop threads).
        try:
            asyncio.run_coroutine_threadsafe(
                coordinator.bus.publish(Message(
                    topic=topic, payload=payload,
                    source_agent="ground_deadman",
                )),
                _aria_loop,
            )
        except Exception as exc:    # noqa: BLE001
            logger.error("ground_deadman.publish_failed",
                         topic=topic, error=str(exc))

    ground_deadman = GroundDeadmanWatchdog(
        on_silence=_on_ground_silence,
        publish_fn=_ground_deadman_publish,
        silence_threshold_s=_silence_threshold,
    )

    # ── Wire cognitive engine to bus ───────────────────────────────────────
    # TT&C audit C-4: every aria.captain.query payload must carry a
    # ``_envelope`` block whose ``verified`` flag is True (HTTP/WS path
    # set this after passing CommandAuthenticator + ReplayGuard).
    # Console-originated messages mark themselves as ``console``; the
    # console runs in-process and is already authenticated by the
    # CommandAuthenticator at command-issue time.
    _PRODUCTION_MODE_API = (
        os.environ.get("ARIA_ENVIRONMENT", "").lower() == "production"
    )

    async def _handle_captain_query(msg):  # type: ignore[no-untyped-def]
        text = msg.payload.get("text", "")
        envelope = msg.payload.get("_envelope") or {}
        source = msg.payload.get("source", "")
        if not text:
            return

        # Console runs in-process; trust the local stdin-bound source.
        # Any wire-originated message MUST present a verified envelope
        # in production mode.  Non-production keeps legacy behaviour
        # so existing tests / dev workflows continue to function.
        wire_source = source in ("api", "ws")
        if wire_source and _PRODUCTION_MODE_API and not envelope.get("verified"):
            logger.warning(
                "captain_query_unverified_blocked",
                source=source,
                hint="production mode requires a signed envelope",
            )
            return

        # TT&C audit D-3 — verified ground commands extend the
        # dead-man window; unverified / console commands do not.
        if envelope.get("verified"):
            ground_deadman.record_handshake()

        try:
            phase = MissionPhase[config.mission_phase]
        except KeyError:
            phase = MissionPhase.NOMINAL_LEO
        ctx = ReasoningContext(mission_phase=phase)
        response = await cognitive.reason(
            input_text=text,
            context=ctx,
            trigger="captain_query",
        )
        print(f"\n  [ARIA] {response}\n  ARIA> ", end="", flush=True)

    # ── Wire agent reasoning requests to cognitive engine ────────────────
    async def _handle_agent_reasoning(msg):  # type: ignore[no-untyped-def]
        """Route agent reasoning requests to the cognitive engine.

        Agents publish to aria.agent.reasoning_request when they encounter
        situations beyond threshold logic (e.g., correlated anomalies across
        subsystems, ambiguous sensor readings, resource trade-off decisions).
        The cognitive engine reasons about it and publishes the response back
        so the requesting agent (and coordinator) can act on it.
        """
        agent_name = msg.payload.get("agent", "unknown")
        question = msg.payload.get("question", "")
        context = msg.payload.get("context", {})
        if not question:
            return
        try:
            phase = MissionPhase[config.mission_phase]
        except KeyError:
            phase = MissionPhase.NOMINAL_LEO
        ctx = ReasoningContext(
            mission_phase=phase,
            system_state=context,
        )
        response = await cognitive.reason(
            input_text=f"[{agent_name}] {question}",
            context=ctx,
            trigger=f"agent_{agent_name}",
        )
        # Publish response back to the requesting agent and coordinator
        await coordinator.bus.publish(Message(
            topic=f"aria.agent.reasoning_response.{agent_name}",
            payload={
                "agent": agent_name,
                "question": question,
                "response": response,
                "source": "cognitive_engine",
            },
            priority=EventPriority.P2_WARNING,
        ))
        logger.info(
            "cognitive.agent_reasoning",
            agent=agent_name,
            question=question[:100],
            response=response[:200] if response else "",
        )

    # ── Register physics sandbox tools for novel-situation reasoning ─────
    try:
        from aria.tools.physics_sandbox import register_physics_sandbox
        register_physics_sandbox(coordinator.tools)
        logger.info("physics_sandbox.registered", tools=3)
    except Exception as e:
        logger.warning("physics_sandbox.register_failed", error=str(e))

    # ── Start Everything ───────────────────────────────────────────────────
    await coordinator.start()

    coordinator.bus.subscribe("aria.captain.query", _handle_captain_query)
    coordinator.bus.subscribe("aria.agent.reasoning_request", _handle_agent_reasoning)

    # R38 — continuous integrity monitor (CIM).  Runs in a daemon thread.
    # Mismatch publishes both `aria.security.cim_mismatch` (audit) and
    # `aria.safety.request_safe_mode` (safe-mode trigger) on the
    # coordinator's bus via run_coroutine_threadsafe.
    try:
        from aria.security.integrity_monitor import start_integrity_monitor

        loop = asyncio.get_running_loop()

        def _coord_publish(topic: str, payload: dict) -> None:
            msg = Message(
                topic=topic,
                payload=dict(payload),
                priority=EventPriority.P0_EMERGENCY,
                source_agent="cim",
            )
            asyncio.run_coroutine_threadsafe(
                coordinator.bus.publish(msg), loop,
            )

        def _on_cim_mismatch(report: dict) -> None:
            _coord_publish("aria.safety.request_safe_mode", {
                "reason": "cim_mismatch",
                "target_level": "MONITORING_ONLY",
                "report": report,
            })

        start_integrity_monitor(
            on_mismatch=_on_cim_mismatch,
            publish_fn=_coord_publish,
        )
        logger.info("aria.cim.started")

        # R38 §1.4 — periodic Merkle-root anchor downlink (1 h cadence).
        from aria.security.audit_downlink import start_audit_downlink
        start_audit_downlink(
            publish_fn=_coord_publish,
            safe_mode_level_provider=lambda: coordinator.safe_mode.current_level.name,
        )
        logger.info("aria.audit_downlink.started")

        # R38 §1.2 + FUTURE_DIRECTIONS_2026 #3 — cross-vendor monitor.
        # Auto-selects the strongest provider available on this host:
        #   1. OllamaCrossCheckProvider (true cross-vendor; needs Ollama
        #      + a model pulled — see docs/CROSS_VENDOR_MONITOR_SETUP.md)
        #   2. LlmCliAuditorProvider (same-vendor; works today via
        #      the LLM CLI; logs same_vendor warning)
        #   3. StubCrossCheckProvider (default-approve; dev only)
        # The bus publish_fn lets the monitor surface disagreements /
        # unavailability through the same trace pipeline.
        from aria.monitor.cross_check import (
            configure as _xc_configure,
            get_cross_vendor_monitor,
        )
        from aria.monitor.providers import best_available_provider
        _xc_configure(
            publish_fn=_coord_publish,
            provider=best_available_provider(),
        )

        # Wiring audit Pass 1 (F8.3) — wire the disagreement-storm
        # alarm. When N cross-vendor disagreements land within the
        # window, force REDUCED_AUTONOMY (primary may be drifting).
        async def _on_cross_disagreement_storm(message):
            sm = get_safe_mode_singleton()
            if sm is None:
                return
            try:
                sm.force_level(
                    SafeLevel.REDUCED_AUTONOMY,
                    reason=(
                        "cross_disagreement_storm:"
                        f"{(message.payload or {}).get('window_count', 0)}"
                        f"/{(message.payload or {}).get('threshold', 0)}"
                    ),
                )
            except Exception as exc:    # noqa: BLE001
                logger.warning(
                    "cross_disagreement.safe_mode_escalation_failed",
                    error=str(exc),
                )

        coordinator.bus.subscribe(
            "aria.safety.cross_disagreement_storm",
            _on_cross_disagreement_storm,
        )

        def _xc_alarm_publish(topic, payload):
            publish_compat(
                coordinator.bus,
                topic,
                severity="critical",
                source="cross_check",
                payload=payload,
            )

        get_cross_vendor_monitor().set_disagreement_alarm_fn(_xc_alarm_publish)
        logger.info("aria.cross_vendor_monitor.configured")
    except Exception as exc:
        logger.error("aria.r38.start_failed", error=str(exc))

    if simulator:
        await simulator.start()

    await console.start()
    # Wiring audit Pass 7 (F11.6) — use the public setters instead of
    # poking the leading-underscore attribute. Also wires the typed
    # readiness callable (F11.4).
    api_server.set_diagnostics_fn(coordinator.diagnostics)
    if hasattr(coordinator, "readiness_check"):
        api_server.set_readiness_fn(coordinator.readiness_check)
    await api_server.start()
    ground_deadman.start()

    # Recovery audit R-13: schedule boot-success marker.  After the
    # grace window of nominal loop iteration, the boot attempt counter
    # is reset.  A crash before this fires leaves the "started"
    # tombstone in boot.history and counts toward the crash-loop
    # threshold.
    from aria.safety.boot_counter import schedule_success_marker
    schedule_success_marker(_aria_loop)

    # Recovery audit R-17 + Wiring audit Pass 1 (F14.4): the heartbeat
    # watcher only makes sense when a separate monitor process is
    # actually running and emitting heartbeats. Previously the watcher
    # was started unconditionally, but no `aria.monitor.runner` process
    # exists yet — so 30 s after every fresh boot the on_silence
    # callback fired and forced SafeLevel.MONITORING_ONLY.  The watcher
    # is now gated on explicit configuration:
    #
    #   ARIA_MONITOR_EMITTER_URL — HTTP/socket address of the monitor
    #                              sidecar that will POST heartbeats to
    #                              the primary's bus ingest endpoint.
    #
    # In production we refuse to start without this — running the
    # primary without an independent monitor defeats the §F-7
    # architecture and the T-V-2 threat model.  In development we skip
    # the watcher with a loud warning so unit tests / local runs boot
    # cleanly.
    # Wiring audit Pass 1 (F14.2 + F7.3): the bus-anomaly detector
    # was a fully-implemented BOCPD-style "low-and-slow drain"
    # monitor that observed nothing because nobody called observe().
    # Subscribe a wildcard handler so every aria.* event is fed in,
    # and route the detector's findings back onto the bus where
    # operators can see them.  Self-published events from the
    # detector are filtered out at the input to break the feedback
    # loop, and a broad except keeps the observer callback from ever
    # crashing the dispatcher.
    from aria.safety.bus_anomaly import BusAnomalyMonitor
    from aria.safety._bus_publish import publish_compat

    bus_anomaly_monitor = BusAnomalyMonitor(
        publish_fn=lambda topic, payload: publish_compat(
            coordinator.bus,
            topic,
            severity="warning",
            source="bus_anomaly",
            payload=payload,
        ),
    )

    async def _bus_anomaly_observer(message):
        try:
            if message.source_agent == "bus_anomaly":
                return  # break self-feedback
            bus_anomaly_monitor.observe(
                source=message.source_agent or "unknown",
                topic=message.topic,
            )
        except Exception as exc:    # noqa: BLE001
            logger.warning("bus_anomaly.observe_failed", error=str(exc))

    coordinator.bus.subscribe("aria.*", _bus_anomaly_observer)
    logger.info("aria.bus_anomaly.wired",
                window_s=getattr(bus_anomaly_monitor, "_window_s", None))

    # Wiring audit Pass 1 (F6.2 + F10.4): configure the IncidentRegistry
    # singleton with a publish callable that routes through the
    # production MessageBus adapter.  Previously the singleton wired
    # itself to ``aria.simulator.event_bus`` only, which silently
    # dropped every incident in production deploys without the
    # simulator package.
    from aria.safety.incident_registry import configure_incident_registry

    def _incident_publish(topic, payload):
        publish_compat(
            coordinator.bus,
            topic,
            severity="warning",
            source="incident_registry",
            payload=payload,
        )

    configure_incident_registry(publish_fn=_incident_publish)
    logger.info("aria.incident_registry.wired")

    # Wiring audit Pass 3 (F1.12 + F7.9): the SandbaggingDetector
    # singleton was constructed with a no-op publish_fn, so every
    # "suspect" verdict went into the void. Plumb the bus through
    # ``configure_sandbagging_detector``, late-binding if the
    # singleton has already been auto-created upstream.
    from aria.cognitive.eval_marker import configure_sandbagging_detector
    from aria.core.types import EventPriority as _EventPriority

    def _sandbagging_publish(topic, payload):
        publish_compat(
            coordinator.bus,
            topic,
            severity="critical",
            source="sandbagging_detector",
            payload=payload,
        )

    configure_sandbagging_detector(publish_fn=_sandbagging_publish)
    logger.info("aria.sandbagging_detector.wired")

    # Wiring audit Pass 3 (F7.9): subscribe safe_mode escalation to
    # ``aria.safety.sandbagging_suspected``. Without this, even with
    # the publisher wired, the alarm reaches the bus but no FDIR /
    # safe-mode handler reacts — same shape as other "alarm into the
    # void" findings.
    async def _on_sandbagging_suspected(message):
        sm = get_safe_mode_singleton()
        if sm is None:
            return
        try:
            sm.force_level(
                SafeLevel.REDUCED_AUTONOMY,
                reason=f"sandbagging_suspected:{(message.payload or {}).get('reason', '')}",
            )
        except Exception as exc:    # noqa: BLE001
            logger.warning(
                "sandbagging.safe_mode_escalation_failed", error=str(exc),
            )

    coordinator.bus.subscribe(
        "aria.safety.sandbagging_suspected", _on_sandbagging_suspected,
    )

    # Wiring audit Pass 3 (F7.10): subscribe ``aria.security.cim_mismatch``
    # to the same safe-mode escalation. The IntegrityMonitor's
    # on_mismatch callback (wired separately at line 451) is one path;
    # this is belt-and-suspenders so a callback misconfiguration
    # cannot silently disable R38 §1.1.
    async def _on_cim_mismatch(message):
        sm = get_safe_mode_singleton()
        if sm is None:
            return
        try:
            sm.force_level(
                SafeLevel.REDUCED_AUTONOMY,
                reason="cim_mismatch_bus_subscriber",
            )
        except Exception as exc:    # noqa: BLE001
            logger.warning(
                "cim_mismatch.safe_mode_escalation_failed", error=str(exc),
            )

    coordinator.bus.subscribe("aria.security.cim_mismatch", _on_cim_mismatch)

    # Wiring audit Pass 3 (F6.9): plumb the bus into the audit-bus
    # mirror so a sustained audit-chain break publishes a structured
    # ``aria.security.audit_mirror_failed`` alert rather than only
    # appearing in the error log.
    from aria.security.audit_bus_mirror import get_audit_bus_mirror

    def _audit_mirror_alert(topic, payload):
        publish_compat(
            coordinator.bus,
            topic,
            severity="critical",
            source="audit_bus_mirror",
            payload=payload,
        )

    get_audit_bus_mirror().set_alert_publish_fn(_audit_mirror_alert)
    logger.info("aria.audit_bus_mirror.alert_wired")

    # Wiring audit Pass 3 (F1.13): mint the internal-channel token
    # exactly once at boot so any agent presenting it gets through
    # ``CommandAuthenticator.authenticate(...)``. Without this,
    # ``verify_internal_channel_token`` always returns False because
    # the token bytes are None, and any future internal-channel agent
    # path hits ``REJECTED_IDENTITY``.
    try:
        from aria.security.auth import mint_internal_channel_token
        mint_internal_channel_token()
        logger.info("aria.internal_channel_token.minted")
    except Exception as exc:    # noqa: BLE001
        logger.warning(
            "aria.internal_channel_token.mint_failed", error=str(exc),
        )

    monitor_emitter_url = os.environ.get("ARIA_MONITOR_EMITTER_URL", "").strip()
    monitor_heartbeat_file = os.environ.get("ARIA_MONITOR_HEARTBEAT_FILE", "").strip()
    aria_environment = os.environ.get("ARIA_ENVIRONMENT", "development").lower()
    monitor_configured = bool(monitor_emitter_url or monitor_heartbeat_file)

    # Wiring audit Pass 4 (F7.5): production deploys MUST configure a
    # HAL endpoint so ``aria.actuator.*`` topics actually fire hardware.
    # Without ``ARIA_HAL_URL``, the LLM may dispatch propulsion /
    # heater / scrubber commands that publish to topics with no
    # subscriber — operators see "command sent" while the spacecraft
    # does nothing. The 39 advisory-tagged tools (Pass 4 F9.5) are
    # safe in this state because the LLM knows their effect="advisory";
    # but the dispatch_command path opened by F1.5/F1.6 expects a
    # real HAL on the other end of the bus.
    hal_url = os.environ.get("ARIA_HAL_URL", "").strip()
    if aria_environment == "production" and not hal_url:
        logger.critical(
            "aria.hal.not_configured_in_production",
            impact="aria.actuator.* topics have no executor; LLM "
                   "dispatched commands would be silently dropped",
            fix="set ARIA_HAL_URL to the hardware-abstraction-layer "
                "endpoint (sidecar process or external service); see "
                "docs/HAL_INTEGRATION.md",
        )
        raise SystemExit(1)
    elif not hal_url:
        logger.warning(
            "aria.hal.not_configured",
            note="development boot — actuator commands publish to a bus "
                 "that has no real HAL subscriber. The 39 advisory-tagged "
                 "tools (effect='advisory') are safe; production deploys "
                 "must set ARIA_HAL_URL.",
        )

    if monitor_configured:
        from aria.monitor.heartbeat import HeartbeatWatcher

        def _on_monitor_silence(age_s: float) -> None:
            sm = get_safe_mode_singleton()
            if sm is None:
                return
            sm.force_level(SafeLevel.MONITORING_ONLY,
                           reason=f"monitor_heartbeat_silence:{age_s:.0f}s")

        heartbeat_watcher = HeartbeatWatcher(
            on_silence=_on_monitor_silence,
            grace_s=30.0,
            emitter_id="monitor",
        )

        async def _heartbeat_bus_handler(message):
            try:
                heartbeat_watcher.on_event(message.payload or {})
            except Exception as exc:    # noqa: BLE001
                logger.warning("heartbeat.bus_handler_failed", error=str(exc))

        coordinator.bus.subscribe("aria.monitor.heartbeat", _heartbeat_bus_handler)
        heartbeat_watcher.start()

        # File-bridge poller (F14.4): when the runner is configured to
        # write atomic heartbeat files, this task tails the file and
        # re-publishes on the local bus so the watcher's existing
        # subscriber path is the single integration point regardless of
        # IPC mechanism. The HMAC inside the payload is verified by the
        # watcher itself; the bridge is pure transport.
        if monitor_heartbeat_file:
            import json as _json
            from pathlib import Path as _Path

            heartbeat_path = _Path(monitor_heartbeat_file)

            async def _poll_heartbeat_file() -> None:
                last_mtime = 0.0
                while True:
                    try:
                        await asyncio.sleep(1.0)
                        if not heartbeat_path.exists():
                            continue
                        try:
                            mtime = heartbeat_path.stat().st_mtime
                        except OSError:
                            continue
                        if mtime <= last_mtime:
                            continue
                        try:
                            with heartbeat_path.open("r") as fp:
                                record = _json.load(fp)
                        except (FileNotFoundError, _json.JSONDecodeError):
                            continue
                        payload = record.get("payload") or {}
                        await coordinator.bus.publish(Message(
                            topic="aria.monitor.heartbeat",
                            payload=payload,
                            source_agent="monitor_bridge",
                        ))
                        last_mtime = mtime
                    except asyncio.CancelledError:
                        break
                    except Exception as exc:    # noqa: BLE001
                        logger.warning(
                            "monitor.bridge.poll_failed", error=str(exc),
                        )

            asyncio.create_task(_poll_heartbeat_file())
            logger.info(
                "aria.monitor.file_bridge_started",
                path=str(heartbeat_path),
            )

        logger.info("aria.monitor.watcher_armed",
                    emitter_url=monitor_emitter_url or None,
                    heartbeat_file=monitor_heartbeat_file or None,
                    grace_s=30.0)
    elif aria_environment == "production":
        logger.critical(
            "aria.monitor.runner_not_configured",
            impact=("§F-7 independent monitor is required in production but "
                    "no transport is configured; refusing to start rather "
                    "than booting with the watcher disabled"),
            fix=("set ARIA_MONITOR_HEARTBEAT_FILE (file bridge) or "
                 "ARIA_MONITOR_EMITTER_URL (HTTP bridge) and run "
                 "python -m aria.monitor.runner alongside the primary"),
        )
        raise SystemExit(1)
    else:
        logger.warning(
            "aria.monitor.watcher_disabled",
            reason="no ARIA_MONITOR_HEARTBEAT_FILE or ARIA_MONITOR_EMITTER_URL configured",
            note=("development boot — heartbeat watcher SKIPPED; T-V-2 "
                  "monitor independence is NOT enforced"),
        )

    logger.info(
        "aria.running",
        mission=config.mission_name,
        phase=config.mission_phase,
        agents=coordinator.agent_count,
        tools=coordinator.tools.count,
        simulate=simulate,
        claude_api=bool(api_key),
    )

    # Print startup summary
    status = coordinator.system_status()
    print(f"\n  Mission: {config.mission_name} | Phase: {config.mission_phase}")
    print(f"  Agents: {coordinator.agent_count} | Tools: {coordinator.tools.count}")
    print(f"  Health: {status.get('health_score', 100.0):.0f}% | "
          f"Safe Mode: {status.get('safe_mode', 'NOMINAL')}")
    print(f"  the LLM API: {'✓ Enabled' if api_key else '✗ Offline (rule-based fallback)'}")
    print(f"  Simulator: {'✓ Running' if simulate else '✗ Off (connect real sensors)'}")
    print(f"  API: http://{api_host}:{api_http_port}/api/v1/status | ws://{api_host}:{api_ws_port}\n")

    # ── Shutdown Handler ───────────────────────────────────────────────────
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("aria.shutdown_signal_received")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass  # Windows

    await shutdown_event.wait()

    # ── Graceful Shutdown ──────────────────────────────────────────────────
    logger.info("aria.shutting_down")
    try:
        from aria.security.integrity_monitor import stop_integrity_monitor
        stop_integrity_monitor()
    except Exception as exc:
        logger.warning("aria.cim.stop_failed", error=str(exc))
    try:
        from aria.security.audit_downlink import stop_audit_downlink
        stop_audit_downlink()
    except Exception as exc:
        logger.warning("aria.audit_downlink.stop_failed", error=str(exc))
    ground_deadman.stop()
    await api_server.stop()
    await console.stop()
    if simulator:
        await simulator.stop()
    await coordinator.stop()

    # Autonomy audit follow-up — flush replay-defence + F-19 counter
    # state on graceful shutdown so a planned restart does not lose up
    # to 25 increments / 5 s of state.  Both helpers swallow their own
    # I/O exceptions so a flaky disk doesn't block shutdown.
    try:
        from aria.security.session_store import get_session_store
        get_session_store().flush_counters()
        logger.info("aria.shutdown.session_counters_flushed")
    except Exception as exc:    # noqa: BLE001
        logger.warning("aria.shutdown.session_counters_flush_failed",
                       error=str(exc))
    try:
        from aria.safety.replay_guard import get_replay_guard
        get_replay_guard().flush()
        logger.info("aria.shutdown.replay_guard_flushed")
    except Exception as exc:    # noqa: BLE001
        logger.warning("aria.shutdown.replay_guard_flush_failed",
                       error=str(exc))

    logger.info("aria.shutdown_complete", mission=config.mission_name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ARIA — Autonomous Reasoning & Integration Architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m aria.main                           # Production mode (no simulator)
  python -m aria.main --simulate                # Dev mode with sensor simulator
  python -m aria.main --config aria.yaml        # Custom config
  ANTHROPIC_API_KEY=sk-... python -m aria.main  # Enable LLM reasoning
  ARIA_PROD_BOOT=1 python -m aria.main          # Enforce strict boot manifest
        """,
    )
    parser.add_argument("--config", default="configs/aria.yaml", help="Config YAML path")
    parser.add_argument("--simulate", action="store_true", help="Enable sensor simulator")
    args = parser.parse_args()

    # Recovery audit R-6: install last-gasp diagnostic dump BEFORE
    # any other subsystem starts.  faulthandler captures segfaults,
    # excepthook catches unhandled Python exceptions, atexit flushes
    # coalesced state.  Best-effort — never blocks boot on failure.
    from aria.safety.last_gasp import install as _install_last_gasp
    _install_last_gasp()

    # Recovery audit R-20: in production, the heartbeat HMAC secret
    # MUST be set; otherwise the boot_id replay defence silently
    # disables and a bus-attacker can mint fake monitor restarts.
    if os.environ.get("ARIA_ENVIRONMENT", "").lower() == "production":
        from aria.monitor.heartbeat import _heartbeat_secret
        if not _heartbeat_secret():
            raise SystemExit(
                "aria.heartbeat_secret_missing — ARIA_ENVIRONMENT=production "
                "requires either ARIA_HEARTBEAT_SECRET (hex) or "
                "data/sealed/heartbeat.key to be present"
            )

    # Recovery audit R-13: pre-boot crash-loop guard.  Increments the
    # boot.attempt counter, evaluates the recent-failure window, and
    # returns a BootDecision that flags rescue_mode if we have crashed
    # ≥ CRASH_LOOP_THRESHOLD times within CRASH_LOOP_WINDOW_S.  Also
    # applies a reboot-rate cooldown if we are bouncing too fast.
    from aria.safety.boot_counter import begin_boot
    boot_decision = begin_boot()
    if boot_decision.rescue_mode:
        logger.error("aria.boot.rescue_mode",
                     reason=boot_decision.reason,
                     attempt=boot_decision.attempt_count,
                     recent_failures=boot_decision.recent_failures)
    if boot_decision.cooldown_applied_s > 0:
        logger.error("aria.boot.cooldown_applied",
                     seconds=boot_decision.cooldown_applied_s)

    # F-1 sealed prompt + F-18 boot manifest verification — first thing
    # in __main__. Either failure exits before any subsystem comes up.
    # In production set ARIA_PROD_BOOT=1 so a missing manifest is also
    # fatal (development trees may not have one).
    try:
        from aria.cognitive.sealed_prompt import verify_and_load
        verify_and_load(strict=True)
        from aria.boot import verify_boot_integrity
        from aria.boot.verify import is_rescue_mode_active
        verify_boot_integrity(
            strict=True,
            skip_if_missing=os.environ.get("ARIA_PROD_BOOT", "") != "1",
        )
        if is_rescue_mode_active():
            # Recovery audit R-19: primary manifest failed but rescue
            # manifest passed.  Set env flag so the run() body knows to
            # bring up beacon-only mode.
            os.environ["ARIA_RESCUE_MODE"] = "1"
            logger.error("aria.boot.rescue_mode_from_manifest")
        # R34: hash-chain audit verify. Tampered chain → operator alert
        # via aria.security.audit_chain_break (the bus subscriber routes
        # it to the SafetyConsole). The runtime continues to boot so
        # the operator still has a console to work from; subsequent
        # writes append to the (now-broken) chain to preserve forensics.
        from aria.security.audit import verify_at_boot
        from aria.simulator.event_bus import get_event_bus
        bus = get_event_bus()
        verify_at_boot(publish_fn=lambda topic, payload: bus.publish(
            topic, severity="critical", payload=payload, source="audit",
        ))
        # R34: subscribe the audit-bus mirror so every safety / security /
        # approval / kill-switch / monitor event lands in the chain
        # without each subsystem having to call log_event() by hand.
        from aria.security.audit_bus_mirror import start_audit_bus_mirror
        start_audit_bus_mirror(bus=bus)
        # R38: continuous integrity monitor (runtime variant of F-18) is
        # started later, after the coordinator's async loop comes up so
        # the on_mismatch callback can request safe-mode on the live bus.
    except SystemExit:
        raise
    except Exception as exc:
        logger.error("aria.boot.failsafe_check_failed", error=str(exc))
        sys.exit(1)

    try:
        asyncio.run(run(config_path=args.config, simulate=args.simulate))
    except KeyboardInterrupt:
        print("\n  Shutdown by user.")
    except Exception as exc:
        logger.error("aria.fatal_error", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
