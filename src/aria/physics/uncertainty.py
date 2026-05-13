"""Honest-uncertainty tagging for ARIA predictions.

Companion to ``docs/UNCERTAINTY.md`` — gives every multi-decade /
out-of-window prediction a runtime confidence tier so the operator
UI and the audit chain can both surface it.

Usage::

    from aria.physics.uncertainty import (
        ConfidenceTier, Prediction, tag_prediction,
    )

    p = tag_prediction(
        value=0.42,
        tier=ConfidenceTier.TIER_C,
        units="Sv/yr",
        model="Cucinotta 2014 GCR LET-Q model",
        falsification_dataset="full TEPC + DNA assay on Mars EVA crew",
        notes="±50 % per Cucinotta 2024 vs 2014 inter-model spread",
    )
    p.value          # 0.42
    p.tier           # ConfidenceTier.TIER_C
    p.is_speculative # True
    p.to_dict()      # JSON-serialisable for /api telemetry

Tier rules — see ``docs/UNCERTAINTY.md``:
  TIER_A  validation data exists in window
  TIER_B  extrapolation across factor ≤ 10
  TIER_C  extrapolation > 10 ×, or no flight validation
  TIER_D  no model exists — do NOT quote

The ``forbid_d_quote`` helper raises if a TIER_D prediction is asked
to render as a number; this is the runtime version of the doc rule.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


class ConfidenceTier(str, enum.Enum):
    TIER_A = "A"     # validated in window
    TIER_B = "B"     # extrapolation ≤ 10×
    TIER_C = "C"     # speculative / extrapolation > 10×
    TIER_D = "D"     # no model — do not quote

    @property
    def is_speculative(self) -> bool:
        return self in (ConfidenceTier.TIER_C, ConfidenceTier.TIER_D)

    @property
    def label(self) -> str:
        return {
            ConfidenceTier.TIER_A: "validated",
            ConfidenceTier.TIER_B: "extrapolated",
            ConfidenceTier.TIER_C: "speculative",
            ConfidenceTier.TIER_D: "no-model",
        }[self]


@dataclass(frozen=True)
class Prediction:
    """A tagged numerical prediction.

    The dataclass is frozen so an audit trail can't mutate it.  The
    JSON form (`.to_dict()`) is what /api endpoints + the React UI
    render — operators see the tier badge alongside the value.
    """
    value: Any
    tier: ConfidenceTier
    units: str = ""
    model: str = ""
    falsification_dataset: str = ""
    confidence_interval: Optional[tuple[float, float]] = None
    notes: str = ""

    @property
    def is_speculative(self) -> bool:
        return self.tier.is_speculative

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tier"] = self.tier.value
        d["tier_label"] = self.tier.label
        if self.confidence_interval is not None:
            d["confidence_interval"] = list(self.confidence_interval)
        return d


def tag_prediction(
    value: Any,
    tier: ConfidenceTier,
    units: str = "",
    model: str = "",
    falsification_dataset: str = "",
    confidence_interval: Optional[tuple[float, float]] = None,
    notes: str = "",
) -> Prediction:
    """Helper: build a :class:`Prediction` with full provenance."""
    return Prediction(
        value=value, tier=tier, units=units, model=model,
        falsification_dataset=falsification_dataset,
        confidence_interval=confidence_interval, notes=notes,
    )


class TierDQuotedError(RuntimeError):
    """Raised when a TIER_D prediction is asked for its value."""


def forbid_d_quote(p: Prediction) -> Any:
    """Return ``p.value``, raising if the prediction is TIER_D.

    Used at API surfaces to prevent silently-zero predictions from
    leaking into operator dashboards.  Caller should catch this and
    render the tier label + the falsification path instead.
    """
    if p.tier is ConfidenceTier.TIER_D:
        raise TierDQuotedError(
            f"TIER_D prediction asked for numeric value; model={p.model!r} "
            f"falsification_dataset={p.falsification_dataset!r}.  "
            f"Render the tier label + path to falsification instead."
        )
    return p.value
