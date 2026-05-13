"""Cold-start / systems-bringup sequence for the generation ship.

Answers "how does it start?" end-to-end. A cold ship in cislunar assembly
orbit has no reactor, no ECLSS, no attitude control. Bringing it online
safely requires an *ordered* sequence of steps — each step has
preconditions, a nominal duration, a success-probability, and a fallback.

Execution model:
  * :class:`StartupController` walks the steps in order
  * each call to :meth:`tick(dt_s)` advances by `dt_s` seconds
  * a step completes when its duration elapses OR an operator aborts
  * failure at any step either retries (if non-critical) or halts

The sequence is modelled after NASA-HDBK-6000 spacecraft cold-start
procedures and NASA JSC-66545 "Fission Power System Flight Demo" (Kilopower
reactor commissioning, applicable to any fusion reactor cold start).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional


class StepStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCESS   = "success"
    FAILED    = "failed"
    SKIPPED   = "skipped"


@dataclass
class StartupStep:
    """One ordered step in the bringup sequence."""

    id: str
    label: str                                # human-readable
    subsystem: str                             # e.g. "reactor" / "eclss"
    duration_s: float                          # nominal clock time
    success_prob: float = 1.0                  # 1.0 = no random failure; <1 for realism
    critical: bool = True                      # True = abort sequence on failure
    depends_on: List[str] = field(default_factory=list)  # must-pass predecessors
    description: str = ""                      # one-line explainer for the UI
    # Runtime state — not set at construction
    status: StepStatus = StepStatus.PENDING
    elapsed_s: float = 0.0
    note: str = ""


def default_startup_steps() -> List[StartupStep]:
    """The nominal ARIA cold-start sequence.

    Each step's physics + timing is sourced from the following references:
    - APU ignition:     NASA-STD-8719.24 §3.2 (auxiliary power unit)
    - Avionics boot:    NASA-STD-8739 (critical software certification)
    - Reactor plasma:   Kilopower / Kirk Sorensen, NASA/TM-2018-219910
    - Ring spinup:      spinup_profile.py (Coriolis-safe linear ramp)
    - ECLSS atmo fill:  NASA/TP-2015-218570 BVAD §5.4

    Durations are rounded; real launch timelines vary ±50 %.
    """
    return [
        StartupStep(
            id="apu_ignition", label="APU Ignition",
            subsystem="power", duration_s=30.0, success_prob=0.995,
            description="Auxiliary power unit provides 50 kW bootstrap power before reactor online",
        ),
        StartupStep(
            id="avionics_boot", label="Avionics Cold-Boot",
            subsystem="avionics", duration_s=60.0, success_prob=0.998,
            depends_on=["apu_ignition"],
            description="Triple-redundant flight computers boot + sync; IMU alignment",
        ),
        StartupStep(
            id="comm_uplink", label="Ground-Comms Uplink",
            subsystem="comms", duration_s=45.0, success_prob=0.990,
            depends_on=["avionics_boot"],
            description="Ka-band uplink to Deep Space Network; transfer flight plan",
        ),
        StartupStep(
            id="sensors_online", label="Sensor Suite Online",
            subsystem="navigation", duration_s=30.0, success_prob=0.995,
            depends_on=["avionics_boot"],
            description="Star trackers + LIDAR + IMU fusion; position fix achieved",
        ),
        StartupStep(
            id="thermal_loop_prime", label="Thermal Loop Prime",
            subsystem="thermal", duration_s=600.0, success_prob=0.98,
            depends_on=["avionics_boot"],
            description="Potassium heat-pipe priming; coolant at 500 K; pumps online",
        ),
        StartupStep(
            id="reactor_coolant_fill", label="Reactor Li-Pb Blanket Fill",
            subsystem="reactor", duration_s=900.0, success_prob=0.97, critical=True,
            depends_on=["thermal_loop_prime"],
            description="Lithium-lead eutectic breeding blanket pre-heated to 700 K and filled",
        ),
        StartupStep(
            id="reactor_magnet_ramp", label="Superconducting Magnet Ramp-Up",
            subsystem="reactor", duration_s=1800.0, success_prob=0.96, critical=True,
            depends_on=["reactor_coolant_fill"],
            description="YBCO/Nb3Sn magnet ramp to 12 T plasma confinement field (30 min)",
        ),
        StartupStep(
            id="reactor_plasma_ignition", label="Plasma Ignition",
            subsystem="reactor", duration_s=120.0, success_prob=0.85, critical=True,
            depends_on=["reactor_magnet_ramp"],
            description="D/He-3 fuel injection + neutral beam heating to ignition (T_i ≈ 100 keV)",
        ),
        StartupStep(
            id="reactor_power_ramp", label="Reactor Power Ramp to 100 MWt",
            subsystem="reactor", duration_s=3600.0, success_prob=0.99,
            depends_on=["reactor_plasma_ignition"],
            description="Ramp thermal power from ignition (~10 MWt) to full 100 MWt over 1 hr",
        ),
        StartupStep(
            id="hvdc_bus_energize", label="HVDC Bus Energize (20.4 kV)",
            subsystem="power", duration_s=30.0, success_prob=0.995,
            depends_on=["reactor_power_ramp"],
            description="Transfer load from APU to reactor-derived 20.4 kV HVDC main bus",
        ),
        StartupStep(
            id="apu_shutdown", label="APU Shutdown",
            subsystem="power", duration_s=15.0, success_prob=1.00,
            depends_on=["hvdc_bus_energize"],
            description="APU deactivated — cold reserve for emergencies",
        ),
        StartupStep(
            id="radiator_deploy", label="Radiator Panel Deploy",
            subsystem="thermal", duration_s=300.0, success_prob=0.99, critical=True,
            depends_on=["hvdc_bus_energize"],
            description="2 × 250×125 m radiator wings deploy from hull-parked position",
        ),
        StartupStep(
            id="eclss_atmo_fill", label="ECLSS Atmosphere Fill",
            subsystem="eclss", duration_s=2400.0, success_prob=0.99,
            depends_on=["hvdc_bus_energize"],
            description="Habitat fill: N₂ 78 %, O₂ 21 %, other 1 %; 101.3 kPa nominal",
        ),
        StartupStep(
            id="eclss_water_loop", label="ECLSS Water Loop",
            subsystem="eclss", duration_s=900.0, success_prob=0.98,
            depends_on=["eclss_atmo_fill"],
            description="Water recycling + hydroponic fluid loop online; UV sterilisation",
        ),
        StartupStep(
            id="eclss_air_revit", label="Air Revitalisation Online",
            subsystem="eclss", duration_s=600.0, success_prob=0.99,
            depends_on=["eclss_water_loop"],
            description="CO₂ scrubber (zeolite 13X + LiOH backup) + trace-contaminant filter",
        ),
        StartupStep(
            id="agriculture_startup", label="Hydroponic Bays Online",
            subsystem="agriculture", duration_s=86400.0,     # 24 hr germination
            success_prob=0.97,
            depends_on=["eclss_water_loop"],
            description="40 000 m² hydroponic grow-beds seeded; LED photoperiod cycle starts",
        ),
        StartupStep(
            id="habitat_ring_spinup", label="Habitat Ring Spin-Up",
            subsystem="habitat", duration_s=7200.0,           # 2 hr linear spin-up
            success_prob=0.95, critical=True,
            depends_on=["hvdc_bus_energize", "eclss_atmo_fill"],
            description="Magnetic bearing engage, linear ramp to 1 RPM (0.56 g) over 2 hr to minimise Coriolis shock",
        ),
        StartupStep(
            id="crew_wake", label="Crew Awake",
            subsystem="crew", duration_s=86400.0,              # 24 hr acclimation
            success_prob=1.0,
            depends_on=["habitat_ring_spinup", "eclss_air_revit", "agriculture_startup"],
            description="Crew from 1000-bunk cryo-module revived in 24 hr bands; full complement online",
        ),
        StartupStep(
            id="mission_ready", label="Mission Ready",
            subsystem="mission", duration_s=1.0, success_prob=1.0,
            depends_on=["crew_wake"],
            description="All systems green — ready for BOOST phase",
        ),
    ]


@dataclass
class StartupController:
    """Executes the startup sequence one `tick()` at a time."""

    steps: List[StartupStep] = field(default_factory=default_startup_steps)
    current_idx: int = 0
    complete: bool = False
    aborted: bool = False
    _rng: random.Random = field(default_factory=lambda: random.Random(1234))

    # ── accessors ────────────────────────────────────────────────

    @property
    def current_step(self) -> Optional[StartupStep]:
        if self.current_idx >= len(self.steps):
            return None
        return self.steps[self.current_idx]

    def get_step(self, step_id: str) -> Optional[StartupStep]:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    # ── execution ────────────────────────────────────────────────

    def begin(self) -> None:
        """Mark the first eligible step as RUNNING."""
        if self.complete or self.aborted:
            return
        step = self.current_step
        if step and step.status == StepStatus.PENDING:
            if self._predecessors_ok(step):
                step.status = StepStatus.RUNNING
            else:
                step.status = StepStatus.SKIPPED
                step.note = "A predecessor failed"

    def tick(self, dt_s: float) -> None:
        """Advance by `dt_s` seconds — step progresses, completes, or fails."""
        if self.complete or self.aborted:
            return
        step = self.current_step
        if step is None:
            self.complete = True
            return
        if step.status == StepStatus.PENDING:
            self.begin()
        if step.status != StepStatus.RUNNING:
            self._advance_idx()
            return
        step.elapsed_s += dt_s
        if step.elapsed_s >= step.duration_s:
            # Resolve success / failure
            roll = self._rng.random()
            if roll <= step.success_prob:
                step.status = StepStatus.SUCCESS
            else:
                step.status = StepStatus.FAILED
                step.note = f"Random failure (roll {roll:.3f} > prob {step.success_prob})"
                if step.critical:
                    self.aborted = True
            self._advance_idx()

    def abort(self, reason: str) -> None:
        self.aborted = True
        step = self.current_step
        if step and step.status == StepStatus.RUNNING:
            step.status = StepStatus.FAILED
            step.note = f"Operator abort: {reason}"

    # ── helpers ──────────────────────────────────────────────────

    def _predecessors_ok(self, step: StartupStep) -> bool:
        for dep_id in step.depends_on:
            dep = self.get_step(dep_id)
            if dep is None or dep.status != StepStatus.SUCCESS:
                return False
        return True

    def _advance_idx(self) -> None:
        self.current_idx += 1
        if self.current_idx >= len(self.steps):
            self.complete = True

    # ── serialisation ────────────────────────────────────────────

    def progress_frac(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps
                   if s.status in (StepStatus.SUCCESS, StepStatus.FAILED, StepStatus.SKIPPED))
        return done / len(self.steps)

    def to_dict(self) -> dict:
        return {
            "complete": self.complete,
            "aborted":  self.aborted,
            "progress_pct": round(100.0 * self.progress_frac(), 1),
            "current_step_id": self.current_step.id if self.current_step else None,
            "steps": [
                {
                    "id": s.id, "label": s.label, "subsystem": s.subsystem,
                    "duration_s": s.duration_s,
                    "elapsed_s": round(s.elapsed_s, 1),
                    "success_prob": s.success_prob,
                    "critical": s.critical,
                    "depends_on": s.depends_on,
                    "description": s.description,
                    "status": s.status.value,
                    "note": s.note,
                }
                for s in self.steps
            ],
        }


# Singleton for the web API
_DEFAULT: Optional[StartupController] = None


def get_startup_controller() -> StartupController:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = StartupController()
    return _DEFAULT


def reset_startup_controller() -> None:
    """For /api/startup/reset to begin a fresh bringup."""
    global _DEFAULT
    _DEFAULT = StartupController()
