"""R223 — Smart-contract upgrade-key custody audit.

Threat: an upgradeable Solidity proxy (UUPS / Transparent) is one
``upgradeTo(NEW_IMPL)`` call away from the attacker swapping the
logic.  Audius 2022 lost $6M because the upgrade key was a 1-of-1
EOA; PolyNetwork 2021 ($600M) was upgrade-key compromise.

Defence: an audit helper that ingests an upgrade-admin descriptor
(EOA / multisig / timelock) and refuses production proxies whose
admin is a single EOA or a 1-of-N multisig.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class UpgradeAdmin:
    kind: str = "eoa"            # "eoa" | "multisig" | "timelock_multisig"
    threshold: int = 1
    signer_count: int = 1
    timelock_seconds: int = 0
    signers: List[str] = field(default_factory=list)


def audit_proxy_admin(admin: UpgradeAdmin) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if admin.kind == "eoa":
        issues.append("proxy.admin_is_eoa")
    if admin.kind in ("multisig", "timelock_multisig"):
        if admin.threshold < 2:
            issues.append(f"proxy.threshold_low:{admin.threshold}/{admin.signer_count}")
        if admin.signer_count < 3:
            issues.append(f"proxy.signer_count_low:{admin.signer_count}")
        if admin.kind == "timelock_multisig" and admin.timelock_seconds < 86_400 * 2:
            issues.append(f"proxy.timelock_too_short:{admin.timelock_seconds}s")
        if len(set(admin.signers)) != admin.signer_count:
            issues.append("proxy.duplicate_signers")
    if admin.kind == "multisig" and admin.timelock_seconds == 0:
        issues.append("proxy.no_timelock")
    return not issues, issues


def recommend_admin() -> str:
    return ("Use a 3-of-5 (or 4-of-7) multisig fronted by a 48-hour "
            "OpenZeppelin TimelockController; signers in HSM-backed "
            "hardware wallets, separated geographically.")


register(DefencePlugin(
    round_id="R223",
    name="proxy_upgrade_audit",
    description="Smart-contract upgrade-admin audit: refuse EOA + low-threshold + no-timelock.",
))
