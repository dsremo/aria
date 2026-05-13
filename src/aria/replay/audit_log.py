from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class AuditLogger:
    path: Path
    _file: Optional[Any] = None
    _lock: threading.Lock = threading.Lock()

    def open(self) -> None:
        with self._lock:
            if self._file is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.flush()
                self._file.close()
                self._file = None

    def write_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            if self._file is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = self.path.open("a", encoding="utf-8")
            payload = dict(event)
            if "ts" not in payload:
                payload["ts"] = time.time()
            self._file.write(json.dumps(payload, default=str) + "\n")
            self._file.flush()


def replay_audit_events_from(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def loop_outcome_to_event(outcome: Any, scenario_id: str) -> dict[str, Any]:
    return {
        "scenario": scenario_id,
        "anomaly": {
            "get_seconds": outcome.anomaly.detected_at_get_s,
            "parameter": outcome.anomaly.parameter,
            "value": outcome.anomaly.value,
            "severity": outcome.anomaly.severity,
            "score": outcome.anomaly.score,
            "detector": outcome.anomaly.detector_name,
            "reason": outcome.anomaly.reason,
        },
        "advisor": {
            "label": getattr(outcome.advisor, "raw_response", "") and "advisor" or "advisor",
            "proposed_action": outcome.advisor.proposed_action if outcome.advisor else "",
            "rationale": outcome.advisor.rationale if outcome.advisor else "",
            "confidence": outcome.advisor.confidence if outcome.advisor else 0.0,
            "elapsed_s": outcome.elapsed_advisor_s,
            "steps": list(outcome.advisor.immediate_steps) if outcome.advisor else [],
        } if outcome.advisor else None,
        "monitor": {
            "decision": outcome.monitor.decision,
            "reason": outcome.monitor.reason,
            "provider": outcome.monitor.provider_label,
        } if outcome.monitor else None,
        "translation": {
            "status": outcome.translation.status,
            "subsystem": outcome.translation.subsystem,
            "hal_primitive": (
                outcome.translation.hal_command.primitive
                if outcome.translation.hal_command else None
            ),
            "residual": outcome.translation.residual_reason,
        } if outcome.translation else None,
        "hal_applied": outcome.hal_command,
    }
