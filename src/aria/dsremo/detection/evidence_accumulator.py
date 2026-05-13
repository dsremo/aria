"""V3-H5: Sequential evidence accumulation across detection cycles.

PROBLEM: anomaly_confidence is computed independently for each cycle.
A sequence of 10 WATCH-level scores (0.52, 0.54, 0.51...) each below
WARNING threshold produces no WARNING, despite strong cumulative evidence.

SOLUTION: Maintain a running belief state per channel using Dempster-Shafer
temporal accumulation:

    accumulated_confidence = 1 - Π_{k=t-W}^{t} (1 - confidence_k)^{w_k}

where w_k is a recency weight (exponential decay).

This captures "P(at least one of the last W cycles is a true anomaly)"
rather than "is THIS cycle an anomaly?"

Reference: Dempster, A.P. (1967). "Upper and lower probabilities induced
           by a multivalued mapping." Annals of Mathematical Statistics.
"""

from __future__ import annotations

import math
from collections import deque

import structlog

logger = structlog.get_logger()


class EvidenceAccumulator:
    """Per-channel temporal evidence accumulation.

    Usage:
        acc = EvidenceAccumulator(window=20, decay=0.9)
        # Called each detection cycle:
        acc_conf = acc.update("SAT1:battery_voltage", cycle_confidence=0.52)
        # acc_conf is the accumulated confidence over the window.
    """

    def __init__(
        self,
        window: int = 20,    # ESTIMATE — 20-cycle evidence window (~20 s at 1 Hz); Dempster 1967 Ann Math Stat 38 325: accumulation window balances recency and stability
        decay: float = 0.9,  # ESTIMATE — 0.9 exponential recency decay; Holt 1957 ONR Memo 52: 0.9 ≈ half-life of 6.6 cycles; balanced for 20-cycle window
    ) -> None:
        self._window = window
        self._decay = decay
        # channel_key → deque of recent cycle confidences
        self._history: dict[str, deque[float]] = {}

    def update(self, key: str, cycle_confidence: float) -> float:
        """Feed one cycle's confidence; return accumulated confidence.

        The accumulated confidence represents the probability that at
        least one of the last `window` cycles is a true anomaly, weighted
        by recency.
        """
        hist = self._history.setdefault(key, deque(maxlen=self._window))
        hist.append(max(0.0, min(1.0, cycle_confidence)))

        # Dempster-Shafer accumulation:
        # P(at least one anomaly) = 1 - Π (1 - c_k)^(decay^age)
        log_complement = 0.0
        for i, c in enumerate(reversed(hist)):
            age = i
            w = self._decay ** age
            if c > 0:
                log_complement += w * math.log(max(1.0 - c, 1e-12))

        accumulated = 1.0 - math.exp(max(log_complement, -50.0))
        return min(1.0, max(0.0, accumulated))

    def get_accumulated(self, key: str) -> float:
        """Return current accumulated confidence without updating."""
        hist = self._history.get(key)
        if not hist:
            return 0.0

        log_complement = 0.0
        for i, c in enumerate(reversed(hist)):
            w = self._decay ** i
            if c > 0:
                log_complement += w * math.log(max(1.0 - c, 1e-12))

        return min(1.0, max(0.0, 1.0 - math.exp(max(log_complement, -50.0))))

    def reset(self, key: str | None = None) -> None:
        """Clear accumulated evidence for one or all channels."""
        if key:
            self._history.pop(key, None)
        else:
            self._history.clear()
