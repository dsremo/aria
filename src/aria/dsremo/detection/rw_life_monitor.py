"""V3-G2: Reaction-wheel life monitor — Miner's Rule cumulative damage.

Problem
-------
Reaction-wheel lifetime depends on three usage metrics, none of which the
detector pipeline currently tracks:

    1. Total operating hours
    2. Number of zero-crossing RPM reversals (bearing load reversal fatigue)
    3. High-RPM hours (centrifugal stress on the bearing race)

Without these, no lifecycle dashboard and no RUL estimate are possible,
and a wheel that crosses zero RPM 500 times/day consumes bearing life far
faster than a constant-speed wheel — but both look identical in the
instantaneous speed channel.

Solution
--------
Per-wheel accumulators:

    cumulative_reversals        — count of sign changes in RPM stream
    cumulative_run_hours        — wall-clock hours wheel was non-zero
    high_rpm_hours              — hours spent > `high_rpm_fraction` of max

Miner's Rule cumulative damage (Miner 1945):

    D = Σ(n_i / N_f(σ_i))

For RW bearings we use two load bins: reversals (number of load-reversal
cycles) and high-RPM time (hours of elevated centrifugal stress).  When
`D_reversals = cumulative_reversals / N_f_reversals` hits 1.0 the bearing
has exhausted its fatigue budget.  A WARNING tier fires at `D > 0.8`.

References
----------
Miner, M.A. (1945).  "Cumulative damage in fatigue."  J. Appl. Mech.
    12(3):A159-A164.  Foundational Miner's Rule paper.

Wijker, J.J. (2008).  *Spacecraft Structures*.  Springer.  §12.4:
    reaction-wheel bearing lifetime calculation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique


# ── Defaults (vendor-generic) ─────────────────────────────────────────────
# Honeywell HR12 (ISS) and similar reaction wheels spec ~10^8 reversal
# cycles and ~50,000 run-hours to the bearing fatigue limit (Wijker 2008
# §12.4 Table 12.3).  Operators override these via `RWWheelSpec` instances
# when the vendor datasheet differs.
N_F_REVERSALS_DEFAULT:   int   = 100_000_000   # Wijker 2008 §12.4 Table 12.3 — Honeywell HR12 class
N_F_RUN_HOURS_DEFAULT:   float = 50_000.0      # Wijker 2008 §12.4 Table 12.3 — run-hour bearing fatigue limit
HIGH_RPM_FRACTION_DEFAULT: float = 0.80        # Wijker 2008 §12.4 — "high stress" threshold = 80 % of max RPM

# Miner's Rule damage tiers (D = accumulated/allowable).
D_WATCH_THRESHOLD:    float = 0.50   # Wijker 2008 §12.4 — derate tier
D_WARNING_THRESHOLD:  float = 0.80   # Wijker 2008 §12.4 — maintenance-window tier
D_CRITICAL_THRESHOLD: float = 1.00   # Miner 1945 — theoretical fatigue life exhaustion


@unique
class LifeTier(str, Enum):
    """Discrete fatigue-damage tier for operator reporting."""

    NOMINAL   = "nominal"
    WATCH     = "watch"
    WARNING   = "warning"
    CRITICAL  = "critical"


@dataclass(frozen=True, slots=True)
class RWWheelSpec:
    """Per-wheel life-limit parameters from the vendor datasheet."""

    n_f_reversals:     int   = N_F_REVERSALS_DEFAULT
    n_f_run_hours:     float = N_F_RUN_HOURS_DEFAULT
    max_rpm:           float = 6000.0   # Honeywell HR12 typical saturation RPM
    high_rpm_fraction: float = HIGH_RPM_FRACTION_DEFAULT


@dataclass
class RWLifeState:
    """Per-wheel accumulator + last-seen RPM (for reversal detection)."""

    wheel_id:                 str
    cumulative_reversals:     int   = 0
    cumulative_run_seconds:   float = 0.0
    cumulative_high_rpm_sec:  float = 0.0
    last_rpm:                 float | None = field(default=None, repr=False)
    last_epoch:               float | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class RWLifeReport:
    """Snapshot of fatigue accumulators + Miner's Rule damage fraction."""

    wheel_id:                 str
    cumulative_reversals:     int
    cumulative_run_hours:     float
    cumulative_high_rpm_hrs:  float
    damage_reversals:         float   # D_reversals = n / N_f
    damage_run_hours:         float   # D_hours     = t / N_f
    damage_overall:           float   # max of the two Miner terms
    tier:                     LifeTier


class RWLifeMonitor:
    """Process-wide registry of reaction-wheel life accumulators.

    Usage (detection loop)::

        mon = RWLifeMonitor()
        # every new rpm sample:
        mon.update("SAT:wheel1", rpm=420.0, epoch=t_unix, spec=DEFAULT_SPEC)
        # every cycle:
        report = mon.report("SAT:wheel1", spec=DEFAULT_SPEC)
        if report.tier in (LifeTier.WARNING, LifeTier.CRITICAL):
            ...
    """

    def __init__(self) -> None:
        self._states: dict[str, RWLifeState] = {}

    def _get_state(self, wheel_id: str) -> RWLifeState:
        st = self._states.get(wheel_id)
        if st is None:
            st = RWLifeState(wheel_id=wheel_id)
            self._states[wheel_id] = st
        return st

    def update(
        self,
        wheel_id: str,
        rpm:      float,
        epoch:    float,
        spec:     RWWheelSpec | None = None,
    ) -> RWLifeState:
        """Process one RPM sample.  Call once per new telemetry point."""
        spec = spec if spec is not None else RWWheelSpec()
        st = self._get_state(wheel_id)

        if st.last_rpm is not None and st.last_epoch is not None:
            dt = epoch - st.last_epoch
            if dt > 0.0:
                # Reversal: sign change from previous sample (including the
                # transition through 0 at exactly 0 on one side).
                if (st.last_rpm > 0.0 and rpm < 0.0) or (st.last_rpm < 0.0 and rpm > 0.0):
                    st.cumulative_reversals += 1
                # Run-time: accumulate whenever wheel was spinning in the
                # previous interval (non-zero start).
                if abs(st.last_rpm) > 0.0:
                    st.cumulative_run_seconds += dt
                # High-RPM bin: accumulate when previous sample exceeded the
                # high-stress threshold.
                high_thresh = spec.high_rpm_fraction * spec.max_rpm
                if abs(st.last_rpm) >= high_thresh:
                    st.cumulative_high_rpm_sec += dt

        st.last_rpm   = float(rpm)
        st.last_epoch = float(epoch)
        return st

    def report(
        self,
        wheel_id: str,
        spec:     RWWheelSpec | None = None,
    ) -> RWLifeReport:
        """Compute Miner's Rule damage fraction + fatigue tier for a wheel."""
        spec = spec if spec is not None else RWWheelSpec()
        st   = self._get_state(wheel_id)

        run_hours        = st.cumulative_run_seconds  / 3600.0
        high_rpm_hours   = st.cumulative_high_rpm_sec / 3600.0

        d_reversals = st.cumulative_reversals / max(spec.n_f_reversals, 1)
        # Guard against zero-limit specs; any positive limit is used as-is
        # (0.5 hr budget is valid — this is the fatigue life allowance).
        d_run_hours = run_hours / spec.n_f_run_hours if spec.n_f_run_hours > 0.0 else 0.0
        d_overall   = max(d_reversals, d_run_hours)

        return RWLifeReport(
            wheel_id=wheel_id,
            cumulative_reversals=st.cumulative_reversals,
            cumulative_run_hours=run_hours,
            cumulative_high_rpm_hrs=high_rpm_hours,
            damage_reversals=d_reversals,
            damage_run_hours=d_run_hours,
            damage_overall=d_overall,
            tier=_tier_for(d_overall),
        )

    def reset(self, wheel_id: str | None = None) -> None:
        if wheel_id is None:
            self._states.clear()
        else:
            self._states.pop(wheel_id, None)


def _tier_for(d_overall: float) -> LifeTier:
    if d_overall >= D_CRITICAL_THRESHOLD:
        return LifeTier.CRITICAL
    if d_overall >= D_WARNING_THRESHOLD:
        return LifeTier.WARNING
    if d_overall >= D_WATCH_THRESHOLD:
        return LifeTier.WATCH
    return LifeTier.NOMINAL
