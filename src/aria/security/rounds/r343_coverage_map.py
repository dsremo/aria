"""R343 — Per-round threat-class coverage map.

Threat: with 350+ rounds, leaders can't tell which threat *classes*
have multiple defenders vs which are single-point-of-failure.  A
coverage map answers "if I lose round R-X, what survives?".

Defence: a static threat-class → round mapping.  ``coverage_for_class``
returns the rounds that defend a given class; ``single_point_classes``
returns classes with only one defender (the SPoF list).
"""

from __future__ import annotations

from typing import Dict, List

from aria.security.plugins import DefencePlugin, register


_CLASSES: Dict[str, List[str]] = {
    "auth_bypass":           ["R3", "R5", "R63", "R64", "R161"],
    "credential_theft":      ["R1", "R2", "R63", "R65", "R195"],
    "injection_classical":   ["R11", "R12", "R13", "R14", "R15", "R272"],
    "llm_jailbreak":         ["R22", "R24", "R136", "R137", "R187", "R190"],
    "dos":                   ["R31", "R32", "R34", "R36", "R39", "R287", "R290"],
    "supply_chain":          ["R41", "R42", "R43", "R44", "R114", "R121", "R302", "R303", "R311"],
    "exfiltration":          ["R140", "R195", "R197", "R271", "R293", "R294", "R299", "R300"],
    "ot_scada":              ["R212", "R213", "R214", "R215", "R216", "R217", "R218", "R219", "R220", "R221"],
    "cloud_misconfig":       ["R122", "R123", "R124", "R125", "R126", "R127", "R128", "R129", "R130"],
    "k8s_misconfig":         ["R112", "R113", "R114", "R115", "R116", "R117", "R118", "R119", "R120", "R121"],
    "post_quantum":          ["R67", "R68", "R202", "R203", "R204", "R205", "R206", "R210", "R211"],
    "crypto_weakness":       ["R52", "R53", "R55", "R56", "R59", "R67", "R108", "R204"],
    "phishing":              ["R225", "R226", "R262", "R264", "R266"],
    "deepfake":              ["R332", "R333", "R334", "R335", "R339"],
    "insider_threat":        ["R246", "R247", "R293", "R294", "R295"],
    "data_privacy":          ["R166", "R167", "R232", "R233", "R235", "R239", "R240", "R241"],
    "browser_xss":           ["R252", "R253", "R254", "R256", "R261"],
    "session_hijack":        ["R67", "R149", "R161"],
    "rce":                   ["R13", "R72", "R73", "R74", "R75", "R76"],
    "denial_of_wallet":      ["R28", "R39", "R189", "R290"],
    "model_supply_chain":    ["R302", "R303", "R304", "R306", "R308"],
    "model_alignment":       ["R182", "R183", "R184", "R185", "R186", "R187", "R190"],
    "side_channel":          ["R109", "R208", "R299", "R310"],
    "forensics":             ["R34", "R98", "R150", "R192", "R193", "R194", "R198", "R199"],
    "compliance_evidence":   ["R162", "R163", "R164", "R165", "R249"],
}


def coverage_for_class(class_name: str) -> List[str]:
    return list(_CLASSES.get(class_name, []))


def single_point_classes() -> List[str]:
    return [c for c, rounds in _CLASSES.items() if len(rounds) <= 1]


def class_summary() -> Dict[str, int]:
    return {c: len(rounds) for c, rounds in _CLASSES.items()}


def render_summary_md() -> str:
    lines = ["| Threat class | Defender count | Rounds |", "|---|---|---|"]
    for c in sorted(_CLASSES):
        rounds = _CLASSES[c]
        lines.append(f"| {c} | {len(rounds)} | {', '.join(rounds[:8])}{'…' if len(rounds) > 8 else ''} |")
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R343",
    name="coverage_map",
    description="Static threat-class → round mapping; reveal SPoF defenders.",
))
