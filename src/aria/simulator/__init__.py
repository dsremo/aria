"""ARIA 4D Simulator — 3D spatial trajectory + time for generation ship missions.

Provides:
  - SimulatorEngine: tick-by-tick simulation with ALL subsystems running
  - SimulatorState: complete ship state at any point in spacetime
  - SimulatorTimeline: 4th dimension — seek/replay through mission history
  - SimulatorRecorder: state recording to JSON/SQLite for playback
  - Simulator4D: factory with mission presets (Alpha Centauri, Barnard's Star, etc.)
  - STAR_CATALOG: real stellar coordinates in light-years

Usage:
    from aria.simulator import Simulator4D

    sim = Simulator4D.create_mission("alpha_centauri")
    sim.run(years=43)
    state = sim.timeline.seek(year=20)
    print(state.position_3d)  # [x, y, z] in light-years
"""

from aria.simulator.engine import (
    Simulator4D,
    SimulatorEngine,
    SimulatorState,
    SimulatorTimeline,
    TickResolution,
)
from aria.simulator.recorder import SimulatorRecorder
from aria.simulator.targets import STAR_CATALOG, StarTarget

__all__ = [
    "Simulator4D",
    "SimulatorEngine",
    "SimulatorRecorder",
    "SimulatorState",
    "SimulatorTimeline",
    "StarTarget",
    "STAR_CATALOG",
    "TickResolution",
]
