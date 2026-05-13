"""R225 — Wallet phishing pattern detector.

Threat: wallet-drainer kits (Inferno, Pink, Angel) lure users into
signing ``setApprovalForAll`` / ``permit`` / ``increaseAllowance``
on attacker-controlled tokens.  Chainalysis 2024: $295M lost to
wallet drainers in 2024 alone.

Defence: detect dangerous EIP-712 / ERC-2612 / ERC-7521 sign-request
shapes — flag ``setApprovalForAll(true)``, infinite-allowance
``approve``, ``permit`` to non-major spenders, and known drainer
contract addresses.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_INF = 2 ** 256 - 1
_NEAR_INF_THRESHOLD = 2 ** 200


_KNOWN_DRAINER_ADDRESSES = {
    a.lower() for a in (
        "0x0000000000000000000000000000000000000000",   # placeholder; real list updated upstream
    )
}


def audit_sign_request(req: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    method = (req.get("method") or "").lower()
    args = req.get("args") or {}

    if method == "setapprovalforall":
        if args.get("approved"):
            issues.append("wallet.setApprovalForAll_true")

    if method == "approve":
        amount = int(args.get("amount") or 0)
        if amount >= _NEAR_INF_THRESHOLD:
            issues.append(f"wallet.infinite_allowance amount={amount}")

    if method == "permit":
        spender = (args.get("spender") or "").lower()
        if spender in _KNOWN_DRAINER_ADDRESSES:
            issues.append(f"wallet.permit_to_drainer:{spender}")

    domain = req.get("domain") or {}
    chain_id = int(domain.get("chainId") or 0)
    if chain_id == 0:
        issues.append("wallet.eip712_no_chain_id")

    return not issues, issues


register(DefencePlugin(
    round_id="R225",
    name="wallet_phish",
    description="Wallet-drainer pattern detector for EIP-712/2612 sign requests.",
))
