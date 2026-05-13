"""Run Dsremo anomaly detection on real EDEN ISS ISS telemetry.

This is the first time ARIA's anomaly detection AI runs on real spacecraft
telemetry data. EDEN ISS operated inside the ISS Columbus module in 2020.
The telemetry is real — CO2, temperature, humidity, grow lights (PAR),
and irrigation control valve sensors.

What we validate:
  - Does Dsremo detect the PAR sensor anomalies (21 large jumps in ams-ses:par-1)?
  - Does it flag the CO2 spikes (biggest: 1307 ppm jump on 2020-02-06)?
  - Does it stay quiet on normal channels?

Dsremo pipeline (proper API):
  1. FeatureEngine.compute(channel, value, epoch) — rolling stats, z-score
  2. CalibrationManager.update(channel, residual) — per-channel baseline
  3. EWMADetector.detect(channel, residual, calib) — drift / level shift
  4. CUSUMDetector.detect(channel, residual, calib) — sustained drift
  5. StatisticalDetector.detect(features, window) — spike z-score
  6. VarianceDetector.detect(residuals_array, calib) — variance inflation

Results are saved to data/processed/eden_iss_anomalies.json.

Reference:
    Romberg et al. (2024) EDEN ISS 2020 dataset, Zenodo 11485183.
    Dsremo detection algorithms: see detection/ module docstrings.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import structlog

logger = structlog.get_logger()

DSREMO_PATH = Path(__file__).parent.parent.parent.parent.parent / \
    "Telemetry Anomaly Detection Systems" / "src"

OUTPUT_PATH = Path(__file__).parent.parent.parent.parent / "data" / "processed" / "eden_iss_anomalies.json"


def _import_dsremo():
    """Import Dsremo detection modules, handling path setup."""
    if str(DSREMO_PATH) not in sys.path:
        sys.path.insert(0, str(DSREMO_PATH))
    try:
        from aria.dsremo.detection.ewma import EWMADetector
        from aria.dsremo.detection.cusum import CUSUMDetector
        from aria.dsremo.detection.statistical import StatisticalDetector
        from aria.dsremo.detection.variance_detector import VarianceDetector
        from aria.dsremo.detection.calibration import CalibrationManager
        from aria.dsremo.features.engine import FeatureEngine
        return EWMADetector, CUSUMDetector, StatisticalDetector, VarianceDetector, CalibrationManager, FeatureEngine
    except ImportError as e:
        logger.error("dsremo.import_failed", error=str(e), path=str(DSREMO_PATH))
        raise


def run_detection_on_channel(
    channel_key: str,
    ts_values: list[tuple[str, float]],
    EWMADetector, CUSUMDetector, StatisticalDetector, VarianceDetector,
    CalibrationManager, FeatureEngine,
) -> dict:
    """Run all four Dsremo detectors on a single channel's time series.

    Uses the full Dsremo pipeline:
      FeatureEngine → CalibrationManager → EWMA + CUSUM + Statistical + Variance

    Args:
        channel_key: e.g. 'ams-feg:co2-1'
        ts_values:   list of (timestamp_str, float) pairs

    Returns:
        dict with anomaly counts and flagged timestamps per detector
    """
    ewma_det   = EWMADetector()
    cusum_det  = CUSUMDetector()
    stat_det   = StatisticalDetector()
    var_det    = VarianceDetector()
    calib_mgr  = CalibrationManager()
    feat_eng   = FeatureEngine(window_size=100)   # 100-sample window for EDEN ISS 5-min data

    flagged = {
        "ewma":        [],
        "cusum":       [],
        "statistical": [],
        "variance":    [],
    }

    # Keep a rolling buffer of residuals for VarianceDetector
    residual_buffer: list[float] = []

    for i, (ts, val) in enumerate(ts_values):
        # Step 1: compute features from raw value
        features = feat_eng.compute(channel_key, val, float(i))

        # Step 2: use deviation_from_trend as residual (mean-subtracted)
        residual = features.deviation_from_trend

        # Step 3: update calibration state
        calib = calib_mgr.update(channel_key, residual)

        residual_buffer.append(residual)
        residuals_arr = np.array(residual_buffer[-30:], dtype=np.float64)  # last 30 for variance

        event_base = {
            "index":     i,
            "timestamp": ts,
            "value":     round(val, 3),
            "residual":  round(residual, 4),
        }

        # EWMA detector — needs calibration
        try:
            res = ewma_det.detect(channel_key, residual, calib)
            if res.is_anomaly:
                flagged["ewma"].append({
                    **event_base,
                    "severity":   str(res.severity),
                    "score":      round(res.score, 3),
                })
        except Exception as e:
            logger.debug("detector.ewma.error", channel=channel_key, i=i, error=str(e))

        # CUSUM detector — needs calibration
        try:
            res = cusum_det.detect(channel_key, residual, calib)
            if res.is_anomaly:
                flagged["cusum"].append({
                    **event_base,
                    "severity":   str(res.severity),
                    "score":      round(res.score, 3),
                })
        except Exception as e:
            logger.debug("detector.cusum.error", channel=channel_key, i=i, error=str(e))

        # StatisticalDetector — needs FeatureVector (uses rolling z-score)
        try:
            window_arr = np.array(
                feat_eng._windows[channel_key].values if channel_key in feat_eng._windows else [val],
                dtype=np.float64,
            )
            res = stat_det.detect(features, window_arr)
            if res.is_anomaly:
                flagged["statistical"].append({
                    **event_base,
                    "severity":   str(res.severity),
                    "score":      round(res.score, 3),
                    "z_score":    round(features.z_score, 3),
                })
        except Exception as e:
            logger.debug("detector.statistical.error", channel=channel_key, i=i, error=str(e))

        # VarianceDetector — needs residuals array + calibration
        try:
            if len(residuals_arr) >= 10 and calib.is_calibrated:  # need enough data
                res = var_det.detect(residuals_arr, calib)
                if res.is_anomaly:
                    flagged["variance"].append({
                        **event_base,
                        "severity":   str(res.severity),
                        "score":      round(res.score, 3),
                    })
        except Exception as e:
            logger.debug("detector.variance.error", channel=channel_key, i=i, error=str(e))

    return {
        det_name: {
            "n_flagged": len(events),
            "events":    events[:20],  # cap to first 20 per detector
        }
        for det_name, events in flagged.items()
    }


def run_eden_iss_detection(
    max_channels: int = 10,
    max_rows_per_channel: int = 5000,
) -> dict:
    """Run Dsremo on real EDEN ISS telemetry. Return detection results.

    Args:
        max_channels:         number of channels to process (memory limit)
        max_rows_per_channel: downsample to this many rows (1 Hz limit)

    Returns:
        dict with per-channel detection results and summary stats
    """
    from aria.integrations.eden_iss_loader import iter_all_channels

    (EWMADetector, CUSUMDetector, StatisticalDetector, VarianceDetector,
     CalibrationManager, FeatureEngine) = _import_dsremo()

    t0 = time.time()
    channel_results = {}
    total_anomalies = 0

    processed = 0
    for channel, points in iter_all_channels():
        if processed >= max_channels:
            break

        # Downsample for speed: take every Nth point
        step = max(1, len(points) // max_rows_per_channel)
        ts_values = [(p.timestamp, p.value) for p in points[::step]]

        logger.info("eden_iss.processing", channel=channel,
                    n_points=len(ts_values), total_points=len(points))

        det_results = run_detection_on_channel(
            channel, ts_values,
            EWMADetector, CUSUMDetector, StatisticalDetector, VarianceDetector,
            CalibrationManager, FeatureEngine,
        )

        n_chan_anomalies = sum(r["n_flagged"] for r in det_results.values())
        total_anomalies += n_chan_anomalies
        channel_results[channel] = {
            "n_points_processed": len(ts_values),
            "n_points_total":     len(points),
            "detectors":          det_results,
            "total_anomalies":    n_chan_anomalies,
        }
        processed += 1

    elapsed = time.time() - t0
    summary = {
        "dataset":              "EDEN ISS 2020 (Romberg et al. Zenodo 11485183)",
        "channels_processed":   processed,
        "total_anomaly_events": total_anomalies,
        "elapsed_s":            round(elapsed, 2),
        "channels":             channel_results,
    }

    # Save to processed/
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    return summary


def print_detection_report(summary: dict) -> None:
    """Print a human-readable detection report."""
    print("=" * 65)
    print("  DSREMO ON REAL ISS TELEMETRY — EDEN ISS 2020")
    print("=" * 65)
    print(f"  Dataset: {summary['dataset']}")
    print(f"  Channels processed: {summary['channels_processed']}")
    print(f"  Total anomaly events: {summary['total_anomaly_events']}")
    print(f"  Processing time: {summary['elapsed_s']:.1f}s")
    print()

    for ch, data in summary["channels"].items():
        total = data["total_anomalies"]
        if total > 0:
            print(f"  *** ANOMALIES DETECTED — {ch}")
        else:
            print(f"      Clean           — {ch}")
        for det, res in data["detectors"].items():
            nf = res["n_flagged"]
            if nf > 0:
                first = res["events"][0] if res["events"] else {}
                print(f"      [{det:13s}] {nf:4d} events  "
                      f"first: {first.get('timestamp','?')} "
                      f"val={first.get('value','?')} "
                      f"sev={first.get('severity','?')}")
    print("=" * 65)
    print(f"  Results saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    print("Running Dsremo anomaly detection on real ISS EDEN data...")
    summary = run_eden_iss_detection(max_channels=10, max_rows_per_channel=2000)
    print_detection_report(summary)
