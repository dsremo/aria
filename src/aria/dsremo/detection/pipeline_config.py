"""DetectionPipelineConfig — structured configuration for the detection pipeline.

P1-C partial fix: encapsulates all detection configuration in a typed dataclass
instead of scattered global variables.  This is the first step toward a full
DetectionPipeline class that owns all state (P1-C full fix).

Usage:
    config = DetectionPipelineConfig.from_settings(settings)
    init_detectors_from_config(config)  # still uses globals internally

For testing:
    config = DetectionPipelineConfig(
        z_score_threshold=4.0,
        cusum_h_factor=5.0,
        detection_tier="minimal",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DetectionPipelineConfig:
    """All configuration for the detection pipeline in one place."""

    # ── Statistical ──
    z_score_threshold: float = 3.5
    severe_z_threshold: float = 5.25  # z_score_threshold × 1.5

    # ── CUSUM ──
    cusum_k_factor: float = 0.5
    cusum_h_factor: float = 5.0
    cusum_recal_factor: float = 10.0

    # ── EWMA ──
    ewma_lambda: float = 0.2
    ewma_sigma_factor: float = 3.0

    # ── Calibration ──
    calibration_window: int = 100
    sigma_update_interval: int = 720
    sigma_update_threshold: float = 0.10
    gmm_enabled: bool = True
    auto_z_threshold_enabled: bool = True

    # ── BOCPD ──
    bocpd_hazard: float = 0.002
    bocpd_alarm_threshold: float = 0.3
    bocpd_max_run: int = 300

    # ── STL ──
    orbital_period_s: int = 5400
    stl_recompute_every: int = 30
    stl_max_fft_samples: int = 5000
    stl_window_factor: int = 3
    stl_max_window: int = 200000

    # ── Variance ──
    variance_z_threshold: float = 2.5
    variance_window: int = 30

    # ── Trend Velocity ──
    tvel_window: int = 20
    tvel_recent_points: int = 5
    tvel_threshold_sigma: float = 3.0

    # ── Discord ──
    matrix_profile_m: int = 20
    matrix_profile_buffer: int = 300
    matrix_profile_sigma: float = 3.0

    # ── Correlation Graph ──
    corr_graph_window: int = 60
    corr_graph_min_calibration: int = 100
    corr_graph_threshold_sigma: float = 3.0

    # ── ML ──
    lstm_seq_length: int = 30
    lstm_hidden_size: int = 32
    lstm_bottleneck_size: int = 8
    lstm_epochs: int = 30
    lstm_min_train_samples: int = 60
    lstm_retrain_interval: int = 500
    lstm_threshold_sigma: float = 3.0
    tcn_seq_length: int = 32
    tcn_n_channels: int = 16
    tcn_n_blocks: int = 4
    tcn_kernel_size: int = 3
    tcn_epochs: int = 40
    tcn_min_train_samples: int = 64
    tcn_retrain_interval: int = 500
    tcn_threshold_sigma: float = 3.0
    model_dir: str | None = None

    # ── Isolation Forest ──
    isolation_contamination: float = 0.001

    # ── Ensemble ──
    ensemble_weights: dict[str, float] = field(default_factory=dict)
    severity_thresholds: dict[str, float] = field(default_factory=lambda: {
        "caution": 0.35, "watch": 0.50, "warning": 0.65, "critical": 0.85,
    })

    # ── Alert ──
    alert_cooldown_hours: float = 72.0
    alert_persistence_min: int = 1

    # ── Incident ──
    incident_window_s: float = 600.0
    incident_close_after_s: float = 3600.0
    incident_causal_delay_s: float = 1800.0

    # ── Stale data ──
    stale_threshold_s: float = 300.0
    ttl_warn_min: float = 60.0
    expected_contact_gap_s: float = 5400.0

    # ── Mission Phase ──
    mission_phase_gating: dict[str, list[str]] = field(default_factory=dict)

    # ── Detection Tier ──
    detection_tier: str = "full"

    @classmethod
    def from_settings(cls, settings: dict) -> "DetectionPipelineConfig":
        """Create from a settings dict (as loaded from aria.dsremo.yaml)."""
        det = settings.get("detection", {})
        feat = settings.get("features", {})

        kwargs: dict = {}
        # Map every field from the det/feat dicts
        for f in cls.__dataclass_fields__:
            if f in det:
                kwargs[f] = det[f]
            elif f in feat:
                kwargs[f] = feat[f]

        # Special mappings
        if "orbital_period" in feat:
            kwargs["orbital_period_s"] = int(feat["orbital_period"])
        if "ensemble_weights" in det:
            kwargs["ensemble_weights"] = det["ensemble_weights"]

        return cls(**kwargs)

    def to_settings(self) -> dict:
        """Convert back to the settings dict format."""
        from dataclasses import asdict  # noqa: PLC0415
        d = asdict(self)
        return {"detection": d, "features": {"orbital_period": self.orbital_period_s}}
