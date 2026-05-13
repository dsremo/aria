"""Saturn V stage-by-stage performance reference.

The full propulsion + mass + timing dataset for the Saturn V launch
vehicle, drawn entirely from public-domain NASA sources. Used by
``saturn_v_launch.py`` to fly an Apollo 11-class ascent in
simulation, and by ``tests/integration/test_saturn_v_replay.py``
to validate the orbital-mechanics + propulsion stack against the
historical record.

Sources (all public-domain, cited per-constant):

  * NASA SP-4029 (Orloff 2000) — "Apollo by the Numbers: A
    Statistical Reference for the Apollo Mission Set"
  * NASA SP-4206 (Bilstein 1980) — "Stages to Saturn: A
    Technological History of the Apollo / Saturn Launch Vehicles"
  * MSC-04112 (NASA 1969) — Apollo 11 Mission Report
  * NASA-MSFC-1969 — Saturn V Launch Vehicle Press Kit, Apollo 11
  * NTRS 19670028071 — Saturn V flight evaluation report
  * NASA TM-X-881 — Saturn V Flight Manual SA-507
  * Rocketdyne F-1 Engine Manual R-3896-1 (Rocketdyne 1968)
  * Rocketdyne J-2 Engine Manual R-3825-1 (Rocketdyne 1967)

ARIA's Apollo 11 launch simulator should match every field below
within stated tolerance bands. Larger divergences mean the
simulator has drifted from the historical record and needs
attention. (Project CLAUDE.md mandate: every numerical constant
carries a citation.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Engine reference data ───────────────────────────────────────


@dataclass(frozen=True)
class RocketEngine:
    """Performance characteristics of a single rocket engine."""

    name: str
    propellant: str               # "RP-1/LOX", "LH2/LOX", etc.
    thrust_sl_n: Optional[float]  # Sea-level thrust (N), None for vacuum-only engines
    thrust_vac_n: float           # Vacuum thrust (N)
    isp_sl_s: Optional[float]     # Sea-level specific impulse (s)
    isp_vac_s: float              # Vacuum specific impulse (s)
    mass_flow_kg_s: float         # Nominal mass-flow rate (kg/s)
    chamber_pressure_pa: float    # Combustion-chamber pressure (Pa)
    expansion_ratio: float        # Nozzle expansion ratio (dimensionless)
    dry_mass_kg: float            # Engine dry mass (kg)
    citation: str


# F-1 engine — used 5× per S-IC stage.
# Source: Rocketdyne F-1 Engine Manual R-3896-1 (1968) §3.1; cross-
# checked against NASA SP-4206 Bilstein 1980 Appendix C.
F1_ENGINE = RocketEngine(
    name="F-1",
    propellant="RP-1/LOX",
    thrust_sl_n=6_770_000.0,         # 1.522 Mlbf sea level (Rocketdyne R-3896-1 §3.1)
    thrust_vac_n=7_770_000.0,        # 1.748 Mlbf vacuum (Rocketdyne R-3896-1 §3.1)
    isp_sl_s=263.0,                  # s (Rocketdyne R-3896-1 §3.1)
    isp_vac_s=304.0,                 # s (Rocketdyne R-3896-1 §3.1)
    mass_flow_kg_s=2_578.0,          # kg/s (Bilstein 1980 §C-2)
    chamber_pressure_pa=7.0e6,       # 1015 psia (Rocketdyne R-3896-1 §3.1)
    expansion_ratio=16.0,            # (Rocketdyne R-3896-1 §3.1)
    dry_mass_kg=8_400.0,             # kg (Bilstein 1980 §C-2)
    citation="Rocketdyne R-3896-1 (1968) §3.1; Bilstein NASA SP-4206 §C-2",
)

# J-2 engine — used 5× per S-II stage and 1× per S-IVB stage.
# Source: Rocketdyne J-2 Engine Manual R-3825-1 (1967) §2.4.
J2_ENGINE = RocketEngine(
    name="J-2",
    propellant="LH2/LOX",
    thrust_sl_n=None,                # vacuum-start engine; not rated at SL
    thrust_vac_n=1_033_100.0,        # 232,250 lbf (Rocketdyne R-3825-1 §2.4)
    isp_sl_s=None,
    isp_vac_s=421.0,                 # s (Rocketdyne R-3825-1 §2.4)
    mass_flow_kg_s=247.2,            # kg/s (Rocketdyne R-3825-1 §2.4)
    chamber_pressure_pa=5.4e6,       # 783 psia (Rocketdyne R-3825-1 §2.4)
    expansion_ratio=27.5,            # (Rocketdyne R-3825-1 §2.4)
    dry_mass_kg=1_584.0,             # kg (Bilstein 1980 §C-3)
    citation="Rocketdyne R-3825-1 (1967) §2.4; Bilstein NASA SP-4206 §C-3",
)


# ── Stage reference data ────────────────────────────────────────


@dataclass(frozen=True)
class SaturnVStage:
    """Mass + propulsion characteristics of one Saturn V stage."""

    name: str                       # "S-IC", "S-II", "S-IVB"
    engine_count: int
    engine: RocketEngine
    dry_mass_kg: float              # Stage dry mass (kg)
    propellant_mass_kg: float       # Usable propellant mass (kg)
    interstage_mass_kg: float       # Interstage adapter mass (kg, 0 for last)
    nominal_burn_s: float           # Nominal burn duration (s)
    citation: str

    @property
    def gross_mass_kg(self) -> float:
        """Total stage mass at ignition."""
        return self.dry_mass_kg + self.propellant_mass_kg + self.interstage_mass_kg

    @property
    def total_thrust_vac_n(self) -> float:
        return self.engine_count * self.engine.thrust_vac_n

    @property
    def total_thrust_sl_n(self) -> float:
        if self.engine.thrust_sl_n is None:
            return 0.0
        return self.engine_count * self.engine.thrust_sl_n


# S-IC first stage (boost phase, sea level → ~67 km).
# Source: NASA SP-4206 Bilstein 1980 §C-2 (Saturn V detailed
# mass + performance). AS-506 (Apollo 11) values from MSC-04112.
S_IC_STAGE = SaturnVStage(
    name="S-IC",
    engine_count=5,                  # 5× F-1 (Bilstein §6)
    engine=F1_ENGINE,
    dry_mass_kg=131_000.0,           # kg (Bilstein 1980 §C-2; AS-506: 130,422 kg)
    propellant_mass_kg=2_148_000.0,  # kg total (RP-1: 647,000 kg + LOX: 1,501,000 kg per NASA TM-X-881 §2.3)
    interstage_mass_kg=5_500.0,      # kg interstage to S-II (Bilstein §C-2)
    nominal_burn_s=165.0,            # s nominal cutoff (NASA TM-X-881 §3.4; AS-506 actual: 161.7 s)
    citation="Bilstein NASA SP-4206 §C-2; NASA TM-X-881 §2.3; MSC-04112 (Apollo 11)",
)

# S-II second stage (sustainer to LEO insertion altitude).
# Source: Bilstein 1980 §C-3, cross-checked against AS-506.
S_II_STAGE = SaturnVStage(
    name="S-II",
    engine_count=5,                  # 5× J-2 (Bilstein §7)
    engine=J2_ENGINE,
    dry_mass_kg=36_000.0,            # kg (Bilstein 1980 §C-3; AS-506: 35,860 kg)
    propellant_mass_kg=444_000.0,    # kg (LH2: 73,500 kg + LOX: 370,500 kg per NASA TM-X-881 §2.4)
    interstage_mass_kg=8_100.0,      # kg interstage to S-IVB (Bilstein §C-3)
    nominal_burn_s=395.0,            # s (NASA TM-X-881 §3.5; AS-506 actual: 384.0 s)
    citation="Bilstein NASA SP-4206 §C-3; NASA TM-X-881 §2.4",
)

# S-IVB third stage (parking orbit insertion + TLI).
# Source: Bilstein 1980 §C-4. Note: S-IVB carries the J-2 at single-
# engine count and burns TWICE — once for circ-LEO insertion, once
# for trans-lunar injection (TLI).
S_IVB_STAGE = SaturnVStage(
    name="S-IVB",
    engine_count=1,                  # 1× J-2 (Bilstein §8)
    engine=J2_ENGINE,
    dry_mass_kg=13_300.0,            # kg (Bilstein 1980 §C-4; AS-506: 13,156 kg)
    propellant_mass_kg=106_900.0,    # kg total for both burns (LH2: 19,200 kg + LOX: 87,700 kg per NASA TM-X-881 §2.5)
    interstage_mass_kg=0.0,          # last propulsive stage; spacecraft mounts directly
    nominal_burn_s=507.0,            # s combined (insertion ~165 s + TLI ~342 s) (MSC-04112 Apollo 11)
    citation="Bilstein NASA SP-4206 §C-4; NASA TM-X-881 §2.5; MSC-04112",
)


# ── Vehicle-level reference ─────────────────────────────────────


# Apollo 11 (AS-506) liftoff mass.
# Source: MSC-04112 Apollo 11 Mission Report, Table 6-1.
# 2,941,748 kg (6,484,289 lbm) at liftoff per NASA records.
APOLLO_11_LIFTOFF_MASS_KG = 2_941_748.0  # MSC-04112 §6.1

# Spacecraft + Launch Escape Tower at liftoff.
# CSM (Apollo 11): 28,801 kg (Orloff SP-4029 Table 1-2)
# LM (Apollo 11):  15,103 kg (Orloff SP-4029 Table 1-2)
# LET (jettisoned at T+3:18): ~4,041 kg (Bilstein 1980 §C-5)
# Spacecraft adapter: ~1,838 kg (Bilstein 1980 §C-5)
APOLLO_11_SPACECRAFT_MASS_KG = 49_783.0  # SP-4029 + Bilstein, sums to launch payload

# At TLI (S-IVB second burn complete) the stack is CSM + LM only.
# Source: Apollo 11 Mission Report MSC-04112 Table 4-2.
APOLLO_11_TLI_MASS_KG = 46_678.0  # MSC-04112 §4.2 (post-LET-jettison, post-S-IVB-cutoff)


# ── Apollo 11 launch sequence (T-relative event timeline) ───────


@dataclass(frozen=True)
class LaunchEvent:
    """One discrete launch-sequence event with reference time + altitude + velocity."""

    name: str
    t_plus_s: float            # Seconds after liftoff (T+)
    altitude_m: Optional[float]
    inertial_velocity_mps: Optional[float]
    citation: str


# Apollo 11 (AS-506) liftoff: 1969-07-16 13:32:00 UTC.
# Every event below is the published flight-evaluation value, not
# the simulation. Source: Apollo 11 Mission Report MSC-04112
# §3.0–§4.0, cross-referenced with the Saturn V Launch Vehicle
# Flight Evaluation Report MPR-SAT-FE-69-9.
APOLLO_11_LAUNCH_SEQUENCE = (
    LaunchEvent(
        name="liftoff",
        t_plus_s=0.0,
        altitude_m=0.0,
        inertial_velocity_mps=408.0,        # Earth's rotational vel at KSC latitude (Bilstein §6)
        citation="MSC-04112 §3.1",
    ),
    LaunchEvent(
        name="roll_program_start",
        t_plus_s=12.5,
        altitude_m=215.0,
        inertial_velocity_mps=438.0,
        citation="MSC-04112 §3.2",
    ),
    LaunchEvent(
        name="max_q",
        t_plus_s=83.0,
        altitude_m=13_700.0,
        inertial_velocity_mps=575.0,
        citation="MSC-04112 §3.3 (Apollo 11 actual: 13,700 m, max-q ≈ 33.5 kPa)",
    ),
    LaunchEvent(
        name="s_ic_inboard_cutoff",
        t_plus_s=135.5,
        altitude_m=43_500.0,
        inertial_velocity_mps=2_004.0,
        citation="MSC-04112 §3.4 (4 engines remaining)",
    ),
    LaunchEvent(
        name="s_ic_outboard_cutoff",
        t_plus_s=161.7,
        altitude_m=66_500.0,
        inertial_velocity_mps=2_390.0,
        citation="MSC-04112 §3.5; Saturn V Flight Eval MPR-SAT-FE-69-9",
    ),
    LaunchEvent(
        name="s_ic_s_ii_separation",
        t_plus_s=162.4,
        altitude_m=66_900.0,
        inertial_velocity_mps=2_392.0,
        citation="MSC-04112 §3.6",
    ),
    LaunchEvent(
        name="s_ii_ignition",
        t_plus_s=163.5,
        altitude_m=68_200.0,
        inertial_velocity_mps=2_394.0,
        citation="MSC-04112 §3.7",
    ),
    LaunchEvent(
        name="launch_escape_tower_jettison",
        t_plus_s=198.9,
        altitude_m=92_400.0,
        inertial_velocity_mps=2_651.0,
        citation="MSC-04112 §3.8 (LET jettison after atmospheric escape)",
    ),
    LaunchEvent(
        name="s_ii_center_engine_cutoff",
        t_plus_s=460.6,
        altitude_m=174_900.0,
        inertial_velocity_mps=5_960.0,
        citation="MSC-04112 §3.9 (commanded shutdown to ease pogo)",
    ),
    LaunchEvent(
        name="s_ii_outboard_cutoff",
        t_plus_s=549.0,
        altitude_m=185_900.0,
        inertial_velocity_mps=6_840.0,
        citation="MSC-04112 §3.10",
    ),
    LaunchEvent(
        name="s_ii_s_ivb_separation",
        t_plus_s=550.3,
        altitude_m=186_300.0,
        inertial_velocity_mps=6_842.0,
        citation="MSC-04112 §3.11",
    ),
    LaunchEvent(
        name="s_ivb_first_ignition",
        t_plus_s=551.4,
        altitude_m=187_000.0,
        inertial_velocity_mps=6_844.0,
        citation="MSC-04112 §3.12 (parking-orbit insertion burn)",
    ),
    LaunchEvent(
        name="s_ivb_first_cutoff",
        t_plus_s=702.6,
        altitude_m=190_400.0,
        inertial_velocity_mps=7_793.0,
        citation="MSC-04112 §3.13 (Earth parking orbit, 184 × 188 km @ 32.5°)",
    ),
    LaunchEvent(
        name="parking_orbit_coast_start",
        t_plus_s=702.6,
        altitude_m=190_400.0,
        inertial_velocity_mps=7_793.0,
        citation="MSC-04112 §3.14 (~2.5 orbits coast)",
    ),
    LaunchEvent(
        name="s_ivb_second_ignition",
        t_plus_s=9_856.2,                    # 2:44:16 mission elapsed (MSC-04112 §4.1)
        altitude_m=334_500.0,
        inertial_velocity_mps=7_793.0,
        citation="MSC-04112 §4.1 (TLI burn ignition)",
    ),
    LaunchEvent(
        name="s_ivb_second_cutoff",
        t_plus_s=10_203.0,                   # 2:50:03 mission elapsed (MSC-04112 §4.2)
        altitude_m=334_500.0,
        inertial_velocity_mps=10_834.0,      # m/s — TLI velocity
        citation="MSC-04112 §4.2 (TLI complete; Δv ≈ 3,131 m/s vs nominal 3,140)",
    ),
)


# Convenience access ─────────────────────────────────────────────


SATURN_V_STAGES = (S_IC_STAGE, S_II_STAGE, S_IVB_STAGE)


def get_stage(name: str) -> SaturnVStage:
    for stage in SATURN_V_STAGES:
        if stage.name == name:
            return stage
    raise KeyError(f"Saturn V stage {name!r} not in reference set")


def get_launch_event(event_name: str) -> LaunchEvent:
    for event in APOLLO_11_LAUNCH_SEQUENCE:
        if event.name == event_name:
            return event
    raise KeyError(f"Launch event {event_name!r} not in Apollo 11 sequence")


def total_vehicle_mass_at_liftoff_kg() -> float:
    """Sum of all three stages + spacecraft = vehicle gross mass at T-0."""
    return (
        sum(stage.gross_mass_kg for stage in SATURN_V_STAGES)
        + APOLLO_11_SPACECRAFT_MASS_KG
    )


def total_propellant_mass_kg() -> float:
    return sum(stage.propellant_mass_kg for stage in SATURN_V_STAGES)
