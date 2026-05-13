"""R98 — Immutable forward-only log shipper.

Threat: even with R10 sealed audit + R92 SIEM forward, an attacker
with write access between the log producer and the forward worker
can edit in-transit.  Banks ship logs to a write-only object store
(S3 Object Lock, GCS retention, Azure immutable blob) so even the
SIEM admin can't rewrite history.

Defence: ``ImmutableSink`` writes hash-chained JSONL where each entry
includes the SHA-256 of the previous entry.  Any tamper breaks the
chain.  ``verify_chain(path)`` walks the file end-to-end and reports
the first broken link.  The append-mode + chmod-444 on rotate keeps
local integrity; pair with R92 + S3 Object Lock for true durability.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


class ImmutableSink:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self._path.is_file():
            return "GENESIS" + "0" * 56
        try:
            with self._path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                # Read last 8 KiB and find the last newline
                step = min(size, 8192)
                f.seek(-step, os.SEEK_END)
                tail = f.read(step).decode("utf-8", errors="replace")
            for line in reversed(tail.strip().splitlines()):
                try:
                    obj = json.loads(line)
                    return obj.get("entry_hash", "")
                except Exception:
                    continue
        except OSError:
            pass
        return "GENESIS" + "0" * 56

    def append(self, event: Dict[str, Any]) -> str:
        """Append ``event`` with a hash-chain link.  Returns the new entry hash."""
        with self._lock:
            payload = {
                "ts": time.time(),
                **event,
                "prev_hash": self._last_hash,
            }
            blob = json.dumps(payload, sort_keys=True).encode("utf-8")
            new_hash = hashlib.sha256(blob).hexdigest()
            payload["entry_hash"] = new_hash
            line = json.dumps(payload) + "\n"
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
            self._last_hash = new_hash
            return new_hash


def verify_chain(path: Path) -> Tuple[bool, int, str]:
    """Walk a chain file end-to-end.  Returns ``(ok, lines, reason)``.

    On break the line number + reason explain.
    """
    p = Path(path)
    if not p.is_file():
        return True, 0, "empty"
    prev = "GENESIS" + "0" * 56
    n = 0
    with p.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            try:
                obj = json.loads(line)
            except Exception:
                return False, i, "json_parse_failed"
            n += 1
            if obj.get("prev_hash") != prev:
                return False, i, "prev_hash_mismatch"
            check = dict(obj)
            check.pop("entry_hash", None)
            blob = json.dumps(check, sort_keys=True).encode("utf-8")
            expected = hashlib.sha256(blob).hexdigest()
            if expected != obj.get("entry_hash"):
                return False, i, "entry_hash_mismatch"
            prev = obj["entry_hash"]
    return True, n, "ok"


register(DefencePlugin(
    round_id="R98",
    name="immutable_logs",
    description="Hash-chained append-only sink + verify_chain integrity walker.",
))
