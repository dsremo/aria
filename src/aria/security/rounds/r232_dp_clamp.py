"""R232 — Differential-privacy noise clamp.

Threat: an analytics endpoint that reports per-user counts /
averages leaks per-user data through repeated queries — the classic
re-identification attack on Netflix prize 2007 and US Census 2020.

Defence: ``add_laplace_noise`` adds calibrated Laplace noise to a
numeric query result and tracks the cumulative privacy budget
(epsilon).  Refuses queries that would exceed the per-user budget.
"""

from __future__ import annotations

import math
import secrets
import threading
from collections import defaultdict
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


_EPSILON_BUDGETS: Dict[str, float] = defaultdict(float)
_LOCK = threading.Lock()
_DEFAULT_EPSILON_PER_QUERY = 0.5
_BUDGET_CEILING = 5.0


def laplace_sample(scale: float) -> float:
    u = (secrets.randbits(53) / (1 << 53)) - 0.5
    sign = -1.0 if u < 0 else 1.0
    return -scale * sign * math.log(1 - 2 * abs(u) + 1e-15)


def add_laplace_noise(
    value: float, *, sensitivity: float = 1.0, epsilon: float = _DEFAULT_EPSILON_PER_QUERY,
    subject_id: str = "default",
) -> Tuple[float, float, str]:
    """Returns ``(noisy_value, remaining_budget, reason)``."""
    with _LOCK:
        used = _EPSILON_BUDGETS[subject_id]
        if used + epsilon > _BUDGET_CEILING:
            return value, _BUDGET_CEILING - used, "dp.budget_exhausted"
        _EPSILON_BUDGETS[subject_id] += epsilon
        remaining = _BUDGET_CEILING - _EPSILON_BUDGETS[subject_id]
    scale = sensitivity / epsilon
    noisy = value + laplace_sample(scale)
    return noisy, remaining, "ok"


def reset_budgets() -> None:
    with _LOCK:
        _EPSILON_BUDGETS.clear()


def remaining_budget(subject_id: str) -> float:
    with _LOCK:
        return _BUDGET_CEILING - _EPSILON_BUDGETS.get(subject_id, 0.0)


register(DefencePlugin(
    round_id="R232",
    name="dp_clamp",
    description="Laplace noise + per-subject epsilon budget for analytics queries.",
))
