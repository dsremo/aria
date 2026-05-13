"""Total Δv budget reconciliation (§4.5 of A3 scope).

Aggregates all contributions to the departure Δv — chemical LEO raise,
fusion burn, gravitational slingshot, Oberth perihelion burn, and
laser-sail push — and checks that their sum meets the required target
(typically `v_target − v_earth_heliocentric ≈ 0.1 c − 29.78 km/s`).

This is pure bookkeeping; the underlying physics is derived in the
other modules in this package. The only "rule" here is that no single
contribution is double-counted and the total Δv has a design margin
applied.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DepartureDeltaVBudget:
    """Departure Δv budget with explicit contribution bookkeeping.

    All contributions are positive magnitudes in m/s. The caller adds
    segments via ``add_segment`` (or the explicit convenience methods)
    and then calls ``summary``/``is_closed`` to check feasibility
    against ``target_delta_v_m_s``.
    """

    target_delta_v_m_s: float
    design_margin_fraction: float = 0.10  # 10% margin (AIAA S-120 guideline)
    segments: dict[str, float] = field(default_factory=dict)

    # --- explicit contribution accessors ---
    def add_segment(self, name: str, delta_v_m_s: float) -> None:
        if delta_v_m_s < 0.0:
            raise ValueError(
                f"Δv contribution must be non-negative; got {delta_v_m_s} "
                f"for segment '{name}'"
            )
        if name in self.segments:
            raise ValueError(f"segment '{name}' already recorded; names must be unique")
        self.segments[name] = delta_v_m_s

    def add_leo_escape(self, delta_v_m_s: float) -> None:
        self.add_segment("LEO_escape_chemical", delta_v_m_s)

    def add_fusion_burn(self, delta_v_m_s: float) -> None:
        self.add_segment("fusion_burn", delta_v_m_s)

    def add_slingshot(self, body: str, delta_v_m_s: float) -> None:
        self.add_segment(f"slingshot_{body}", delta_v_m_s)

    def add_oberth_burn(self, delta_v_m_s: float) -> None:
        self.add_segment("oberth_perihelion", delta_v_m_s)

    def add_laser_push(self, delta_v_m_s: float) -> None:
        self.add_segment("laser_sail_push", delta_v_m_s)

    # --- reporting ---
    @property
    def total_delta_v_m_s(self) -> float:
        return sum(self.segments.values())

    @property
    def required_with_margin_m_s(self) -> float:
        return self.target_delta_v_m_s * (1.0 + self.design_margin_fraction)

    @property
    def margin_m_s(self) -> float:
        return self.total_delta_v_m_s - self.required_with_margin_m_s

    @property
    def is_closed(self) -> bool:
        return self.total_delta_v_m_s >= self.required_with_margin_m_s

    def summary(self) -> dict[str, float | bool]:
        """Return a plain dict for logging / reporting."""
        return {
            "target_delta_v_m_s": self.target_delta_v_m_s,
            "design_margin_fraction": self.design_margin_fraction,
            "required_with_margin_m_s": self.required_with_margin_m_s,
            "segments": dict(self.segments),
            "total_delta_v_m_s": self.total_delta_v_m_s,
            "margin_m_s": self.margin_m_s,
            "is_closed": self.is_closed,
        }
