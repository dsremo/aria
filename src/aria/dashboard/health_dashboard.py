"""ARIA Health Dashboard — comprehensive system health aggregation.

Collects health data from all ARIA subsystems into a single dashboard view:
  - Mission state (orbit, phase, elapsed time)
  - Agent health (all 9 agents: status, message count, last heartbeat)
  - Subsystem telemetry (power, thermal, ECLSS, navigation latest values)
  - Anomaly summary (active alerts, severity distribution, Dsremo scores)
  - Challenge status (interstellar only: 6 challenges with severity)
  - System resources (bus queue depth, memory, uptime)

Designed to be consumed by:
  - OpenMCT dashboard (via telemetry server)
  - ARIA API /api/v1/dashboard endpoint
  - CLI monitoring tools
  - Automated health checks
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class SubsystemHealth:
    """Health status of one subsystem."""
    name: str
    status: str = "NOMINAL"  # NOMINAL, WARNING, CRITICAL, OFFLINE
    last_update_s: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    active_alerts: int = 0
    dsremo_score: float = 0.0


@dataclass
class DashboardSnapshot:
    """Complete health snapshot at a point in time."""
    timestamp: float = 0.0
    uptime_s: float = 0.0

    # Mission
    mission_name: str = ""
    mission_phase: str = ""
    mission_elapsed_s: float = 0.0

    # Orbit (if applicable)
    altitude_km: float = 0.0
    velocity_m_s: float = 0.0
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    in_eclipse: bool = False

    # Power
    battery_soc_pct: float = 100.0  # Default = full (safe)
    solar_power_w: float = 0.0
    total_load_w: float = 0.0
    bus_voltage_v: float = 28.0

    # ECLSS
    o2_percent: float = 20.9  # Earth atmosphere
    co2_ppm: float = 400.0
    cabin_pressure_psi: float = 14.7
    cabin_temp_c: float = 22.0

    # Subsystems
    subsystems: dict[str, SubsystemHealth] = field(default_factory=dict)

    # Alerts
    total_alerts: int = 0
    active_critical: int = 0
    active_warnings: int = 0
    severity_distribution: dict[str, int] = field(default_factory=dict)

    # System
    agent_count: int = 0
    agents_healthy: int = 0
    bus_messages_total: int = 0
    dsremo_max_score: float = 0.0

    # Challenges (interstellar)
    challenges: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Overall
    overall_status: str = "NOMINAL"  # NOMINAL, CAUTION, WARNING, CRITICAL, EMERGENCY

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "uptime_s": self.uptime_s,
            "mission": {
                "name": self.mission_name,
                "phase": self.mission_phase,
                "elapsed_s": self.mission_elapsed_s,
            },
            "orbit": {
                "altitude_km": self.altitude_km,
                "velocity_m_s": self.velocity_m_s,
                "latitude_deg": self.latitude_deg,
                "longitude_deg": self.longitude_deg,
                "in_eclipse": self.in_eclipse,
            },
            "power": {
                "battery_soc_pct": self.battery_soc_pct,
                "solar_power_w": self.solar_power_w,
                "total_load_w": self.total_load_w,
                "bus_voltage_v": self.bus_voltage_v,
            },
            "eclss": {
                "o2_percent": self.o2_percent,
                "co2_ppm": self.co2_ppm,
                "cabin_pressure_psi": self.cabin_pressure_psi,
                "cabin_temp_c": self.cabin_temp_c,
            },
            "subsystems": {
                name: {
                    "status": ss.status,
                    "active_alerts": ss.active_alerts,
                    "dsremo_score": ss.dsremo_score,
                    "metrics": ss.metrics,
                }
                for name, ss in self.subsystems.items()
            },
            "alerts": {
                "total": self.total_alerts,
                "active_critical": self.active_critical,
                "active_warnings": self.active_warnings,
                "severity_distribution": self.severity_distribution,
            },
            "system": {
                "agent_count": self.agent_count,
                "agents_healthy": self.agents_healthy,
                "bus_messages_total": self.bus_messages_total,
                "dsremo_max_score": self.dsremo_max_score,
            },
            "challenges": self.challenges,
            "overall_status": self.overall_status,
        }


class HealthDashboard:
    """Aggregates health from all ARIA components.

    Usage:
        dashboard = HealthDashboard()

        # Feed data from various sources
        dashboard.update_orbit(altitude_km=400, velocity_m_s=7673, ...)
        dashboard.update_power(battery_soc=80, solar_w=2722, ...)
        dashboard.update_subsystem("power", status="NOMINAL", alerts=0, score=0.1)
        dashboard.record_alert("WARNING", "power")

        # Get snapshot
        snap = dashboard.snapshot()
        print(snap.overall_status)
    """

    def __init__(self, mission_name: str = "ARIA") -> None:
        self._start_time = time.time()
        self._mission_name = mission_name
        self._snap = DashboardSnapshot(mission_name=mission_name)
        self._alert_history: list[dict[str, Any]] = []
        self._severity_counts: dict[str, int] = {
            "WATCH": 0, "WARNING": 0, "CRITICAL": 0, "EMERGENCY": 0,
        }

    def update_orbit(
        self,
        altitude_km: float = 0,
        velocity_m_s: float = 0,
        latitude_deg: float = 0,
        longitude_deg: float = 0,
        in_eclipse: bool = False,
    ) -> None:
        self._snap.altitude_km = altitude_km
        self._snap.velocity_m_s = velocity_m_s
        self._snap.latitude_deg = latitude_deg
        self._snap.longitude_deg = longitude_deg
        self._snap.in_eclipse = in_eclipse

    def update_power(
        self,
        battery_soc: float = 0,
        solar_w: float = 0,
        load_w: float = 0,
        bus_v: float = 28.0,
    ) -> None:
        self._snap.battery_soc_pct = battery_soc
        self._snap.solar_power_w = solar_w
        self._snap.total_load_w = load_w
        self._snap.bus_voltage_v = bus_v

    def update_eclss(
        self,
        o2_pct: float = 20.9,
        co2_ppm: float = 400,
        pressure_psi: float = 14.7,
        temp_c: float = 22.0,
    ) -> None:
        self._snap.o2_percent = o2_pct
        self._snap.co2_ppm = co2_ppm
        self._snap.cabin_pressure_psi = pressure_psi
        self._snap.cabin_temp_c = temp_c

    def update_subsystem(
        self,
        name: str,
        status: str = "NOMINAL",
        alerts: int = 0,
        dsremo_score: float = 0.0,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        self._snap.subsystems[name] = SubsystemHealth(
            name=name,
            status=status,
            last_update_s=time.time(),
            active_alerts=alerts,
            dsremo_score=dsremo_score,
            metrics=metrics or {},
        )

    def update_mission(self, phase: str = "", elapsed_s: float = 0) -> None:
        self._snap.mission_phase = phase
        self._snap.mission_elapsed_s = elapsed_s

    def update_agents(self, total: int = 0, healthy: int = 0) -> None:
        self._snap.agent_count = total
        self._snap.agents_healthy = healthy

    def update_challenges(self, challenges: dict[str, dict[str, Any]]) -> None:
        self._snap.challenges = challenges

    def record_alert(self, severity: str, subsystem: str = "", message: str = "") -> None:
        self._severity_counts[severity] = self._severity_counts.get(severity, 0) + 1
        self._snap.total_alerts += 1
        self._alert_history.append({
            "time": time.time(),
            "severity": severity,
            "subsystem": subsystem,
            "message": message,
        })
        # Keep last 500
        if len(self._alert_history) > 500:
            self._alert_history = self._alert_history[-500:]

    def snapshot(self) -> DashboardSnapshot:
        """Get current health snapshot with overall status computed."""
        snap = self._snap
        snap.timestamp = time.time()
        snap.uptime_s = time.time() - self._start_time
        snap.severity_distribution = dict(self._severity_counts)

        # Compute active critical/warning from subsystems
        snap.active_critical = sum(
            1 for ss in snap.subsystems.values() if ss.status == "CRITICAL"
        )
        snap.active_warnings = sum(
            1 for ss in snap.subsystems.values() if ss.status == "WARNING"
        )

        # Max Dsremo score
        scores = [ss.dsremo_score for ss in snap.subsystems.values()]
        snap.dsremo_max_score = max(scores) if scores else 0.0

        # Compute overall status
        snap.overall_status = self._compute_overall_status(snap)

        return snap

    @staticmethod
    def _compute_overall_status(snap: DashboardSnapshot) -> str:
        """Determine overall system status from all inputs."""
        # Emergency conditions
        if snap.battery_soc_pct < 5:
            return "EMERGENCY"
        if snap.o2_percent < 18:
            return "EMERGENCY"
        if any(ss.status == "CRITICAL" for ss in snap.subsystems.values()):
            if sum(1 for ss in snap.subsystems.values() if ss.status == "CRITICAL") >= 2:
                return "EMERGENCY"

        # Critical conditions
        if snap.battery_soc_pct < 15:
            return "CRITICAL"
        if snap.o2_percent < 19:
            return "CRITICAL"
        if snap.dsremo_max_score > 0.8:
            return "CRITICAL"
        if any(ss.status == "CRITICAL" for ss in snap.subsystems.values()):
            return "CRITICAL"

        # Warning conditions
        if snap.battery_soc_pct < 25:
            return "WARNING"
        if snap.co2_ppm > 5000:
            return "WARNING"
        if snap.dsremo_max_score > 0.5:
            return "WARNING"
        if snap.bus_voltage_v < 25 or snap.bus_voltage_v > 31:
            return "WARNING"
        if any(ss.status == "WARNING" for ss in snap.subsystems.values()):
            return "WARNING"

        # Caution conditions
        if snap.dsremo_max_score > 0.3:
            return "CAUTION"
        if snap.in_eclipse and snap.battery_soc_pct < 60:
            return "CAUTION"

        return "NOMINAL"

    def update_from_basilisk_frame(self, frame: Any) -> None:
        """Update dashboard from a BasiliskRunner TelemetryFrame."""
        self.update_orbit(
            altitude_km=frame.altitude_km,
            velocity_m_s=frame.orbital_velocity_m_s,
            latitude_deg=frame.ground_track_lat_deg,
            longitude_deg=frame.ground_track_lon_deg,
            in_eclipse=frame.in_eclipse,
        )
        self.update_power(
            battery_soc=frame.battery_soc * 100,
            solar_w=frame.solar_power_w,
            load_w=frame.power_draw_w,
        )

    def recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get most recent alerts."""
        return self._alert_history[-limit:]
