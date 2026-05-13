"""Save / load mission state.

Snapshot every singleton's state to a single JSON document; restore from
that JSON on load. Lets the operator checkpoint a mission at year 5,
inject failures, see what happens, and roll back.

The save format is a top-level object with one key per subsystem,
matching its module name. Each subsystem is responsible for serialising
its own state (we just call .to_dict()) and for restoring (we set
attributes back via setattr — works because the state objects are
plain dataclasses).

Save files are not promised to be backward-compatible across versions —
this is a checkpoint mechanism, not a long-term archive format.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


# Map of subsystem name → (singleton-getter, reset-fn, optional-restore-fn)
# The restore function takes the saved-state dict and applies it.
#
# R8 (2026-04-24, sync refactor): MissionClock + MissionState added at
# the top.  Without these, save/restore left the central clock and
# crew_alive at whatever the live singletons held BEFORE the restore;
# every other subsystem snapped back to the saved year-50 state but
# the clock kept reporting year-50.x, and downstream anomaly detectors
# flagged the time discontinuity as a false event.
_SUBSYSTEMS = [
    ("mission_clock",     "aria.core.mission_clock",          "get_mission_clock",         "reset_mission_clock",   None),
    ("mission_state",     "aria.core.mission_state",          "get_mission_state",         "reset_mission_state",   None),
    ("mission_phases",    "aria.simulator.mission_phases",    "get_phase_controller",      None,                  None),
    ("startup_sequence",  "aria.simulator.startup_sequence",  "get_startup_controller",    "reset_startup_controller", None),
    ("trajectory_state",  "aria.simulator.trajectory_state",  "get_trajectory_state",      "reset_trajectory_state", None),
    ("fuel_tracker",      "aria.simulator.fuel_tracker",      "get_fuel_inventory",        "reset_fuel_inventory",   None),
    ("crew_health",       "aria.simulator.crew_health",       "get_crew_health",           "reset_crew_health",      None),
    ("computing_radiation","aria.simulator.computing_radiation","get_computing_radiation", "reset_computing_radiation",None),
    ("eclss_contaminants","aria.simulator.eclss_contaminants","get_eclss_contaminants",    "reset_eclss_contaminants",None),
    ("bearing_dynamics",  "aria.simulator.bearing_dynamics",  "get_bearing_state",         "reset_bearing_state",    None),
    ("propulsion_thermal","aria.simulator.propulsion_thermal","get_propulsion_thermal",    "reset_propulsion_thermal",None),
    ("power_tracker",     "aria.simulator.power_tracker",     "get_power_budget",          "reset_power_budget",     None),
    ("comms_budget",      "aria.simulator.comms_budget",      "get_comms_budget",          "reset_comms_budget",     None),
    ("agriculture_yield", "aria.simulator.agriculture_yield", "get_agriculture",           "reset_agriculture",      None),
    ("hull_damage",       "aria.simulator.hull_damage",       "get_hull_damage",           "reset_hull_damage",      "restore_from_dict"),
    ("random_events",     "aria.simulator.random_events",     "get_random_events",         "reset_random_events",    None),
    ("event_scheduler",   "aria.simulator.event_scheduler",   "get_scheduler",             "reset_scheduler",        "restore_from_dict"),
]


def _get_singleton(modpath: str, fn: str) -> Any:
    import importlib
    return getattr(importlib.import_module(modpath), fn)()


def _reset_singleton(modpath: str, fn: Optional[str]) -> None:
    if fn is None:
        return
    import importlib
    getattr(importlib.import_module(modpath), fn)()


def snapshot() -> Dict[str, Any]:
    """Capture full mission state."""
    out: Dict[str, Any] = {
        "_meta": {
            "saved_at_wall": datetime.utcnow().isoformat() + "Z",
            "schema_version": 1,
        },
    }
    for name, modpath, getter, _reset, _restore in _SUBSYSTEMS:
        try:
            obj = _get_singleton(modpath, getter)
            out[name] = obj.to_dict()
        except Exception as e:
            out[name] = {"_error": f"{type(e).__name__}: {e}"}
    return out


def save_to_file(path: str | Path) -> Path:
    """Write snapshot to `path` (creates parent dirs if needed)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        json.dump(snapshot(), f, indent=2)
    return p.resolve()


def restore(state: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a saved snapshot. Subsystems are restored field-by-field via
    setattr where the attribute exists. Restoration is best-effort —
    fields the running version doesn't recognise are skipped, with a note.

    Returns a per-subsystem report of what was applied / skipped.
    """
    report: Dict[str, Any] = {"applied": [], "missing": [], "errors": []}
    for name, modpath, getter, reset, custom in _SUBSYSTEMS:
        if name not in state or "_error" in state[name]:
            report["missing"].append(name)
            continue
        try:
            _reset_singleton(modpath, reset)        # fresh state to overwrite
            obj = _get_singleton(modpath, getter)
            saved = state[name]
            # Prefer a subsystem-provided restore method when the on-wire shape
            # can't be mapped field-for-field (e.g. regions dict serialised as
            # list of dicts). Falls back to the generic copier otherwise.
            if custom and hasattr(obj, custom):
                applied_fields = getattr(obj, custom)(saved) or []
            else:
                applied_fields = _restore_object(obj, saved)
            report["applied"].append({"name": name, "fields": applied_fields})
        except Exception as e:
            report["errors"].append({"name": name, "error": f"{type(e).__name__}: {e}"})
    return report


def _restore_object(obj: Any, saved: Dict[str, Any]) -> list[str]:
    """Walk `saved` (dict) and copy any matching scalar/dict fields onto
    `obj`. Returns the list of fields that were applied."""
    applied: list[str] = []
    for key, value in saved.items():
        if key.startswith("_"):
            continue
        if hasattr(obj, key):
            cur = getattr(obj, key)
            # Scalar overwrite (numbers, strings, bools, None)
            if isinstance(value, (int, float, str, bool, type(None))):
                try:
                    setattr(obj, key, value)
                    applied.append(key)
                except Exception:
                    pass
            # If existing field is a dict, merge value into it
            elif isinstance(cur, dict) and isinstance(value, dict):
                cur.clear()
                cur.update(value)
                applied.append(key)
            # If list of dicts, just replace
            elif isinstance(cur, list) and isinstance(value, list):
                cur.clear()
                cur.extend(value)
                applied.append(key)
    return applied


def load_from_file(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r") as f:
        state = json.load(f)
    return restore(state)
