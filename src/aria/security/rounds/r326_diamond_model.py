"""R326 — Diamond Model attribution structuring.

Threat: incident reports written as free text are unsearchable +
incomparable.  The Diamond Model (DoD JTF-GNO 2013) gives four
vertices — adversary, capability, infrastructure, victim — every
intrusion is one event ⇒ comparable across cases.

Defence: a strongly-typed ``DiamondEvent`` + canonicalised JSON
emitter so events feed naturally into R249 audit chain or external
ATT&CK tooling.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List

from aria.security.plugins import DefencePlugin, register


@dataclass
class DiamondEvent:
    timestamp: float
    adversary: str
    capability: str
    infrastructure: str
    victim: str
    metadata: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.5
    notes: str = ""


def make_event(
    *, adversary: str, capability: str, infrastructure: str, victim: str,
    confidence: float = 0.5, metadata: Dict[str, str] = None, notes: str = "",
) -> DiamondEvent:
    return DiamondEvent(
        timestamp=time.time(),
        adversary=adversary, capability=capability,
        infrastructure=infrastructure, victim=victim,
        metadata=dict(metadata or {}), confidence=confidence, notes=notes,
    )


def canonical_json(event: DiamondEvent) -> str:
    return json.dumps(asdict(event), sort_keys=True, default=str)


def cluster_by_vertex(events: List[DiamondEvent], vertex: str) -> Dict[str, List[DiamondEvent]]:
    if vertex not in ("adversary", "capability", "infrastructure", "victim"):
        raise ValueError("R326: vertex must be one of the four")
    out: Dict[str, List[DiamondEvent]] = {}
    for e in events:
        key = getattr(e, vertex)
        out.setdefault(key, []).append(e)
    return out


register(DefencePlugin(
    round_id="R326",
    name="diamond_model",
    description="Diamond Model intrusion-event encoder + per-vertex clustering.",
))
