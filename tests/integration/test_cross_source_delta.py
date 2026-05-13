from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from aria.conjunction.data.cross_source_delta import (
    CrossSourceDeltaDetector,
    SourceSnapshot,
    format_delta_human,
    parse_celestrak_response_to_snapshot,
)


ISS_TLE_OLD = (
    "ISS (ZARYA)\n"
    "1 25544U 98067A   24001.00000000  .00010000  00000+0  18000-3 0  9999\n"
    "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000123454\n"
)
ISS_TLE_MANEUVER = (
    "ISS (ZARYA)\n"
    "1 25544U 98067A   24010.00000000  .00010000  00000+0  18000-3 0  9999\n"
    "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.40000000123453\n"
)
HUBBLE_TLE = (
    "HST\n"
    "1 20580U 90037B   24001.00000000  .00000500  00000+0  20000-4 0  9991\n"
    "2 20580  28.4700 200.0000 0002800  85.0000 275.0000 15.10000000234564\n"
)
NEW_DEBRIS_TLE = (
    "DEBRIS-NEW\n"
    "1 99999U 24001A   24010.00000000  .00001000  00000+0  10000-4 0  9994\n"
    "2 99999  53.0000 150.0000 0010000  10.0000 350.0000 15.30000000111115\n"
)


def _snapshot(source: str, *tle_blocks: str) -> SourceSnapshot:
    return parse_celestrak_response_to_snapshot(
        source=source,
        raw_text="\n".join(block.strip() for block in tle_blocks),
        fetched_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
    )


class TestParse:
    def test_parses_celestrak_block(self):
        snap = _snapshot("celestrak:active", ISS_TLE_OLD, HUBBLE_TLE)
        assert snap.source == "celestrak:active"
        assert "25544" in snap.objects_by_norad_id
        assert "20580" in snap.objects_by_norad_id
        assert snap.objects_by_norad_id["25544"].name.startswith("ISS")


class TestFirstRun:
    def test_first_run_no_baseline_no_deltas(self, tmp_path: Path):
        snap = _snapshot("celestrak:active", ISS_TLE_OLD)
        detector = CrossSourceDeltaDetector(
            baseline_path=tmp_path / "baseline.json",
        )
        delta = detector.compute([snap])
        assert delta.baseline_compared is False
        assert delta.new_objects == ()
        assert delta.missing_objects == ()
        assert delta.maneuver_flags == ()


class TestNewObjectDetected:
    def test_new_object_appears_after_baseline(self, tmp_path: Path):
        baseline_snap = _snapshot("celestrak:active", ISS_TLE_OLD, HUBBLE_TLE)
        detector = CrossSourceDeltaDetector(
            baseline_path=tmp_path / "baseline.json",
        )
        detector.write_baseline([baseline_snap])
        current_snap = _snapshot(
            "celestrak:active", ISS_TLE_OLD, HUBBLE_TLE, NEW_DEBRIS_TLE,
        )
        delta = detector.compute([current_snap])
        assert delta.baseline_compared is True
        assert len(delta.new_objects) == 1
        assert delta.new_objects[0].norad_id == "99999"


class TestMissingObjectDetected:
    def test_missing_object_after_decay(self, tmp_path: Path):
        baseline_snap = _snapshot("celestrak:active", ISS_TLE_OLD, HUBBLE_TLE)
        detector = CrossSourceDeltaDetector(
            baseline_path=tmp_path / "baseline.json",
        )
        detector.write_baseline([baseline_snap])
        current_snap = _snapshot("celestrak:active", ISS_TLE_OLD)
        delta = detector.compute([current_snap])
        assert "20580" in delta.missing_objects


class TestManeuverFlagged:
    def test_maneuver_detected_against_baseline_tle(self, tmp_path: Path):
        baseline_snap = _snapshot("celestrak:active", ISS_TLE_OLD)
        detector = CrossSourceDeltaDetector(
            baseline_path=tmp_path / "baseline.json",
        )
        detector.write_baseline([baseline_snap])
        current_snap = _snapshot("celestrak:active", ISS_TLE_MANEUVER)
        delta = detector.compute([current_snap])
        flagged_ids = {flag.norad_id for flag in delta.maneuver_flags}
        assert "25544" in flagged_ids


class TestSourceDisagreement:
    def test_object_in_one_source_not_other(self, tmp_path: Path):
        snap_a = _snapshot("celestrak:active", ISS_TLE_OLD, HUBBLE_TLE)
        snap_b = _snapshot("celestrak:stations", ISS_TLE_OLD)
        detector = CrossSourceDeltaDetector(
            baseline_path=tmp_path / "baseline.json",
        )
        delta = detector.compute([snap_a, snap_b])
        ids = {dis.norad_id for dis in delta.source_disagreements}
        assert "20580" in ids
        hubble_dis = next(
            dis for dis in delta.source_disagreements if dis.norad_id == "20580"
        )
        assert "celestrak:active" in hubble_dis.sources_present
        assert "celestrak:stations" in hubble_dis.sources_absent


class TestBaselinePersistence:
    def test_baseline_round_trip(self, tmp_path: Path):
        snap = _snapshot("celestrak:active", ISS_TLE_OLD, HUBBLE_TLE)
        detector = CrossSourceDeltaDetector(
            baseline_path=tmp_path / "baseline.json",
        )
        detector.write_baseline([snap])
        baseline = detector.load_baseline()
        assert "celestrak:active" in baseline.snapshots
        assert "25544" in baseline.snapshots["celestrak:active"]

    def test_corrupt_baseline_returns_empty(self, tmp_path: Path):
        path = tmp_path / "baseline.json"
        path.write_text("not json", encoding="utf-8")
        detector = CrossSourceDeltaDetector(baseline_path=path)
        baseline = detector.load_baseline()
        assert baseline.snapshots == {}


class TestDigestSerialisation:
    def test_as_dict_is_json_safe(self, tmp_path: Path):
        baseline_snap = _snapshot("celestrak:active", ISS_TLE_OLD)
        detector = CrossSourceDeltaDetector(
            baseline_path=tmp_path / "baseline.json",
        )
        detector.write_baseline([baseline_snap])
        current_snap = _snapshot(
            "celestrak:active", ISS_TLE_OLD, NEW_DEBRIS_TLE,
        )
        delta = detector.compute([current_snap])
        encoded = json.dumps(delta.as_dict())
        assert "99999" in encoded
        assert "celestrak:active" in encoded

    def test_human_format_runs_without_baseline(self, tmp_path: Path):
        snap = _snapshot("celestrak:active", ISS_TLE_OLD)
        detector = CrossSourceDeltaDetector(
            baseline_path=tmp_path / "baseline.json",
        )
        delta = detector.compute([snap])
        text = format_delta_human(delta)
        assert "first run" in text
        assert "celestrak:active" in text


class TestDetectorBehaviour:
    def test_empty_snapshots_rejected(self, tmp_path: Path):
        detector = CrossSourceDeltaDetector(
            baseline_path=tmp_path / "baseline.json",
        )
        with pytest.raises(ValueError, match="snapshot"):
            detector.compute([])
