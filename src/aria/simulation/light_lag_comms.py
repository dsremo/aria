"""Light-lag command queue for interstellar / deep-space operations.

Every command issued from Earth to a spacecraft has to wait one
light-time (one-way latency); every telemetry packet from the
spacecraft has to wait the same time on the way back.  At 4.24 ly
to Alpha Centauri the round-trip is **8.48 years** — long enough
that an operator who issues a "do X" command in 2030 won't see
*any* response until 2038.

ARIA's interstellar simulators (`generation_ship`, `interstellar`,
`braking_architecture`) treat command-execution as instantaneous.
That's fine for trajectory math but lies about operational reality:

* a command queued today won't fire until later;
* a response received today reflects a state ≥ 1 light-time old;
* the spacecraft must take autonomous decisions whenever the
  question lifetime is shorter than one round-trip.

This module gives every simulator a tiny scheduler that:

  1. accepts a command at sim-time T₀ from Earth;
  2. delays its execution to T₀ + d/c on the spacecraft side;
  3. captures a response and delays it again by d/c on the way back;
  4. exposes both queues so the UI / log can show what's "in flight".

It's deliberately distance-aware (you supply the spacecraft's current
distance from Earth as a function of sim-time), so the same queue
correctly models a Moon mission (1.3 s) and an Alpha Centauri probe
(4.24 yr).

References
----------
* Pratt, A.  *Deep Space Communications*. NASA SP-2012-4408, §3.2 —
  command-response latency over DSN.
* Heller, R. & Hippke, M. (2017). *Deceleration of high-velocity
  interstellar photon sails into bound orbits at α Centauri.*
  ApJL 835:L32 — round-trip-latency operational regime.
"""

from __future__ import annotations

import enum
import heapq
import itertools
import math
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


# Speed of light.  NIST CODATA 2018 exact value (Tiesinga et al. 2021
# Rev Mod Phys 93 025010).
C_M_S = 299_792_458.0
LY_M = 9.4607304725808e15        # IAU 2012 Resolution B2 light-year [m]
AU_M = 1.495978707e11            # IAU 2012 Resolution B2 astronomical unit [m]


class CommandStatus(str, enum.Enum):
    PENDING = "pending"          # queued on Earth, in-flight outbound
    EXECUTING = "executing"      # arrived at spacecraft, executor running
    DONE = "done"                # response generated; in-flight inbound
    ACKED = "acked"              # response back at Earth — operator can see it
    FAILED = "failed"


@dataclass
class Command:
    """A single Earth→spacecraft command with a planned response."""
    cmd_id: int
    issued_at_yr: float                    # Earth sim-time when queued
    arrives_at_yr: float                   # spacecraft sim-time when delivered
    payload: dict
    response: Optional[dict] = None
    response_at_yr: Optional[float] = None  # Earth sim-time when ACK lands
    status: CommandStatus = CommandStatus.PENDING


# Internal heap ordering: (timestamp, counter, command, kind) — counter
# breaks ties so heappop is deterministic across same-time events.
_counter = itertools.count()


@dataclass
class LightLagCommandQueue:
    """Bidirectional command/telemetry queue with light-time delays.

    The queue is a single heap of (event_time_yr, counter, cmd, kind)
    tuples sorted by sim-time; advancing the simulator to time T pops
    every event with t ≤ T and updates command status accordingly.

    Parameters
    ----------
    distance_at_yr : Callable[[float], float]
        Function returning the spacecraft's distance from Earth in
        metres at a given Earth sim-time (years).  For a constant-
        velocity cruise this is just ``v * t``; for trajectories with
        boost/cruise/decel phases pass in a function that integrates
        the trajectory.
    autonomous_handlers : Optional[dict]
        Maps command kind (string) → handler ``(payload) → response``.
        These handlers run *on the spacecraft side* — i.e. at
        ``arrives_at_yr``, not at ``issued_at_yr``.  Use them to model
        autonomous decisions the spacecraft can take without consulting
        Earth (e.g. fault recovery, attitude trim).
    """
    distance_at_yr: Callable[[float], float]
    autonomous_handlers: Optional[dict[str, Callable[[dict], dict]]] = None

    _earth_now_yr: float = 0.0
    _commands: dict[int, Command] = field(default_factory=dict)
    _heap: list = field(default_factory=list)

    def issue(self, kind: str, payload: dict) -> Command:
        """Earth issues a command at the current sim-time.

        The command is delivered at the spacecraft side after a
        one-way light-time delay computed from the spacecraft's
        current distance.  We freeze the distance at issue-time
        rather than recomputing later — over a single light-time the
        spacecraft moves significantly, but the command was sent based
        on Earth's view of its position *now*.
        """
        d_m = max(0.0, self.distance_at_yr(self._earth_now_yr))
        light_time_yr = (d_m / C_M_S) / (365.25 * 24 * 3600)
        arrives = self._earth_now_yr + light_time_yr
        cmd = Command(
            cmd_id=next(_counter),
            issued_at_yr=self._earth_now_yr,
            arrives_at_yr=arrives,
            payload={**payload, "kind": kind},
        )
        self._commands[cmd.cmd_id] = cmd
        # Schedule the "arrival" event.
        heapq.heappush(self._heap, (arrives, cmd.cmd_id, "arrive"))
        return cmd

    def advance_earth_clock(self, new_now_yr: float) -> list[Command]:
        """Move Earth's clock forward to ``new_now_yr`` and process any
        events whose timestamps fall within the window.  Returns the list
        of commands that newly transitioned to ``ACKED`` so the caller
        (UI / log) can render them.

        ``new_now_yr`` is the *Earth* sim-time.  Spacecraft-side events
        with ``arrives_at_yr ≤ new_now_yr`` execute and queue an inbound
        ACK whose return time is ``arrives_at_yr + d(arrives_at_yr) / c``.
        """
        if new_now_yr < self._earth_now_yr:
            raise ValueError("clock cannot run backward")
        newly_acked: list[Command] = []

        while self._heap and self._heap[0][0] <= new_now_yr:
            t_event, cmd_id, kind = heapq.heappop(self._heap)
            cmd = self._commands.get(cmd_id)
            if cmd is None:
                continue
            if kind == "arrive":
                # Spacecraft receives the command, runs its handler
                # (or, if no handler is registered, marks DONE with an
                # empty response so Earth still gets an ACK).  The
                # handler runs in spacecraft time, but for ARIA's
                # purposes we treat it as instantaneous on the
                # spacecraft (computational time is negligible
                # compared with light-lag).
                cmd.status = CommandStatus.EXECUTING
                handler = (self.autonomous_handlers or {}).get(
                    cmd.payload.get("kind", ""),
                )
                try:
                    cmd.response = handler(cmd.payload) if handler else {"ok": True}
                    cmd.status = CommandStatus.DONE
                except Exception as exc:  # never let a handler kill the loop
                    cmd.response = {"error": f"{type(exc).__name__}: {exc}"}
                    cmd.status = CommandStatus.FAILED

                # Schedule ACK return.  Distance at the moment the
                # spacecraft is sending the response — likely different
                # from issue-time distance if the ship moved during the
                # outbound flight.
                d_m_back = max(0.0, self.distance_at_yr(t_event))
                light_time_back = (d_m_back / C_M_S) / (365.25 * 24 * 3600)
                ack_at = t_event + light_time_back
                cmd.response_at_yr = ack_at
                heapq.heappush(self._heap, (ack_at, cmd_id, "ack"))

            elif kind == "ack":
                # ACK arrives at Earth — operator can finally see it.
                if cmd.status not in (CommandStatus.FAILED,):
                    cmd.status = CommandStatus.ACKED
                newly_acked.append(cmd)

        self._earth_now_yr = new_now_yr
        return newly_acked

    # ── Inspection ────────────────────────────────────────────────

    @property
    def now_yr(self) -> float:
        return self._earth_now_yr

    def in_flight(self) -> list[Command]:
        """Commands that haven't acked yet — anything not ACKED/FAILED."""
        return [c for c in self._commands.values()
                if c.status not in (CommandStatus.ACKED, CommandStatus.FAILED)]

    def round_trip_latency_yr(self) -> float:
        """Current Earth↔spacecraft round-trip latency in years.

        Useful for status panels: shows the operator how stale the
        next telemetry will be when it arrives.
        """
        d_m = max(0.0, self.distance_at_yr(self._earth_now_yr))
        return 2.0 * (d_m / C_M_S) / (365.25 * 24 * 3600)

    def all_commands(self) -> list[Command]:
        return list(self._commands.values())


# ── Pre-built distance functions for common missions ─────────────────


def constant_cruise_distance(velocity_c: float) -> Callable[[float], float]:
    """Constant-velocity cruise — distance = v · t (in metres)."""
    v_m_s = velocity_c * C_M_S
    def d(yr: float) -> float:
        return v_m_s * (yr * 365.25 * 24 * 3600)
    return d


def boost_cruise_decel_distance(
    boost_yr: float,
    cruise_yr: float,
    decel_yr: float,
    cruise_velocity_c: float,
) -> Callable[[float], float]:
    """Three-phase mission profile.

    Boost: linear ramp 0 → v_c over ``boost_yr``.
    Cruise: constant v_c for ``cruise_yr``.
    Decel: linear ramp v_c → 0 over ``decel_yr``.
    After deceleration the spacecraft is parked — distance is
    constant at the arrival distance.
    """
    v_c_m_s = cruise_velocity_c * C_M_S
    s_per_yr = 365.25 * 24 * 3600
    # Distances at end of each phase (closed-form for linear ramps).
    d_boost  = 0.5 * v_c_m_s * boost_yr * s_per_yr
    d_cruise = d_boost + v_c_m_s * cruise_yr * s_per_yr
    d_arrival = d_cruise + 0.5 * v_c_m_s * decel_yr * s_per_yr

    def d(yr: float) -> float:
        if yr <= 0:
            return 0.0
        if yr < boost_yr:
            return 0.5 * v_c_m_s * yr * s_per_yr * (yr / boost_yr)
        if yr < boost_yr + cruise_yr:
            return d_boost + v_c_m_s * (yr - boost_yr) * s_per_yr
        if yr < boost_yr + cruise_yr + decel_yr:
            t_in_decel = yr - boost_yr - cruise_yr
            v_at_t = v_c_m_s * (1.0 - t_in_decel / decel_yr)
            avg_v = 0.5 * (v_c_m_s + v_at_t)
            return d_cruise + avg_v * t_in_decel * s_per_yr
        return d_arrival

    return d
