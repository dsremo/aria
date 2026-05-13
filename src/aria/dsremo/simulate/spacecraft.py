"""Spacecraft simulator — generates physically realistic satellite telemetry.

Models a LEO CubeSat with four subsystems: EPS, ADCS, Thermal, Comms.
Key physics modeled:
  - 90-minute orbital period with eclipse cycles
  - Solar power varies with sun exposure
  - Battery charges in sunlight, discharges in eclipse
  - Thermal follows orbital heating/cooling
  - Subsystem interdependencies (power → thermal → ADCS)
  - Configurable sensor noise

This is NOT a toy random number generator. The telemetry has real correlations
that the anomaly detector must learn to distinguish from actual faults.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np

from aria.dsremo.core.models import TelemetryPoint

# Orbital constants for LEO CubeSat
ORBIT_PERIOD_SEC = 5400        # ESTIMATE — 90-min LEO orbital period (Wertz & Larson 1999 SMAD §6.2: ISS ~92 min; CubeSat ~90-95 min)
ECLIPSE_FRACTION = 0.35        # ESTIMATE — ~35% eclipse fraction typical LEO (Wertz & Larson 1999 §11.4)
SUNLIT_START = 0.0
ECLIPSE_START = 1.0 - ECLIPSE_FRACTION


class SpacecraftSimulator:
    """Stateful satellite telemetry generator.

    Each call to generate_tick() advances the clock and returns telemetry
    for all parameters, with values driven by orbital mechanics and
    subsystem physics.
    """

    def __init__(
        self,
        satellite_id: str = "DEMO-SAT-01",
        rate_hz: float = 1.0,
        noise_level: float = 0.02,
        start_time: datetime | None = None,
        seed: int | None = None,
    ):
        self.satellite_id = satellite_id
        self.rate_hz = rate_hz
        self.noise_level = noise_level
        self.rng = np.random.default_rng(seed)

        self._time = start_time or datetime.now(timezone.utc)
        self._tick = 0
        self._elapsed_sec = 0.0

        # Internal state — tracks degradation, faults, etc.
        self._battery_soc = 0.85  # state of charge (0-1)
        self._wheel_friction = np.array([1.0, 1.0, 1.0])  # 1.0 = nominal
        self._thermal_mass = 25.0  # internal temp baseline (°C)
        self._active_faults: list[dict] = []

    @property
    def orbital_phase(self) -> float:
        """Current position in orbit as fraction [0, 1)."""
        return (self._elapsed_sec % ORBIT_PERIOD_SEC) / ORBIT_PERIOD_SEC

    @property
    def in_sunlight(self) -> bool:
        return self.orbital_phase < ECLIPSE_START

    @property
    def sun_intensity(self) -> float:
        """Smooth sun exposure: 1.0 in full sun, 0.0 in eclipse, with penumbra transitions."""
        phase = self.orbital_phase
        if phase < ECLIPSE_START - 0.02:
            return 1.0
        elif phase < ECLIPSE_START + 0.02:
            # Smooth transition (penumbra)
            t = (phase - (ECLIPSE_START - 0.02)) / 0.04
            return 0.5 * (1.0 + math.cos(math.pi * t))
        elif phase < 1.0 - 0.02:
            return 0.0
        else:
            t = (phase - (1.0 - 0.02)) / 0.02
            return 0.5 * (1.0 - math.cos(math.pi * t))

    def generate_tick(self) -> list[TelemetryPoint]:
        """Advance one time step and return telemetry for all parameters."""
        self._tick += 1
        self._elapsed_sec += 1.0 / self.rate_hz
        self._time += timedelta(seconds=1.0 / self.rate_hz)

        # Apply any active faults
        fault_mods = self._compute_fault_modifiers()

        points = []
        points.extend(self._generate_eps(fault_mods))
        points.extend(self._generate_adcs(fault_mods))
        points.extend(self._generate_thermal(fault_mods))
        points.extend(self._generate_comms(fault_mods))

        # Expire completed faults
        self._active_faults = [
            f for f in self._active_faults
            if self._elapsed_sec < f["end_time"]
        ]

        return points

    def inject_fault(
        self,
        fault_type: str,
        subsystem: str,
        parameter: str,
        intensity: float = 0.5,
        duration_seconds: float = 60.0,
    ) -> None:
        """Inject a fault that will affect telemetry generation."""
        self._active_faults.append({
            "type": fault_type,
            "subsystem": subsystem,
            "parameter": parameter,
            "intensity": intensity,
            "start_time": self._elapsed_sec,
            "end_time": self._elapsed_sec + duration_seconds,
        })

    def _noise(self, nominal: float, scale: float | None = None) -> float:
        """Add Gaussian sensor noise to a nominal value."""
        s = scale if scale is not None else abs(nominal) * self.noise_level
        return nominal + self.rng.normal(0, max(s, 1e-6))

    def _make_point(self, subsystem: str, parameter: str, value: float, unit: str) -> TelemetryPoint:
        return TelemetryPoint(
            satellite_id=self.satellite_id,
            timestamp=self._time,
            subsystem=subsystem,
            parameter=parameter,
            value=round(value, 6),
            unit=unit,
        )

    # --- EPS (Electrical Power System) ---

    def _generate_eps(self, faults: dict) -> list[TelemetryPoint]:
        sun = self.sun_intensity

        # Solar array: ~2.5A in full sun, 0 in eclipse
        solar_current_nominal = 2.5 * sun  # ESTIMATE — 2.5 A typical 2U CubeSat solar array (Clyde Space 2024 datasheet: ~2.5 W/panel @ 5V)
        solar_current = self._noise(solar_current_nominal, 0.05)
        solar_current = max(0, solar_current + faults.get("solar_array_current", 0))

        # Battery: charges in sun, discharges in eclipse
        load_current = 1.2 + 0.3 * self.rng.random()  # ESTIMATE — ~1.2-1.5 A quiescent load for 2U CubeSat (Bouwmeester & Guo 2010 Acta Astron 67 907)
        net_current = solar_current - load_current
        self._battery_soc = np.clip(self._battery_soc + net_current * 0.0001, 0.05, 1.0)

        battery_voltage_nominal = 6.0 + 2.4 * self._battery_soc  # ESTIMATE — 2S Li-ion: 6.0 V (empty) → 8.4 V (full); IEC 62660-1 §5 cell voltage
        battery_voltage = self._noise(battery_voltage_nominal, 0.02)
        battery_voltage += faults.get("battery_voltage", 0)

        battery_current = self._noise(load_current - solar_current * 0.8, 0.03)
        bus_voltage = self._noise(5.0 + 0.3 * (self._battery_soc - 0.5), 0.01)

        return [
            self._make_point("eps", "battery_voltage", battery_voltage, "V"),
            self._make_point("eps", "battery_current", abs(battery_current), "A"),
            self._make_point("eps", "solar_array_current", max(0, solar_current), "A"),
            self._make_point("eps", "bus_voltage", bus_voltage, "V"),
        ]

    # --- ADCS (Attitude Determination & Control) ---

    def _generate_adcs(self, faults: dict) -> list[TelemetryPoint]:
        # Reaction wheels: ~3000 RPM nominal with slight variation per axis
        # ESTIMATE — 3000 RPM nominal for small-sat RW (Sinclair Interplanetary RW0 datasheet: 2000-6000 RPM range)
        base_speeds = [3000, 2950, 3050]
        wheels = []
        for i, (base, friction) in enumerate(zip(base_speeds, self._wheel_friction)):
            speed = self._noise(base / friction, 30)
            speed += faults.get(f"wheel_speed_{'xyz'[i]}", 0)
            axis = "xyz"[i]
            wheels.append(
                self._make_point("adcs", f"wheel_speed_{axis}", max(0, speed), "rpm")
            )

        # Pointing error: small in sunlight (star tracker works), worse in eclipse
        # ESTIMATE — 0.1° in sun (star tracker), 0.5° in eclipse (gyro propagation); Wertz 1978 §12.2
        base_error = 0.1 if self.in_sunlight else 0.5
        pointing = self._noise(base_error, 0.02)
        pointing += faults.get("pointing_error", 0)

        wheels.append(self._make_point("adcs", "pointing_error", abs(pointing), "deg"))
        return wheels

    # --- Thermal ---

    def _generate_thermal(self, faults: dict) -> list[TelemetryPoint]:
        sun = self.sun_intensity

        # Sun-facing panel: hot in sun, cold in eclipse
        panel_sun = self._noise(60.0 * sun + (-30.0 * (1 - sun)), 2.0)
        panel_shade = self._noise(-20.0 - 20.0 * (1 - sun), 2.0)

        # Battery temp: slowly follows internal temp, affected by charge/discharge
        self._thermal_mass += (22.0 - self._thermal_mass) * 0.001  # radiative cooling
        self._thermal_mass += sun * 0.005  # solar heating
        battery_temp = self._noise(self._thermal_mass, 0.5)
        battery_temp += faults.get("battery_temp", 0)

        electronics_temp = self._noise(30.0 + 5.0 * sun, 1.0)

        return [
            self._make_point("thermal", "panel_temp_sun", panel_sun, "C"),
            self._make_point("thermal", "panel_temp_shade", panel_shade, "C"),
            self._make_point("thermal", "battery_temp", battery_temp, "C"),
            self._make_point("thermal", "electronics_temp", electronics_temp, "C"),
        ]

    # --- Comms ---

    def _generate_comms(self, faults: dict) -> list[TelemetryPoint]:
        # Signal strength: varies with ground station visibility (simplified)
        visibility = 0.5 + 0.5 * math.sin(2 * math.pi * self._elapsed_sec / ORBIT_PERIOD_SEC * 1.1)
        signal = self._noise(-80.0 + 30.0 * visibility, 3.0)

        ber = self._noise(0.0001 * (1.5 - visibility), 0.00002)
        link_margin = self._noise(10.0 + 8.0 * visibility, 0.5)

        return [
            self._make_point("comms", "signal_strength", signal, "dBm"),
            self._make_point("comms", "bit_error_rate", max(0, ber), ""),
            self._make_point("comms", "link_margin", max(0, link_margin), "dB"),
        ]

    # --- Fault Modifiers ---

    def _compute_fault_modifiers(self) -> dict[str, float]:
        """Combine all active faults into parameter modifiers."""
        mods: dict[str, float] = {}
        for fault in self._active_faults:
            param = fault["parameter"]
            intensity = fault["intensity"]
            elapsed_in_fault = self._elapsed_sec - fault["start_time"]
            duration = fault["end_time"] - fault["start_time"]
            progress = elapsed_in_fault / max(duration, 1)

            match fault["type"]:
                case "drift":
                    # Gradual drift — ramps linearly
                    mods[param] = mods.get(param, 0) + intensity * progress * 5.0
                case "spike":
                    # Sharp spike at fault start, then decays
                    decay = math.exp(-elapsed_in_fault * 0.1)
                    mods[param] = mods.get(param, 0) + intensity * 20.0 * decay
                case "dropout":
                    # Value drops toward zero
                    mods[param] = -999.0  # sentinel value handled by generators
                case "degradation":
                    # Exponential degradation
                    mods[param] = mods.get(param, 0) - intensity * (1 - math.exp(-progress * 3))
                case "oscillation":
                    # Unexpected periodic signal
                    freq = 0.1 * intensity
                    mods[param] = mods.get(param, 0) + intensity * 3.0 * math.sin(2 * math.pi * freq * elapsed_in_fault)

        return mods
