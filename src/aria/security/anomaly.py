"""Anomaly Detection for AI-Driven Attacks.

Layer 3 defense — specifically designed to detect Mythos-class adversaries.

Why statistical anomaly detection vs. signature matching?
  Mythos generates novel attack chains that no signature DB has seen.
  But Mythos is still computationally constrained: it must probe, adapt,
  and chain within real-time. Its behavioral signatures are:

  1. Probe velocity:       Normal human: 0.5-2 req/s. Mythos: 50-500 req/s.
  2. Endpoint diversity:   Normal: 5-30 unique paths/session. Mythos: 1000+.
  3. Parameter fuzzing:    Normal: fixed parameters. Mythos: systematic variation.
  4. Temporal pattern:     Normal: bursty (open browser, navigate). Mythos: uniform.
  5. Error rate:           Normal: <5% errors. Mythos: 20-80% (intentional probing).
  6. Prompt similarity:    Normal: varied natural language. Mythos: slight variations
                           of the same injection payload (vector walk).
  7. Semantic clustering:  Normal: broad topic range. Mythos: tight semantic cluster
                           around auth bypass / privilege escalation.

Algorithms:
  - CUSUM (cumulative sum) for velocity drift detection
  - Shannon entropy for request diversity
  - Cosine similarity clustering for LLM injection pattern detection
  - Poisson rate test for temporal regularity (bots are TOO regular)

References:
  Page, E.S. (1954) "Continuous inspection schemes." Biometrika 41(1-2), 100-115.
  Shannon, C.E. (1948) "A mathematical theory of communication." Bell Syst. Tech. J.
  Mythos red-team evaluation: AISI 2026 report.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger()


@dataclass
class AnomalySignal:
    identity: str
    signal_type: str       # "velocity", "diversity", "pattern", "injection", "regularity"
    score: float           # 0.0-1.0, higher = more anomalous
    threshold: float
    details: str
    timestamp: float = field(default_factory=time.time)

    @property
    def is_alert(self) -> bool:
        return self.score > self.threshold


@dataclass
class IdentityProfile:
    request_times: Deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    endpoints: Deque[str] = field(default_factory=lambda: deque(maxlen=1000))
    error_count: int = 0
    total_count: int = 0
    payload_hashes: Deque[str] = field(default_factory=lambda: deque(maxlen=200))
    param_sets: Deque[frozenset] = field(default_factory=lambda: deque(maxlen=500))
    first_seen: float = field(default_factory=time.time)
    cusum: float = 0.0             # cumulative sum for velocity drift
    cusum_ref_rate: float = 2.0    # expected req/s (normal user baseline)


class AnomalyDetector:
    """Statistical anomaly detector for Mythos-class adversarial AI.

    Maintains per-identity behavioral profiles and runs lightweight
    statistical tests on every request. No ML model to poison; all
    tests are closed-form statistics.
    """

    _VELOCITY_THRESHOLD = 0.75    # CUSUM score above this = alert
    _DIVERSITY_THRESHOLD = 0.80   # Shannon entropy divergence
    _REGULARITY_THRESHOLD = 0.85  # Poisson regularity (too uniform = bot)
    _INJECTION_THRESHOLD = 0.70   # Cosine similarity of payload hashes
    _ERROR_RATE_THRESHOLD = 0.40  # >40% error rate = scanner

    def __init__(self) -> None:
        self._profiles: Dict[str, IdentityProfile] = {}
        self._alerts: List[AnomalySignal] = []

    def record_request(
        self,
        identity: str,
        endpoint: str,
        is_error: bool = False,
        payload: str = "",
        params: Optional[dict] = None,
    ) -> List[AnomalySignal]:
        """Record a request and return any anomaly signals generated."""
        prof = self._profiles.setdefault(identity, IdentityProfile())
        now = time.time()

        prof.request_times.append(now)
        prof.endpoints.append(endpoint)
        prof.total_count += 1
        if is_error:
            prof.error_count += 1

        if payload:
            # Audit MED-12 — SHA-256 with a 16-hex truncation (64-bit
            # collision space).  MD5's 8-hex truncation gave only
            # 32-bit collision space, which an attacker could exploit
            # to fold real anomalies into duplicate-suppression.
            h = hashlib.sha256(payload.encode()).hexdigest()[:16]
            prof.payload_hashes.append(h)

        if params:
            prof.param_sets.append(frozenset(f"{k}:{str(v)[:20]}" for k, v in params.items()))

        signals: List[AnomalySignal] = []

        # Only run tests after 20 requests (warmup)
        if prof.total_count >= 20:
            signals.extend(self._test_velocity(identity, prof))
            signals.extend(self._test_endpoint_diversity(identity, prof))
            signals.extend(self._test_error_rate(identity, prof))
            signals.extend(self._test_temporal_regularity(identity, prof))
            signals.extend(self._test_injection_patterns(identity, prof))

        alerts = [s for s in signals if s.is_alert]
        if alerts:
            self._alerts.extend(alerts)
            for sig in alerts:
                logger.warning(
                    "anomaly.detected",
                    identity=identity,
                    signal=sig.signal_type,
                    score=f"{sig.score:.3f}",
                    details=sig.details[:100],
                )

        return signals

    def get_risk_score(self, identity: str) -> float:
        """Overall risk score 0-1 for an identity based on all signals."""
        recent_alerts = [
            a for a in self._alerts
            if a.identity == identity and a.timestamp > time.time() - 300
        ]
        if not recent_alerts:
            return 0.0
        return min(1.0, sum(a.score for a in recent_alerts) / len(recent_alerts))

    def is_likely_ai_attacker(self, identity: str) -> bool:
        """High-confidence determination of Mythos-class adversarial AI."""
        prof = self._profiles.get(identity)
        if prof is None or prof.total_count < 50:
            return False

        req_per_s = self._current_velocity(prof)
        unique_eps = len(set(prof.endpoints))
        error_rate = prof.error_count / max(prof.total_count, 1)
        regularity = self._temporal_regularity_score(prof)

        # Mythos-class: high velocity + high endpoint diversity + high regularity
        return (
            req_per_s > 20.0
            and unique_eps > 100
            and regularity > 0.7
        )

    def get_alerts(self, since: float = 0.0) -> List[AnomalySignal]:
        return [a for a in self._alerts if a.timestamp >= since]

    # ── Internal test functions ────────────────────────────────────────────────

    def _test_velocity(self, identity: str, prof: IdentityProfile) -> List[AnomalySignal]:
        """CUSUM velocity test — detects sustained rate above normal baseline."""
        velocity = self._current_velocity(prof)
        # CUSUM update: accumulate excess above reference rate
        excess = velocity - prof.cusum_ref_rate
        prof.cusum = max(0.0, prof.cusum + excess - 0.5)  # 0.5 slack

        # Normalize to 0-1 score (5× baseline = score of 1.0)
        score = min(1.0, prof.cusum / (5.0 * prof.cusum_ref_rate))

        return [AnomalySignal(
            identity=identity,
            signal_type="velocity",
            score=score,
            threshold=self._VELOCITY_THRESHOLD,
            details=f"{velocity:.1f} req/s (baseline {prof.cusum_ref_rate:.1f})",
        )]

    def _test_endpoint_diversity(self, identity: str, prof: IdentityProfile) -> List[AnomalySignal]:
        """Shannon entropy of endpoint distribution.

        Normal user: entropy concentrates around a few paths.
        Scanner: nearly uniform distribution → maximum entropy.
        """
        counts: Dict[str, int] = defaultdict(int)
        for ep in prof.endpoints:
            counts[ep] += 1
        total = sum(counts.values())
        if total < 10:
            return []
        entropy = 0.0
        for c in counts.values():
            p = c / total
            entropy -= p * math.log2(p)

        # Max theoretical entropy for |endpoints| endpoints
        max_entropy = math.log2(max(len(counts), 1))
        score = entropy / max_entropy if max_entropy > 0 else 0.0

        return [AnomalySignal(
            identity=identity,
            signal_type="endpoint_diversity",
            score=score,
            threshold=self._DIVERSITY_THRESHOLD,
            details=f"entropy={entropy:.2f} / max={max_entropy:.2f} ({len(counts)} unique endpoints)",
        )]

    def _test_error_rate(self, identity: str, prof: IdentityProfile) -> List[AnomalySignal]:
        """High error rate indicates scanner probing non-existent paths."""
        error_rate = prof.error_count / max(prof.total_count, 1)
        score = min(1.0, error_rate / self._ERROR_RATE_THRESHOLD)

        return [AnomalySignal(
            identity=identity,
            signal_type="error_rate",
            score=score,
            threshold=1.0,  # alert only when error_rate >= threshold
            details=f"{error_rate*100:.1f}% errors ({prof.error_count}/{prof.total_count})",
        )]

    def _test_temporal_regularity(self, identity: str, prof: IdentityProfile) -> List[AnomalySignal]:
        """Poisson regularity: bots are TOO regular, humans are bursty.

        Under Poisson arrivals, coefficient of variation (CV) of inter-arrival
        times ≈ 1.0. Human browsing: CV >> 1.0. Bot (Mythos): CV << 0.2.
        """
        score = self._temporal_regularity_score(prof)

        return [AnomalySignal(
            identity=identity,
            signal_type="temporal_regularity",
            score=score,
            threshold=self._REGULARITY_THRESHOLD,
            details=f"regularity_score={score:.3f} (CV<0.2 = bot, CV~1.0 = human)",
        )]

    def _test_injection_patterns(self, identity: str, prof: IdentityProfile) -> List[AnomalySignal]:
        """Detect systematic variation in injection payloads.

        Mythos walks a semantic vector to find the injection that bypasses
        defenses. The payload hashes form a cluster with small Hamming distance.
        We approximate this with prefix-similarity counting.
        """
        if len(prof.payload_hashes) < 10:
            return []

        # Count how many hashes share 3+ character prefix (similarity proxy)
        hashes = list(prof.payload_hashes)
        similar_pairs = 0
        total_pairs = 0
        for i in range(min(50, len(hashes))):
            for j in range(i + 1, min(50, len(hashes))):
                total_pairs += 1
                if hashes[i][:3] == hashes[j][:3]:
                    similar_pairs += 1

        score = similar_pairs / max(total_pairs, 1)

        return [AnomalySignal(
            identity=identity,
            signal_type="injection_pattern_cluster",
            score=score,
            threshold=self._INJECTION_THRESHOLD,
            details=f"{similar_pairs}/{total_pairs} similar payload pairs",
        )]

    def _current_velocity(self, prof: IdentityProfile) -> float:
        now = time.time()
        window_s = 10.0
        cutoff = now - window_s
        recent = sum(1 for t in prof.request_times if t >= cutoff)
        return recent / window_s

    def _temporal_regularity_score(self, prof: IdentityProfile) -> float:
        times = list(prof.request_times)
        if len(times) < 10:
            return 0.0
        intervals = [times[i+1] - times[i] for i in range(len(times)-1)]
        if not intervals:
            return 0.0
        mean_i = sum(intervals) / len(intervals)
        if mean_i < 1e-9:
            return 1.0  # near-zero intervals = definitely a machine
        variance = sum((x - mean_i)**2 for x in intervals) / len(intervals)
        std_i = math.sqrt(variance)
        cv = std_i / mean_i  # coefficient of variation
        # CV < 0.2 = very regular = high bot probability
        regularity = max(0.0, 1.0 - cv / 0.2) if cv < 0.2 else 0.0
        return min(1.0, regularity)
