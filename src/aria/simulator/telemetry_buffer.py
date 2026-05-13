"""Double-buffered telemetry with dirty-flag optimization.

Implements the F Prime TlmChan pattern: two hash-table buffers alternate
between writer and reader roles. Subsystems write to the active buffer.
On each downlink cycle, pointers swap atomically. Only changed channels
are transmitted, reducing bus traffic dramatically.

This is production-critical: without buffering, every sensor reading
is a separate event on the bus with full serialization overhead. Under
high telemetry rates, the bus drowns in redundant data.

Pattern studied from NASA JPL F Prime Svc/TlmChan/TlmChan.cpp (Apache 2.0).

Usage:
    buf = TelemetryBuffer()
    buf.update("thermal.zone3.temp_k", 325.4)
    buf.update("power.bus_v", 28.1)
    # On each downlink cycle:
    changed = buf.swap_and_read()
    # changed = {"thermal.zone3.temp_k": 325.4, "power.bus_v": 28.1}
    # Next cycle, only newly changed values are returned
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional


class TelemetryBuffer:
    """Double-buffered telemetry store with atomic swap.

    Thread-safe: writers never block on readers, readers never see
    half-written entries.
    """

    def __init__(self) -> None:
        # Two buffers: active (writers use) and inactive (readers use)
        self._buffers: List[Dict[str, Any]] = [{}, {}]
        self._dirty: List[Dict[str, bool]] = [{}, {}]
        self._active: int = 0  # index of the active (writer) buffer
        self._lock = threading.Lock()

        # Metadata
        self._channel_units: Dict[str, str] = {}
        self._channel_limits: Dict[str, tuple] = {}  # (yellow_lo, yellow_hi, red_lo, red_hi)
        self._swap_count: int = 0
        self._total_updates: int = 0
        self._total_changed: int = 0

    def update(self, channel: str, value: Any) -> None:
        """Write a telemetry value to the active buffer.

        This is the hot path — called by every subsystem every tick.
        Must be fast and never block.
        """
        with self._lock:
            buf = self._buffers[self._active]
            dirty = self._dirty[self._active]
            old = buf.get(channel)
            buf[channel] = value
            if old != value:
                dirty[channel] = True
            self._total_updates += 1

    def update_batch(self, values: Dict[str, Any]) -> None:
        """Write multiple telemetry values atomically."""
        with self._lock:
            buf = self._buffers[self._active]
            dirty = self._dirty[self._active]
            for channel, value in values.items():
                old = buf.get(channel)
                buf[channel] = value
                if old != value:
                    dirty[channel] = True
            self._total_updates += len(values)

    def swap_and_read(self) -> Dict[str, Any]:
        """Atomically swap buffers and return only changed values.

        After swap, the old active buffer becomes the reader buffer.
        Only entries marked dirty are returned. This is the downlink
        cycle operation.

        Returns:
            Dict of {channel: value} for channels that changed since last swap.
        """
        with self._lock:
            # Swap active buffer
            reader_idx = self._active
            self._active = 1 - self._active

            # Copy dirty values from the reader buffer
            buf = self._buffers[reader_idx]
            dirty = self._dirty[reader_idx]

            changed: Dict[str, Any] = {}
            for channel, is_dirty in dirty.items():
                if is_dirty:
                    changed[channel] = buf[channel]
                    self._total_changed += 1

            # Clear dirty flags on the reader buffer
            dirty.clear()

            # Copy current values to the new active buffer so writers
            # see the latest values (not stale from 2 swaps ago)
            new_active = self._buffers[self._active]
            for k, v in buf.items():
                if k not in new_active:
                    new_active[k] = v

            self._swap_count += 1

        return changed

    def read_all(self) -> Dict[str, Any]:
        """Read all current telemetry values (non-swap, snapshot)."""
        with self._lock:
            return dict(self._buffers[self._active])

    def read_channel(self, channel: str, default: Any = None) -> Any:
        """Read a single channel value."""
        with self._lock:
            return self._buffers[self._active].get(channel, default)

    def register_channel(
        self,
        channel: str,
        units: str = "",
        limits: Optional[tuple] = None,
    ) -> None:
        """Register channel metadata (units, alarm limits).

        Args:
            channel: channel name
            units: display units (e.g., "K", "V", "rad/s")
            limits: (yellow_lo, yellow_hi, red_lo, red_hi) or None
        """
        if units:
            self._channel_units[channel] = units
        if limits:
            self._channel_limits[channel] = limits

    def check_limits(self) -> Dict[str, str]:
        """Check all channels against their registered limits.

        Returns dict of {channel: severity} for channels outside limits.
        severity is "yellow" or "red".
        """
        violations: Dict[str, str] = {}
        with self._lock:
            buf = self._buffers[self._active]
            for channel, limits in self._channel_limits.items():
                value = buf.get(channel)
                if value is None or not isinstance(value, (int, float)):
                    continue
                yellow_lo, yellow_hi, red_lo, red_hi = limits
                if value <= red_lo or value >= red_hi:
                    violations[channel] = "red"
                elif value <= yellow_lo or value >= yellow_hi:
                    violations[channel] = "yellow"
        return violations

    def stats(self) -> Dict[str, Any]:
        """Return telemetry buffer statistics."""
        with self._lock:
            return {
                "channels": len(self._buffers[self._active]),
                "swap_count": self._swap_count,
                "total_updates": self._total_updates,
                "total_changed": self._total_changed,
                "change_rate": self._total_changed / max(self._swap_count, 1),
            }
