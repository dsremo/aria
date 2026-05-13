"""STL decomposer — removes predictable variation before anomaly detection.

Key principle (from DETECTION_PRINCIPLES.md):
    Detectors run on STL residuals only, never on raw telemetry values.

Raw satellite telemetry contains two non-anomalous components:
    1. Orbital sinusoid  — 90-min eclipse cycle in thermal, power, comms.
    2. Long-term trend   — slow drift in battery capacity, sensor aging, etc.

STL separates:  raw = trend + seasonal + residual

Only the residual is passed to CUSUM / EWMA / z-score / PELT.  The seasonal
component is removed so eclipse cycles never become false positives.  The
trend IS included in the residual (raw - seasonal only) because gradual
degradation is exactly what CUSUM must detect — trend changes ARE anomalies.

Decomposition modes (auto-selected per channel):
    "stl"           — full statsmodels.STL when period_samples >= 4 and
                      len(values) >= 2 × period_samples
    "savgol_trend"  — Savitzky-Golay trend extraction only (no seasonal);
                      used when orbital period is too fine for the data rate
    "cold_start"    — global mean subtraction when < MIN_SAMPLES points
                      available; activates CUSUM/EWMA warmup

Caching: decomposition is expensive.  Each channel caches its last result
and only recomputes when at least RECOMPUTE_EVERY new points have arrived.
The cache key is (channel_key, n_values) — a recompute fires the moment the
window changes meaningfully, not on every single sample.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import numpy as np
import structlog

from aria.dsremo.detection.box_cox import (
    BoxCoxFit,
    fit_lambda,
    transform as boxcox_transform,
)

logger = structlog.get_logger()

# Minimum samples before any decomposition is attempted.
_MIN_SAMPLES: int = 20       # ESTIMATE — 20 samples minimum for meaningful decomposition

# Recompute STL / Savitzky-Golay only when this many new values have arrived
# since the last decomposition.  Amortises the O(n) cost over multiple cycles.
_RECOMPUTE_EVERY: int = 30   # ESTIMATE — recompute every 30 samples (amortise O(n) STL cost)

# V3-K5: fractional tolerance around the orbital period.  An FFT peak outside
# this band is treated as an instrumental artefact (reaction-wheel spin,
# switching-converter harmonics, etc.) and rejected in favour of the orbital
# hint.  ±15 % is the value recommended in the V3 audit (Vallado 2013 §9 notes
# that LEO period drift from perturbations rarely exceeds 1-2 %, so 15 % gives
# wide margin for FFT resolution error without accepting unrelated frequencies).
_ORBITAL_PERIOD_TOLERANCE: float = 0.15   # V3-K5 — ±15 % of orbital period


@dataclass(frozen=True, slots=True)
class DecompositionResult:
    """Immutable result of one decomposition cycle for a channel window."""

    trend: np.ndarray       # long-term trend (kept in residual for CUSUM)
    seasonal: np.ndarray    # periodic orbital component (removed)
    residual: np.ndarray    # raw - seasonal  (= raw - seasonal, trend kept)
    method: str             # "stl" | "savgol_trend" | "cold_start"
    period_samples: int     # effective orbital period in samples (0 if N/A)
    n_samples: int          # length of the input window
    transition_mask: np.ndarray | None = None  # True at eclipse/transition points
    # V3-K1: Box-Cox fit attached to this decomposition.  None when no fit
    # has been registered for the channel (the default — backward compatible).
    # Operator UI / display code inverses with `box_cox.inverse_transform`
    # to recover engineering units; detectors operate on the transformed
    # residual directly (variance-stabilised → single σ_ref is valid).
    box_cox_fit: BoxCoxFit | None = None


@dataclass
class _ChannelCache:
    """Per-channel decomposition cache."""
    last_result: DecompositionResult | None = field(default=None)
    last_n: int = field(default=0)          # n_values at last recompute
    calls_since_recompute: int = field(default=0)
    # V3-K1: per-channel Box-Cox fit.  None = transform disabled for this
    # channel; fit_box_cox() opts channels in explicitly.
    box_cox_fit: BoxCoxFit | None = field(default=None)


class STLDecomposer:
    """Per-channel STL decomposer.  Singleton — one instance per server.

    Usage:
        result = decomposer.decompose(key, values, timestamps)
        residuals = result.residual          # pass to CUSUM / EWMA / z-score
        current_residual = residuals[-1]     # residual for the latest point
    """

    def __init__(
        self,
        orbital_period_s: int = 5400,          # LEO period ~90 min (Wertz & Larson 1999 SMAD §6.2)
        recompute_every: int = _RECOMPUTE_EVERY,
        max_fft_samples: int = 5000,            # ESTIMATE — 5000-sample FFT window (Nyquist: resolves ≥10s periods at 1 Hz)
        orbital_period_tolerance: float = _ORBITAL_PERIOD_TOLERANCE,  # V3-K5
    ):
        self._orbital_period_s  = orbital_period_s
        self._recompute_every   = recompute_every
        # Maximum number of samples passed to _fft_period() for period detection.
        # Default 5000: with Hann windowing + 4× zero-padding, this resolves
        # periods up to 2500 samples.  At 1 Hz that's ~42 min — enough for LEO
        # orbital periods (90 min) when at least 2 cycles are present.
        # For GEO (24h), increase via stl_max_fft_samples config or use the
        # orbital_period_s fallback.
        self._max_fft_samples   = max_fft_samples
        # V3-K5: fractional tolerance around the orbital period.  FFT peaks
        # outside this band are rejected as instrumental artefacts and the
        # orbital hint is used instead.
        self._orbital_period_tolerance = orbital_period_tolerance
        self._cache: dict[str, _ChannelCache] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decompose(
        self,
        key: str,
        values: np.ndarray,
        timestamps: np.ndarray | None = None,
    ) -> DecompositionResult:
        """Decompose a channel window.  Returns cached result when unchanged.

        Args:
            key:        Unique channel key, e.g. "ESA-MISSION1:channel_047".
            values:     Raw telemetry values, oldest → newest.
            timestamps: Unix epoch seconds, same length as values (optional).
                        Used to estimate the effective sampling interval so the
                        orbital period can be expressed in samples.

        Returns:
            DecompositionResult with .residual ready for detectors.
        """
        n = len(values)
        ch = self._cache.setdefault(key, _ChannelCache())
        ch.calls_since_recompute += 1

        needs_recompute = (
            ch.last_result is None
            or ch.calls_since_recompute >= self._recompute_every
            or n != ch.last_n
        )

        if needs_recompute:
            # Period estimation uses RAW values.  Box-Cox is monotone, so
            # the orbital period in samples is invariant; but FFT peak
            # detection is more reliable on the signal with its natural
            # scale, especially near the identity case.
            period_samples = self._estimate_period(timestamps, n, values)
            # V3-K1: apply the fitted Box-Cox transform (if any) before STL.
            # Identity fits are no-ops by contract in box_cox.transform,
            # so this path stays free when no fit has been registered.
            working_values = values
            if ch.box_cox_fit is not None and not ch.box_cox_fit.identity:
                working_values = boxcox_transform(values, ch.box_cox_fit)
            ch.last_result = self._compute(working_values, period_samples)
            # Stamp the fit onto the immutable DecompositionResult so
            # downstream display code can invert the transform.
            ch.last_result = dataclasses.replace(
                ch.last_result, box_cox_fit=ch.box_cox_fit
            )
            ch.last_n = n
            ch.calls_since_recompute = 0

        return ch.last_result  # type: ignore[return-value]

    def reset(self, key: str | None = None) -> None:
        """Clear cache for one channel or all channels."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    def fit_box_cox(self, key: str, values: np.ndarray) -> BoxCoxFit:
        """V3-K1: register a Box-Cox variance-stabilising transform for a channel.

        After this call, every subsequent `decompose(key, …)` will apply the
        fitted transform to the raw values before STL.  The fit is cached
        per channel until explicitly reset.  Channels that have not opted in
        continue to receive the default additive-STL behaviour unchanged.

        The cached decomposition (if any) is invalidated so the next call
        recomputes in transformed space — otherwise downstream detectors
        would keep seeing the stale raw-space residuals.

        Args:
            key:    Channel key matching the one used in `decompose`.
            values: Historical values for λ estimation.  Typically the
                    last few hundred calibrated samples for this channel.

        Returns:
            The fitted BoxCoxFit (identity when the LR test accepts λ=1).
        """
        ch = self._cache.setdefault(key, _ChannelCache())
        ch.box_cox_fit = fit_lambda(values)
        ch.last_result = None
        ch.last_n = 0
        ch.calls_since_recompute = 0
        return ch.box_cox_fit

    def get_box_cox_fit(self, key: str) -> BoxCoxFit | None:
        """Return the channel's registered Box-Cox fit, or None."""
        ch = self._cache.get(key)
        return ch.box_cox_fit if ch is not None else None

    # ------------------------------------------------------------------
    # Period estimation
    # ------------------------------------------------------------------

    def _estimate_period(
        self,
        timestamps: np.ndarray | None,
        n: int,
        values: np.ndarray | None = None,
    ) -> int:
        """Estimate dominant period in samples, using FFT first.

        Strategy (in priority order):
        1. Compute expected orbital period in samples from timestamps.
        2. FFT on the value window — finds any strong periodic component in
           the actual data, regardless of the orbital hint.
        3. V3-K5: validate that the FFT peak is within
           ±orbital_period_tolerance of the expected orbital period.
           An unvalidated FFT peak is likely an instrumental artefact
           (reaction-wheel spin, switching harmonic) and is rejected in
           favour of the orbital hint.
        4. Orbital hint — orbital_period_s / median_interval_s.  Used when
           FFT finds nothing OR its peak fails validation.
        5. Return 0 → caller uses savgol_trend fallback.

        Returns 0 when the data is too coarse to resolve any periodicity.
        """
        # ── Expected orbital period in samples (needed for K-5 validation) ──
        expected_period_samples = 0
        if timestamps is not None and len(timestamps) >= 2:
            diffs = np.diff(timestamps[-min(n, 200):])
            valid = diffs[diffs > 0]
            if len(valid) > 0:
                median_interval_s = float(np.median(valid))
                if median_interval_s > 0:
                    candidate = self._orbital_period_s / median_interval_s
                    if candidate >= 4.0 and int(candidate) <= n // 2:
                        expected_period_samples = int(candidate)

        # ── FFT-based period detection (primary) ──────────────────────
        if values is not None and len(values) >= 8:
            fft_period = self._fft_period(values[-min(n, self._max_fft_samples):])
            if fft_period > 0:
                # V3-K5: reject FFT peaks that are far from the orbital period.
                # With no expected period, accept the FFT peak (no reference).
                if expected_period_samples <= 0:
                    return fft_period
                rel_err = abs(fft_period - expected_period_samples) / expected_period_samples
                if rel_err <= self._orbital_period_tolerance:
                    return fft_period
                logger.debug(
                    "stl_fft_period_rejected",
                    fft_period=fft_period,
                    expected_period=expected_period_samples,
                    rel_err=round(rel_err, 3),
                    tolerance=self._orbital_period_tolerance,
                )
                # Fall through to the orbital hint below.

        # ── Orbital period hint (fallback) ────────────────────────────
        if expected_period_samples > 0:
            return expected_period_samples
        return 0

    @staticmethod
    def _fft_period(values: np.ndarray, min_period: int = 4) -> int:
        """Return dominant period in samples via FFT, or 0 if none found.

        Algorithm:
        1. Linearly detrend the window to remove DC offset and slow drift.
        2. Apply Hann window to reduce spectral leakage (P3-T fix).
        3. Zero-pad to 4× input length for finer frequency resolution,
           enabling detection of periods up to n/2 samples (P0-D fix).
        4. Compute the real-FFT amplitude spectrum.
        5. Exclude DC (index 0) and the Nyquist bin (last index).
        6. Find the peak amplitude bin.
        7. Accept the peak only if its amplitude is > 4× the median of all
           non-DC bins — this filters broadband noise.
        8. Convert peak bin index to period using nfft (zero-padded length).
        9. Reject if period < min_period or period > n//2 (need 2 full
           cycles in the ORIGINAL data for meaningful STL decomposition).

        Args:
            values:     1-D signal array (oldest → newest).
            min_period: Minimum acceptable period in samples (default 4).

        Returns:
            Dominant period in samples (integer ≥ min_period), or 0.

        Examples:
            >>> x = np.sin(2 * np.pi * np.arange(300) / 30)  # period=30
            >>> STLDecomposer._fft_period(x)
            30
        """
        n = len(values)
        if n < 2 * min_period:
            return 0

        # Linear detrend: subtract the best-fit line to remove DC + slow drift.
        detrended = values - np.linspace(float(values[0]), float(values[-1]), n)

        # Hann window: reduces spectral leakage from rectangular windowing.
        # Without this, a strong signal bleeds into adjacent frequency bins,
        # creating phantom peaks at harmonics.
        windowed = detrended * np.hanning(n)

        # Zero-pad to at least 4× input length for finer frequency resolution.
        # Frequency resolution = sampling_rate / nfft.  With nfft = 4n,
        # resolution improves 4× — enabling detection of periods up to n/2
        # even with limited data.  For n=5000 at 1 Hz, this resolves orbital
        # periods up to 2500s (enough for LEO 5400s with 2 cycles).
        nfft = max(n * 4, 2048)

        spectrum = np.abs(np.fft.rfft(windowed, n=nfft))
        # Skip DC (index 0) and Nyquist (last) — only examine interior bins.
        interior = spectrum[1:-1]
        if len(interior) == 0:
            return 0

        peak_pos   = int(np.argmax(interior))   # index within interior
        peak_amp   = float(interior[peak_pos])
        median_amp = float(np.median(interior))

        # Require the peak to stand clearly above the noise floor.
        # For Gaussian noise (n=300), expected peak/median ≈ 2.7× due to
        # order-statistic concentration.  A threshold of 4× rejects broadband
        # noise while accepting genuine periodicity (peak/median > 10× typical
        # for clean sinusoidal components).
        if median_amp <= 0 or peak_amp < 4.0 * median_amp:
            return 0

        peak_bin = peak_pos + 1   # +1 because we skipped DC
        # Period computed from nfft (zero-padded length), not n.
        period   = round(nfft / peak_bin)

        # Validate against ORIGINAL data length: need at least 2 full cycles
        # in the actual data for STL decomposition, regardless of zero-padding.
        if period < min_period or period > n // 2:
            return 0

        return period

    # ------------------------------------------------------------------
    # Eclipse / transition detection (P1-A fix)
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_transitions(
        values: np.ndarray,
        period_samples: int,
        sigma_mult: float = 4.0,   # ESTIMATE — 4× MAD eclipse-step threshold (Hampel 1974 Technometrics 16 37)
    ) -> np.ndarray:
        """Detect sharp transitions (eclipse entry/exit) in the signal.

        Returns a boolean mask: True at indices where the signal has a sharp
        step discontinuity (derivative exceeds sigma_mult × MAD of derivatives).
        These points should be excluded from CUSUM/EWMA accumulation to prevent
        systematic false positives at eclipse boundaries.

        Algorithm:
        1. Compute first differences: d[i] = values[i] - values[i-1]
        2. Compute MAD (Median Absolute Deviation) of differences
        3. Mark indices where |d[i]| > sigma_mult × MAD as transitions
        4. Expand mask by ±2 samples (transitions have ringing)

        Args:
            values:         Raw or residual telemetry values.
            period_samples: Detected orbital period (used for validation).
            sigma_mult:     How many MADs above median to flag as transition.

        Returns:
            Boolean ndarray, same length as values. True = transition point.
        """
        n = len(values)
        mask = np.zeros(n, dtype=bool)
        if n < 10:
            return mask

        diffs = np.diff(values)
        if len(diffs) == 0:
            return mask

        mad = float(np.median(np.abs(diffs - np.median(diffs))))
        if mad < 1e-12:
            return mask

        threshold = sigma_mult * mad
        transition_indices = np.where(np.abs(diffs) > threshold)[0]

        # Expand each transition by ±2 samples (ringing from sharp edges).
        for idx in transition_indices:
            lo = max(0, idx - 1)
            hi = min(n, idx + 3)  # +3 because diff shifts by 1
            mask[lo:hi] = True

        return mask

    # ------------------------------------------------------------------
    # Decomposition
    # ------------------------------------------------------------------

    def _compute(self, values: np.ndarray, period_samples: int) -> DecompositionResult:
        n = len(values)

        if n < _MIN_SAMPLES:
            return self._cold_start(values)

        # Detect eclipse/transition boundaries in the raw signal.
        transition_mask = self._detect_transitions(values, period_samples)

        # Full STL: requires period >= 4 AND at least 2 complete cycles of data.
        if period_samples >= 4 and n >= 2 * period_samples:
            result = self._try_stl(values, period_samples, transition_mask)
            if result is not None:
                return result

        # Fallback: extract trend via Savitzky-Golay, no seasonal component.
        # Residual = raw - trend.  CUSUM will then detect accelerating drift.
        return self._savgol_trend(values, transition_mask)

    def _try_stl(self, values: np.ndarray, period_samples: int, transition_mask: np.ndarray | None = None) -> DecompositionResult | None:
        try:
            from statsmodels.tsa.seasonal import STL  # type: ignore

            n = len(values)
            # seasonal window must be odd and >= 7
            sw = max(7, period_samples | 1)  # bitwise OR 1 → make odd
            if sw % 2 == 0:
                sw += 1

            stl = STL(
                values,
                period=period_samples,
                seasonal=sw,
                robust=True,   # resistant to outliers during decomposition
            )
            fit = stl.fit()

            trend    = np.asarray(fit.trend,    dtype=np.float64)
            seasonal = np.asarray(fit.seasonal, dtype=np.float64)

            # Residual = raw - seasonal only.
            # We keep the trend inside the residual so CUSUM can detect
            # when the long-term drift itself becomes anomalous.
            residual = values - seasonal

            return DecompositionResult(
                trend=trend,
                seasonal=seasonal,
                residual=residual,
                method="stl",
                period_samples=period_samples,
                n_samples=n,
                transition_mask=transition_mask,
            )
        except Exception as exc:
            logger.debug("stl_decomp_failed", error=str(exc))
            return None

    def _savgol_trend(self, values: np.ndarray, transition_mask: np.ndarray | None = None) -> DecompositionResult:
        """Trend-only decomposition via Savitzky-Golay smoothing.

        Used when the data rate is too coarse for orbital STL.
        Extracts a smooth trend; residual = raw - trend, which centres the
        signal and removes baseline drift so CUSUM operates on deviations.
        """
        n = len(values)
        # Window: ~15% of data, must be odd, between 5 and 101
        window = max(5, min(n // 7, 101))
        if window % 2 == 0:
            window += 1
        window = min(window, n if n % 2 == 1 else n - 1)
        window = max(window, 5)

        trend = self._apply_savgol(values, window)
        seasonal = np.zeros(n, dtype=np.float64)
        # Residual = raw - trend here (no seasonal component)
        residual = values - trend

        return DecompositionResult(
            trend=trend,
            seasonal=seasonal,
            residual=residual,
            method="savgol_trend",
            period_samples=0,
            n_samples=n,
            transition_mask=transition_mask,
        )

    @staticmethod
    def _apply_savgol(values: np.ndarray, window: int) -> np.ndarray:
        try:
            from scipy.signal import savgol_filter  # type: ignore
            return np.asarray(savgol_filter(values, window_length=window, polyorder=2), dtype=np.float64)
        except Exception:
            # Final fallback: centred rolling mean
            return np.asarray(
                np.convolve(values, np.ones(window) / window, mode="same"),
                dtype=np.float64,
            )

    @staticmethod
    def _cold_start(values: np.ndarray) -> DecompositionResult:
        """Minimal decomposition during warm-up (<20 samples).

        Removes only the global mean so residuals are centred at zero.
        CUSUM and EWMA skip detection until calibration completes anyway.
        """
        n = len(values)
        mean = float(np.mean(values)) if n > 0 else 0.0
        trend    = np.full(n, mean, dtype=np.float64)
        seasonal = np.zeros(n, dtype=np.float64)
        residual = values - trend

        return DecompositionResult(
            trend=trend,
            seasonal=seasonal,
            residual=residual,
            method="cold_start",
            period_samples=0,
            n_samples=n,
        )
