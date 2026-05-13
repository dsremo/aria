"""Bayesian Online Changepoint Detection (BOCPD).

Reference: Adams, R. P. and MacKay, D. J. C. (2007).
           Bayesian Online Changepoint Detection. arXiv:0710.3742.

Why BOCPD instead of PELT (current changepoint detector):
    PELT is a batch algorithm — it re-analyses a full look-back window on
    every call.  On non-stationary telemetry (the norm in spacecraft ops),
    PELT's retrospective window always contains structural breaks and fires
    continuously (confirmed by CATS benchmark: TPR ≈ FPR ≈ 0.98 → weight=0).

    BOCPD is online: it maintains a probability distribution over "run length"
    (time since last changepoint) that is updated with ONE observation per step
    using Bayesian inference.  It outputs P(changepoint NOW) — a calibrated
    probability ∈ [0, 1] that integrates naturally with the score-based ensemble.

Algorithm (conjugate Normal-Gamma model):
    State: R_t[r] = P(run_length = r at time t), vector of length max_run+1.

    Per step for a new observation x:
      1. Compute predictive P(x | run_length = r) for each r via Student-t
         predictive distribution under conjugate Normal-Gamma posterior.
      2. Grow: R_t[r+1] ∝ R_{t-1}[r] × P(x|r) × (1−H)   (run continues)
      3. Changepoint: R_t[0] ∝ Σ_r R_{t-1}[r] × P(x|r) × H  (new run starts)
      4. Normalise R_t.
      5. Score = R_t[0] = P(changepoint at step t).

    Conjugate update after r observations x_{t-r+1:t}:
        κ_r = κ_0 + r
        α_r = α_0 + r/2
        μ_r = (κ_0 μ_0 + Σx) / κ_r
        β_r = β_0 + 0.5 Σ(x_i − x̄)² + κ_0 r (x̄ − μ_0)² / (2 κ_r)

    Predictive: Student-t with 2α_r dof, mean μ_r, scale √(β_r(κ_r+1)/(α_r κ_r)).

Complexity: O(max_run) per sample (vectorised numpy).  Memory: O(max_run) per
channel.  At max_run=300 and 17 channels: ~40 KB total — negligible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import structlog

from aria.dsremo.core.models import DetectorResult, Severity
from aria.dsremo.detection.calibration import CalibrationState

logger = structlog.get_logger()


# ── Per-channel state ─────────────────────────────────────────────────────


@dataclass
class _BOCPDState:
    """Mutable per-channel BOCPD state."""

    # Run-length probability distribution (index = run length).
    # R[r] = P(r consecutive steps since last changepoint).
    # Starts with R[0]=1 (run of length 0 at t=0; first observation is t=1).
    R: np.ndarray = field(default_factory=lambda: np.array([1.0]))

    # Ring buffer of past observations (oldest index 0, newest index -1).
    obs: list[float] = field(default_factory=list)

    # Number of observations processed.
    t: int = 0


# ── Student-t log-PDF (vectorised) ───────────────────────────────────────


def _student_t_logpdf(
    x: float,
    dof: np.ndarray,
    mu: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    """Log PDF of the Student-t distribution, vectorised over r.

    Uses scipy.special.gammaln for numerical stability across a wide range
    of degrees of freedom (dof) and scale values.

    Args:
        x:     Scalar observation.
        dof:   Degrees of freedom per run length, shape (n_r,).
        mu:    Location per run length, shape (n_r,).
        scale: Scale per run length, shape (n_r,).

    Returns:
        Log-probability array, shape (n_r,).
    """
    from scipy.special import gammaln  # noqa: PLC0415

    nu = np.asarray(dof, dtype=np.float64)
    t  = (x - mu) / np.maximum(scale, 1e-12)
    lp = (
        gammaln(0.5 * (nu + 1.0))
        - gammaln(0.5 * nu)
        - 0.5 * np.log(nu * math.pi)
        - np.log(np.maximum(scale, 1e-12))
        - 0.5 * (nu + 1.0) * np.log1p(t ** 2 / nu)
    )
    return lp


# ── Main detector ─────────────────────────────────────────────────────────


class BOCPDDetector:
    """Bayesian Online Changepoint Detector.  One state per channel key.

    Replaces the PELT-based ChangePointDetector in the ensemble.  PELT
    re-analyses a full look-back window on each call and fires continuously
    on non-stationary data (CATS benchmark: weight=0).  BOCPD is strictly
    online: O(max_run) per sample, outputs a calibrated P(changepoint).

    Usage (mirrors CUSUM/EWMA API):
        result = bocpd.detect(key, residual, calibration)
        # result.score  = P(changepoint at this step) ∈ [0, 1]
        # result.is_anomaly = score > alarm_threshold
    """

    def __init__(
        self,
        hazard: float = 0.002,      # ESTIMATE — 1/500 per step (Adams & MacKay 2007 arXiv:0710.3742 §3)
                                    # → expected run length ≈ 500 samples.
                                    # At 60 s resolution that is 500 min ≈ 8 h,
                                    # typical between genuine spacecraft mode changes.
        mu_0: float = 0.0,          # Prior mean = 0 for STL residuals (centred by design)
                                    # Adams & MacKay 2007 §2: Normal-Gamma conjugate prior
        kappa_0: float = 1.0,       # Prior precision weight (Adams & MacKay 2007 §2)
        alpha_0: float = 2.0,       # Prior shape α_0 = 2 (Adams & MacKay 2007: α_0 > 1 for finite variance)
                                    # E[σ²] = β_0 / (α_0 − 1).
        beta_0: float = 1.0,        # Prior scale β_0 = 1 (Adams & MacKay 2007 §2)
                                    # Auto-scaled from CalibrationState.ref_std when calibrated.
        max_run: int = 300,         # ESTIMATE — 300 × 60 s = 5 h; caps memory and compute
                                    # all realistic inter-changepoint intervals.
        alarm_threshold: float = 0.3,  # ESTIMATE — P(CP) ≥ 0.3: Adams & MacKay 2007 §3 practice
        detection_lag: int = 1,     # V3-A3 — score = sum(R_t[:detection_lag]).
                                    # detection_lag=1 reproduces the original
                                    # R_t[0] semantics (backward compatible).
                                    # Callers facing late-detection misses
                                    # (Mellor 2017 §4.3) opt in with e.g.
                                    # detection_lag=10 AND a proportionally
                                    # higher alarm_threshold to avoid false
                                    # positives from the wider window.
        alpha_max: float | None = None,  # V3-A1 — cap posterior α to keep the
                                    # Student-t predictive heavy-tailed
                                    # forever.  None (default) = no cap,
                                    # identical to previous behaviour.
                                    # For heavy-tailed ADCS channels set
                                    # alpha_max=10 → Turner et al. 2009
                                    # recommended ν = 20 throughout.
    ) -> None:
        if not (0.0 < hazard < 1.0):
            raise ValueError(f"hazard must be in (0, 1); got {hazard}")
        if alpha_0 <= 1.0:
            raise ValueError(f"alpha_0 must be > 1 for finite prior variance; got {alpha_0}")

        self.hazard          = hazard
        self._default_hazard = hazard   # fallback when no per-channel override
        self.mu_0            = mu_0
        self.kappa_0         = kappa_0
        self.alpha_0         = alpha_0
        self.beta_0          = beta_0
        self.max_run         = max_run
        self.alarm_threshold = alarm_threshold
        # V3-A3: clamp to [1, max_run] so the score is always well-defined.
        self.detection_lag   = max(1, min(int(detection_lag), max_run))
        # V3-A1: optional cap on posterior alpha.  Must exceed 1 to keep
        # finite variance (same rule as alpha_0); None means no cap.
        if alpha_max is not None and alpha_max <= 1.0:
            raise ValueError(
                f"alpha_max must be > 1 for finite variance; got {alpha_max}"
            )
        self.alpha_max = alpha_max

        self._states: dict[str, _BOCPDState] = {}
        # Per-channel hazard overrides (P2-H fix).  Channels with known
        # changepoint frequency can have their hazard tuned independently.
        self._channel_hazard: dict[str, float] = {}

    def set_channel_hazard(self, key: str, hazard: float) -> None:
        """Set a per-channel hazard rate (P2-H: empirical Bayes approach)."""
        self._channel_hazard[key] = hazard

    def _get_hazard(self, key: str) -> float:
        """Return per-channel hazard if set, else the global default."""
        return self._channel_hazard.get(key, self._default_hazard)

    # ── Public API ────────────────────────────────────────────────────────

    def detect(
        self,
        key: str,
        residual: float,
        calibration: CalibrationState,
    ) -> DetectorResult:
        """Run one BOCPD step for the given channel.

        Args:
            key:         Channel key, e.g. "ESA-MISSION1:channel_047".
            residual:    Latest STL residual (centred near 0).
            calibration: CalibrationState for this channel.  Used to set
                         an informed prior on the noise scale (β_0 ← ref_std²).

        Returns:
            DetectorResult.  score = P(changepoint at this step) ∈ [0, 1].
            is_anomaly=False during calibration warm-up (score is still
            returned so the ensemble can use partial evidence).
        """
        state = self._states.setdefault(key, _BOCPDState())

        # V3-A4 empirical Bayes: derive the Normal-Gamma prior from the
        # channel's own calibration statistics (Gelman 2013 §5.4; Murphy 2007
        # §4 moment matching).  Without this, a static prior μ_0 = 0 /
        # β_0 = 1 is orders of magnitude from real physical channels
        # (battery_voltage ≈ 28 V, panel_temp ≈ 15 °C) and inflates
        # spurious P(changepoint) for the first ~100 samples post-calibration.
        mu_0   = self.mu_0
        beta_0 = self.beta_0
        if calibration.is_calibrated:
            # μ_0 ← calibration.ref_mean (the channel's own centre).
            mu_0 = float(calibration.ref_mean)
            if calibration.ref_std > 1e-9:
                # E[σ²] = β_0/(α_0−1) = ref_std²  →  β_0 = ref_std² × (α_0−1)
                beta_0 = (calibration.ref_std ** 2) * (self.alpha_0 - 1.0)
                beta_0 = max(beta_0, 1e-12)

        cp_prob = self._run_step(state, float(residual), beta_0, key=key, mu_0=mu_0)

        if not calibration.is_calibrated:
            # During warm-up still update state (keep model learning) but
            # never alarm — CUSUM/EWMA also wait for calibration.
            return DetectorResult(
                detector_name="bocpd",
                is_anomaly=False,
                score=float(cp_prob),
                severity=Severity.NOMINAL,
                details={"reason": "warming_up", "cp_prob": round(cp_prob, 4)},
            )

        is_anomaly = cp_prob >= self.alarm_threshold
        severity   = self._severity(cp_prob)

        return DetectorResult(
            detector_name="bocpd",
            is_anomaly=is_anomaly,
            score=float(cp_prob),
            severity=severity,
            details={
                "cp_prob":         round(cp_prob, 4),
                "threshold":       self.alarm_threshold,
                "run_length_mode": int(np.argmax(state.R)),
                "hazard":          self.hazard,
            },
        )

    def reset(self, key: str | None = None) -> None:
        """Reset BOCPD state for one channel or all channels."""
        if key:
            self._states.pop(key, None)
        else:
            self._states.clear()

    def get_state(self, key: str) -> dict:
        s = self._states.get(key)
        if s is None:
            return {}
        return {
            "t":               s.t,
            "run_length_mode": int(np.argmax(s.R)),
            "cp_prob_last":    float(s.R[0]) if len(s.R) > 0 else 0.0,
        }

    # ── Core BOCPD update ─────────────────────────────────────────────────

    def _run_step(
        self,
        state: _BOCPDState,
        x: float,
        beta_0: float,
        key: str = "",
        mu_0: float | None = None,
    ) -> float:
        """One BOCPD update step.  Returns P(changepoint at this step).

        Derivation (Adams & MacKay 2007, eq. 1):
            The key insight: the CHANGEPOINT term uses ONLY the prior predictive
            P(x | prior), while the GROWTH term uses P(x | posterior from last r obs).
            This asymmetry is what makes BOCPD informative — when x doesn't fit the
            recent history but fits the prior, P(changepoint) spikes.

            Unnormalized update:
              U[0]   = H × P(x | prior)                 [changepoint: new run starts]
              U[r+1] = R_prev[r] × (1−H) × P(x | r obs) [growth: run continues]

            Normalise: R_t = U / Σ U.

        Bug avoided: if both terms used Σ_r R_prev[r] × P(x|r) × H (wrong), H would
        cancel during normalisation and R_t[0] would always equal H regardless of x.
        The correct changepoint probability uses the PRIOR predictive (pp_log[0] only).

        Complexity: O(max_run) — fully vectorised.
        Numerical: all operations in log-space to handle large run lengths.
        """
        H   = self._get_hazard(key) if key else self.hazard
        n   = len(state.obs)          # observations already in buffer
        r_n = min(n, self.max_run)    # maximum run length to evaluate

        # ── 1. Predictive log-probabilities ───────────────────────────────
        # pp_log[0]   = log P(x | prior)                  ← used for changepoint
        # pp_log[r]   = log P(x | posterior from r obs)   ← used for growth r → r+1
        # V3-A4: allow per-channel empirical-Bayes override of μ_0; fall
        # back to the global default when the caller didn't supply one.
        effective_mu_0 = self.mu_0 if mu_0 is None else float(mu_0)
        pp_log = self._predictive_log_probs(
            state, x, r_n, beta_0, mu_0=effective_mu_0,
        )  # (r_n+1,)

        # ── 2. Previous run-length distribution ───────────────────────────
        R_prev = state.R[: r_n + 1].copy()   # shape (r_n+1,)

        with np.errstate(divide="ignore"):
            log_R_prev = np.log(np.maximum(R_prev, 1e-300))

        # ── 3. Log unnormalized probabilities ─────────────────────────────
        # Changepoint: U[0] = H × P(x | prior)
        log_U_cp = math.log(H) + pp_log[0]                         # scalar

        # Growth:  U[r+1] = R_prev[r] × (1−H) × P(x | r obs), r=0..r_n
        log_U_growth = log_R_prev + pp_log + math.log(1.0 - H)     # (r_n+1,)

        # ── 4. Normalise via logsumexp ────────────────────────────────────
        # Stack: all_log[0] = log_U_cp, all_log[1..r_n+1] = log_U_growth
        all_log = np.empty(r_n + 2)
        all_log[0]  = log_U_cp
        all_log[1:] = log_U_growth

        log_total = np.logaddexp.reduce(all_log)
        all_prob  = np.exp(all_log - log_total)   # normalized probabilities

        # ── 5. Store into new R distribution ─────────────────────────────
        # V3-A2: keep the total probability mass equal to 1 even when the
        # growth tail exceeds max_run.  all_prob has length r_n + 2:
        #   all_prob[0]               = P(changepoint)
        #   all_prob[1 .. r_n + 1]    = P(run_length = k) for k = 1..r_n+1
        # When r_n + 1 > max_run, the excess mass P(r ≥ max_run) is collapsed
        # into R_new[max_run] instead of silently dropped.  Dropping it
        # inflates R_new[0] on the next normalise step (Caron 2007 §3 note:
        # naive truncation biases changepoint probability upwards on long
        # stable regimes — the exact failure mode described in V3-A2).
        R_new = np.zeros(self.max_run + 1)
        R_new[0] = all_prob[0]                                  # changepoint
        upper = min(r_n + 1, self.max_run)
        R_new[1 : upper + 1] = all_prob[1 : upper + 1]         # growth
        if r_n + 1 > self.max_run:
            # Overflow: sum all bins from max_run onward into R_new[max_run].
            R_new[self.max_run] += all_prob[self.max_run + 1 :].sum()

        state.R = R_new

        # ── 6. Update observation buffer ──────────────────────────────────
        state.obs.append(x)
        if len(state.obs) > self.max_run:
            state.obs.pop(0)
        state.t += 1

        # V3-A3: cumulative changepoint probability over the detection-lag
        # window — "did a changepoint occur within the last `detection_lag`
        # samples?".  R_t[0] alone spikes only at the exact sample of the
        # change; by the time the residual becomes unambiguously anomalous
        # R_t[0] has decayed back to near-hazard.  Summing R_t[:lag] retains
        # elevated score for `lag` samples after the change (Mellor 2017 §4.3).
        lag = self.detection_lag
        return float(R_new[:lag].sum())

    def _predictive_log_probs(
        self,
        state: _BOCPDState,
        x: float,
        r_n: int,
        beta_0: float,
        mu_0: float | None = None,
    ) -> np.ndarray:
        """Vectorised Normal-Gamma predictive log-probability for each run length.

        Returns array of shape (r_n+1,): pp_log[r] = log P(x | run_length=r).

        For r=0 (prior): parameters are (κ_0, μ_0, α_0, β_0).
        For r>0: conjugate posterior after the r most recent observations.

        Sufficient statistics for the last r observations are computed via
        reverse cumulative sums over the observation buffer — O(r_n) total.
        """
        mu_0    = self.mu_0 if mu_0 is None else float(mu_0)
        kappa_0 = self.kappa_0
        alpha_0 = self.alpha_0

        # ── r = 0 (prior only) ────────────────────────────────────────────
        dof_0   = np.array([2.0 * alpha_0])
        scale_0 = np.array([math.sqrt(beta_0 * (kappa_0 + 1.0) / (alpha_0 * kappa_0))])
        mu_0_arr = np.array([mu_0])
        log_pp_0 = _student_t_logpdf(x, dof_0, mu_0_arr, scale_0)   # shape (1,)

        if r_n == 0:
            return log_pp_0

        # ── r ≥ 1 (posterior after r observations) ────────────────────────
        # obs buffer: state.obs[-r_n:] gives last r_n observations, oldest first.
        obs_arr   = np.array(state.obs[-r_n:], dtype=np.float64)   # shape (r_n,)
        r_n_actual = len(obs_arr)

        if r_n_actual == 0:
            return log_pp_0

        # Reverse cumulative sums so index r-1 gives the sum of the last r obs.
        rev       = obs_arr[::-1]
        cum_sum   = np.cumsum(rev)          # cum_sum[r-1] = sum of last r obs
        cum_sum2  = np.cumsum(rev ** 2)     # cum_sum2[r-1] = sum of squares

        r_arr    = np.arange(1, r_n_actual + 1, dtype=np.float64)  # 1..r_n
        kappa_r  = kappa_0 + r_arr
        alpha_r  = alpha_0 + 0.5 * r_arr
        # V3-A1: optional cap keeps Student-t ν = 2·α bounded so the
        # predictive stays heavy-tailed even deep into long runs.
        # Without this, α grows linearly with r and ν → ∞ (Gaussian), which
        # misrepresents ADCS angular-rate distributions during slews where
        # excess_kurtosis routinely exceeds 10.
        if self.alpha_max is not None:
            alpha_r = np.minimum(alpha_r, self.alpha_max)
        xbar_r   = cum_sum / r_arr
        mu_r     = (kappa_0 * mu_0 + cum_sum) / kappa_r

        # β_r = β_0 + 0.5*(Σxi² − r*x̄²) + κ_0*r*(x̄ − μ_0)² / (2*κ_r)
        beta_r = (
            beta_0
            + 0.5 * (cum_sum2 - r_arr * xbar_r ** 2)
            + kappa_0 * r_arr * (xbar_r - mu_0) ** 2 / (2.0 * kappa_r)
        )
        beta_r = np.maximum(beta_r, 1e-12)   # guard against floating-point underflow

        dof_r   = 2.0 * alpha_r
        scale_r = np.sqrt(
            np.maximum(beta_r * (kappa_r + 1.0) / (alpha_r * kappa_r), 1e-24)
        )

        log_pp_r = _student_t_logpdf(x, dof_r, mu_r, scale_r)   # shape (r_n,)

        return np.concatenate([log_pp_0, log_pp_r])   # shape (r_n+1,)

    # ── Severity mapping ──────────────────────────────────────────────────

    def _severity(self, cp_prob: float) -> Severity:
        """Map P(changepoint) to severity.

        Calibration (Bayesian probability is already in [0,1]):
            < alarm_threshold      → NOMINAL  (not is_anomaly)
            alarm_threshold–0.60   → WATCH
            0.60–0.80              → WARNING
            ≥ 0.80                 → CRITICAL
        ESTIMATE: severity tiers at 0.60 and 0.80 are operational thresholds —
        no published standard; chosen to match ESA telemetry monitoring practice
        (ECSS-E-ST-70-32C §4.3: watch/warning/critical three-tier hierarchy).
        """
        if cp_prob >= 0.80:  # ESTIMATE — 80%: CRITICAL tier (ECSS-E-ST-70-32C §4.3 analogue)
            return Severity.CRITICAL
        if cp_prob >= 0.60:  # ESTIMATE — 60%: WARNING tier
            return Severity.WARNING
        if cp_prob >= self.alarm_threshold:  # 0.30: WATCH tier (Adams & MacKay 2007)
            return Severity.WATCH
        return Severity.NOMINAL
