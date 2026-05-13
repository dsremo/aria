"""V3-F2: Shift handover report generation.

24/7 spacecraft operations require formal shift handover.  At ESA ESOC,
every 8-hour shift ends with: anomaly summary, open action items, subsystem
health summary, upcoming events.

This module auto-generates handover reports from the anomaly/incident database.

Reference: ECSS-E-ST-70-11C §9.2: operational documentation requirements.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


async def generate_handover_report(
    satellite_id: str,
    start: datetime,
    end: datetime,
    queries_module: Any,
) -> dict:
    """Generate a shift handover report for a satellite.

    Args:
        satellite_id: Satellite to report on.
        start: Shift start time.
        end: Shift end time.
        queries_module: The dsremo.db.queries module (passed to avoid circular import).

    Returns:
        Report dict with anomaly summary, incident summary, and health overview.
    """
    # Fetch anomalies in the shift window.
    anomalies = await queries_module.get_anomalies(
        satellite_id=satellite_id,
        after=start,
        before=end,
        limit=500,
    )

    # Fetch incidents.
    incidents = await queries_module.get_incidents_v2(
        satellite_id=satellite_id,
        limit=100,
    )
    shift_incidents = [
        i for i in incidents
        if _in_range(i.get("first_anomaly_at") or i.get("opened_at"), start, end)
    ]

    # Severity breakdown.
    sev_counts: dict[str, int] = {}
    for a in anomalies:
        sev = a.get("severity", "unknown")
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    # False positive rate (if verification data available).
    total = len(anomalies)
    fp_count = sum(
        1 for a in anomalies
        if a.get("verification_status") == "false_positive"
    )
    confirmed = sum(
        1 for a in anomalies
        if a.get("verification_status") == "confirmed"
    )

    # Open (unacknowledged) anomalies.
    open_anomalies = [
        a for a in anomalies
        if a.get("verification_status") in ("suspected", None)
    ]

    # Subsystem health (anomaly count per subsystem).
    subsystem_health: dict[str, int] = {}
    for a in anomalies:
        sub = a.get("subsystem", "unknown")
        subsystem_health[sub] = subsystem_health.get(sub, 0) + 1

    return {
        "satellite_id": satellite_id,
        "shift_start": start.isoformat(),
        "shift_end": end.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_anomalies": total,
            "severity_breakdown": sev_counts,
            "confirmed": confirmed,
            "false_positives": fp_count,
            "open_unacknowledged": len(open_anomalies),
            "incidents": len(shift_incidents),
        },
        "subsystem_health": subsystem_health,
        "open_anomalies": [
            {
                "id": a.get("id"),
                "parameter": a.get("parameter"),
                "severity": a.get("severity"),
                "confidence": a.get("confidence"),
                "timestamp": str(a.get("timestamp")),
            }
            for a in open_anomalies[:20]  # cap for readability
        ],
    }


def _in_range(ts: Any, start: datetime, end: datetime) -> bool:
    if ts is None:
        return False
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return False
    try:
        return start <= ts <= end
    except TypeError:
        return False
