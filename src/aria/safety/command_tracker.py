"""Command sequence tracker — ensures every command gets a response.

Implements the F Prime CmdDispatcher pattern: every command dispatched
to a subsystem agent is tracked with a sequence number and deadline.
If the agent doesn't respond within the deadline, the command is
marked as timed-out and a WARNING is emitted.

This closes the fire-and-forget gap in ARIA's event bus — previously,
commands published to the bus had no guarantee of completion tracking.

Pattern studied from NASA JPL F Prime CommandDispatcherImpl.cpp
(Apache 2.0) and reimplemented for ARIA's Python event bus.

Usage:
    tracker = CommandTracker(bus=get_event_bus())
    seq = tracker.dispatch("thermal.set_heater", {"zone": 3, "power": 500})
    # ... agent processes and calls:
    tracker.complete(seq, success=True)
    # Or if agent is slow:
    tracker.check_timeouts()  # emits WARNING for overdue commands
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TrackedCommand:
    """A dispatched command awaiting response."""
    seq: int
    topic: str
    params: Dict[str, Any]
    dispatched_at: float        # monotonic time
    deadline_s: float           # max time to wait
    source: str = ""            # who dispatched it
    status: str = "pending"     # pending, completed, failed, timed_out
    response: Optional[Dict[str, Any]] = None
    completed_at: float = 0.0


class CommandTracker:
    """Tracks dispatched commands and ensures completion responses.

    Every command gets a sequence number. Agents MUST call complete()
    or fail() with that sequence number. check_timeouts() detects
    commands that exceeded their deadline without a response.
    """

    def __init__(self, bus: Any = None, default_timeout_s: float = 30.0) -> None:
        self._bus = bus
        self._default_timeout_s = default_timeout_s
        self._seq_counter: int = 0
        self._pending: Dict[int, TrackedCommand] = {}
        self._history: List[TrackedCommand] = []
        self._lock = threading.Lock()

        # Metrics
        self.commands_dispatched: int = 0
        self.commands_completed: int = 0
        self.commands_failed: int = 0
        self.commands_timed_out: int = 0

    def dispatch(
        self,
        topic: str,
        params: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
        source: str = "",
        sim_time_yr: float = 0.0,
    ) -> int:
        """Dispatch a command and track it.

        Args:
            topic: Command topic (e.g., "thermal.set_heater")
            params: Command parameters
            timeout_s: Max time to wait for response (default: 30s)
            source: Who dispatched this command

        Returns:
            Sequence number for tracking
        """
        with self._lock:
            self._seq_counter += 1
            seq = self._seq_counter

        cmd = TrackedCommand(
            seq=seq,
            topic=topic,
            params=params or {},
            dispatched_at=time.monotonic(),
            deadline_s=timeout_s or self._default_timeout_s,
            source=source,
        )

        with self._lock:
            self._pending[seq] = cmd
            self.commands_dispatched += 1

        # Publish command on the bus
        if self._bus is not None:
            from aria.safety._bus_publish import publish_compat
            publish_compat(
                self._bus,
                topic,
                severity="info",
                source=source or "command_tracker",
                payload={"seq": seq, **cmd.params},
                sim_time_yr=sim_time_yr,
            )

        return seq

    def complete(self, seq: int, success: bool = True, response: Optional[Dict[str, Any]] = None) -> bool:
        """Mark a command as completed or failed.

        Args:
            seq: Sequence number from dispatch()
            success: True if command succeeded
            response: Optional response data

        Returns:
            True if the command was found and updated
        """
        with self._lock:
            cmd = self._pending.pop(seq, None)
            if cmd is None:
                return False

            cmd.status = "completed" if success else "failed"
            cmd.response = response
            cmd.completed_at = time.monotonic()

            if success:
                self.commands_completed += 1
            else:
                self.commands_failed += 1

            self._history.append(cmd)
            if len(self._history) > 10_000:
                self._history = self._history[-5_000:]

            return True

    def fail(self, seq: int, error: str = "") -> bool:
        """Convenience: mark a command as failed."""
        return self.complete(seq, success=False, response={"error": error})

    def check_timeouts(self, sim_time_yr: float = 0.0) -> List[int]:
        """Check for commands that exceeded their deadline.

        Returns list of timed-out sequence numbers.
        """
        now = time.monotonic()
        timed_out: List[int] = []

        with self._lock:
            for seq, cmd in list(self._pending.items()):
                elapsed = now - cmd.dispatched_at
                if elapsed > cmd.deadline_s:
                    cmd.status = "timed_out"
                    cmd.completed_at = now
                    self.commands_timed_out += 1
                    timed_out.append(seq)
                    self._history.append(cmd)
                    del self._pending[seq]

        # Emit warnings for timed-out commands
        if self._bus is not None and timed_out:
            from aria.safety._bus_publish import publish_compat
            for timed_out_seq in timed_out:
                cmd = next((c for c in self._history if c.seq == timed_out_seq), None)
                if cmd:
                    publish_compat(
                        self._bus,
                        "command.timeout",
                        severity="warning",
                        source="command_tracker",
                        payload={
                            "seq": timed_out_seq,
                            "topic": cmd.topic,
                            "elapsed_s": cmd.completed_at - cmd.dispatched_at,
                            "deadline_s": cmd.deadline_s,
                        },
                        sim_time_yr=sim_time_yr,
                    )

        return timed_out

    def stats(self) -> Dict[str, Any]:
        """Return command tracking statistics."""
        with self._lock:
            return {
                "dispatched": self.commands_dispatched,
                "completed": self.commands_completed,
                "failed": self.commands_failed,
                "timed_out": self.commands_timed_out,
                "pending": len(self._pending),
                "success_rate": self.commands_completed / max(self.commands_dispatched, 1),
            }

    def pending_commands(self) -> List[Dict[str, Any]]:
        """List currently pending commands."""
        with self._lock:
            return [
                {
                    "seq": cmd.seq,
                    "topic": cmd.topic,
                    "age_s": time.monotonic() - cmd.dispatched_at,
                    "deadline_s": cmd.deadline_s,
                    "source": cmd.source,
                }
                for cmd in self._pending.values()
            ]
