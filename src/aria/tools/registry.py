"""Tool registry: discover, register, validate, and invoke ARIA tools.

  - getAllBaseTools() -> register()
  - getTools() -> get_tools()
  - filterToolsByDenyRules() -> get_tools(exclude_categories=...)
  - Tool schemas exported for LLM context -> export_schemas()
"""

from __future__ import annotations

from typing import Any

import structlog

from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, ToolCategory
from aria.metrics.collector import MetricsCollector

logger = structlog.get_logger()


class ToolRegistry:
    """Central registry for all ARIA tools.

    The coordinator and agents use this to discover and invoke tools.
    Tools self-register on startup. The registry enforces:
      - No duplicate tool names
      - Schema validation on registration
      - Health tracking per tool
      - Category-based filtering
    """

    def __init__(self, metrics: MetricsCollector | None = None) -> None:
        self._tools: dict[str, ARIATool] = {}
        self._metrics = metrics

    @property
    def count(self) -> int:
        return len(self._tools)

    def register(self, tool: ARIATool) -> None:
        """Register a tool. Raises ValueError on duplicate name."""
        if not tool.name:
            raise ValueError("Tool must have a non-empty name")
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")

        # Validate the tool has a proper schema
        try:
            schema = tool.input_schema()
            if not isinstance(schema, dict):
                raise TypeError(f"input_schema() must return dict, got {type(schema)}")
        except Exception as exc:
            raise ValueError(f"Tool '{tool.name}' has invalid schema: {exc}") from exc

        self._tools[tool.name] = tool
        # Propagate shared metrics collector to the tool
        if self._metrics is not None:
            tool._metrics = self._metrics
        logger.info("tool.registered", name=tool.name, category=tool.category.name, version=tool.version)

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        if name in self._tools:
            del self._tools[name]
            logger.info("tool.unregistered", name=name)

    def get(self, name: str) -> ARIATool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_tools(
        self,
        category: ToolCategory | None = None,
        exclude_categories: set[ToolCategory] | None = None,
        max_authority: AuthorityLevel | None = None,
    ) -> list[ARIATool]:
        """Get tools filtered by category and/or authority level.

        """
        tools = list(self._tools.values())

        if category is not None:
            tools = [t for t in tools if t.category == category]

        if exclude_categories:
            tools = [t for t in tools if t.category not in exclude_categories]

        if max_authority is not None:
            tools = [t for t in tools if t.authority_level.value <= max_authority.value]

        return tools

    def get_healthy_tools(self) -> list[ARIATool]:
        """Get only tools whose circuit breaker is not open."""
        return [t for t in self._tools.values() if not t.health.circuit_breaker_open]

    async def invoke(
        self,
        tool_name: str,
        params: dict[str, Any],
        authority: AuthorityLevel = AuthorityLevel.ROUTINE,
    ) -> ToolResult:
        """Invoke a tool by name through the full safe_execute lifecycle.

        This is the primary entry point used by the cognitive loop.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
                tool_name=tool_name,
            )

        return await tool.safe_execute(params, authority)

    async def safe_invoke(
        self,
        tool_name: str,
        params: dict[str, Any],
        authority: AuthorityLevel = AuthorityLevel.ROUTINE,
    ) -> ToolResult:
        """LLM-bound invocation that requires a F-6 capability token.

        Unlike `invoke`, this entry point refuses any call without a
        valid `_capability_token` in `params`. The token must:
          - name this exact tool,
          - hash the exact arg dict (with `_capability_token` stripped),
          - be unexpired and unique-by-nonce (one-shot).

        The token is stripped before the tool sees its params, so the
        downstream tool is unaware of the failsafe layer.

        Use from the cognitive engine when dispatching LLM-derived
        tool calls. Agents with their own authority continue using
        `invoke`.
        """
        from aria.cognitive.capability_token import verify_token

        encoded = params.get("_capability_token")
        if not encoded or not isinstance(encoded, str):
            return ToolResult(
                success=False,
                error=(
                    f"safe_invoke('{tool_name}') refused: missing "
                    f"_capability_token (F-6)"
                ),
                tool_name=tool_name,
            )
        result = verify_token(
            encoded,
            expected_tool=tool_name,
            args=params,
        )
        if not result.valid:
            return ToolResult(
                success=False,
                error=f"capability token rejected: {result.reason}",
                tool_name=tool_name,
            )
        # Strip the meta param before the tool sees it.
        cleaned = {k: v for k, v in params.items() if k != "_capability_token"}
        return await self.invoke(tool_name, cleaned, authority)

    def export_schemas(self, category: ToolCategory | None = None) -> list[dict[str, Any]]:
        """Export tool schemas for LLM context injection.

        """
        tools = self.get_tools(category=category)
        return [t.to_schema() for t in tools]

    def health_report(self) -> dict[str, Any]:
        """System-wide tool health summary."""
        total = len(self._tools)
        healthy = sum(1 for t in self._tools.values() if not t.health.is_degraded)
        degraded = [t.name for t in self._tools.values() if t.health.is_degraded]
        tripped = [t.name for t in self._tools.values() if t.health.circuit_breaker_open]

        return {
            "total_tools": total,
            "healthy": healthy,
            "degraded": degraded,
            "circuit_breakers_open": tripped,
        }
