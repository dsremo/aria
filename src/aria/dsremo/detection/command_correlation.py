"""Command-response correlation — suppress expected telemetry changes.

When a ground station sends a command (e.g., heater ON), the subsequent
telemetry change is expected, not anomalous.  Without command awareness,
every commanded state change triggers false positives.

This module provides a simple command registration API:
    1. Operator registers a command with expected affected parameters
    2. Detection pipeline checks if a recent command explains the change
    3. If yes, suppress the anomaly (not the detection — we still run it)

Usage:
    register_command("SAT-1", "HEATER_ON", ["panel_temp_sun", "panel_temp_shade"], duration_s=600)
    # Next 10 minutes: anomalies on panel_temp_sun/shade are suppressed

    is_command_expected("SAT-1", "panel_temp_sun")  # True for 10 min
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class CommandRecord:
    """A registered command and its expected telemetry effects."""
    satellite_id: str
    command_name: str
    affected_parameters: list[str]
    registered_at: float = field(default_factory=time.time)
    duration_s: float = 300.0  # how long to suppress (default 5 min)
    reason: str = ""

    @property
    def expires_at(self) -> float:
        return self.registered_at + self.duration_s

    @property
    def is_active(self) -> bool:
        return time.time() < self.expires_at


class CommandCorrelator:
    """Registry of recent commands for anomaly suppression."""

    def __init__(self) -> None:
        self._commands: list[CommandRecord] = []

    def register(
        self,
        satellite_id: str,
        command_name: str,
        affected_parameters: list[str],
        duration_s: float = 300.0,
        reason: str = "",
    ) -> CommandRecord:
        """Register a command that will cause expected telemetry changes."""
        cmd = CommandRecord(
            satellite_id=satellite_id,
            command_name=command_name,
            affected_parameters=affected_parameters,
            duration_s=duration_s,
            reason=reason,
        )
        self._commands.append(cmd)
        self._gc()  # clean up expired
        logger.info(
            "command_registered",
            satellite=satellite_id,
            command=command_name,
            params=affected_parameters,
            duration_s=duration_s,
        )
        return cmd

    def is_command_expected(self, satellite_id: str, parameter: str) -> bool:
        """Check if a recent command explains a change in this parameter."""
        now = time.time()
        for cmd in self._commands:
            if (cmd.satellite_id == satellite_id
                    and parameter in cmd.affected_parameters
                    and cmd.expires_at > now):
                return True
        return False

    def get_active_command(self, satellite_id: str, parameter: str) -> CommandRecord | None:
        """Return the active command affecting this parameter, if any."""
        now = time.time()
        for cmd in self._commands:
            if (cmd.satellite_id == satellite_id
                    and parameter in cmd.affected_parameters
                    and cmd.expires_at > now):
                return cmd
        return None

    def list_active(self, satellite_id: str | None = None) -> list[CommandRecord]:
        """Return all active (non-expired) commands."""
        self._gc()
        if satellite_id:
            return [c for c in self._commands if c.satellite_id == satellite_id and c.is_active]
        return [c for c in self._commands if c.is_active]

    def _gc(self) -> None:
        """Remove expired commands."""
        now = time.time()
        self._commands = [c for c in self._commands if c.expires_at > now]


# Singleton instance
_correlator = CommandCorrelator()


def get_command_correlator() -> CommandCorrelator:
    return _correlator
