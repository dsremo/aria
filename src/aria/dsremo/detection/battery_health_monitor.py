"""V3-G1: Battery State of Health (SoH) monitor via Coulomb counting.

Separates State of Health (SoH — irreversible capacity degradation) from
State of Charge (SoC — normal charge/discharge cycle) which voltage-only
monitoring conflates.  A battery at 80% SoC at BOL and 80% SoC at EOL have
nearly identical open-circuit voltages; only capacity tracking reveals the
difference.

Also estimates internal resistance R_internal from V/I observations,
which is the leading indicator of battery degradation (IEC 62660-1).

References:
    Plett, G.L. (2015). Battery Management Systems, Vol. 1. Artech House.
    NASA/TM-2010-216726: Li-Ion Battery SoH Estimation.
"""

from __future__ import annotations

from collections import deque

import structlog

from aria.dsremo.core.models import DetectorResult, Severity
from aria.dsremo.detection.battery_knee import (
    MIN_CYCLES_FOR_KNEE,
    DegradationPhase,
    EOL_SOH_DEFAULT,
    fit_two_phase,
    project_remaining_cycles,
)

logger = structlog.get_logger()

# V3-G4 thresholds.  When the two-phase model says we've entered PHASE_2
# (knee crossed) AND projected remaining cycles drop below this horizon,
# escalate the DetectorResult to WARNING so the operator sees end-of-life
# acceleration before the capacity limit is actually reached.  50 cycles
# ≈ 1 month at LEO eclipse cadence — enough runway to order a spare.
_KNEE_WARNING_CYCLES_REMAINING: float = 50.0   # IEC 62660-1 §6.2 early-warning zone
# Ring-buffer length for the SoH trajectory feeding the G-4 fit.
# 500 cycles covers ~3 yr of LEO eclipse cycling; NASA battery dataset
# (Saha & Goebel 2007) runs 168 cycles to EOL — 500 leaves generous margin.
_SOH_TRAJECTORY_MAX_LEN: int = 500   # ESTIMATE — 500 cycle ring (Saha & Goebel 2007)


class BatteryHealthMonitor:
    """Battery SoH monitor via Coulomb counting and R_internal estimation.

    Requires both battery_voltage and battery_current channels to be
    ingested for the same satellite.

    Outputs:
        - soh_estimate: measured_capacity / nominal_capacity (1.0 = new)
        - r_internal_ohm: average internal resistance from recent V/I pairs
        - cycle_count: number of charge-discharge cycles observed
    """

    VOLTAGE_PARAMS: frozenset[str] = frozenset({
        "battery_voltage", "bus_voltage",
    })
    CURRENT_PARAMS: frozenset[str] = frozenset({
        "battery_current",
    })

    def __init__(
        self,
        nominal_capacity_ah: float = 10.0,   # ESTIMATE — 10 Ah typical small satellite Li-ion cell (IEC 62660-1)
        soh_warning_threshold: float = 0.80, # ESTIMATE — SoH 80% warning; IEC 62660-1: EOL criterion = 80% capacity
        soh_critical_threshold: float = 0.60,# ESTIMATE — SoH 60% critical (replacement threshold; Plett 2015 §2.4)
        r_internal_warning: float = 0.2,     # ESTIMATE — 0.2 Ω R_int warning (IEC 62660-1 §5.2 resistance rise)
    ) -> None:
        self._nominal_capacity = nominal_capacity_ah
        self._soh_warning = soh_warning_threshold
        self._soh_critical = soh_critical_threshold
        self._r_int_warning = r_internal_warning
        self._state: dict[str, dict] = {}

    def _get_state(self, satellite_id: str) -> dict:
        if satellite_id not in self._state:
            self._state[satellite_id] = {
                "voltage": None,
                "current": None,
                "prev_voltage": None,
                "prev_current": None,
                "charge_accumulated_ah": 0.0,
                "discharge_accumulated_ah": 0.0,
                "cycle_count": 0,
                "is_charging": None,
                "soh_estimate": 1.0,
                "r_internal_estimates": [],
                "last_cycle_capacity_ah": None,
                "prev_timestamp": None,
                # V3-G4: per-cycle SoH trajectory feeds the two-phase
                # degradation fit.  deque with maxlen so long-running
                # missions do not grow memory unbounded — oldest cycles
                # are dropped first (they are the least relevant for
                # detecting a recent knee anyway).
                "soh_trajectory": deque(maxlen=_SOH_TRAJECTORY_MAX_LEN),
                "last_recorded_cycle": 0,
            }
        return self._state[satellite_id]

    def update(
        self,
        satellite_id: str,
        parameter: str,
        value: float,
        timestamp_epoch: float,
    ) -> DetectorResult | None:
        """Process a battery telemetry reading.

        Returns a DetectorResult when SoH or R_internal crosses a threshold.
        Returns None when not enough data or parameter is not battery-related.
        """
        state = self._get_state(satellite_id)

        if parameter in self.VOLTAGE_PARAMS:
            state["prev_voltage"] = state["voltage"]
            state["voltage"] = value
            return None

        if parameter not in self.CURRENT_PARAMS:
            return None

        # ── Process battery current ──────────────────────────────────
        state["prev_current"] = state["current"]
        state["current"] = value

        # Estimate internal resistance from V/I changes.
        if (state["prev_voltage"] is not None
                and state["voltage"] is not None
                and state["prev_current"] is not None):
            di = value - state["prev_current"]
            if abs(di) > 0.1:
                dv = state["voltage"] - state["prev_voltage"]
                r_est = abs(dv / di)
                if 0.001 < r_est < 10.0:
                    r_list = state["r_internal_estimates"]
                    r_list.append(r_est)
                    if len(r_list) > 100:
                        r_list.pop(0)

        # Coulomb counting: integrate current over time.
        if state["prev_timestamp"] is not None:
            dt_h = (timestamp_epoch - state["prev_timestamp"]) / 3600.0
            if 0 < dt_h < 1.0:
                charge_ah = value * dt_h
                if value > 0.05:
                    # Charging.
                    state["charge_accumulated_ah"] += charge_ah
                    if state["is_charging"] is False:
                        # Discharge → Charge transition: cycle completed.
                        state["cycle_count"] += 1
                        discharge_cap = state["discharge_accumulated_ah"]
                        if discharge_cap > 0.1:
                            state["last_cycle_capacity_ah"] = discharge_cap
                            state["soh_estimate"] = min(
                                1.0, discharge_cap / self._nominal_capacity,
                            )
                        state["discharge_accumulated_ah"] = 0.0
                        # V3-G4: stamp the just-computed SoH onto the per-cycle
                        # trajectory — exactly once per completed cycle, indexed
                        # by cycle_count so the two-phase fit sees the right x-axis.
                        if state["cycle_count"] != state["last_recorded_cycle"]:
                            state["soh_trajectory"].append(state["soh_estimate"])
                            state["last_recorded_cycle"] = state["cycle_count"]
                    state["is_charging"] = True
                elif value < -0.05:
                    # Discharging.
                    state["discharge_accumulated_ah"] += abs(charge_ah)
                    if state["is_charging"] is True:
                        state["charge_accumulated_ah"] = 0.0
                    state["is_charging"] = False

        state["prev_timestamp"] = timestamp_epoch

        # ── Produce detector result once we have cycle data ──────────
        if state["cycle_count"] < 1:
            return None

        soh = state["soh_estimate"]
        r_int = (
            sum(state["r_internal_estimates"]) / len(state["r_internal_estimates"])
            if state["r_internal_estimates"]
            else 0.0
        )

        if soh < self._soh_critical or r_int > self._r_int_warning * 2:
            severity = Severity.CRITICAL
            score = 1.0
        elif soh < self._soh_warning or r_int > self._r_int_warning:
            severity = Severity.WARNING
            score = 0.7
        else:
            severity = Severity.NOMINAL
            score = 0.0

        details: dict = {
            "soh_estimate": round(soh, 4),
            "cycle_count": state["cycle_count"],
            "r_internal_ohm": round(r_int, 4) if r_int > 0 else None,
            "last_cycle_capacity_ah": (
                round(state["last_cycle_capacity_ah"], 2)
                if state["last_cycle_capacity_ah"]
                else None
            ),
            "nominal_capacity_ah": self._nominal_capacity,
        }

        # V3-G4: escalate to WARNING when the two-phase fit shows we're
        # past the knee and projected remaining cycles are below the
        # early-warning horizon.  Evaluated only once per completed cycle
        # to keep the hot path O(1) — fit_two_phase is O(n²) and n ≤ 500.
        if len(state["soh_trajectory"]) >= MIN_CYCLES_FOR_KNEE:
            fit = fit_two_phase(list(state["soh_trajectory"]))
            remaining = project_remaining_cycles(fit, soh)
            details["degradation_phase"] = fit.phase.value
            if fit.n_knee is not None:
                details["n_knee"] = fit.n_knee
            if remaining != float("inf"):
                details["remaining_cycles_to_eol"] = round(remaining, 1)
            if (
                fit.phase == DegradationPhase.PHASE_2
                and remaining < _KNEE_WARNING_CYCLES_REMAINING
            ):
                # The flag is always set in this regime — operators care
                # whether we are past the knee even when absolute SoH has
                # already tripped the soh_warning / soh_critical gate.
                details["knee_warning"] = True
                # Only escalate severity when the absolute thresholds have
                # not already done so.  Never downgrade.
                if severity == Severity.NOMINAL:
                    severity = Severity.WARNING
                    score = max(score, 0.65)

        is_anomaly = severity not in (Severity.NOMINAL, Severity.CAUTION)

        return DetectorResult(
            detector_name="battery_health",
            is_anomaly=is_anomaly,
            score=score,
            severity=severity,
            details=details,
        )

    def report_degradation(self, satellite_id: str) -> dict | None:
        """V3-G4: current two-phase degradation fit + RUL projection.

        Returns None when the satellite has not accumulated enough cycles
        for a meaningful fit (< MIN_CYCLES_FOR_KNEE).  Callers get the
        phase, slope estimates, knee position (when detected), and
        projected remaining cycles to EOL.
        """
        state = self._state.get(satellite_id)
        if state is None or len(state["soh_trajectory"]) < MIN_CYCLES_FOR_KNEE:
            return None
        fit = fit_two_phase(list(state["soh_trajectory"]))
        remaining = project_remaining_cycles(fit, state["soh_estimate"])
        return {
            "phase": fit.phase.value,
            "phase_1_slope": fit.phase_1_slope,
            "phase_2_slope": fit.phase_2_slope,
            "n_knee": fit.n_knee,
            "soh_at_knee": fit.soh_at_knee,
            "current_soh": state["soh_estimate"],
            "eol_soh": EOL_SOH_DEFAULT,
            "remaining_cycles_to_eol": (
                None if remaining == float("inf") else round(remaining, 1)
            ),
            "cycles_observed": len(state["soh_trajectory"]),
        }

    def get_soh(self, satellite_id: str) -> float | None:
        """Return current SoH estimate for a satellite, or None if no data."""
        state = self._state.get(satellite_id)
        if state and state["cycle_count"] > 0:
            return state["soh_estimate"]
        return None

    def reset(self, satellite_id: str | None = None) -> None:
        """Clear state for one or all satellites."""
        if satellite_id:
            self._state.pop(satellite_id, None)
        else:
            self._state.clear()
