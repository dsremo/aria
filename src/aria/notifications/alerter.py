"""Alert Notification System — sends alerts via webhook, file, or console.

Supports multiple notification channels:
  - Console (stdout with severity coloring)
  - File (append to alert log file)
  - Webhook (POST JSON to any URL — Slack, Discord, custom)
  - Callback (in-process function call for testing)

Usage:
    alerter = AlertNotifier()
    alerter.add_channel(ConsoleChannel())
    alerter.add_channel(WebhookChannel("https://hooks.slack.com/..."))
    alerter.add_channel(FileChannel("/var/log/aria/alerts.log"))

    alerter.notify(Alert(
        severity="CRITICAL",
        subsystem="power",
        message="Battery SoC below 10%",
        timestamp=time.time(),
    ))
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import structlog

logger = structlog.get_logger()


@dataclass
class Alert:
    """A single alert notification."""
    severity: str  # WATCH, WARNING, CRITICAL, EMERGENCY
    subsystem: str
    message: str
    timestamp: float = 0.0
    mission_year: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @property
    def is_critical(self) -> bool:
        return self.severity in ("CRITICAL", "EMERGENCY")


class NotificationChannel(ABC):
    """Base class for alert delivery channels."""

    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """Send alert. Returns True if successful."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class ConsoleChannel(NotificationChannel):
    """Print alerts to stdout with severity coloring."""

    COLORS = {
        "WATCH": "\033[36m",     # Cyan
        "WARNING": "\033[33m",   # Yellow
        "CRITICAL": "\033[31m",  # Red
        "EMERGENCY": "\033[41m", # Red background
    }
    RESET = "\033[0m"

    def __init__(self, min_severity: str = "WARNING") -> None:
        self._min = min_severity
        self._severity_order = ["WATCH", "WARNING", "CRITICAL", "EMERGENCY"]

    @property
    def name(self) -> str:
        return "console"

    def send(self, alert: Alert) -> bool:
        if self._severity_order.index(alert.severity) < self._severity_order.index(self._min):
            return True  # Filtered out, not a failure

        color = self.COLORS.get(alert.severity, "")
        print(f"{color}[{alert.severity}]{self.RESET} {alert.subsystem}: {alert.message}")
        return True


class FileChannel(NotificationChannel):
    """Append alerts to a log file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return f"file:{self._path}"

    def send(self, alert: Alert) -> bool:
        try:
            with open(self._path, "a") as f:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(alert.timestamp))
                f.write(f"{ts} [{alert.severity}] {alert.subsystem}: {alert.message}\n")
            return True
        except Exception as e:
            logger.error("alerter.file_failed", path=str(self._path), error=str(e))
            return False


class WebhookChannel(NotificationChannel):
    """POST alert as JSON to a webhook URL (Slack, Discord, custom)."""

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._headers = headers or {"Content-Type": "application/json"}

    @property
    def name(self) -> str:
        return f"webhook:{self._url[:50]}"

    def send(self, alert: Alert) -> bool:
        try:
            import urllib.request

            from aria.security.guard import GuardError, validate_outbound_url

            # Reject webhook URLs pointing at private/internal IPs to prevent
            # SSRF — even if the operator configures a hostile target, ARIA
            # refuses to deliver.
            try:
                validate_outbound_url(
                    self._url,
                    allowed_schemes=("https",),
                    host_allowlist=None,  # webhook hosts are operator-chosen
                )
            except GuardError as exc:
                logger.warning(
                    "alerter.webhook_blocked",
                    url=self._url[:50], reason=str(exc),
                )
                return False

            data = json.dumps({
                "text": f"[{alert.severity}] {alert.subsystem}: {alert.message}",
                "severity": alert.severity,
                "subsystem": alert.subsystem,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "details": alert.details,
            }).encode()
            req = urllib.request.Request(
                self._url, data=data, headers=self._headers,
            )
            urllib.request.urlopen(req, timeout=5)  # nosec B310 (URL validated by guard.validate_outbound_url above)
            return True
        except Exception as e:
            logger.warning("alerter.webhook_failed", url=self._url[:50], error=str(e))
            return False


class CallbackChannel(NotificationChannel):
    """Call a function with the alert — for testing and in-process integration."""

    def __init__(self, callback: Callable[[Alert], None], name: str = "callback") -> None:
        self._callback = callback
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def send(self, alert: Alert) -> bool:
        try:
            self._callback(alert)
            return True
        except Exception as exc:
            # R65 (2026-04-24): was silent `return False` — if the
            # notification callback crashes (e.g. mission-critical
            # crew-wake path) the caller couldn't distinguish "channel
            # not registered" from "channel raised".  Log the failure.
            import structlog
            structlog.get_logger().error(
                "alerter.callback_failed",
                channel=self._name,
                severity=getattr(alert, "severity", "unknown"),
                error=f"{type(exc).__name__}: {exc}",
            )
            return False


class AlertNotifier:
    """Central alert notification dispatcher.

    Routes alerts to multiple channels with filtering, rate limiting,
    and delivery tracking.
    """

    def __init__(self) -> None:
        self._channels: list[NotificationChannel] = []
        self._history: list[Alert] = []
        self._max_history = 1000
        self._sent_count = 0
        self._failed_count = 0
        # Rate limiting: max alerts per minute per subsystem
        self._rate_limit = 10
        self._rate_window: dict[str, list[float]] = {}

    def add_channel(self, channel: NotificationChannel) -> None:
        self._channels.append(channel)

    def remove_channel(self, name: str) -> None:
        self._channels = [c for c in self._channels if c.name != name]

    def notify(self, alert: Alert) -> int:
        """Send alert to all channels. Returns number of successful deliveries."""
        # Rate limiting
        key = alert.subsystem
        now = time.time()
        if key not in self._rate_window:
            self._rate_window[key] = []
        self._rate_window[key] = [t for t in self._rate_window[key] if now - t < 60]
        if len(self._rate_window[key]) >= self._rate_limit:
            return 0  # Rate limited
        self._rate_window[key].append(now)

        # Send to all channels
        successes = 0
        for channel in self._channels:
            try:
                if channel.send(alert):
                    successes += 1
                    self._sent_count += 1
                else:
                    self._failed_count += 1
            except Exception:
                self._failed_count += 1

        # Store in history
        self._history.append(alert)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return successes

    def notify_from_event(self, event: dict[str, Any]) -> int:
        """Create and send alert from a simulation event dict."""
        alert = Alert(
            severity=event.get("severity", "WATCH"),
            subsystem=event.get("subsystem", "unknown"),
            message=event.get("message", ""),
            mission_year=event.get("year", 0),
            details=event,
        )
        return self.notify(alert)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "channels": len(self._channels),
            "channel_names": [c.name for c in self._channels],
            "total_sent": self._sent_count,
            "total_failed": self._failed_count,
            "history_size": len(self._history),
        }

    def recent(self, limit: int = 20) -> list[Alert]:
        return self._history[-limit:]

    def recent_by_severity(self, severity: str, limit: int = 10) -> list[Alert]:
        return [a for a in self._history if a.severity == severity][-limit:]
