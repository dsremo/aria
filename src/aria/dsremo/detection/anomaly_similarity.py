"""Anomaly similarity and novelty detection.

Provides fingerprinting for anomalies so AI systems can answer:
"Is this anomaly NOVEL (never seen before) or RECURRENT (same pattern
as Event #47 three months ago)?"

Each anomaly is represented as a feature vector:
    - Which detectors fired (binary 12-vector)
    - Subsystem (one-hot)
    - Confidence score
    - Severity level

Similarity is computed via cosine distance between fingerprints.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from aria.dsremo.core.models import Anomaly

# All detector names in canonical order
_DETECTOR_NAMES = [
    "cusum", "ewma", "statistical", "changepoint", "isolation_forest",
    "variance", "lstm", "tcn", "trend_velocity", "matrix_profile",
    "correlation_graph", "bocpd",
]

_SUBSYSTEMS = ["eps", "adcs", "thermal", "comms", "unknown"]

_SEV_MAP = {"nominal": 0.0, "watch": 0.33, "warning": 0.67, "critical": 1.0}


@dataclass(frozen=True)
class AnomalyFingerprint:
    """Fixed-length feature vector for an anomaly."""
    vector: tuple[float, ...]
    anomaly_id: str


def fingerprint(anomaly: Anomaly) -> AnomalyFingerprint:
    """Create a fingerprint from an Anomaly object."""
    # Detector binary features
    triggered = set(anomaly.detectors_triggered)
    det_vec = [1.0 if d in triggered else 0.0 for d in _DETECTOR_NAMES]

    # Subsystem one-hot
    sub = anomaly.subsystem.lower() if anomaly.subsystem else "unknown"
    sub_vec = [1.0 if s == sub else 0.0 for s in _SUBSYSTEMS]

    # Confidence and severity
    conf = [anomaly.confidence]
    sev = [_SEV_MAP.get(anomaly.severity.value, 0.0)]

    vector = tuple(det_vec + sub_vec + conf + sev)
    return AnomalyFingerprint(vector=vector, anomaly_id=anomaly.id)


def cosine_similarity(a: AnomalyFingerprint, b: AnomalyFingerprint) -> float:
    """Cosine similarity between two anomaly fingerprints."""
    dot = sum(x * y for x, y in zip(a.vector, b.vector))
    mag_a = math.sqrt(sum(x * x for x in a.vector))
    mag_b = math.sqrt(sum(x * x for x in b.vector))
    if mag_a < 1e-12 or mag_b < 1e-12:
        return 0.0
    return dot / (mag_a * mag_b)


class AnomalyMemory:
    """Stores historical anomaly fingerprints for novelty detection."""

    def __init__(self, max_size: int = 1000) -> None:
        self._fingerprints: list[AnomalyFingerprint] = []
        self._max_size = max_size

    def add(self, anomaly: Anomaly) -> None:
        fp = fingerprint(anomaly)
        self._fingerprints.append(fp)
        if len(self._fingerprints) > self._max_size:
            self._fingerprints = self._fingerprints[-self._max_size:]

    def find_similar(
        self, anomaly: Anomaly, threshold: float = 0.85, top_k: int = 5,
    ) -> list[tuple[str, float]]:
        """Find historical anomalies similar to the given one.

        Returns:
            List of (anomaly_id, similarity_score) sorted by similarity desc.
        """
        fp = fingerprint(anomaly)
        scored = [
            (hfp.anomaly_id, cosine_similarity(fp, hfp))
            for hfp in self._fingerprints
            if hfp.anomaly_id != anomaly.id
        ]
        scored.sort(key=lambda x: -x[1])
        return [(aid, s) for aid, s in scored[:top_k] if s >= threshold]

    def is_novel(self, anomaly: Anomaly, threshold: float = 0.85) -> bool:
        """Return True if no historical anomaly is similar above threshold."""
        return len(self.find_similar(anomaly, threshold, top_k=1)) == 0

    @property
    def size(self) -> int:
        return len(self._fingerprints)


# Singleton
_memory = AnomalyMemory()


def get_anomaly_memory() -> AnomalyMemory:
    return _memory
