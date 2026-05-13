"""R344 — Defence-in-depth multiplier check.

Threat: a class defended by a single round, no matter how good, has
no defence-in-depth.  Removing the round = full breach surface.

Defence: walks R343 coverage map and returns classes with fewer than
``min_layers`` defenders.  Operators escalate these for reinforcement
in the next planning cycle.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_defense_in_depth(*, min_layers: int = 3) -> Tuple[bool, List[Dict[str, object]]]:
    from aria.security.rounds.r343_coverage_map import _CLASSES
    weak: List[Dict[str, object]] = []
    for class_name, rounds in _CLASSES.items():
        if len(rounds) < min_layers:
            weak.append({
                "class": class_name,
                "layers": len(rounds),
                "defenders": list(rounds),
                "shortfall": min_layers - len(rounds),
            })
    return not weak, weak


def render_audit_md(min_layers: int = 3) -> str:
    ok, weak = audit_defense_in_depth(min_layers=min_layers)
    lines = [
        f"# Defence-in-depth audit (min_layers={min_layers})",
        f"all_classes_pass: {ok}",
        "",
        "| Class | Layers | Defenders | Shortfall |",
        "|-------|--------|-----------|-----------|",
    ]
    for w in weak:
        lines.append(
            f"| {w['class']} | {w['layers']} | "
            f"{', '.join(w['defenders'])} | {w['shortfall']} |"
        )
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R344",
    name="defense_in_depth",
    description="Audit threat classes with fewer than min_layers defenders.",
))
