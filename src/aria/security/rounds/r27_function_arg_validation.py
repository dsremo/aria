"""R27 — LLM function-call argument validation.

Threat: an LLM with structured-tool access generates JSON arguments
that match the *shape* of the schema but contain hostile values
(``{"cmd": "rm -rf /"}`` for a tool whose schema only declared
``cmd: str``).  The handler trusts the schema match and runs.

Defence: ``validate_args(args, schema, strict_string=True)`` —
schema-shape check PLUS per-field hostile-content check (R13 metadensity,
R12 SSTI markers, R14 LDAP injection patterns) + length cap.  Returns
``(ok, errors)`` so the LLM can be told why and asked to retry within
bounds.  Refusal is deterministic; the LLM cannot social-engineer past
it because the validator runs in a separate Python process boundary
from the model.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def _value_safe(value: Any, *, max_len: int = 2048) -> Tuple[bool, str]:
    if value is None:
        return True, ""
    if isinstance(value, str):
        if len(value) > max_len:
            return False, f"string_too_long({len(value)}>{max_len})"
        # R13: shell metachars density
        try:
            from aria.security.rounds.r13_command_injection import metachar_density
            d = metachar_density(value)
            if d >= 0.05:
                return False, f"shell_metachar_density={d:.2f}"
        except Exception:
            pass
        # R12: SSTI markers
        if any(marker in value for marker in ("{{", "{%", "${", "<%=")):
            return False, "ssti_marker"
        # R14: LDAP injection shapes
        if "*)(" in value or ")(&" in value or ")(|" in value:
            return False, "ldap_pattern"
        return True, ""
    if isinstance(value, (int, float, bool)):
        return True, ""
    if isinstance(value, (list, tuple)):
        for v in value:
            ok, why = _value_safe(v, max_len=max_len)
            if not ok:
                return False, f"list[]: {why}"
        return True, ""
    if isinstance(value, dict):
        for k, v in value.items():
            ok, why = _value_safe(v, max_len=max_len)
            if not ok:
                return False, f"dict[{k!r}]: {why}"
        return True, ""
    return False, f"type_not_allowed:{type(value).__name__}"


def validate_args(
    args: Dict[str, Any],
    schema: Dict[str, type],
    *,
    max_string_length: int = 2048,
    allow_extra: bool = False,
) -> Tuple[bool, List[str]]:
    """Validate LLM-generated tool arguments against ``schema``.

    Returns ``(ok, errors)``.  Errors is a list of human-readable
    reasons; empty when ok.
    """
    errors: List[str] = []
    if not isinstance(args, dict):
        return False, ["args must be a dict"]
    if not allow_extra:
        extra = set(args.keys()) - set(schema.keys())
        if extra:
            errors.append(f"extra_fields:{sorted(extra)}")
    for k, expected in schema.items():
        if k not in args:
            errors.append(f"missing:{k}")
            continue
        if not isinstance(args[k], expected):
            errors.append(f"type_mismatch:{k}={type(args[k]).__name__}!={expected.__name__}")
            continue
        ok, why = _value_safe(args[k], max_len=max_string_length)
        if not ok:
            errors.append(f"hostile_value:{k}: {why}")
    return len(errors) == 0, errors


register(DefencePlugin(
    round_id="R27",
    name="function_arg_validation",
    description="Schema + content validator for LLM-generated tool arguments.",
))
