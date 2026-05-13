from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


COLD_GAS_ISP_S = 70.0  # GN2 cold-gas typical (Sutton, "Rocket Propulsion Elements" 9th ed., Table 1-2)
COLD_GAS_F_THRUST_N = 1.0  # CubeSat cold-gas class (VACCO MiPS family datasheets)
G0_M_S2 = 9.80665  # CGPM 1901 standard gravity
RW_MAX_TORQUE_NM = 0.10  # Blue Canyon RWp050 max torque (BCT datasheet)
RW_MAX_MOMENTUM_NMS = 0.40  # Blue Canyon RWp050 max momentum (BCT datasheet)
HEATER_DEFAULT_POWER_W = 10.0  # MMRTG-class survival-heater envelope (NASA/TM-2018-219690)
HEATER_THERMAL_CAPACITY_J_K = 1200.0  # ESTIMATE — ~1 kg Al component thermal mass (c_p Al ≈ 900 J/kg/K)
HEATER_AMBIENT_LEAK_W_K = 0.05  # ESTIMATE — MLI-equivalent leak per ECSS-E-HB-31-01


@dataclass
class ActuatorState:
    delta_v_total_m_s: float = 0.0
    propellant_remaining_kg: float = 0.50
    rw_momentum_nms: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rw_saturated: bool = False
    heater_on: bool = False
    heater_temp_k: float = 293.15
    payload_on: bool = False
    last_command: str = ""
    last_command_counter: int = 0


@dataclass
class ColdGasThruster:
    isp_s: float = COLD_GAS_ISP_S
    thrust_n: float = COLD_GAS_F_THRUST_N
    propellant_kg: float = 0.50

    def fire(self, *, dry_mass_kg: float, burn_time_s: float) -> tuple[float, float]:
        if burn_time_s <= 0:
            raise ValueError("burn_time_s must be positive")
        if dry_mass_kg <= 0:
            raise ValueError("dry_mass_kg must be positive")
        if self.propellant_kg <= 0:
            raise ValueError("propellant_exhausted")
        m_dot = self.thrust_n / (self.isp_s * G0_M_S2)
        burn = min(burn_time_s, self.propellant_kg / m_dot)
        spent_kg = m_dot * burn
        m_initial = dry_mass_kg + self.propellant_kg
        m_final = m_initial - spent_kg
        ve = self.isp_s * G0_M_S2
        delta_v = ve * (1.0 - m_final / m_initial) if m_initial > 0 else 0.0
        self.propellant_kg = max(self.propellant_kg - spent_kg, 0.0)
        return delta_v, spent_kg


@dataclass
class ReactionWheelTriad:
    momentum_nms: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    max_torque_nm: float = RW_MAX_TORQUE_NM
    max_momentum_nms: float = RW_MAX_MOMENTUM_NMS

    def apply_torque(self, torque_nm: tuple[float, float, float], dt_s: float) -> bool:
        if dt_s <= 0:
            raise ValueError("dt_s must be positive")
        saturated = False
        for axis_index in range(3):
            commanded = torque_nm[axis_index]
            if abs(commanded) > self.max_torque_nm:
                commanded = self.max_torque_nm * (1.0 if commanded > 0 else -1.0)
                saturated = True
            new_h = self.momentum_nms[axis_index] + commanded * dt_s
            if abs(new_h) > self.max_momentum_nms:
                new_h = self.max_momentum_nms * (1.0 if new_h > 0 else -1.0)
                saturated = True
            self.momentum_nms[axis_index] = new_h
        return saturated


@dataclass
class SurvivalHeater:
    power_w: float = HEATER_DEFAULT_POWER_W
    capacity_j_k: float = HEATER_THERMAL_CAPACITY_J_K
    ambient_leak_w_k: float = HEATER_AMBIENT_LEAK_W_K
    temperature_k: float = 293.15
    ambient_k: float = 273.15
    on: bool = False

    def step(self, dt_s: float) -> float:
        if dt_s <= 0:
            raise ValueError("dt_s must be positive")
        q_in = self.power_w if self.on else 0.0
        q_leak = self.ambient_leak_w_k * (self.temperature_k - self.ambient_k)
        net_w = q_in - q_leak
        delta_t = net_w * dt_s / self.capacity_j_k
        self.temperature_k += delta_t
        return self.temperature_k


class ActuatorBank:
    def __init__(
        self,
        *,
        dry_mass_kg: float = 12.0,
        thruster: ColdGasThruster | None = None,
        wheel: ReactionWheelTriad | None = None,
        heater: SurvivalHeater | None = None,
    ) -> None:
        if dry_mass_kg <= 0:
            raise ValueError("dry_mass_kg must be positive")
        self._lock = threading.Lock()
        self._dry_mass_kg = dry_mass_kg
        self._thruster = thruster or ColdGasThruster()
        self._wheel = wheel or ReactionWheelTriad()
        self._heater = heater or SurvivalHeater()
        self._payload_on = False
        self._delta_v_total = 0.0
        self._last_command = ""
        self._last_counter = 0

    def dispatch(
        self, *, command: str, params: dict[str, Any], counter: int,
    ) -> tuple[bool, str]:
        with self._lock:
            self._last_command = command
            self._last_counter = counter
            try:
                if command == "thruster.fire":
                    burn = float(params.get("burn_time_s", 0.0))
                    delta_v, spent = self._thruster.fire(
                        dry_mass_kg=self._dry_mass_kg, burn_time_s=burn,
                    )
                    self._delta_v_total += delta_v
                    return True, (
                        f"burn ok; delta_v={delta_v:.4f} m/s; "
                        f"spent={spent*1000:.2f} g"
                    )
                if command == "wheel.torque":
                    torque = params.get("torque_nm")
                    dt = float(params.get("dt_s", 1.0))
                    if not isinstance(torque, (list, tuple)) or len(torque) != 3:
                        return False, "torque_nm must be a 3-vector"
                    sat = self._wheel.apply_torque(
                        (float(torque[0]), float(torque[1]), float(torque[2])),
                        dt,
                    )
                    return True, ("saturated" if sat else "torque applied")
                if command == "heater.on":
                    self._heater.on = True
                    return True, "heater on"
                if command == "heater.off":
                    self._heater.on = False
                    return True, "heater off"
                if command == "heater.step":
                    dt = float(params.get("dt_s", 1.0))
                    temp = self._heater.step(dt)
                    return True, f"temp_k={temp:.3f}"
                if command == "payload.on":
                    self._payload_on = True
                    return True, "payload on"
                if command == "payload.off":
                    self._payload_on = False
                    return True, "payload off"
                if command == "ping":
                    return True, "pong"
                return False, f"unknown_command:{command}"
            except ValueError as exc:
                return False, f"value_error:{exc}"

    def snapshot(self) -> ActuatorState:
        with self._lock:
            return ActuatorState(
                delta_v_total_m_s=self._delta_v_total,
                propellant_remaining_kg=self._thruster.propellant_kg,
                rw_momentum_nms=tuple(self._wheel.momentum_nms),
                rw_saturated=any(
                    abs(component) >= self._wheel.max_momentum_nms - 1e-9
                    for component in self._wheel.momentum_nms
                ),
                heater_on=self._heater.on,
                heater_temp_k=self._heater.temperature_k,
                payload_on=self._payload_on,
                last_command=self._last_command,
                last_command_counter=self._last_counter,
            )

    def snapshot_dict(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "delta_v_total_m_s": snap.delta_v_total_m_s,
            "propellant_remaining_kg": snap.propellant_remaining_kg,
            "rw_momentum_nms": list(snap.rw_momentum_nms),
            "rw_saturated": snap.rw_saturated,
            "heater_on": snap.heater_on,
            "heater_temp_k": snap.heater_temp_k,
            "payload_on": snap.payload_on,
            "last_command": snap.last_command,
            "last_command_counter": snap.last_command_counter,
        }
