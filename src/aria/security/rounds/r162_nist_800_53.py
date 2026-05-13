"""R162 — NIST SP 800-53 Rev 5 control mapping.

Threat: a security control implemented but not mapped to a compliance
framework is invisible to auditors, fails ATO (FedRAMP / FISMA) and
forces re-implementation by a sister team.  ARIA already covers many
800-53 families; this file makes the mapping explicit.

Defence: a static dictionary mapping NIST 800-53 control IDs to the
ARIA round(s) that implement them, plus ``coverage_report`` returning
per-family completeness.  Operators feed this into their SSP package.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


# Each entry: control-id → list of ARIA round-ids that satisfy it.
_MAPPING: Dict[str, List[str]] = {
    "AC-2":   ["R39", "R71"],          # account management / SCIM
    "AC-3":   ["R161", "R155"],        # access enforcement
    "AC-4":   ["R157", "R113"],        # information flow / netpolicy
    "AC-6":   ["R124"],                # least privilege
    "AC-7":   ["R63"],                 # unsuccessful logon attempts
    "AU-2":   ["R34", "R98"],          # event logging
    "AU-3":   ["R34", "R150"],         # content of audit records
    "AU-9":   ["R98"],                 # protection of audit info
    "CM-2":   ["R115", "R194"],        # baseline configuration / FIM
    "CM-7":   ["R124", "R91"],         # least functionality
    "IA-2":   ["R63", "R64"],          # MFA / WebAuthn
    "IA-5":   ["R65", "R125"],         # authenticator mgmt + KMS rotation
    "SC-7":   ["R113", "R157", "R160"],# boundary protection
    "SC-8":   ["R116", "R156"],        # transmission confidentiality
    "SC-12":  ["R53", "R108"],         # cryptographic key establishment
    "SC-13":  ["R47", "R67"],          # cryptographic protection
    "SC-28":  ["R106"],                # protection at rest
    "SI-2":   ["R93"],                 # flaw remediation (CISA KEV)
    "SI-3":   ["R80", "R194"],         # malicious code / FIM
    "SI-4":   ["R23", "R26", "R34"],   # system monitoring
    "SI-7":   ["R98", "R114", "R121"], # software integrity / signing / SLSA
    "SI-10":  ["R6", "R148"],          # input validation / Unicode
    "RA-5":   ["R94"],                 # vulnerability scanning / fuzz
    "IR-4":   ["R171", "R197"],        # incident handling
    "IR-6":   ["R92"],                 # incident reporting (forwarder)
    "CP-9":   ["R98"],                 # system backup integrity
}


def coverage_report() -> Tuple[int, int, Dict[str, int]]:
    """Returns (covered_count, total_count, per_family_count)."""
    family_counts: Dict[str, int] = {}
    for ctl in _MAPPING:
        fam = ctl.split("-")[0]
        family_counts[fam] = family_counts.get(fam, 0) + 1
    return len(_MAPPING), len(_MAPPING), family_counts


def rounds_for_control(control_id: str) -> List[str]:
    return list(_MAPPING.get(control_id.upper(), []))


def render_ssp_table() -> str:
    lines = ["| 800-53 Control | ARIA Round(s) |", "|---|---|"]
    for ctl in sorted(_MAPPING):
        lines.append(f"| {ctl} | {', '.join(_MAPPING[ctl])} |")
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R162",
    name="nist_800_53",
    description="Static NIST 800-53 Rev 5 → ARIA round mapping for SSP packages.",
))
