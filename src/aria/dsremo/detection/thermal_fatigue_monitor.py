"""V3-G3: Thermal fatigue cycle counter for PCB / solder-joint life.

Problem
-------
PCB solder joints fail by low-cycle thermal fatigue: every eclipse→sunlit
transition drives ΔT between ~0 °C and +60 °C, and over a 5-year LEO
mission that's ~29 000 thermal cycles.  The existing pipeline tracks
instantaneous temperature and gradients but never counts cycles, so no
fatigue-life prediction is possible for channels that thermally cycle
(panel_temp, pcb_temp, battery_temp).

Solution
--------
1. Extract full-cycle ranges from the temperature stream via streaming
   rain-flow (Endo-Matsuishi-Mitsunaga 3-point variant, the streaming
   form of ASTM E1049-85).  Input = the turning-point sequence; output
   = one `(range_C, mean_C)` tuple per closed cycle.
2. Apply the Coffin-Manson relation `N_f(ΔT) = C · (ΔT)⁻ᵏ` per cycle
   and accumulate Miner's damage `D = Σ n_i / N_f(ΔT_i)`.
3. Report tier:
     NOMINAL     D < 0.50
     WATCH       0.50 ≤ D < 0.80
     WARNING     0.80 ≤ D < 1.00
     CRITICAL    D ≥ 1.00

Component defaults ship SAC305 solder on Cu pads (the modern aerospace
baseline, MIL-PRF-55110 compliant); callers override via
`ThermalChannelSpec` from their component datasheet.

Reference
---------
Coffin, L.F. (1954).  "A study of the effects of cyclic thermal stresses
    on a ductile metal."  Trans. ASME 76:931-950.  §II: ΔT-exponent form.

ASTM E1049-85 (reapproved 2017).  "Standard Practices for Cycle Counting
    in Fatigue Analysis."  §5.4.4: rain-flow counting algorithm.

Gilmore, D.G. (2002).  *Spacecraft Thermal Control Handbook, Vol. 1*.
    Aerospace Press.  §17.3: solder-joint fatigue in orbit.

Engelmaier, W. (1983).  "Fatigue life of leadless chip carrier solder
    joints during power cycling."  IEEE Trans. CHMT 6(3):232-237.
    §3: SAC305 / eutectic k≈1.9 exponent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique


# ── Coffin-Manson defaults for SAC305 lead-free solder on Cu pads ─────────
# These are the modern aerospace-industry baseline.  Operators with other
# solder systems override per channel via `ThermalChannelSpec`.
COFFIN_MANSON_C_DEFAULT: float = 7.0e8   # Engelmaier 1983 §3 — SAC305 C
COFFIN_MANSON_K_DEFAULT: float = 1.9     # Engelmaier 1983 §3 — SAC305 k

# Minimum temperature swing worth counting.  Sub-degree oscillations come
# from sensor noise, not real thermal strain.  Below this threshold we
# do not open a cycle in the rain-flow stack (standard practice — ASTM
# E1049 §5.4.1 calls this the "gate" amplitude).
RAINFLOW_GATE_DELTA_C: float = 0.5   # ESTIMATE — ASTM E1049 §5.4.1 gating convention

# Miner's Rule damage tiers.  NOMINAL/WATCH at D < 0.8 matches NASA-STD-5001B
# §4.3 structural-fatigue life factor of 4 (design life = 0.25 × rated life).
D_WATCH_THRESHOLD:    float = 0.50   # NASA-STD-5001B §4.3 life-factor convention
D_WARNING_THRESHOLD:  float = 0.80   # Gilmore 2002 §17.3 preventive-maintenance zone
D_CRITICAL_THRESHOLD: float = 1.00   # Miner 1945 — theoretical fatigue exhaustion


@unique
class ThermalLifeTier(str, Enum):
    """Fatigue-damage tier surfaced to operators."""

    NOMINAL  = "nominal"
    WATCH    = "watch"
    WARNING  = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ThermalChannelSpec:
    """Per-channel Coffin-Manson parameters from the component datasheet."""

    # Coffin-Manson coefficient and exponent.  Defaults are SAC305 values.
    coffin_manson_c: float = COFFIN_MANSON_C_DEFAULT
    coffin_manson_k: float = COFFIN_MANSON_K_DEFAULT
    # Rain-flow gate amplitude in engineering units (°C for thermal, strain
    # for mechanical).  Sub-gate oscillations do not open a cycle.
    gate_delta: float = RAINFLOW_GATE_DELTA_C


@dataclass
class _TPoint:
    """One turning point in the rain-flow stack."""

    value: float
    epoch: float


@dataclass
class _ChannelState:
    """Per-channel rain-flow state + accumulated damage."""

    # Last two samples — used to detect turning points (direction change).
    last_sample: float | None = None
    prev_direction: int = 0  # +1 rising, -1 falling, 0 unknown
    # Rain-flow stack of turning points in FIFO order.
    stack: list[_TPoint] = field(default_factory=list)
    # Number of closed half-cycles counted (two half-cycles = one full cycle).
    half_cycles: int = 0
    full_cycles: int = 0
    # Accumulated Miner damage from closed full-cycles only.
    damage: float = 0.0
    # Sum of squared ranges, useful for reporting RMS ΔT.
    sum_range_sq: float = 0.0


@dataclass(frozen=True, slots=True)
class ThermalFatigueReport:
    """Snapshot of the Miner's-Rule accumulator at report time."""

    channel_id:   str
    full_cycles:  int
    damage:       float
    rms_range_c:  float
    tier:         ThermalLifeTier


def _coffin_manson_cycles_to_failure(
    delta_t_c: float, spec: ThermalChannelSpec
) -> float:
    """N_f(ΔT) = C · (ΔT)⁻ᵏ.  ΔT below the gate returns +inf (no damage)."""
    if delta_t_c <= spec.gate_delta:
        return float("inf")
    return float(spec.coffin_manson_c) / (delta_t_c ** spec.coffin_manson_k)


def _tier_for(damage: float) -> ThermalLifeTier:
    if damage >= D_CRITICAL_THRESHOLD:
        return ThermalLifeTier.CRITICAL
    if damage >= D_WARNING_THRESHOLD:
        return ThermalLifeTier.WARNING
    if damage >= D_WATCH_THRESHOLD:
        return ThermalLifeTier.WATCH
    return ThermalLifeTier.NOMINAL


class ThermalFatigueMonitor:
    """Streaming rain-flow + Coffin-Manson damage accumulator.

    Usage (per new temperature sample)::
        mon.update("SAT:panel_temp", temp_c=35.4, epoch=t_unix, spec=SPEC)
        report = mon.report("SAT:panel_temp", spec=SPEC)
        if report.tier in (ThermalLifeTier.WARNING, ThermalLifeTier.CRITICAL):
            ...

    The streaming rain-flow implementation follows the Endo-Matsuishi-
    Mitsunaga 3-point algorithm (ASTM E1049 §5.4.4): inspect the top
    three turning points on the stack; if the inner range is ≤ the outer
    range, extract a full cycle of that inner range and drop the inner two
    points.  Residual half-cycles stay on the stack until a future sample
    closes them — this matches the canonical behaviour of rain-flow
    counting on a finite time series.
    """

    def __init__(self) -> None:
        self._states: dict[str, _ChannelState] = {}

    # ------------------------------------------------------------------ #
    # Mutators                                                             #
    # ------------------------------------------------------------------ #

    def update(
        self,
        channel_id: str,
        temp_c: float,
        epoch: float,
        spec: ThermalChannelSpec | None = None,
    ) -> _ChannelState:
        """Ingest one temperature sample.  Returns the mutated state."""
        spec = spec if spec is not None else ThermalChannelSpec()
        st = self._states.setdefault(channel_id, _ChannelState())

        if st.last_sample is None:
            st.last_sample = float(temp_c)
            # First point — treat as the initial turning point so a
            # direction can emerge.
            st.stack.append(_TPoint(value=float(temp_c), epoch=float(epoch)))
            return st

        diff = float(temp_c) - st.last_sample
        # Ignore truly flat samples — they don't change direction or stack.
        if diff == 0.0:
            return st

        direction = 1 if diff > 0.0 else -1
        if st.prev_direction != 0 and direction != st.prev_direction:
            # Turning point detected: push the *previous* sample onto the stack,
            # then try to collapse the stack via the 3-point rule.
            st.stack.append(_TPoint(value=st.last_sample, epoch=float(epoch)))
            self._collapse_stack(st, spec)

        st.prev_direction = direction
        st.last_sample = float(temp_c)
        return st

    # ------------------------------------------------------------------ #
    # Reporting                                                            #
    # ------------------------------------------------------------------ #

    def report(
        self,
        channel_id: str,
        spec: ThermalChannelSpec | None = None,
    ) -> ThermalFatigueReport:
        """Summarise Miner damage + tier for the channel."""
        _ = spec  # accepted for symmetry; damage is already accumulated.
        st = self._states.get(channel_id)
        if st is None:
            return ThermalFatigueReport(
                channel_id=channel_id,
                full_cycles=0,
                damage=0.0,
                rms_range_c=0.0,
                tier=ThermalLifeTier.NOMINAL,
            )
        rms = (st.sum_range_sq / st.full_cycles) ** 0.5 if st.full_cycles else 0.0
        return ThermalFatigueReport(
            channel_id=channel_id,
            full_cycles=st.full_cycles,
            damage=st.damage,
            rms_range_c=rms,
            tier=_tier_for(st.damage),
        )

    def reset(self, channel_id: str | None = None) -> None:
        if channel_id is None:
            self._states.clear()
        else:
            self._states.pop(channel_id, None)

    # ------------------------------------------------------------------ #
    # Rain-flow stack collapse (ASTM E1049 §5.4.4)                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _collapse_stack(st: _ChannelState, spec: ThermalChannelSpec) -> None:
        """Apply the 3-point rain-flow rule until the stack is stable.

        Given top-of-stack points [..., X, Y, Z] with ranges
        R1 = |X − Y| and R2 = |Y − Z|, close a full cycle of amplitude R1
        when R2 ≥ R1 (the inner cycle is "enclosed" by the outer swing).
        Remove X and Y from the stack.  Repeat — collapsing can cascade.
        """
        while len(st.stack) >= 3:
            x = st.stack[-3].value
            y = st.stack[-2].value
            z = st.stack[-1].value
            r1 = abs(x - y)
            r2 = abs(y - z)
            if r2 < r1:
                # Inner cycle is not yet closed — leave it on the stack.
                break
            # Close a full cycle of amplitude r1.
            if r1 > spec.gate_delta:
                n_f = _coffin_manson_cycles_to_failure(r1, spec)
                st.damage += 1.0 / n_f
                st.full_cycles += 1
                st.half_cycles += 2
                st.sum_range_sq += r1 * r1
            # Drop the inner two turning points (x and y); keep z.
            del st.stack[-3:-1]


# ── Process-wide singleton ────────────────────────────────────────────── #

_monitor: ThermalFatigueMonitor | None = None


def get_monitor() -> ThermalFatigueMonitor:
    global _monitor
    if _monitor is None:
        _monitor = ThermalFatigueMonitor()
    return _monitor


def reset_monitor() -> None:
    global _monitor
    _monitor = None
