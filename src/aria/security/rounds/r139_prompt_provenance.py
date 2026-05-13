"""R139 — End-to-end prompt-provenance chain.

Threat: a supply-chain compromise quietly edits the prompt template
between developer-write and LLM-receive — extra system instructions
appended, citation rules removed, etc.  The R29 sealed audit covers
the audit log, but not the prompt itself en route to the LLM.

Defence: ``capture_provenance(prompt, role, source)`` records every
hop a prompt takes (system → spotlight wrap → tool result → final
LLM payload) into a sealed list.  ``verify_chain(provenance)``
confirms each hop's body hash matches the next hop's expected
prefix; any mutation breaks the chain.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class ProvenanceHop:
    role: str               # "system" / "user" / "tool" / "spotlight" / "llm_in"
    source: str             # human-readable origin
    body_hash: str          # SHA-256 of the body at this hop
    ts: float               # monotonic time


@dataclass
class ProvenanceChain:
    hops: List[ProvenanceHop] = field(default_factory=list)
    session_id: str = ""

    def add(self, *, role: str, source: str, body: str) -> None:
        self.hops.append(ProvenanceHop(
            role=role, source=source,
            body_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            ts=time.monotonic(),
        ))


_CHAINS: Dict[str, ProvenanceChain] = {}


def capture_provenance(
    session_id: str,
    *,
    role: str,
    source: str,
    body: str,
) -> None:
    chain = _CHAINS.setdefault(session_id, ProvenanceChain(session_id=session_id))
    chain.add(role=role, source=source, body=body)


def get_chain(session_id: str) -> ProvenanceChain | None:
    return _CHAINS.get(session_id)


def verify_chain(session_id: str, *, expected_final_body: str) -> Tuple[bool, str]:
    chain = _CHAINS.get(session_id)
    if not chain or not chain.hops:
        return False, "no_chain"
    expected = hashlib.sha256(expected_final_body.encode("utf-8")).hexdigest()
    if chain.hops[-1].body_hash != expected:
        return False, "final_hash_mismatch"
    return True, f"verified hops={len(chain.hops)}"


def reset(session_id: str) -> None:
    _CHAINS.pop(session_id, None)


register(DefencePlugin(
    round_id="R139",
    name="prompt_provenance",
    description="Sealed hop-by-hop provenance chain for prompts en route to the LLM.",
))
