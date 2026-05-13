"""R322 — MITRE ATT&CK technique mapping.

Threat: detections without ATT&CK technique IDs are unmappable to
adversary playbooks.  The MITRE ATT&CK matrix is the lingua franca
of threat-informed defence; rounds without IDs cannot be plotted on
the heatmap.

Defence: a static map of ARIA round → ATT&CK technique IDs +
``coverage_heatmap`` returning the Tactic-by-Technique grid for
operator dashboards.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


# round_id → list of (tactic, technique_id, name)
_MAPPING: Dict[str, List[Tuple[str, str, str]]] = {
    "R1":  [("TA0006", "T1110", "Brute Force")],
    "R2":  [("TA0009", "T1552", "Unsecured Credentials")],
    "R3":  [("TA0006", "T1556", "Modify Authentication Process")],
    "R8":  [("TA0006", "T1110.004", "Credential Stuffing")],
    "R11": [("TA0001", "T1190", "Exploit Public-Facing Application")],
    "R13": [("TA0002", "T1059", "Command and Scripting Interpreter")],
    "R21": [("TA0001", "T1190", "Exploit Public-Facing Application")],
    "R22": [("TA0040", "T1499", "Endpoint DoS")],
    "R31": [("TA0040", "T1498", "Network DoS")],
    "R34": [("TA0040", "T1499.003", "Application Exhaustion Flood")],
    "R41": [("TA0001", "T1195", "Supply Chain Compromise")],
    "R42": [("TA0001", "T1195.002", "Compromise Software Supply Chain")],
    "R44": [("TA0001", "T1195.002", "Compromise Software Supply Chain")],
    "R51": [("TA0043", "T1595", "Active Scanning")],
    "R67": [("TA0006", "T1098.001", "Additional Cloud Credentials")],
    "R80": [("TA0005", "T1027", "Obfuscated Files or Information")],
    "R86": [("TA0011", "T1071", "Application Layer Protocol")],
    "R88": [("TA0006", "T1556.005", "Reversible Encryption")],
    "R94": [("TA0043", "T1595.002", "Vulnerability Scanning")],
    "R98": [("TA0005", "T1070", "Indicator Removal")],
    "R99": [("TA0040", "T1485", "Data Destruction")],
    "R102": [("TA0006", "T1542", "Pre-OS Boot")],
    "R114": [("TA0001", "T1195.002", "Compromise Software Supply Chain")],
    "R122": [("TA0006", "T1552.005", "Cloud Instance Metadata API")],
    "R124": [("TA0004", "T1078.004", "Cloud Accounts")],
    "R132": [("TA0001", "T1190", "Exploit Public-Facing Application")],
    "R140": [("TA0010", "T1567", "Exfiltration Over Web Service")],
    "R150": [("TA0005", "T1070.003", "Clear Command History")],
    "R157": [("TA0008", "T1021", "Remote Services")],
    "R161": [("TA0004", "T1068", "Exploitation for Privilege Escalation")],
    "R168": [("TA0009", "T1213", "Data from Information Repositories")],
    "R171": [("TA0040", "T1499", "Endpoint DoS")],
    "R195": [("TA0007", "T1480", "Execution Guardrails")],
    "R197": [("TA0011", "T1071", "Application Layer Protocol")],
    "R210": [("TA0006", "T1098", "Account Manipulation")],
    "R213": [("TA0008", "T1021.005", "VNC")],
    "R220": [("TA0005", "T1070.001", "Clear Windows Event Logs")],
    "R225": [("TA0001", "T1566", "Phishing")],
    "R232": [("TA0009", "T1530", "Data from Cloud Storage")],
    "R246": [("TA0001", "T1078", "Valid Accounts")],
    "R247": [("TA0011", "T1041", "Exfiltration Over C2 Channel")],
    "R262": [("TA0001", "T1566.001", "Spearphishing Attachment")],
    "R264": [("TA0001", "T1566.002", "Spearphishing Link")],
    "R271": [("TA0011", "T1071.004", "DNS")],
    "R275": [("TA0006", "T1078", "Valid Accounts")],
    "R288": [("TA0001", "T1190", "Exploit Public-Facing Application")],
    "R298": [("TA0005", "T1027.003", "Steganography")],
    "R299": [("TA0011", "T1071.001", "Web Protocols")],
    "R300": [("TA0009", "T1052", "Exfiltration Over Physical Medium")],
}


def coverage_heatmap() -> Dict[str, List[str]]:
    by_tactic: Dict[str, List[str]] = defaultdict(list)
    for techniques in _MAPPING.values():
        for tactic, tid, _ in techniques:
            if tid not in by_tactic[tactic]:
                by_tactic[tactic].append(tid)
    return dict(by_tactic)


def render_heatmap_md() -> str:
    lines = ["| Tactic | Technique IDs |", "|--------|---------------|"]
    for tactic, ids in sorted(coverage_heatmap().items()):
        lines.append(f"| {tactic} | {', '.join(sorted(ids))} |")
    return "\n".join(lines)


def techniques_for_round(round_id: str) -> List[Tuple[str, str, str]]:
    return list(_MAPPING.get(round_id.upper(), []))


register(DefencePlugin(
    round_id="R322",
    name="attack_mapping",
    description="Static MITRE ATT&CK technique mapping per ARIA round; coverage heatmap.",
))
