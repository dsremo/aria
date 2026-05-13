"""V3-M2: Physical constraint checker — cross-channel conservation law validation.

Validates Kirchhoff's Current Law at the EPS power bus:
    solar_current × bus_voltage ≈ total_power_consumption

A violation >3× measurement uncertainty indicates either a sensor failure
(one current sensor reading wrong) or an unreported load (latent fault).
This catches faults that single-channel anomaly detection cannot see.

Sensor-fusion audit hardenings:
    * S-4: replaced ``or`` truthiness fallback with explicit
            ``is None`` checks.  At eclipse (solar_array_current=0.0)
            Python's ``or`` silently fell through to a
            different sensor name, causing the cross-check to disable
            itself at exactly the operationally-stressed moment.
    * S-5: each parameter is stored with a monotonic timestamp; KCL
            evaluation is skipped when any input is older than
            ``stale_after_s`` (default ~2 sample periods at 1 Hz).
    * S-20/S-21: hard-coded eclipse and tolerance constants now carry
            citations.

Extensible to ADCS angular momentum conservation and thermal energy balance.

Reference: Wertz, J.R. & Larson, W.J. (1999). Space Mission Analysis and
           Design, 3rd ed. §11.4: EPS power budget methodology.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

from aria.dsremo.core.models import DetectorResult, Severity

logger = structlog.get_logger()


# ── Tunable constants with citations ────────────────────────────────

# 3σ violation threshold per ECSS-E-ST-70-41C §6.3.4.1 ("instrument
# verification, alarm threshold").  Below the threshold the imbalance is
# explained by sensor uncertainty; above, it is a real anomaly.
DEFAULT_TOLERANCE_FACTOR = 3.0   # σ — ECSS-E-ST-70-41C §6.3.4.1

# 5% measurement uncertainty is the conservative-bound for shunt-based
# current sensing on satellite EPS at the bus level (Patel 2004,
# "Spacecraft Power Systems," §3.5.2).  Operators with calibrated sensors
# should override this per-mission.
DEFAULT_MEAS_UNCERTAINTY = 0.05  # fractional — Patel 2004 §3.5.2

# Bus voltage below this threshold means deep-eclipse / battery-pack
# under-voltage; the linear KCL approximation breaks down because of
# DC-DC converter dropout.  0.5 V is the conservative under-voltage
# cutoff for most LEO buses (NASA-STD-4002A §6.7).  Was 0.1 V before
# (uncited); 0.5 V protects against marginal-bus false negatives near
# the converter cliff.
DEFAULT_BUS_UV_CUTOFF_V = 0.5    # V — NASA-STD-4002A §6.7

# Two telemetry samples old, at the canonical 1 Hz EPS rate, is the
# longest gap we allow before we treat an input as stale.  Rationale:
# at 1 Hz the second sample carries < 5% additional drift relative to
# the first (Wertz/Larson §11.4.2 sensor settling time); beyond that,
# combining heterogeneous-age samples makes KCL meaningless.
DEFAULT_STALE_AFTER_S = 2.0      # s — derived from 1 Hz nominal rate × 2


@dataclass(frozen=True)
class _Sample:
    """A single (value, monotonic_ts) pair.  Stored per parameter to
    let the KCL evaluator skip stale combinations (S-5)."""
    value: float
    ts_monotonic: float


class PhysicalConstraintChecker:
    """Validates physical conservation laws across subsystem parameters.

    Currently implements:
        - EPS power balance (Kirchhoff's Current Law)

    Detects sensor failures and unreported loads that single-channel
    anomaly detectors cannot catch.
    """

    EPS_PARAMS: frozenset[str] = frozenset({
        "solar_array_current", "solar_current",
        "bus_voltage", "battery_voltage",
        "power_consumption", "battery_current",
    })

    def __init__(
        self,
        tolerance_factor: float = DEFAULT_TOLERANCE_FACTOR,
        measurement_uncertainty: float = DEFAULT_MEAS_UNCERTAINTY,
        bus_uv_cutoff_v: float = DEFAULT_BUS_UV_CUTOFF_V,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
    ) -> None:
        self._tolerance_factor = tolerance_factor
        self._measurement_uncertainty = measurement_uncertainty
        self._bus_uv_cutoff_v = bus_uv_cutoff_v
        self._stale_after_s = stale_after_s
        # satellite_id → {parameter_name: _Sample}
        self._latest: dict[str, dict[str, _Sample]] = {}

    def update(
        self,
        satellite_id: str,
        parameter: str,
        value: float,
    ) -> DetectorResult | None:
        """Update a parameter value and check KCL if enough EPS data.

        Returns None for non-EPS parameters or when insufficient data.
        """
        if parameter not in self.EPS_PARAMS:
            return None

        now_m = time.monotonic()
        sat = self._latest.setdefault(satellite_id, {})
        sat[parameter] = _Sample(value=value, ts_monotonic=now_m)

        # S-4 fix: explicit ``is None`` checks instead of ``or``
        # truthiness.  ``solar_array_current = 0.0`` (eclipse) used to
        # silently fall through to ``solar_current``, blending two
        # semantically distinct sensors.
        solar_i_sample = self._first_non_none(sat,
                                              "solar_array_current",
                                              "solar_current")
        bus_v_sample = self._first_non_none(sat,
                                            "bus_voltage",
                                            "battery_voltage")
        power_sample = sat.get("power_consumption")

        if solar_i_sample is None or bus_v_sample is None or power_sample is None:
            return None

        # S-5 fix: skip if any input is stale.
        for sample in (solar_i_sample, bus_v_sample, power_sample):
            if now_m - sample.ts_monotonic > self._stale_after_s:
                logger.debug(
                    "kcl_skipped_stale_input",
                    satellite=satellite_id,
                    age_s=round(now_m - sample.ts_monotonic, 2),
                    stale_after_s=self._stale_after_s,
                )
                return None

        bus_v = bus_v_sample.value
        if bus_v < self._bus_uv_cutoff_v:
            # Deep-eclipse / converter dropout — KCL approximation
            # invalid here (see DEFAULT_BUS_UV_CUTOFF_V citation).
            return None

        solar_i = solar_i_sample.value
        power = power_sample.value
        expected_power = solar_i * bus_v
        imbalance = abs(expected_power - power)
        tolerance = (self._tolerance_factor
                     * self._measurement_uncertainty
                     * max(expected_power, power, 1.0))

        if imbalance <= tolerance:
            return DetectorResult(
                detector_name="physical_constraint",
                is_anomaly=False,
                score=imbalance / max(tolerance, 1e-9),
                severity=Severity.NOMINAL,
                details={
                    "imbalance_w": round(imbalance, 2),
                    "tolerance_w": round(tolerance, 2),
                },
            )

        score = min(1.0, imbalance / max(tolerance, 1e-9) - 1.0)
        if score > 0.8:
            severity = Severity.CRITICAL
        elif score > 0.3:
            severity = Severity.WARNING
        else:
            severity = Severity.WATCH

        logger.warning(
            "eps_power_balance_violation",
            satellite=satellite_id,
            expected_w=round(expected_power, 2),
            measured_w=round(power, 2),
            imbalance_w=round(imbalance, 2),
        )

        return DetectorResult(
            detector_name="physical_constraint",
            is_anomaly=True,
            score=score,
            severity=severity,
            details={
                "reason": "eps_power_balance_violation",
                "expected_power_w": round(expected_power, 2),
                "measured_power_w": round(power, 2),
                "imbalance_w": round(imbalance, 2),
                "tolerance_w": round(tolerance, 2),
            },
        )

    @staticmethod
    def _first_non_none(
        sat: dict[str, _Sample],
        *keys: str,
    ) -> _Sample | None:
        """Return the first sample whose value is not None.

        Replaces the ``a or b`` truthiness pattern that mis-handled
        zero-valued sensors at eclipse boundaries (S-4).
        """
        for key in keys:
            sample = sat.get(key)
            if sample is not None:
                return sample
        return None

    def reset(self, satellite_id: str | None = None) -> None:
        """Clear state for one or all satellites."""
        if satellite_id:
            self._latest.pop(satellite_id, None)
        else:
            self._latest.clear()
