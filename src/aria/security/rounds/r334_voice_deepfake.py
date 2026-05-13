"""R334 — Voice deepfake detection (heuristic).

Threat: voice cloning needs as little as 3 seconds of training audio.
"Hi, it's the CEO calling from a different number" social engineering
is a $25M-class category (Hong Kong CFO 2024 case).

Defence: a small heuristic scorer over per-call audio features —
unnatural breath-pause distribution, sudden bandwidth changes,
metadata mismatch between codec and container, missing background
noise.  Soft helper.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class CallSegment:
    duration_ms: float
    rms_db: float
    pause_count: int
    bandwidth_hz: float
    background_noise_db: float


def score_call(segments: List[CallSegment]) -> Tuple[float, List[str]]:
    if not segments:
        return 0.0, ["empty"]
    notes: List[str] = []
    score = 0.0

    rms = [s.rms_db for s in segments]
    if rms and statistics.pstdev(rms) < 1.5:
        score += 0.25
        notes.append(f"flat_rms:{statistics.pstdev(rms):.2f}dB")

    bw = [s.bandwidth_hz for s in segments]
    if bw and (max(bw) - min(bw)) > 4000:
        score += 0.2
        notes.append("bandwidth_swings")

    pauses_per_sec = sum(s.pause_count for s in segments) / max(1, sum(s.duration_ms for s in segments) / 1000.0)
    if pauses_per_sec < 0.05:
        score += 0.3
        notes.append(f"too_few_pauses:{pauses_per_sec:.3f}")

    bg = [s.background_noise_db for s in segments]
    if bg and statistics.mean(bg) < -55:
        score += 0.25
        notes.append(f"clean_background:{statistics.mean(bg):.1f}dB")

    return min(1.0, score), notes


register(DefencePlugin(
    round_id="R334",
    name="voice_deepfake",
    description="Voice-deepfake heuristic scorer: pause distribution + bandwidth + background floor.",
))
