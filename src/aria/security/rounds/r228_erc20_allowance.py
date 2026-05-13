"""R228 — ERC-20 infinite-allowance audit.

Threat: ``approve(spender, 2**256-1)`` is the dApp UX shortcut that
hands the spender unrestricted access to the user's tokens.  When
the spender contract is later upgraded or compromised, the user's
balance is gone.  Sushi 2023 phishing variants harvested allowances
this way.

Defence: per-token-pair allowance budget.  Refuse any approve >
``soft_cap`` and require the dApp to explicitly justify near-infinite
amounts.  ``audit_allowance_grants`` walks an existing allowance
ledger and flags entries above threshold.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_SOFT_CAP = 10 ** 28               # ~10 quadrillion 18-decimal units
_NEAR_INF = 2 ** 200


def audit_approve(amount: int, *, soft_cap: int = _SOFT_CAP) -> Tuple[bool, str]:
    if amount >= _NEAR_INF:
        return False, f"erc20.infinite_allowance amount={amount}"
    if amount > soft_cap:
        return False, f"erc20.over_soft_cap amount={amount} cap={soft_cap}"
    return True, "ok"


def audit_existing_allowances(
    grants: Dict[Tuple[str, str], int],     # (token, spender) -> amount
    *,
    soft_cap: int = _SOFT_CAP,
) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for (token, spender), amount in grants.items():
        ok, why = audit_approve(amount, soft_cap=soft_cap)
        if not ok:
            issues.append(f"{token}/{spender}:{why}")
    return not issues, issues


register(DefencePlugin(
    round_id="R228",
    name="erc20_allowance",
    description="ERC-20 approve audit; refuse infinite + over-soft-cap allowances.",
))
