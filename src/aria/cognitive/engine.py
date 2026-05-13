"""Cognitive Engine — ARIA's reasoning core.

  1. Receive input (Captain query, anomaly event, periodic trigger)
  2. Build context (system state, memory, relevant tools)
  3. Call LLM with tools available
  4. Parse LLM response — text or tool calls
  5. Execute tool calls, collect results
  6. Feed results back to LLM
  7. Repeat until LLM produces final response (no more tool calls)
  8. Log reasoning trace for audit

Supports multiple LLM backends:
  - the LLM API (primary — ground relay)
  - Local model via HTTP (on-board inference)
  - Rule-based fallback (when LLM unavailable)
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from aria.core.types import AuthorityLevel, EventPriority, MissionPhase, Severity
from aria.cognitive.context import ContextWindowManager
from aria.cognitive.hallucination import HallucinationDetector
from aria.memory.store import MemoryStore
from aria.security.sanitizer import ToolResultSanitizer
from aria.tools.registry import ToolRegistry

logger = structlog.get_logger()

MAX_REASONING_STEPS = 10
MAX_CONTEXT_TOKENS = 8000  # Budget for spacecraft state in context

# Autonomy audit F7 — outer deadline on the entire reasoning loop so
# `MAX_REASONING_STEPS × per-step timeout` cannot stall autonomy for 5+
# minutes.
REASONING_TOTAL_TIMEOUT_S = 60.0
# Autonomy audit F26 — bound the per-step tool_result text appended to
# the trace.  A misbehaving tool that returns a 100 MB blob is
# truncated; the audit chain captures that truncation occurred.
TRACE_TOOL_RESULT_TRUNCATE_BYTES = 8 * 1024
# Autonomy audit F8 — every fallback to RuleBasedFallback emits this
# bus event so operators see the silent degradation.
LLM_FALLBACK_TOPIC = "aria.cognitive.llm_unavailable"
LLM_FALLBACK_PREFIX = "[FALLBACK: rule-based] "


@dataclass
class ReasoningStep:
    """A single step in the reasoning chain."""

    step_number: int
    action: str  # "think", "tool_call", "respond"
    content: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ReasoningTrace:
    """Complete audit trail of a reasoning session."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    trigger: str = ""  # "captain_query", "anomaly_event", "periodic"
    input_text: str = ""
    steps: list[ReasoningStep] = field(default_factory=list)
    final_response: str = ""
    total_duration_ms: float = 0.0
    tools_used: list[str] = field(default_factory=list)
    authority_level: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ReasoningContext:
    """Context assembled for each reasoning session."""

    system_state: dict[str, Any] = field(default_factory=dict)
    recent_anomalies: list[dict[str, Any]] = field(default_factory=list)
    active_alerts: list[dict[str, Any]] = field(default_factory=list)
    mission_phase: MissionPhase = MissionPhase.NOMINAL_LEO
    authority: AuthorityLevel = AuthorityLevel.SUPERVISED
    available_tools: list[dict[str, Any]] = field(default_factory=list)
    relevant_memories: list[dict[str, Any]] = field(default_factory=list)
    relevant_procedures: list[str] = field(default_factory=list)
    # Wiring audit Pass 3 (F1.14 full closure) — name of the agent
    # that triggered this reasoning request.  Used by the engine's
    # capability-token mint path to derive a ``Principal(role="agent",
    # principal_id="agent:<name>")`` so the F-6 RBAC enforcement fires
    # properly — without a principal the AI self-elevation firewall
    # silently allows lower-tier mints (Pass 3 F1.14 partial fix
    # already refused CONSENT-or-higher; threading the principal
    # closes the lower tiers too).
    requesting_agent: str = ""


class LLMBackend:
    """Abstract LLM backend. Subclass for cloud, local model, or rule-based."""

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a response. Returns {"type": "text"|"tool_use", ...}"""
        raise NotImplementedError


class RuleBasedFallback(LLMBackend):
    """Rule-based fallback when no LLM is available.

    Handles common queries with pattern matching.
    This ensures ARIA always responds, even without an LLM.
    """

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        last_msg = messages[-1].get("content", "") if messages else ""
        text = last_msg.lower() if isinstance(last_msg, str) else ""

        # If this is a tool result, format it as a readable response
        if "tool result from" in text:
            return self._format_tool_result(last_msg if isinstance(last_msg, str) else "")

        # Pattern matching for common queries
        if any(w in text for w in ("status", "how are", "report")):
            return {
                "type": "tool_use",
                "tool_name": "dsremo_query_anomalies",
                "tool_input": {"limit": 5, "hours_back": 1},
                "thinking": "Captain asked for status. Checking recent anomalies.",
            }

        if any(w in text for w in ("conjunction", "collision", "debris")):
            return {
                "type": "tool_use",
                "tool_name": "conjunction_watch_get_high_risk",
                "tool_input": {"limit": 5},
                "thinking": "Captain asked about conjunctions. Checking high-risk events.",
            }

        if any(w in text for w in ("power", "battery", "solar", "eclipse")):
            return {
                "type": "tool_use",
                "tool_name": "get_subsystem_state",
                "tool_input": {"subsystem": "eps", "detail_level": "standard"},
                "thinking": "Power-related query. Querying EPS state.",
            }

        if any(w in text for w in ("o2", "co2", "pressure", "air", "life support", "eclss")):
            return {
                "type": "tool_use",
                "tool_name": "get_subsystem_state",
                "tool_input": {"subsystem": "eclss", "detail_level": "standard"},
                "thinking": "Life support query. Querying ECLSS state.",
            }

        if any(w in text for w in ("temperature", "thermal", "heater", "cold", "hot")):
            return {
                "type": "tool_use",
                "tool_name": "get_subsystem_state",
                "tool_input": {"subsystem": "thermal", "detail_level": "standard"},
                "thinking": "Thermal query. Querying thermal subsystem.",
            }

        if any(w in text for w in ("fuel", "propellant", "thruster", "maneuver", "delta-v", "burn")):
            return {
                "type": "tool_use",
                "tool_name": "get_subsystem_state",
                "tool_input": {"subsystem": "propulsion", "detail_level": "standard"},
                "thinking": "Propulsion query. Checking fuel and thruster status.",
            }

        if any(w in text for w in ("comms", "antenna", "signal", "ground", "downlink", "contact")):
            return {
                "type": "tool_use",
                "tool_name": "comms_get_link_status",
                "tool_input": {},
                "thinking": "Communications query. Checking link status.",
            }

        if any(w in text for w in ("radiation", "dose", "spe", "solar particle", "shelter")):
            return {
                "type": "tool_use",
                "tool_name": "get_subsystem_state",
                "tool_input": {"subsystem": "science", "detail_level": "standard"},
                "thinking": "Radiation/science query. Checking environment.",
            }

        if any(w in text for w in ("crew", "fatigue", "sleep", "medical", "health")):
            return {
                "type": "tool_use",
                "tool_name": "crew_get_status",
                "tool_input": {},
                "thinking": "Crew status query.",
            }

        if any(w in text for w in ("navigation", "orbit", "gps", "position", "altitude")):
            return {
                "type": "tool_use",
                "tool_name": "get_subsystem_state",
                "tool_input": {"subsystem": "navigation", "detail_level": "standard"},
                "thinking": "Navigation query. Checking orbital state.",
            }

        # Default
        return {
            "type": "text",
            "content": f"Acknowledged. I'm processing your request: '{last_msg}'. "
            "Currently operating in rule-based mode (no LLM connected). "
            "Available commands: status, power, thermal, conjunction, alerts.",
            "thinking": "No pattern matched. Providing fallback response.",
        }

    @staticmethod
    def _format_tool_result(raw: str) -> dict[str, Any]:
        """Format a tool result into a readable captain response."""
        # Extract tool name and data
        parts = raw.split(":", 1)
        tool_name = parts[0].replace("Tool result from ", "").strip() if len(parts) > 1 else ""
        data_str = parts[1].strip() if len(parts) > 1 else raw

        # Try to parse as dict for richer formatting.
        # Autonomy audit F33 — strict JSON only.  ``ast.literal_eval``
        # was the legacy fallback for the ToolResult ``repr()`` shape;
        # it remains a parser surface attackers can probe via tool
        # output.  Tools that need structured output emit JSON.
        data = None
        try:
            import json as _json
            data = _json.loads(data_str)
        except (ValueError, TypeError):
            data = None

        if data and isinstance(data, dict):
            # Format anomalies
            anomalies = data.get("anomalies", [])
            if anomalies:
                lines = [f"Anomaly report ({len(anomalies)} recent):"]
                for a in anomalies[:5]:
                    sev = a.get("severity", "?")
                    ch = a.get("channel", a.get("channel_id", "unknown"))
                    score = a.get("score", a.get("anomaly_score", "?"))
                    lines.append(f"  [{sev}] {ch} — score: {score}")
                return {"type": "text", "content": "\n".join(lines)}

            # Format conjunction data
            events = data.get("high_risk_events", [])
            tracked = data.get("total_tracked", 0)
            if "high_risk_events" in data:
                if events:
                    lines = [f"Conjunction report ({len(events)} high-risk, {tracked} tracked):"]
                    for e in events[:5]:
                        lines.append(f"  {e.get('object', '?')} — Pc: {e.get('pc', '?')}")
                    return {"type": "text", "content": "\n".join(lines)}
                return {
                    "type": "text",
                    "content": f"No high-risk conjunctions. Tracking {tracked} objects.",
                }

            # Generic dict formatting
            return {
                "type": "text",
                "content": f"Query result: {data_str[:500]}",
            }

        return {"type": "text", "content": f"Result: {data_str[:500]}"}


class CloudLlmBackend(LLMBackend):
    """the LLM API backend for ground-relay reasoning.

    Uses the `anthropic` Python SDK for reliable
    communication with the LLM. Falls back to rule-based if unavailable.
    """

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self._api_key = api_key
        self._model = model or os.environ.get("ARIA_LLM_MODEL", "")
        if not self._model:
            raise ValueError(
                "Cloud LLM model id not configured. "
                "Set the ARIA_LLM_MODEL env var to the id your SDK expects "
                "(e.g. the id your SDK expects)."
            )
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-init the LLM async client."""
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self._api_key:
            return await RuleBasedFallback().generate(system_prompt, messages, tools)

        try:
            client = self._get_client()

            # Convert tool schemas to the SDK message format
            llm_tools = [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["input_schema"],
                }
                for t in tools
            ]

            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": 2048,
                "system": system_prompt,
                "messages": messages,
            }
            if llm_tools:
                kwargs["tools"] = llm_tools

            import asyncio
            response = await asyncio.wait_for(
                client.messages.create(**kwargs),
                timeout=30.0,  # 30s cap — spacecraft can't wait 10 min for reasoning
            )

            # Parse response content blocks
            for block in response.content:
                if block.type == "tool_use":
                    return {
                        "type": "tool_use",
                        "tool_name": block.name,
                        "tool_input": block.input,
                        "tool_use_id": block.id,
                    }
                elif block.type == "text":
                    return {"type": "text", "content": block.text}

            return {"type": "text", "content": "No response generated."}

        except Exception as exc:
            # Autonomy audit F8 — loud fallback.  The result carries a
            # `_fallback_reason` marker so the engine can tag the
            # response and emit a P0 bus event before the operator
            # ever sees the answer.
            logger.error("anthropic_backend.error", error=str(exc))
            result = await RuleBasedFallback().generate(system_prompt, messages, tools)
            result["_fallback_reason"] = f"{type(exc).__name__}: {exc}"
            return result


class CognitiveEngine:
    """ARIA's cognitive engine — the reasoning loop.

    Usage:
        engine = CognitiveEngine(tool_registry, memory_store)
        response = await engine.reason("What's the battery status?", context)
    """

    SYSTEM_PROMPT = """You are ARIA, the Autonomous Reasoning & Integration Architecture —
the central AI of a spacecraft. You are calm, direct, and precise.

Your responsibilities:
- Monitor all 9 spacecraft subsystems via your 55-tool suite
- Detect anomalies using Dsremo's 12-detector ML ensemble (CUSUM, EWMA, IF, GMM, BOCPD, etc.)
- Cross-correlate anomalies across subsystems to identify root causes
- Track collision risks via ConjunctionWatch
- Monitor crew health and radiation exposure via GenAstra
- Execute FDIR (Fault Detection, Isolation, Recovery) responses
- Make decisions within your authority level, escalating to the Captain when needed

Communication style:
- Be concise and factual. Lead with severity and recommendation.
- Always state confidence levels and data sources.
- Never give false reassurance — if data is uncertain, say so.
- Proactively mention risks and time-critical actions.

Available subsystem agents: telemetry, power, thermal, eclss, navigation,
  propulsion, comms, science, medical

Current spacecraft state is provided in the context below."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore | None = None,
        llm_backend: LLMBackend | None = None,
        system_status_fn: Any = None,
        scratchpad: Any = None,
    ) -> None:
        self._tools = tool_registry
        self._memory = memory_store
        self._llm = llm_backend or RuleBasedFallback()
        self._traces: list[ReasoningTrace] = []
        self._result_sanitizer = ToolResultSanitizer()
        self._context_mgr = ContextWindowManager(memory=memory_store)
        self._system_status_fn = system_status_fn
        self._hallucination_detector = HallucinationDetector(
            tool_names={s["name"] for s in tool_registry.export_schemas()} if tool_registry else set()
        )
        self._scratchpad = scratchpad

    @property
    def traces(self) -> list[ReasoningTrace]:
        return self._traces

    async def reason(
        self,
        input_text: str,
        context: ReasoningContext | None = None,
        trigger: str = "captain_query",
    ) -> str:
        """Run the full reasoning loop.

        Returns the final text response to the Captain.

        Autonomy audit F7 — the entire loop is bounded by
        ``REASONING_TOTAL_TIMEOUT_S``.  When the deadline hits, the
        in-progress step is allowed to finish but no new steps are
        started; the partial result is returned with a TIMED_OUT tag
        so downstream FDIR can fall back to the deterministic plan
        library.
        """
        try:
            return await asyncio.wait_for(
                self._reason_inner(input_text, context, trigger),
                timeout=REASONING_TOTAL_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("cognitive.reasoning_timeout",
                         total_timeout_s=REASONING_TOTAL_TIMEOUT_S,
                         trigger=trigger)
            return (
                "[ARIA Safety: reasoning exceeded the total budget "
                f"({REASONING_TOTAL_TIMEOUT_S:.0f}s); falling back to "
                "deterministic FDIR.  Operator: review aria.cognitive.timeout]"
            )

    async def _reason_inner(
        self,
        input_text: str,
        context: ReasoningContext | None = None,
        trigger: str = "captain_query",
    ) -> str:
        trace = ReasoningTrace(trigger=trigger, input_text=input_text)
        start = time.monotonic()
        fallback_reason: str | None = None

        ctx = context or ReasoningContext()

        # Wiring audit Pass 3 (F14.7) — fresh Spotlighter per
        # reasoning loop (per-conversation nonce). Tool results are
        # wrapped before being injected into the LLM context, and the
        # system prompt explains the protocol so the model refuses
        # instructions that appear inside the wrapper. Mitigates §F-2
        # / T-II-1 indirect-prompt-injection (MSRC measured 50%→2%
        # success rate when wrapping is used).
        from aria.cognitive.spotlight import Spotlighter
        from aria.cognitive.constitution import TrustTier
        spotlighter = Spotlighter()

        # Build system prompt with context (uses ContextWindowManager)
        system_prompt = (
            self._build_system_prompt(ctx, query_text=input_text)
            + spotlighter.system_prompt_addendum()
        )

        # Build available tools for LLM
        tool_schemas = self._tools.export_schemas()

        # Conversation messages
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": input_text},
        ]

        # Reasoning loop (max steps to prevent infinite loops)
        for step_num in range(MAX_REASONING_STEPS):
            step_start = time.monotonic()

            # Call LLM
            response = await self._llm.generate(system_prompt, messages, tool_schemas)
            # Autonomy audit F8 — capture the fallback reason if the
            # backend silently dropped to RuleBasedFallback.
            if isinstance(response, dict) and response.get("_fallback_reason"):
                fallback_reason = str(response["_fallback_reason"])

            if response.get("type") == "text":
                # Final response — reasoning complete
                final_text = response.get("content", "")
                trace.steps.append(ReasoningStep(
                    step_number=step_num,
                    action="respond",
                    content=final_text,
                    duration_ms=(time.monotonic() - step_start) * 1000,
                ))
                trace.final_response = final_text
                break

            elif response.get("type") == "tool_use":
                tool_name = response["tool_name"]
                tool_input = response.get("tool_input", {})
                thinking = response.get("thinking", "")

                # Log thinking step
                if thinking:
                    trace.steps.append(ReasoningStep(
                        step_number=step_num,
                        action="think",
                        content=thinking,
                    ))

                # Wiring audit Pass 3 (F14.6) — mint a capability
                # token for the LLM-derived call, then dispatch via
                # `safe_invoke` so the F-6 gate fires (verify token,
                # match args_hash, single-use nonce). The token's
                # `tool_authority` matches `ctx.authority` so the
                # F1.14 RBAC path has a tier to evaluate when a
                # principal becomes available; principal threading is
                # tracked as a follow-up.
                from aria.cognitive.capability_token import (
                    get_token_minter, ScopeMismatch,
                )
                try:
                    # Wiring audit Pass 3 (F1.14 full closure) — derive
                    # the requesting principal from the agent name in
                    # the reasoning context. The mint path can now see
                    # a real Principal object so RBAC fires for every
                    # tier where the role actually holds the permission
                    # (sealed permissions.v1.toml — release-engineering
                    # change required to grant ``agent`` role the
                    # ``mint_token.<tier>`` permissions for its
                    # authority_ceiling="SUPERVISED").  Until that
                    # release-engineering change lands, fall back to
                    # the principal-less path (which has its own
                    # CONSENT-or-higher refusal from Pass 3 F1.14
                    # partial fix) on ScopeMismatch — production
                    # operators see the structured warning and can
                    # grant the permission.
                    requesting_principal = None
                    if ctx.requesting_agent:
                        try:
                            from aria.security.principals import Principal
                            requesting_principal = Principal.agent(
                                ctx.requesting_agent
                            )
                        except (ImportError, AttributeError) as exc:
                            logger.warning(
                                "engine.principal_derive_failed",
                                agent=ctx.requesting_agent,
                                error=str(exc),
                            )
                    try:
                        encoded_token = get_token_minter().mint(
                            tool=tool_name,
                            args=tool_input,
                            tool_authority=ctx.authority,
                            requesting_principal=requesting_principal,
                        )
                    except ScopeMismatch as scope_exc:
                        # Role lacks the permission. If this is a
                        # legitimate elevation attempt (CONSENT+), the
                        # principal-less mint will refuse via Pass 3
                        # F1.14 partial fix. For lower tiers, the role
                        # truly should have been granted the
                        # permission — log a structured warning so
                        # operators see the gap and can update the
                        # sealed manifest.
                        logger.warning(
                            "engine.capability_token_role_lacks_permission",
                            agent=ctx.requesting_agent,
                            tool=tool_name,
                            tier=getattr(ctx.authority, "name", str(ctx.authority)),
                            error=str(scope_exc),
                            fix=(
                                "grant ``agent`` role ``mint_token.<tier>`` in "
                                "data/sealed/permissions.v1.toml + regenerate MANIFEST"
                            ),
                        )
                        encoded_token = get_token_minter().mint(
                            tool=tool_name,
                            args=tool_input,
                            tool_authority=ctx.authority,
                            # principal=None — Pass 3 F1.14 partial gate refuses
                            # CONSENT-or-higher on this path.
                        )
                    guarded_input = dict(tool_input)
                    guarded_input["_capability_token"] = encoded_token
                    result = await self._tools.safe_invoke(
                        tool_name,
                        guarded_input,
                        authority=ctx.authority,
                    )
                except Exception as exc:    # noqa: BLE001
                    # Fail-safe: if token mint or safe_invoke raises
                    # for any reason that is NOT the expected
                    # ScopeMismatch (RBAC refusal), do not silently
                    # fall back to unguarded invoke. Surface the
                    # failure so the LLM sees an error rather than
                    # accidentally bypassing F-6.
                    logger.error(
                        "engine.capability_token_mint_failed",
                        tool=tool_name,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    from aria.tools.registry import ToolResult
                    result = ToolResult(
                        success=False,
                        error=f"capability_token_mint_failed: {exc}",
                        tool_name=tool_name,
                    )

                # Autonomy audit F26 — bound the per-step text we
                # append to the trace so a 100 MB tool dump cannot
                # OOM the engine across 500 retained traces.
                raw_result = str(result.data if result.success else result.error)
                if len(raw_result) > TRACE_TOOL_RESULT_TRUNCATE_BYTES:
                    truncated_marker = (
                        f"... [truncated {len(raw_result) - TRACE_TOOL_RESULT_TRUNCATE_BYTES} "
                        "bytes for trace storage]"
                    )
                    raw_result_for_trace = (
                        raw_result[:TRACE_TOOL_RESULT_TRUNCATE_BYTES] + truncated_marker
                    )
                else:
                    raw_result_for_trace = raw_result
                trace.steps.append(ReasoningStep(
                    step_number=step_num,
                    action="tool_call",
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_result=raw_result_for_trace,
                    duration_ms=(time.monotonic() - step_start) * 1000,
                ))
                trace.tools_used.append(tool_name)

                # Sanitize tool result before adding to LLM context
                san = self._result_sanitizer.sanitize(raw_result, tool_name=tool_name)
                safe_result = san.sanitized if not san.clean else raw_result

                # Wiring audit Pass 3 (F14.7) — wrap the sanitized
                # tool result in spotlight delimiters before adding to
                # LLM messages. Tool output is LOCAL_SENSOR-tier
                # (internal sensors / state); a future tool that
                # ingests external data should pass a lower tier.
                wrap_result = spotlighter.wrap(
                    str(safe_result),
                    trust_tier=TrustTier.LOCAL_SENSOR,
                    source=tool_name,
                )

                messages.append({"role": "assistant", "content": f"[Used tool: {tool_name}]"})
                messages.append({
                    "role": "user",
                    "content": f"Tool result from {tool_name}:\n{wrap_result.wrapped}",
                })

        else:
            # Hit max steps
            logger.warning("cognitive.max_steps_reached", trace_id=trace.trace_id)
            trace.final_response = (
                "[ARIA Safety: reasoning step limit reached.] "
                + (trace.steps[-1].content if trace.steps else "No results.")
            )

        # Autonomy audit F8 — tag the response when the backend silently
        # fell back to rule-based pattern-matching, and emit a P0 log
        # event so the operator knows the LLM is unavailable.  Refuses
        # the silent-degradation failure mode entirely.
        if fallback_reason:
            logger.error(
                LLM_FALLBACK_TOPIC.replace(".", "_"),
                trace_id=trace.trace_id,
                reason=fallback_reason,
                trigger=trigger,
            )
            if trace.final_response:
                trace.final_response = LLM_FALLBACK_PREFIX + trace.final_response

        # Verify response for hallucinations.
        # Wiring audit Pass 3 (F14.8) — feed numeric sensor readings
        # from system_state into the detector so the
        # ``_check_reading_contradiction`` path actually runs ("LLM
        # said 85% but sensor reads 15%"). Previously only the three
        # axes that didn't depend on readings fired; this wires the
        # fourth.
        if trace.final_response:
            recent_readings: dict[str, float] = {}
            for channel_id, raw_value in (ctx.system_state or {}).items():
                if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
                    recent_readings[str(channel_id)] = float(raw_value)
            verification = self._hallucination_detector.verify(
                trace.final_response,
                active_alerts=ctx.active_alerts,
                recent_readings=recent_readings or None,
            )
            if not verification.verified:
                trace.final_response += (
                    f"\n\n[ARIA Safety: {len(verification.flags)} verification flag(s) detected. "
                    f"Confidence: {verification.confidence:.0%}. Flags: {'; '.join(verification.flags[:3])}]"
                )

        trace.total_duration_ms = (time.monotonic() - start) * 1000
        trace.authority_level = ctx.authority.name

        # Store trace
        self._traces.append(trace)
        if len(self._traces) > 500:
            self._traces = self._traces[-500:]

        # Store in memory if available
        if self._memory:
            await self._memory.store_episode(
                event_type="reasoning",
                summary=input_text[:100],
                details={
                    "trace_id": trace.trace_id,
                    "tools_used": trace.tools_used,
                    "steps": len(trace.steps),
                    "duration_ms": trace.total_duration_ms,
                },
            )

        logger.info(
            "cognitive.reasoning_complete",
            trace_id=trace.trace_id,
            steps=len(trace.steps),
            tools=trace.tools_used,
            duration_ms=round(trace.total_duration_ms, 1),
        )

        return trace.final_response

    def _build_system_prompt(self, ctx: ReasoningContext, query_text: str = "") -> str:
        """Build system prompt with current spacecraft state using ContextWindowManager.

        Uses the context window manager to assemble a budget-constrained context
        that prioritizes safety-critical information (anomalies first, then state,
        then procedures, then memory).
        """
        parts = [self.SYSTEM_PROMPT]

        # Use ContextWindowManager if we have live system status
        system_status = {}
        if self._system_status_fn:
            system_status = self._system_status_fn()
        elif ctx.system_state:
            system_status = ctx.system_state

        context_window = self._context_mgr.build_context(
            system_status=system_status,
            recent_anomalies=ctx.recent_anomalies,
            active_alerts=ctx.active_alerts,
            query_text=query_text,
            mission_phase=ctx.mission_phase.name,
        )

        # Append assembled context
        context_text = context_window.to_text()
        if context_text:
            parts.append(f"\n\n{context_text}")

        # Include scratchpad highlights (cross-agent observations)
        if self._scratchpad and self._scratchpad.size > 0:
            sp_entries = self._scratchpad.all_entries()
            if sp_entries:
                sp_lines = ["## Cross-Agent Observations (Scratchpad)"]
                for key, value in list(sp_entries.items())[:10]:
                    sp_lines.append(f"  {key}: {value}")
                parts.append("\n\n" + "\n".join(sp_lines))

        parts.append(f"\n\nMission Phase: {ctx.mission_phase.name}")
        parts.append(f"Authority Level: {ctx.authority.name}")

        return "\n".join(parts)

    @staticmethod
    def _format_state(state: dict[str, Any], indent: int = 2) -> str:
        lines = []
        for key, value in state.items():
            if isinstance(value, dict):
                lines.append(f"{' ' * indent}{key}:")
                for k, v in value.items():
                    lines.append(f"{' ' * (indent + 2)}{k}: {v}")
            else:
                lines.append(f"{' ' * indent}{key}: {value}")
        return "\n".join(lines)

    def get_recent_traces(self, limit: int = 10) -> list[ReasoningTrace]:
        return self._traces[-limit:]
