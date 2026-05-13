"""Plan tier limits — enforced at API boundaries.

Each plan defines hard caps. Enforcement is done at ingest time so:
- Free: 1 satellite, 5 channels, 1 MB upload, 7-day retention, no ML detectors
- Pro:  5 satellites, 50 channels, 100 MB upload, 90-day retention, all detectors
- Team: 20 satellites, 500 channels, 500 MB upload, 1-year retention, all detectors
- Enterprise: unlimited

The plan is stored on the tenant row (`tenants.plan`). This module
provides the limit lookup — billing enforcement is separate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    satellites:       int    # -1 = unlimited
    channels:         int    # -1 = unlimited
    upload_bytes:     int    # -1 = unlimited
    retention_days:   int    # -1 = unlimited
    api_calls_per_day: int   # -1 = unlimited
    ml_detectors:     bool   # GRU, TCN, Matrix Profile, Correlation, Trend Velocity


_LIMITS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        satellites=1,
        channels=5,
        upload_bytes=1 * 1024 * 1024,       # 1 MB
        retention_days=7,
        api_calls_per_day=100,
        ml_detectors=False,
    ),
    "pro": PlanLimits(
        satellites=5,
        channels=50,
        upload_bytes=100 * 1024 * 1024,     # 100 MB
        retention_days=90,
        api_calls_per_day=10_000,
        ml_detectors=True,
    ),
    "team": PlanLimits(
        satellites=20,
        channels=500,
        upload_bytes=500 * 1024 * 1024,     # 500 MB
        retention_days=365,
        api_calls_per_day=100_000,
        ml_detectors=True,
    ),
    "enterprise": PlanLimits(
        satellites=-1,
        channels=-1,
        upload_bytes=-1,
        retention_days=-1,
        api_calls_per_day=-1,
        ml_detectors=True,
    ),
}

# Default: treat unknown plan strings as free
_DEFAULT = _LIMITS["free"]


def get_limits(plan: str | None) -> PlanLimits:
    """Return the PlanLimits for the given plan string. Unknown → free."""
    return _LIMITS.get(plan or "free", _DEFAULT)
