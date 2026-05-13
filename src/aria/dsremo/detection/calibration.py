"""Per-channel calibration — reference distribution for CUSUM and EWMA.

Every channel learns its own reference mean (μ_ref) and standard deviation
(σ_ref) from its first CALIBRATION_WINDOW residual values.  These two numbers
drive ALL threshold calculations for CUSUM and EWMA; there are no global
thresholds anywhere in the detection pipeline.

State machine per channel:
    warming_up    — collecting the first N residuals; CUSUM/EWMA are disabled
    calibrated    — μ_ref and σ_ref are set; detectors are fully active
    recalibrating — μ_ref has drifted by > RECAL_FACTOR × σ_ref, indicating a
                    genuine operational regime change; restarting the reference
                    window (rare: only fires on large permanent step changes)

Derived parameters (recomputed whenever σ_ref changes):
    CUSUM:  k = K_FACTOR × σ_ref   (allowance — half the "shift to detect")
            H = H_FACTOR × σ_ref   (alarm threshold)
    EWMA:   UCL = +SIGMA_FACTOR × σ_ref × sqrt(λ/(2-λ))
            LCL = -SIGMA_FACTOR × σ_ref × sqrt(λ/(2-λ))

All four values are stored on the CalibrationState object so detectors never
need to recompute them — they just read the fields.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import structlog

logger = structlog.get_logger()

# ── tuneable constants (also overridable via dsremo.yaml / init) ──────────
CALIBRATION_WINDOW:  int   = 100    # ESTIMATE — 100-sample burn-in (Page 1954 Biometrika 41 100)
CUSUM_K_FACTOR:      float = 0.5    # k = 0.5σ: Page 1954 Biometrika 41 100 optimal for 1σ shift detection
CUSUM_H_FACTOR:      float = 5.0    # H = 5σ: NASA-STD-8719.13C standard CUSUM threshold (Lucas 1982 Technometrics 24 199)
EWMA_LAMBDA:         float = 0.2    # λ = 0.2: Roberts 1959 Technometrics 1 239 recommended λ for slow drifts
EWMA_SIGMA_FACTOR:   float = 3.0    # UCL/LCL ±3σ: Lucas & Saccucci 1990 Technometrics 32 1 control limits
# Sensor-fusion audit S-12: lowered from 10σ → 4σ.
#
# A real catastrophic event (battery cell short, prop leak) produces
# exactly the >10σ drift the previous threshold required, so the
# auto-recalibration was *masking* the worst failures by absorbing them
# into a new "normal."  4σ matches Lucas & Saccucci 1990 recommended
# regime-change-detection threshold for SPC charts and stays above the
# 3σ false-positive rate.  Above this threshold AND below
# RECAL_HARD_FACTOR we still auto-recal; above RECAL_HARD_FACTOR we
# *do not* auto-recal — operator acknowledgement is required.
RECAL_FACTOR:        float = 4.0    # σ — Lucas & Saccucci 1990 Technometrics 32 1 (regime-change SPC threshold)
RECAL_HARD_FACTOR:   float = 8.0    # σ — auto-recal disabled above this; operator-ack required (sensor-fusion audit S-12)
SIGMA_UPDATE_INTERVAL: int = 720    # ESTIMATE — 720 samples = 30 days at 1-h resampling
                                    # aging / long-term seasonal variance shifts
SIGMA_UPDATE_THRESHOLD: float = 0.10  # ESTIMATE — 10% σ change to trigger update (avoids noisy micro-updates)

# Pre-computed EWMA spread factor sqrt(λ/(2-λ)) — constant for a given λ
_ewma_spread = math.sqrt(EWMA_LAMBDA / (2.0 - EWMA_LAMBDA))

# ── Adaptive feature flags (overridable via dsremo.yaml / init_detectors) ─
GMM_ENABLED: bool = True            # fit GMM-2 on calibration window to handle
                                    # bimodal channels (two operating modes)
AUTO_Z_THRESHOLD_ENABLED: bool = True  # compute per-channel 99th-pct z from
                                       # calibration window; raises threshold
                                       # automatically for noisy channels


@dataclass
class CalibrationState:
    """All calibration data for one (satellite_id, parameter) pair."""

    state: str = "warming_up"           # warming_up | calibrated | recalibrating

    # Reference distribution (set once calibration window is full)
    ref_mean: float = 0.0
    ref_std:  float = 0.0
    sample_count: int = 0

    # CUSUM thresholds derived from σ_ref
    cusum_k: float = 0.0                # allowance
    cusum_h: float = 0.0                # alarm threshold

    # EWMA control limits derived from σ_ref
    ewma_ucl: float = 0.0
    ewma_lcl: float = 0.0

    # Internal: raw residuals collected during warming_up
    _buffer: list[float] = field(default_factory=list, repr=False)

    # Internal: recent post-calibration residuals for periodic σ_ref refresh.
    # Kept at ≤ CALIBRATION_WINDOW entries — a sliding window of recent noise.
    _recent_buffer: list[float] = field(default_factory=list, repr=False)
    _sigma_update_counter: int = 0

    # ── GMM-2 bimodal reference (set only when BIC(GMM-2) < BIC(Gaussian) - 10) ─
    # When not None, z-scores are computed as min distance to either component,
    # preventing false alarms on channels that oscillate between two normal states.
    gmm_means: list[float] | None = field(default=None, repr=False)
    gmm_stds:  list[float] | None = field(default=None, repr=False)

    # ── Per-channel empirical z-threshold ────────────────────────────────────
    # 99th percentile of |residual|/σ_ref from the calibration window.
    # Stored as the auto-calibrated lower bound for z-threshold overrides.
    # None until calibration completes.  Clamped to [3.5, 10.0].
    auto_z_threshold: float | None = None

    # ── AR(1) autocorrelation pre-whitening ───────────────────────────────────
    # Lag-1 Pearson correlation coefficient estimated from the calibration window.
    # 0.0 = no significant autocorrelation (i.i.d. assumption holds).
    # When |rho_1| > 0.2, pre-whitening is active for CUSUM and EWMA:
    #     w_t = r_t - ar1_phi × r_{t-1}
    # This removes the autocorrelation component so the CUSUM/EWMA ARL formulas
    # (derived for i.i.d. Normal residuals) remain valid.  Without pre-whitening,
    # AR(1) correlation ρ inflates the effective variance by (1+ρ)/(1-ρ), which
    # can increase the false-positive rate by up to 10× for ρ ≈ 0.5.
    ar1_phi: float = 0.0
    # Previous raw residual value — used in whiten() to compute w_t.
    # Stores the raw r_{t-1} (not the whitened value) because the AR(1) model
    # is r_t = ar1_phi × r_{t-1} + w_t, so w_t = r_t - ar1_phi × r_{t-1}.
    _prev_residual: float = field(default=0.0, repr=False)

    # Sensor noise floor (optional per-channel override).
    # When set, ref_std is decomposed: σ²_total = σ²_process + σ²_sensor.
    # σ_process = √(ref_std² - sensor_noise_floor²) when ref_std > sensor_noise_floor.
    # Detectors should use σ_process for threshold derivation, not raw ref_std.
    sensor_noise_floor: float = 0.0

    # ── EWMA adaptive variance (P2-G: heteroskedasticity handling) ────────
    # Exponentially weighted variance tracks time-varying noise levels.
    # Updated per-sample: σ²_ewma = λ × r² + (1-λ) × σ²_ewma_prev
    # Provides a short-memory variance estimate for detectors on channels
    # where variance changes faster than the 720-sample σ_ref refresh cycle
    # (e.g., thermal telemetry during eclipse transitions).
    ewma_variance: float = 0.0
    _ewma_var_initialized: bool = field(default=False, repr=False)

    # ── Normality test (P3-R: validate i.i.d. Normal assumption) ──────────
    # Shapiro-Wilk p-value from calibration window whitened innovations.
    # p < 0.05 means the Normal assumption is likely violated; CUSUM ARL
    # formulas may not be accurate.  Logged as informational warning.
    normality_p_value: float | None = None

    # ── derived-parameter helpers ───────────────────────────────────────

    @property
    def process_std(self) -> float:
        """Process noise standard deviation, excluding known sensor noise floor."""
        if self.sensor_noise_floor > 0 and self.ref_std > self.sensor_noise_floor:
            import math
            return math.sqrt(self.ref_std ** 2 - self.sensor_noise_floor ** 2)
        return self.ref_std

    @property
    def is_calibrated(self) -> bool:
        return self.state == "calibrated"

    @property
    def is_warming(self) -> bool:
        return self.state in ("warming_up", "recalibrating")

    def whiten(self, residual: float) -> float:
        """Apply AR(1) pre-whitening to one residual and advance the lag buffer.

        Returns w_t = residual - ar1_phi × r_{t-1}.
        When ar1_phi = 0.0 (no autocorrelation detected), returns residual
        unchanged — zero overhead on the common path.

        Also updates the EWMA adaptive variance (P2-G fix) for
        heteroskedasticity tracking.

        Must be called once per residual in strict chronological order.
        Called in detector.py immediately after calibration_mgr.update(),
        before passing the residual to CUSUM and EWMA.
        """
        w = residual - self.ar1_phi * self._prev_residual
        self._prev_residual = residual  # store raw r_t for next call

        # EWMA adaptive variance: σ²_ewma = λ × r² + (1-λ) × σ²_ewma_prev
        # Uses the same λ as EWMA detector for consistency.
        if not self._ewma_var_initialized:
            self.ewma_variance = residual * residual
            self._ewma_var_initialized = True
        else:
            lam = 0.2  # matches EWMA_LAMBDA default
            self.ewma_variance = lam * residual * residual + (1.0 - lam) * self.ewma_variance

        return w

    def _update_derived(self, sigma: float) -> None:
        """Recompute CUSUM and EWMA thresholds from a new σ_ref.

        When AR(1) pre-whitening is active (ar1_phi ≠ 0), CUSUM and EWMA see
        whitened innovations w_t = r_t - φ·r_{t-1}, whose variance is:

            Var(w_t) = σ²_raw × (1 − φ²)   →   σ_innov = σ_raw × √(1 − φ²)

        P2-K: When sensor_noise_floor is set, use process_std (σ_process)
        instead of raw σ_ref for threshold derivation, so CUSUM/EWMA are
        sensitive to real process variation, not inflated by measurement noise.
        """
        sigma = max(sigma, 1e-6)        # guard against near-zero variance
        self.ref_std  = sigma
        # P2-K: Use process std (excluding known sensor noise) for thresholds.
        sigma_eff = self.process_std if self.sensor_noise_floor > 0 else sigma
        # Innovation std for CUSUM/EWMA: reduced by √(1-φ²) when |φ| > 0.
        sigma_innov = sigma_eff * math.sqrt(max(1.0 - self.ar1_phi ** 2, 0.01))
        self.cusum_k  = CUSUM_K_FACTOR  * sigma_innov
        self.cusum_h  = CUSUM_H_FACTOR  * sigma_innov
        spread        = _ewma_spread
        self.ewma_ucl = +EWMA_SIGMA_FACTOR * sigma_innov * spread
        self.ewma_lcl = -EWMA_SIGMA_FACTOR * sigma_innov * spread

    def to_dict(self) -> dict:
        return {
            "state":        self.state,
            "ref_mean":     self.ref_mean,
            "ref_std":      self.ref_std,
            "sample_count": self.sample_count,
        }


def _try_fit_gmm(state: "CalibrationState", arr: "np.ndarray") -> None:
    """Attempt GMM fit on the calibration window (k=1,2,3).

    P3-F fix: Test k=1,2,3 (not just k=2) because some spacecraft channels
    have 3 modes (sunlit, eclipse, transition).  Select by BIC.

    Sets state.gmm_means and state.gmm_stds when a multi-component GMM
    fits the data significantly better than a single Gaussian.

    Silently does nothing if sklearn is unavailable or the fit fails.
    """
    try:
        from sklearn.mixture import GaussianMixture  # noqa: PLC0415
    except ImportError:
        return

    try:
        data = arr.reshape(-1, 1)
        bic_threshold = 3.0 * math.log(max(len(arr), 2))

        # Fit k=1,2,3 and select by BIC (lower = better).
        best_k = 1
        best_bic = float("inf")
        best_gmm = None

        for k in (1, 2, 3):
            if len(arr) < k * 5:  # need at least 5 samples per component
                continue
            gmm = GaussianMixture(n_components=k, covariance_type="full", random_state=0)
            gmm.fit(data)
            bic = gmm.bic(data)
            if bic < best_bic:
                best_bic = bic
                best_k = k
                best_gmm = gmm

        if best_k > 1 and best_gmm is not None:
            # Verify the improvement over k=1 is significant.
            gmm1 = GaussianMixture(n_components=1, covariance_type="full", random_state=0)
            gmm1.fit(data)
            bic1 = gmm1.bic(data)
            if (bic1 - best_bic) > bic_threshold:
                means = best_gmm.means_.flatten().tolist()
                stds  = [float(np.sqrt(c[0, 0])) for c in best_gmm.covariances_]
                if all(s > 1e-9 for s in stds):
                    state.gmm_means = means
                    state.gmm_stds  = stds
    except Exception:  # noqa: BLE001
        pass  # any sklearn failure → fall back to single-Gaussian silently


class CalibrationManager:
    """Registry of per-channel calibration states.  Singleton.

    Call update() on every new residual value.  The state machine advances
    automatically:
        - First CALIBRATION_WINDOW calls → warming_up; returns state with
          is_calibrated=False so callers can skip CUSUM/EWMA.
        - At sample CALIBRATION_WINDOW → transitions to calibrated; μ_ref
          and σ_ref are frozen from the reference buffer.
        - Later: if |current_residual - μ_ref| > RECAL_FACTOR × σ_ref for
          RECAL_STREAK consecutive samples → recalibrating (rare).
    """

    # How many consecutive extreme-deviation samples trigger recalibration.
    _RECAL_STREAK: int = 20

    def __init__(self) -> None:
        self._states: dict[str, CalibrationState] = {}
        # Track consecutive high-deviation counts per channel for recal.
        self._recal_streak: dict[str, int] = {}

    # ── public API ──────────────────────────────────────────────────────

    def update(self, key: str, residual: float) -> CalibrationState:
        """Feed one residual; advance state machine; return current state.

        Args:
            key:     Channel key, e.g. "ESA-MISSION1:channel_047".
            residual: Latest STL residual value for the channel.

        Returns:
            CalibrationState — callers check .is_calibrated before running
            CUSUM/EWMA.  All thresholds (cusum_k, cusum_h, ewma_ucl, ewma_lcl)
            are ready to use when is_calibrated is True.
        """
        state = self._states.setdefault(key, CalibrationState())

        if state.state in ("warming_up", "recalibrating"):
            self._collect(key, state, residual)
        else:
            # Calibrated — check for regime shift
            self._check_regime(key, state, residual)

        return state

    def get(self, key: str) -> CalibrationState | None:
        """Return current calibration state without updating it."""
        return self._states.get(key)

    def load_from_db(self, key: str, data: dict) -> None:
        """Warm the in-memory state from a DB row loaded at startup.

        data keys: state, ref_mean, ref_std, ref_sample_count
        """
        state = self._states.setdefault(key, CalibrationState())
        state.state        = data.get("state", "warming_up")
        state.ref_mean     = float(data.get("ref_mean") or 0.0)
        state.sample_count = int(data.get("ref_sample_count") or 0)
        sigma              = float(data.get("ref_std") or 0.0)
        if state.state == "calibrated" and sigma > 0:
            state._update_derived(sigma)

    def all_db_records(self) -> list[tuple[str, dict]]:
        """Serialize all calibration states for DB persistence.

        Returns list of (key, record_dict) tuples.
        """
        return [
            (
                k,
                {
                    "state":            s.state,
                    "ref_mean":         s.ref_mean,
                    "ref_std":          s.ref_std,
                    "ref_sample_count": s.sample_count,
                },
            )
            for k, s in self._states.items()
        ]

    # ── state machine internals ─────────────────────────────────────────

    def _collect(self, key: str, state: CalibrationState, residual: float) -> None:
        """Accumulate residuals in the warmup buffer; transition when full."""
        state._buffer.append(residual)
        state.sample_count += 1

        if len(state._buffer) >= CALIBRATION_WINDOW:
            arr = np.asarray(state._buffer, dtype=np.float64)
            state.ref_mean = float(np.mean(arr))

            # ── AR(1) autocorrelation detection ───────────────────────────
            # P3-U fix: Detrend the calibration window before AR(1) estimation.
            # If the calibration window contains a trend (e.g., thermal ramp-up),
            # the raw lag-1 correlation is biased upward.  Linear detrending
            # removes this bias.
            state.ar1_phi = 0.0
            state._prev_residual = 0.0
            if len(arr) >= 4:
                # Detrend: subtract best-fit line before estimating autocorrelation.
                detrended = arr - np.linspace(float(arr[0]), float(arr[-1]), len(arr))
                rho1 = float(np.corrcoef(detrended[:-1], detrended[1:])[0, 1])
                if np.isfinite(rho1) and abs(rho1) > 0.2:
                    state.ar1_phi = rho1

            state._update_derived(float(np.std(arr, ddof=1)))

            # ── GMM-2 bimodal fit (resets on recalibration) ───────────────
            state.gmm_means = None
            state.gmm_stds  = None
            if GMM_ENABLED:
                _try_fit_gmm(state, arr)

            # ── Per-channel empirical z-threshold (P3-S: parametric fit) ──
            state.auto_z_threshold = None
            if AUTO_Z_THRESHOLD_ENABLED and state.ref_std > 1e-9:
                z_scores = np.abs(arr - state.ref_mean) / state.ref_std
                # P3-S fix: Use parametric Gaussian fit instead of raw empirical
                # percentile.  With only n=100 observations, the 99th percentile
                # is the ~99th-largest value (1 observation from the tail) — unreliable.
                # Parametric approach: assume z ~ |N(0,1)|, so the 99th percentile
                # of |z| = Φ⁻¹(0.995) ≈ 2.576 for a standard Normal.
                # For non-standard noise: fit σ_z from the trimmed z-scores, then
                # threshold = σ_z × 2.576.
                n_trim = max(1, int(len(z_scores) * 0.05))
                z_trimmed = np.sort(z_scores)[:-n_trim]
                if len(z_trimmed) > 0:
                    # Fit half-normal: σ_z = √(π/2) × mean(|z|) (MLE for folded normal)
                    sigma_z = float(np.mean(z_trimmed)) * math.sqrt(math.pi / 2.0)
                    # 99th percentile of |N(0, σ_z²)| = σ_z × Φ⁻¹(0.995)
                    parametric_pct = sigma_z * 2.576
                else:
                    parametric_pct = 3.5
                state.auto_z_threshold = float(np.clip(parametric_pct, 3.5, 10.0))

            # ── Normality test (P3-R: validate i.i.d. assumption) ─────────
            state.normality_p_value = None
            if len(arr) >= 20:
                try:
                    from scipy.stats import shapiro  # noqa: PLC0415
                    # Test whitened innovations if AR(1) is active, else raw residuals.
                    test_data = arr
                    if state.ar1_phi != 0.0 and len(arr) >= 4:
                        test_data = arr[1:] - state.ar1_phi * arr[:-1]
                    # Shapiro-Wilk limited to 5000 samples; subsample if needed.
                    if len(test_data) > 5000:
                        rng = np.random.default_rng(42)
                        test_data = rng.choice(test_data, 5000, replace=False)
                    _, p_val = shapiro(test_data)
                    state.normality_p_value = round(float(p_val), 6)
                    if p_val < 0.05:
                        logger.warning(
                            "normality_violated",
                            key=key,
                            p_value=round(float(p_val), 4),
                            msg="CUSUM/EWMA ARL formulas assume Normal innovations; "
                                "results may be approximate for this channel.",
                        )
                except ImportError:
                    pass  # scipy not available
                except Exception:  # noqa: BLE001
                    pass

            state._buffer.clear()
            state.state = "calibrated"
            self._recal_streak[key] = 0
            logger.info(
                "channel_calibrated",
                key=key,
                ref_mean=round(state.ref_mean, 4),
                ref_std=round(state.ref_std, 6),
                samples=state.sample_count,
                gmm_active=state.gmm_means is not None,
                auto_z=round(state.auto_z_threshold, 3) if state.auto_z_threshold else None,
            )
            # Log ARL budget so operators know the false alarm and detection delay
            # characteristics of CUSUM/EWMA for this channel.
            try:
                from aria.dsremo.detection.arl import log_channel_arl  # noqa: PLC0415
                log_channel_arl(
                    key=key,
                    cusum_k=state.cusum_k,
                    cusum_h=state.cusum_h,
                    ewma_lambda=EWMA_LAMBDA,
                    ewma_L=EWMA_SIGMA_FACTOR,
                    ref_std=state.ref_std,
                )
            except Exception:  # noqa: BLE001
                pass  # ARL logging is informational; never block calibration

    def _check_regime(self, key: str, state: CalibrationState, residual: float) -> None:
        """Detect if the process has shifted to a new regime.

        Also performs a periodic σ_ref refresh every SIGMA_UPDATE_INTERVAL
        samples.  This prevents the frozen σ_ref (computed from the first
        CALIBRATION_WINDOW residuals) from becoming stale on long time-series
        where signal variance evolves due to component aging or seasonal effects.

        When σ_ref is too small relative to the current noise floor, CUSUM
        accumulates small-but-consistent deviations and fires repeatedly as a
        false positive — this adaptive update is the root-cause fix for that.
        """
        if state.ref_std < 1e-9:
            return
        deviation = abs(residual - state.ref_mean) / state.ref_std
        streak = self._recal_streak.get(key, 0)

        if deviation > RECAL_FACTOR:
            streak += 1
            self._recal_streak[key] = streak
            if streak >= self._RECAL_STREAK:
                # Sensor-fusion audit S-12: above RECAL_HARD_FACTOR the
                # drift is large enough to be a real failure (cell
                # short, prop leak, sensor stuck-at).  Refuse to auto-
                # recalibrate; surface as an operator-ack event so the
                # detector cannot silently bake the failure into the
                # baseline.
                if deviation > RECAL_HARD_FACTOR:
                    logger.error(
                        "channel_recal_blocked_for_operator_ack",
                        key=key,
                        deviation_sigma=round(deviation, 2),
                        streak=streak,
                        hard_factor=RECAL_HARD_FACTOR,
                    )
                    # Reset streak so we don't spam the log; a future
                    # operator-ack hook can call ``force_recalibrate``.
                    self._recal_streak[key] = 0
                    return
                # Genuine regime change — restart calibration.
                logger.info(
                    "channel_recalibrating",
                    key=key,
                    deviation_sigma=round(deviation, 2),
                    streak=streak,
                )
                state.state = "recalibrating"
                state._buffer = [residual]
                state._recent_buffer.clear()
                state._sigma_update_counter = 0
                state.sample_count += 1
                self._recal_streak[key] = 0
                # Reset AR(1) state — will be recomputed from new calibration window.
                state.ar1_phi = 0.0
                state._prev_residual = 0.0
        else:
            # Normal — reset streak counter.
            self._recal_streak[key] = 0

        # ── Periodic σ_ref refresh ─────────────────────────────────────────
        # Accumulate recent residuals in a sliding window and refresh σ_ref
        # every SIGMA_UPDATE_INTERVAL samples.  Only acts when the new σ
        # differs meaningfully from the current one (>10% change) to avoid
        # noisy micro-updates.
        state._recent_buffer.append(residual)
        if len(state._recent_buffer) > CALIBRATION_WINDOW:
            # Keep only the most recent CALIBRATION_WINDOW residuals.
            state._recent_buffer = state._recent_buffer[-CALIBRATION_WINDOW:]

        state._sigma_update_counter += 1
        if state._sigma_update_counter >= SIGMA_UPDATE_INTERVAL:
            state._sigma_update_counter = 0
            min_samples = CALIBRATION_WINDOW // 2
            if len(state._recent_buffer) >= min_samples:
                arr = np.asarray(state._recent_buffer, dtype=np.float64)
                new_sigma = float(np.std(arr, ddof=1))
                if new_sigma > 1e-9:
                    old_sigma = state.ref_std
                    ratio = new_sigma / max(old_sigma, 1e-9)
                    if abs(ratio - 1.0) > SIGMA_UPDATE_THRESHOLD:
                        state._update_derived(new_sigma)
                        logger.debug(
                            "sigma_refreshed",
                            key=key,
                            old=round(old_sigma, 6),
                            new=round(new_sigma, 6),
                            ratio=round(ratio, 3),
                        )
