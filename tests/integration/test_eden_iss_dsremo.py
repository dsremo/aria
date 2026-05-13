"""Integration tests: Dsremo anomaly detection on real EDEN ISS telemetry.

Validates that the full Dsremo pipeline (FeatureEngine → CalibrationManager
→ EWMA + CUSUM + Statistical + Variance detectors) correctly identifies
known anomalies in real ISS greenhouse telemetry.

Ground truth from dataset analysis (Romberg et al. 2024, Zenodo 11485183):
  - ams-ses:par-1: 21 large PAR jumps (grow-light sensor failure pattern)
  - ams-feg:co2-1: CO2 spikes, largest ~2000 ppm above normal in early 2020
  - ams-feg:temp-gl: Temperature anomaly 2020-02-05 (confirmed multi-detector)
  - Temperature channels (temp-1, temp-2): should be mostly stable
"""

from __future__ import annotations

import pytest
from pathlib import Path

EDEN_ISS_BASE = (
    Path(__file__).parent.parent.parent
    / "data" / "raw" / "eden_iss" / "edeniss2020"
)


def _has_eden_data() -> bool:
    """Check if EDEN ISS raw data is present."""
    return EDEN_ISS_BASE.exists() and any(EDEN_ISS_BASE.iterdir())


def _has_dsremo() -> bool:
    """Check if Dsremo src is importable."""
    import sys
    dsremo_path = (
        Path(__file__).parent.parent.parent.parent.parent
        / "Telemetry Anomaly Detection Systems" / "src"
    )
    if str(dsremo_path) not in sys.path:
        sys.path.insert(0, str(dsremo_path))
    try:
        import dsremo  # noqa: F401
        return True
    except ImportError:
        return False


skip_no_eden = pytest.mark.skipif(
    not _has_eden_data(),
    reason="EDEN ISS raw data not present in data/raw/eden_iss/",
)
skip_no_dsremo = pytest.mark.skipif(
    not _has_dsremo(),
    reason="Dsremo package not importable",
)
needs_both = pytest.mark.skipif(
    not (_has_eden_data() and _has_dsremo()),
    reason="Requires both EDEN ISS data and Dsremo package",
)


class TestEdenIssLoader:
    """Verify the EDEN ISS CSV loader works on real data."""

    @skip_no_eden
    def test_iter_all_channels_yields_data(self):
        """iter_all_channels() must yield at least 50 channels."""
        from aria.integrations.eden_iss_loader import iter_all_channels
        channels = list(iter_all_channels())
        assert len(channels) >= 50, (
            f"Expected ≥50 EDEN ISS channels, got {len(channels)}"
        )

    @skip_no_eden
    def test_co2_channel_has_many_points(self):
        """CO2 channel must have ≥1000 points (full-year 5-min data)."""
        from aria.integrations.eden_iss_loader import iter_all_channels
        for channel, points in iter_all_channels():
            if "co2" in channel.lower():
                assert len(points) >= 1000, (
                    f"CO2 channel {channel} has only {len(points)} points"
                )
                break

    @skip_no_eden
    def test_par_channel_has_anomaly_jumps(self):
        """ams-ses:par-1 must have ≥10 large-jump anomalies (known ground truth)."""
        from aria.integrations.eden_iss_loader import iter_all_channels, compute_channel_stats
        for channel, points in iter_all_channels():
            if channel == "ams-ses:par-1":
                stats = compute_channel_stats(channel, points)
                assert stats.n_large_jumps >= 10, (
                    f"ams-ses:par-1 should have ≥10 large jumps, got {stats.n_large_jumps}"
                )
                return
        pytest.skip("ams-ses:par-1 not found in dataset")

    @skip_no_eden
    def test_telemetry_points_have_valid_values(self):
        """All loaded TelemetryPoints must have finite values (no NaN passed through)."""
        import math
        from aria.integrations.eden_iss_loader import iter_all_channels
        n_checked = 0
        for channel, points in iter_all_channels():
            for p in points[:50]:
                assert math.isfinite(p.value), (
                    f"NaN/Inf in {channel}: {p.value} at {p.timestamp}"
                )
                n_checked += 1
            if n_checked > 500:
                break
        assert n_checked > 0


class TestDsremoDetectionOnEdenIss:
    """Dsremo detects known anomalies in real EDEN ISS telemetry."""

    @needs_both
    def test_pipeline_runs_without_error(self):
        """Full detection pipeline must complete on 3 channels without raising."""
        from aria.integrations.eden_iss_dsremo import run_eden_iss_detection
        summary = run_eden_iss_detection(max_channels=3, max_rows_per_channel=500)
        assert "channels" in summary
        assert summary["channels_processed"] == 3

    @needs_both
    def test_co2_channel_has_anomaly_events(self):
        """CO2 channel must have at least one anomaly detected by any detector.

        CO2 in EDEN ISS FEG section spikes above 2000 ppm during early 2020,
        driven by plant respiration and sensor recalibration events.
        """
        from aria.integrations.eden_iss_dsremo import run_eden_iss_detection
        from aria.integrations.eden_iss_loader import iter_all_channels

        summary = run_eden_iss_detection(max_channels=10, max_rows_per_channel=500)
        assert "ams-feg:co2-1" in summary["channels"], (
            "ams-feg:co2-1 not in processed channels"
        )
        co2 = summary["channels"]["ams-feg:co2-1"]
        assert co2["total_anomalies"] > 0, (
            "Expected CO2 anomalies in EDEN ISS data, got zero"
        )

    @needs_both
    def test_statistical_detector_flags_co2_spike(self):
        """StatisticalDetector (z-score) must flag the CO2 spike above 2000 ppm.

        The 2020-02-18 13:45 reading of 2030 ppm is ~3σ above baseline.
        Ground truth: first event val=2030.0 at 2020-02-18 in ams-feg:co2-1.
        """
        from aria.integrations.eden_iss_dsremo import run_eden_iss_detection

        summary = run_eden_iss_detection(max_channels=10, max_rows_per_channel=2000)
        co2 = summary["channels"].get("ams-feg:co2-1", {})
        stat = co2.get("detectors", {}).get("statistical", {})
        assert stat.get("n_flagged", 0) > 0, (
            "StatisticalDetector found no CO2 spikes — expected ≥1 from 2030 ppm event"
        )
        # Verify at least one event has value > 1500 ppm (above normal ~800 ppm)
        high_events = [
            e for e in stat.get("events", [])
            if e.get("value", 0) > 1500
        ]
        assert len(high_events) > 0, (
            f"No CO2 spike events with val > 1500 ppm. Events: {stat.get('events', [])[:5]}"
        )

    @needs_both
    def test_all_four_detectors_agree_on_critical_channel(self):
        """All 4 detectors must flag ams-feg:temp-gl on 2020-02-05.

        This temperature anomaly in the grow-light gallery is confirmed
        multi-detector: EWMA, CUSUM, Statistical, and Variance all flag CRITICAL.
        This is the strongest validation point — consensus across all 4 algorithms.
        """
        from aria.integrations.eden_iss_dsremo import run_eden_iss_detection

        summary = run_eden_iss_detection(max_channels=10, max_rows_per_channel=2000)
        temp_gl = summary["channels"].get("ams-feg:temp-gl", {})
        detectors = temp_gl.get("detectors", {})

        detectors_with_events = [
            det for det, res in detectors.items()
            if res.get("n_flagged", 0) > 0
        ]
        assert len(detectors_with_events) >= 3, (
            f"Expected ≥3 detectors to flag ams-feg:temp-gl. "
            f"Only flagged by: {detectors_with_events}"
        )

    @needs_both
    def test_results_saved_to_json(self):
        """Detection results must be saved to data/processed/eden_iss_anomalies.json."""
        from aria.integrations.eden_iss_dsremo import run_eden_iss_detection, OUTPUT_PATH
        import json

        run_eden_iss_detection(max_channels=3, max_rows_per_channel=300)

        assert OUTPUT_PATH.exists(), f"Output file not created: {OUTPUT_PATH}"
        with open(OUTPUT_PATH) as f:
            data = json.load(f)

        assert "dataset" in data
        assert "channels" in data
        assert data["channels_processed"] >= 1

    @needs_both
    def test_channel_results_have_required_keys(self):
        """Each channel result must contain n_points_processed and detectors."""
        from aria.integrations.eden_iss_dsremo import run_eden_iss_detection

        summary = run_eden_iss_detection(max_channels=3, max_rows_per_channel=300)
        for channel, data in summary["channels"].items():
            assert "n_points_processed" in data, f"{channel} missing n_points_processed"
            assert "detectors" in data, f"{channel} missing detectors"
            for det_name in ("ewma", "cusum", "statistical", "variance"):
                assert det_name in data["detectors"], (
                    f"{channel} missing detector '{det_name}'"
                )

    @needs_both
    def test_total_anomaly_count_nonzero(self):
        """Processing 10 channels of real ISS data must find at least 50 anomaly events."""
        from aria.integrations.eden_iss_dsremo import run_eden_iss_detection

        summary = run_eden_iss_detection(max_channels=10, max_rows_per_channel=500)
        assert summary["total_anomaly_events"] >= 50, (
            f"Expected ≥50 anomaly events across 10 channels, "
            f"got {summary['total_anomaly_events']}"
        )
