"""Expected behavior profiles — suppress known non-nominal patterns.

During maneuvers, thermal transients, or payload operations, telemetry
follows predictable but non-nominal patterns.  Operators define these as
"expected behavior profiles" so the detection pipeline suppresses the
expected pattern instead of disabling ALL detection during that phase.

Example:
    profile = BehaviorProfile(
        name="thruster_firing",
        parameter_patterns={
            "battery_current": {"expected_range": (10.0, 18.0), "duration_s": 30},
            "bus_voltage": {"expected_range": (27.0, 29.5), "duration_s": 45},
        },
    )
    register_profile("SAT-1", profile)
    activate_profile("SAT-1", "thruster_firing")
    # For next 45 seconds: anomalies on battery_current and bus_voltage
    # within expected ranges are suppressed, but anomalies OUTSIDE the
    # expected range still fire (unlike phase gating which suppresses ALL).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class ParameterExpectation:
    """Expected behavior for one parameter during a profile."""
    expected_range: tuple[float, float]  # (min, max) — values in this range are expected
    duration_s: float = 300.0
    max_rate_of_change: float | None = None  # max expected dv/dt


@dataclass
class BehaviorProfile:
    """A named set of parameter expectations for a known operational mode."""
    name: str
    description: str = ""
    parameter_patterns: dict[str, ParameterExpectation] = field(default_factory=dict)


@dataclass
class ActiveProfile:
    """A profile that is currently active on a satellite."""
    profile: BehaviorProfile
    activated_at: float
    satellite_id: str

    def is_expired(self) -> bool:
        now = time.time()
        max_duration = max(
            (p.duration_s for p in self.profile.parameter_patterns.values()),
            default=0.0,
        )
        return now > self.activated_at + max_duration

    def is_value_expected(self, parameter: str, value: float) -> bool:
        """Check if a value is within the expected range for a parameter."""
        pattern = self.profile.parameter_patterns.get(parameter)
        if pattern is None:
            return False
        elapsed = time.time() - self.activated_at
        if elapsed > pattern.duration_s:
            return False
        lo, hi = pattern.expected_range
        return lo <= value <= hi


class BehaviorProfileManager:
    """Manages expected behavior profiles for satellites."""

    def __init__(self) -> None:
        self._profiles: dict[str, dict[str, BehaviorProfile]] = {}  # sat → name → profile
        self._active: dict[str, list[ActiveProfile]] = {}  # sat → active profiles

    def register(self, satellite_id: str, profile: BehaviorProfile) -> None:
        """Register a behavior profile for a satellite."""
        profiles = self._profiles.setdefault(satellite_id, {})
        profiles[profile.name] = profile
        logger.info("behavior_profile_registered",
                    satellite=satellite_id, name=profile.name)

    def activate(self, satellite_id: str, profile_name: str) -> bool:
        """Activate a registered profile. Returns False if not found."""
        profiles = self._profiles.get(satellite_id, {})
        profile = profiles.get(profile_name)
        if profile is None:
            return False
        active = self._active.setdefault(satellite_id, [])
        active.append(ActiveProfile(
            profile=profile,
            activated_at=time.time(),
            satellite_id=satellite_id,
        ))
        self._gc(satellite_id)
        logger.info("behavior_profile_activated",
                    satellite=satellite_id, name=profile_name)
        return True

    def is_expected(self, satellite_id: str, parameter: str, value: float) -> bool:
        """Check if a value is expected under any active profile."""
        for ap in self._active.get(satellite_id, []):
            if not ap.is_expired() and ap.is_value_expected(parameter, value):
                return True
        return False

    def get_active_profiles(self, satellite_id: str) -> list[str]:
        """Return names of active (non-expired) profiles."""
        self._gc(satellite_id)
        return [ap.profile.name for ap in self._active.get(satellite_id, [])]

    def _gc(self, satellite_id: str) -> None:
        """Remove expired profiles."""
        if satellite_id in self._active:
            self._active[satellite_id] = [
                ap for ap in self._active[satellite_id] if not ap.is_expired()
            ]


# Singleton
_manager = BehaviorProfileManager()


def get_profile_manager() -> BehaviorProfileManager:
    return _manager
