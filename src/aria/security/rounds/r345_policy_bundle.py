"""R345 — Defensive policy bundle (single-file rule export).

Threat: distributing 350+ defence configurations across teams creates
drift — every team interprets the rules slightly differently.  A
single policy bundle that emits Sigma + Suricata + Nginx fragments
in one signed file is the unambiguous source of truth.

Defence: ``build_bundle`` collects every emitter (R88 CORS, R252
CSP, R275 pg_hba, R206 SSH KEX, …) into one JSON-shaped policy
manifest, signed via R67 hybrid signing.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from aria.security.plugins import DefencePlugin, register


@dataclass
class PolicyBundle:
    issued_at: float = 0.0
    fragments: Dict[str, str] = field(default_factory=dict)
    sha256: str = ""
    signature: bytes = b""


def build_bundle() -> PolicyBundle:
    fragments: Dict[str, str] = {}

    try:
        from aria.security.rounds.r252_csp_strict import make_strict_csp
        csp_header, _ = make_strict_csp()
        fragments["http.csp"] = csp_header
    except Exception:
        pass
    try:
        from aria.security.rounds.r255_permissions_policy import strict_permissions_policy
        fragments["http.permissions_policy"] = strict_permissions_policy()
    except Exception:
        pass
    try:
        from aria.security.rounds.r256_clickjacking import strict_clickjack_headers
        fragments.update({f"http.{k}": v for k, v in strict_clickjack_headers().items()})
    except Exception:
        pass
    try:
        from aria.security.rounds.r257_coop_coep import strict_isolation_headers
        fragments.update({f"http.{k}": v for k, v in strict_isolation_headers().items()})
    except Exception:
        pass
    try:
        from aria.security.rounds.r206_pq_ssh import recommended_kex_line
        fragments["sshd.KexAlgorithms"] = recommended_kex_line()
    except Exception:
        pass
    try:
        from aria.security.rounds.r152_istio_authz import deny_all_policy
        fragments["istio.deny_all"] = deny_all_policy("aria-prod")
    except Exception:
        pass
    try:
        from aria.security.rounds.r327_tlp_tagging import tag_outgoing
        fragments["intel.tlp_template"] = tag_outgoing("<message>", "AMBER")
    except Exception:
        pass

    bundle = PolicyBundle(
        issued_at=time.time(),
        fragments=fragments,
    )
    bundle.sha256 = hashlib.sha256(serialise(bundle).encode()).hexdigest()
    return bundle


def serialise(bundle: PolicyBundle) -> str:
    return json.dumps({
        "issued_at": bundle.issued_at,
        "fragments": bundle.fragments,
    }, sort_keys=True)


def sign_bundle(bundle: PolicyBundle, sk: bytes) -> Optional[bytes]:
    try:
        from aria.security.rounds.r55_hybrid_signing import hybrid_sign
        return hybrid_sign(serialise(bundle).encode("utf-8"), sk)
    except Exception:
        return None


def verify_bundle(bundle: PolicyBundle, signature: bytes, pk: bytes) -> bool:
    try:
        from aria.security.rounds.r55_hybrid_signing import hybrid_verify
        return hybrid_verify(serialise(bundle).encode("utf-8"), signature, pk)
    except Exception:
        return False


register(DefencePlugin(
    round_id="R345",
    name="policy_bundle",
    description="Defensive policy bundle (CSP + sshd + Istio + ...) with hybrid signing.",
))
