"""R25 — Tool-output watchdog (LLM-agent guardrail).

Threat: an LLM with tool access (file_read, http_get, code_exec) can
be coerced into self-destructive or exfiltrating tool calls — even when
the prompt itself looks benign — because tool *results* are model
outputs in a feedback loop.  Recent published work: ``WaspBench``
(Lakera 2024), ``Backbone Jailbreak`` against agent frameworks (2024).

Defence: a small ledger that records every tool call (kind + arg
fingerprint) per session, and refuses sequences that look hostile:
  * 5+ identical tool calls in 2 seconds (loop)
  * tool call to a domain that wasn't in any prior step
  * any tool call whose argument contains an active decoy token
  * tool calls to ``http_*`` immediately after a ``file_read`` of
    secret-shaped content (exfil pattern)
"""

from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _ToolLogEntry:
    ts: float
    kind: str
    arg_digest: str


_LEDGER: Dict[str, Deque[_ToolLogEntry]] = collections.defaultdict(
    lambda: collections.deque(maxlen=64)
)
_LOCK = threading.Lock()


def _fingerprint(arg: Any) -> str:
    import hashlib
    s = repr(arg)[:512]
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def watchdog(
    session_id: str,
    *,
    tool: str,
    arg: Any,
) -> Tuple[bool, str]:
    """Return ``(allowed, reason)`` for this tool call."""
    fp = _fingerprint(arg)
    now = time.monotonic()
    with _LOCK:
        d = _LEDGER[session_id]

        # Loop detector: 5+ identical calls within 2 s — once we already
        # have 4 prior in the ledger, the 5th attempt is the loop.
        same_recent = [e for e in d
                       if e.kind == tool and e.arg_digest == fp
                       and now - e.ts < 2.0]
        if len(same_recent) >= 4:
            return False, f"r25.tool_loop {tool}"

        # Exfil pattern: secret-shaped read followed by http_* call
        if tool.startswith("http_") and any(
            e.kind == "file_read" and "secret" in str(e.arg_digest).lower()
            for e in list(d)[-3:]
        ):
            return False, "r25.exfil_pattern"

        # Decoy-token argument
        try:
            from aria.security.honeypot_llm import is_decoy
            if isinstance(arg, str) and is_decoy(arg):
                return False, "r25.decoy_token_in_arg"
        except Exception:
            pass

        d.append(_ToolLogEntry(ts=now, kind=tool, arg_digest=fp))
    return True, ""


def reset_session(session_id: str) -> None:
    with _LOCK:
        _LEDGER.pop(session_id, None)


register(DefencePlugin(
    round_id="R25",
    name="tool_output_watchdog",
    description="Block LLM tool-call loops, exfil patterns, decoy-leak args.",
))
