"""Mission narrative log — turns the event bus stream into a
human-readable "captain's log".

Subscribes to high-level topics on the event bus, formats each event
into a short prose sentence, and accumulates them into a chronological
narrative the operator can read end-to-end.

This is not an LLM — it's deterministic templates per topic family. The
output reads like:

    Year 5.20  ▶ Mission Boost begun
    Year 5.21  ⚠ Maglev controller fault — habitat ring on roller backup
    Year 6.00  ✓ Reactor reached full power
    Year 7.43  ⚠ Micrometeoroid impact on Hull Zone 3 (8 kJ)
    Year 7.43     · Repair task created (8 kg feedstock, 4 crew-hours)
    ...

Keeps the latest N entries (configurable). Good for end-of-mission
reports, debriefs, and the React UI's "narrative" tab.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


@dataclass(frozen=True)
class NarrativeEntry:
    sim_time_yr: float
    severity: str
    icon: str
    text: str
    topic: str
    wall_ts: float


# Template prefixes per topic family — keep this table here so adding a
# new event is one row not a code change.
_TOPIC_TEMPLATES: Dict[str, tuple[str, str]] = {
    # (icon, prose template — uses {payload} shorthand for substitution)
    "phase.transition":          ("▶", "Phase transition: {old} → {new}"),
    # R7 (2026-04-24, sync refactor): subsystem tick errors are
    # diagnostic gold — render them prominently.
    "tick.subsystem_error":      ("✗", "Subsystem tick crashed: {subsystem} — {error}"),
    "mission.clock.reset":       ("↺", "Mission clock reset to T+ {to_yr:.3f} yr (gen {generation})"),
    "bus.queue_overflow":        ("⚠", "Event-bus subscriber queue full — events dropping (pattern={pattern})"),
    "tick.advanced":             ("·", "Sim advanced {dt_s} s in {wall_ms} ms"),
    "trajectory.milestone":      ("◆", "Mission milestone — {milestone_pct} % distance reached"),
    "trajectory.arrival":        ("✓", "Arrival at {target}"),
    "trajectory.fuel_low":       ("⚠", "Propellant remaining below 5 % ({remaining_frac:.3f})"),

    "reactor.scram":             ("⚠", "Reactor SCRAM"),
    "bearing.transition.roller": ("⚠", "Habitat-ring maglev tripped — on roller backup"),
    "bearing.transition.off":    ("⚠", "Habitat ring offline — both bearings down"),
    "bearing.transition.magnetic":("✓", "Habitat-ring maglev re-engaged"),
    "bearing.alarm":             ("⚠", "Bearing alarm: {message}"),

    "propulsion.thermal.throttle": ("⚠", "Auto-throttle engaged — thermal margin negative"),
    "propulsion.thermal.hull_overtemp": ("⚠", "Hull aft-cap overtemperature"),

    "power.overload.shed":       ("⚠", "Power overload — load shedding {shed_subsystems}"),
    "auto_tick.started":         ("▶", "Auto-tick started at {speed_factor}× speed"),
    "auto_tick.stopped":         ("⏸", "Auto-tick stopped"),

    "avionics.ecc_escape":       ("⚠", "Avionics: SEU escaped ECC (silent corruption)"),
    "avionics.ecc_detect_only_halt": ("⚠", "Avionics: SEU triggered ECC halt"),

    "eclss.contaminant":         ("⚠", "ECLSS contaminant breach"),
    "agriculture.harvest":       ("·", "Harvest: {crop} yielded {harvest_kg:.1f} kg"),
    "agriculture.shortage":      ("⚠", "Food shortage — {days_short} days short"),
    "agriculture.failure":       ("⚠", "Agriculture failure — {failure}"),

    "comms.transmitted":         ("→", "Earth comm queued ({bytes} B) — ETA {eta_earth_yr:.3f} yr"),
    "comms.delivered":           ("✓", "Earth comm delivered: {label}"),

    "fuel.main.low":             ("⚠", "Main fuel below 5 %"),
    "fuel.main.empty":           ("⚠", "Main fuel tank empty"),

    "hull.impact":               ("⚠", "MMOD impact on hull zone — {energy_j:.0f} J"),
    "hull.repair":               ("✓", "Hull repair complete on {region_id}"),

    "env.solar_flare":           ("⚠", "Solar flare — radiation rate ×50"),

    "scheduler.fired":           ("◆", "Scheduled event fired: {label}"),

    "objective.complete":        ("✓", "Objective complete: {label}"),
    "failure_injector":          ("⚠", "Operator drill: {label} — {impact}"),

    "repair.complete":           ("✓", "Repair complete on {source}"),

    "crew.health.warning":       ("⚠", "Crew health warning: {message}"),
    "crew.health.critical":      ("⚠", "Crew health CRITICAL: {message}"),
    "crew.overtime":             ("·", "Overtime: band {band} +{extra_hours} hr"),
}


def _render(topic: str, payload: dict, severity: str) -> tuple[str, str]:
    """Pick the best matching template by topic prefix."""
    best_key = None
    for key in _TOPIC_TEMPLATES:
        if topic == key or topic.startswith(key + "."):
            if best_key is None or len(key) > len(best_key):
                best_key = key
    if best_key is None:
        # Fallback — generic format
        sev_icon = {"critical": "⚠", "warning": "⚠", "info": "·", "debug": "·"}.get(severity, "·")
        return (sev_icon, f"{topic}  payload={payload}")
    icon, template = _TOPIC_TEMPLATES[best_key]
    try:
        return (icon, template.format(**payload))
    except (KeyError, IndexError):
        # Missing payload field — render template literally
        return (icon, f"{topic}  payload={payload}")


@dataclass
class NarrativeLogState:
    capacity: int = 20_000
    entries: Deque[NarrativeEntry] = field(default_factory=lambda: deque(maxlen=20_000))
    subscribed: bool = False
    # R7 (2026-04-24, sync refactor): removed `tick.subsystem_error`
    # from the suppress list — it was hiding the most diagnostically
    # important class of event (subsystem tick crashes) under the
    # same prefix as routine `tick.advanced`.  An operator now sees
    # these in the narrative log, where they belong.
    suppress_topics: List[str] = field(default_factory=lambda: ["tick.advanced"])

    # ── lifecycle ───────────────────────────────────────────

    def subscribe(self) -> None:
        """Subscribe to the bus — idempotent."""
        if self.subscribed:
            return
        from aria.simulator.event_bus import get_event_bus
        bus = get_event_bus()
        bus.subscribe("*", self._on_event)
        self.subscribed = True

    def _on_event(self, event) -> None:   # type: ignore[no-untyped-def]
        # Skip noisy topics
        for sup in self.suppress_topics:
            if event.topic == sup or event.topic.startswith(sup + "."):
                return
        icon, text = _render(event.topic, event.payload, event.severity)
        entry = NarrativeEntry(
            sim_time_yr=event.sim_time_yr,
            severity=event.severity,
            icon=icon,
            text=text,
            topic=event.topic,
            wall_ts=event.timestamp,
        )
        self.entries.append(entry)

    # ── operator API ─────────────────────────────────────────

    def clear(self) -> None:
        self.entries.clear()

    def add_note(self, text: str, severity: str = "info") -> None:
        from aria.simulator.mission_phases import get_phase_controller
        self.entries.append(NarrativeEntry(
            sim_time_yr=get_phase_controller().elapsed_yr,
            severity=severity, icon="✎", text=text, topic="operator.note",
            wall_ts=time.time(),
        ))

    # ── serialisation ──────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "capacity": self.capacity,
            "subscribed": self.subscribed,
            "entry_count": len(self.entries),
            "suppress_topics": self.suppress_topics,
            "entries": [
                {
                    "sim_time_yr": round(e.sim_time_yr, 4),
                    "severity":    e.severity,
                    "icon":        e.icon,
                    "text":        e.text,
                    "topic":       e.topic,
                    "wall_ts":     e.wall_ts,
                }
                for e in list(self.entries)[-200:]
            ],
        }

    def to_text(self, limit: int = 100) -> str:
        """Produce a plain-text 'captain's log' for export."""
        items = list(self.entries)[-limit:]
        lines = []
        for e in items:
            yr = f"Year {e.sim_time_yr:>7.2f}"
            lines.append(f"{yr}  {e.icon} {e.text}")
        return "\n".join(lines)


_DEFAULT: Optional[NarrativeLogState] = None


def get_narrative_log() -> NarrativeLogState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = NarrativeLogState()
        _DEFAULT.subscribe()
    return _DEFAULT


def reset_narrative_log() -> None:
    global _DEFAULT
    _DEFAULT = NarrativeLogState()
    _DEFAULT.subscribe()
