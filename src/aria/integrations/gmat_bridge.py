"""GMAT (General Mission Analysis Tool) Bridge for ARIA NavigationAgent.

Integrates NASA's GMAT high-fidelity trajectory tool with ARIA's navigation
and maneuver planning subsystems.  GMAT is a C++ mission analysis tool that
uses its own scripting language (.script files) and can produce:
  - ReportFile: tabular ASCII ephemeris / orbital-element data
  - EphemerisFile: CCSDS-OEM compliant orbit ephemeris messages
  - DifferentialCorrector reports: targeter convergence data

This bridge:
  1. Generates GMAT .script files for LEO, GEO, lunar, and Mars scenarios.
  2. Parses GMAT ReportFile and CCSDS-OEM output into Python data structures.
  3. Converts GMAT trajectories into the ARIA NavigationAgent wire format.
  4. Loads pre-computed GMAT trajectories from files.
  5. Creates GMAT scripts from ARIA mission parameters (trajectory planner).
  6. Works without GMAT installed — all parsing is pure-Python.

GMAT batch execution (when GMAT is installed):
  GmatConsole --run <script.script>
  GmatConsole -r   <script.script>
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import math
import os
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Iterator, Sequence

import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Physical constants (matching GMAT defaults)
# ---------------------------------------------------------------------------
MU_EARTH_KM3S2 = 398600.4418  # km^3/s^2
MU_MOON_KM3S2 = 4902.8000     # km^3/s^2
MU_SUN_KM3S2 = 1.32712440018e11
MU_MARS_KM3S2 = 42828.3719    # km^3/s^2
R_EARTH_KM = 6378.1363         # GMAT default equatorial radius
R_MOON_KM = 1738.2
R_MARS_KM = 3396.19
GEO_RADIUS_KM = 42164.0
SECONDS_PER_DAY = 86400.0

# GMAT epoch reference: 01 Jan 2000 12:00:00.000 TDB = TAIModJulian 21545
GMAT_TAI_MJD_J2000 = 21545.0


# ---------------------------------------------------------------------------
# Enums & dataclasses
# ---------------------------------------------------------------------------

class OrbitType(Enum):
    """Mission orbit regime."""
    LEO = auto()
    GEO = auto()
    LUNAR_TRANSFER = auto()
    MARS_TRANSFER = auto()
    CUSTOM = auto()


class PropagatorType(Enum):
    """GMAT integrator selection."""
    RUNGE_KUTTA_89 = "RungeKutta89"
    RUNGE_KUTTA_68 = "RungeKutta68"
    PRINCE_DORMAND_45 = "PrinceDormand45"
    PRINCE_DORMAND_78 = "PrinceDormand78"
    ADAMS_BASHFORTH_MOULTON = "AdamsBashforthMoulton"


class CoordinateFrame(Enum):
    """GMAT coordinate system names."""
    EARTH_MJ2000_EQ = "EarthMJ2000Eq"
    EARTH_FIXED = "EarthFixed"
    MOON_INERTIAL = "MoonInertial"
    MARS_MJ2000_EQ = "MarsMJ2000Eq"
    SUN_ECLIPTIC = "SunEcliptic"


@dataclass
class KeplerianState:
    """Classical orbital elements (GMAT conventions, km / deg)."""
    sma: float          # Semi-major axis [km]
    ecc: float          # Eccentricity
    inc: float          # Inclination [deg]
    raan: float         # Right Ascension of Ascending Node [deg]
    aop: float          # Argument of Perigee [deg]
    ta: float           # True Anomaly [deg]

    def to_dict(self) -> dict[str, float]:
        return {
            "sma_km": self.sma, "ecc": self.ecc, "inc_deg": self.inc,
            "raan_deg": self.raan, "aop_deg": self.aop, "ta_deg": self.ta,
        }


@dataclass
class CartesianState:
    """Cartesian position/velocity (km, km/s)."""
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float

    @property
    def position_km(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @property
    def velocity_kms(self) -> tuple[float, float, float]:
        return (self.vx, self.vy, self.vz)

    @property
    def radius_km(self) -> float:
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    @property
    def speed_kms(self) -> float:
        return math.sqrt(self.vx ** 2 + self.vy ** 2 + self.vz ** 2)

    def to_dict(self) -> dict[str, float]:
        return {
            "x_km": self.x, "y_km": self.y, "z_km": self.z,
            "vx_kms": self.vx, "vy_kms": self.vy, "vz_kms": self.vz,
        }


@dataclass
class ImpulsiveBurn:
    """A single impulsive maneuver in VNB (velocity-normal-binormal) frame."""
    name: str
    delta_v_vnb_kms: tuple[float, float, float]  # (V, N, B) components km/s
    epoch: str = ""          # UTCGregorian or TAIModJulian string
    origin: str = "Earth"
    isp_s: float = 300.0
    decrement_mass: bool = False

    @property
    def total_delta_v_kms(self) -> float:
        return math.sqrt(sum(c ** 2 for c in self.delta_v_vnb_kms))


@dataclass
class EphemerisPoint:
    """Single ephemeris record (time + state)."""
    epoch: str                    # ISO-8601 or UTCGregorian string
    epoch_mjd: float | None = None
    cartesian: CartesianState | None = None
    keplerian: KeplerianState | None = None
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"epoch": self.epoch, "elapsed_s": self.elapsed_seconds}
        if self.epoch_mjd is not None:
            d["epoch_mjd"] = self.epoch_mjd
        if self.cartesian:
            d["cartesian"] = self.cartesian.to_dict()
        if self.keplerian:
            d["keplerian"] = self.keplerian.to_dict()
        return d


@dataclass
class ManeuverPlan:
    """Collection of burns constituting a maneuver plan."""
    name: str
    burns: list[ImpulsiveBurn] = field(default_factory=list)
    total_delta_v_kms: float = 0.0
    notes: str = ""

    def recompute_total_dv(self) -> None:
        self.total_delta_v_kms = sum(b.total_delta_v_kms for b in self.burns)


@dataclass
class GmatTrajectory:
    """Full trajectory result from a GMAT run or parsed output."""
    mission_name: str
    orbit_type: OrbitType
    coordinate_frame: str = CoordinateFrame.EARTH_MJ2000_EQ.value
    epoch_start: str = ""
    epoch_end: str = ""
    ephemeris: list[EphemerisPoint] = field(default_factory=list)
    maneuver_plan: ManeuverPlan | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if not self.ephemeris:
            return 0.0
        return self.ephemeris[-1].elapsed_seconds - self.ephemeris[0].elapsed_seconds

    def to_aria_nav_format(self) -> dict[str, Any]:
        """Convert to ARIA NavigationAgent wire format."""
        points = [p.to_dict() for p in self.ephemeris]
        result: dict[str, Any] = {
            "source": "gmat",
            "mission_name": self.mission_name,
            "orbit_type": self.orbit_type.name,
            "coordinate_frame": self.coordinate_frame,
            "epoch_start": self.epoch_start,
            "epoch_end": self.epoch_end,
            "duration_s": self.duration_seconds,
            "num_points": len(points),
            "ephemeris": points,
            "metadata": self.metadata,
        }
        if self.maneuver_plan:
            result["maneuver_plan"] = {
                "name": self.maneuver_plan.name,
                "total_delta_v_kms": self.maneuver_plan.total_delta_v_kms,
                "burns": [
                    {
                        "name": b.name,
                        "delta_v_vnb_kms": list(b.delta_v_vnb_kms),
                        "total_delta_v_kms": b.total_delta_v_kms,
                        "epoch": b.epoch,
                        "origin": b.origin,
                        "isp_s": b.isp_s,
                    }
                    for b in self.maneuver_plan.burns
                ],
            }
        return result


@dataclass
class SpacecraftConfig:
    """Spacecraft parameters for GMAT script generation."""
    name: str = "AriaSC"
    dry_mass_kg: float = 850.0
    cd: float = 2.2          # Drag coefficient
    cr: float = 1.8          # Reflectivity coefficient
    drag_area_m2: float = 15.0
    srp_area_m2: float = 1.0


@dataclass
class MissionConfig:
    """Full mission configuration for the trajectory planner."""
    name: str = "ARIA_Mission"
    orbit_type: OrbitType = OrbitType.LEO
    spacecraft: SpacecraftConfig = field(default_factory=SpacecraftConfig)
    # Initial orbit (Keplerian)
    initial_state: KeplerianState | None = None
    # Cartesian alternative
    initial_cartesian: CartesianState | None = None
    # Target parameters
    target_altitude_km: float | None = None
    target_sma_km: float | None = None
    target_ecc: float | None = None
    target_inc_deg: float | None = None
    # Epoch
    epoch_format: str = "UTCGregorian"
    epoch: str = "01 Jan 2025 12:00:00.000"
    # Propagation
    propagator: PropagatorType = PropagatorType.RUNGE_KUTTA_89
    propagation_duration_days: float = 1.0
    coordinate_frame: CoordinateFrame = CoordinateFrame.EARTH_MJ2000_EQ
    # Force model
    include_drag: bool = False
    include_srp: bool = False
    include_third_body: bool = True  # Sun, Moon point masses
    gravity_degree: int = 0          # 0 = point mass, >0 = harmonic
    gravity_order: int = 0
    # Output
    output_dir: str = "/tmp/gmat_aria"  # nosec B108 (test/dev fixture path; not a security boundary)
    report_step_size_s: float = 60.0


# ---------------------------------------------------------------------------
# GMAT Script Generator
# ---------------------------------------------------------------------------

class GmatScriptGenerator:
    """Generates GMAT .script files for various orbit scenarios.

    Each generator method returns the script text and the expected output
    filenames so the parser knows what to look for.
    """

    def __init__(self, config: MissionConfig) -> None:
        self.cfg = config
        self._report_filename = f"{config.name}_Report.txt"
        self._ephem_filename = f"{config.name}_Ephem.oem"

    @property
    def report_filename(self) -> str:
        return self._report_filename

    @property
    def ephem_filename(self) -> str:
        return self._ephem_filename

    # -- public API ----------------------------------------------------------

    def generate(self) -> str:
        """Generate a complete GMAT script for the configured mission."""
        dispatch = {
            OrbitType.LEO: self._generate_leo,
            OrbitType.GEO: self._generate_geo_transfer,
            OrbitType.LUNAR_TRANSFER: self._generate_lunar_transfer,
            OrbitType.MARS_TRANSFER: self._generate_mars_transfer,
            OrbitType.CUSTOM: self._generate_custom,
        }
        generator = dispatch.get(self.cfg.orbit_type, self._generate_custom)
        return generator()

    def write(self, directory: str | Path | None = None) -> Path:
        """Write generated script to disk and return the file path."""
        directory = Path(directory or self.cfg.output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        script_path = directory / f"{self.cfg.name}.script"
        script_path.write_text(self.generate(), encoding="utf-8")
        logger.info("gmat_bridge.script_written", path=str(script_path))
        return script_path

    # -- LEO -----------------------------------------------------------------

    def _generate_leo(self) -> str:
        state = self.cfg.initial_state or KeplerianState(
            sma=R_EARTH_KM + 400.0, ecc=0.001, inc=51.6,
            raan=0.0, aop=0.0, ta=0.0,
        )
        sc = self.cfg.spacecraft
        parts = [
            self._header("LEO Propagation"),
            self._spacecraft_keplerian(sc.name, state),
            self._force_model_earth("LEOProp_FM", include_drag=self.cfg.include_drag,
                                    include_srp=self.cfg.include_srp,
                                    include_third_body=self.cfg.include_third_body,
                                    gravity_degree=self.cfg.gravity_degree,
                                    gravity_order=self.cfg.gravity_order),
            self._propagator("LEOProp", "LEOProp_FM"),
            self._report_file(sc.name),
            self._ephem_file(sc.name),
            self._mission_sequence_propagate(sc.name, "LEOProp",
                                             self.cfg.propagation_duration_days),
        ]
        return "\n".join(parts)

    # -- GEO transfer (Hohmann) ----------------------------------------------

    def _generate_geo_transfer(self) -> str:
        state = self.cfg.initial_state or KeplerianState(
            sma=R_EARTH_KM + 200.0, ecc=0.001, inc=0.0,
            raan=0.0, aop=0.0, ta=0.0,
        )
        sc = self.cfg.spacecraft
        parts = [
            self._header("GEO Transfer (Hohmann)"),
            self._spacecraft_keplerian(sc.name, state),
            self._force_model_earth("GEOProp_FM"),
            self._propagator("GEOProp", "GEOProp_FM"),
            self._impulsive_burn("TOI", origin="Earth"),
            self._impulsive_burn("GOI", origin="Earth"),
            self._differential_corrector("DC"),
            self._report_file(sc.name),
            self._ephem_file(sc.name),
            self._mission_sequence_hohmann(sc.name, "GEOProp", "TOI", "GOI", "DC",
                                           target_rmag_km=GEO_RADIUS_KM),
        ]
        return "\n".join(parts)

    # -- Lunar transfer -------------------------------------------------------

    def _generate_lunar_transfer(self) -> str:
        state = self.cfg.initial_state or KeplerianState(
            sma=R_EARTH_KM + 185.0, ecc=0.001, inc=28.5,
            raan=0.0, aop=0.0, ta=0.0,
        )
        sc = self.cfg.spacecraft
        parts = [
            self._header("Lunar Transfer"),
            self._spacecraft_keplerian(sc.name, state),
            self._force_model_earth("NearEarthProp_FM", include_third_body=True),
            self._force_model_moon("NearMoonProp_FM"),
            self._propagator("NearEarthProp", "NearEarthProp_FM",
                             max_step=160000),
            self._propagator("NearMoonProp", "NearMoonProp_FM",
                             initial_step=60, max_step=86400),
            self._impulsive_burn("TLI", origin="Earth"),
            self._impulsive_burn("LOI", origin="Luna",
                                 initial_dv=(-0.5, 0.0, 0.0)),
            self._coordinate_system_moon_inertial(),
            self._differential_corrector("DC1", max_iterations=150),
            self._report_file(sc.name),
            self._ephem_file(sc.name),
            self._mission_sequence_lunar(sc.name, "NearEarthProp", "NearMoonProp",
                                         "TLI", "LOI", "DC1"),
        ]
        return "\n".join(parts)

    # -- Mars transfer --------------------------------------------------------

    def _generate_mars_transfer(self) -> str:
        state = self.cfg.initial_state or KeplerianState(
            sma=R_EARTH_KM + 200.0, ecc=0.001, inc=28.5,
            raan=0.0, aop=0.0, ta=0.0,
        )
        sc = self.cfg.spacecraft
        parts = [
            self._header("Mars Transfer"),
            self._spacecraft_keplerian(sc.name, state),
            self._force_model_earth("EarthProp_FM", include_third_body=True),
            self._force_model_heliocentric("SunProp_FM"),
            self._force_model_mars("MarsProp_FM"),
            self._propagator("EarthProp", "EarthProp_FM"),
            self._propagator("SunProp", "SunProp_FM", max_step=86400),
            self._propagator("MarsProp", "MarsProp_FM"),
            self._impulsive_burn("TMI", origin="Earth"),
            self._impulsive_burn("MOI", origin="Mars",
                                 initial_dv=(-2.0, 0.0, 0.0)),
            self._coordinate_system_mars(),
            self._differential_corrector("DC1", max_iterations=200),
            self._report_file(sc.name),
            self._ephem_file(sc.name),
            self._mission_sequence_mars(sc.name, "EarthProp", "SunProp",
                                        "MarsProp", "TMI", "MOI", "DC1"),
        ]
        return "\n".join(parts)

    # -- Custom ---------------------------------------------------------------

    def _generate_custom(self) -> str:
        """Generate a basic propagation with whatever state is configured."""
        sc = self.cfg.spacecraft
        if self.cfg.initial_cartesian:
            state_block = self._spacecraft_cartesian(
                sc.name, self.cfg.initial_cartesian,
            )
        elif self.cfg.initial_state:
            state_block = self._spacecraft_keplerian(sc.name, self.cfg.initial_state)
        else:
            state_block = self._spacecraft_keplerian(
                sc.name,
                KeplerianState(sma=R_EARTH_KM + 400.0, ecc=0.001,
                               inc=51.6, raan=0.0, aop=0.0, ta=0.0),
            )
        parts = [
            self._header("Custom Mission"),
            state_block,
            self._force_model_earth("Prop_FM",
                                    include_drag=self.cfg.include_drag,
                                    include_srp=self.cfg.include_srp,
                                    include_third_body=self.cfg.include_third_body),
            self._propagator("Prop", "Prop_FM"),
            self._report_file(sc.name),
            self._ephem_file(sc.name),
            self._mission_sequence_propagate(sc.name, "Prop",
                                             self.cfg.propagation_duration_days),
        ]
        return "\n".join(parts)

    # ========================================================================
    # Building blocks — each returns a GMAT script fragment
    # ========================================================================

    @staticmethod
    def _header(title: str) -> str:
        return textwrap.dedent(f"""\
            %  GMAT Script — {title}
            %  Auto-generated by ARIA GMAT Bridge
            %  Generated: {_dt.datetime.now(_dt.timezone.utc).isoformat()}
            """)

    def _spacecraft_keplerian(self, name: str, state: KeplerianState) -> str:
        import re
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
            raise ValueError(f"Invalid GMAT spacecraft name: {name!r} (must be alphanumeric)")
        sc = self.cfg.spacecraft
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Spacecraft
            %----------------------------------------
            Create Spacecraft {name};
            GMAT {name}.DateFormat = {self.cfg.epoch_format};
            GMAT {name}.Epoch = '{self.cfg.epoch}';
            GMAT {name}.CoordinateSystem = {self.cfg.coordinate_frame.value};
            GMAT {name}.DisplayStateType = Keplerian;
            GMAT {name}.SMA = {state.sma};
            GMAT {name}.ECC = {state.ecc};
            GMAT {name}.INC = {state.inc};
            GMAT {name}.RAAN = {state.raan};
            GMAT {name}.AOP = {state.aop};
            GMAT {name}.TA = {state.ta};
            GMAT {name}.DryMass = {sc.dry_mass_kg};
            GMAT {name}.Cd = {sc.cd};
            GMAT {name}.Cr = {sc.cr};
            GMAT {name}.DragArea = {sc.drag_area_m2};
            GMAT {name}.SRPArea = {sc.srp_area_m2};
            GMAT {name}.Attitude = CoordinateSystemFixed;
            """)

    def _spacecraft_cartesian(self, name: str, state: CartesianState) -> str:
        sc = self.cfg.spacecraft
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Spacecraft
            %----------------------------------------
            Create Spacecraft {name};
            GMAT {name}.DateFormat = {self.cfg.epoch_format};
            GMAT {name}.Epoch = '{self.cfg.epoch}';
            GMAT {name}.CoordinateSystem = {self.cfg.coordinate_frame.value};
            GMAT {name}.DisplayStateType = Cartesian;
            GMAT {name}.X = {state.x};
            GMAT {name}.Y = {state.y};
            GMAT {name}.Z = {state.z};
            GMAT {name}.VX = {state.vx};
            GMAT {name}.VY = {state.vy};
            GMAT {name}.VZ = {state.vz};
            GMAT {name}.DryMass = {sc.dry_mass_kg};
            GMAT {name}.Cd = {sc.cd};
            GMAT {name}.Cr = {sc.cr};
            GMAT {name}.DragArea = {sc.drag_area_m2};
            GMAT {name}.SRPArea = {sc.srp_area_m2};
            GMAT {name}.Attitude = CoordinateSystemFixed;
            """)

    @staticmethod
    def _force_model_earth(
        name: str,
        *,
        include_drag: bool = False,
        include_srp: bool = False,
        include_third_body: bool = False,
        gravity_degree: int = 0,
        gravity_order: int = 0,
    ) -> str:
        lines = [
            "%----------------------------------------",
            "%---------- ForceModels",
            "%----------------------------------------",
            f"Create ForceModel {name};",
            f"GMAT {name}.CentralBody = Earth;",
        ]
        if gravity_degree > 0:
            lines.append(f"GMAT {name}.PrimaryBodies = {{Earth}};")
            lines.append(f"GMAT {name}.GravityField.Earth.Degree = {gravity_degree};")
            lines.append(f"GMAT {name}.GravityField.Earth.Order = {gravity_order};")
            lines.append(f"GMAT {name}.GravityField.Earth.PotentialFile = 'JGM2.cof';")
        else:
            pm = ["Earth"]
            if include_third_body:
                pm.extend(["Sun", "Luna"])
            lines.append(f"GMAT {name}.PointMasses = {{{', '.join(pm)}}};")

        drag_val = "JacchiaRoberts" if include_drag else "None"
        srp_val = "On" if include_srp else "Off"
        lines.append(f"GMAT {name}.Drag = {drag_val};" if not include_drag
                      else f"GMAT {name}.Drag.AtmosphereModel = {drag_val};")
        lines.append(f"GMAT {name}.SRP = {srp_val};")
        lines.append(f"GMAT {name}.RelativisticCorrection = Off;")
        lines.append(f"GMAT {name}.ErrorControl = RSSStep;")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _force_model_moon(name: str) -> str:
        return textwrap.dedent(f"""\
            Create ForceModel {name};
            GMAT {name}.CentralBody = Luna;
            GMAT {name}.PointMasses = {{Sun, Earth, Jupiter, Luna}};
            GMAT {name}.Drag = None;
            GMAT {name}.SRP = On;
            GMAT {name}.RelativisticCorrection = Off;
            GMAT {name}.ErrorControl = RSSStep;
            GMAT {name}.SRP.Flux = 1367;
            GMAT {name}.SRP.Nominal_Sun = 149597870.691;
            """)

    @staticmethod
    def _force_model_heliocentric(name: str) -> str:
        return textwrap.dedent(f"""\
            Create ForceModel {name};
            GMAT {name}.CentralBody = Sun;
            GMAT {name}.PointMasses = {{Sun, Earth, Mars, Jupiter}};
            GMAT {name}.Drag = None;
            GMAT {name}.SRP = On;
            GMAT {name}.RelativisticCorrection = Off;
            GMAT {name}.ErrorControl = RSSStep;
            """)

    @staticmethod
    def _force_model_mars(name: str) -> str:
        return textwrap.dedent(f"""\
            Create ForceModel {name};
            GMAT {name}.CentralBody = Mars;
            GMAT {name}.PointMasses = {{Mars, Sun}};
            GMAT {name}.Drag = None;
            GMAT {name}.SRP = Off;
            GMAT {name}.RelativisticCorrection = Off;
            GMAT {name}.ErrorControl = RSSStep;
            """)

    @staticmethod
    def _propagator(
        name: str,
        force_model: str,
        *,
        integrator: str = "RungeKutta89",
        initial_step: float = 120.0,
        accuracy: float = 1e-12,
        min_step: float = 0.001,
        max_step: float = 2700.0,
    ) -> str:
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Propagators
            %----------------------------------------
            Create Propagator {name};
            GMAT {name}.FM = {force_model};
            GMAT {name}.Type = {integrator};
            GMAT {name}.InitialStepSize = {initial_step};
            GMAT {name}.Accuracy = {accuracy};
            GMAT {name}.MinStep = {min_step};
            GMAT {name}.MaxStep = {max_step};
            GMAT {name}.MaxStepAttempts = 50;
            GMAT {name}.StopIfAccuracyIsViolated = true;
            """)

    @staticmethod
    def _impulsive_burn(
        name: str,
        *,
        origin: str = "Earth",
        initial_dv: tuple[float, float, float] = (0.0001, 0.0, 0.0),
    ) -> str:
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Burns
            %----------------------------------------
            Create ImpulsiveBurn {name};
            GMAT {name}.CoordinateSystem = Local;
            GMAT {name}.Origin = {origin};
            GMAT {name}.Axes = VNB;
            GMAT {name}.Element1 = {initial_dv[0]};
            GMAT {name}.Element2 = {initial_dv[1]};
            GMAT {name}.Element3 = {initial_dv[2]};
            GMAT {name}.DecrementMass = false;
            GMAT {name}.Isp = 300;
            GMAT {name}.GravitationalAccel = 9.81;
            """)

    @staticmethod
    def _differential_corrector(
        name: str,
        *,
        max_iterations: int = 25,
    ) -> str:
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Solvers
            %----------------------------------------
            Create DifferentialCorrector {name};
            GMAT {name}.ShowProgress = true;
            GMAT {name}.ReportStyle = Normal;
            GMAT {name}.ReportFile = '{name}_report.data';
            GMAT {name}.MaximumIterations = {max_iterations};
            GMAT {name}.DerivativeMethod = ForwardDifference;
            """)

    def _report_file(self, sc_name: str) -> str:
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Subscribers
            %----------------------------------------
            Create ReportFile TrajectoryReport;
            GMAT TrajectoryReport.Filename = '{self._report_filename}';
            GMAT TrajectoryReport.Add = {{{sc_name}.UTCGregorian, {sc_name}.ElapsedSecs, {sc_name}.Earth.SMA, {sc_name}.Earth.ECC, {sc_name}.EarthMJ2000Eq.INC, {sc_name}.EarthMJ2000Eq.RAAN, {sc_name}.EarthMJ2000Eq.AOP, {sc_name}.Earth.TA, {sc_name}.EarthMJ2000Eq.X, {sc_name}.EarthMJ2000Eq.Y, {sc_name}.EarthMJ2000Eq.Z, {sc_name}.EarthMJ2000Eq.VX, {sc_name}.EarthMJ2000Eq.VY, {sc_name}.EarthMJ2000Eq.VZ}};
            GMAT TrajectoryReport.WriteHeaders = true;
            """)

    def _ephem_file(self, sc_name: str) -> str:
        return textwrap.dedent(f"""\
            Create EphemerisFile TrajectoryEphem;
            GMAT TrajectoryEphem.Spacecraft = {sc_name};
            GMAT TrajectoryEphem.Filename = '{self._ephem_filename}';
            GMAT TrajectoryEphem.FileFormat = CCSDS-OEM;
            GMAT TrajectoryEphem.EpochFormat = UTCGregorian;
            GMAT TrajectoryEphem.InitialEpoch = InitialSpacecraftEpoch;
            GMAT TrajectoryEphem.FinalEpoch = FinalSpacecraftEpoch;
            GMAT TrajectoryEphem.StepSize = {self.cfg.report_step_size_s};
            """)

    @staticmethod
    def _coordinate_system_moon_inertial() -> str:
        return textwrap.dedent("""\
            %----------------------------------------
            %---------- Coordinate Systems
            %----------------------------------------
            Create CoordinateSystem MoonInertial;
            GMAT MoonInertial.Origin = Luna;
            GMAT MoonInertial.Axes = BodyInertial;
            """)

    @staticmethod
    def _coordinate_system_mars() -> str:
        return textwrap.dedent("""\
            Create CoordinateSystem MarsMJ2000Eq;
            GMAT MarsMJ2000Eq.Origin = Mars;
            GMAT MarsMJ2000Eq.Axes = MJ2000Eq;
            """)

    # -- Mission sequences ----------------------------------------------------

    @staticmethod
    def _mission_sequence_propagate(sc_name: str, prop: str, days: float) -> str:
        secs = days * SECONDS_PER_DAY
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Mission Sequence
            %----------------------------------------
            BeginMissionSequence;
            Propagate '{prop} for {days:.1f} days' {prop}({sc_name}) {{{sc_name}.ElapsedSecs = {secs}}};
            """)

    @staticmethod
    def _mission_sequence_hohmann(
        sc_name: str, prop: str,
        toi: str, goi: str, dc: str,
        target_rmag_km: float,
    ) -> str:
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Mission Sequence
            %----------------------------------------
            BeginMissionSequence;

            Propagate 'Prop to Perigee' {prop}({sc_name}) {{{sc_name}.Periapsis}};

            Target 'Raise and Circularize' {dc} {{SolveMode = Solve, ExitMode = DiscardAndContinue}};
               Vary 'Vary TOI.V' {dc}({toi}.Element1 = 0.5, {{Perturbation = 0.0001, Lower = 0, Upper = 3.14159, MaxStep = 0.2}});
               Maneuver 'Apply TOI' {toi}({sc_name});
               Propagate 'Prop to Apogee' {prop}({sc_name}) {{{sc_name}.Apoapsis}};
               Achieve 'Achieve RMAG' {dc}({sc_name}.Earth.RMAG = {target_rmag_km}, {{Tolerance = 0.1}});
               Vary 'Vary GOI.V' {dc}({goi}.Element1 = 0.5, {{Perturbation = 0.0001, Lower = 0, Upper = 3.14159, MaxStep = 0.2}});
               Maneuver 'Apply GOI' {goi}({sc_name});
               Achieve 'Achieve ECC' {dc}({sc_name}.ECC = 0, {{Tolerance = 0.1}});
            EndTarget;

            Propagate 'Coast 1 Day' {prop}({sc_name}) {{{sc_name}.ElapsedSecs = 86400}};
            """)

    @staticmethod
    def _mission_sequence_lunar(
        sc_name: str,
        earth_prop: str, moon_prop: str,
        tli: str, loi: str, dc: str,
    ) -> str:
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Mission Sequence
            %----------------------------------------
            BeginMissionSequence;

            Target 'Lunar Transfer' {dc} {{SolveMode = Solve, ExitMode = DiscardAndContinue}};
               Vary 'Vary RAAN' {dc}({sc_name}.RAAN = 0, {{Perturbation = 0.00001, MaxStep = 5}});
               Vary 'Vary AOP' {dc}({sc_name}.AOP = 0, {{Perturbation = 0.00001, MaxStep = 5}});
               Vary 'Vary TLI' {dc}({tli}.Element1 = 3.14, {{Perturbation = 0.0000001, MaxStep = 0.01}});
               Maneuver 'Apply TLI' {tli}({sc_name});
               Propagate 'Prop to Moon' {earth_prop}({sc_name}) {{{sc_name}.Luna.Periapsis, {sc_name}.ElapsedDays = 6, {sc_name}.Luna.RMAG = 1000}};
               Achieve 'Achieve RadPer' {dc}({sc_name}.Luna.RMAG = 15000, {{Tolerance = 0.1}});
               Vary 'Vary LOI' {dc}({loi}.Element1 = -0.6, {{Perturbation = 0.00001, MaxStep = 0.3}});
               Maneuver 'Apply LOI' {loi}({sc_name});
               Achieve 'Achieve ECC' {dc}({sc_name}.Luna.ECC = 0.01, {{Tolerance = 0.1}});
            EndTarget;

            Propagate 'Lunar Orbit' {moon_prop}({sc_name}) {{{sc_name}.ElapsedDays = 4}};
            """)

    @staticmethod
    def _mission_sequence_mars(
        sc_name: str,
        earth_prop: str, sun_prop: str, mars_prop: str,
        tmi: str, moi: str, dc: str,
    ) -> str:
        return textwrap.dedent(f"""\
            %----------------------------------------
            %---------- Mission Sequence
            %----------------------------------------
            BeginMissionSequence;

            Target 'Mars Transfer' {dc} {{SolveMode = Solve, ExitMode = DiscardAndContinue}};
               Vary 'Vary TMI' {dc}({tmi}.Element1 = 3.6, {{Perturbation = 0.0001, Lower = 0, Upper = 10, MaxStep = 0.1}});
               Maneuver 'Apply TMI' {tmi}({sc_name});
               Propagate 'Prop to Mars SOI' {sun_prop}({sc_name}) {{{sc_name}.Mars.RMAG = 900000, {sc_name}.ElapsedDays = 400}};
               Achieve 'Achieve Mars RMAG' {dc}({sc_name}.Mars.RMAG = 500000, {{Tolerance = 1000}});
            EndTarget;

            Propagate 'Approach Mars' {mars_prop}({sc_name}) {{{sc_name}.Mars.Periapsis}};
            Maneuver 'Apply MOI' {moi}({sc_name});
            Propagate 'Mars Orbit' {mars_prop}({sc_name}) {{{sc_name}.ElapsedDays = 2}};
            """)


# ---------------------------------------------------------------------------
# GMAT Output Parser
# ---------------------------------------------------------------------------

class GmatOutputParser:
    """Parses GMAT ReportFile and CCSDS-OEM ephemeris output.

    All parsing is pure-Python — no GMAT installation required.
    """

    # -- ReportFile parsing ---------------------------------------------------

    @staticmethod
    def parse_report_file(
        filepath: str | Path,
        *,
        mission_name: str = "GMAT_Trajectory",
        orbit_type: OrbitType = OrbitType.CUSTOM,
    ) -> GmatTrajectory:
        """Parse a GMAT ReportFile (.txt/.data) into a GmatTrajectory.

        Expects a whitespace- or tab-delimited file with an optional header row.
        The standard ARIA-generated report has columns:
          UTCGregorian  ElapsedSecs  SMA  ECC  INC  RAAN  AOP  TA  X  Y  Z  VX  VY  VZ
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"GMAT report file not found: {filepath}")

        text = filepath.read_text(encoding="utf-8")
        return GmatOutputParser.parse_report_text(
            text, mission_name=mission_name, orbit_type=orbit_type,
        )

    @staticmethod
    def parse_report_text(
        text: str,
        *,
        mission_name: str = "GMAT_Trajectory",
        orbit_type: OrbitType = OrbitType.CUSTOM,
    ) -> GmatTrajectory:
        """Parse report text content (header + data rows)."""
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        if not lines:
            raise ValueError("Empty GMAT report file")

        # Detect header row — GMAT headers contain column names with dots
        has_header = False
        header_cols: list[str] = []
        start_idx = 0
        if lines[0] and not _is_numeric_start(lines[0]):
            has_header = True
            header_cols = lines[0].split()
            start_idx = 1

        trajectory = GmatTrajectory(
            mission_name=mission_name,
            orbit_type=orbit_type,
        )

        for line in lines[start_idx:]:
            fields = line.split()
            if len(fields) < 2:
                continue

            point = _parse_report_row(fields, header_cols, has_header)
            if point is not None:
                trajectory.ephemeris.append(point)

        if trajectory.ephemeris:
            trajectory.epoch_start = trajectory.ephemeris[0].epoch
            trajectory.epoch_end = trajectory.ephemeris[-1].epoch

        return trajectory

    # -- CCSDS-OEM parsing ----------------------------------------------------

    @staticmethod
    def parse_oem_file(
        filepath: str | Path,
        *,
        mission_name: str = "GMAT_Trajectory",
        orbit_type: OrbitType = OrbitType.CUSTOM,
    ) -> GmatTrajectory:
        """Parse a CCSDS Orbit Ephemeris Message (.oem) file."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"CCSDS-OEM file not found: {filepath}")

        text = filepath.read_text(encoding="utf-8")
        return GmatOutputParser.parse_oem_text(
            text, mission_name=mission_name, orbit_type=orbit_type,
        )

    @staticmethod
    def parse_oem_text(
        text: str,
        *,
        mission_name: str = "GMAT_Trajectory",
        orbit_type: OrbitType = OrbitType.CUSTOM,
    ) -> GmatTrajectory:
        """Parse CCSDS-OEM text content.

        OEM format (simplified):
            CCSDS_OEM_VERS = 2.0
            ...
            META_START
            OBJECT_NAME = ...
            CENTER_NAME = EARTH
            REF_FRAME = EME2000
            TIME_SYSTEM = UTC
            START_TIME = 2025-01-01T12:00:00.000
            STOP_TIME  = 2025-01-02T12:00:00.000
            META_STOP

            2025-01-01T12:00:00.000  X  Y  Z  VX  VY  VZ
            ...
        """
        trajectory = GmatTrajectory(
            mission_name=mission_name,
            orbit_type=orbit_type,
        )
        metadata: dict[str, str] = {}

        in_meta = False
        in_data = False
        first_epoch_s: float | None = None

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("COMMENT"):
                continue

            if line == "META_START":
                in_meta = True
                continue

            if line == "META_STOP":
                in_meta = False
                in_data = True
                trajectory.coordinate_frame = metadata.get("REF_FRAME", "EME2000")
                trajectory.metadata = dict(metadata)
                continue

            if line in ("COVARIANCE_START", "COVARIANCE_STOP"):
                continue

            # Parse metadata key = value (both before and inside META block)
            if "=" in line and not in_data:
                key, _, val = line.partition("=")
                metadata[key.strip()] = val.strip()
                continue

            # Data line: epoch  x  y  z  vx  vy  vz
            if in_data:
                parts = line.split()
                if len(parts) >= 7:
                    epoch_str = parts[0]
                    try:
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        vx, vy, vz = float(parts[4]), float(parts[5]), float(parts[6])
                    except ValueError:
                        continue

                    elapsed = 0.0
                    epoch_seconds = _oem_epoch_to_seconds(epoch_str)
                    if epoch_seconds is not None:
                        if first_epoch_s is None:
                            first_epoch_s = epoch_seconds
                        elapsed = epoch_seconds - first_epoch_s

                    trajectory.ephemeris.append(EphemerisPoint(
                        epoch=epoch_str,
                        cartesian=CartesianState(x, y, z, vx, vy, vz),
                        elapsed_seconds=elapsed,
                    ))

        if trajectory.ephemeris:
            trajectory.epoch_start = trajectory.ephemeris[0].epoch
            trajectory.epoch_end = trajectory.ephemeris[-1].epoch

        return trajectory

    # -- GMAT script parsing (extract burns from existing scripts) ------------

    @staticmethod
    def parse_script_burns(script_text: str) -> list[ImpulsiveBurn]:
        """Extract ImpulsiveBurn definitions from a GMAT script."""
        burns: list[ImpulsiveBurn] = []
        burn_names: list[str] = []

        # Find all "Create ImpulsiveBurn <name>" lines
        for match in re.finditer(r"Create\s+ImpulsiveBurn\s+(\w+)", script_text):
            burn_names.append(match.group(1))

        for bname in burn_names:
            e1 = _extract_gmat_value(script_text, bname, "Element1", 0.0)
            e2 = _extract_gmat_value(script_text, bname, "Element2", 0.0)
            e3 = _extract_gmat_value(script_text, bname, "Element3", 0.0)
            origin = _extract_gmat_string(script_text, bname, "Origin", "Earth")
            isp = _extract_gmat_value(script_text, bname, "Isp", 300.0)

            burns.append(ImpulsiveBurn(
                name=bname,
                delta_v_vnb_kms=(e1, e2, e3),
                origin=origin,
                isp_s=isp,
            ))

        return burns

    @staticmethod
    def parse_script_spacecraft(script_text: str) -> dict[str, Any]:
        """Extract spacecraft state from a GMAT script."""
        sc_match = re.search(r"Create\s+Spacecraft\s+(\w+)", script_text)
        if not sc_match:
            return {}
        name = sc_match.group(1)
        display = _extract_gmat_string(script_text, name, "DisplayStateType", "Keplerian")
        result: dict[str, Any] = {"name": name, "display_state_type": display}

        if display == "Keplerian":
            result["state"] = KeplerianState(
                sma=_extract_gmat_value(script_text, name, "SMA", 7000.0),
                ecc=_extract_gmat_value(script_text, name, "ECC", 0.001),
                inc=_extract_gmat_value(script_text, name, "INC", 0.0),
                raan=_extract_gmat_value(script_text, name, "RAAN", 0.0),
                aop=_extract_gmat_value(script_text, name, "AOP", 0.0),
                ta=_extract_gmat_value(script_text, name, "TA", 0.0),
            )
        else:
            result["state"] = CartesianState(
                x=_extract_gmat_value(script_text, name, "X", 0.0),
                y=_extract_gmat_value(script_text, name, "Y", 0.0),
                z=_extract_gmat_value(script_text, name, "Z", 0.0),
                vx=_extract_gmat_value(script_text, name, "VX", 0.0),
                vy=_extract_gmat_value(script_text, name, "VY", 0.0),
                vz=_extract_gmat_value(script_text, name, "VZ", 0.0),
            )

        return result


# ---------------------------------------------------------------------------
# GMAT Execution Runner
# ---------------------------------------------------------------------------

class GmatRunner:
    """Execute GMAT scripts in batch/headless mode.

    Works by invoking GmatConsole (the command-line GMAT binary).
    Falls back gracefully if GMAT is not installed.
    """

    def __init__(
        self,
        gmat_path: str | Path | None = None,
        *,
        timeout_s: int = 600,
        verbose: bool = True,
    ) -> None:
        self._gmat_path = self._find_gmat(gmat_path)
        self._timeout_s = timeout_s
        self._verbose = verbose

    @property
    def is_available(self) -> bool:
        """Check if GMAT is installed and accessible."""
        return self._gmat_path is not None

    def run_script(
        self,
        script_path: str | Path,
        *,
        working_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run a GMAT script in headless mode.

        Returns:
            dict with keys: success, returncode, stdout, stderr, output_dir
        """
        if not self.is_available:
            return {
                "success": False,
                "error": "GMAT not installed or not found on PATH",
                "returncode": -1,
                "stdout": "",
                "stderr": "",
            }

        script_path = Path(script_path)
        if not script_path.exists():
            return {
                "success": False,
                "error": f"Script file not found: {script_path}",
                "returncode": -1,
                "stdout": "",
                "stderr": "",
            }

        work_dir = Path(working_dir) if working_dir else script_path.parent
        cmd = [str(self._gmat_path), "--run", str(script_path)]
        if not self._verbose:
            cmd.extend(["--verbose", "off"])

        logger.info("gmat_bridge.running", cmd=" ".join(cmd), cwd=str(work_dir))

        try:
            result = subprocess.run(
                cmd,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
            success = result.returncode == 0
            if not success:
                logger.warning(
                    "gmat_bridge.run_failed",
                    returncode=result.returncode,
                    stderr=result.stderr[:500],
                )
            return {
                "success": success,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "output_dir": str(work_dir),
            }
        except subprocess.TimeoutExpired:
            logger.error("gmat_bridge.timeout", timeout_s=self._timeout_s)
            return {
                "success": False,
                "error": f"GMAT timed out after {self._timeout_s}s",
                "returncode": -1,
                "stdout": "",
                "stderr": "",
            }
        except OSError as exc:
            logger.error("gmat_bridge.exec_error", error=str(exc))
            return {
                "success": False,
                "error": str(exc),
                "returncode": -1,
                "stdout": "",
                "stderr": "",
            }

    @staticmethod
    def _find_gmat(explicit_path: str | Path | None) -> Path | None:
        """Locate the GmatConsole binary."""
        if explicit_path:
            p = Path(explicit_path)
            if p.exists():
                return p

        # Check common locations
        _project_root = Path(__file__).resolve().parents[3]
        candidates = [
            _project_root.parent / "tools" / "gmat" / "application" / "bin" / "GmatConsole",
            Path("/usr/local/bin/GmatConsole"),
            Path("/opt/gmat/bin/GmatConsole"),
        ]
        for c in candidates:
            if c.exists():
                return c

        # Check PATH
        found = shutil.which("GmatConsole")
        if found:
            return Path(found)

        return None


# ---------------------------------------------------------------------------
# GMAT Bridge — Main integration class
# ---------------------------------------------------------------------------

class GmatBridge:
    """Main entry point for ARIA-GMAT integration.

    Usage:
        bridge = GmatBridge()

        # Generate and (optionally) run a GMAT script
        trajectory = bridge.plan_trajectory(MissionConfig(
            orbit_type=OrbitType.LEO,
            propagation_duration_days=1.0,
        ))

        # Parse an existing GMAT output file
        trajectory = bridge.load_report("/path/to/report.txt")

        # Convert to ARIA NavigationAgent format
        nav_data = trajectory.to_aria_nav_format()
    """

    def __init__(
        self,
        gmat_path: str | Path | None = None,
        output_dir: str | Path = "/tmp/gmat_aria",  # nosec B108 (test/dev fixture path; not a security boundary)
    ) -> None:
        self._runner = GmatRunner(gmat_path)
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._parser = GmatOutputParser()

    @property
    def gmat_available(self) -> bool:
        return self._runner.is_available

    # -- High-level API -------------------------------------------------------

    def plan_trajectory(
        self,
        config: MissionConfig,
        *,
        execute: bool = True,
    ) -> GmatTrajectory:
        """Generate a GMAT script and optionally execute it.

        If GMAT is not installed or execute=False, returns a trajectory
        with metadata only (no ephemeris data).  The generated script is
        always written to disk for later use.

        Args:
            config: Mission configuration.
            execute: If True and GMAT is available, run the script.

        Returns:
            GmatTrajectory with ephemeris data (if executed) or metadata only.
        """
        config.output_dir = str(self._output_dir)
        generator = GmatScriptGenerator(config)
        script_path = generator.write(self._output_dir)

        trajectory = GmatTrajectory(
            mission_name=config.name,
            orbit_type=config.orbit_type,
            coordinate_frame=config.coordinate_frame.value,
            epoch_start=config.epoch,
            metadata={
                "script_path": str(script_path),
                "orbit_type": config.orbit_type.name,
                "generated": True,
                "executed": False,
            },
        )

        if execute and self._runner.is_available:
            result = self._runner.run_script(script_path, working_dir=self._output_dir)
            trajectory.metadata["executed"] = result["success"]
            trajectory.metadata["gmat_stdout"] = result.get("stdout", "")[:2000]

            if result["success"]:
                # Try to parse the report file
                report_path = self._output_dir / generator.report_filename
                if report_path.exists():
                    parsed = self._parser.parse_report_file(
                        report_path,
                        mission_name=config.name,
                        orbit_type=config.orbit_type,
                    )
                    trajectory.ephemeris = parsed.ephemeris
                    trajectory.epoch_start = parsed.epoch_start
                    trajectory.epoch_end = parsed.epoch_end

                # Try OEM as fallback / supplement
                oem_path = self._output_dir / generator.ephem_filename
                if oem_path.exists() and not trajectory.ephemeris:
                    parsed = self._parser.parse_oem_file(
                        oem_path,
                        mission_name=config.name,
                        orbit_type=config.orbit_type,
                    )
                    trajectory.ephemeris = parsed.ephemeris
                    trajectory.epoch_start = parsed.epoch_start
                    trajectory.epoch_end = parsed.epoch_end
        elif execute and not self._runner.is_available:
            logger.warning("gmat_bridge.gmat_not_available",
                           msg="Script generated but not executed — GMAT not found")
            trajectory.metadata["warning"] = "GMAT not installed; script saved for offline use"

        return trajectory

    def load_report(
        self,
        filepath: str | Path,
        *,
        mission_name: str = "Loaded_Trajectory",
        orbit_type: OrbitType = OrbitType.CUSTOM,
    ) -> GmatTrajectory:
        """Load a pre-computed GMAT report file."""
        return self._parser.parse_report_file(
            filepath, mission_name=mission_name, orbit_type=orbit_type,
        )

    def load_oem(
        self,
        filepath: str | Path,
        *,
        mission_name: str = "Loaded_Trajectory",
        orbit_type: OrbitType = OrbitType.CUSTOM,
    ) -> GmatTrajectory:
        """Load a pre-computed CCSDS-OEM ephemeris file."""
        return self._parser.parse_oem_file(
            filepath, mission_name=mission_name, orbit_type=orbit_type,
        )

    def load_script(self, filepath: str | Path) -> dict[str, Any]:
        """Parse an existing GMAT .script file for spacecraft state and burns."""
        text = Path(filepath).read_text(encoding="utf-8")
        return {
            "spacecraft": self._parser.parse_script_spacecraft(text),
            "burns": self._parser.parse_script_burns(text),
        }

    def trajectory_to_nav_update(
        self,
        trajectory: GmatTrajectory,
        *,
        index: int = -1,
    ) -> dict[str, Any]:
        """Extract a single navigation state update from a trajectory.

        Useful for feeding the most recent (or any) ephemeris point
        into ARIA's NavigationAgent as a GPS-like update.

        Args:
            trajectory: The GMAT trajectory.
            index: Which ephemeris point to use (-1 = last).

        Returns:
            Dict compatible with ``aria.sensor.nav.gps`` message payload.
        """
        if not trajectory.ephemeris:
            return {"fix": False, "satellites": 0, "source": "gmat"}

        point = trajectory.ephemeris[index]
        result: dict[str, Any] = {
            "fix": True,
            "satellites": 12,  # synthetic — GMAT data is high-fidelity
            "source": "gmat",
            "epoch": point.epoch,
        }

        if point.cartesian:
            r_km = point.cartesian.radius_km
            alt_km = r_km - R_EARTH_KM
            result["altitude_km"] = alt_km
            result["velocity_ms"] = point.cartesian.speed_kms * 1000.0
            result["position_km"] = list(point.cartesian.position_km)
            result["velocity_kms"] = list(point.cartesian.velocity_kms)

        if point.keplerian:
            result["sma_km"] = point.keplerian.sma
            result["ecc"] = point.keplerian.ecc
            result["inc_deg"] = point.keplerian.inc

        return result

    def generate_script_only(self, config: MissionConfig) -> str:
        """Generate a GMAT script string without writing to disk."""
        config.output_dir = str(self._output_dir)
        generator = GmatScriptGenerator(config)
        return generator.generate()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_numeric_start(line: str) -> bool:
    """Check if line starts with a number or date-like epoch."""
    parts = line.split()
    if not parts:
        return False
    first = parts[0]
    # Numeric start
    try:
        float(first)
        return True
    except ValueError:
        pass
    # GMAT UTCGregorian: "01 Jan 2025 ..."
    if re.match(r"\d{1,2}\s+\w{3}\s+\d{4}", line):
        return True
    # ISO-8601
    if re.match(r"\d{4}-\d{2}-\d{2}", first):
        return True
    return False


def _parse_report_row(
    fields: list[str],
    header_cols: list[str],
    has_header: bool,
) -> EphemerisPoint | None:
    """Parse a single report data row.

    GMAT UTCGregorian epochs span multiple whitespace-delimited fields:
      "01 Jan 2025 12:00:00.000"  ->  4 fields before numeric data begins
    """
    # Detect if the row starts with a date (UTCGregorian) or a number
    epoch_str = ""
    numeric_start = 0

    # Try UTCGregorian: DD Mon YYYY HH:MM:SS.sss
    if len(fields) >= 4 and re.match(r"\d{1,2}$", fields[0]):
        # Check if fields[1] looks like a month abbreviation
        if re.match(r"[A-Za-z]{3}$", fields[1]) and re.match(r"\d{4}$", fields[2]):
            epoch_str = f"{fields[0]} {fields[1]} {fields[2]} {fields[3]}"
            numeric_start = 4
        else:
            numeric_start = 0
    elif len(fields) >= 1:
        # Could be TAIModJulian or ISO epoch as first field
        try:
            float(fields[0])
            numeric_start = 0
        except ValueError:
            # Might be ISO date
            epoch_str = fields[0]
            numeric_start = 1

    remaining = fields[numeric_start:]
    if not remaining:
        return None

    try:
        nums = [float(f) for f in remaining]
    except ValueError:
        return None

    # Map to our standard layout:
    #   ElapsedSecs SMA ECC INC RAAN AOP TA X Y Z VX VY VZ
    # (13 numeric fields if full report)
    kep = None
    cart = None
    elapsed = 0.0
    epoch_mjd = None

    if not epoch_str and numeric_start == 0 and len(nums) >= 1:
        # First field might be MJD epoch or elapsed seconds.
        # Only consume it as epoch if remaining fields match a known count.
        remaining_after_pop = len(nums) - 1
        if remaining_after_pop in (13, 7, 6, 12):
            epoch_mjd = nums[0]
            epoch_str = str(nums[0])
            nums = nums[1:]

    if len(nums) >= 13:
        # Full: ElapsedSecs SMA ECC INC RAAN AOP TA X Y Z VX VY VZ
        elapsed = nums[0]
        kep = KeplerianState(sma=nums[1], ecc=nums[2], inc=nums[3],
                             raan=nums[4], aop=nums[5], ta=nums[6])
        cart = CartesianState(x=nums[7], y=nums[8], z=nums[9],
                              vx=nums[10], vy=nums[11], vz=nums[12])
    elif len(nums) >= 7:
        # Possibly: ElapsedSecs X Y Z VX VY VZ (cartesian only)
        elapsed = nums[0]
        cart = CartesianState(x=nums[1], y=nums[2], z=nums[3],
                              vx=nums[4], vy=nums[5], vz=nums[6])
    elif len(nums) >= 6:
        # Bare cartesian: X Y Z VX VY VZ
        cart = CartesianState(x=nums[0], y=nums[1], z=nums[2],
                              vx=nums[3], vy=nums[4], vz=nums[5])

    if cart is None and kep is None:
        return None

    return EphemerisPoint(
        epoch=epoch_str,
        epoch_mjd=epoch_mjd,
        cartesian=cart,
        keplerian=kep,
        elapsed_seconds=elapsed,
    )


def _oem_epoch_to_seconds(epoch_str: str) -> float | None:
    """Convert an ISO-8601 epoch string to seconds since reference."""
    # Format: 2025-01-01T12:00:00.000 or 2025-01-01T12:00:00.000000
    try:
        # Handle fractional seconds properly
        if "." in epoch_str:
            dt = _dt.datetime.strptime(epoch_str[:23], "%Y-%m-%dT%H:%M:%S.%f")
        else:
            dt = _dt.datetime.strptime(epoch_str[:19], "%Y-%m-%dT%H:%M:%S")
        # Seconds since J2000 (2000-01-01 12:00:00)
        j2000 = _dt.datetime(2000, 1, 1, 12, 0, 0)
        return (dt - j2000).total_seconds()
    except (ValueError, IndexError):
        return None


def _extract_gmat_value(
    script: str, obj_name: str, prop: str, default: float,
) -> float:
    """Extract a numeric GMAT property value from script text."""
    pattern = rf"GMAT\s+{re.escape(obj_name)}\.{re.escape(prop)}\s*=\s*([^;]+)"
    match = re.search(pattern, script)
    if match:
        try:
            return float(match.group(1).strip().strip("'\""))
        except ValueError:
            pass
    return default


def _extract_gmat_string(
    script: str, obj_name: str, prop: str, default: str,
) -> str:
    """Extract a string GMAT property value from script text."""
    pattern = rf"GMAT\s+{re.escape(obj_name)}\.{re.escape(prop)}\s*=\s*([^;]+)"
    match = re.search(pattern, script)
    if match:
        return match.group(1).strip().strip("'\"")
    return default
