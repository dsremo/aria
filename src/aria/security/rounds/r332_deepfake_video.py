"""R332 — Deepfake video heuristics.

Threat: face-swap / lip-sync deepfakes are routinely used for CEO-
fraud calls, KYC liveness bypass, election-season disinfo.  Per-frame
inspection at the codec level reveals statistical anomalies that
purely visual review misses.

Defence: a heuristic scorer over per-frame metadata — abnormal frame-
size variance, sudden bitrate jumps, missing motion vectors in face
regions, double-encoding artefacts — that flags suspicious clips for
analyst review.  Soft helper; not a substitute for ML detector.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class FrameMetadata:
    frame_index: int
    bytes_in_frame: int
    is_keyframe: bool
    motion_vector_count: int
    face_region_motion: int


def score_video_metadata(frames: List[FrameMetadata]) -> Tuple[float, List[str]]:
    if len(frames) < 30:
        return 0.0, ["too_few_frames"]

    notes: List[str] = []
    score = 0.0

    sizes = [f.bytes_in_frame for f in frames if not f.is_keyframe]
    if sizes:
        mean = statistics.mean(sizes) or 1.0
        stdev = statistics.pstdev(sizes)
        if stdev / mean > 0.6:
            score += 0.25
            notes.append(f"high_size_variance:{stdev / mean:.2f}")

    keyframe_gaps: List[int] = []
    last = -1
    for f in frames:
        if f.is_keyframe:
            if last >= 0:
                keyframe_gaps.append(f.frame_index - last)
            last = f.frame_index
    if keyframe_gaps and (max(keyframe_gaps) - min(keyframe_gaps)) > 30:
        score += 0.2
        notes.append("irregular_keyframes")

    face_motion = [f.face_region_motion for f in frames]
    if face_motion:
        burst_share = sum(1 for m in face_motion if m == 0) / len(face_motion)
        if burst_share > 0.4:
            score += 0.3
            notes.append(f"face_motion_quiet:{burst_share:.2f}")

    mv_share = sum(1 for f in frames if f.motion_vector_count == 0) / len(frames)
    if mv_share > 0.5:
        score += 0.25
        notes.append(f"missing_motion_vectors:{mv_share:.2f}")

    return min(1.0, score), notes


register(DefencePlugin(
    round_id="R332",
    name="deepfake_video",
    description="Per-frame metadata heuristic scorer for face-swap / lip-sync deepfakes.",
))
