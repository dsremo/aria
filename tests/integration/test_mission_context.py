"""Mission-context bridge tests.

Verifies the LL2 + JPL SBDB feeds fuse into a ranked priority queue
the operator console can drill into. Mocks both upstream clients so
the test never touches the network.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aria.conjunction.mission_context import (
    MissionEvent,
    build_mission_context,
    _classify_severity,
    _days_until_iso,
    _days_until_jd,
    _launch_density_score,
    _neo_proximity_score,
    _time_score,
)
from aria.integrations.jpl_sbdb import CloseApproach, JplSbdbClient
from aria.integrations.launch_library import (
    LaunchLibraryClient,
    UpcomingLaunch,
)


# ── Helper builders ─────────────────────────────────────────────


def _iso_in_n_days(n: float) -> str:
    target = datetime.now(timezone.utc) + timedelta(days=n)
    return target.isoformat().replace("+00:00", "Z")


def _jd_in_n_days(n: float) -> float:
    """Convert "now + N days" into a Julian Date."""
    now_jd = (time.time() / 86400.0) + 2440587.5
    return now_jd + n


def _make_launch(
    name: str = "Falcon 9 | Starlink Group 7-99",
    days_out: float = 10.0,
    rocket: str = "Falcon 9 Block 5",
    provider: str = "SpaceX",
    mission: str = "Starlink Group 7-99",
    orbit: str = "LEO",
) -> UpcomingLaunch:
    return UpcomingLaunch(
        launch_id=f"id-{name}",
        name=name,
        net_iso=_iso_in_n_days(days_out),
        status="GO",
        rocket_name=rocket,
        provider=provider,
        mission_name=mission,
        mission_orbit=orbit,
        pad_name="LC-39A",
        pad_lat_deg=28.6,
        pad_lon_deg=-80.6,
    )


def _make_neo(
    designation: str = "2024 BX1",
    days_out: float = 5.0,
    dist_au: float = 0.0008,
    h_mag: float = 21.5,
) -> CloseApproach:
    return CloseApproach(
        designation=designation,
        body="Earth",
        cd_tca=_iso_in_n_days(days_out),
        jd_tca=_jd_in_n_days(days_out),
        dist_au=dist_au,
        dist_min_au=dist_au * 0.95,
        dist_max_au=dist_au * 1.05,
        v_rel_kmps=8.5,
        v_inf_kmps=8.0,
        h_mag=h_mag,
        orbit_id="42",
    )


def _client_pair(
    launches: list[UpcomingLaunch],
    approaches: list[CloseApproach],
):
    ll = MagicMock(spec=LaunchLibraryClient)
    ll.upcoming.return_value = launches
    sb = MagicMock(spec=JplSbdbClient)
    sb.close_approaches.return_value = approaches
    return ll, sb


# ── Scoring helpers ─────────────────────────────────────────────


class TestTimeScoring:
    def test_event_today_scores_near_one(self):
        assert _time_score(0.0, horizon_days=60.0) == pytest.approx(1.0)

    def test_event_at_horizon_scores_zero(self):
        assert _time_score(60.0, horizon_days=60.0) == pytest.approx(0.0)

    def test_past_event_scores_zero(self):
        assert _time_score(-1.0, horizon_days=60.0) == 0.0

    def test_event_past_horizon_scores_zero(self):
        assert _time_score(120.0, horizon_days=60.0) == 0.0


class TestNeoProximityScore:
    def test_very_close_apophis_class_scores_high(self):
        approach = _make_neo(dist_au=0.00009, h_mag=19.7)
        score = _neo_proximity_score(approach)
        assert score >= 0.7

    def test_distant_small_neo_scores_low(self):
        approach = _make_neo(dist_au=0.04, h_mag=24.5)
        score = _neo_proximity_score(approach)
        assert score <= 0.4

    def test_missing_h_mag_uses_neutral_size_factor(self):
        approach = CloseApproach(
            designation="X", body="Earth", cd_tca="x", jd_tca=0.0,
            dist_au=0.001, dist_min_au=0.0009, dist_max_au=0.0011,
            v_rel_kmps=1.0, v_inf_kmps=1.0, h_mag=None,
        )
        score = _neo_proximity_score(approach)
        assert 0.0 < score < 1.0


class TestLaunchDensityScore:
    def test_starlink_scores_high(self):
        launch = _make_launch(mission="Starlink Group 8-99")
        assert _launch_density_score(launch) >= 0.85

    def test_crewed_mission_scores_high(self):
        launch = _make_launch(mission="Crew-9 to ISS")
        assert _launch_density_score(launch) >= 0.7

    def test_lunar_orbit_scores_moderately(self):
        launch = _make_launch(orbit="TLI", mission="Lunar lander")
        assert 0.5 <= _launch_density_score(launch) <= 0.7

    def test_default_leo_single_scores_low(self):
        launch = _make_launch(mission="Some smallsat", orbit="LEO")
        assert _launch_density_score(launch) <= 0.4


class TestSeverityClassification:
    def test_high_score_is_alert(self):
        assert _classify_severity(0.85) == "alert"

    def test_mid_score_is_watch(self):
        assert _classify_severity(0.55) == "watch"

    def test_low_score_is_info(self):
        assert _classify_severity(0.20) == "info"


# ── Aggregator ──────────────────────────────────────────────────


class TestBuildMissionContext:
    def test_empty_inputs_return_empty_list(self):
        ll, sb = _client_pair([], [])
        events = build_mission_context(ll_client=ll, sbdb_client=sb)
        assert events == []

    def test_starlink_launch_in_3_days_ranks_high(self):
        starlink = _make_launch(
            name="Falcon 9 | Starlink Group 7-99",
            days_out=3.0,
            mission="Starlink Group 7-99",
        )
        ll, sb = _client_pair([starlink], [])
        events = build_mission_context(ll_client=ll, sbdb_client=sb)
        assert len(events) == 1
        assert events[0].event_type == "launch"
        assert events[0].score >= 0.7
        assert events[0].severity == "alert"

    def test_apophis_class_neo_ranks_high(self):
        # Apophis 2029-class: very close (< 0.0001 AU), big (H = 19.7)
        apophis = _make_neo(
            designation="(99942) Apophis",
            days_out=10.0,
            dist_au=0.00009,
            h_mag=19.7,
        )
        ll, sb = _client_pair([], [apophis])
        events = build_mission_context(ll_client=ll, sbdb_client=sb)
        assert len(events) == 1
        assert events[0].event_type == "neo_close_approach"
        assert events[0].score >= 0.7
        assert events[0].severity == "alert"

    def test_events_sorted_by_score_desc(self):
        urgent = _make_launch(name="Crew-9", days_out=2.0, mission="Crew-9 to ISS")
        distant = _make_launch(
            name="GSLV", days_out=55.0, mission="LVM3-M5", orbit="GTO",
        )
        ll, sb = _client_pair([urgent, distant], [])
        events = build_mission_context(ll_client=ll, sbdb_client=sb)
        assert len(events) == 2
        assert events[0].score >= events[1].score
        assert events[0].designation == "Crew-9"

    def test_past_events_dropped(self):
        past = _make_launch(name="History", days_out=-3.0)
        future = _make_launch(name="Future", days_out=10.0)
        ll, sb = _client_pair([past, future], [])
        events = build_mission_context(ll_client=ll, sbdb_client=sb)
        assert len(events) == 1
        assert events[0].designation == "Future"

    def test_far_future_events_dropped(self):
        soon = _make_launch(name="Soon", days_out=5.0)
        far = _make_launch(name="Far", days_out=120.0)
        ll, sb = _client_pair([soon, far], [])
        events = build_mission_context(
            ll_client=ll, sbdb_client=sb, horizon_days=60.0,
        )
        assert len(events) == 1
        assert events[0].designation == "Soon"

    def test_one_upstream_failure_does_not_break_other_feed(self):
        ll = MagicMock(spec=LaunchLibraryClient)
        ll.upcoming.side_effect = RuntimeError("LL2 rate-limit")
        sb = MagicMock(spec=JplSbdbClient)
        sb.close_approaches.return_value = [_make_neo(days_out=7.0)]
        events = build_mission_context(ll_client=ll, sbdb_client=sb)
        assert len(events) == 1
        assert events[0].event_type == "neo_close_approach"

    def test_both_feeds_returned_in_one_batch(self):
        launch = _make_launch(name="Crew-9", days_out=2.0, mission="Crew-9 to ISS")
        neo = _make_neo(days_out=5.0)
        ll, sb = _client_pair([launch], [neo])
        events = build_mission_context(ll_client=ll, sbdb_client=sb)
        types = {event.event_type for event in events}
        assert types == {"launch", "neo_close_approach"}

    def test_payload_round_trips(self):
        launch = _make_launch(days_out=3.0)
        ll, sb = _client_pair([launch], [])
        events = build_mission_context(ll_client=ll, sbdb_client=sb)
        # Payload is the upstream's raw record so the operator UI can
        # surface launch_id, pad lat/lon, etc.
        assert events[0].payload["launch_id"] == launch.launch_id
        assert events[0].payload["pad_name"] == "LC-39A"


# ── Time-stamp helpers ──────────────────────────────────────────


class TestTimeStampHelpers:
    def test_iso_in_3_days_returns_3(self):
        days = _days_until_iso(_iso_in_n_days(3.0))
        assert 2.99 <= days <= 3.01

    def test_iso_past_returns_negative(self):
        days = _days_until_iso(_iso_in_n_days(-2.0))
        assert -2.01 <= days <= -1.99

    def test_jd_in_5_days_returns_5(self):
        days = _days_until_jd(_jd_in_n_days(5.0))
        assert 4.99 <= days <= 5.01

    def test_malformed_iso_returns_inf(self):
        import math
        result = _days_until_iso("not-a-date")
        assert math.isinf(result)
