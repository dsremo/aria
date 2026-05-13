"""V3-G5: Load-compensated battery voltage for anomaly detection.

During high-current RF transmission (e.g., X-band: 15A), a voltage dip
to 26.5V is nominal (IR drop: ΔV = I × R_internal ≈ 1.5V).  At idle
(0.5A), the same 26.5V indicates severe degradation.

This module computes: V_comp = V_measured + I × R_est
And separately tracks R_internal as its own channel — rising R_internal
is the leading indicator of battery degradation (IEC 62660-1).

Reference: Plett, G.L. (2004). "Extended Kalman filtering for battery
           management systems." J. Power Sources 134(2):262–276.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


class LoadCompensatedVoltage:
    """Computes load-compensated battery voltage and R_internal.

    Usage:
        lc = LoadCompensatedVoltage()
        result = lc.update("SAT-1", voltage=27.5, current=10.0, timestamp=...)
        # result.v_compensated ≈ 28.5 (compensated for IR drop)
        # result.r_internal ≈ 0.10 ohm
    """

    def __init__(
        self,
        r_internal_initial: float = 0.05,     # ESTIMATE — 0.05 Ω initial R_int for new Li-ion cell (IEC 62660-1)
        r_internal_ewma_alpha: float = 0.1,   # ESTIMATE — EWMA α=0.1 for slow R_int tracking (Plett 2004)
        min_current_for_r_est: float = 0.5,   # ESTIMATE — 0.5 A minimum ΔI to compute reliable ΔV/ΔI
    ) -> None:
        self._r_init = r_internal_initial
        self._alpha = r_internal_ewma_alpha
        self._min_current = min_current_for_r_est
        # satellite_id → state
        self._state: dict[str, dict] = {}

    def _get_state(self, satellite_id: str) -> dict:
        if satellite_id not in self._state:
            self._state[satellite_id] = {
                "r_internal": self._r_init,
                "prev_voltage": None,
                "prev_current": None,
                "v_compensated": None,
            }
        return self._state[satellite_id]

    def update(
        self,
        satellite_id: str,
        voltage: float,
        current: float,
    ) -> dict:
        """Process a voltage/current pair.

        Args:
            voltage: Battery terminal voltage (V).
            current: Battery current (A, positive=charging, negative=discharging).

        Returns:
            {"v_compensated": float, "r_internal": float, "ir_drop": float}
        """
        state = self._get_state(satellite_id)

        # Estimate R_internal from V/I changes (ΔV/ΔI).
        if (state["prev_voltage"] is not None
                and state["prev_current"] is not None):
            di = current - state["prev_current"]
            dv = voltage - state["prev_voltage"]
            if abs(di) > self._min_current:
                r_est = abs(dv / di)
                if 0.001 < r_est < 5.0:  # sanity bounds
                    # EWMA update of R_internal.
                    state["r_internal"] = (
                        self._alpha * r_est
                        + (1.0 - self._alpha) * state["r_internal"]
                    )

        state["prev_voltage"] = voltage
        state["prev_current"] = current

        # Compute load-compensated voltage.
        r_int = state["r_internal"]
        ir_drop = abs(current) * r_int
        v_comp = voltage + ir_drop  # add back the IR drop

        state["v_compensated"] = v_comp

        return {
            "v_compensated": round(v_comp, 4),
            "r_internal": round(r_int, 6),
            "ir_drop": round(ir_drop, 4),
        }

    def get_r_internal(self, satellite_id: str) -> float | None:
        state = self._state.get(satellite_id)
        return state["r_internal"] if state else None

    def get_v_compensated(self, satellite_id: str) -> float | None:
        state = self._state.get(satellite_id)
        return state["v_compensated"] if state else None

    def reset(self, satellite_id: str | None = None) -> None:
        if satellite_id:
            self._state.pop(satellite_id, None)
        else:
            self._state.clear()
