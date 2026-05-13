"""IPC bridges between the monitor runner process and the primary's bus.

The runner (``aria.monitor.runner``) runs as a separate process per
the §F-7 / T-V-2 threat model. The primary's ``MessageBus`` is
process-local so the runner cannot publish to it directly — a transport
is required. This module defines the transports.

Currently provided
==================

``file_publish_fn(path)`` — returns a ``publish_fn`` that writes
the heartbeat payload atomically to a JSON file. The primary's
file-bridge poller (in ``aria.main``) tails the file and re-publishes
on the local bus.

Authentication
==============

The ``HeartbeatEmitter`` already HMAC-signs ``boot_id`` per S-14 using
the shared ``ARIA_HEARTBEAT_SECRET``. The bridge is pure transport —
verification happens in the watcher. So a tampered file with a forged
boot_id is rejected by ``_verify_boot_id_signature`` regardless of how
it got there.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict

import structlog

logger = structlog.get_logger()


PublishFn = Callable[[str, Dict[str, Any]], None]


def file_publish_fn(path: str | os.PathLike) -> PublishFn:
    """Return a ``publish_fn`` that writes the payload atomically to
    ``path`` on every beat. The file is overwritten (latest-wins).

    Atomic write pattern: tmp file in the same directory → fsync →
    ``os.replace``. The primary's poller therefore never reads a
    partially-written JSON document.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    def _publish(topic: str, payload: Dict[str, Any]) -> None:
        record = {"topic": topic, "payload": payload}
        fd, tmp_name = tempfile.mkstemp(
            prefix=".heartbeat-", suffix=".tmp", dir=str(target.parent),
        )
        try:
            with os.fdopen(fd, "w") as fp:
                json.dump(record, fp)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    return _publish
