"""ARIA Mission Report Generator — comprehensive post-mission reporting.

Produces structured text, JSON, and HTML reports from completed mission data.
Accepts MissionResults (required), DashboardSnapshot (optional), and
interstellar challenge states (optional).

Usage:
    from aria.reporting import MissionReportGenerator

    gen = MissionReportGenerator(results, dashboard=snapshot, challenge_summary=challenges)
    text = gen.generate_text()
    data = gen.generate_json()
    html = gen.generate_html()
    score = gen.compute_score()
"""

from __future__ import annotations

import html as html_mod
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from aria.dashboard.health_dashboard import DashboardSnapshot
from aria.simulation.mission_runner import MissionResults


class ReportFormat(Enum):
    """Supported report output formats."""
    TEXT = "text"
    JSON = "json"
    HTML = "html"


# ────────────────────────────────────────────────────────────────────
#  Mission Score
# ────────────────────────────────────────────────────────────────────

@dataclass
class MissionScore:
    """Composite mission score (0-100) broken into weighted components."""
    total: float = 0.0

    # Sub-scores (0-100 each)
    completion: float = 0.0       # Mission completed without fatal errors
    alert_health: float = 0.0     # Inverse of alert density
    system_health: float = 0.0    # Based on dashboard overall status
    challenge_survival: float = 0.0  # Interstellar challenges survived
    physics_compliance: float = 0.0  # Orbital mechanics validation

    # Weights (must sum to 1.0)
    weights: dict[str, float] = field(default_factory=lambda: {
        "completion": 0.30,
        "alert_health": 0.25,
        "system_health": 0.20,
        "challenge_survival": 0.15,
        "physics_compliance": 0.10,
    })

    def compute_total(self) -> float:
        w = self.weights
        self.total = (
            self.completion * w["completion"]
            + self.alert_health * w["alert_health"]
            + self.system_health * w["system_health"]
            + self.challenge_survival * w["challenge_survival"]
            + self.physics_compliance * w["physics_compliance"]
        )
        self.total = round(max(0.0, min(100.0, self.total)), 1)
        return self.total

    def grade(self) -> str:
        if self.total >= 90:
            return "A"
        if self.total >= 80:
            return "B"
        if self.total >= 70:
            return "C"
        if self.total >= 60:
            return "D"
        return "F"


# ────────────────────────────────────────────────────────────────────
#  Recommendations Engine
# ────────────────────────────────────────────────────────────────────

_STATUS_SEVERITY_ORDER = {
    "NOMINAL": 0,
    "CAUTION": 1,
    "WARNING": 2,
    "CRITICAL": 3,
    "EMERGENCY": 4,
}


def _generate_recommendations(
    results: MissionResults,
    dashboard: DashboardSnapshot | None,
    score: MissionScore,
) -> list[str]:
    """Generate actionable recommendations based on mission data."""
    recs: list[str] = []

    # Alert-rate based
    if results.total_frames > 0:
        alert_rate = results.total_alerts / max(results.total_frames, 1)
        if alert_rate > 0.5:
            recs.append(
                "HIGH ALERT DENSITY: Alert-to-frame ratio is "
                f"{alert_rate:.2f}. Review alert thresholds for possible "
                "false-positive tuning."
            )

    # Severity distribution
    sev = results.severity_distribution
    if sev.get("EMERGENCY", 0) > 0:
        recs.append(
            f"EMERGENCY EVENTS: {sev['EMERGENCY']} emergency-level events "
            "occurred. Conduct root-cause analysis on each."
        )
    if sev.get("CRITICAL", 0) > 5:
        recs.append(
            f"RECURRING CRITICAL: {sev['CRITICAL']} critical events. "
            "Investigate systemic failure pattern."
        )

    # Power
    if dashboard:
        if dashboard.battery_soc_pct < 20:
            recs.append(
                f"LOW BATTERY: Final SoC {dashboard.battery_soc_pct:.1f}%. "
                "Review power budget and eclipse duty cycles."
            )
        if dashboard.solar_power_w < 100 and not dashboard.in_eclipse:
            recs.append(
                "LOW SOLAR POWER: Solar generation below 100W outside eclipse. "
                "Check panel degradation or attitude."
            )

    # Challenges
    terminal = results.terminal_challenges
    if terminal > 0:
        recs.append(
            f"TERMINAL CHALLENGES: {terminal}/6 interstellar challenges "
            "reached terminal state. Mission sustainability compromised."
        )
    if terminal >= 3:
        recs.append(
            "MISSION VIABILITY: Majority of challenges terminal. "
            "Recommend mission architecture redesign."
        )

    # Score-driven
    if score.total < 50:
        recs.append(
            f"OVERALL SCORE {score.total:.0f}/100: Mission scored below "
            "acceptable threshold. Full design review recommended."
        )
    elif score.total < 70:
        recs.append(
            f"MARGINAL SCORE {score.total:.0f}/100: Mission marginally "
            "acceptable. Address top-severity alerts before next run."
        )

    # Errors
    if results.errors:
        recs.append(
            f"RUNTIME ERRORS: {len(results.errors)} error(s) encountered. "
            "Fix before production runs."
        )

    if not recs:
        recs.append("No critical recommendations. Mission performed within nominal parameters.")

    return recs


# ────────────────────────────────────────────────────────────────────
#  Physics Validation
# ────────────────────────────────────────────────────────────────────

_MU_EARTH = 3.986004418e14  # m^3/s^2
_R_EARTH = 6371.0  # km


def _validate_physics(results: MissionResults) -> list[dict[str, Any]]:
    """Validate orbital parameters against Kepler/Newton laws."""
    checks: list[dict[str, Any]] = []

    alt_lo, alt_hi = results.altitude_range_km
    vel_lo, vel_hi = results.velocity_range_m_s

    if alt_hi <= 0 or vel_hi <= 0:
        checks.append({
            "check": "data_present",
            "passed": False,
            "detail": "No orbital data available for physics validation.",
        })
        return checks

    # Kepler velocity check: v = sqrt(mu / r) for circular orbit
    for label, alt, vel in [("periapsis", alt_lo, vel_hi), ("apoapsis", alt_hi, vel_lo)]:
        r_m = (alt + _R_EARTH) * 1000.0
        v_kepler = math.sqrt(_MU_EARTH / r_m)
        deviation_pct = abs(vel - v_kepler) / v_kepler * 100 if v_kepler > 0 else 0
        passed = deviation_pct < 5.0  # 5% tolerance for non-circular orbits
        checks.append({
            "check": f"kepler_velocity_{label}",
            "passed": passed,
            "expected_m_s": round(v_kepler, 1),
            "actual_m_s": round(vel, 1),
            "deviation_pct": round(deviation_pct, 2),
        })

    # Orbital period estimate (vis-viva for circular at mean altitude)
    mean_alt = (alt_lo + alt_hi) / 2
    r_m = (mean_alt + _R_EARTH) * 1000.0
    period_s = 2 * math.pi * math.sqrt(r_m ** 3 / _MU_EARTH)
    checks.append({
        "check": "estimated_orbital_period",
        "passed": True,
        "period_s": round(period_s, 1),
        "period_min": round(period_s / 60, 1),
    })

    # Energy conservation: check altitude range is reasonable for near-circular
    alt_spread_km = alt_hi - alt_lo
    eccentricity_est = alt_spread_km / (2 * (mean_alt + _R_EARTH))
    checks.append({
        "check": "eccentricity_estimate",
        "passed": eccentricity_est < 0.1,
        "eccentricity": round(eccentricity_est, 6),
        "altitude_spread_km": round(alt_spread_km, 2),
    })

    return checks


# ────────────────────────────────────────────────────────────────────
#  Report Generator
# ────────────────────────────────────────────────────────────────────

class MissionReportGenerator:
    """Generates comprehensive post-mission reports.

    Args:
        results: MissionResults from a completed MissionRunner.run()
        dashboard: Optional final DashboardSnapshot for system state details.
        challenge_summary: Optional dict from InterstellarChallengeOrchestrator.get_summary().
        alerts: Optional list of alert dicts (topic, severity, message).
        generated_at: Optional override for report timestamp (ISO format).
    """

    def __init__(
        self,
        results: MissionResults,
        *,
        dashboard: DashboardSnapshot | None = None,
        challenge_summary: dict[str, dict[str, Any]] | None = None,
        alerts: list[dict[str, Any]] | None = None,
        generated_at: str | None = None,
    ) -> None:
        self._results = results
        self._dashboard = dashboard
        self._challenge_summary = challenge_summary or {}
        self._alerts = alerts or []
        self._generated_at = generated_at or datetime.now(timezone.utc).isoformat()

        # Compute score once — reused across all formats
        self._score = self.compute_score()
        self._physics = _validate_physics(results)
        self._recommendations = _generate_recommendations(results, dashboard, self._score)

    # ── Public API ──────────────────────────────────────────────────

    def compute_score(self) -> MissionScore:
        """Calculate composite mission score (0-100)."""
        r = self._results
        d = self._dashboard
        score = MissionScore()

        # 1. Completion (30%)
        score.completion = 100.0 if r.success else max(0.0, 50.0 - len(r.errors) * 10)

        # 2. Alert health (25%) — fewer alerts per frame = better
        if r.total_frames > 0:
            alert_ratio = r.total_alerts / r.total_frames
            # ratio 0 → 100, ratio >= 1 → 0
            score.alert_health = max(0.0, 100.0 * (1.0 - min(alert_ratio, 1.0)))
        else:
            score.alert_health = 100.0 if r.total_alerts == 0 else 0.0

        # 3. System health (20%) — based on dashboard status
        if d:
            status_scores = {
                "NOMINAL": 100.0,
                "CAUTION": 80.0,
                "WARNING": 60.0,
                "CRITICAL": 30.0,
                "EMERGENCY": 0.0,
            }
            score.system_health = status_scores.get(d.overall_status, 50.0)
        else:
            # No dashboard: infer from results
            score.system_health = 80.0 if r.success else 40.0

        # 4. Challenge survival (15%)
        if r.challenge_states:
            total_challenges = len(r.challenge_states)
            terminal = r.terminal_challenges
            survived = total_challenges - terminal
            score.challenge_survival = (survived / total_challenges) * 100.0 if total_challenges > 0 else 100.0
        else:
            score.challenge_survival = 100.0  # N/A = full marks

        # 5. Physics compliance (10%)
        physics = _validate_physics(r)
        if physics:
            passed = sum(1 for c in physics if c.get("passed", False))
            score.physics_compliance = (passed / len(physics)) * 100.0
        else:
            score.physics_compliance = 100.0

        score.compute_total()
        return score

    def generate_text(self) -> str:
        """Generate a structured plain-text mission report."""
        r = self._results
        d = self._dashboard
        s = self._score
        lines: list[str] = []

        def section(title: str) -> None:
            lines.append("")
            lines.append(f"{'=' * 72}")
            lines.append(f"  {title}")
            lines.append(f"{'=' * 72}")

        def kv(key: str, value: Any, indent: int = 2) -> None:
            lines.append(f"{' ' * indent}{key}: {value}")

        # Header
        lines.append("ARIA MISSION REPORT")
        lines.append(f"Generated: {self._generated_at}")
        lines.append(f"Score: {s.total:.1f}/100 (Grade: {s.grade()})")

        # 1. Mission Summary
        section("MISSION SUMMARY")
        kv("Name", r.mission_name)
        kv("Type", r.mission_type)
        kv("Status", "SUCCESS" if r.success else "FAILED")
        kv("Sim Duration", f"{r.duration_sim_s:.1f} s")
        kv("Wall Duration", f"{r.duration_wall_s:.2f} s")
        kv("Total Frames", r.total_frames)
        kv("Total Events", r.total_events)
        kv("Total Alerts", r.total_alerts)
        if r.errors:
            kv("Errors", len(r.errors))
            for e in r.errors:
                lines.append(f"    - {e}")

        # 2. Orbital Parameters
        section("ORBITAL PARAMETERS")
        kv("Altitude Range", f"{r.altitude_range_km[0]:.1f} - {r.altitude_range_km[1]:.1f} km")
        kv("Velocity Range", f"{r.velocity_range_m_s[0]:.0f} - {r.velocity_range_m_s[1]:.0f} m/s")
        kv("Latitude Range", f"{r.latitude_range_deg[0]:.1f} to {r.latitude_range_deg[1]:.1f} deg")
        kv("Eclipse Count", r.eclipse_count)
        if d:
            kv("Final Altitude", f"{d.altitude_km:.1f} km")
            kv("In Eclipse", d.in_eclipse)

        # 3. Power System
        section("POWER SYSTEM")
        if d:
            kv("Battery SoC", f"{d.battery_soc_pct:.1f}%")
            kv("Solar Power", f"{d.solar_power_w:.1f} W")
            kv("Total Load", f"{d.total_load_w:.1f} W")
            kv("Bus Voltage", f"{d.bus_voltage_v:.1f} V")
        else:
            kv("Data", "No dashboard snapshot available")

        # 4. Alert Summary
        section("ALERT SUMMARY")
        kv("Total Alerts", r.total_alerts)
        if r.severity_distribution:
            kv("Severity Distribution", "")
            for sev, count in sorted(r.severity_distribution.items()):
                lines.append(f"      {sev}: {count}")
        if self._alerts:
            top_n = min(10, len(self._alerts))
            kv(f"Top {top_n} Alerts", "")
            for alert in self._alerts[:top_n]:
                sev = alert.get("severity", "?")
                msg = alert.get("message", alert.get("topic", ""))
                lines.append(f"      [{sev}] {msg}")

        # 5. Agent Performance
        section("AGENT PERFORMANCE")
        kv("Messages Processed", r.agent_messages_processed)
        kv("Anomalies Detected", r.anomalies_detected)
        if d:
            kv("Agents Total", d.agent_count)
            kv("Agents Healthy", d.agents_healthy)
            kv("Bus Messages Total", d.bus_messages_total)
            if d.subsystems:
                kv("Subsystem Status", "")
                for name, ss in sorted(d.subsystems.items()):
                    lines.append(f"      {name}: {ss.status} (alerts={ss.active_alerts}, dsremo={ss.dsremo_score:.3f})")

        # 6. Challenge Status
        section("CHALLENGE STATUS (INTERSTELLAR)")
        if r.challenge_states:
            kv("Terminal Challenges", f"{r.terminal_challenges}/6")
            for name, status in sorted(r.challenge_states.items()):
                detail = ""
                if name in self._challenge_summary:
                    cs = self._challenge_summary[name]
                    detail = f" (severity={cs.get('severity', '?'):.2f})"
                lines.append(f"      {name}: {status}{detail}")
        else:
            kv("Status", "N/A (non-interstellar mission)")

        # 7. Physics Validation
        section("PHYSICS VALIDATION")
        for check in self._physics:
            passed = "PASS" if check.get("passed") else "FAIL"
            name = check["check"]
            detail_parts = [f"{k}={v}" for k, v in check.items() if k not in ("check", "passed")]
            detail_str = ", ".join(detail_parts)
            lines.append(f"    [{passed}] {name}: {detail_str}")

        # 8. Recommendations
        section("RECOMMENDATIONS")
        for i, rec in enumerate(self._recommendations, 1):
            lines.append(f"    {i}. {rec}")

        # Score breakdown
        section("SCORE BREAKDOWN")
        kv("Completion", f"{s.completion:.1f}/100 (weight {s.weights['completion']:.0%})")
        kv("Alert Health", f"{s.alert_health:.1f}/100 (weight {s.weights['alert_health']:.0%})")
        kv("System Health", f"{s.system_health:.1f}/100 (weight {s.weights['system_health']:.0%})")
        kv("Challenge Survival", f"{s.challenge_survival:.1f}/100 (weight {s.weights['challenge_survival']:.0%})")
        kv("Physics Compliance", f"{s.physics_compliance:.1f}/100 (weight {s.weights['physics_compliance']:.0%})")
        kv("TOTAL", f"{s.total:.1f}/100 (Grade: {s.grade()})")

        lines.append("")
        lines.append(f"{'=' * 72}")
        lines.append("END OF REPORT")
        lines.append(f"{'=' * 72}")
        return "\n".join(lines)

    def generate_json(self) -> dict[str, Any]:
        """Generate a machine-consumable JSON report."""
        r = self._results
        d = self._dashboard
        s = self._score

        report: dict[str, Any] = {
            "meta": {
                "generated_at": self._generated_at,
                "format_version": "1.0",
                "generator": "aria.reporting.mission_report",
            },
            "score": {
                "total": s.total,
                "grade": s.grade(),
                "completion": s.completion,
                "alert_health": s.alert_health,
                "system_health": s.system_health,
                "challenge_survival": s.challenge_survival,
                "physics_compliance": s.physics_compliance,
                "weights": s.weights,
            },
            "mission_summary": {
                "name": r.mission_name,
                "type": r.mission_type,
                "success": r.success,
                "duration_sim_s": r.duration_sim_s,
                "duration_wall_s": r.duration_wall_s,
                "total_frames": r.total_frames,
                "total_events": r.total_events,
                "total_alerts": r.total_alerts,
                "errors": r.errors,
            },
            "orbital_parameters": {
                "altitude_range_km": list(r.altitude_range_km),
                "velocity_range_m_s": list(r.velocity_range_m_s),
                "latitude_range_deg": list(r.latitude_range_deg),
                "eclipse_count": r.eclipse_count,
            },
            "power_system": None,
            "alert_summary": {
                "total": r.total_alerts,
                "severity_distribution": r.severity_distribution,
                "top_alerts": self._alerts[:10],
            },
            "agent_performance": {
                "messages_processed": r.agent_messages_processed,
                "anomalies_detected": r.anomalies_detected,
            },
            "challenge_status": {
                "states": r.challenge_states,
                "terminal_count": r.terminal_challenges,
                "details": self._challenge_summary,
            },
            "physics_validation": self._physics,
            "recommendations": self._recommendations,
        }

        if d:
            report["power_system"] = {
                "battery_soc_pct": d.battery_soc_pct,
                "solar_power_w": d.solar_power_w,
                "total_load_w": d.total_load_w,
                "bus_voltage_v": d.bus_voltage_v,
            }
            report["agent_performance"]["agent_count"] = d.agent_count
            report["agent_performance"]["agents_healthy"] = d.agents_healthy
            report["agent_performance"]["bus_messages_total"] = d.bus_messages_total
            report["orbital_parameters"]["final_altitude_km"] = d.altitude_km
            report["orbital_parameters"]["in_eclipse"] = d.in_eclipse

        return report

    def generate_json_string(self) -> str:
        """Generate JSON report as a formatted string."""
        return json.dumps(self.generate_json(), indent=2, default=str)

    def generate_html(self) -> str:
        """Generate a self-contained HTML mission report."""
        r = self._results
        d = self._dashboard
        s = self._score
        esc = html_mod.escape

        grade_colors = {"A": "#22c55e", "B": "#84cc16", "C": "#eab308", "D": "#f97316", "F": "#ef4444"}
        grade_color = grade_colors.get(s.grade(), "#6b7280")
        status_str = "SUCCESS" if r.success else "FAILED"
        status_color = "#22c55e" if r.success else "#ef4444"

        # Build sections
        html_parts: list[str] = []
        html_parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ARIA Mission Report - {esc(r.mission_name)}</title>
<style>
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 20px; background: #0f172a; color: #e2e8f0; }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ color: #38bdf8; border-bottom: 2px solid #1e40af; padding-bottom: 10px; }}
  h2 {{ color: #7dd3fc; margin-top: 30px; border-bottom: 1px solid #1e3a5f; padding-bottom: 5px; }}
  .score-badge {{ display: inline-block; background: {grade_color}; color: #000; font-size: 24px; font-weight: bold; padding: 8px 20px; border-radius: 8px; }}
  .status {{ display: inline-block; background: {status_color}; color: #fff; padding: 4px 12px; border-radius: 4px; font-weight: bold; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #1e3a5f; }}
  th {{ background: #1e293b; color: #94a3b8; font-weight: 600; }}
  tr:hover {{ background: #1e293b; }}
  .pass {{ color: #22c55e; font-weight: bold; }}
  .fail {{ color: #ef4444; font-weight: bold; }}
  .rec {{ background: #1e293b; padding: 10px 15px; margin: 5px 0; border-left: 3px solid #f59e0b; border-radius: 4px; }}
  .meta {{ color: #64748b; font-size: 14px; }}
  .bar {{ height: 12px; border-radius: 6px; background: #1e3a5f; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 6px; }}
</style>
</head>
<body>
<div class="container">
<h1>ARIA Mission Report</h1>
<p class="meta">Generated: {esc(self._generated_at)}</p>
<p><span class="score-badge">{s.total:.0f}/100 ({s.grade()})</span>
   <span class="status">{esc(status_str)}</span></p>
""")

        # Mission Summary
        html_parts.append(f"""<h2>Mission Summary</h2>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Name</td><td>{esc(r.mission_name)}</td></tr>
<tr><td>Type</td><td>{esc(r.mission_type)}</td></tr>
<tr><td>Sim Duration</td><td>{r.duration_sim_s:.1f} s</td></tr>
<tr><td>Wall Duration</td><td>{r.duration_wall_s:.2f} s</td></tr>
<tr><td>Frames</td><td>{r.total_frames}</td></tr>
<tr><td>Events</td><td>{r.total_events}</td></tr>
<tr><td>Alerts</td><td>{r.total_alerts}</td></tr>
</table>""")

        # Orbital Parameters
        html_parts.append(f"""<h2>Orbital Parameters</h2>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Altitude Range</td><td>{r.altitude_range_km[0]:.1f} - {r.altitude_range_km[1]:.1f} km</td></tr>
<tr><td>Velocity Range</td><td>{r.velocity_range_m_s[0]:.0f} - {r.velocity_range_m_s[1]:.0f} m/s</td></tr>
<tr><td>Latitude Range</td><td>{r.latitude_range_deg[0]:.1f} to {r.latitude_range_deg[1]:.1f} deg</td></tr>
<tr><td>Eclipse Count</td><td>{r.eclipse_count}</td></tr>
</table>""")

        # Power System
        html_parts.append("<h2>Power System</h2>")
        if d:
            soc_color = "#22c55e" if d.battery_soc_pct > 50 else "#eab308" if d.battery_soc_pct > 20 else "#ef4444"
            html_parts.append(f"""<table>
<tr><th>Parameter</th><th>Value</th></tr>
<tr><td>Battery SoC</td><td>
  <div class="bar" style="width:200px;display:inline-block;vertical-align:middle;">
    <div class="bar-fill" style="width:{min(d.battery_soc_pct, 100):.0f}%;background:{soc_color};"></div>
  </div> {d.battery_soc_pct:.1f}%</td></tr>
<tr><td>Solar Power</td><td>{d.solar_power_w:.1f} W</td></tr>
<tr><td>Total Load</td><td>{d.total_load_w:.1f} W</td></tr>
<tr><td>Bus Voltage</td><td>{d.bus_voltage_v:.1f} V</td></tr>
</table>""")
        else:
            html_parts.append("<p>No dashboard snapshot available.</p>")

        # Alert Summary
        html_parts.append("<h2>Alert Summary</h2>")
        if r.severity_distribution:
            html_parts.append("<table><tr><th>Severity</th><th>Count</th></tr>")
            for sev, count in sorted(r.severity_distribution.items()):
                html_parts.append(f"<tr><td>{esc(sev)}</td><td>{count}</td></tr>")
            html_parts.append("</table>")
        if self._alerts:
            html_parts.append("<h3>Top Alerts</h3><table><tr><th>Severity</th><th>Message</th></tr>")
            for alert in self._alerts[:10]:
                sev = esc(str(alert.get("severity", "?")))
                msg = esc(str(alert.get("message", alert.get("topic", ""))))
                html_parts.append(f"<tr><td>{sev}</td><td>{msg}</td></tr>")
            html_parts.append("</table>")

        # Agent Performance
        html_parts.append(f"""<h2>Agent Performance</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Messages Processed</td><td>{r.agent_messages_processed}</td></tr>
<tr><td>Anomalies Detected</td><td>{r.anomalies_detected}</td></tr>""")
        if d:
            html_parts.append(f"""<tr><td>Agents Total</td><td>{d.agent_count}</td></tr>
<tr><td>Agents Healthy</td><td>{d.agents_healthy}</td></tr>""")
        html_parts.append("</table>")

        # Challenges
        html_parts.append("<h2>Challenge Status (Interstellar)</h2>")
        if r.challenge_states:
            html_parts.append(f"<p>Terminal: {r.terminal_challenges}/6</p>")
            html_parts.append("<table><tr><th>Challenge</th><th>Status</th><th>Severity</th></tr>")
            for name, status in sorted(r.challenge_states.items()):
                sev_val = ""
                if name in self._challenge_summary:
                    sev_val = f"{self._challenge_summary[name].get('severity', 0):.2f}"
                css = "fail" if status == "terminal" else "pass" if status == "nominal" else ""
                html_parts.append(
                    f'<tr><td>{esc(name)}</td><td class="{css}">{esc(status)}</td><td>{sev_val}</td></tr>'
                )
            html_parts.append("</table>")
        else:
            html_parts.append("<p>N/A (non-interstellar mission)</p>")

        # Physics Validation
        html_parts.append("<h2>Physics Validation</h2>")
        html_parts.append("<table><tr><th>Check</th><th>Result</th><th>Details</th></tr>")
        for check in self._physics:
            passed = check.get("passed", False)
            css = "pass" if passed else "fail"
            label = "PASS" if passed else "FAIL"
            name = esc(check["check"])
            details = ", ".join(f"{k}={v}" for k, v in check.items() if k not in ("check", "passed"))
            html_parts.append(f'<tr><td>{name}</td><td class="{css}">{label}</td><td>{esc(details)}</td></tr>')
        html_parts.append("</table>")

        # Recommendations
        html_parts.append("<h2>Recommendations</h2>")
        for rec in self._recommendations:
            html_parts.append(f'<div class="rec">{esc(rec)}</div>')

        # Score Breakdown
        html_parts.append("<h2>Score Breakdown</h2>")
        html_parts.append("<table><tr><th>Component</th><th>Score</th><th>Weight</th><th>Contribution</th></tr>")
        components = [
            ("Completion", s.completion, s.weights["completion"]),
            ("Alert Health", s.alert_health, s.weights["alert_health"]),
            ("System Health", s.system_health, s.weights["system_health"]),
            ("Challenge Survival", s.challenge_survival, s.weights["challenge_survival"]),
            ("Physics Compliance", s.physics_compliance, s.weights["physics_compliance"]),
        ]
        for name, score_val, weight in components:
            contribution = score_val * weight
            html_parts.append(
                f"<tr><td>{name}</td><td>{score_val:.1f}</td>"
                f"<td>{weight:.0%}</td><td>{contribution:.1f}</td></tr>"
            )
        html_parts.append(f"<tr><th>Total</th><th>{s.total:.1f}</th><th>100%</th><th>{s.total:.1f}</th></tr>")
        html_parts.append("</table>")

        # Footer
        html_parts.append("""
</div>
</body>
</html>""")

        return "\n".join(html_parts)

    def generate(self, fmt: ReportFormat = ReportFormat.TEXT) -> str:
        """Generate report in the requested format."""
        if fmt == ReportFormat.TEXT:
            return self.generate_text()
        elif fmt == ReportFormat.JSON:
            return self.generate_json_string()
        elif fmt == ReportFormat.HTML:
            return self.generate_html()
        else:
            raise ValueError(f"Unsupported format: {fmt}")
