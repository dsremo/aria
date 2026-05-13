"""Alert service — per-tenant anomaly notification dispatch.

Architecture:
  AlertRouter ABC — strategy pattern, one subclass per delivery channel.
  WebhookRouter   — HMAC-SHA256 signed POST (Slack, PagerDuty, custom).
  EmailRouter     — SMTP via asyncio.run_in_executor (stdlib smtplib, no new dep).
  AlertService    — class-level config cache; per-tenant dispatch + dedup + escalation.

Key design decisions:
  - Dedup key includes tenant_id → eliminates cross-tenant collision bug.
  - insert_alert() called before routers → persistence survives network failures.
  - asyncio.gather() for concurrent delivery → webhook + email in parallel.
  - load_configs() replaces singleton init_alert_service() → hot-reloadable.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import smtplib
import time
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from typing import ClassVar

import httpx
import structlog

from aria.dsremo.core.models import Anomaly, Severity

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Multilingual severity labels (ISRO operations requirement).
# ---------------------------------------------------------------------------

_SEVERITY_LABELS: dict[str, dict[str, str]] = {
    "en": {"critical": "CRITICAL", "warning": "WARNING", "watch": "WATCH", "nominal": "NOMINAL"},
    "hi": {"critical": "गंभीर", "warning": "चेतावनी", "watch": "निगरानी", "nominal": "सामान्य"},
}

# Default locale for alert messages.
_alert_locale: str = "en"


def set_alert_locale(locale: str) -> None:
    """Set the locale for alert messages (e.g. 'en', 'hi')."""
    global _alert_locale
    _alert_locale = locale


def get_severity_label(severity_value: str) -> str:
    """Return localized severity label."""
    labels = _SEVERITY_LABELS.get(_alert_locale, _SEVERITY_LABELS["en"])
    return labels.get(severity_value, severity_value.upper())


_dead_letters: list[dict] = []
_MAX_DEAD_LETTERS: int = 1000


# ---------------------------------------------------------------------------
# AlertRouter — strategy ABC
# ---------------------------------------------------------------------------

class AlertRouter(ABC):
    """Base class for alert delivery channels."""

    @abstractmethod
    async def send(self, anomaly: Anomaly, tenant_id: str) -> bool:
        """Dispatch alert for the given anomaly. Returns True on success."""


class WebhookRouter(AlertRouter):
    """POST JSON payload to a webhook URL with optional HMAC-SHA256 signature.

    Retries up to 3 times on 429/502/503 with exponential backoff (capped at 30s).
    Respects Retry-After header for 429 responses.
    """

    _MAX_RETRIES: int = 3
    _RETRIABLE_STATUSES: frozenset[int] = frozenset({429, 502, 503})
    _MAX_BACKOFF: float = 30.0

    def __init__(self, url: str, secret: str = "") -> None:
        self._url = url
        self._secret = secret

    async def send(self, anomaly: Anomaly, tenant_id: str) -> bool:
        payload = {
            "tenant_id": tenant_id,
            "satellite_id": anomaly.satellite_id,
            "parameter": anomaly.parameter,
            "subsystem": anomaly.subsystem,
            "severity": anomaly.severity.value,
            "confidence": anomaly.confidence,
            "timestamp": anomaly.timestamp.isoformat(),
            "explanation": anomaly.explanation,
            "detectors": list(anomaly.detectors_triggered),
        }
        body = json.dumps(payload).encode()

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._secret:
            sig = hmac.new(
                self._secret.encode(), body, hashlib.sha256
            ).hexdigest()
            headers["X-Dsremo-Signature"] = f"sha256={sig}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for attempt in range(self._MAX_RETRIES + 1):
                    resp = await client.post(self._url, content=body, headers=headers)

                    if resp.status_code < 400:
                        return True

                    if resp.status_code not in self._RETRIABLE_STATUSES:
                        logger.warning(
                            "webhook_failed",
                            tenant_id=tenant_id,
                            status=resp.status_code,
                            url=self._url,
                        )
                        return False

                    if attempt >= self._MAX_RETRIES:
                        break

                    # Compute backoff: Retry-After for 429, exponential for 502/503
                    if resp.status_code == 429:
                        wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                    else:
                        wait = min(2 ** attempt, self._MAX_BACKOFF)

                    logger.info(
                        "webhook_retry",
                        tenant_id=tenant_id,
                        attempt=attempt + 1,
                        status=resp.status_code,
                        wait_s=wait,
                        url=self._url,
                    )
                    await asyncio.sleep(wait)

                # All retries exhausted
                logger.warning(
                    "webhook_failed",
                    tenant_id=tenant_id,
                    status=resp.status_code,
                    url=self._url,
                    retries_exhausted=True,
                )
                return False
        except (httpx.TransportError, httpx.HTTPError) as exc:
            logger.error("webhook_error", tenant_id=tenant_id, error=str(exc))
            return False


class EmailRouter(AlertRouter):
    """Send alert via SMTP.

    Uses asyncio.run_in_executor so the blocking smtplib call doesn't block
    the event loop. No new dependency — smtplib is stdlib.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        to: list[str],
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._to = to

    def _send_sync(self, subject: str, body: str) -> None:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self._user
        msg["To"] = ", ".join(self._to)

        with smtplib.SMTP(self._host, self._port) as server:
            server.ehlo()
            server.starttls()
            if self._user and self._password:
                server.login(self._user, self._password)
            server.sendmail(self._user, self._to, msg.as_string())

    async def send(self, anomaly: Anomaly, tenant_id: str) -> bool:
        subject = (
            f"[Dsremo {get_severity_label(anomaly.severity.value)}] "
            f"{anomaly.satellite_id} — {anomaly.parameter}"
        )
        body = (
            f"Satellite:  {anomaly.satellite_id}\n"
            f"Parameter:  {anomaly.parameter} ({anomaly.subsystem})\n"
            f"Severity:   {anomaly.severity.value}\n"
            f"Confidence: {anomaly.confidence:.1%}\n"
            f"Timestamp:  {anomaly.timestamp.isoformat()}\n\n"
            f"{anomaly.explanation}\n\n"
            f"Detectors: {', '.join(anomaly.detectors_triggered)}"
        )
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_sync, subject, body)
            return True
        except smtplib.SMTPException as exc:
            logger.error(
                "email_error", tenant_id=tenant_id, error=str(exc), to=self._to
            )
            return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _build_routers(config: dict) -> list[AlertRouter]:
    """Build the list of active delivery routers from a tenant config dict.

    Returns an empty list when enabled=False so dispatch is a no-op.
    """
    if not config.get("enabled", True):
        return []

    routers: list[AlertRouter] = []

    if config.get("webhook_url"):
        routers.append(WebhookRouter(
            url=config["webhook_url"],
            secret=config.get("webhook_secret") or "",
        ))

    if config.get("email_to") and config.get("smtp_host"):
        routers.append(EmailRouter(
            host=config["smtp_host"],
            port=int(config.get("smtp_port") or 587),
            user=config.get("smtp_user") or "",
            password=config.get("smtp_password") or "",
            to=list(config["email_to"]),
        ))

    return routers


# ---------------------------------------------------------------------------
# AlertService — class-level state (no singleton, no init function)
# ---------------------------------------------------------------------------

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.NOMINAL: 0,
    Severity.WATCH: 1,
    Severity.WARNING: 2,
    Severity.CRITICAL: 3,
}


class AlertService:
    """Class-level alert dispatch with per-tenant configuration.

    All state is stored at the class level so the service is available
    everywhere without passing an instance around.  load_configs() is called
    at startup (and after each PUT /alerts/config) to hot-reload settings.
    """

    # Per-tenant config rows keyed by tenant_id
    _config_cache: ClassVar[dict[str, dict]] = {}
    # Dedup: f"{tenant_id}::{satellite_id}::{parameter}" → last_sent monotonic time
    _dedup: ClassVar[dict[str, float]] = {}
    # Escalation: same key → (first_alert time, severity at first alert)
    _escalation: ClassVar[dict[str, tuple[float, Severity]]] = {}

    @classmethod
    def load_configs(cls, configs: list[dict]) -> None:
        """Populate the class-level config cache from DB rows.

        Safe to call multiple times — replaces the cache atomically.
        Called at startup and after PUT /alerts/config.
        """
        cls._config_cache = {c["tenant_id"]: c for c in configs}
        logger.info("alert_configs_loaded", count=len(cls._config_cache))

    @classmethod
    def update_config(cls, tenant_id: str, config: dict) -> None:
        """Hot-reload a single tenant's config after PUT /alerts/config."""
        cls._config_cache[tenant_id] = config

    @classmethod
    def remove_config(cls, tenant_id: str) -> None:
        """Remove a tenant's config after DELETE /alerts/config."""
        cls._config_cache.pop(tenant_id, None)

    @classmethod
    async def dispatch(cls, anomaly: Anomaly, tenant_id: str) -> bool:
        """Dispatch an anomaly alert for the given tenant.

        Steps:
        1. Validate severity against per-tenant min_severity.
        2. Check dedup window — suppress if recently alerted.
        3. Persist to DB via insert_alert() (even if routers fail).
        4. Dispatch all routers concurrently via asyncio.gather().
        5. Update dedup + escalation state.

        Returns True if alert was dispatched, False if suppressed.
        """
        config = cls._config_cache.get(tenant_id)
        if not config:
            return False

        if not config.get("enabled", True):
            return False

        # Severity filter
        min_sev = config.get("min_severity", "warning")
        if _SEVERITY_RANK.get(anomaly.severity, 0) < _SEVERITY_RANK.get(
            Severity(min_sev), 2
        ):
            return False

        # Dedup check
        key = f"{tenant_id}::{anomaly.satellite_id}::{anomaly.parameter}"
        now = time.monotonic()
        dedup_window = float(config.get("dedup_window_s", 300))
        last_sent = cls._dedup.get(key, 0)
        if now - last_sent < dedup_window:
            # Only suppress if severity hasn't increased
            prev_sev = cls._escalation.get(key, (0, Severity.NOMINAL))[1]
            if _SEVERITY_RANK.get(anomaly.severity, 0) <= _SEVERITY_RANK.get(prev_sev, 0):
                return False

        # Persist first — ensures history exists even if delivery fails
        try:
            from aria.dsremo.db import queries  # local import avoids circular at module level
            await queries.insert_alert(anomaly)
        except Exception as exc:
            logger.error("insert_alert_failed", tenant_id=tenant_id, error=str(exc))

        # Build and dispatch routers concurrently
        routers = _build_routers(config)
        any_succeeded = False
        if routers:
            results = await asyncio.gather(
                *[r.send(anomaly, tenant_id) for r in routers],
                return_exceptions=True,
            )
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    logger.error(
                        "router_exception",
                        router=type(routers[i]).__name__,
                        error=str(res),
                    )
                elif res is True:
                    any_succeeded = True

        # Dead-letter queue: capture alerts where all routers failed
        if routers and not any_succeeded:
            if len(_dead_letters) < _MAX_DEAD_LETTERS:
                _dead_letters.append({
                    "tenant_id": tenant_id,
                    "satellite_id": anomaly.satellite_id,
                    "parameter": anomaly.parameter,
                    "severity": anomaly.severity.value,
                    "timestamp": anomaly.timestamp.isoformat(),
                    "explanation": anomaly.explanation,
                    "failed_at": time.time(),
                })
                logger.warning(
                    "alert_dead_lettered",
                    tenant_id=tenant_id,
                    satellite_id=anomaly.satellite_id,
                    parameter=anomaly.parameter,
                    queue_size=len(_dead_letters),
                )

        # Update dedup + escalation state
        cls._dedup[key] = now
        if key not in cls._escalation:
            cls._escalation[key] = (now, anomaly.severity)
        else:
            cls._escalation[key] = (cls._escalation[key][0], anomaly.severity)

        logger.info(
            "alert_dispatched",
            tenant_id=tenant_id,
            satellite_id=anomaly.satellite_id,
            parameter=anomaly.parameter,
            severity=anomaly.severity.value,
            routers=len(routers),
        )
        return True

    @classmethod
    async def check_escalations(cls) -> int:
        """Auto-escalate anomalies that have persisted past escalation_delay_s.

        Called by a background task every 60 seconds.
        Returns count of escalations dispatched.
        """
        now = time.monotonic()
        count = 0

        for key, (started, severity) in list(cls._escalation.items()):
            parts = key.split("::", 2)
            if len(parts) < 3:
                continue
            tenant_id, satellite_id, parameter = parts

            config = cls._config_cache.get(tenant_id)
            if not config:
                continue

            delay = float(config.get("escalation_delay_s", 600))
            if now - started < delay:
                continue
            if severity == Severity.CRITICAL:
                continue  # already at max

            # Build an escalation anomaly with elevated severity
            from aria.dsremo.core.models import Anomaly as _Anomaly  # avoid circular
            escalation = _Anomaly(
                satellite_id=satellite_id,
                parameter=parameter,
                subsystem="unknown",
                severity=Severity.CRITICAL,
                confidence=1.0,
                explanation=(
                    f"Anomaly on {parameter} has persisted for "
                    f"{int(now - started)}s without resolution. "
                    f"Auto-escalated to CRITICAL."
                ),
            )

            # Temporarily remove dedup to force dispatch
            dedup_key = key
            saved_dedup = cls._dedup.pop(dedup_key, None)
            await cls.dispatch(escalation, tenant_id)
            if saved_dedup is not None:
                cls._dedup[dedup_key] = saved_dedup

            cls._escalation[key] = (started, Severity.CRITICAL)
            count += 1

        return count

    @classmethod
    def clear_resolved(cls, tenant_id: str, satellite_id: str, parameter: str) -> None:
        """Mark an anomaly as resolved — clears dedup and escalation state."""
        key = f"{tenant_id}::{satellite_id}::{parameter}"
        cls._dedup.pop(key, None)
        cls._escalation.pop(key, None)


# ---------------------------------------------------------------------------
# Dead-letter queue accessors
# ---------------------------------------------------------------------------

def get_dead_letters() -> list[dict]:
    """Return dead-letter queue entries."""
    return list(_dead_letters)


def clear_dead_letters() -> int:
    """Clear dead-letter queue. Returns count cleared."""
    n = len(_dead_letters)
    _dead_letters.clear()
    return n
