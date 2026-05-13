"""Captain's Console MVP — terminal-based dashboard for ARIA.

Displays:
  - System status (mission, phase, agents)
  - Active alerts by severity
  - Power / Navigation / Telemetry summaries
  - Text command interface

This is the MVP — Sprint 4 deliverable.
Production version will be a web-based React dashboard.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority, Severity
from aria.security.auth import CommandAuthenticator, CommandCredential
from aria.security.sanitizer import InputSanitizer

logger = structlog.get_logger()

# ANSI color codes
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

SEVERITY_COLORS = {
    "NOMINAL": GREEN,
    "WATCH": CYAN,
    "WARNING": YELLOW,
    "CRITICAL": RED,
    "EMERGENCY": f"{RED}{BOLD}",
}


class CaptainConsole:
    """Terminal-based Captain's Console.

    Subscribes to all alert/status topics and renders a live dashboard.
    Accepts text commands for querying ARIA.
    """

    def __init__(
        self,
        bus: MessageBus,
        system_status_fn: Any = None,
        shared_secret: str | None = None,
    ) -> None:
        self._bus = bus
        self._system_status_fn = system_status_fn
        self._alerts: list[dict[str, Any]] = []
        self._max_alerts = 50
        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []
        # CommandAuthenticator now refuses well-known defaults and short
        # secrets (audit CRIT-1).  Resolution order: explicit kwarg →
        # ARIA_CONSOLE_SECRET env var → RuntimeError.
        self._auth = CommandAuthenticator(shared_secret=shared_secret)
        self._sanitizer = InputSanitizer()
        # Create a session token for the captain operator
        self._captain_token = self._auth.create_session("captain")

    async def start(self) -> None:
        """Start the console — subscribe to events and begin rendering."""
        self._running = True
        self._bus.subscribe("aria.captain.alert", self._on_alert)
        self._bus.subscribe("aria.anomaly.*", self._on_anomaly)
        self._bus.subscribe("aria.power.*", self._on_power_event)

        self._tasks.append(asyncio.create_task(self._render_loop()))
        self._tasks.append(asyncio.create_task(self._input_loop()))
        logger.info("console.started")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _on_alert(self, message: Message) -> None:
        """Receive captain alerts."""
        alert = message.payload
        alert["received_at"] = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._alerts.append(alert)
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts:]

        # Print alert immediately
        severity = alert.get("severity", "NOMINAL")
        color = SEVERITY_COLORS.get(severity, RESET)
        msg = alert.get("description", alert.get("message", ""))
        print(f"\n{color}[{severity}]{RESET} {msg}")

        if alert.get("type") == "approval_required":
            decision_id = alert.get("decision_id", "")
            timeout = alert.get("timeout_s", 30)
            print(f"  {YELLOW}Approval required. Decision ID: {decision_id}")
            print(f"  Respond within {timeout}s or ARIA will act autonomously.{RESET}")
            print(f"  Type: approve {decision_id} / reject {decision_id} / override {decision_id} <option>")

    async def _on_anomaly(self, message: Message) -> None:
        """Log anomaly events."""
        severity = message.payload.get("severity", "NOMINAL")
        msg = message.payload.get("message", "")
        color = SEVERITY_COLORS.get(severity, RESET)
        source = message.source_agent
        print(f"  {DIM}[{source}]{RESET} {color}{msg}{RESET}")

    async def _on_power_event(self, message: Message) -> None:
        """Log power events."""
        if "load_shed" in message.topic:
            loads = message.payload.get("shed_loads", [])
            reason = message.payload.get("reason", "")
            print(f"  {RED}[POWER] Load shed executed: {loads} (reason: {reason}){RESET}")

    def _render_status(self) -> str:
        """Render the status header."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        status = self._system_status_fn() if self._system_status_fn else {}

        mission = status.get("mission", "ARIA")
        phase = status.get("phase", "UNKNOWN")
        sys_status = status.get("status", "UNKNOWN")
        agents = status.get("agents", {})
        tools = status.get("tools", {})

        status_color = GREEN if sys_status == "RUNNING" else YELLOW

        lines = [
            f"\n{BOLD}{'=' * 70}{RESET}",
            f"  {BOLD}ARIA{RESET}  |  {now}  |  Phase: {CYAN}{phase}{RESET}",
            f"  Status: {status_color}{sys_status}{RESET}  |  Mission: {mission}",
            f"  Agents: {len(agents)} active  |  Tools: {tools.get('total_tools', 0)} ({tools.get('healthy', 0)} healthy)",
            f"{BOLD}{'=' * 70}{RESET}",
        ]

        # Recent alerts
        if self._alerts:
            lines.append(f"\n  {BOLD}Recent Alerts:{RESET}")
            for alert in self._alerts[-5:]:
                sev = alert.get("severity", "")
                color = SEVERITY_COLORS.get(sev, RESET)
                ts = alert.get("received_at", "")
                msg = alert.get("description", alert.get("message", ""))[:60]
                lines.append(f"  {DIM}{ts}{RESET} {color}[{sev}]{RESET} {msg}")
        else:
            lines.append(f"\n  {GREEN}No alerts. All systems nominal.{RESET}")

        lines.append(f"\n{DIM}  Type a command or 'help' for options.{RESET}")
        lines.append(f"  {BOLD}ARIA>{RESET} ")

        return "\n".join(lines)

    async def _render_loop(self) -> None:
        """Periodically refresh the display."""
        while self._running:
            try:
                print(self._render_status(), end="", flush=True)
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break

    async def _input_loop(self) -> None:
        """Read commands from stdin (non-blocking)."""
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, input),
                    timeout=60,
                )
                await self._handle_command(line.strip())
            except asyncio.TimeoutError:
                continue
            except (asyncio.CancelledError, EOFError):
                break

    async def _handle_command(self, command: str) -> None:
        """Process a command from the Captain — sanitize and authenticate first."""
        if not command:
            return

        # Sanitize input
        san = self._sanitizer.sanitize_text(command)
        if not san.clean:
            print(f"  {RED}[SECURITY] Input rejected: {san.patterns_found}{RESET}")
            return
        command = san.sanitized

        # Authenticate using captain session token
        cred = CommandCredential(issuer="captain", session_token=self._captain_token)
        from aria.security.auth import AuthResult
        result = self._auth.authenticate(cred)
        if result != AuthResult.ACCEPTED:
            print(f"  {RED}[AUTH] Command rejected: {result.name}{RESET}")
            return

        parts = command.split()
        cmd = parts[0].lower()

        if cmd == "help":
            print(f"""
{BOLD}ARIA Commands:{RESET}
  status          — Show full system status
  alerts          — Show recent alerts
  anomalies       — Query Dsremo for anomalies
  nav             — Show navigation state
  power           — Show power state
  approve <id>    — Approve a pending decision
  reject <id>     — Reject a pending decision
  tools           — List registered tools
  quit            — Shutdown ARIA
""")

        elif cmd == "status":
            status = self._system_status_fn() if self._system_status_fn else {}
            for k, v in status.items():
                if isinstance(v, dict):
                    print(f"  {BOLD}{k}:{RESET}")
                    for kk, vv in v.items():
                        print(f"    {kk}: {vv}")
                else:
                    print(f"  {k}: {v}")

        elif cmd == "alerts":
            if not self._alerts:
                print(f"  {GREEN}No alerts.{RESET}")
            for alert in self._alerts[-10:]:
                sev = alert.get("severity", "")
                color = SEVERITY_COLORS.get(sev, RESET)
                msg = alert.get("description", alert.get("message", ""))
                print(f"  {color}[{sev}]{RESET} {msg}")

        elif cmd in ("approve", "reject") and len(parts) > 1:
            decision_id = parts[1]
            approved = cmd == "approve"
            await self._bus.publish(
                Message(
                    topic="aria.captain.response",
                    payload={"decision_id": decision_id, "approved": approved},
                    priority=EventPriority.P1_CRITICAL,
                    source_agent="captain",
                )
            )
            action = "approved" if approved else "rejected"
            print(f"  Decision {decision_id} {action}.")

        elif cmd == "quit":
            print(f"  {YELLOW}Shutting down ARIA...{RESET}")
            self._running = False

        else:
            # Forward as a natural language query to the cognitive engine
            await self._bus.publish(
                Message(
                    topic="aria.captain.query",
                    payload={"text": command},
                    priority=EventPriority.P3_ROUTINE,
                    source_agent="captain",
                )
            )
            print(f"  {DIM}Processing: {command}{RESET}")
