"""ARIA Tool base class — the heart of the tool system.

  - inputSchema -> input_schema (Pydantic model)
  - validateInput -> validate_input
  - checkPermissions -> check_permission
  - call -> execute
  - isReadOnly/isDestructive/isConcurrencySafe -> safety_level, concurrency_safe
  - interruptBehavior -> interrupt_behavior
  - maxResultSizeChars -> max_result_size

Every spacecraft capability (sensor read, thruster fire, anomaly query) is an ARIATool.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

import structlog

from aria.metrics.collector import MetricsCollector
from aria.core.types import (
    AuthorityLevel,
    InterruptBehavior,
    SafetyLevel,
    Severity,
    ToolCategory,
)

logger = structlog.get_logger()

T_In = TypeVar("T_In")
T_Out = TypeVar("T_Out")


@dataclass(frozen=True)
class ValidationResult:
    """Result of input validation."""

    valid: bool
    message: str = ""


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool execution.

    """

    success: bool
    data: Any = None
    error: str | None = None
    confidence: float = 1.0
    execution_time_ms: float = 0.0
    tool_name: str = ""
    call_id: str = ""
    side_effects: tuple[str, ...] = ()
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ToolHealthStatus:
    """Runtime health tracking for a registered tool."""

    tool_name: str
    version: str
    total_calls: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0
    avg_latency_ms: float = 0.0
    last_execution: datetime | None = None
    is_degraded: bool = False
    circuit_breaker_open: bool = False
    circuit_breaker_opens_at: int = 5  # consecutive failures to trip

    def record_success(self, latency_ms: float) -> None:
        self.total_calls += 1
        self.consecutive_failures = 0
        self.last_execution = datetime.now(timezone.utc)
        # Exponential moving average
        alpha = 0.1
        self.avg_latency_ms = alpha * latency_ms + (1 - alpha) * self.avg_latency_ms
        if self.circuit_breaker_open:
            self.circuit_breaker_open = False
            self.is_degraded = False

    def record_failure(self) -> None:
        self.total_calls += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_execution = datetime.now(timezone.utc)
        if self.consecutive_failures >= self.circuit_breaker_opens_at:
            self.circuit_breaker_open = True
            self.is_degraded = True


class ARIATool(ABC):
    """Base class for all ARIA tools.

    Subclass this for every capability ARIA can invoke:
      - DsremoQueryAnomalies
      - ConjunctionWatchRunScreening
      - GenAstraAnalyzeBiosignature
      - ReadSensor, FireThruster, AdjustHeater, etc.

      1. validate_input()
      2. check_permission()
      3. execute()
      4. record health metrics
    """

    # --- Subclass must set these ---
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    category: ToolCategory = ToolCategory.DIAGNOSTIC
    authority_level: AuthorityLevel = AuthorityLevel.SENSOR_ONLY
    safety_level: SafetyLevel = SafetyLevel.READ_ONLY
    concurrency_safe: bool = True
    interrupt_behavior: InterruptBehavior = InterruptBehavior.CANCEL
    timeout_ms: int = 5000
    max_result_size: int = 100_000  # chars

    # Wiring audit Pass 4 (F7.5 / F9.5) — explicit flag distinguishing
    # tools that produce a real side-effect (publish to bus, mutate
    # state, hit hardware) from tools that return canned advisory data.
    # The cognitive engine surfaces this in the LLM context so the
    # model knows whether ``success=True`` means "a real action fired"
    # or "I rendered a recommendation; the operator has to act."
    # ``"effect"`` is left as a string rather than an enum to keep the
    # extension surface open (e.g. ``"hal_passthrough"`` once HAL
    # ships).  Stub tools without a real bus publish should set this
    # to ``"advisory"`` so the LLM does not mistake them for actuators.
    effect: str = "real"   # "real" (default), "advisory", "hal_passthrough", ...

    # Optional shared metrics collector — set by ToolRegistry after registration
    _metrics: MetricsCollector | None = None

    def __init__(self) -> None:
        self._health = ToolHealthStatus(tool_name=self.name, version=self.version)

    @property
    def health(self) -> ToolHealthStatus:
        return self._health

    @property
    def is_read_only(self) -> bool:
        return self.safety_level == SafetyLevel.READ_ONLY

    @property
    def is_destructive(self) -> bool:
        return self.safety_level in (SafetyLevel.IRREVERSIBLE, SafetyLevel.EMERGENCY)

    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for this tool's input parameters."""
        ...

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        """Validate input params against schema. Override for custom validation."""
        return ValidationResult(valid=True)

    async def check_permission(
        self,
        params: dict[str, Any],
        current_authority: AuthorityLevel,
        mission_phase: Any = None,
    ) -> bool:
        """Check if the current authority level permits this tool invocation.

        """
        return current_authority.value >= self.authority_level.value

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute the tool. This is the core logic."""
        ...

    async def safe_execute(
        self,
        params: dict[str, Any],
        current_authority: AuthorityLevel = AuthorityLevel.ROUTINE,
    ) -> ToolResult:
        """Full lifecycle: validate -> permission -> execute -> record.

        This is the method the coordinator calls. Never call execute() directly.
        """
        call_id = uuid.uuid4().hex[:12]

        # Circuit breaker check — with half-open timeout (300s cooldown).
        # Without this, a tool that fails 5× is permanently offline even
        # after the underlying issue is fixed (stuck-open circuit breaker).
        if self._health.circuit_breaker_open:
            last = self._health.last_execution
            cooldown_s = 300.0  # 5 min half-open window
            if last and (datetime.now(timezone.utc) - last).total_seconds() > cooldown_s:
                logger.info("tool.circuit_breaker_half_open", tool=self.name)
                self._health.circuit_breaker_open = False
                self._health.consecutive_failures = 0
            else:
                logger.warning("tool.circuit_breaker_open", tool=self.name, call_id=call_id)
                return ToolResult(
                    success=False,
                    error=f"Circuit breaker open for {self.name} after {self._health.consecutive_failures} failures",
                    tool_name=self.name,
                    call_id=call_id,
                )

        # Step 1: Validate input
        validation = self.validate_input(params)
        if not validation.valid:
            logger.warning(
                "tool.validation_failed",
                tool=self.name,
                message=validation.message,
                call_id=call_id,
            )
            return ToolResult(
                success=False,
                error=f"Validation failed: {validation.message}",
                tool_name=self.name,
                call_id=call_id,
            )

        # Step 2: Check permission
        permitted = await self.check_permission(params, current_authority)
        if not permitted:
            logger.warning(
                "tool.permission_denied",
                tool=self.name,
                required=self.authority_level.name,
                current=current_authority.name,
                call_id=call_id,
            )
            return ToolResult(
                success=False,
                error=f"Permission denied: requires {self.authority_level.name}, have {current_authority.name}",
                tool_name=self.name,
                call_id=call_id,
            )

        # Step 3: Execute with timeout
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.execute(params),
                timeout=self.timeout_ms / 1000.0,
            )
            latency_ms = (time.monotonic() - start) * 1000
            result = ToolResult(
                success=result.success,
                data=result.data,
                error=result.error,
                confidence=result.confidence,
                execution_time_ms=latency_ms,
                tool_name=self.name,
                call_id=call_id,
                side_effects=result.side_effects,
            )
            self._health.record_success(latency_ms)
            if self._metrics:
                self._metrics.increment("aria.tool.calls")
                self._metrics.increment(f"aria.tool.{self.name}.calls")
                self._metrics.record_latency(f"tool.{self.name}", latency_ms)
            logger.info(
                "tool.executed",
                tool=self.name,
                success=result.success,
                latency_ms=round(latency_ms, 1),
                call_id=call_id,
            )
            return result

        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - start) * 1000
            self._health.record_failure()
            if self._metrics:
                self._metrics.increment("aria.tool.timeouts")
                self._metrics.increment(f"aria.tool.{self.name}.timeouts")
            logger.error(
                "tool.timeout",
                tool=self.name,
                timeout_ms=self.timeout_ms,
                call_id=call_id,
            )
            return ToolResult(
                success=False,
                error=f"Timeout after {self.timeout_ms}ms",
                execution_time_ms=latency_ms,
                tool_name=self.name,
                call_id=call_id,
            )

        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            self._health.record_failure()
            if self._metrics:
                self._metrics.increment("aria.tool.errors")
                self._metrics.increment(f"aria.tool.{self.name}.errors")
            logger.error(
                "tool.exception",
                tool=self.name,
                error=str(exc),
                call_id=call_id,
            )
            return ToolResult(
                success=False,
                error=str(exc),
                execution_time_ms=latency_ms,
                tool_name=self.name,
                call_id=call_id,
            )

    def to_schema(self) -> dict[str, Any]:
        """Export tool definition for LLM tool catalog.

        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category.name,
            "authority_level": self.authority_level.name,
            "safety_level": self.safety_level.name,
            "concurrency_safe": self.concurrency_safe,
            "timeout_ms": self.timeout_ms,
            # Wiring audit Pass 4 (F7.5 / F9.5) — surface the
            # advisory-vs-real-side-effect flag so the LLM knows
            # whether a successful tool call actually fired hardware.
            "effect": self.effect,
            "input_schema": self.input_schema(),
        }
