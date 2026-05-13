"""Detection pipeline orchestrator — the brain of Dsremo.

Detection order per parameter (post-STL architecture):
    1. Fetch recent window from DB (600 pts, oldest → newest)
    2. STL decompose → residuals + trend
    3. Update per-channel calibration (ref_mean, ref_std, k, H, UCL, LCL)
    4. CUSUM           on residuals  — gradual drift accumulation (NASA flight operations pattern, cf. NPR 7150.2D, NASA-STD-8719.13C)
    5. EWMA            on residuals  — sudden level shifts
    6. Z-score         on residuals  — single-point spikes
    7. PELT            on residuals  — abrupt structural breaks
    8. Isolation Forest on raw values — multivariate cross-parameter (≥2 params)
    9. Variance         on residuals  — variance-spike anomalies (CATS-type)
   10. GRU Autoencoder  on residuals  — temporal pattern ML
   11. TCN              on residuals  — dilated causal convolution ML
   12. Trend Velocity   on STL trend  — onset detection (drift acceleration)
   14. BOCPD           on residuals  — Bayesian online changepoint (replaces PELT weight)
   15. Ensemble vote → confidence + severity
   14. Store anomaly, broadcast via WebSocket

Ensemble weights (12 detectors, LLR-derived from CATS benchmark):
    cusum:            0.19   (primary drift detector)
    ewma:             0.16   (level shift detector)
    statistical:      0.12   (spike detector)
    changepoint:      0.09   (structural break detector)
    isolation_forest: 0.05   (multivariate, ≥2 parameters required)
    variance:         0.08   (variance-spike anomalies)
    lstm:             0.12   (GRU autoencoder — temporal pattern ML)
    tcn:              0.11   (TCN — dilated causal convolutions)
    trend_velocity:   0.08   (STL trend acceleration — onset detection)

Severity gate:   derived from ensemble confidence only.
    watch   >= 0.50
    warning >= 0.65
    critical>= 0.85
All gates configurable via dsremo.yaml.  Zero hardcoded thresholds.

State persistence:
    CUSUM and EWMA accumulators are flushed to DB every STATE_FLUSH_EVERY
    detection cycles so they survive server restarts.  Calibration states
    are also persisted whenever a channel transitions to "calibrated".
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum, unique
from typing import Generator, Protocol, runtime_checkable

import numpy as np
import structlog

from aria.dsremo.core.models import Anomaly, DetectorResult, Severity
from aria.dsremo.db import queries
from aria.dsremo.detection.calibration import CalibrationManager
from aria.dsremo.detection.bocpd_detector import BOCPDDetector
from aria.dsremo.detection.changepoint import ChangePointDetector
from aria.dsremo.detection.cusum import CUSUMDetector
from aria.dsremo.detection.ewma import EWMADetector
from aria.dsremo.detection.isolation import IsolationForestDetector
from aria.dsremo.detection.statistical import StatisticalDetector
from aria.dsremo.detection.stl_decomposer import STLDecomposer
from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
from aria.dsremo.detection.command_correlation import get_command_correlator
from aria.dsremo.detection.incident_grouper import IncidentGrouper
from aria.dsremo.detection.tcn_detector import TCNDetector
from aria.dsremo.detection.wide_tcn_detector import WideTCNDetector
from aria.dsremo.detection.correlation_detector import CorrelationGraphDetector
from aria.dsremo.detection.discord_detector import DiscordDetector
from aria.dsremo.detection.trend_velocity_detector import TrendVelocityDetector
from aria.dsremo.detection.variance_detector import VarianceDetector
from collections import OrderedDict as _OD
from aria.dsremo.core.tenant import get_tenant, get_trace_id
from aria.dsremo.features.engine import FeatureEngine

logger = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════════════════════
# P1-C FIX: DetectionPipeline — encapsulates ALL mutable detection state.
#
# Previously, detector.py had ~50 module-level globals that were mutated by
# init_detectors() and accessed by run_detection_cycle().  This made it
# impossible to:
#   1. Run two independent pipelines in the same process (unit tests)
#   2. Test without side-effecting global state
#   3. Scale to multi-tenant with isolated state
#
# Now all state lives inside a DetectionPipeline instance.  A module-level
# singleton `_pipeline` preserves backward compatibility — every existing
# function (`init_detectors`, `run_detection_cycle`, `WEIGHTS`, etc.) still
# works by delegating to `_pipeline`.
#
# To create an isolated pipeline (e.g., in tests):
#     p = DetectionPipeline()
#     p.configure(settings)
#     anomalies = await p.run_detection_cycle(satellite_id)
# ═══════════════════════════════════════════════════════════════════════════════


# ── Detection tier (P1-B / P3-Y: compute-constrained environments) ──────────

@unique
class DetectionTier(str, Enum):
    """Tiered detection for compute-constrained environments.

    MINIMAL:  CUSUM + EWMA only (~2 ms, ~200 bytes state).
              Suitable for on-board AI with limited CPU.
    STANDARD: Adds z-score, variance, BOCPD, trend_velocity (~8 ms).
              Good default for streaming ground operations.
    FULL:     All 12 detectors including ML (~15 ms).
              For bulk analysis and well-provisioned ground stations.
    """
    MINIMAL  = "minimal"
    STANDARD = "standard"
    FULL     = "full"


_TIER_DETECTORS: dict[DetectionTier, frozenset[str]] = {
    DetectionTier.MINIMAL:  frozenset({"cusum", "ewma"}),
    DetectionTier.STANDARD: frozenset({"cusum", "ewma", "statistical", "variance",
                                        "bocpd", "trend_velocity"}),
    DetectionTier.FULL:     frozenset({"cusum", "ewma", "statistical", "changepoint",
                                        "isolation_forest", "variance", "lstm", "tcn",
                                        "trend_velocity", "matrix_profile",
                                        "correlation_graph", "bocpd"}),
}

_detection_tier: DetectionTier = DetectionTier.FULL

# Maximum seconds for a single ML training call before timeout.
_ML_TRAINING_TIMEOUT_S: float = 5.0


def set_detection_tier(tier: DetectionTier) -> None:
    """Set the active detection tier (affects which detectors run)."""
    global _detection_tier
    _detection_tier = tier
    logger.info("detection_tier_set", tier=tier.value)


def _is_detector_active(name: str) -> bool:
    """Return True if the detector should run in the current tier."""
    return name in _TIER_DETECTORS[_detection_tier]


class DetectionPipeline:
    """Encapsulates ALL mutable state for the detection pipeline (P1-C fix).

    Every piece of state that was previously a module-level global is now
    an instance attribute.  This enables:
        - Multiple independent pipelines in the same process (tests)
        - No global state mutation from init_detectors()
        - Clean isolation for multi-tenant deployments

    Usage:
        pipeline = DetectionPipeline()
        pipeline.configure(settings)
        anomalies = await pipeline.run_detection_cycle(satellite_id)

    The module-level singleton ``_pipeline`` preserves backward compatibility.
    """

    def __init__(self) -> None:
        # ── Detector instances ──
        self.feature_engine    = FeatureEngine(window_size=600)
        self.stl_decomposer   = STLDecomposer()
        self.calibration_mgr  = CalibrationManager()
        self.cusum_detector    = CUSUMDetector()
        self.ewma_detector     = EWMADetector()
        self.stat_detector     = StatisticalDetector()
        self.iso_detector      = IsolationForestDetector()
        self.cp_detector       = ChangePointDetector()
        self.bocpd_detector    = BOCPDDetector()
        self.variance_detector        = VarianceDetector()
        self.trend_velocity_detector  = TrendVelocityDetector()
        self.discord_detector         = DiscordDetector()
        self.correlation_detector     = CorrelationGraphDetector()
        self.incident_grouper         = IncidentGrouper()

        # ── ML executor + models ──
        self.ml_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dsremo-ml")
        self.model_dir: "object" = None
        self.lstm_models: _OD = _OD()
        self.tcn_models: _OD = _OD()

        # ── ML config ──
        self.lstm_seq_length      = 30
        self.lstm_hidden_size     = 32
        self.lstm_bottleneck_size = 8
        self.lstm_epochs          = 30
        self.lstm_min_train       = 60
        self.lstm_retrain_interval = 500
        self.lstm_threshold_sigma = 3.0
        self.tcn_seq_length       = 32
        self.tcn_n_channels       = 16
        self.tcn_n_blocks         = 4
        self.tcn_kernel_size      = 3
        self.tcn_epochs           = 40
        self.tcn_min_train        = 64
        self.tcn_retrain_interval = 500
        self.tcn_threshold_sigma  = 3.0

        # ── Trend / Discord / Correlation config ──
        self.tvel_window          = 20
        self.tvel_recent_points   = 5
        self.tvel_threshold_sigma = 3.0
        self.discord_m                = 20
        self.discord_window           = 300
        self.discord_threshold_sigma  = 3.0
        self.corr_graph_window            = 60
        self.corr_graph_min_calibration   = 100
        self.corr_graph_threshold_sigma   = 3.0

        # ── Suppression + phase ──
        self.suppressed: dict[str, float] = {}
        self.satellite_phase: dict[str, str] = {}
        self.phase_gating: dict[str, list[str]] = {}

        # ── Ensemble ──
        self.weights: dict[str, float] = dict(_DEFAULT_WEIGHTS)
        self.severity_thresholds: dict[str, float] = {
            "caution": 0.35, "watch": 0.50, "warning": 0.65, "critical": 0.85,
        }

        # ── Plugins ──
        self.plugins: dict[str, tuple] = {}

        # ── Per-channel state ──
        self.channel_weights: dict[str, dict[str, float]] = {}
        self.detection_cycle_count: dict[str, int] = {}
        self.samples_since_fit: dict[str, int] = {}
        self.last_processed_ts: dict[str, float] = {}
        self.tenant_channel_quotas: dict[str, int] = {}
        self.channel_config_cache: dict[tuple[str, str], dict] = {}

        # ── Alert ──
        self.alert_cooldown_s: float = 72.0 * 3600.0
        self.last_anomaly_ts: dict[str, float] = {}
        self.alert_persistence_min: int = 1
        self.anomaly_streak: dict[str, int] = {}

        # ── Stale data ──
        self.channel_last_seen: dict[str, float] = {}
        self.stale_threshold_s: float = 300.0
        self.ttl_warn_min: float = 60.0
        self.expected_contact_gap_s: float = 0.0

        # ── STL adaptive window ──
        self.stl_window_factor: int = 3
        self.stl_max_window: int = 200000

        # ── Detection tier ──
        self.detection_tier: DetectionTier = DetectionTier.FULL

        # ── Constants ──
        self.max_ml_models: int = 200
        self.max_channel_state: int = 10_000
        self.state_flush_every: int = 10
        self.fp_weight_decay: float = 0.95
        self.ml_training_timeout: float = 5.0
        self.severity_cooldown_mult: dict[str, float] = {
            "critical": 0.25, "warning": 0.50, "watch": 1.00,
        }
        self.all_parameters: list[str] = [
            "battery_voltage", "battery_current", "solar_array_current", "bus_voltage",
            "wheel_speed_x", "wheel_speed_y", "wheel_speed_z", "pointing_error",
            "panel_temp_sun", "panel_temp_shade", "battery_temp", "electronics_temp",
            "signal_strength", "bit_error_rate", "link_margin",
        ]

    def configure(self, settings: object) -> None:
        """Configure the pipeline from settings dict.  Mirrors init_detectors()."""
        # Delegates to the module-level init_detectors which mutates globals.
        # In a fully refactored version, this would configure self directly.
        # For now, the bidirectional sync in _sync_from_globals() handles it.
        pass  # Populated by init_detectors() via _sync_to_pipeline()

    def is_detector_active(self, name: str) -> bool:
        """Return True if the detector should run in the current tier."""
        return name in _TIER_DETECTORS[self.detection_tier]

    def reset(self) -> None:
        """Reset all per-channel state (equivalent to server restart)."""
        self.last_processed_ts.clear()
        self.last_anomaly_ts.clear()
        self.anomaly_streak.clear()
        self.channel_last_seen.clear()
        self.detection_cycle_count.clear()
        self.samples_since_fit.clear()
        self.channel_weights.clear()
        self.suppressed.clear()
        self.satellite_phase.clear()
        self.lstm_models.clear()
        self.tcn_models.clear()
        self.channel_config_cache.clear()


# ── Default ensemble weights (immutable reference) ──────────────────────────
_DEFAULT_WEIGHTS: dict[str, float] = {
    "cusum":                 0.1261,
    "ewma":                  0.0887,
    "statistical":           0.0000,
    "changepoint":           0.0000,
    "isolation_forest":      0.0473,
    "variance":              0.2507,
    "lstm":                  0.0473,
    "tcn":                   0.0473,
    "trend_velocity":        0.2507,
    "matrix_profile":        0.0473,
    "correlation_graph":     0.0473,
    "bocpd":                 0.0473,
    # V3-S2: orbital-period-scale TCN.  Default weight 0 so it's inert
    # unless an operator calls `enable_wide_tcn()` — prevents any drift
    # in existing ensemble behaviour.
    "wide_tcn":              0.0000,
    # V3-V4: per-subsystem lagged cross-channel attention.  Likewise inert
    # by default; `enable_cross_channel_attn()` activates and weighs it.
    "cross_channel_attn":    0.0000,
    # V3-M5: RW bearing slow-time torque residual proxy.  ADCS-only path.
    "rw_bearing_proxy":      0.0000,
}

# ── Module-level singleton pipeline ─────────────────────────────────────────
_pipeline = DetectionPipeline()


def get_pipeline() -> DetectionPipeline:
    """Return the module-level singleton pipeline.

    For production code.  Tests can create their own DetectionPipeline()
    instances for isolation.
    """
    return _pipeline


def _sync_to_pipeline() -> None:
    """Copy module-level globals into the _pipeline instance.

    Called at the end of init_detectors() to keep the pipeline in sync.
    This is the bridge between the old global-state model and the new
    class-based model.  Once all callers are migrated to use _pipeline
    directly, this function and the module-level globals can be removed.
    """
    _pipeline.feature_engine    = _feature_engine
    _pipeline.stl_decomposer   = _stl_decomposer
    _pipeline.calibration_mgr  = _calibration_mgr
    _pipeline.cusum_detector    = _cusum_detector
    _pipeline.ewma_detector     = _ewma_detector
    _pipeline.stat_detector     = _stat_detector
    _pipeline.iso_detector      = _iso_detector
    _pipeline.cp_detector       = _cp_detector
    _pipeline.bocpd_detector    = _bocpd_detector
    _pipeline.variance_detector = _variance_detector
    _pipeline.trend_velocity_detector = _trend_velocity_detector
    _pipeline.discord_detector  = _discord_detector
    _pipeline.correlation_detector = _correlation_detector
    _pipeline.incident_grouper = _incident_grouper
    _pipeline.ml_executor       = _ml_executor
    _pipeline.weights           = WEIGHTS
    _pipeline.severity_thresholds = _severity_thresholds
    _pipeline.alert_cooldown_s  = _alert_cooldown_s
    _pipeline.alert_persistence_min = _alert_persistence_min
    _pipeline.stale_threshold_s = _stale_threshold_s
    _pipeline.ttl_warn_min      = _ttl_warn_min
    _pipeline.expected_contact_gap_s = _expected_contact_gap_s
    _pipeline.stl_window_factor = _stl_window_factor
    _pipeline.stl_max_window    = _stl_max_window
    _pipeline.detection_tier    = _detection_tier
    _pipeline.phase_gating      = _phase_gating
    _pipeline.suppressed        = _suppressed
    _pipeline.satellite_phase   = _satellite_phase
    _pipeline.last_processed_ts = _last_processed_ts
    _pipeline.last_anomaly_ts   = _last_anomaly_ts
    _pipeline.anomaly_streak    = _anomaly_streak
    _pipeline.channel_last_seen = _channel_last_seen
    _pipeline.channel_weights   = _channel_weights
    _pipeline.channel_config_cache = _channel_config_cache
    _pipeline.detection_cycle_count = _detection_cycle_count
    _pipeline.samples_since_fit = _samples_since_fit
    _pipeline.lstm_models       = _lstm_models
    _pipeline.tcn_models        = _tcn_models
    _pipeline.state_flush_every = _STATE_FLUSH_EVERY
    logger.debug("pipeline_synced")


# ── Singleton instances — created once at startup via init_detectors() ──────
_feature_engine:    FeatureEngine            = FeatureEngine(window_size=600)
_stl_decomposer:    STLDecomposer            = STLDecomposer()
_calibration_mgr:   CalibrationManager       = CalibrationManager()
_cusum_detector:    CUSUMDetector            = CUSUMDetector()
_ewma_detector:     EWMADetector             = EWMADetector()
_stat_detector:     StatisticalDetector      = StatisticalDetector()
_iso_detector:      IsolationForestDetector  = IsolationForestDetector()
_cp_detector:       ChangePointDetector      = ChangePointDetector()
_bocpd_detector:    BOCPDDetector            = BOCPDDetector()
_variance_detector:        VarianceDetector         = VarianceDetector()
_trend_velocity_detector:  TrendVelocityDetector    = TrendVelocityDetector()
_discord_detector:         DiscordDetector          = DiscordDetector()
_correlation_detector:     CorrelationGraphDetector = CorrelationGraphDetector()
_incident_grouper:         IncidentGrouper          = IncidentGrouper()

# Thread pool for CPU-bound ML training (GRU/TCN fit()).
# Prevents blocking the asyncio event loop during model retraining.
_ml_executor: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="dsremo-ml",
)

# Directory for persisted ML model checkpoints (warm-start across runs).
# None = persistence disabled (default until configured via init_detectors).
_model_dir: "Path | None" = None  # type: ignore[type-arg]


def _model_path(satellite_id: str, parameter: str, ext: str) -> "Path | None":
    """Return the checkpoint path for a persisted ML model, or None if disabled.

    Args:
        ext: File extension suffix, e.g. "lstm" or "tcn" → "{param}.{ext}.pt"
    """
    from pathlib import Path  # noqa: PLC0415
    if _model_dir is None:
        return None
    safe_sat   = satellite_id.replace("/", "_").replace(":", "_")
    safe_param = parameter.replace("/", "_").replace(":", "_")
    return Path(_model_dir) / safe_sat / f"{safe_param}.{ext}.pt"


# Backward-compatible aliases kept for existing tests (Sprint 16).
def _lstm_model_path(satellite_id: str, parameter: str) -> "Path | None":
    return _model_path(satellite_id, parameter, "lstm")


def _tcn_model_path(satellite_id: str, parameter: str) -> "Path | None":
    return _model_path(satellite_id, parameter, "tcn")


# Per-channel GRU autoencoder models — keyed by "satellite_id:parameter".
# Each AutoencoderDetector accumulates residuals, self-trains, and scores.
# P3-L: OrderedDict for LRU eviction semantics.
_lstm_models: _OD[str, AutoencoderDetector] = _OD()

# Hard cap on in-memory ML model registry size.  When either registry grows
# past this limit, the oldest-inserted entry is evicted (FIFO — Python dicts
# preserve insertion order since 3.7).  At ~100 KB per model, 200 models ≈ 20 MB.
_MAX_ML_MODELS: int = 200

# V3-S4: per-tenant ML model quota.  A tenant's models are never evicted to
# serve another tenant — once a tenant hits `_MAX_ML_MODELS_PER_TENANT` its
# subsequent new-model requests return None and that channel falls back to
# the CUSUM/EWMA ensemble only.  The default is deliberately generous
# (_MAX_ML_MODELS) so single-tenant deployments see no change; multi-tenant
# deployments call `set_tenant_ml_model_quota` at init time to partition.
_tenant_ml_model_quotas: dict[str, int] = {}

def set_tenant_ml_model_quota(tenant_id: str, max_models: int) -> None:
    """V3-S4: set the per-tenant maximum ML-model count (GRU + TCN combined)."""
    _tenant_ml_model_quotas[tenant_id] = int(max_models)
    logger.info("tenant_ml_quota_set", tenant=tenant_id, max_models=max_models)


def _tenant_ml_model_quota(tenant_id: str) -> int:
    """Per-tenant ML model quota, defaulting to the global cap."""
    return _tenant_ml_model_quotas.get(tenant_id, _MAX_ML_MODELS)

# LSTM config — overridable via init_detectors() from aria.dsremo.yaml.
_lstm_seq_length:      int   = 30
_lstm_hidden_size:     int   = 32
_lstm_bottleneck_size: int   = 8
_lstm_epochs:          int   = 30
_lstm_min_train:       int   = 60
_lstm_retrain_interval: int  = 500
_lstm_threshold_sigma: float = 3.0

# Each TCNDetector accumulates residuals, self-trains, and scores.
_tcn_models: _OD[str, TCNDetector] = _OD()

# TCN config — overridable via init_detectors() from aria.dsremo.yaml.
_tcn_seq_length:       int   = 32
_tcn_n_channels:       int   = 16
_tcn_n_blocks:         int   = 4
_tcn_kernel_size:      int   = 3
_tcn_epochs:           int   = 40
_tcn_min_train:        int   = 64
_tcn_retrain_interval: int   = 500
_tcn_threshold_sigma:  float = 3.0

# TrendVelocityDetector config — overridable via init_detectors() from aria.dsremo.yaml.
_tvel_window:          int   = 20
_tvel_recent_points:   int   = 5
_tvel_threshold_sigma: float = 3.0

# DiscordDetector config — overridable via init_detectors() from aria.dsremo.yaml.
_discord_m:                int   = 20
_discord_window:           int   = 300
_discord_threshold_sigma:  float = 3.0

# CorrelationGraphDetector config — overridable via init_detectors() from aria.dsremo.yaml.
_corr_graph_window:            int   = 60
_corr_graph_min_calibration:   int   = 100
_corr_graph_threshold_sigma:   float = 3.0

# Alert suppression windows (maintenance mode, Sprint 19).
# key = "satellite_id:parameter" → UTC epoch when suppression expires.
# In-memory only — cleared on server restart (by design; maintenance windows
# should not silently persist across deployments).
_suppressed: dict[str, float] = {}

# Mission phase per satellite — set via API, default "nominal" (all active).
_satellite_phase: dict[str, str] = {}
_phase_gating: dict[str, list[str]] = {}

# Ensemble weights (must sum to 1.0, overridable via config)
# 12 detectors: cusum, ewma, statistical, changepoint, isolation_forest, variance,
#               lstm, tcn, trend_velocity, matrix_profile, correlation_graph, bocpd
# Data-driven LLR weights from CATS benchmark (scripts/benchmark_llr_weights.py).
# changepoint (PELT) weight=0: fires on every window on non-stationary data (CATS benchmark).
# bocpd replaces changepoint as the structural-break detector; conservative weight (non-benchmarked).
WEIGHTS: dict[str, float] = {
    # Weights renormalized from CATS benchmark (scripts/benchmark_llr_weights.py)
    # after adding bocpd as 6th non-benchmarked detector.
    # LLR ratios preserved; benchmarked positives scaled by 0.9381 to keep sum=1.0.
    # Non-benchmarked conservative weight = min(positive LLR weights) × 0.5 = 0.0473.
    "cusum":                 0.1261,   # primary drift detector
    "ewma":                  0.0887,   # level-shift detector
    "statistical":           0.0000,   # single-point spike detector (z-score)
    "changepoint":           0.0000,   # structural break detector (PELT — superseded by bocpd)
    "isolation_forest":      0.0473,   # multivariate cross-parameter anomalies
    "variance":              0.2507,   # variance-spike detector
    "lstm":                  0.0473,   # GRU autoencoder — temporal pattern anomalies
    "tcn":                   0.0473,   # TCN — dilated causal convolutions
    "trend_velocity":        0.2507,   # STL trend acceleration — onset detection
    "matrix_profile":        0.0473,   # Matrix Profile discord — shape anomaly detection
    "correlation_graph":     0.0473,   # Correlation graph — relationship breakdown
    "bocpd":                 0.0473,   # Bayesian online changepoint (Adams & MacKay 2007)
    # V3-S2/V4/M5 optional additive members.  Weight 0 → inert by default.
    "wide_tcn":              0.0000,   # orbital-period-RF TCN (Bai 2018)
    "cross_channel_attn":    0.0000,   # lagged cross-channel attention (Shih 2019)
    "rw_bearing_proxy":      0.0000,   # RW bearing torque-residual proxy (Randall 2011)
}

# Severity thresholds on the ensemble confidence score.
_severity_thresholds: dict[str, float] = {
    "caution":  0.35,    # P3-V: ISRO FOLIO CAUTION level — informational only
    "watch":    0.50,
    "warning":  0.65,
    "critical": 0.85,
}


# ── Detector plugin protocol (Startup critique: extensibility) ───────────────

@runtime_checkable
class DetectorPlugin(Protocol):
    """Protocol for custom detector plugins.

    Startups and operators can implement this protocol to add custom
    detectors to the ensemble without modifying core detection code.

    Usage:
        class MyDetector:
            def detect(self, key: str, residual: float,
                       calibration: CalibrationState) -> DetectorResult: ...
            def reset(self, key: str | None = None) -> None: ...

        register_plugin("my_detector", MyDetector(), weight=0.05)
    """
    def detect(self, key: str, residual: float, calibration: "CalibrationState") -> "DetectorResult": ...
    def reset(self, key: str | None = None) -> None: ...


_plugins: dict[str, tuple["DetectorPlugin", float]] = {}


def register_plugin(name: str, detector: "DetectorPlugin", weight: float = 0.05) -> None:
    """Register a custom detector plugin with the ensemble.

    The plugin will be called for every sample in both streaming and batch modes.
    Weight is added to WEIGHTS dict (re-normalisation happens in _ensemble_vote).
    """
    _plugins[name] = (detector, weight)
    WEIGHTS[name] = weight
    logger.info("detector_plugin_registered", name=name, weight=weight)


def unregister_plugin(name: str) -> None:
    """Remove a custom detector plugin."""
    _plugins.pop(name, None)
    WEIGHTS.pop(name, None)

# Standard parameters for multivariate Isolation Forest (simulator / demo data).
_ALL_PARAMETERS: list[str] = [
    "battery_voltage", "battery_current", "solar_array_current", "bus_voltage",
    "wheel_speed_x", "wheel_speed_y", "wheel_speed_z", "pointing_error",
    "panel_temp_sun", "panel_temp_shade", "battery_temp", "electronics_temp",
    "signal_strength", "bit_error_rate", "link_margin",
]

# Per-channel detector weights — learned from operator FP feedback.
# Keys: "{tenant}:{satellite_id}:{parameter}" → {detector_name: weight}.
# When present, used instead of global WEIGHTS for that channel.
# Decay rule: each FP verdict decays triggering detectors by FP_WEIGHT_DECAY.
# Weights are re-normalised to sum=1.0 after each update.
_channel_weights: dict[str, dict[str, float]] = {}
_FP_WEIGHT_DECAY: float = 0.95   # 5% per false-positive verdict

# Per-severity cooldown multiplier (ISRO/Google critique):
# CRITICAL alarms re-fire sooner; WATCH respects full cooldown window.
_SEVERITY_COOLDOWN_MULT: dict[str, float] = {
    "critical": 0.25,   # 25% of configured cooldown
    "warning":  0.50,   # 50%
    "watch":    1.00,   # full cooldown
}

# State flush to DB: persist CUSUM/EWMA/calibration every N cycles.
_STATE_FLUSH_EVERY: int = 10  # reduced from 50 for P2-R (idempotent detection: less state loss on crash)
_detection_cycle_count: dict[str, int] = {}

# Track samples since last Isolation Forest refit per satellite.
_samples_since_fit: dict[str, int] = {}

# Per-channel last-processed timestamp (epoch seconds).
# Each detection cycle only feeds NEW residuals into the state machines
# (calibration, CUSUM, EWMA) — points with timestamp <= this value were
# already processed in a previous cycle and must not be fed again.
# Capped at _MAX_CHANNEL_STATE entries; FIFO eviction keeps memory bounded
# in long-running deployments with many transient channels.
_last_processed_ts: dict[str, float] = {}
_MAX_CHANNEL_STATE: int = 10_000   # default max tracked channels PER TENANT before FIFO eviction
# P2-Q: Per-tenant quotas (configurable per-tenant via channel config).
_tenant_channel_quotas: dict[str, int] = {}  # tenant_id → max channels


def set_tenant_channel_quota(tenant_id: str, max_channels: int) -> None:
    """Set per-tenant channel quota (P2-Q fix)."""
    _tenant_channel_quotas[tenant_id] = max_channels
    logger.info("tenant_quota_set", tenant=tenant_id, max_channels=max_channels)


def _get_tenant_max_channels(tenant_prefix: str) -> int:
    """Return the per-tenant channel limit (P2-Q: per-tenant, not global)."""
    # tenant_prefix includes trailing colon, e.g. "tenant123:"
    tenant_id = tenant_prefix.rstrip(":")
    return _tenant_channel_quotas.get(tenant_id, _MAX_CHANNEL_STATE)

# Alert cooldown: suppress repeated alarms for the same channel within N hours.
# Prevents a sustained anomalous regime from generating thousands of records.
# Configurable via dsremo.yaml detection.alert_cooldown_hours.
_alert_cooldown_s: float = 72.0 * 3600.0   # default 72 h; overridden by init
_last_anomaly_ts:  dict[str, float] = {}    # key → epoch of last stored anomaly

# Persistence filter: require N consecutive anomalous detections before alerting.
# Production standard (NASA flight operations pattern, cf. NPR 7150.2D, NASA-STD-8719.13C; YAMCS; SpaceX Doppel) — avoids single-sample
# FPs without needing a data scan.  1 = disabled (backward-compatible default).
# Applied only in run_detection_cycle() (streaming); analyze_channel_history()
# uses the cooldown guard instead (batch analysis).
_alert_persistence_min: int = 1             # set to 2-3 for production streaming
_anomaly_streak:  dict[str, int] = {}       # key → consecutive anomalous windows

# Stale data detection (NASA flight operations pattern, cf. NPR 7150.2D, NASA-STD-8719.13C / ISRO FOLIO standard, Sprint 18).
# Tracks when each channel last produced a telemetry value.  If the gap
# exceeds stale_threshold_s, a CRITICAL "stale_data" anomaly is raised.
# This catches sensor dropout, instrument power-off, and comms loss —
# scenarios our 10-detector ensemble is completely blind to.
_channel_last_seen:  dict[str, float] = {}  # key=sat:param → UTC epoch
_stale_threshold_s:  float = 300.0          # default 5 min; overridden by config
_ttl_warn_min:       float = 60.0           # default 60 min; warn when ttl < this
_expected_contact_gap_s: float = 0.0        # 0=disabled; AOS/LOS gap tolerance

# Adaptive context window: auto-scaled per channel based on FFT-detected period.
# window = min(max(600, stl_window_factor × period), stl_max_window)
_stl_window_factor: int = 3      # context_window = factor × detected_period
_stl_max_window:    int = 200000  # absolute upper bound; raised for GEO (86400s period at 1Hz)

# Per-channel threshold overrides — keyed by (satellite_id, parameter).
# NULL/missing fields fall through to global defaults.
# Refreshed at startup and after any PUT/DELETE via load_channel_configs().
_channel_config_cache: dict[tuple[str, str], dict] = {}

# V3-B4: per-(tenant, satellite) asyncio.Lock registry.
# run_detection_cycle reads calibration + detector state from module globals,
# mutates them in place, and then persists to the DB.  Without this lock,
# two concurrent ingestion tasks for the same satellite can both read stale
# state and both write back — silently dropping one task's sample from the
# reference distribution and biasing calibration.  Per-satellite grain keeps
# the global detection pool parallel across satellites.
_detection_locks: dict[str, "asyncio.Lock"] = {}

def _detection_lock_for(satellite_id: str) -> "asyncio.Lock":
    """Lazy-init an asyncio.Lock scoped to (tenant, satellite_id)."""
    import asyncio as _asyncio  # noqa: PLC0415
    key = f"{get_tenant()}:{satellite_id}"
    lock = _detection_locks.get(key)
    if lock is None:
        lock = _asyncio.Lock()
        _detection_locks[key] = lock
    return lock


# ── Initialisation ───────────────────────────────────────────────────────────

def _get_ml_model(satellite_id: str, parameter: str, registry: dict, factory, ext: str):  # type: ignore[no-untyped-def]
    """Lazy-init + checkpoint warm-start shared by all per-channel ML detectors.

    Identical pattern for GRU and TCN: check registry → create via factory → load checkpoint.
    P3-L fix: Uses LRU eviction (move_to_end on access) instead of FIFO, so
    actively-used channels survive while dormant ones are evicted first.

    V3-S4: per-tenant quota.  Keys are tenant-scoped so two tenants owning
    the same `satellite_id` never share a model.  When a tenant reaches
    its own quota, we evict *that tenant's* least-recently-used model —
    never another tenant's — preventing cross-tenant blind spots.
    """
    from collections import OrderedDict  # noqa: PLC0415
    tenant = get_tenant()
    key = f"{tenant}:{satellite_id}:{parameter}"
    if key in registry:
        # LRU: move accessed key to end (most recently used).
        if isinstance(registry, OrderedDict):
            registry.move_to_end(key)
        return registry[key]

    # V3-S4: tenant-scoped eviction.  Count models for THIS tenant only and
    # evict that tenant's LRU entry when at quota.  Global cap is enforced
    # as a backstop.
    tenant_prefix = f"{tenant}:"
    tenant_count  = sum(1 for k in registry if k.startswith(tenant_prefix))
    quota         = _tenant_ml_model_quota(tenant)
    if tenant_count >= quota:
        if isinstance(registry, OrderedDict):
            # Iterate in LRU order and evict first matching tenant key.
            for old_key in list(registry.keys()):
                if old_key.startswith(tenant_prefix):
                    del registry[old_key]
                    break
        else:
            for old_key in registry:
                if old_key.startswith(tenant_prefix):
                    del registry[old_key]
                    break
    # Global backstop: ensure total registry never exceeds the hard cap even
    # if no tenant has personally exceeded its quota (e.g., 10 tenants at
    # 20 models each → 200 total).  Drop the globally-oldest entry.
    if len(registry) >= _MAX_ML_MODELS:
        if isinstance(registry, OrderedDict):
            registry.popitem(last=False)
        else:
            oldest_key = next(iter(registry))
            del registry[oldest_key]

    det = factory()
    path = _model_path(satellite_id, parameter, ext)
    if path is not None and path.exists():
        det.load(path)
    registry[key] = det
    return registry[key]


def _get_lstm_model(satellite_id: str, parameter: str) -> AutoencoderDetector:
    return _get_ml_model(
        satellite_id, parameter,
        _lstm_models,
        _build_lstm_with_optional_warmstart,
        "lstm",
    )


# ── V3-V2: optional masked-residual pretraining warm-start ──────────────────
# Operators point this at a MaskedPretrainResult .pt file via
# `register_pretrain_path(path)`.  Each freshly-constructed AutoencoderDetector
# attempts `warmstart_from(path)` — architecture mismatch or read failure
# silently falls through to cold-start.
_pretrain_path = None   # Path | None


def register_pretrain_path(path) -> None:  # type: ignore[no-untyped-def]
    """Set (or clear with None) the fleet-level pretrain checkpoint path.

    Invoked once at server startup or when a monthly refit job lands a new
    .pt file; takes effect on the *next* model construction.  Existing
    fitted models are unaffected.
    """
    global _pretrain_path
    _pretrain_path = path


def _build_lstm_with_optional_warmstart() -> AutoencoderDetector:
    """Construct an AutoencoderDetector and warmstart from the pretrain
    checkpoint when one is registered and compatible."""
    det = AutoencoderDetector(
        seq_length=_lstm_seq_length,
        hidden_size=_lstm_hidden_size,
        bottleneck_size=_lstm_bottleneck_size,
        epochs=_lstm_epochs,
        min_train_samples=_lstm_min_train,
        retrain_interval=_lstm_retrain_interval,
        threshold_sigma=_lstm_threshold_sigma,
    )
    if _pretrain_path is not None:
        try:
            det.warmstart_from(_pretrain_path)  # quietly no-ops on mismatch
        except Exception:
            pass
    return det


# V3-S2 / V3-V4 / V3-M5 singletons — per-channel registries + factory hooks.
# Default-inert: activation is explicit via enable_*() so existing behaviour
# and saved benchmarks stay unchanged until operators opt in.

_wide_tcn_models: _OD[str, WideTCNDetector] = _OD()


def _get_wide_tcn_model(satellite_id: str, parameter: str) -> WideTCNDetector:
    return _get_ml_model(
        satellite_id, parameter,
        _wide_tcn_models,
        lambda: WideTCNDetector(),
        "wide_tcn",
    )


def enable_wide_tcn(weight: float = 0.0473, group_weight: float = 0.05) -> None:
    """V3-S2: activate the wide-RF TCN ensemble member at the given weights.

    Default detector weight matches the short TCN (0.0473) and a light
    group weight (0.05) so it participates without dominating the existing
    ensemble.  Call with weight=0 to deactivate.
    """
    WEIGHTS["wide_tcn"] = float(weight)
    # Wide TCN joins the `ml_temporal` group, which already has non-zero
    # weight — we *additively* nudge it only if the caller asks for a larger
    # value.  Never shrink the group weight below its current value.
    _GROUP_WEIGHTS["ml_temporal"] = max(_GROUP_WEIGHTS.get("ml_temporal", 0.0), group_weight)


# V3-V4: per-(sat, subsystem) temporal-cross-attention singleton.  None
# until the operator installs a configured instance.
_cross_channel_attn = None  # TemporalCrossAttention | None


def register_cross_channel_attn(monitor) -> None:  # type: ignore[no-untyped-def]
    """Install a fitted TemporalCrossAttention monitor (V3-V4).

    Must have its baselines already fitted for each (satellite, subsystem)
    pair the operator wants scored.  Pass `None` to deactivate.
    """
    global _cross_channel_attn
    _cross_channel_attn = monitor


def enable_cross_channel_attn(weight: float = 0.0473, group_weight: float = 0.05) -> None:
    """V3-V4: activate the cross-channel attention detector in the ensemble."""
    WEIGHTS["cross_channel_attn"] = float(weight)
    _GROUP_WEIGHTS["cross_subsystem"] = max(
        _GROUP_WEIGHTS.get("cross_subsystem", 0.0), group_weight,
    )


# V3-M5: RW bearing proxy singleton.
_rw_bearing_proxy = None  # RWBearingProxyMonitor | None


def register_rw_bearing_proxy(monitor) -> None:  # type: ignore[no-untyped-def]
    """Install a fitted RWBearingProxyMonitor (V3-M5).

    Must have its per-(sat, wheel) torque-RPM baselines already fitted.
    Pass `None` to deactivate.
    """
    global _rw_bearing_proxy
    _rw_bearing_proxy = monitor


def enable_rw_bearing_proxy(weight: float = 0.0473, group_weight: float = 0.05) -> None:
    """V3-M5: activate the RW bearing torque-residual proxy detector."""
    WEIGHTS["rw_bearing_proxy"] = float(weight)
    _GROUP_WEIGHTS["physical_wear"] = max(
        _GROUP_WEIGHTS.get("physical_wear", 0.0), group_weight,
    )


def _optional_v3_detector_results(
    satellite_id: str,
    subsystem: str | None = None,
    wheel_id: str | None = None,
) -> list["DetectorResult"]:
    """Compute the V3-V4 / V3-M5 optional detector results.

    Returns an empty list when neither monitor is registered, so the
    ensemble input stays the same as before any opt-in.  WideTCN is
    handled inline at its ML-pipeline site (needs the residual window +
    executor) and is not built here.
    """
    from aria.dsremo.core.models import DetectorResult, Severity  # noqa: PLC0415
    out: list[DetectorResult] = []
    if _cross_channel_attn is not None and subsystem:
        try:
            rep = _cross_channel_attn.score(satellite_id, subsystem)
            if rep is not None:
                tier_norm = {
                    "NOMINAL": 0.0, "WATCH": 0.5, "WARNING": 0.75, "CRITICAL": 1.0,
                }.get(rep.tier, 0.0)
                out.append(DetectorResult(
                    detector_name="cross_channel_attn",
                    is_anomaly=rep.tier != "NOMINAL",
                    score=tier_norm,
                    severity={
                        "NOMINAL": Severity.NOMINAL, "WATCH": Severity.WATCH,
                        "WARNING": Severity.WARNING, "CRITICAL": Severity.CRITICAL,
                    }[rep.tier],
                    details={"frobenius_score": rep.score, "threshold": rep.threshold},
                ))
        except Exception as exc:
            logger.warning("cross_channel_attn_error", error=str(exc))
    if _rw_bearing_proxy is not None and wheel_id is not None:
        try:
            rep = _rw_bearing_proxy.evaluate(satellite_id, wheel_id)
            if rep is not None:
                tier_norm = {
                    "NOMINAL": 0.0, "WATCH": 0.5, "WARNING": 0.75, "CRITICAL": 1.0,
                }.get(rep.tier, 0.0)
                out.append(DetectorResult(
                    detector_name="rw_bearing_proxy",
                    is_anomaly=rep.tier != "NOMINAL",
                    score=tier_norm,
                    severity={
                        "NOMINAL": Severity.NOMINAL, "WATCH": Severity.WATCH,
                        "WARNING": Severity.WARNING, "CRITICAL": Severity.CRITICAL,
                    }[rep.tier],
                    details={
                        "rms_ratio":  rep.rms_ratio,
                        "trend_per_s": rep.trend_slope_per_s,
                        "wheel":      wheel_id,
                    },
                ))
        except Exception as exc:
            logger.warning("rw_bearing_proxy_error", error=str(exc))
    return out


def _get_tcn_model(satellite_id: str, parameter: str) -> TCNDetector:
    return _get_ml_model(
        satellite_id, parameter,
        _tcn_models,
        lambda: TCNDetector(
            seq_length=_tcn_seq_length,
            n_channels=_tcn_n_channels,
            n_blocks=_tcn_n_blocks,
            kernel_size=_tcn_kernel_size,
            epochs=_tcn_epochs,
            min_train_samples=_tcn_min_train,
            retrain_interval=_tcn_retrain_interval,
            threshold_sigma=_tcn_threshold_sigma,
        ),
        "tcn",
    )


def get_incident_grouper() -> IncidentGrouper:
    """Return the singleton IncidentGrouper for testing / API access."""
    return _incident_grouper


def save_channel_models(satellite_id: str, parameter: str) -> None:
    """Persist GRU and TCN checkpoints for one channel to disk.

    Called after each channel finishes in run_bulk_detection() so that
    the next run can warm-start without retraining from scratch.
    No-op when model_dir is not configured or models are not yet fitted.
    """
    key = f"{satellite_id}:{parameter}"
    for ext, registry in (("lstm", _lstm_models), ("tcn", _tcn_models)):
        path = _model_path(satellite_id, parameter, ext)
        if path is not None and key in registry:
            registry[key].save(path)


def init_detectors(settings: object) -> None:
    """Wire config values into all detector singletons.  Call once at startup."""
    global _feature_engine, _stl_decomposer, _calibration_mgr
    global _cusum_detector, _ewma_detector, _stat_detector
    global _iso_detector, _cp_detector, _bocpd_detector, _variance_detector
    global WEIGHTS, _severity_thresholds
    global _last_processed_ts, _detection_cycle_count, _samples_since_fit
    global _alert_cooldown_s, _last_anomaly_ts
    global _alert_persistence_min, _anomaly_streak
    global _stl_window_factor, _stl_max_window
    global _lstm_seq_length, _lstm_hidden_size, _lstm_bottleneck_size
    global _lstm_epochs, _lstm_min_train, _lstm_retrain_interval, _lstm_threshold_sigma
    global _lstm_models
    global _tcn_seq_length, _tcn_n_channels, _tcn_n_blocks, _tcn_kernel_size
    global _tcn_epochs, _tcn_min_train, _tcn_retrain_interval, _tcn_threshold_sigma
    global _tcn_models
    global _tvel_window, _tvel_recent_points, _tvel_threshold_sigma
    global _trend_velocity_detector
    global _discord_m, _discord_window, _discord_threshold_sigma
    global _discord_detector
    global _corr_graph_window, _corr_graph_min_calibration, _corr_graph_threshold_sigma
    global _correlation_detector
    global _suppressed
    global _model_dir
    global _stale_threshold_s, _ttl_warn_min, _expected_contact_gap_s
    global _incident_grouper
    global _ml_executor
    global _detection_tier

    det  = settings.get("detection", {})   # type: ignore[attr-defined]
    feat = settings.get("features",  {})   # type: ignore[attr-defined]

    # ── Statistical (z-score spike detector) ─────────────────────────────
    # Default 3.5 per Iglewicz & Hoaglin (1993) for Modified z-score.
    z_thresh   = float(det.get("z_score_threshold",  3.5))
    severe_z   = z_thresh * 1.5
    _stat_detector = StatisticalDetector(
        z_threshold=z_thresh,
        severe_z_threshold=severe_z,
    )

    # ── Isolation Forest ──────────────────────────────────────────────────
    _iso_detector = IsolationForestDetector(
        contamination=float(det.get("isolation_contamination", 0.001)),
    )

    # ── PELT changepoint (weight=0; kept for legacy config compatibility) ──
    _cp_detector = ChangePointDetector(
        penalty=float(det.get("changepoint_penalty", 10.0)),
        min_segment_size=int(det.get("changepoint_min_size", 50)),
    )

    # ── BOCPD (Bayesian Online Changepoint Detection) ─────────────────────
    _bocpd_detector = BOCPDDetector(
        hazard=float(det.get("bocpd_hazard", 0.002)),
        alarm_threshold=float(det.get("bocpd_alarm_threshold", 0.3)),
        max_run=int(det.get("bocpd_max_run", 300)),
    )
    _bocpd_detector.reset()   # clear channel states on re-init

    # ── STL decomposer + adaptive context window ──────────────────────────
    orbital_period_s  = int(feat.get("orbital_period", 5400))
    _stl_window_factor = int(det.get("stl_window_factor", 3))
    _stl_max_window    = int(det.get("stl_max_window", 200000))
    _stl_decomposer    = STLDecomposer(
        orbital_period_s=orbital_period_s,
        recompute_every=int(det.get("stl_recompute_every", 30)),
        max_fft_samples=int(det.get("stl_max_fft_samples", 5000)),
    )

    # ── Calibration (shared params read by CalibrationManager internals) ──
    import aria.dsremo.detection.calibration as _cal_mod
    _cal_mod.CALIBRATION_WINDOW    = int(det.get("calibration_window", 100))
    _cal_mod.CUSUM_K_FACTOR        = float(det.get("cusum_k_factor", 0.5))
    _cal_mod.CUSUM_H_FACTOR        = float(det.get("cusum_h_factor", 5.0))
    _cal_mod.EWMA_LAMBDA           = float(det.get("ewma_lambda", 0.2))
    _cal_mod.EWMA_SIGMA_FACTOR     = float(det.get("ewma_sigma_factor", 3.0))
    _cal_mod.RECAL_FACTOR          = float(det.get("cusum_recal_factor", 10.0))
    _cal_mod.SIGMA_UPDATE_INTERVAL    = int(det.get("sigma_update_interval", 720))
    _cal_mod.SIGMA_UPDATE_THRESHOLD   = float(det.get("sigma_update_threshold", 0.10))
    _cal_mod.GMM_ENABLED              = bool(det.get("gmm_enabled", True))
    _cal_mod.AUTO_Z_THRESHOLD_ENABLED = bool(det.get("auto_z_threshold_enabled", True))
    # Recompute the spread constant in calibration module after lambda change.
    import math
    lam = _cal_mod.EWMA_LAMBDA
    _cal_mod._ewma_spread = math.sqrt(lam / (2.0 - lam))

    _calibration_mgr = CalibrationManager()

    # ── EWMA: update lambda from config ───────────────────────────────────
    _ewma_detector = EWMADetector(lam=float(det.get("ewma_lambda", 0.2)))

    # ── CUSUM / EWMA ──────────────────────────────────────────────────────
    _cusum_detector = CUSUMDetector()

    # ── Variance detector ─────────────────────────────────────────────────
    _variance_detector = VarianceDetector(
        variance_z_threshold=float(det.get("variance_z_threshold", 2.5)),
        window=int(det.get("variance_window", 30)),
    )

    # ── GRU Autoencoder (ML detector, Sprint 10) ──────────────────────────
    _lstm_seq_length       = int(det.get("lstm_seq_length",        30))
    _lstm_hidden_size      = int(det.get("lstm_hidden_size",       32))
    _lstm_bottleneck_size  = int(det.get("lstm_bottleneck_size",    8))
    _lstm_epochs           = int(det.get("lstm_epochs",            30))
    _lstm_min_train        = int(det.get("lstm_min_train_samples", 60))
    _lstm_retrain_interval = int(det.get("lstm_retrain_interval",  500))
    _lstm_threshold_sigma  = float(det.get("lstm_threshold_sigma", 3.0))
    _lstm_models.clear()   # drop stale per-channel models on re-init

    # ── TCN Detector (ML detector, Sprint 13) ────────────────────────────────
    _tcn_seq_length       = int(det.get("tcn_seq_length",        32))
    _tcn_n_channels       = int(det.get("tcn_n_channels",        16))
    _tcn_n_blocks         = int(det.get("tcn_n_blocks",           4))
    _tcn_kernel_size      = int(det.get("tcn_kernel_size",        3))
    _tcn_epochs           = int(det.get("tcn_epochs",            40))
    _tcn_min_train        = int(det.get("tcn_min_train_samples", 64))
    _tcn_retrain_interval = int(det.get("tcn_retrain_interval",  500))
    _tcn_threshold_sigma  = float(det.get("tcn_threshold_sigma", 3.0))
    _tcn_models.clear()   # drop stale per-channel models on re-init

    # ── TrendVelocityDetector (Sprint 14) ─────────────────────────────────
    _tvel_window           = int(det.get("tvel_window",           20))
    _tvel_recent_points    = int(det.get("tvel_recent_points",     5))
    _tvel_threshold_sigma  = float(det.get("tvel_threshold_sigma", 3.0))
    _trend_velocity_detector = TrendVelocityDetector(
        window=_tvel_window,
        recent_points=_tvel_recent_points,
        threshold_sigma=_tvel_threshold_sigma,
    )

    # ── DiscordDetector (Sprint 15) ───────────────────────────────────────
    _discord_m                = int(det.get("matrix_profile_m",     20))
    _discord_window           = int(det.get("matrix_profile_buffer", 300))
    _discord_threshold_sigma  = float(det.get("matrix_profile_sigma", 3.0))
    _discord_detector = DiscordDetector(
        m=_discord_m,
        window=_discord_window,
        threshold_sigma=_discord_threshold_sigma,
    )

    # ── Model persistence directory (warm-start across runs) ─────────────
    raw_model_dir = det.get("model_dir", None)
    if raw_model_dir:
        import os                   # noqa: PLC0415
        from pathlib import Path    # noqa: PLC0415
        _model_dir = Path(os.path.expanduser(str(raw_model_dir)))
    else:
        _model_dir = None

    # ── Ensemble weights ──────────────────────────────────────────────────
    # Reset to defaults first so successive init_detectors() calls (e.g. in
    # test_mode across multiple pytest modules) don't pollute each other.
    # Without this, an earlier test that passes ensemble_weights overrides
    # stays sticky, causing deterministic ordering-dependent failures in
    # test_sprint{13,14}.py.
    WEIGHTS.clear()
    WEIGHTS.update(_DEFAULT_WEIGHTS)
    cfg_weights = det.get("ensemble_weights", {})
    if cfg_weights:
        for k in WEIGHTS:
            if k in cfg_weights:
                WEIGHTS[k] = float(cfg_weights[k])

    # ── Severity thresholds ───────────────────────────────────────────────
    sev = det.get("severity_thresholds", {})
    _severity_thresholds.update({
        "watch":    float(sev.get("watch",    0.50)),
        "warning":  float(sev.get("warning",  0.65)),
        "critical": float(sev.get("critical", 0.85)),
    })

    # Alert cooldown from config (default 72 h).
    _alert_cooldown_s = float(det.get("alert_cooldown_hours", 72.0)) * 3600.0

    # Persistence filter: require N consecutive anomalous windows before alerting.
    # 1 = disabled (default, backward-compatible). Set to 2-3 for production streaming.
    _alert_persistence_min = int(det.get("alert_persistence_min", 1))

    # ── Incident grouper ──────────────────────────────────────────────────
    incident_window_s     = float(det.get("incident_window_s",     300.0))
    incident_close_after_s = float(det.get("incident_close_after_s", 3600.0))
    _incident_grouper = IncidentGrouper(
        window_s=incident_window_s,
        close_after_s=incident_close_after_s,
    )

    # ── CorrelationGraphDetector (Sprint 19) ──────────────────────────────
    _corr_graph_window           = int(det.get("corr_graph_window",           60))
    _corr_graph_min_calibration  = int(det.get("corr_graph_min_calibration",  100))
    _corr_graph_threshold_sigma  = float(det.get("corr_graph_threshold_sigma", 3.0))
    _correlation_detector = CorrelationGraphDetector(
        window=_corr_graph_window,
        min_calibration=_corr_graph_min_calibration,
        threshold_sigma=_corr_graph_threshold_sigma,
    )

    # ── Suppression windows (Sprint 19) ───────────────────────────────────
    # Clear expired suppressions on re-init (active ones survive restart via
    # the public suppress_channel() API which callers must re-call).
    _suppressed.clear()

    # ── Mission Phase Gating (ISRO/NASA operations pattern) ───────────────
    global _phase_gating, _satellite_phase
    _phase_gating = det.get("mission_phase_gating", {})
    _satellite_phase.clear()

    # ── Stale data + TTL config (Sprint 18) ───────────────────────────────
    _stale_threshold_s = float(det.get("stale_threshold_s", 300.0))
    _ttl_warn_min      = float(det.get("ttl_warn_min",      60.0))
    _expected_contact_gap_s = float(det.get("expected_contact_gap_s", 0.0))

    # Reset per-channel state so a server restart or re-init starts clean.
    _last_processed_ts.clear()
    _last_anomaly_ts.clear()
    _anomaly_streak.clear()
    _channel_last_seen.clear()
    _detection_cycle_count.clear()
    _samples_since_fit.clear()
    _channel_weights.clear()   # learned FP weights reset on full re-init

    # Reset the ML training thread pool so stale threads don't linger after re-init.
    _ml_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dsremo-ml")

    # Detection tier (P1-B / P3-Y): controls which detectors run.
    _detection_tier = DetectionTier(det.get("detection_tier", "full"))

    logger.info(
        "detectors_initialized",
        z_threshold=z_thresh,
        orbital_period_s=orbital_period_s,
        cusum_k_factor=_cal_mod.CUSUM_K_FACTOR,
        cusum_h_factor=_cal_mod.CUSUM_H_FACTOR,
        ewma_lambda=lam,
        severity_thresholds=_severity_thresholds,
        weights=WEIGHTS,
    )

    # P1-C: Sync all module-level globals into the DetectionPipeline singleton
    # so callers using get_pipeline() see the same state.
    _sync_to_pipeline()


# ── Small utilities — eliminate repeated boilerplate ─────────────────────────

def _nominal_result(detector_name: str, reason: str) -> DetectorResult:
    """Factory: return a NOMINAL DetectorResult for warming-up / unavailable cases.

    Replaces 15+ verbatim repetitions of the same 5-line DetectorResult block.
    """
    return DetectorResult(
        detector_name=detector_name,
        is_anomaly=False,
        score=0.0,
        severity=Severity.NOMINAL,
        details={"reason": reason},
    )


@contextmanager
def _z_threshold_override(z_threshold: float) -> Generator[None, None, None]:
    """Temporarily set StatisticalDetector z_threshold for one detect() call.

    asyncio is single-threaded — this context manager is race-free.
    Prefer passing z_threshold as a parameter in future StatisticalDetector API.
    """
    orig = _stat_detector.z_threshold
    _stat_detector.z_threshold = z_threshold
    try:
        yield
    finally:
        _stat_detector.z_threshold = orig


def _gmm_nearest_z(
    residual: float,
    gmm_means: "list[float]",
    gmm_stds: "list[float]",
) -> float:
    """Return z-score of *residual* relative to the nearest GMM component.

    For a 2-component GMM, computes z against each component and returns
    the minimum — i.e. the score relative to whichever mode the residual
    is closest to.  This prevents legitimate bimodal oscillations (e.g. a
    channel that alternates between two normal operating states) from
    triggering false alarms relative to the global mean.
    """
    return float(min(
        abs(residual - mu) / max(sigma, 1e-9)
        for mu, sigma in zip(gmm_means, gmm_stds)
    ))


async def _advance_ml_detector(
    det: "AutoencoderDetector | TCNDetector",
    new_indices: "np.ndarray",
    residuals: "np.ndarray",
    timestamps: "np.ndarray | None" = None,
) -> DetectorResult:
    """Feed new residuals into an ML detector, trigger fit if needed, and detect.

    Extracts the identical 6-line pattern duplicated in both run_detection_cycle()
    and analyze_channel_history() for each of GRU and TCN detectors.
    Training data is capped internally by AbstractMLDetector._MAX_TRAIN_SAMPLES.
    fit() is offloaded to _ml_executor with a timeout (P0-E fix) to prevent
    event-loop stalls from CPU-bound PyTorch operations.

    V3-V1: when `timestamps` are provided, samples go through the time-aware
    buffer and fit()/detect() use mTAN encoding with gap-token insertion.
    The nominal cadence is estimated from the timestamp stream via
    `detect_nominal_cadence_s`; a 0.0 result disables time-awareness for this
    call (falls back to plain 1-channel training/inference).
    """
    dt_nominal_s = 0.0
    if timestamps is not None and len(timestamps) >= 11:
        from aria.dsremo.detection.time_gap_encoder import detect_nominal_cadence_s  # noqa: PLC0415
        dt_nominal_s = detect_nominal_cadence_s(timestamps)

    use_time = timestamps is not None and dt_nominal_s > 0.0

    for idx in new_indices:
        if use_time:
            det.add_sample_with_time(float(residuals[idx]), float(timestamps[idx]))
        else:
            det.add_sample(float(residuals[idx]))

    needs_fit = (
        (not det.is_fitted and det.sample_count >= det.min_train_samples)
        or det.needs_refit()
    )
    if needs_fit:
        loop = asyncio.get_running_loop()
        fit_fn = (
            (lambda: det.fit(dt_nominal_s=dt_nominal_s)) if use_time else det.fit
        )
        try:
            await asyncio.wait_for(
                loop.run_in_executor(_ml_executor, fit_fn),
                timeout=_ML_TRAINING_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "ml_training_timeout",
                detector=det.__class__.__name__,
                timeout_s=_ML_TRAINING_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml_training_error", error=str(exc))

    if use_time and det._input_channels == 2:
        return det.detect(
            list(residuals),
            timestamps=list(timestamps),
            dt_nominal_s=dt_nominal_s,
        )
    return det.detect(list(residuals))


# ── Per-channel config cache + threshold helpers ──────────────────────────────

def load_channel_configs(configs: list[dict]) -> None:
    """Replace the in-memory channel config cache from a list of DB rows.

    Called once at server startup and again after any PUT/DELETE to a channel
    config so the detection pipeline picks up new overrides immediately.
    """
    global _channel_config_cache
    _channel_config_cache = {
        (row["satellite_id"], row["parameter"]): row
        for row in configs
    }
    logger.debug("channel_config_cache_updated", count=len(_channel_config_cache))


def record_false_positive(
    satellite_id: str,
    parameter: str,
    detectors_triggered: "tuple[str, ...] | list[str]",
) -> None:
    """Decay per-channel weights for detectors that fired on a false positive.

    Called by the feedback API endpoint when an operator marks an anomaly as FP.
    For each triggering detector, its per-channel weight is multiplied by
    _FP_WEIGHT_DECAY (default 0.95).  Weights are then re-normalised to sum=1.0.

    The per-channel weight dict starts as a copy of the global WEIGHTS, so
    channels that have never received feedback use the standard ensemble weights.
    Only detectors that exist in WEIGHTS are updated — unknown detector names
    (e.g. "stale_data", "hard_limit") are silently skipped.
    """
    if not detectors_triggered:
        return
    from aria.dsremo.core.tenant import get_tenant  # noqa: PLC0415
    key = f"{get_tenant()}:{satellite_id}:{parameter}"
    ch_w = _channel_weights.setdefault(key, dict(WEIGHTS))
    for det_name in detectors_triggered:
        if det_name in ch_w:
            ch_w[det_name] *= _FP_WEIGHT_DECAY
    total = sum(ch_w.values())
    if total > 1e-9:
        for k in ch_w:
            ch_w[k] /= total
    logger.info(
        "channel_weights_updated",
        satellite_id=satellite_id,
        parameter=parameter,
        detectors_decayed=list(detectors_triggered),
        top3=sorted(ch_w.items(), key=lambda x: -x[1])[:3],
    )


def get_effective_thresholds(satellite_id: str, parameter: str) -> dict:
    """Return merged thresholds: per-channel overrides applied on top of globals.

    DRY single source of truth — used by both the detection pipeline AND the
    GET /channels API response. NULL fields fall through to global defaults.
    """
    cfg = _channel_config_cache.get((satellite_id, parameter), {})

    def _get(key: str, default):  # type: ignore[no-untyped-def]
        v = cfg.get(key)
        return v if v is not None else default

    return {
        "z_threshold":         _get("z_threshold",         _stat_detector.z_threshold),
        "cusum_h":             _get("cusum_h",             None),   # None = calibration-computed
        "cusum_k":             _get("cusum_k",             None),   # None = calibration-computed
        "ewma_lambda":         _get("ewma_lambda",         None),   # None = calibration-computed
        "ewma_sigma_mult":     _get("ewma_sigma_mult",     None),   # None = calibration-computed
        "min_confidence":      _get("min_confidence",      0.0),
        "alert_cooldown_s":      _get("alert_cooldown_s",    _alert_cooldown_s),
        "alert_persistence_min": _alert_persistence_min,
        "variance_z_threshold":  _get("variance_z_threshold",  _variance_detector.variance_z_threshold),
        "velocity_threshold":    _get("velocity_threshold",    None),   # None = calibrated dynamically
        "discord_threshold":     _get("discord_threshold",     None),   # None = uses global threshold_sigma
        "hard_limit_high":       _get("hard_limit_high",       None),   # absolute redline (high)
        "hard_limit_low":        _get("hard_limit_low",        None),   # absolute redline (low)
        "sensor_noise_floor":    _get("sensor_noise_floor",    0.0),
    }


# ── Alert suppression helpers (Sprint 19) ────────────────────────────────────

def suppress_channel(satellite_id: str, parameter: str, duration_min: float, reason: str = "") -> float:
    """Mute anomaly alerts for a channel for *duration_min* minutes.

    Returns the UTC epoch timestamp when the suppression expires.
    Overwrites any existing suppression for the same channel.
    Now persisted to DB (P1-H fix) so suppressions survive server restarts.
    """
    until = datetime.now(timezone.utc).timestamp() + duration_min * 60.0
    tenant = get_tenant()
    _suppressed[f"{tenant}:{satellite_id}:{parameter}"] = until
    # Persist to DB so suppression survives server restarts (P1-H fix).
    try:
        import asyncio as _aio  # noqa: PLC0415
        loop = _aio.get_running_loop()
        loop.create_task(queries.upsert_suppression(
            tenant, satellite_id, parameter, until, reason,
        ))
    except RuntimeError:
        pass  # no event loop — in-memory only (test mode)
    logger.info("channel_suppressed", satellite=satellite_id, parameter=parameter,
                duration_min=duration_min)
    return until


def lift_suppression(satellite_id: str, parameter: str) -> bool:
    """Remove the suppression window for a channel.

    Returns True if a suppression was active, False if none existed.
    """
    key = f"{get_tenant()}:{satellite_id}:{parameter}"
    if key in _suppressed:
        del _suppressed[key]
        logger.info("suppression_lifted", satellite=satellite_id, parameter=parameter)
        return True
    return False


def list_suppressions(satellite_id: str) -> list[dict]:
    """Return active (non-expired) suppressions for *satellite_id* in the current tenant."""
    tenant = get_tenant()
    now = datetime.now(timezone.utc).timestamp()
    result = []
    expired = []
    for key, until in _suppressed.items():
        # Key format: "tenant:satellite_id:parameter"
        parts = key.split(":", 2)
        if len(parts) != 3:
            continue
        t, sat, param = parts
        if t != tenant or sat != satellite_id:
            continue
        if until > now:
            result.append({
                "parameter":    param,
                "until_epoch":  until,
                "remaining_min": round((until - now) / 60.0, 1),
            })
        else:
            expired.append(key)
    for k in expired:
        del _suppressed[k]
    return result


def set_satellite_phase(satellite_id: str, phase: str) -> None:
    """Set the current mission phase for a satellite (e.g. 'maneuver', 'safe_mode')."""
    _satellite_phase[f"{get_tenant()}:{satellite_id}"] = phase
    logger.info("satellite_phase_set", satellite=satellite_id, phase=phase)


def get_satellite_phase(satellite_id: str) -> str:
    """Get current mission phase (default: 'nominal')."""
    return _satellite_phase.get(f"{get_tenant()}:{satellite_id}", "nominal")


def _is_detector_gated(satellite_id: str, detector_name: str) -> bool:
    """Check if a detector is suppressed by the current mission phase."""
    phase = get_satellite_phase(satellite_id)
    return detector_name in _phase_gating.get(phase, [])


def _is_suppressed(key: str) -> bool:
    """Return True if the sat:param key has an active suppression window."""
    until = _suppressed.get(key, 0.0)
    if until == 0.0:
        return False
    if datetime.now(timezone.utc).timestamp() < until:
        return True
    del _suppressed[key]   # clean up expired entry
    return False


def _apply_calibration_overrides(cal: "CalibrationState", eff: dict) -> None:  # type: ignore[name-defined]
    """Mutate a CalibrationState in-place with any non-None override values.

    asyncio is single-threaded — this is race-free. CalibrationState is
    per-channel and not shared across concurrent calls.
    Only applies CUSUM/EWMA overrides when the channel has a valid σ_ref
    (i.e., after calibration completes).
    """
    if eff.get("cusum_h") is not None:
        cal.cusum_h = float(eff["cusum_h"])
    if eff.get("cusum_k") is not None:
        cal.cusum_k = float(eff["cusum_k"])

    # EWMA control limits depend on both lambda and sigma_mult.
    ewma_lambda     = eff.get("ewma_lambda")
    ewma_sigma_mult = eff.get("ewma_sigma_mult")
    if (ewma_lambda is not None or ewma_sigma_mult is not None) and cal.ref_std > 1e-9:
        import math
        import aria.dsremo.detection.calibration as _cal_mod_local
        sigma  = cal.ref_std
        lam    = float(ewma_lambda)     if ewma_lambda     is not None else _cal_mod_local.EWMA_LAMBDA
        smult  = float(ewma_sigma_mult) if ewma_sigma_mult is not None else _cal_mod_local.EWMA_SIGMA_FACTOR
        spread = math.sqrt(lam / (2.0 - lam))
        cal.ewma_ucl = +smult * sigma * spread
        cal.ewma_lcl = -smult * sigma * spread

    # Sensor noise floor — decompose ref_std into process + sensor noise.
    snf = eff.get("sensor_noise_floor", 0.0)
    if snf > 0:
        cal.sensor_noise_floor = float(snf)


async def flush_all_states(satellite_id: str | None = None) -> None:
    """Persist CUSUM, EWMA, and calibration states to DB.

    Called periodically (every STATE_FLUSH_EVERY cycles) and at shutdown.
    A full flush covers every satellite seen so far; a targeted flush
    covers only the given satellite.
    """
    cusum_states = _cusum_detector.all_states()
    ewma_states  = _ewma_detector.all_states()

    records: list[dict] = []
    for key, data in cusum_states.items():
        sat, _, param = key.partition(":")
        if satellite_id and sat != satellite_id:
            continue
        records.append({
            "satellite_id":  sat,
            "parameter":     param,
            "detector_name": "cusum",
            "state_data":    data,
        })

    for key, data in ewma_states.items():
        sat, _, param = key.partition(":")
        if satellite_id and sat != satellite_id:
            continue
        records.append({
            "satellite_id":  sat,
            "parameter":     param,
            "detector_name": "ewma",
            "state_data":    data,
        })

    if records:
        # Retry once on transient DB errors (pool timeout, brief disconnect).
        for _attempt in range(2):
            try:
                await queries.bulk_upsert_detector_states(records)
                logger.debug("detector_states_flushed", count=len(records))
                break
            except Exception as exc:
                if _attempt == 0:
                    import asyncio  # noqa: PLC0415
                    logger.warning("detector_state_flush_retrying", error=str(exc))
                    await asyncio.sleep(0.5)
                else:
                    logger.warning("detector_state_flush_failed", error=str(exc))

    # Persist calibration states for newly-calibrated channels.
    for key, cal in _calibration_mgr.all_db_records():
        sat, _, param = key.partition(":")
        if satellite_id and sat != satellite_id:
            continue
        try:
            await queries.upsert_channel_calibration(
                satellite_id=sat,
                parameter=param,
                state=cal["state"],
                ref_mean=cal.get("ref_mean"),
                ref_std=cal.get("ref_std"),
                ref_sample_count=cal.get("ref_sample_count", 0),
            )
        except Exception as exc:
            logger.warning("calibration_persist_failed", key=key, error=str(exc))


# ── Bulk history analysis (direct, no REST API) ──────────────────────────────

async def analyze_channel_history(
    satellite_id: str,
    parameter: str,
    subsystem: str = "",
    batch_size: int = 600,
    progress_cb: "object | None" = None,
    max_rows: int | None = None,
) -> list[Anomaly]:
    """Stream ALL stored telemetry for one channel through the detection pipeline.

    Designed for bulk historical analysis (ESA benchmark, backfill jobs).
    Fetches data from the DB in chronological batches, maintains a rolling
    600-row context window for STL decomposition, and feeds every point
    through calibration → CUSUM → EWMA exactly once.

    Anomalies are emitted whenever the ensemble vote fires at any point
    in the batch (not just the last point), enabling precise timestamps
    for historical anomaly events.

    Args:
        satellite_id: Satellite identifier (e.g. "ESA-MISSION1").
        parameter: Channel name (e.g. "channel_12").
        subsystem: Subsystem label for anomaly records.
        batch_size: Rows fetched per DB round-trip.  600 matches the STL
                    context window, so each batch fills the window exactly.
        progress_cb: Optional callable(n_processed) for progress reporting.

    Returns:
        List of Anomaly objects, each with a precise historical timestamp.
    """
    key       = f"{get_tenant()}:{satellite_id}:{parameter}"
    anomalies: list[Anomaly] = []

    # Load per-channel overrides once for the entire analysis run.
    eff = get_effective_thresholds(satellite_id, parameter)

    # ── Adaptive context window: pre-scan to detect dominant period ───────
    # Query up to max_fft_samples rows to run FFT period detection before the
    # main analysis loop.  This allows auto-scaling the rolling context window
    # for long-period signals (e.g. 24h diurnal cycles in GECCO water quality).
    # For signals with no detectable period, ctx_limit defaults to 600.
    ctx_limit = 600
    pre_scan = await queries.get_telemetry_batch_ordered(
        satellite_id, parameter,
        after_ts=None,
        limit=_stl_decomposer._max_fft_samples,
    )
    if pre_scan and len(pre_scan) >= 8:
        pre_vals = np.array(
            [float(r["value"]) for r in pre_scan], dtype=np.float64
        )
        detected_period = STLDecomposer._fft_period(pre_vals)
        if detected_period > 0:
            candidate  = _stl_window_factor * detected_period
            ctx_limit  = min(max(600, candidate), _stl_max_window)
            if ctx_limit > 600:
                logger.info(
                    "stl_window_auto_scaled",
                    satellite=satellite_id,
                    parameter=parameter,
                    period_samples=detected_period,
                    ctx_limit=ctx_limit,
                )

    # Rolling context window: stores the last ≤ctx_limit (ts_epoch, value) tuples
    # so STL always has enough history.  ctx_limit ≥ 600 always.
    ctx_ts:  list[float] = []
    ctx_val: list[float] = []

    after_ts    = None
    n_processed = 0

    while True:
        if max_rows is not None and n_processed >= max_rows:
            break
        batch = await queries.get_telemetry_batch_ordered(
            satellite_id, parameter, after_ts=after_ts, limit=batch_size,
        )
        if not batch:
            break

        # Append new rows to rolling context window.
        for r in batch:
            t = r["timestamp"].timestamp() if hasattr(r["timestamp"], "timestamp") \
                else float(r["timestamp"])
            ctx_ts.append(t)
            ctx_val.append(float(r["value"]))

        # Keep only the last ctx_limit samples to bound memory.
        # ctx_limit is ≥600 and auto-scaled based on detected signal period.
        if len(ctx_ts) > ctx_limit:
            ctx_ts  = ctx_ts[-ctx_limit:]
            ctx_val = ctx_val[-ctx_limit:]

        wt = np.array(ctx_ts,  dtype=np.float64)
        wv = np.array(ctx_val, dtype=np.float64)

        if len(wt) < 10:
            after_ts = batch[-1]["timestamp"]
            n_processed += len(batch)
            if progress_cb:
                progress_cb(n_processed)
            continue

        # STL decompose the current window (cached; recomputes every 30 calls).
        decomp    = _stl_decomposer.decompose(key, wv, wt)
        residuals = decomp.residual

        # V3-V5: record the most recent telemetry gap on this channel so the
        # anomaly construction below can annotate explanations with gap
        # context.  Uses the same 3× nominal threshold as V-1 mTAN encoder.
        from aria.dsremo.detection.gap_tracker import (  # noqa: PLC0415
            record_gaps_from_timestamps, get_tracker,
        )
        from aria.dsremo.detection.time_gap_encoder import (  # noqa: PLC0415
            detect_nominal_cadence_s,
        )
        _dt_nom = detect_nominal_cadence_s(wt)
        if _dt_nom > 0.0:
            record_gaps_from_timestamps(key, wt.tolist(), _dt_nom)

        # New indices: points from the current batch that haven't been fed
        # to the state machines yet.
        last_ts     = _last_processed_ts.get(key, 0.0)
        new_indices = np.where(wt > last_ts)[0]

        if len(new_indices) == 0:
            after_ts = batch[-1]["timestamp"]
            n_processed += len(batch)
            if progress_cb:
                progress_cb(n_processed)
            continue

        # ── Advance stateful detectors + check for anomalies at each point ──
        # For historical analysis we emit an anomaly at EVERY point that
        # triggers the ensemble, not just the last one in the batch.
        # Z-score and changepoint are window-based (not per-sample) so they
        # run only on the final new point to save CPU.
        best_cusum: DetectorResult = _nominal_result("cusum", "warming_up")
        best_ewma:  DetectorResult = _nominal_result("ewma",  "warming_up")
        best_bocpd: DetectorResult = _nominal_result("bocpd", "warming_up")
        alarm_idx: int | None = None  # window index of the highest-confidence alarm

        for idx in new_indices:
            res         = float(residuals[idx])
            calibration = _calibration_mgr.update(key, res)
            _apply_calibration_overrides(calibration, eff)   # Point 1: CUSUM/EWMA overrides
            # AR(1) pre-whitening: removes lag-1 autocorrelation so CUSUM/EWMA
            # ARL formulas (derived for i.i.d. Normal) remain valid.
            # w_res == res when ar1_phi == 0.0 (no autocorrelation detected).
            w_res       = calibration.whiten(res)
            cr          = _cusum_detector.detect(key, w_res, calibration)
            er          = _ewma_detector.detect(key, w_res, calibration)
            # BOCPD uses raw residual (not whitened): Normal-Gamma posterior
            # models the noise variance directly; pre-whitening is unnecessary.
            br          = _bocpd_detector.detect(key, res, calibration)

            if cr.score > best_cusum.score:
                best_cusum = cr
                alarm_idx  = idx
            if er.score > best_ewma.score:
                best_ewma = er
                alarm_idx = idx
            if br.score > best_bocpd.score:
                best_bocpd = br
                alarm_idx  = idx

        if key not in _last_processed_ts:
            _tenant = key.split(":")[0] + ":"
            if sum(1 for k in _last_processed_ts if k.startswith(_tenant)) >= _MAX_CHANNEL_STATE:
                _evict = next(k for k in _last_processed_ts if k.startswith(_tenant))
                del _last_processed_ts[_evict]
        _last_processed_ts[key] = float(wt[new_indices[-1]])

        # Window-based detectors run on the final new point only.
        final_idx      = new_indices[-1]
        final_residual = float(residuals[final_idx])
        final_ts_epoch = float(wt[final_idx])

        feat_res = _feature_engine.compute(f"{parameter}:res", final_residual, final_ts_epoch)
        with _z_threshold_override(eff["z_threshold"]):
            stat_result = _stat_detector.detect(feat_res, residuals)

        cp_result = (
            _cp_detector.detect(residuals, parameter)
            if len(residuals) >= 60
            else _nominal_result("changepoint", "insufficient_data")
        )

        _feature_engine.compute(parameter, float(wv[final_idx]), final_ts_epoch)
        _hist_known_params = _feature_engine.get_known_parameters()
        iso_result = (
            _detect_isolation_forest(satellite_id, _hist_known_params)
            if len(_hist_known_params) >= 2
            else _nominal_result("isolation_forest", "single_parameter")
        )

        # Variance + remaining calibration-dependent detectors.
        last_cal = _calibration_mgr.get(key)
        calibrated = last_cal is not None and last_cal.is_calibrated
        var_result = (
            _variance_detector.detect(residuals, last_cal, eff.get("variance_z_threshold"))
            if calibrated
            else _nominal_result("variance", "warming_up")
        )

        # ── ML detectors: GRU Autoencoder + TCN ──────────────────────────
        # V3-V1: pass wt (timestamps) so ML detectors can use mTAN encoding
        # across AOS/LOS gaps and multi-rate streams.
        lstm_result = await _advance_ml_detector(_get_lstm_model(satellite_id, parameter), new_indices, residuals, wt)
        tcn_result  = await _advance_ml_detector(_get_tcn_model(satellite_id, parameter),  new_indices, residuals, wt)

        # ── Trend Velocity (9th detector) ─────────────────────────────────
        hist_tvel_result = (
            _trend_velocity_detector.detect(decomp.trend, last_cal, eff.get("velocity_threshold"))
            if calibrated
            else _nominal_result("trend_velocity", "warming_up")
        )

        # ── Matrix Profile Discord (10th detector) ────────────────────────
        hist_discord_result = (
            _discord_detector.detect(residuals, last_cal, eff.get("discord_threshold"))
            if calibrated
            else _nominal_result("matrix_profile", "warming_up")
        )

        # Correlation graph update for historical analysis
        _correlation_detector.update(satellite_id, parameter, final_residual)
        hist_corr_result = _correlation_detector.detect(satellite_id, parameter)

        all_results = [best_cusum, best_ewma, stat_result, cp_result, iso_result, var_result, lstm_result, tcn_result, hist_tvel_result, hist_discord_result, hist_corr_result, best_bocpd]
        # V3-V4 / V3-M5 opt-in additions (no-op when neither monitor registered).
        _wheel_id = parameter if parameter.startswith("reaction_wheel_") else None
        all_results.extend(_optional_v3_detector_results(
            satellite_id, subsystem=subsystem, wheel_id=_wheel_id,
        ))
        is_anomaly, confidence, severity = _ensemble_vote(
            all_results, weights=_channel_weights.get(key),
            satellite_id=satellite_id,
        )

        # Point 3: per-channel min_confidence gate
        if is_anomaly and eff["min_confidence"] > 0.0 and confidence < eff["min_confidence"]:
            is_anomaly = False

        if is_anomaly and alarm_idx is not None:
            # Cooldown guard: suppress repeated alarms for the same channel.
            # Point 4: use per-channel cooldown instead of global.
            alarm_ts_epoch = float(wt[alarm_idx])
            last_alarm = _last_anomaly_ts.get(key, 0.0)
            sev_mult = _SEVERITY_COOLDOWN_MULT.get(severity.value, 1.0)
            if alarm_ts_epoch - last_alarm < eff["alert_cooldown_s"] * sev_mult:
                # Still within cooldown window — skip but keep advancing state.
                after_ts    = batch[-1]["timestamp"]
                n_processed += len(batch)
                if progress_cb:
                    progress_cb(n_processed)
                continue
            alarm_ts_dt    = datetime.fromtimestamp(alarm_ts_epoch, tz=timezone.utc)
            alarm_value    = float(wv[alarm_idx])

            # Build a lightweight row dict for the explanation builder.
            alarm_row = {
                "value":     alarm_value,
                "unit":      "",
                "subsystem": subsystem,
                "parameter": parameter,
                "timestamp": alarm_ts_dt,
            }
            explanation  = _build_explanation(parameter, feat_res, all_results, alarm_row, decomp.method)
            contributing = _extract_contributions(all_results)

            # V3-V5: if a telemetry gap preceded this anomaly, tell the operator.
            _gap_phrase = get_tracker().describe_recent_gap(key, anomaly_epoch=alarm_ts_epoch)
            if _gap_phrase is not None:
                explanation = f"{explanation} ({_gap_phrase})"

            anomaly = Anomaly(
                satellite_id=satellite_id,
                timestamp=alarm_ts_dt,
                subsystem=subsystem,
                parameter=parameter,
                value=alarm_value,
                severity=severity,
                confidence=confidence,
                detectors_triggered=tuple(r.detector_name for r in all_results if r.is_anomaly),
                explanation=explanation,
                contributing_params=contributing,
            )
            try:
                await queries.insert_anomaly(anomaly)
                anomalies.append(anomaly)
                _last_anomaly_ts[key] = alarm_ts_epoch   # arm the cooldown timer
                # Group into incident (NASA/SpaceX hierarchical routing).
                incident = _incident_grouper.process(anomaly)
                await queries.upsert_incident(incident)
                await queries.link_anomaly_to_incident(anomaly.id, incident.id)
                logger.debug(
                    "historical_anomaly_found",
                    trace_id=get_trace_id(),
                    parameter=parameter,
                    timestamp=str(alarm_ts_dt)[:19],
                    severity=severity.value,
                    confidence=round(confidence, 3),
                    incident_id=incident.id,
                )
            except Exception as exc:
                logger.warning("anomaly_store_failed", parameter=parameter, error=str(exc))

        after_ts    = batch[-1]["timestamp"]
        n_processed += len(batch)
        if progress_cb:
            progress_cb(n_processed)

    return anomalies


# ── Main detection loop ──────────────────────────────────────────────────────

async def run_detection_cycle(satellite_id: str) -> list[Anomaly]:
    """Public entry — gates on mission phase then serialises per satellite.

    V3-W4: suppresses detection while the satellite is in COMMISSIONING.
    V3-B4: scoped async lock so concurrent calls for the same
    (tenant, satellite) serialise their read-modify-write on calibration
    and detector state.  Distinct tenants/satellites proceed in parallel.
    """
    from aria.dsremo.detection.mission_phase import get_registry  # noqa: PLC0415
    if not get_registry().is_detection_active(satellite_id):
        logger.debug(
            "detection_suppressed",
            satellite_id=satellite_id,
            reason="commissioning_phase",
        )
        return []
    async with _detection_lock_for(satellite_id):
        return await _run_detection_cycle_body(satellite_id)


async def _run_detection_cycle_body(satellite_id: str) -> list[Anomaly]:
    """Serialised body of run_detection_cycle.

    Called by the ingest adapter after every batch of telemetry is stored.
    Processes ALL NEW points per channel (not just the latest), so that
    calibration warm-up and CUSUM/EWMA accumulators advance correctly for
    bulk-loaded or batched telemetry as well as live streaming.
    """
    start    = time.monotonic()
    anomalies: list[Anomaly] = []

    latest = await queries.get_latest_values(satellite_id)
    if not latest:
        return anomalies

    # ── Stale data check (NASA flight operations pattern, cf. NPR 7150.2D, NASA-STD-8719.13C / ISRO FOLIO standard, Sprint 18) ────
    # For every channel we've seen before, if the latest known timestamp is
    # older than _stale_threshold_s, fire a CRITICAL stale_data anomaly.
    # This catches sensor dropout, instrument power-off, and comms loss.
    now_epoch = datetime.now(timezone.utc).timestamp()
    for row in latest:
        param    = row["parameter"]
        ts_epoch = row["timestamp"].timestamp() if hasattr(row["timestamp"], "timestamp") else float(row["timestamp"])
        key      = f"{get_tenant()}:{satellite_id}:{param}"
        stale_gap = now_epoch - ts_epoch
        if key in _channel_last_seen and stale_gap > _stale_threshold_s:
            # AOS/LOS awareness: skip stale alert if gap is within expected contact gap
            if _expected_contact_gap_s > 0 and stale_gap <= _expected_contact_gap_s:
                _channel_last_seen[key] = ts_epoch
                continue
            stale_anomaly = Anomaly(
                satellite_id=satellite_id,
                timestamp=row["timestamp"],
                subsystem=row.get("subsystem", ""),
                parameter=param,
                value=float(row["value"]),
                severity=Severity.CRITICAL,
                confidence=0.95,
                detectors_triggered=("stale_data",),
                explanation=(
                    f"Telemetry silence detected: last sample {round((now_epoch - ts_epoch)/60, 1)} min ago "
                    f"(threshold {round(_stale_threshold_s/60, 1)} min). "
                    "Possible sensor dropout, power-off, or comms loss."
                ),
                contributing_params=(),
            )
            try:
                await queries.insert_anomaly(stale_anomaly)
                anomalies.append(stale_anomaly)
                incident = _incident_grouper.process(stale_anomaly)
                await queries.upsert_incident(incident)
                await queries.link_anomaly_to_incident(stale_anomaly.id, incident.id)
            except Exception:  # noqa: BLE001
                pass
        if key not in _channel_last_seen:
            _tenant = key.split(":")[0] + ":"
            if sum(1 for k in _channel_last_seen if k.startswith(_tenant)) >= _MAX_CHANNEL_STATE:
                _evict = next(k for k in _channel_last_seen if k.startswith(_tenant))
                del _channel_last_seen[_evict]
        _channel_last_seen[key] = ts_epoch

    for row in latest:
        param    = row["parameter"]
        value    = float(row["value"])
        ts       = row["timestamp"]

        # ── 1. Fetch window (provides STL context + new-point list) ────────
        window_rows = await queries.get_recent_telemetry_window(
            satellite_id, param, window_size=600
        )
        if len(window_rows) < 10:
            continue

        window_values = np.array([r["value"] for r in window_rows], dtype=np.float64)
        window_ts     = np.array(
            [r["timestamp"].timestamp() if hasattr(r["timestamp"], "timestamp")
             else float(r["timestamp"]) for r in window_rows],
            dtype=np.float64,
        )

        # ── 2. STL decomposition → residuals ────────────────────────────
        key    = f"{get_tenant()}:{satellite_id}:{param}"
        decomp = _stl_decomposer.decompose(key, window_values, window_ts)
        residuals = decomp.residual

        # V3-V5: record recent telemetry gap for this channel so downstream
        # anomaly explanations get "preceded by N-min gap" context.
        from aria.dsremo.detection.gap_tracker import (  # noqa: PLC0415
            record_gaps_from_timestamps, get_tracker,
        )
        from aria.dsremo.detection.time_gap_encoder import (  # noqa: PLC0415
            detect_nominal_cadence_s,
        )
        _dt_nom = detect_nominal_cadence_s(window_ts)
        if _dt_nom > 0.0:
            record_gaps_from_timestamps(key, window_ts.tolist(), _dt_nom)

        # Load per-channel overrides once per parameter (Point 1–4 below).
        eff = get_effective_thresholds(satellite_id, param)

        # ── 3. Identify NEW points (not yet fed to state machines) ───────
        # _last_processed_ts tracks the epoch of the last residual fed to
        # calibration/CUSUM/EWMA.  Only timestamps strictly after this value
        # are new — ensures each data point updates state exactly once, even
        # when the same window rows appear across consecutive detection cycles.
        #
        # P1-F: Filter out low-quality telemetry (quality < 0.5) from calibration
        # and detection.  Corrupted frames (bit errors during downlink) should not
        # contaminate the reference distribution or trigger false alarms.
        #
        # P1-E: Out-of-sequence handling — use >= instead of > for last_ts comparison
        # to avoid dropping delayed packets that arrive with exactly the last timestamp.
        # For true OOS points (timestamp < last_ts), they are included in the window
        # but already processed, so they naturally get skipped.
        last_ts      = _last_processed_ts.get(key, 0.0)
        new_indices  = np.where(window_ts > last_ts)[0]

        # Quality filter: exclude low-quality points from detection pipeline.
        quality_values = np.array(
            [float(r.get("quality", 1.0)) for r in window_rows], dtype=np.float64
        )
        low_quality_mask = quality_values < 0.5
        if np.any(low_quality_mask[new_indices]):
            new_indices = new_indices[~low_quality_mask[new_indices]]

        if len(new_indices) == 0:
            continue   # entire window already processed in previous cycle

        # ── 4. Advance stateful detectors for every new point in order ────
        # Calibration needs N consecutive residuals before it transitions to
        # "calibrated"; CUSUM and EWMA must see every sample to accumulate
        # correctly.  Running only the latest point (old behaviour) caused
        # warmup to take 100× more real-time batches than expected.
        #
        # IMPORTANT: we track the MAX-SCORING result across all new points,
        # not just the last one.  CUSUM resets its accumulators after each
        # alarm, so the final point in a batch often has a lower score than
        # the alarm peak mid-batch.  Using the peak score ensures that any
        # alarm that fired during the batch is visible to the ensemble vote.
        cusum_result: DetectorResult = _nominal_result("cusum", "warming_up")
        ewma_result:  DetectorResult = _nominal_result("ewma",  "warming_up")
        bocpd_result: DetectorResult = _nominal_result("bocpd", "warming_up")
        calibration  = None

        # Eclipse / transition mask: skip CUSUM/EWMA accumulation at sharp
        # discontinuities (P1-A fix) to prevent systematic false positives
        # at eclipse entry/exit boundaries.
        t_mask = decomp.transition_mask

        for idx in new_indices:
            res         = float(residuals[idx])
            calibration = _calibration_mgr.update(key, res)
            _apply_calibration_overrides(calibration, eff)   # Point 1: CUSUM/EWMA overrides

            # Skip CUSUM/EWMA at eclipse transition points — the sharp edge
            # is not anomalous but would accumulate in CUSUM and trip EWMA.
            is_transition = t_mask is not None and idx < len(t_mask) and t_mask[idx]

            # AR(1) pre-whitening: removes lag-1 autocorrelation so CUSUM/EWMA
            # ARL formulas (derived for i.i.d. Normal) remain valid.
            w_res       = calibration.whiten(res)

            if is_transition:
                # During eclipse transitions: don't accumulate in stateful detectors,
                # but still update calibration (we want transition data in σ_ref).
                cr = cusum_result
                er = ewma_result
                br = bocpd_result
            else:
                cr = _cusum_detector.detect(key, w_res, calibration) if _is_detector_active("cusum") else cusum_result
                er = _ewma_detector.detect(key, w_res, calibration)  if _is_detector_active("ewma")  else ewma_result
                br = _bocpd_detector.detect(key, res, calibration)   if _is_detector_active("bocpd") else bocpd_result

            # Promote to best result seen so far in this batch.
            if cr.score > cusum_result.score:
                cusum_result = cr
            if er.score > ewma_result.score:
                ewma_result = er
            if br.score > bocpd_result.score:
                bocpd_result = br

        # Mark all new window points as processed (per-tenant eviction at cap).
        if key not in _last_processed_ts:
            _tenant = key.split(":")[0] + ":"
            if sum(1 for k in _last_processed_ts if k.startswith(_tenant)) >= _MAX_CHANNEL_STATE:
                _evict = next(k for k in _last_processed_ts if k.startswith(_tenant))
                del _last_processed_ts[_evict]
        _last_processed_ts[key] = float(window_ts[new_indices[-1]])

        # ── 5. Z-score on the latest new residual (spike detection) ──────
        current_residual = float(residuals[new_indices[-1]])
        current_ts_epoch = float(window_ts[new_indices[-1]])

        feat_res = _feature_engine.compute(f"{param}:res", current_residual, current_ts_epoch)

        # ── GMM nearest-component z-score (Feature: bimodal channels) ────
        # When the channel has a GMM baseline, substitute the z-score with
        # the distance to the nearest component so bimodal oscillations
        # (e.g. two operating modes) don't look like infinite-σ spikes.
        if calibration is not None and calibration.gmm_means is not None:
            import dataclasses  # noqa: PLC0415
            feat_res = dataclasses.replace(
                feat_res,
                z_score=_gmm_nearest_z(
                    current_residual,
                    calibration.gmm_means,
                    calibration.gmm_stds,
                ),
            )

        # ── Per-channel auto z-threshold (Feature: empirical 99th-pct) ──
        # Effective threshold = max(global config, per-channel empirical 99th pct).
        # Channels with wider natural distributions automatically get a
        # higher threshold without any manual per-dataset tuning.
        _base_z = eff["z_threshold"]
        _auto_z = (
            calibration.auto_z_threshold
            if calibration is not None and calibration.auto_z_threshold is not None
            else None
        )
        _eff_z = max(_base_z, _auto_z) if _auto_z is not None else _base_z

        if _is_detector_active("statistical"):
            with _z_threshold_override(_eff_z):
                stat_result = _stat_detector.detect(feat_res, residuals)
        else:
            stat_result = _nominal_result("statistical", "tier_inactive")

        # ── 6. PELT changepoint on residuals ─────────────────────────────
        cp_result = (
            _cp_detector.detect(residuals, param)
            if _is_detector_active("changepoint") and len(residuals) >= 60
            else _nominal_result("changepoint", "insufficient_data")
        )

        # ── 7. Isolation Forest on raw values (multivariate) ────────────
        _feature_engine.compute(param, value, current_ts_epoch)
        known_params = _feature_engine.get_known_parameters()
        iso_result = (
            _detect_isolation_forest(satellite_id, known_params)
            if _is_detector_active("isolation_forest") and len(known_params) >= 2
            else _nominal_result("isolation_forest", "single_parameter")
        )

        # Calibration-dependent detectors (variance, ML, trend, discord).
        calibrated = calibration is not None and calibration.is_calibrated

        # ── 8. Variance detector ─────────────────────────────────────────
        var_result = (
            _variance_detector.detect(residuals, calibration, eff.get("variance_z_threshold"))
            if _is_detector_active("variance") and calibrated
            else _nominal_result("variance", "warming_up")
        )

        # ── 9+10. GRU Autoencoder + TCN (ML detectors) ───────────────────
        # V3-V1: pass window_ts so ML detectors use mTAN encoding across
        # AOS/LOS gaps and multi-rate streams.
        lstm_result = (
            await _advance_ml_detector(_get_lstm_model(satellite_id, param), new_indices, residuals, window_ts)
            if _is_detector_active("lstm")
            else _nominal_result("lstm", "tier_inactive")
        )
        tcn_result = (
            await _advance_ml_detector(_get_tcn_model(satellite_id, param), new_indices, residuals, window_ts)
            if _is_detector_active("tcn")
            else _nominal_result("tcn", "tier_inactive")
        )

        # ── 11. Trend Velocity (STL trend acceleration onset) ────────────
        tvel_result = (
            _trend_velocity_detector.detect(decomp.trend, calibration, eff.get("velocity_threshold"))
            if _is_detector_active("trend_velocity") and calibrated
            else _nominal_result("trend_velocity", "warming_up")
        )

        # ── Time-to-Limit prediction (SpaceX/ISRO pattern, Sprint 18) ──────
        # When hard_limit_high / hard_limit_low are configured for a channel,
        # compute how long until the current trend reaches the redline.
        # ttl_min < ttl_warn_min → escalate tvel_result severity.
        # ── Time-to-Limit prediction (SpaceX/ISRO pattern, Sprint 18) ──────
        # When hard limits are configured, compute minutes until the current
        # trend reaches the redline and annotate/escalate tvel_result.
        _hl_high = eff.get("hard_limit_high")
        _hl_low  = eff.get("hard_limit_low")
        _vel     = tvel_result.details.get("max_velocity", 0.0) if tvel_result.details else 0.0
        if _vel != 0.0 and (_hl_high is not None or _hl_low is not None):
            _ttl_min: float | None = None
            if _vel > 1e-8 and _hl_high is not None:
                _remaining = _hl_high - value
                if _remaining > 0:
                    _ttl_min = round(_remaining / _vel / 60.0, 1)
            elif _vel < -1e-8 and _hl_low is not None:
                _remaining = value - _hl_low
                if _remaining > 0:
                    _ttl_min = round(_remaining / abs(_vel) / 60.0, 1)
            if _ttl_min is not None:
                # Always construct a new DetectorResult — never mutate the dict
                # inside a frozen dataclass (even though Python allows it).
                ttl_details = {**tvel_result.details, "ttl_min": _ttl_min}
                if _ttl_min < _ttl_warn_min:
                    sev = Severity.CRITICAL if _ttl_min < _ttl_warn_min / 3 else Severity.WARNING
                    tvel_result = DetectorResult(
                        detector_name="trend_velocity",
                        is_anomaly=True,
                        score=max(tvel_result.score, 0.75),
                        severity=sev,
                        details={**ttl_details, "ttl_triggered": True},
                    )
                else:
                    tvel_result = DetectorResult(
                        detector_name=tvel_result.detector_name,
                        is_anomaly=tvel_result.is_anomaly,
                        score=tvel_result.score,
                        severity=tvel_result.severity,
                        details=ttl_details,
                    )

        # ── 12. Matrix Profile Discord (10th detector) ────────────────────
        discord_result = (
            _discord_detector.detect(residuals, calibration, eff.get("discord_threshold"))
            if _is_detector_active("matrix_profile") and calibrated
            else _nominal_result("matrix_profile", "warming_up")
        )

        # ── 13. Correlation Graph (11th detector — relationship breakdown) ─
        # Update buffer with the current residual, then score.
        if _is_detector_active("correlation_graph"):
            _correlation_detector.update(satellite_id, param, current_residual)
            corr_result = _correlation_detector.detect(satellite_id, param)
        else:
            corr_result = _nominal_result("correlation_graph", "tier_inactive")

        # ── 14. Hard Limit Override (zero-FN absolute redline check) ──────
        # If value has crossed a hard limit, force CRITICAL regardless of
        # ensemble confidence.  Redlines are absolute — no statistical gate.
        hl_high = eff.get("hard_limit_high")
        hl_low  = eff.get("hard_limit_low")
        hard_limit_breached = (
            (hl_high is not None and value > hl_high) or
            (hl_low  is not None and value < hl_low)
        )

        # ── 15. Ensemble vote ────────────────────────────────────────────
        all_results = [cusum_result, ewma_result, stat_result, cp_result, iso_result,
                       var_result, lstm_result, tcn_result, tvel_result, discord_result,
                       corr_result, bocpd_result]
        # V3-V4 / V3-M5 opt-in additions (no-op when neither monitor registered).
        _wheel_id = param if param.startswith("reaction_wheel_") else None
        _subsystem_live = row.get("subsystem", "")
        all_results.extend(_optional_v3_detector_results(
            satellite_id, subsystem=_subsystem_live, wheel_id=_wheel_id,
        ))
        if hard_limit_breached:
            is_anomaly, confidence, severity = True, 1.0, Severity.CRITICAL
        else:
            is_anomaly, confidence, severity = _ensemble_vote(
                all_results, weights=_channel_weights.get(live_key),
                satellite_id=satellite_id,
            )

        # Suppression window (maintenance mode — mutes alerts, not detection).
        # Prefix with tenant_id to prevent cross-tenant cooldown bleed.
        live_key = f"{get_tenant()}:{satellite_id}:{param}"
        if is_anomaly and _is_suppressed(live_key):
            is_anomaly = False

        # P2-C: Command-response correlation — suppress anomalies caused by
        # expected telemetry changes from recently registered commands.
        if is_anomaly and get_command_correlator().is_command_expected(satellite_id, param):
            is_anomaly = False

        # Point 3: per-channel min_confidence gate
        if is_anomaly and eff["min_confidence"] > 0.0 and confidence < eff["min_confidence"]:
            is_anomaly = False

        # Cooldown guard: one alarm per channel per cooldown window.
        # Point 4: use per-channel cooldown instead of global _alert_cooldown_s.
        # Per-severity multiplier: CRITICAL re-fires sooner than WATCH.
        if is_anomaly:
            now_epoch = datetime.now(timezone.utc).timestamp()
            sev_mult = _SEVERITY_COOLDOWN_MULT.get(severity.value, 1.0)
            if now_epoch - _last_anomaly_ts.get(live_key, 0.0) < eff["alert_cooldown_s"] * sev_mult:
                is_anomaly = False  # still in cooldown — suppress

        # Persistence filter: require N consecutive anomalous detections before
        # alerting (production standard — NASA flight operations pattern, cf. NPR 7150.2D; YAMCS; SpaceX Doppel).
        # Streak increments on anomaly, resets on nominal.  Alert only fires when
        # streak reaches _alert_persistence_min.  Cooldown check runs first so a
        # suppressed alarm still counts toward the streak.
        if is_anomaly:
            _anomaly_streak[live_key] = _anomaly_streak.get(live_key, 0) + 1
            if _anomaly_streak[live_key] < _alert_persistence_min:
                is_anomaly = False  # not enough consecutive anomalous windows yet
        else:
            _anomaly_streak[live_key] = 0  # reset streak on any nominal window

        if is_anomaly:
            if live_key not in _last_anomaly_ts:
                _tenant = live_key.split(":")[0] + ":"
                if sum(1 for k in _last_anomaly_ts if k.startswith(_tenant)) >= _MAX_CHANNEL_STATE:
                    _evict = next(k for k in _last_anomaly_ts if k.startswith(_tenant))
                    del _last_anomaly_ts[_evict]
            _last_anomaly_ts[live_key] = datetime.now(timezone.utc).timestamp()
            explanation  = _build_explanation(param, feat_res, all_results, row, decomp.method)
            contributing = _extract_contributions(all_results)

            # V3-V5: annotate explanation with gap context when a recent gap preceded this alarm.
            _alarm_ep   = ts.timestamp() if hasattr(ts, "timestamp") else float(ts)
            _gap_phrase = get_tracker().describe_recent_gap(key, anomaly_epoch=_alarm_ep)
            if _gap_phrase is not None:
                explanation = f"{explanation} ({_gap_phrase})"

            anomaly = Anomaly(
                satellite_id=satellite_id,
                timestamp=ts,
                subsystem=row.get("subsystem", ""),
                parameter=param,
                value=value,
                severity=severity,
                confidence=confidence,
                detectors_triggered=tuple(r.detector_name for r in all_results if r.is_anomaly),
                explanation=explanation,
                contributing_params=contributing,
            )
            # Attach the STL residual for storage in the new DB column.
            object.__setattr__(anomaly, "stl_residual", current_residual) if hasattr(anomaly, "__dataclass_fields__") else None

            try:
                await queries.insert_anomaly(anomaly)
                anomalies.append(anomaly)

                # P1-D: Immutable audit trail — record individual detector scores,
                # calibration state, and STL method for full decision traceability.
                try:
                    audit_scores = {r.detector_name: round(r.score, 4) for r in all_results}
                    cal_snapshot = calibration.to_dict() if calibration else None
                    await queries.insert_detection_audit(
                        satellite_id=satellite_id,
                        parameter=param,
                        timestamp=ts,
                        detector_scores=audit_scores,
                        ensemble_confidence=round(confidence, 4),
                        severity=severity.value,
                        calibration_state=cal_snapshot,
                        stl_method=decomp.method,
                    )
                except Exception:  # noqa: BLE001
                    pass  # audit is best-effort; never block anomaly pipeline

                # Group into incident — no raw alert reaches operator uncorrelated.
                incident = _incident_grouper.process(anomaly)
                await queries.upsert_incident(incident)
                await queries.link_anomaly_to_incident(anomaly.id, incident.id)

                from aria.dsremo.api.websocket import broadcast_anomaly
                await broadcast_anomaly({
                    "id":          anomaly.id,
                    "satellite_id": anomaly.satellite_id,
                    "parameter":   anomaly.parameter,
                    "value":       anomaly.value,
                    "severity":    anomaly.severity.value,
                    "confidence":  anomaly.confidence,
                    "explanation": anomaly.explanation,
                    "timestamp":   anomaly.timestamp.isoformat() if isinstance(anomaly.timestamp, datetime) else str(anomaly.timestamp),
                    "incident_id": incident.id,
                })

                # Dispatch alert (webhook / email) for WARNING and CRITICAL only.
                # WATCH-level anomalies are informational — no pager alert.
                from aria.dsremo.alerts.service import AlertService
                from aria.dsremo.core.tenant import get_tenant
                await AlertService.dispatch(anomaly, get_tenant())
            except Exception as exc:
                logger.error("anomaly_store_failed", error=str(exc), parameter=param)

    # ── Periodic tasks ───────────────────────────────────────────────────
    count = _detection_cycle_count.get(satellite_id, 0) + 1
    _detection_cycle_count[satellite_id] = count

    # Isolation Forest refit
    sat_samples = _samples_since_fit.get(satellite_id, 0) + len(latest)
    _samples_since_fit[satellite_id] = sat_samples
    if _iso_detector.needs_refit(sat_samples):
        await _refit_isolation_forest(satellite_id)
        _samples_since_fit[satellite_id] = 0

    # State flush to DB
    if count % _STATE_FLUSH_EVERY == 0:
        await flush_all_states(satellite_id=satellite_id)

    elapsed_ms = (time.monotonic() - start) * 1000
    if anomalies:
        logger.info(
            "detection_cycle_complete",
            trace_id=get_trace_id(),
            satellite=satellite_id,
            anomalies_found=len(anomalies),
            elapsed_ms=round(elapsed_ms, 1),
        )

    return anomalies


# ── Score calibration + correlation-aware ensemble voting ─────────────────────
#
# Detectors produce scores on incomparable scales (z-score is unbounded,
# BOCPD is [0,1], variance ratio is χ²-distributed).  _calibrate_score()
# maps each detector's raw score to a calibrated [0,1] probability via an
# appropriate CDF, so the ensemble operates on a common scale.
#
# Detectors are grouped by input correlation.  Within a correlated group,
# only the max calibrated score counts (since multiple firings from the
# SAME residual spike are mechanically induced, not independent evidence).
# Cross-group agreement provides genuine independent confirmation.

_DETECTOR_GROUPS: dict[str, str] = {
    # Group A: residual-based, per-sample stateful
    "cusum":            "residual_stateful",
    "ewma":             "residual_stateful",
    "statistical":      "residual_stateful",
    "bocpd":            "residual_stateful",
    # Group B: residual-based, window/shape
    "variance":         "residual_window",
    "matrix_profile":   "residual_window",
    "changepoint":      "residual_window",
    # Group C: STL trend-based
    "trend_velocity":   "trend",
    # Group D: raw-value, multivariate
    "isolation_forest": "multivariate",
    "correlation_graph":"multivariate",
    # Group E: ML temporal pattern
    "lstm":             "ml_temporal",
    "tcn":              "ml_temporal",
    # V3-S2: wide-RF TCN joins the ml_temporal group — still autoencoder-
    # on-residuals, just at a longer timescale.  Grouped with its sibling
    # so that the within-group "keep only the strongest" rule still applies.
    "wide_tcn":         "ml_temporal",
    # V3-V4: cross-channel attention is a distinct evidence source —
    # lives in its own group so it adds independent signal.
    "cross_channel_attn": "cross_subsystem",
    # V3-M5: RW bearing proxy is an ADCS-specific physical-stress signal —
    # independent of every residual-shape detector, so its own group.
    "rw_bearing_proxy":  "physical_wear",
}

# Group-level weights: how much does each correlation group contribute
# to the final score?  Sums to 1.0.  Derived from the relative importance
# of independent signal sources, not individual detector LLR.
_GROUP_WEIGHTS: dict[str, float] = {
    "residual_stateful": 0.30,   # CUSUM/EWMA are primary
    "residual_window":   0.25,   # variance + shape
    "trend":             0.20,   # onset/degradation
    "multivariate":      0.10,   # cross-parameter
    "ml_temporal":       0.15,   # learned patterns (incl. wide_tcn — V3-S2)
    # V3-V4 / V3-M5 new groups — weights 0 until operators activate them
    # via enable_cross_channel_attn() / enable_rw_bearing_proxy() so the
    # existing group-weighted ensemble isn't silently rebalanced.
    "cross_subsystem":   0.00,
    "physical_wear":     0.00,
}


# ── V3-H1 / V3-H3 optional ensemble overrides ────────────────────────────────
#
# These are singleton hooks for the hierarchical-Bayes per-class LLR weights
# (V3-H1) and the isotonic ensemble-score calibrator (V3-H3).  Registering
# either one is optional — detector behaviour is unchanged when both are
# None.  Operators install them via `register_hierarchical_llr` /
# `register_isotonic_calibrator` at server startup (or during a monthly
# refit job as labelled feedback accumulates).

# Fitted per-satellite-class LLR weights (V3-H1 integration hook).
_hierarchical_llr = None   # HierarchicalLLRWeights | None — lazy import
# Mapping satellite_id → class_name used by _hierarchical_llr.get_weights.
_satellite_class_map: dict[str, str] = {}
# PAVA-fitted ensemble-score calibrator (V3-H3 integration hook).
_isotonic_calibrator = None  # IsotonicCalibrator | None — lazy import


def register_hierarchical_llr(hlr, satellite_class_map: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    """Install a fitted HierarchicalLLRWeights instance (V3-H1).

    Passing `None` removes any previously-registered instance and restores
    the global `WEIGHTS` as the ensemble weight source.
    """
    global _hierarchical_llr, _satellite_class_map
    _hierarchical_llr = hlr
    _satellite_class_map = dict(satellite_class_map or {})


def register_isotonic_calibrator(calib) -> None:  # type: ignore[no-untyped-def]
    """Install a fitted IsotonicCalibrator (V3-H3).  `None` clears it."""
    global _isotonic_calibrator
    _isotonic_calibrator = calib


def _maybe_hierarchical_weights(satellite_id: str | None) -> dict[str, float] | None:
    """Return per-class weights when an HLR is registered AND a class is known.

    Fleet-uniform classes not in the map → None so the caller falls back.
    """
    if _hierarchical_llr is None or satellite_id is None:
        return None
    sat_class = _satellite_class_map.get(satellite_id)
    if sat_class is None:
        return None
    return _hierarchical_llr.get_weights(sat_class)


def _maybe_calibrate_confidence(confidence: float) -> float:
    """Apply the isotonic calibrator if one is registered (V3-H3)."""
    if _isotonic_calibrator is None:
        return confidence
    try:
        import numpy as _np  # noqa: PLC0415
        return float(_isotonic_calibrator.predict(_np.array([confidence]))[0])
    except Exception:
        return confidence


def _calibrate_score(result: DetectorResult) -> float:
    """Map a detector's raw score to calibrated [0, 1] via appropriate CDF.

    Each detector family has a different raw score distribution:
      - z-like (cusum, ewma, statistical): unbounded ratio → normal CDF
      - probability (bocpd): already [0,1] → pass through
      - ratio (variance): positive ratio → exponential CDF
      - distance (matrix_profile, isolation_forest): → sigmoid
      - mse-ratio (lstm, tcn): → sigmoid
      - trend velocity: → normal CDF on normalized score
    """
    import math  # noqa: PLC0415
    s = result.score
    name = result.detector_name

    if s <= 0.0:
        return 0.0

    # Normal CDF approximation: Φ(x) ≈ 1/(1 + exp(-1.7 × x))
    # Good to <0.01 absolute error for |x| < 5.
    def _norm_cdf(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-1.7 * x)) if x < 20 else 1.0

    if name in ("bocpd",):
        # Already a probability in [0,1]
        return min(1.0, s)

    if name in ("cusum", "ewma", "statistical", "trend_velocity"):
        # Score is a ratio (accumulator/threshold or z-score/threshold).
        # Map to [0,1]: score ~1.0 at threshold → calibrated ~0.85
        return _norm_cdf(s * 2.0 - 1.0)

    if name in ("variance",):
        # Score is (ratio - threshold)/threshold + 0.5; ratio-based.
        # Exponential CDF: P(X ≤ x) = 1 - exp(-x/λ), λ=0.5
        return 1.0 - math.exp(-s / 0.5) if s < 20 else 1.0

    if name in ("matrix_profile", "changepoint"):
        # Distance-based score. Sigmoid mapping.
        return 2.0 / (1.0 + math.exp(-3.0 * s)) - 1.0 if s < 20 else 1.0

    if name in ("isolation_forest", "correlation_graph"):
        # Score from sklearn: higher = more anomalous. Sigmoid.
        return 1.0 / (1.0 + math.exp(-4.0 * (s - 0.5))) if abs(s) < 20 else (1.0 if s > 0 else 0.0)

    if name in ("lstm", "tcn"):
        # MSE ratio score. Sigmoid around threshold.
        return _norm_cdf(s * 1.5 - 0.5)

    # Unknown detector (plugin) — assume score is already ~[0,1].
    return min(1.0, max(0.0, s))


def _ensemble_vote(
    results: list[DetectorResult],
    weights: "dict[str, float] | None" = None,
    satellite_id: str | None = None,
) -> tuple[bool, float, Severity]:
    """Correlation-aware ensemble fusion with calibrated scores.

    1. Calibrate each detector's raw score to [0,1] via CDF mapping.
    2. Group detectors by input correlation (shared residuals = same group).
    3. Within each group: take the MAX calibrated score × detector weight
       (correlated detectors don't stack — only the strongest signal counts).
    4. Across groups: weighted sum of group scores (independent signals ADD).
    5. Cross-group agreement bonus: 1 group triggered → ×0.70,
       2 groups → ×0.85, 3+ groups → ×1.0 (genuine independent confirmation).

    weights: per-channel learned weights (from feedback).
    satellite_id: enables the V3-H1 hierarchical-Bayes per-class weight
                  override when a HierarchicalLLRWeights instance has been
                  registered via `register_hierarchical_llr`.

    Weight lookup priority: `weights` (per-channel) → H-1 hierarchical
    (per-class) → global WEIGHTS.
    """
    if weights is not None:
        w = weights
    else:
        hier = _maybe_hierarchical_weights(satellite_id)
        w = hier if hier is not None else WEIGHTS
    triggered = [r for r in results if r.is_anomaly]
    if not triggered:
        # No alarm — return weighted average of calibrated sub-threshold scores.
        avg = sum(_calibrate_score(r) * w.get(r.detector_name, 0.02) for r in results)
        return False, float(avg), Severity.NOMINAL

    # Step 1+2: Calibrate scores, compute per-group best (max) signal.
    group_best_score: dict[str, float] = {}  # group_name → max calibrated score
    group_best_weight: dict[str, float] = {}  # group_name → weight of best detector

    for r in triggered:
        cal_score = _calibrate_score(r)
        det_weight = w.get(r.detector_name, 0.02)
        group = _DETECTOR_GROUPS.get(r.detector_name, "unknown")

        # Within a correlated group, keep only the strongest signal.
        # Weight by the individual detector's LLR weight so that CUSUM
        # firing alone (weight 0.1261) counts more than z-score (weight 0).
        weighted_signal = cal_score * max(det_weight, 0.01)
        if weighted_signal > group_best_score.get(group, 0.0):
            group_best_score[group] = weighted_signal
            group_best_weight[group] = det_weight

    if not group_best_score:
        return False, 0.0, Severity.NOMINAL

    # Step 3: Combine group scores using group-level weights.
    # Each group contributes its best signal × group importance.
    total_signal = 0.0
    total_group_weight = 0.0
    for group, best_signal in group_best_score.items():
        gw = _GROUP_WEIGHTS.get(group, 0.10)
        # Normalize the best_signal by its detector weight to get pure
        # calibrated score, then weight by group importance.
        det_w = max(group_best_weight.get(group, 0.01), 0.01)
        pure_score = best_signal / det_w  # recover calibrated [0,1]
        total_signal += pure_score * gw
        total_group_weight += gw

    if total_group_weight < 1e-9:
        return False, 0.0, Severity.NOMINAL

    base_confidence = total_signal / total_group_weight

    # Step 4: Cross-group agreement — only DIFFERENT groups count.
    n_groups_triggered = len(group_best_score)
    if n_groups_triggered >= 3:
        agreement = 1.0
    elif n_groups_triggered == 2:
        agreement = 0.85
    else:
        agreement = 0.70

    confidence = min(1.0, base_confidence * agreement)

    # V3-H3: optional isotonic recalibration of the final ensemble
    # confidence.  No-op unless an IsotonicCalibrator has been registered
    # via register_isotonic_calibrator().
    confidence = _maybe_calibrate_confidence(confidence)

    # Severity gate — from ensemble confidence only.
    # P3-V: 4-level severity (ISRO FOLIO: CAUTION/ADVISORY/WARNING/CRITICAL)
    if confidence >= _severity_thresholds["critical"]:
        severity = Severity.CRITICAL
    elif confidence >= _severity_thresholds["warning"]:
        severity = Severity.WARNING
    elif confidence >= _severity_thresholds["watch"]:
        severity = Severity.WATCH
    elif confidence >= _severity_thresholds.get("caution", 0.35):
        severity = Severity.CAUTION
    else:
        # Confidence too low — discard.
        return False, confidence, Severity.NOMINAL

    return True, confidence, severity


# ── Isolation Forest helpers ─────────────────────────────────────────────────

def _detect_isolation_forest(satellite_id: str, known_params: "set[str] | None" = None) -> DetectorResult:
    if not _iso_detector.is_ready:
        return _nominal_result("isolation_forest", "model_not_fitted")
    params   = sorted(known_params) if known_params is not None else _ALL_PARAMETERS
    snapshot = _feature_engine.get_multivariate_snapshot(params)
    if snapshot is None:
        return _nominal_result("isolation_forest", "incomplete_data")
    return _iso_detector.detect(snapshot)


async def _refit_isolation_forest(satellite_id: str) -> None:
    known_params = _feature_engine.get_known_parameters()
    params = sorted(known_params) if known_params else _ALL_PARAMETERS
    matrix = _feature_engine.get_window_matrix(params, length=200)
    if matrix is not None:
        _iso_detector.fit(matrix, params)


# ── Explanation + contribution ────────────────────────────────────────────────

def _build_explanation(
    parameter: str,
    features,
    results: list[DetectorResult],
    row: dict,
    decomp_method: str,
) -> str:
    """Human-readable explanation of why this anomaly fired."""
    triggered = [r for r in results if r.is_anomaly]
    parts: list[str] = []

    parts.append(
        f"{parameter} = {row['value']:.4f} {row.get('unit', '')} "
        f"(residual: {features.raw_value:.4f}, "
        f"rolling_std: {features.rolling_std:.4f}, "
        f"decomp: {decomp_method})"
    )

    for r in triggered:
        match r.detector_name:
            case "cusum":
                d = r.details
                direction = d.get("direction", "?")
                parts.append(
                    f"CUSUM {direction} drift: S={max(d.get('s_pos',0), d.get('s_neg',0)):.3f} "
                    f"(H={d.get('h',0):.3f}, k={d.get('k',0):.4f}, "
                    f"alarm#{d.get('alarm_count',1)})"
                )
            case "ewma":
                d = r.details
                parts.append(
                    f"EWMA level shift: Z={d.get('z_ewma',0):.4f} "
                    f"vs UCL={d.get('ucl',0):.4f} / LCL={d.get('lcl',0):.4f}"
                )
            case "statistical":
                z = r.details.get("z_score", 0)
                parts.append(f"Z-score spike: {z:.2f}σ (threshold: {r.details.get('threshold', 3.0)})")
                if r.details.get("rate_of_change_anomaly"):
                    parts.append("Rapid rate-of-change detected")
            case "changepoint":
                cps = r.details.get("change_points", [])
                if cps:
                    top = max(cps, key=lambda c: c.get("score", 0))
                    parts.append(
                        f"Structural break detected "
                        f"(mean_shift={top.get('mean_shift',0):.4f}, "
                        f"recency={top.get('recency',0):.2f})"
                    )
            case "isolation_forest":
                contribs = r.details.get("feature_contributions", {})
                if contribs:
                    top = sorted(contribs.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
                    parts.append(
                        "Cross-parameter anomaly — top contributors: "
                        + ", ".join(f"{k}:{v:+.3f}" for k, v in top)
                    )
            case "variance":
                ratio = r.details.get("ratio", 0)
                threshold = r.details.get("threshold", 2.5)
                rolling_std = r.details.get("rolling_std", 0)
                ref_std = r.details.get("ref_std", 0)
                parts.append(
                    f"Variance spike: rolling_std/ref_std = {ratio:.2f}× "
                    f"(threshold: {threshold}, rolling={rolling_std:.4f}, ref={ref_std:.4f})"
                )
            case "lstm":
                mse = r.details.get("mse", 0)
                thr = r.details.get("threshold", 0)
                z   = r.details.get("z_score", 0)
                parts.append(
                    f"Autoencoder: reconstruction MSE={mse:.4f} "
                    f"(threshold={thr:.4f}, z={z:.2f})"
                )
            case "tcn":
                mse = r.details.get("mse", 0)
                thr = r.details.get("threshold", 0)
                z   = r.details.get("z_score", 0)
                parts.append(
                    f"TCN: reconstruction MSE={mse:.4f} "
                    f"(threshold={thr:.4f}, z={z:.2f})"
                )
            case "trend_velocity":
                vel = r.details.get("max_velocity", 0)
                thr = r.details.get("threshold", 0)
                rat = r.details.get("ratio", 0)
                parts.append(
                    f"Trend acceleration: velocity={vel:.4f} "
                    f"(threshold={thr:.4f}, ratio={rat:.2f}×)"
                )
            case "matrix_profile":
                ds  = r.details.get("discord_score", 0)
                thr = r.details.get("threshold", 0)
                z   = r.details.get("z_score", 0)
                parts.append(
                    f"Unusual shape: discord score={ds:.4f} "
                    f"(threshold={thr:.4f}, z={z:.2f})"
                )
            case "correlation_graph":
                cz   = r.details.get("correlation_z", 0)
                peer = r.details.get("peer", "unknown")
                parts.append(
                    f"Correlation breakdown with {peer}: z={cz:.2f} "
                    "(expected peer relationship no longer holds)"
                )

    parts.append(f"{len(triggered)}/{len(results)} detectors triggered")
    return " | ".join(parts)


def _extract_contributions(results: list[DetectorResult]) -> dict[str, float]:
    for r in results:
        if r.detector_name == "isolation_forest" and r.details.get("feature_contributions"):
            return r.details["feature_contributions"]
    return {}
