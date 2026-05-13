"""Mission-context bridge — proactive conjunction-risk awareness.

Combines two upstream live feeds:

  * `aria.integrations.launch_library` — upcoming launches; each
    launch deposits new objects into orbit at a specific NET time
    and (eventually) at a specific orbital regime, so the screener
    should pre-compute close-approach windows around launch days.

  * `aria.integrations.jpl_sbdb` — asteroid/comet close-approaches;
    NEOs passing inside ~0.05 AU may interact with high-altitude
    spacecraft trajectories, particularly at L1/L2 / cislunar /
    interplanetary destinations.

Output: a single ranked list of "interesting upcoming events" the
operator console should highlight, with severity scored from a
combination of:

  * Time proximity (sooner = higher score)
  * Orbital-regime overlap with the protected asset (LEO / GEO /
    HEO / cislunar / interplanetary)
  * Asteroid: closer approach distance + larger H magnitude (proxy
    for size) → higher score
  * Launch: high-density mission profile (Starlink Group, OneWeb)
    populates the LEO regime with many objects → higher score

This module is a *bridge* — it does NOT call into the orbital-
mechanics core or duplicate the screener's geometry. It simply
fuses the two upstream feeds into a structured priority queue the
operator can drill into.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import structlog

from aria.integrations.jpl_sbdb import (
    CloseApproach,
    JplSbdbClient,
    get_jpl_sbdb_client,
)
from aria.integrations.launch_library import (
    LaunchLibraryClient,
    UpcomingLaunch,
    get_launch_library_client,
)

logger = structlog.get_logger()


# ── Risk scoring constants ──────────────────────────────────────


# Cited per JPL CNEOS NEO close-approach table:
# < 0.0001 AU is a "very-close" approach (within 4 lunar distances).
NEO_VERY_CLOSE_AU = 0.0001
NEO_CLOSE_AU = 0.001
NEO_NOTABLE_AU = 0.01

# Time-proximity decay constant — events further than 60 days score 0.
DEFAULT_TIME_HORIZON_DAYS = 60.0


# ── Data classes ────────────────────────────────────────────────


@dataclass(frozen=True)
class MissionEvent:
    """One proactive-warning entry for the operator console."""

    event_type: str                    # "launch" | "neo_close_approach"
    designation: str                   # mission name or NEO designation
    when_iso: str                      # ISO-8601 event time
    days_until: float                  # signed days from now
    severity: str                      # "info" | "watch" | "alert"
    score: float                       # 0..1 unitless priority
    description: str                   # operator-readable summary
    upstream_id: Optional[str] = None  # LL2 launch_id or NEO orbit_id
    payload: dict = field(default_factory=dict)


# ── Scoring helpers ─────────────────────────────────────────────


def _days_until_iso(iso_ts: str, now_unix: Optional[float] = None) -> float:
    """Return signed days from now until the ISO timestamp."""
    if now_unix is None:
        now_unix = time.time()
    try:
        # Strip trailing 'Z' and parse as UTC.
        normalized = iso_ts.replace("Z", "+00:00")
        target = datetime.fromisoformat(normalized)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return (target.timestamp() - now_unix) / 86400.0
    except (TypeError, ValueError):
        return math.inf


def _days_until_jd(jd: float, now_unix: Optional[float] = None) -> float:
    """Return signed days from now to a Julian Date."""
    if now_unix is None:
        now_unix = time.time()
    # JD epoch: 1970-01-01 00:00:00 UTC = JD 2440587.5
    target_unix = (jd - 2440587.5) * 86400.0
    return (target_unix - now_unix) / 86400.0


def _time_score(days_until: float, horizon_days: float) -> float:
    """Linear decay 0..1; events past horizon score 0; past events score 0."""
    if days_until < 0 or days_until > horizon_days:
        return 0.0
    return 1.0 - (days_until / horizon_days)


def _neo_proximity_score(close_approach: CloseApproach) -> float:
    """Closer approach + larger object → higher score."""
    if close_approach.dist_au <= NEO_VERY_CLOSE_AU:
        proximity = 1.0
    elif close_approach.dist_au <= NEO_CLOSE_AU:
        proximity = 0.7
    elif close_approach.dist_au <= NEO_NOTABLE_AU:
        proximity = 0.4
    else:
        proximity = 0.1
    # Size proxy: H_mag is INVERTED (smaller H = larger / brighter).
    # H = 22 ≈ 100 m diameter; H = 18 ≈ 1 km. We want bigger = higher.
    if close_approach.h_mag is None:
        size_factor = 0.5
    else:
        # Linear: H=15 (huge) → 1.0; H=25 (small) → 0.0.
        size_factor = max(0.0, min(1.0, (25.0 - close_approach.h_mag) / 10.0))
    return 0.7 * proximity + 0.3 * size_factor


def _launch_density_score(launch: UpcomingLaunch) -> float:
    """Heuristic: high-density missions (Starlink, OneWeb) populate
    LEO with many objects per launch and should rank higher."""
    name_lower = (launch.mission_name or launch.name or "").lower()
    high_density_markers = ("starlink", "oneweb", "kuiper", "iridium next")
    if any(marker in name_lower for marker in high_density_markers):
        return 0.9
    # Crewed missions also rank high (debris awareness for safety).
    if any(marker in name_lower for marker in ("crew", "soyuz", "shenzhou")):
        return 0.8
    # Cislunar / lunar / Mars destinations rank moderately.
    orbit_lower = (launch.mission_orbit or "").lower()
    if any(x in orbit_lower for x in ("lunar", "tli", "tmi", "interplanetary")):
        return 0.6
    # GTO / GEO commercial — moderate.
    if any(x in orbit_lower for x in ("gto", "geo", "gso")):
        return 0.4
    # Default LEO single launch.
    return 0.3


# ── Severity classification ─────────────────────────────────────


def _classify_severity(score: float) -> str:
    if score >= 0.7:
        return "alert"
    if score >= 0.4:
        return "watch"
    return "info"


# ── Aggregator ──────────────────────────────────────────────────


def build_mission_context(
    *,
    horizon_days: float = DEFAULT_TIME_HORIZON_DAYS,
    launch_limit: int = 20,
    neo_dist_max_au: float = 0.05,
    ll_client: Optional[LaunchLibraryClient] = None,
    sbdb_client: Optional[JplSbdbClient] = None,
    now_unix: Optional[float] = None,
) -> List[MissionEvent]:
    """Fetch upcoming launches + NEO close-approaches, score them,
    and return a ranked list of MissionEvent (most urgent first).

    Failures from either upstream are logged and the surviving feed
    still produces output — the bridge degrades gracefully rather
    than failing-closed.
    """
    if ll_client is None:
        ll_client = get_launch_library_client()
    if sbdb_client is None:
        sbdb_client = get_jpl_sbdb_client()

    events: List[MissionEvent] = []

    # ── Upcoming launches ──────────────────────────────────────
    try:
        launches = ll_client.upcoming(limit=launch_limit)
    except Exception as exc:
        logger.warning("mission_context.ll2_unavailable", error=str(exc))
        launches = []

    for launch in launches:
        days_until = _days_until_iso(launch.net_iso, now_unix=now_unix)
        time_s = _time_score(days_until, horizon_days)
        if time_s == 0.0:
            continue
        density_s = _launch_density_score(launch)
        score = 0.6 * time_s + 0.4 * density_s
        events.append(MissionEvent(
            event_type="launch",
            designation=launch.name,
            when_iso=launch.net_iso,
            days_until=days_until,
            severity=_classify_severity(score),
            score=score,
            description=(
                f"{launch.provider} {launch.rocket_name}"
                + (f" → {launch.mission_orbit}" if launch.mission_orbit else "")
            ),
            upstream_id=launch.launch_id,
            payload=launch.as_dict(),
        ))

    # ── NEO close approaches ───────────────────────────────────
    try:
        date_max = f"+{int(horizon_days)}"
        approaches = sbdb_client.close_approaches(
            date_min="now", date_max=date_max,
            dist_max_au=neo_dist_max_au, neo_only=True,
        )
    except Exception as exc:
        logger.warning("mission_context.jpl_unavailable", error=str(exc))
        approaches = []

    for approach in approaches:
        days_until = _days_until_jd(approach.jd_tca, now_unix=now_unix)
        time_s = _time_score(days_until, horizon_days)
        if time_s == 0.0:
            continue
        prox_s = _neo_proximity_score(approach)
        score = 0.5 * time_s + 0.5 * prox_s
        events.append(MissionEvent(
            event_type="neo_close_approach",
            designation=approach.designation,
            when_iso=approach.cd_tca,
            days_until=days_until,
            severity=_classify_severity(score),
            score=score,
            description=(
                f"close approach to {approach.body}: "
                f"{approach.dist_au:.6f} AU, "
                f"v_rel = {approach.v_rel_kmps:.1f} km/s, "
                f"H = {approach.h_mag if approach.h_mag is not None else 'unknown'}"
            ),
            upstream_id=approach.orbit_id,
            payload=approach.as_dict(),
        ))

    events.sort(key=lambda event: event.score, reverse=True)
    return events
