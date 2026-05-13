"""R163 — SOC 2 Type II evidence collector.

Threat: SOC 2 audits ask for *artefacts* (logs, config snapshots,
access reviews) covering a 6-12 month window.  Without automated
collection, teams scramble at audit time and produce inconsistent
evidence.

Defence: a JSON evidence-bundle builder mapping the five Trust
Services Criteria (Security, Availability, Confidentiality, Processing
Integrity, Privacy) to the ARIA round whose state should be captured.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from aria.security.plugins import DefencePlugin, register


_TSC: Dict[str, List[str]] = {
    "CC6.1": ["R39", "R71", "R161"],     # logical access
    "CC6.6": ["R64", "R63"],             # MFA
    "CC6.7": ["R157", "R113"],           # transmission of data
    "CC6.8": ["R80", "R194"],            # malware / integrity
    "CC7.1": ["R23", "R26", "R94"],      # vuln + monitoring
    "CC7.2": ["R34", "R150"],            # security incidents detection
    "CC7.3": ["R171"],                   # incident response
    "CC7.4": ["R99"],                    # incident recovery (kill switch)
    "CC8.1": ["R115", "R114"],           # change mgmt / signing
    "A1.2":  ["R98"],                    # availability / immutable logs
    "C1.2":  ["R97"],                    # data classification
    "P1.1":  ["R166", "R167"],           # privacy notice / DSAR
}


def collect_evidence(timestamp: float = 0.0) -> Dict[str, Any]:
    ts = timestamp or time.time()
    return {
        "framework": "SOC2-TypeII",
        "collected_at": ts,
        "criteria": {ctl: list(rounds) for ctl, rounds in _TSC.items()},
        "version": "ARIA-R163-v1",
    }


def render_evidence_json() -> str:
    return json.dumps(collect_evidence(), indent=2, sort_keys=True)


register(DefencePlugin(
    round_id="R163",
    name="soc2_evidence",
    description="SOC 2 Type II Trust-Services-Criteria → ARIA round evidence map.",
))
