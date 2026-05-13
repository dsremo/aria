"""Event detection during orbit propagation.

Detects when specific conditions occur during propagation:
- Apoapsis/periapsis crossing
- Eclipse entry/exit
- Ground station contact (AOS/LOS)
- Altitude threshold crossing
- Custom boolean conditions

Uses bisection root-finding on a continuous event function g(t,r,v).
When g changes sign between two steps, the exact crossing time is
found to within the specified tolerance.

Algorithm approach studied from:
- Open Space Toolkit EventCondition framework (Apache 2.0)
- Orekit EventDetector (Apache 2.0, Java)

References:
    Montenbruck & Gill (2000). "Satellite Orbits" §7.4 event location.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np


@dataclass
class DetectedEvent:
    """An event detected during propagation."""
    name: str
    time: float               # exact time of event [s]
    position: np.ndarray      # position at event [m]
    velocity: np.ndarray      # velocity at event [m/s]
    value: float              # event function value at crossing


class EventCondition:
    """A condition to detect during orbit propagation.

    The event function g(t, r, v) should be continuous. An event is
    detected when g changes sign between two propagation steps.

    Args:
        name: human-readable event name
        g_fn: callable(t, r, v) → float (event function)
        direction: +1 (rising only), -1 (falling only), 0 (both)
        terminal: if True, stop propagation when event occurs
    """

    def __init__(
        self,
        name: str,
        g_fn: Callable[[float, np.ndarray, np.ndarray], float],
        direction: int = 0,
        terminal: bool = False,
    ) -> None:
        self.name = name
        self.g_fn = g_fn
        self.direction = direction
        self.terminal = terminal


def detect_events(
    accel_fn: Callable[[float, np.ndarray], np.ndarray],
    r0: np.ndarray,
    v0: np.ndarray,
    t0: float,
    t_end: float,
    dt: float,
    events: List[EventCondition],
    tol: float = 1e-6,
    max_bisections: int = 50,
) -> Tuple[np.ndarray, np.ndarray, float, List[DetectedEvent]]:
    """Propagate with event detection using RK4 + bisection.

    Returns (r_final, v_final, t_final, detected_events).
    Propagation stops early if a terminal event is detected.
    """
    r = np.asarray(r0, dtype=float).copy()
    v = np.asarray(v0, dtype=float).copy()
    t = float(t0)

    detected: List[DetectedEvent] = []

    # Initial event function values
    g_prev = {i: ev.g_fn(t, r, v) for i, ev in enumerate(events)}

    while t < t_end:
        h = min(dt, t_end - t)

        # RK4 step
        r_new, v_new = _rk4_step(accel_fn, t, r, v, h)
        t_new = t + h

        # Check each event for sign change
        for i, ev in enumerate(events):
            g_new = ev.g_fn(t_new, r_new, v_new)

            if g_prev[i] * g_new < 0:
                # Sign change — event crossing detected
                # Check direction
                rising = g_new > g_prev[i]
                if ev.direction == 1 and not rising:
                    g_prev[i] = g_new
                    continue
                if ev.direction == -1 and rising:
                    g_prev[i] = g_new
                    continue

                # Bisection to find exact crossing time
                t_lo, t_hi = t, t_new
                r_lo, v_lo = r.copy(), v.copy()

                for _ in range(max_bisections):
                    t_mid = 0.5 * (t_lo + t_hi)
                    r_mid, v_mid = _rk4_step(accel_fn, t, r, v, t_mid - t)
                    g_mid = ev.g_fn(t_mid, r_mid, v_mid)

                    if abs(g_mid) < tol or (t_hi - t_lo) < tol:
                        break

                    if g_prev[i] * g_mid < 0:
                        t_hi = t_mid
                    else:
                        t_lo = t_mid
                        g_prev[i] = g_mid

                # Record event
                r_evt, v_evt = _rk4_step(accel_fn, t, r, v, t_mid - t)
                detected.append(DetectedEvent(
                    name=ev.name,
                    time=t_mid,
                    position=r_evt,
                    velocity=v_evt,
                    value=g_mid,
                ))

                if ev.terminal:
                    return r_evt, v_evt, t_mid, detected

            g_prev[i] = g_new

        r = r_new
        v = v_new
        t = t_new

    return r, v, t, detected


def _rk4_step(accel_fn, t, r, v, h):
    """Single RK4 step."""
    a1 = accel_fn(t, r)
    r2 = r + 0.5 * h * v
    v2 = v + 0.5 * h * a1
    a2 = accel_fn(t + 0.5 * h, r2)
    r3 = r + 0.5 * h * v2
    v3 = v + 0.5 * h * a2
    a3 = accel_fn(t + 0.5 * h, r3)
    r4 = r + h * v3
    v4 = v + h * a3
    a4 = accel_fn(t + h, r4)
    r_new = r + h / 6 * (v + 2*v2 + 2*v3 + v4)
    v_new = v + h / 6 * (a1 + 2*a2 + 2*a3 + a4)
    return r_new, v_new


# ══════════════════════════════════════════════════════════════════
#  Built-in event conditions
# ══════════════════════════════════════════════════════════════════

def periapsis_event(mu: float) -> EventCondition:
    """Detect periapsis crossing (r_dot changes from negative to positive)."""
    def g(t, r, v):
        return np.dot(r, v)  # r·v = 0 at apsides; negative→positive = periapsis
    return EventCondition("periapsis", g, direction=1)


def apoapsis_event(mu: float) -> EventCondition:
    """Detect apoapsis crossing (r_dot changes from positive to negative)."""
    def g(t, r, v):
        return np.dot(r, v)
    return EventCondition("apoapsis", g, direction=-1)


def altitude_crossing(altitude_m: float, R_body: float = 6378137.0) -> EventCondition:
    """Detect when altitude crosses a threshold."""
    target_r = R_body + altitude_m
    def g(t, r, v):
        return np.linalg.norm(r) - target_r
    return EventCondition(f"altitude_{altitude_m/1000:.0f}km", g, direction=0)


def eclipse_event(
    R_body: float = 6378137.0,
    sun_position_fn: Optional[Callable[[float], np.ndarray]] = None,
) -> EventCondition:
    """Detect eclipse entry/exit (shadow of central body).

    Uses line-of-sight check from nbody module.
    """
    def g(t, r, v):
        if sun_position_fn is None:
            r_sun = np.array([1.496e11, 0, 0])  # approximate Sun position
        else:
            r_sun = sun_position_fn(t)
        from aria.physics.gravity.nbody import line_of_sight
        return 1.0 if line_of_sight(r, r_sun, R_body) else -1.0

    return EventCondition("eclipse", g, direction=0)


def ground_contact_event(
    station_ecef: np.ndarray,
    min_elevation_deg: float = 5.0,
    R_body: float = 6378137.0,
) -> EventCondition:
    """Detect ground station contact (satellite above min elevation).

    Note: assumes ECEF ≈ ECI for simplicity (valid for short arcs).
    """
    sin_el = math.sin(math.radians(min_elevation_deg))

    def g(t, r, v):
        delta = r - station_ecef
        delta_norm = np.linalg.norm(delta)
        if delta_norm < 1e-10:
            return 1.0
        # Elevation: angle above local horizon
        r_sta = np.linalg.norm(station_ecef)
        cos_zenith = np.dot(delta, station_ecef) / (delta_norm * r_sta)
        sin_elev = -cos_zenith  # negative because delta points away from center
        return sin_elev - sin_el

    return EventCondition("ground_contact", g, direction=0)
