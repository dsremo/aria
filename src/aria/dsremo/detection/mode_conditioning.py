"""V3-Sch2: Mode-conditioned calibration for operational state changes.

When a satellite transitions from nominal to safe mode, ALL parameters
change simultaneously.  Without conditioning on operational mode, the
system generates 20+ false alarms from one mode change.

This module maintains separate CalibrationState per (satellite, parameter,
operational_mode).  When mode changes, the corresponding baseline is
activated instead of re-calibrating.

Reference: Peters, J., Janzing, D. & Schölkopf, B. (2017). Elements of
           Causal Inference. MIT Press. §2.4.
"""

from __future__ import annotations

import structlog

from aria.dsremo.detection.calibration import CalibrationState

logger = structlog.get_logger()


class ModeConditionedCalibration:
    """Manages per-mode calibration states for each channel.

    Usage:
        mc = ModeConditionedCalibration()
        # During normal operations:
        cal = mc.get_calibration("SAT:batt_v", mode="nominal")
        # On safe mode transition:
        cal = mc.get_calibration("SAT:batt_v", mode="safe_mode")
        # Returns a separate CalibrationState for safe_mode
    """

    def __init__(self) -> None:
        # (channel_key, mode) → CalibrationState
        self._states: dict[tuple[str, str], CalibrationState] = {}

    def get_calibration(
        self,
        channel_key: str,
        mode: str = "nominal",
    ) -> CalibrationState:
        """Get the calibration state for a specific channel + mode.

        Creates a new warming_up state if this (channel, mode) combo
        hasn't been seen before.
        """
        key = (channel_key, mode)
        if key not in self._states:
            self._states[key] = CalibrationState()
            logger.info(
                "mode_calibration_created",
                channel=channel_key,
                mode=mode,
            )
        return self._states[key]

    def has_calibration(self, channel_key: str, mode: str) -> bool:
        """Check if a calibrated state exists for this mode."""
        key = (channel_key, mode)
        state = self._states.get(key)
        return state is not None and state.is_calibrated

    def transfer_calibration(
        self,
        channel_key: str,
        from_mode: str,
        to_mode: str,
        scale_factor: float = 1.0,
    ) -> CalibrationState:
        """Copy calibration from one mode to another, optionally scaled.

        Useful for pre-populating safe_mode calibration from nominal data
        with a known offset (e.g., safe mode σ is typically 1.5× nominal).
        """
        source = self._states.get((channel_key, from_mode))
        if source is None or not source.is_calibrated:
            return self.get_calibration(channel_key, to_mode)

        target = CalibrationState(
            state="calibrated",
            ref_mean=source.ref_mean,
            ref_std=source.ref_std * scale_factor,
            sample_count=source.sample_count,
        )
        target._update_derived(target.ref_std)
        self._states[(channel_key, to_mode)] = target
        return target

    def known_modes(self, channel_key: str) -> list[str]:
        """List all modes that have calibration data for a channel."""
        return [mode for (ck, mode) in self._states if ck == channel_key]

    def reset(self, channel_key: str | None = None) -> None:
        if channel_key:
            keys = [k for k in self._states if k[0] == channel_key]
            for k in keys:
                del self._states[k]
        else:
            self._states.clear()
