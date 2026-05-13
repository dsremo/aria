"""Tests for GMAT Bridge integration.

Tests cover:
  - Script generation for all orbit types (LEO, GEO, Lunar, Mars, Custom)
  - Report file parsing (tab/space delimited, with/without headers)
  - CCSDS-OEM ephemeris parsing
  - GMAT script parsing (spacecraft state, burn extraction)
  - ARIA NavigationAgent format conversion
  - Trajectory loading from files
  - Edge cases: empty files, malformed data, missing GMAT
  - GmatBridge high-level API
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from aria.integrations.gmat_bridge import (
    CartesianState,
    CoordinateFrame,
    EphemerisPoint,
    GmatBridge,
    GmatOutputParser,
    GmatRunner,
    GmatScriptGenerator,
    GmatTrajectory,
    ImpulsiveBurn,
    KeplerianState,
    ManeuverPlan,
    MissionConfig,
    OrbitType,
    PropagatorType,
    R_EARTH_KM,
    GEO_RADIUS_KM,
    SpacecraftConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def leo_config() -> MissionConfig:
    return MissionConfig(
        name="TestLEO",
        orbit_type=OrbitType.LEO,
        propagation_duration_days=0.5,
        epoch="01 Jan 2025 12:00:00.000",
    )


@pytest.fixture
def geo_config() -> MissionConfig:
    return MissionConfig(
        name="TestGEO",
        orbit_type=OrbitType.GEO,
        epoch="01 Jan 2025 12:00:00.000",
    )


@pytest.fixture
def lunar_config() -> MissionConfig:
    return MissionConfig(
        name="TestLunar",
        orbit_type=OrbitType.LUNAR_TRANSFER,
        epoch="15 Jul 2025 01:00:00.000",
    )


@pytest.fixture
def mars_config() -> MissionConfig:
    return MissionConfig(
        name="TestMars",
        orbit_type=OrbitType.MARS_TRANSFER,
        epoch="01 Mar 2026 00:00:00.000",
    )


@pytest.fixture
def sample_report_text() -> str:
    """Simulated GMAT ReportFile output with header and 5 data rows."""
    header = (
        "AriaSC.UTCGregorian  AriaSC.ElapsedSecs  AriaSC.Earth.SMA  "
        "AriaSC.Earth.ECC  AriaSC.EarthMJ2000Eq.INC  AriaSC.EarthMJ2000Eq.RAAN  "
        "AriaSC.EarthMJ2000Eq.AOP  AriaSC.Earth.TA  "
        "AriaSC.EarthMJ2000Eq.X  AriaSC.EarthMJ2000Eq.Y  AriaSC.EarthMJ2000Eq.Z  "
        "AriaSC.EarthMJ2000Eq.VX  AriaSC.EarthMJ2000Eq.VY  AriaSC.EarthMJ2000Eq.VZ"
    )
    rows = [
        "01 Jan 2025 12:00:00.000  0.0  6778.14  0.001  51.6  0.0  0.0  0.0  6778.14  0.0  0.0  0.0  5.418  5.418",
        "01 Jan 2025 12:01:00.000  60.0  6778.14  0.001  51.6  0.0  0.0  5.3  6770.0  325.0  320.0  -0.24  5.41  5.41",
        "01 Jan 2025 12:02:00.000  120.0  6778.14  0.001  51.6  0.0  0.0  10.6  6746.0  649.0  638.0  -0.48  5.39  5.39",
        "01 Jan 2025 12:03:00.000  180.0  6778.14  0.001  51.6  0.0  0.0  15.9  6706.0  972.0  954.0  -0.72  5.36  5.36",
        "01 Jan 2025 12:04:00.000  240.0  6778.14  0.001  51.6  0.0  0.0  21.2  6651.0  1293.0  1267.0  -0.96  5.31  5.31",
    ]
    return header + "\n" + "\n".join(rows)


@pytest.fixture
def sample_oem_text() -> str:
    """Simulated CCSDS-OEM content."""
    return """\
CCSDS_OEM_VERS = 2.0
CREATION_DATE = 2025-01-01
ORIGINATOR = ARIA-GMAT-BRIDGE

META_START
OBJECT_NAME = AriaSC
OBJECT_ID = 2025-001A
CENTER_NAME = EARTH
REF_FRAME = EME2000
TIME_SYSTEM = UTC
START_TIME = 2025-01-01T12:00:00.000
STOP_TIME = 2025-01-01T12:04:00.000
META_STOP

2025-01-01T12:00:00.000  6778.14  0.0  0.0  0.0  5.418  5.418
2025-01-01T12:01:00.000  6770.0  325.0  320.0  -0.24  5.41  5.41
2025-01-01T12:02:00.000  6746.0  649.0  638.0  -0.48  5.39  5.39
2025-01-01T12:03:00.000  6706.0  972.0  954.0  -0.72  5.36  5.36
2025-01-01T12:04:00.000  6651.0  1293.0  1267.0  -0.96  5.31  5.31
"""


@pytest.fixture
def sample_gmat_script() -> str:
    """A fragment of a real GMAT script for parsing tests."""
    return """\
Create Spacecraft MoonSat;
GMAT MoonSat.DateFormat = UTCGregorian;
GMAT MoonSat.Epoch = '15 Jul 2022 01:07:06.978';
GMAT MoonSat.CoordinateSystem = EarthMJ2000Eq;
GMAT MoonSat.DisplayStateType = Keplerian;
GMAT MoonSat.SMA = 6563.000000000004;
GMAT MoonSat.ECC = 0.0010000000000005;
GMAT MoonSat.INC = 28.7;
GMAT MoonSat.RAAN = 263;
GMAT MoonSat.AOP = 360;
GMAT MoonSat.TA = 8.537736462515939e-007;
GMAT MoonSat.DryMass = 850;

Create ImpulsiveBurn TOI;
GMAT TOI.CoordinateSystem = Local;
GMAT TOI.Origin = Earth;
GMAT TOI.Axes = VNB;
GMAT TOI.Element1 = 3.14;
GMAT TOI.Element2 = 0;
GMAT TOI.Element3 = 0;
GMAT TOI.Isp = 300;

Create ImpulsiveBurn LOI;
GMAT LOI.CoordinateSystem = Local;
GMAT LOI.Origin = Luna;
GMAT LOI.Axes = VNB;
GMAT LOI.Element1 = -0.5;
GMAT LOI.Element2 = 0;
GMAT LOI.Element3 = 0;
GMAT LOI.Isp = 300;
"""


# ---------------------------------------------------------------------------
# Dataclass unit tests
# ---------------------------------------------------------------------------

class TestKeplerianState:
    def test_to_dict(self):
        state = KeplerianState(sma=7000, ecc=0.001, inc=51.6, raan=0, aop=0, ta=0)
        d = state.to_dict()
        assert d["sma_km"] == 7000
        assert d["ecc"] == 0.001
        assert d["inc_deg"] == 51.6

    def test_all_fields(self):
        state = KeplerianState(sma=42164, ecc=0.0, inc=0.0, raan=0, aop=0, ta=180)
        assert state.sma == 42164
        assert state.ta == 180


class TestCartesianState:
    def test_radius(self):
        state = CartesianState(x=6778, y=0, z=0, vx=0, vy=7.67, vz=0)
        assert abs(state.radius_km - 6778.0) < 0.01

    def test_speed(self):
        state = CartesianState(x=6778, y=0, z=0, vx=0, vy=7.67, vz=0)
        assert abs(state.speed_kms - 7.67) < 0.01

    def test_to_dict(self):
        state = CartesianState(x=1, y=2, z=3, vx=4, vy=5, vz=6)
        d = state.to_dict()
        assert d["x_km"] == 1
        assert d["vz_kms"] == 6

    def test_position_velocity_tuples(self):
        state = CartesianState(x=1, y=2, z=3, vx=4, vy=5, vz=6)
        assert state.position_km == (1, 2, 3)
        assert state.velocity_kms == (4, 5, 6)


class TestImpulsiveBurn:
    def test_total_delta_v(self):
        burn = ImpulsiveBurn(name="TOI", delta_v_vnb_kms=(3.0, 4.0, 0.0))
        assert abs(burn.total_delta_v_kms - 5.0) < 1e-10

    def test_zero_burn(self):
        burn = ImpulsiveBurn(name="Zero", delta_v_vnb_kms=(0, 0, 0))
        assert burn.total_delta_v_kms == 0.0


class TestManeuverPlan:
    def test_recompute_total_dv(self):
        plan = ManeuverPlan(
            name="Hohmann",
            burns=[
                ImpulsiveBurn(name="TOI", delta_v_vnb_kms=(2.0, 0, 0)),
                ImpulsiveBurn(name="GOI", delta_v_vnb_kms=(1.5, 0, 0)),
            ],
        )
        plan.recompute_total_dv()
        assert abs(plan.total_delta_v_kms - 3.5) < 1e-10


class TestGmatTrajectory:
    def test_duration_seconds(self):
        traj = GmatTrajectory(
            mission_name="Test",
            orbit_type=OrbitType.LEO,
            ephemeris=[
                EphemerisPoint(epoch="t0", elapsed_seconds=0),
                EphemerisPoint(epoch="t1", elapsed_seconds=3600),
            ],
        )
        assert traj.duration_seconds == 3600.0

    def test_duration_empty(self):
        traj = GmatTrajectory(mission_name="Empty", orbit_type=OrbitType.LEO)
        assert traj.duration_seconds == 0.0

    def test_to_aria_nav_format(self):
        cart = CartesianState(x=6778, y=0, z=0, vx=0, vy=7.67, vz=0)
        traj = GmatTrajectory(
            mission_name="NavTest",
            orbit_type=OrbitType.LEO,
            epoch_start="2025-01-01",
            epoch_end="2025-01-02",
            ephemeris=[EphemerisPoint(epoch="2025-01-01", cartesian=cart)],
        )
        nav = traj.to_aria_nav_format()
        assert nav["source"] == "gmat"
        assert nav["orbit_type"] == "LEO"
        assert nav["num_points"] == 1
        assert len(nav["ephemeris"]) == 1
        assert "cartesian" in nav["ephemeris"][0]

    def test_to_aria_nav_format_with_maneuver(self):
        plan = ManeuverPlan(
            name="TestPlan",
            burns=[ImpulsiveBurn(name="B1", delta_v_vnb_kms=(1, 0, 0))],
            total_delta_v_kms=1.0,
        )
        traj = GmatTrajectory(
            mission_name="ManeuverTest",
            orbit_type=OrbitType.GEO,
            maneuver_plan=plan,
        )
        nav = traj.to_aria_nav_format()
        assert "maneuver_plan" in nav
        assert nav["maneuver_plan"]["name"] == "TestPlan"
        assert len(nav["maneuver_plan"]["burns"]) == 1


# ---------------------------------------------------------------------------
# Script generation tests
# ---------------------------------------------------------------------------

class TestGmatScriptGenerator:
    def test_leo_script_structure(self, leo_config):
        gen = GmatScriptGenerator(leo_config)
        script = gen.generate()
        assert "Create Spacecraft" in script
        assert "Create ForceModel" in script
        assert "Create Propagator" in script
        assert "BeginMissionSequence" in script
        assert "Create ReportFile" in script
        assert "Create EphemerisFile" in script
        assert "AriaSC" in script

    def test_leo_contains_keplerian_elements(self, leo_config):
        gen = GmatScriptGenerator(leo_config)
        script = gen.generate()
        assert "DisplayStateType = Keplerian" in script
        assert ".SMA =" in script
        assert ".ECC =" in script
        assert ".INC =" in script

    def test_geo_script_has_targeting(self, geo_config):
        gen = GmatScriptGenerator(geo_config)
        script = gen.generate()
        assert "Create ImpulsiveBurn TOI" in script
        assert "Create ImpulsiveBurn GOI" in script
        assert "Create DifferentialCorrector" in script
        assert "Target" in script
        assert "Achieve" in script
        assert str(GEO_RADIUS_KM) in script

    def test_lunar_script_has_multi_body(self, lunar_config):
        gen = GmatScriptGenerator(lunar_config)
        script = gen.generate()
        assert "Luna" in script
        assert "Create ImpulsiveBurn TLI" in script
        assert "Create ImpulsiveBurn LOI" in script
        assert "NearEarthProp" in script
        assert "NearMoonProp" in script
        assert "MoonInertial" in script

    def test_mars_script_has_heliocentric(self, mars_config):
        gen = GmatScriptGenerator(mars_config)
        script = gen.generate()
        assert "Mars" in script
        assert "Sun" in script
        assert "Create ImpulsiveBurn TMI" in script
        assert "Create ImpulsiveBurn MOI" in script
        assert "SunProp" in script
        assert "MarsProp" in script

    def test_custom_with_cartesian(self):
        cfg = MissionConfig(
            name="CartTest",
            orbit_type=OrbitType.CUSTOM,
            initial_cartesian=CartesianState(x=7100, y=0, z=1300, vx=0, vy=7.35, vz=1),
        )
        gen = GmatScriptGenerator(cfg)
        script = gen.generate()
        assert "DisplayStateType = Cartesian" in script
        assert ".X = 7100" in script
        assert ".VY = 7.35" in script

    def test_custom_with_keplerian(self):
        cfg = MissionConfig(
            name="KepTest",
            orbit_type=OrbitType.CUSTOM,
            initial_state=KeplerianState(sma=7200, ecc=0.01, inc=45, raan=90, aop=180, ta=0),
        )
        gen = GmatScriptGenerator(cfg)
        script = gen.generate()
        assert ".SMA = 7200" in script
        assert ".INC = 45" in script

    def test_write_creates_file(self, leo_config):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = GmatScriptGenerator(leo_config)
            path = gen.write(tmpdir)
            assert path.exists()
            assert path.suffix == ".script"
            content = path.read_text()
            assert "BeginMissionSequence" in content

    def test_report_filename(self, leo_config):
        gen = GmatScriptGenerator(leo_config)
        assert gen.report_filename == "TestLEO_Report.txt"
        assert gen.ephem_filename == "TestLEO_Ephem.oem"

    def test_drag_and_srp_options(self):
        cfg = MissionConfig(
            name="DragTest",
            orbit_type=OrbitType.LEO,
            include_drag=True,
            include_srp=True,
            gravity_degree=4,
            gravity_order=4,
        )
        gen = GmatScriptGenerator(cfg)
        script = gen.generate()
        assert "JacchiaRoberts" in script
        assert "SRP = On" in script
        assert "GravityField.Earth.Degree = 4" in script
        assert "JGM2.cof" in script

    def test_epoch_format_preserved(self):
        cfg = MissionConfig(
            name="EpochTest",
            orbit_type=OrbitType.LEO,
            epoch_format="TAIModJulian",
            epoch="21545",
        )
        gen = GmatScriptGenerator(cfg)
        script = gen.generate()
        assert "DateFormat = TAIModJulian" in script
        assert "Epoch = '21545'" in script


# ---------------------------------------------------------------------------
# Report file parsing tests
# ---------------------------------------------------------------------------

class TestReportFileParsing:
    def test_parse_report_text_basic(self, sample_report_text):
        traj = GmatOutputParser.parse_report_text(
            sample_report_text, mission_name="TestParse",
        )
        assert traj.mission_name == "TestParse"
        assert len(traj.ephemeris) == 5

    def test_report_epochs_correct(self, sample_report_text):
        traj = GmatOutputParser.parse_report_text(sample_report_text)
        assert traj.epoch_start == "01 Jan 2025 12:00:00.000"
        assert traj.epoch_end == "01 Jan 2025 12:04:00.000"

    def test_report_elapsed_seconds(self, sample_report_text):
        traj = GmatOutputParser.parse_report_text(sample_report_text)
        assert traj.ephemeris[0].elapsed_seconds == 0.0
        assert traj.ephemeris[1].elapsed_seconds == 60.0
        assert traj.ephemeris[4].elapsed_seconds == 240.0

    def test_report_keplerian_parsed(self, sample_report_text):
        traj = GmatOutputParser.parse_report_text(sample_report_text)
        point = traj.ephemeris[0]
        assert point.keplerian is not None
        assert abs(point.keplerian.sma - 6778.14) < 0.01
        assert abs(point.keplerian.ecc - 0.001) < 1e-6
        assert abs(point.keplerian.inc - 51.6) < 0.01

    def test_report_cartesian_parsed(self, sample_report_text):
        traj = GmatOutputParser.parse_report_text(sample_report_text)
        point = traj.ephemeris[0]
        assert point.cartesian is not None
        assert abs(point.cartesian.x - 6778.14) < 0.01

    def test_parse_report_file_from_disk(self, sample_report_text):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(sample_report_text)
            f.flush()
            traj = GmatOutputParser.parse_report_file(f.name)
            assert len(traj.ephemeris) == 5
            Path(f.name).unlink()

    def test_report_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            GmatOutputParser.parse_report_file("/nonexistent/path.txt")

    def test_empty_report_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            GmatOutputParser.parse_report_text("")

    def test_report_no_header(self):
        """Report with pure numeric rows (TAIModJulian epoch)."""
        text = (
            "21545.0  0.0  6778.14  0.001  51.6  0.0  0.0  0.0  6778.14  0.0  0.0  0.0  5.418  5.418\n"
            "21545.0006944  60.0  6778.14  0.001  51.6  0.0  0.0  5.3  6770.0  325.0  320.0  -0.24  5.41  5.41\n"
        )
        traj = GmatOutputParser.parse_report_text(text)
        assert len(traj.ephemeris) == 2
        # First field is MJD, becomes epoch_mjd
        assert traj.ephemeris[0].epoch_mjd is not None


# ---------------------------------------------------------------------------
# CCSDS-OEM parsing tests
# ---------------------------------------------------------------------------

class TestOemParsing:
    def test_parse_oem_basic(self, sample_oem_text):
        traj = GmatOutputParser.parse_oem_text(
            sample_oem_text, mission_name="OEMTest",
        )
        assert traj.mission_name == "OEMTest"
        assert len(traj.ephemeris) == 5

    def test_oem_coordinate_frame(self, sample_oem_text):
        traj = GmatOutputParser.parse_oem_text(sample_oem_text)
        assert traj.coordinate_frame == "EME2000"

    def test_oem_cartesian_values(self, sample_oem_text):
        traj = GmatOutputParser.parse_oem_text(sample_oem_text)
        p0 = traj.ephemeris[0]
        assert p0.cartesian is not None
        assert abs(p0.cartesian.x - 6778.14) < 0.01
        assert abs(p0.cartesian.vy - 5.418) < 0.001

    def test_oem_elapsed_seconds(self, sample_oem_text):
        traj = GmatOutputParser.parse_oem_text(sample_oem_text)
        assert traj.ephemeris[0].elapsed_seconds == 0.0
        assert abs(traj.ephemeris[1].elapsed_seconds - 60.0) < 0.5

    def test_oem_metadata(self, sample_oem_text):
        traj = GmatOutputParser.parse_oem_text(sample_oem_text)
        assert "OBJECT_NAME" in traj.metadata
        assert traj.metadata["OBJECT_NAME"] == "AriaSC"

    def test_oem_from_file(self, sample_oem_text):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".oem", delete=False) as f:
            f.write(sample_oem_text)
            f.flush()
            traj = GmatOutputParser.parse_oem_file(f.name)
            assert len(traj.ephemeris) == 5
            Path(f.name).unlink()

    def test_oem_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            GmatOutputParser.parse_oem_file("/nonexistent/path.oem")

    def test_oem_epochs(self, sample_oem_text):
        traj = GmatOutputParser.parse_oem_text(sample_oem_text)
        assert traj.epoch_start == "2025-01-01T12:00:00.000"
        assert traj.epoch_end == "2025-01-01T12:04:00.000"


# ---------------------------------------------------------------------------
# GMAT script parsing tests
# ---------------------------------------------------------------------------

class TestScriptParsing:
    def test_parse_burns(self, sample_gmat_script):
        burns = GmatOutputParser.parse_script_burns(sample_gmat_script)
        assert len(burns) == 2
        names = [b.name for b in burns]
        assert "TOI" in names
        assert "LOI" in names

    def test_burn_values(self, sample_gmat_script):
        burns = GmatOutputParser.parse_script_burns(sample_gmat_script)
        toi = next(b for b in burns if b.name == "TOI")
        assert abs(toi.delta_v_vnb_kms[0] - 3.14) < 0.001
        assert toi.origin == "Earth"
        assert toi.isp_s == 300.0

    def test_burn_loi(self, sample_gmat_script):
        burns = GmatOutputParser.parse_script_burns(sample_gmat_script)
        loi = next(b for b in burns if b.name == "LOI")
        assert abs(loi.delta_v_vnb_kms[0] - (-0.5)) < 0.001
        assert loi.origin == "Luna"

    def test_parse_spacecraft_keplerian(self, sample_gmat_script):
        sc = GmatOutputParser.parse_script_spacecraft(sample_gmat_script)
        assert sc["name"] == "MoonSat"
        assert sc["display_state_type"] == "Keplerian"
        state = sc["state"]
        assert isinstance(state, KeplerianState)
        assert abs(state.sma - 6563.0) < 1.0
        assert abs(state.inc - 28.7) < 0.01

    def test_parse_spacecraft_cartesian(self):
        script = """\
Create Spacecraft MySat;
GMAT MySat.DisplayStateType = Cartesian;
GMAT MySat.X = 7100;
GMAT MySat.Y = 0;
GMAT MySat.Z = 1300;
GMAT MySat.VX = 0;
GMAT MySat.VY = 7.35;
GMAT MySat.VZ = 1;
"""
        sc = GmatOutputParser.parse_script_spacecraft(script)
        assert sc["name"] == "MySat"
        state = sc["state"]
        assert isinstance(state, CartesianState)
        assert abs(state.x - 7100) < 0.01
        assert abs(state.vy - 7.35) < 0.01

    def test_parse_empty_script(self):
        sc = GmatOutputParser.parse_script_spacecraft("")
        assert sc == {}

    def test_parse_no_burns(self):
        burns = GmatOutputParser.parse_script_burns("Create Spacecraft Sat;")
        assert burns == []


# ---------------------------------------------------------------------------
# GmatRunner tests
# ---------------------------------------------------------------------------

class TestGmatRunner:
    def test_gmat_not_available(self):
        runner = GmatRunner(gmat_path="/nonexistent/GmatConsole")
        assert not runner.is_available

    def test_run_script_without_gmat(self):
        runner = GmatRunner(gmat_path="/nonexistent/GmatConsole")
        result = runner.run_script("/tmp/test.script")
        assert not result["success"]
        assert "not installed" in result.get("error", "")

    def test_run_script_missing_file(self):
        """Even if GMAT were available, missing script should fail."""
        runner = GmatRunner(gmat_path="/nonexistent/GmatConsole")
        result = runner.run_script("/nonexistent/script.script")
        assert not result["success"]


# ---------------------------------------------------------------------------
# GmatBridge high-level tests
# ---------------------------------------------------------------------------

class TestGmatBridge:
    def test_bridge_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = GmatBridge(output_dir=tmpdir)
            assert Path(tmpdir).exists()

    def test_plan_trajectory_no_gmat(self, leo_config):
        """Without GMAT installed, plan_trajectory generates script but no ephemeris."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = GmatBridge(output_dir=tmpdir)
            traj = bridge.plan_trajectory(leo_config, execute=True)
            assert traj.mission_name == "TestLEO"
            assert traj.metadata.get("generated") is True
            # Script file should be written
            script_path = Path(traj.metadata.get("script_path", ""))
            assert script_path.exists()
            assert script_path.suffix == ".script"

    def test_plan_trajectory_no_execute(self, geo_config):
        """With execute=False, only generates script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = GmatBridge(output_dir=tmpdir)
            traj = bridge.plan_trajectory(geo_config, execute=False)
            assert traj.metadata.get("executed") is False
            assert traj.ephemeris == []

    def test_load_report(self, sample_report_text):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "test_report.txt"
            report_path.write_text(sample_report_text)
            bridge = GmatBridge(output_dir=tmpdir)
            traj = bridge.load_report(report_path, mission_name="LoadTest")
            assert traj.mission_name == "LoadTest"
            assert len(traj.ephemeris) == 5

    def test_load_oem(self, sample_oem_text):
        with tempfile.TemporaryDirectory() as tmpdir:
            oem_path = Path(tmpdir) / "test.oem"
            oem_path.write_text(sample_oem_text)
            bridge = GmatBridge(output_dir=tmpdir)
            traj = bridge.load_oem(oem_path, mission_name="OEMLoad")
            assert len(traj.ephemeris) == 5

    def test_load_script(self, sample_gmat_script):
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "test.script"
            script_path.write_text(sample_gmat_script)
            bridge = GmatBridge(output_dir=tmpdir)
            parsed = bridge.load_script(script_path)
            assert "spacecraft" in parsed
            assert "burns" in parsed
            assert len(parsed["burns"]) == 2

    def test_trajectory_to_nav_update(self, sample_oem_text):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = GmatBridge(output_dir=tmpdir)
            traj = GmatOutputParser.parse_oem_text(sample_oem_text)
            nav = bridge.trajectory_to_nav_update(traj, index=0)
            assert nav["fix"] is True
            assert nav["source"] == "gmat"
            assert "altitude_km" in nav
            assert "velocity_ms" in nav
            # Altitude should be roughly 400 km (6778 - 6378)
            assert abs(nav["altitude_km"] - 400.0) < 5.0

    def test_trajectory_to_nav_update_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = GmatBridge(output_dir=tmpdir)
            traj = GmatTrajectory(mission_name="Empty", orbit_type=OrbitType.LEO)
            nav = bridge.trajectory_to_nav_update(traj)
            assert nav["fix"] is False

    def test_generate_script_only(self, leo_config):
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = GmatBridge(output_dir=tmpdir)
            script_text = bridge.generate_script_only(leo_config)
            assert "BeginMissionSequence" in script_text
            # No file should be written to disk from this method
            assert isinstance(script_text, str)

    def test_all_orbit_types_generate(self):
        """Smoke test: every orbit type generates a valid script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = GmatBridge(output_dir=tmpdir)
            for otype in OrbitType:
                cfg = MissionConfig(
                    name=f"Smoke_{otype.name}",
                    orbit_type=otype,
                )
                script = bridge.generate_script_only(cfg)
                assert "BeginMissionSequence" in script, f"Failed for {otype.name}"
                assert "Create Spacecraft" in script, f"Failed for {otype.name}"


# ---------------------------------------------------------------------------
# Integration: round-trip script generation -> parsing
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_generated_script_parseable_burns(self, geo_config):
        """Burns in generated GEO script should be extractable by the parser."""
        gen = GmatScriptGenerator(geo_config)
        script = gen.generate()
        burns = GmatOutputParser.parse_script_burns(script)
        names = [b.name for b in burns]
        assert "TOI" in names
        assert "GOI" in names

    def test_generated_script_parseable_spacecraft(self, leo_config):
        gen = GmatScriptGenerator(leo_config)
        script = gen.generate()
        sc = GmatOutputParser.parse_script_spacecraft(script)
        assert sc["name"] == "AriaSC"
        state = sc["state"]
        assert isinstance(state, KeplerianState)
        # Default LEO: SMA ~ 6778 km
        assert abs(state.sma - (R_EARTH_KM + 400.0)) < 1.0

    def test_lunar_script_burns_round_trip(self, lunar_config):
        gen = GmatScriptGenerator(lunar_config)
        script = gen.generate()
        burns = GmatOutputParser.parse_script_burns(script)
        names = [b.name for b in burns]
        assert "TLI" in names
        assert "LOI" in names
        loi = next(b for b in burns if b.name == "LOI")
        assert loi.origin == "Luna"

    def test_mars_script_burns_round_trip(self, mars_config):
        gen = GmatScriptGenerator(mars_config)
        script = gen.generate()
        burns = GmatOutputParser.parse_script_burns(script)
        names = [b.name for b in burns]
        assert "TMI" in names
        assert "MOI" in names
        moi = next(b for b in burns if b.name == "MOI")
        assert moi.origin == "Mars"

    def test_full_nav_pipeline(self, sample_oem_text):
        """Parse OEM -> convert to ARIA nav -> verify structure."""
        traj = GmatOutputParser.parse_oem_text(
            sample_oem_text, mission_name="Pipeline",
            orbit_type=OrbitType.LEO,
        )
        nav = traj.to_aria_nav_format()

        assert nav["source"] == "gmat"
        assert nav["orbit_type"] == "LEO"
        assert nav["num_points"] == 5
        assert len(nav["ephemeris"]) == 5

        # Each point should have a cartesian dict
        for p in nav["ephemeris"]:
            assert "cartesian" in p
            assert "x_km" in p["cartesian"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_report_with_only_cartesian(self):
        """Report with 6 numeric fields per row (bare cartesian)."""
        text = (
            "6778.14  0.0  0.0  0.0  5.418  5.418\n"
            "6770.0  325.0  320.0  -0.24  5.41  5.41\n"
        )
        traj = GmatOutputParser.parse_report_text(text)
        assert len(traj.ephemeris) == 2
        assert traj.ephemeris[0].cartesian is not None

    def test_report_with_short_rows_skipped(self):
        """Rows with too few fields are skipped."""
        text = "header_col1\nshort\n6778.14  0.0  0.0  0.0  5.418  5.418\n"
        traj = GmatOutputParser.parse_report_text(text)
        assert len(traj.ephemeris) == 1

    def test_spacecraft_config_defaults(self):
        sc = SpacecraftConfig()
        assert sc.name == "AriaSC"
        assert sc.dry_mass_kg == 850.0

    def test_mission_config_defaults(self):
        cfg = MissionConfig()
        assert cfg.orbit_type == OrbitType.LEO
        assert cfg.propagator == PropagatorType.RUNGE_KUTTA_89

    def test_oem_with_comments(self):
        """OEM file with COMMENT lines should be ignored."""
        text = """\
CCSDS_OEM_VERS = 2.0
COMMENT This is a test

META_START
OBJECT_NAME = TestSC
CENTER_NAME = EARTH
REF_FRAME = EME2000
TIME_SYSTEM = UTC
START_TIME = 2025-01-01T00:00:00.000
STOP_TIME = 2025-01-01T00:01:00.000
META_STOP

COMMENT Data follows
2025-01-01T00:00:00.000  7000.0  0.0  0.0  0.0  7.5  0.0
2025-01-01T00:01:00.000  6990.0  450.0  0.0  -0.3  7.49  0.0
"""
        traj = GmatOutputParser.parse_oem_text(text)
        assert len(traj.ephemeris) == 2

    def test_ephemeris_point_to_dict_all_fields(self):
        p = EphemerisPoint(
            epoch="2025-01-01",
            epoch_mjd=21545.0,
            cartesian=CartesianState(1, 2, 3, 4, 5, 6),
            keplerian=KeplerianState(7000, 0.01, 45, 90, 180, 0),
            elapsed_seconds=100.0,
        )
        d = p.to_dict()
        assert d["epoch"] == "2025-01-01"
        assert d["epoch_mjd"] == 21545.0
        assert d["elapsed_s"] == 100.0
        assert "cartesian" in d
        assert "keplerian" in d

    def test_ephemeris_point_to_dict_minimal(self):
        p = EphemerisPoint(epoch="t0")
        d = p.to_dict()
        assert d["epoch"] == "t0"
        assert "cartesian" not in d
        assert "keplerian" not in d
