"""Resource inventory tracking and depletion forecasting for long-duration missions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Resource:
    """A single trackable resource aboard the vessel."""

    name: str
    quantity_kg: float
    unit: str = "kg"
    consumption_rate_per_day: float = 0.0
    critical_threshold_kg: float = 0.0
    can_be_recycled: bool = False
    recycling_efficiency: float = 0.0  # 0.0 - 1.0

    def __post_init__(self) -> None:
        if self.quantity_kg < 0:
            raise ValueError(f"quantity_kg cannot be negative for '{self.name}'")
        if not 0.0 <= self.recycling_efficiency <= 1.0:
            raise ValueError(
                f"recycling_efficiency must be 0.0-1.0 for '{self.name}'"
            )


class ResourceInventory:
    """Tracks all material resources for a mission."""

    def __init__(self, resources: Optional[List[Resource]] = None) -> None:
        self._resources: Dict[str, Resource] = {}
        for r in resources or []:
            self._resources[r.name] = r

    # -- mutators ----------------------------------------------------------

    def consume(self, name: str, amount: float) -> float:
        """Consume *amount* kg of *name*. Returns the actual amount consumed."""
        r = self._get(name)
        if amount < 0:
            raise ValueError("consume amount must be non-negative")
        actual = min(amount, r.quantity_kg)
        r.quantity_kg -= actual
        return actual

    def produce(self, name: str, amount: float) -> None:
        """Add *amount* kg of *name* (e.g. via recycling or synthesis)."""
        r = self._get(name)
        if amount < 0:
            raise ValueError("produce amount must be non-negative")
        r.quantity_kg += amount

    # -- queries -----------------------------------------------------------

    def get_days_remaining(self, name: str) -> float:
        """Days until *name* is exhausted at current consumption rate.

        Returns ``float('inf')`` when consumption rate is zero.
        If the resource can be recycled the effective consumption rate is
        reduced by ``recycling_efficiency``.
        """
        r = self._get(name)
        if r.consumption_rate_per_day <= 0:
            return float("inf")
        effective_rate = r.consumption_rate_per_day * (1.0 - r.recycling_efficiency)
        if effective_rate <= 0:
            return float("inf")
        return r.quantity_kg / effective_rate

    def get_critical_resources(self) -> List[Resource]:
        """Return resources at or below their critical threshold."""
        return [
            r for r in self._resources.values()
            if r.quantity_kg <= r.critical_threshold_kg
        ]

    def get_all_resources(self) -> List[Resource]:
        """Return a list of every tracked resource."""
        return list(self._resources.values())

    # -- internals ---------------------------------------------------------

    def _get(self, name: str) -> Resource:
        try:
            return self._resources[name]
        except KeyError:
            raise KeyError(f"Unknown resource: '{name}'") from None


class ResourceForecaster:
    """Stateless forecasting utilities that operate on a ResourceInventory."""

    @staticmethod
    def predict_depletion(inventory: ResourceInventory) -> Dict[str, float]:
        """Map every resource name to its estimated days until depletion."""
        return {
            r.name: inventory.get_days_remaining(r.name)
            for r in inventory.get_all_resources()
        }

    @staticmethod
    def get_critical_in_days(
        inventory: ResourceInventory, days: float
    ) -> List[Resource]:
        """Return resources that will drop below critical threshold within *days*."""
        results: List[Resource] = []
        for r in inventory.get_all_resources():
            effective_rate = r.consumption_rate_per_day * (
                1.0 - r.recycling_efficiency
            )
            projected = r.quantity_kg - effective_rate * days
            if projected <= r.critical_threshold_kg:
                results.append(r)
        return results


# ---------------------------------------------------------------------------
# Pre-built manifest: 4-crew generation ship
# ---------------------------------------------------------------------------

INTERSTELLAR_RESOURCES: List[Resource] = [
    Resource(
        name="fuel",
        quantity_kg=500_000.0,
        unit="kg",
        consumption_rate_per_day=12.0,
        critical_threshold_kg=50_000.0,
        can_be_recycled=False,
        recycling_efficiency=0.0,
    ),
    Resource(
        name="water",
        quantity_kg=40_000.0,
        unit="kg",
        consumption_rate_per_day=12.0,  # ~3 kg/person/day
        critical_threshold_kg=2_000.0,
        can_be_recycled=True,
        recycling_efficiency=0.93,
    ),
    Resource(
        name="food",
        quantity_kg=20_000.0,
        unit="kg",
        consumption_rate_per_day=8.0,  # ~2 kg/person/day
        critical_threshold_kg=1_000.0,
        can_be_recycled=False,
        recycling_efficiency=0.0,
    ),
    Resource(
        name="metals",
        quantity_kg=15_000.0,
        unit="kg",
        consumption_rate_per_day=0.5,
        critical_threshold_kg=500.0,
        can_be_recycled=True,
        recycling_efficiency=0.85,
    ),
    Resource(
        name="chemicals",
        quantity_kg=5_000.0,
        unit="kg",
        consumption_rate_per_day=1.0,
        critical_threshold_kg=300.0,
        can_be_recycled=True,
        recycling_efficiency=0.60,
    ),
    Resource(
        name="spare_parts",
        quantity_kg=8_000.0,
        unit="kg",
        consumption_rate_per_day=0.3,
        critical_threshold_kg=400.0,
        can_be_recycled=True,
        recycling_efficiency=0.50,
    ),
]
