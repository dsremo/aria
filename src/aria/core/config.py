"""ARIA configuration system — YAML-based with schema validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class DsremoConfig:
    """Configuration for Dsremo integration."""

    base_url: str = "http://localhost:8000"
    api_version: str = "v1"
    websocket_url: str = "ws://localhost:8000/api/v1/ws/live"
    api_key: str = ""
    timeout_ms: int = 5000
    severity_thresholds: dict[str, float] = field(
        default_factory=lambda: {"watch": 0.50, "warning": 0.65, "critical": 0.85}
    )


@dataclass
class ConjunctionWatchConfig:
    """Configuration for ConjunctionWatch integration."""

    screening_interval_s: int = 3600
    pc_threshold: float = 1e-4
    tle_max_age_days: float = 3.0
    spacetrack_identity: str = ""
    spacetrack_password: str = ""


@dataclass
class GenAstraConfig:
    """Configuration for GenAstra integration."""

    base_url: str = "http://localhost:8001"
    api_version: str = "v1"
    radiation_update_interval_s: int = 86400  # daily
    timeout_ms: int = 30000


@dataclass
class BusConfig:
    """Message bus configuration."""

    max_history: int = 10_000
    p0_timeout_ms: float = 50
    p1_timeout_ms: float = 1000


@dataclass
class AgentConfig:
    """Per-agent configuration."""

    heartbeat_interval_s: float = 10.0
    max_restart_attempts: int = 3
    restart_backoff_s: float = 5.0


@dataclass
class SafetyConfig:
    """Safety system configuration."""

    checkpoint_interval_s: int = 300
    health_check_interval_s: int = 30


@dataclass
class APIConfig:
    """REST + WebSocket API server configuration."""

    host: str = "127.0.0.1"
    http_port: int = 8080
    ws_port: int = 8081


@dataclass
class AriaConfig:
    """Top-level ARIA configuration."""

    mission_name: str = "ARIA-DEV"
    mission_phase: str = "NOMINAL_LEO"
    authority_level: str = "SUPERVISED"
    dsremo: DsremoConfig = field(default_factory=DsremoConfig)
    conjunction_watch: ConjunctionWatchConfig = field(default_factory=ConjunctionWatchConfig)
    genastra: GenAstraConfig = field(default_factory=GenAstraConfig)
    bus: BusConfig = field(default_factory=BusConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    api: APIConfig = field(default_factory=APIConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> AriaConfig:
        """Load configuration from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        config = cls()
        if "mission_name" in data:
            config.mission_name = data["mission_name"]
        if "mission_phase" in data:
            config.mission_phase = data["mission_phase"]
        if "authority_level" in data:
            config.authority_level = data["authority_level"]

        if "dsremo" in data:
            for k, v in data["dsremo"].items():
                if hasattr(config.dsremo, k):
                    setattr(config.dsremo, k, v)

        if "conjunction_watch" in data:
            for k, v in data["conjunction_watch"].items():
                if hasattr(config.conjunction_watch, k):
                    setattr(config.conjunction_watch, k, v)

        if "genastra" in data:
            for k, v in data["genastra"].items():
                if hasattr(config.genastra, k):
                    setattr(config.genastra, k, v)

        if "safety" in data:
            for k, v in data["safety"].items():
                if hasattr(config.safety, k):
                    setattr(config.safety, k, v)

        if "api" in data:
            for k, v in data["api"].items():
                if hasattr(config.api, k):
                    setattr(config.api, k, v)

        return config
