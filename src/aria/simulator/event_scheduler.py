"""Mission-event scheduler — fire scripted events at specified mission times.

Lets the operator (or a test) say "at year 5.0, trigger maglev_trip" or
"at year 105, transition to deceleration phase". The scheduler ticks each
sim cycle and fires everything past its scheduled time.

This is the back-end for "planned mission events" — the React UI can
show a timeline of upcoming + completed events, and the user can add /
cancel them.

Event payload kinds:
  * 'failure'      — invokes failure_injector.trigger(scenario_id)
  * 'phase'        — invokes mission_phases.transition(target)
  * 'message'      — emits a comms_budget message
  * 'note'         — pure log entry on the bus
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


@dataclass
class ScheduledEvent:
    event_id: str
    fire_at_yr: float
    kind: str          # 'failure' / 'phase' / 'message' / 'note'
    label: str
    payload: dict       # kind-specific data
    fired: bool = False
    fired_at_yr: Optional[float] = None
    note: str = ""


@dataclass
class EventScheduler:
    events: List[ScheduledEvent] = field(default_factory=list)
    next_id: int = 1

    # ── add / cancel ──────────────────────────────────────────

    def schedule(self, fire_at_yr: float, kind: str, label: str, payload: dict | None = None) -> ScheduledEvent:
        if kind not in ("failure", "phase", "message", "note"):
            raise ValueError(f"Unknown event kind '{kind}'")
        evt = ScheduledEvent(
            event_id=f"evt_{self.next_id:04d}",
            fire_at_yr=float(fire_at_yr),
            kind=kind,
            label=label,
            payload=payload or {},
        )
        self.next_id += 1
        self.events.append(evt)
        # Keep events sorted by fire-time
        self.events.sort(key=lambda e: e.fire_at_yr)
        return evt

    def cancel(self, event_id: str) -> bool:
        for i, e in enumerate(self.events):
            if e.event_id == event_id and not e.fired:
                self.events.pop(i)
                return True
        return False

    def clear_fired(self) -> int:
        before = len(self.events)
        self.events = [e for e in self.events if not e.fired]
        return before - len(self.events)

    # ── tick ──────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        for evt in self.events:
            if evt.fired or evt.fire_at_yr > phase.elapsed_yr:
                continue
            self._fire(evt)

    def _fire(self, evt: ScheduledEvent) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        try:
            if evt.kind == "failure":
                from aria.simulator.failure_injector import trigger
                result = trigger(evt.payload.get("scenario_id", ""))
                evt.note = f"injected {evt.payload.get('scenario_id')} → {result.get('impact','')}"
            elif evt.kind == "phase":
                from aria.simulator.mission_phases import Phase
                target = evt.payload.get("to")
                force = bool(evt.payload.get("force", True))
                phase.transition(Phase(target), force=force)
                evt.note = f"phase → {target}"
            elif evt.kind == "message":
                from aria.simulator.comms_budget import get_comms_budget
                msg = get_comms_budget().queue_message(
                    label=evt.payload.get("label", "scheduled message"),
                    bytes_size=int(evt.payload.get("bytes_size", 1024)),
                )
                evt.note = f"queued message {msg.msg_id}"
            else:   # note
                evt.note = evt.payload.get("text", evt.label)

            evt.fired = True
            evt.fired_at_yr = phase.elapsed_yr
            bus.publish(f"scheduler.fired.{evt.kind}",
                        severity="info", source="event_scheduler",
                        payload={"event_id": evt.event_id, "label": evt.label,
                                 "kind": evt.kind, "note": evt.note},
                        sim_time_yr=phase.elapsed_yr)
        except Exception as e:
            evt.note = f"FIRE FAILED: {type(e).__name__}: {e}"
            evt.fired = True
            evt.fired_at_yr = phase.elapsed_yr
            bus.publish("scheduler.fire_error",
                        severity="warning", source="event_scheduler",
                        payload={"event_id": evt.event_id, "error": str(e)},
                        sim_time_yr=phase.elapsed_yr)

    # ── serialisation ─────────────────────────────────────────

    def to_dict(self) -> dict:
        phase = get_phase_controller()
        return {
            "current_yr": round(phase.elapsed_yr, 4),
            "next_id":    self.next_id,
            "events": [
                {
                    "event_id":     e.event_id,
                    "fire_at_yr":   round(e.fire_at_yr, 4),
                    "kind":         e.kind,
                    "label":        e.label,
                    "payload":      e.payload,
                    "fired":        e.fired,
                    "fired_at_yr":  round(e.fired_at_yr, 4) if e.fired_at_yr is not None else None,
                    "note":         e.note,
                }
                for e in self.events
            ],
            "stats": {
                "total":  len(self.events),
                "fired":  sum(1 for e in self.events if e.fired),
                "pending": sum(1 for e in self.events if not e.fired),
            },
        }

    def restore_from_dict(self, saved: dict) -> list[str]:
        """Rebuild ScheduledEvent dataclasses from the saved list. The generic
        mission_persistence restore would leave `self.events` as a list of raw
        dicts, which would crash tick() at `evt.fired`."""
        self.events.clear()
        for edict in saved.get("events", []) or []:
            try:
                self.events.append(ScheduledEvent(
                    event_id=str(edict.get("event_id", "")),
                    fire_at_yr=float(edict.get("fire_at_yr", 0.0)),
                    kind=str(edict.get("kind", "note")),
                    label=str(edict.get("label", "")),
                    payload=dict(edict.get("payload") or {}),
                    fired=bool(edict.get("fired", False)),
                    fired_at_yr=edict.get("fired_at_yr"),
                    note=str(edict.get("note", "")),
                ))
            except (TypeError, ValueError):
                continue
        self.next_id = int(saved.get("next_id", len(self.events) + 1))
        return ["events", "next_id"]


_DEFAULT: Optional[EventScheduler] = None


def get_scheduler() -> EventScheduler:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = EventScheduler()
    return _DEFAULT


def reset_scheduler() -> None:
    global _DEFAULT
    _DEFAULT = EventScheduler()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("event_scheduler", get_scheduler().tick, order=10)
