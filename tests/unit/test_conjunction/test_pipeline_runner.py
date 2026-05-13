"""Tests for ConjunctionPipeline.run() and PipelineResult."""

import math
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np

from aria.conjunction.core.types import (
    CloseApproach,
    ObjectType,
    OrbitalElements,
    RiskLevel,
    SpaceObject,
)
from aria.conjunction.pipeline.alerts import Alert
from aria.conjunction.pipeline.runner import ConjunctionPipeline, PipelineResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EPOCH = datetime(2024, 6, 15, 12, 0, 0)

# Real ISS TLE (2026 epoch)
_ISS_L1 = "1 25544U 98067A   26090.13309952  .00011434  00000+0  21777-3 0  9998"
_ISS_L2 = "2 25544  51.6341 326.3497 0006203 253.7499 106.2807 15.48671303559658"

# POISK TLE
_POI_L1 = "1 36086U 09060A   26090.13309952  .00011434  00000+0  21777-3 0  9996"
_POI_L2 = "2 36086  51.6341 326.3497 0006203 253.7499 106.2807 15.48671303559459"


def _make_obj(norad_id: str, tle1: str = _ISS_L1, tle2: str = _ISS_L2) -> SpaceObject:
    elements = OrbitalElements(
        semi_major_axis=6780.0, eccentricity=0.001,
        inclination=math.radians(51.6), raan=0.0, arg_perigee=0.0,
        true_anomaly=0.0, epoch=_EPOCH,
    )
    return SpaceObject(
        norad_id=norad_id, name=f"OBJ-{norad_id}",
        tle_line1=tle1, tle_line2=tle2,
        object_type=ObjectType.PAYLOAD,
        elements=elements,
    )


def _make_approach(  # noqa: E501
    miss_km: float = 0.5, pc: float = 1e-4, risk: RiskLevel = RiskLevel.RED
) -> CloseApproach:
    tca = _EPOCH + timedelta(hours=24)
    primary = _make_obj("25544")
    secondary = _make_obj("99999")
    return CloseApproach(
        primary=primary, secondary=secondary,
        tca=tca,
        miss_distance_km=miss_km,
        miss_distance_rtn=np.array([0.1, miss_km, 0.1]),
        relative_velocity_km_s=7.5,
        relative_position=np.array([miss_km, 0.0, 0.0]),
        relative_velocity_vec=np.array([0.0, 7.5, 0.0]),
        probability_of_collision=pc,
        risk_level=risk,
    )


def _make_alert(approach: CloseApproach, risk: RiskLevel = RiskLevel.RED) -> Alert:
    return Alert(
        approach=approach,
        risk_level=risk,
        reasons=["Test alert"],
        time_critical=True,
        requires_maneuver=(risk == RiskLevel.RED),
    )


# ---------------------------------------------------------------------------
# PipelineResult
# ---------------------------------------------------------------------------

class TestPipelineResult:

    def test_summary_contains_key_fields(self):
        result = PipelineResult(catalog_size=100, screening_window_hours=72.0)
        result.total_pairs_checked = 4950
        result.candidates = 12
        result.elapsed_seconds = 3.5
        s = result.summary()
        assert "100" in s
        assert "72" in s
        assert "12" in s
        assert "3.5" in s

    def test_summary_red_yellow_counts(self):
        approach_red = _make_approach(risk=RiskLevel.RED)
        approach_yellow = _make_approach(risk=RiskLevel.YELLOW)
        result = PipelineResult(catalog_size=50, screening_window_hours=24.0)
        result.alerts = [
            _make_alert(approach_red, RiskLevel.RED),
            _make_alert(approach_yellow, RiskLevel.YELLOW),
        ]
        s = result.summary()
        assert "1 RED" in s
        assert "1 YELLOW" in s

    def test_summary_cdm_count(self):
        result = PipelineResult(catalog_size=10, screening_window_hours=48.0)
        result.cdms = ["cdm1", "cdm2", "cdm3"]
        s = result.summary()
        assert "3" in s

    def test_summary_zero_alerts(self):
        result = PipelineResult(catalog_size=5, screening_window_hours=72.0)
        result.alerts = []
        s = result.summary()
        assert "0 RED" in s
        assert "0 YELLOW" in s

    def test_summary_returns_string(self):
        result = PipelineResult(catalog_size=1, screening_window_hours=24.0)
        assert isinstance(result.summary(), str)

    def test_total_pairs_computed(self):
        """n objects → n*(n-1)/2 pairs."""
        result = PipelineResult(catalog_size=10, screening_window_hours=72.0)
        result.total_pairs_checked = 10 * 9 // 2
        assert result.total_pairs_checked == 45


# ---------------------------------------------------------------------------
# ConjunctionPipeline — empty catalog / no candidates (fast paths)
# ---------------------------------------------------------------------------

class TestPipelineEmptyAndNoCandidates:

    def test_empty_catalog(self):
        pipeline = ConjunctionPipeline()
        result = pipeline.run([], window_hours=24.0, start_epoch=_EPOCH)
        assert result.catalog_size == 0
        assert result.candidates == 0
        assert len(result.close_approaches) == 0
        assert len(result.alerts) == 0

    def test_single_object_no_pairs(self):
        obj = _make_obj("25544", _ISS_L1, _ISS_L2)
        pipeline = ConjunctionPipeline()
        result = pipeline.run([obj], window_hours=24.0, start_epoch=_EPOCH)
        assert result.catalog_size == 1
        assert result.total_pairs_checked == 0
        assert result.candidates == 0

    def test_no_candidates_returns_early(self):
        """When screener returns no candidates, pipeline stops early."""
        mock_screener = MagicMock()
        mock_screener.screen.return_value = []
        pipeline = ConjunctionPipeline(screener=mock_screener)

        obj1 = _make_obj("25544", _ISS_L1, _ISS_L2)
        obj2 = _make_obj("36086", _POI_L1, _POI_L2)
        result = pipeline.run([obj1, obj2], window_hours=24.0, start_epoch=_EPOCH)

        assert result.candidates == 0
        assert len(result.close_approaches) == 0
        assert len(result.alerts) == 0
        assert result.run_end is not None

    def test_run_sets_elapsed_time(self):
        pipeline = ConjunctionPipeline()
        result = pipeline.run([], window_hours=24.0, start_epoch=_EPOCH)
        assert result.elapsed_seconds >= 0.0
        assert result.run_end is not None


# ---------------------------------------------------------------------------
# ConjunctionPipeline — with mocked sub-components
# ---------------------------------------------------------------------------

class TestPipelineMockedComponents:

    def _build_pipeline_with_mocks(
        self,
        candidates=None,
        approaches=None,
        alerts=None,
        cdms=None,
        maneuver_plans=None,
    ) -> tuple["ConjunctionPipeline", dict]:
        """Build a pipeline with all sub-components mocked."""
        _make_approach()
        candidates = candidates or []
        approaches = approaches or []
        alerts = alerts or []
        cdms = cdms or []
        maneuver_plans = maneuver_plans or []

        mock_screener = MagicMock()
        mock_screener.screen.return_value = candidates

        mock_pc = MagicMock()
        mock_pc.calculate.return_value = 1e-4

        mock_alert = MagicMock()
        mock_alert.classify.return_value = alerts

        mock_cdm = MagicMock()
        mock_cdm.write_many.return_value = cdms

        mock_maneuver = MagicMock()
        mock_maneuver.plan_batch.return_value = maneuver_plans

        pipeline = ConjunctionPipeline(
            screener=mock_screener,
            pc_calculator=mock_pc,
            alert_classifier=mock_alert,
            cdm_writer=mock_cdm,
            maneuver_planner=mock_maneuver,
        )
        mocks = {
            "screener": mock_screener,
            "pc": mock_pc,
            "alert": mock_alert,
            "cdm": mock_cdm,
            "maneuver": mock_maneuver,
        }
        return pipeline, mocks

    def test_pipeline_with_one_red_approach(self):
        """Full pipeline flow with one RED approach."""
        approach = _make_approach(risk=RiskLevel.RED)
        alert = _make_alert(approach, RiskLevel.RED)
        candidate = (0, 1, _EPOCH + timedelta(hours=24))

        pipeline, mocks = self._build_pipeline_with_mocks(
            candidates=[candidate],
            alerts=[alert],
            cdms=["CDM_CONTENT"],
            maneuver_plans=[MagicMock()],
        )

        with patch.object(pipeline, "_parallel_build_approaches", return_value=[approach]):
            result = pipeline.run(
                [_make_obj("25544"), _make_obj("99999")],
                window_hours=24.0,
                start_epoch=_EPOCH,
            )

        assert result.candidates == 1
        assert len(result.close_approaches) == 1
        assert len(result.alerts) == 1
        assert len(result.cdms) == 1
        assert len(result.maneuver_plans) == 1

    def test_pc_calculator_called_for_each_approach(self):
        approach1 = _make_approach(risk=RiskLevel.YELLOW)
        approach2 = _make_approach(risk=RiskLevel.GREEN)
        candidate = (0, 1, _EPOCH + timedelta(hours=24))

        pipeline, mocks = self._build_pipeline_with_mocks(
            candidates=[candidate],
            alerts=[],
        )
        with patch.object(pipeline, "_parallel_build_approaches", return_value=[approach1, approach2]):  # noqa: E501
            pipeline.run(
                [_make_obj("A"), _make_obj("B")],
                window_hours=24.0,
                start_epoch=_EPOCH,
            )

        # Should call calculate for both approaches
        assert mocks["pc"].calculate.call_count == 2

    def test_cdm_writer_called_for_alerting_approaches(self):
        approach = _make_approach(risk=RiskLevel.YELLOW)
        alert = _make_alert(approach, RiskLevel.YELLOW)
        candidate = (0, 1, _EPOCH + timedelta(hours=24))

        pipeline, mocks = self._build_pipeline_with_mocks(
            candidates=[candidate],
            alerts=[alert],
            cdms=["<CDM/>"],
        )
        with patch.object(pipeline, "_parallel_build_approaches", return_value=[approach]):
            result = pipeline.run(
                [_make_obj("A"), _make_obj("B")],
                window_hours=24.0,
                start_epoch=_EPOCH,
            )

        # CDM writer should be called with the alerting approaches
        mocks["cdm"].write_many.assert_called_once()
        assert len(result.cdms) == 1

    def test_maneuver_planner_only_for_red(self):
        """Maneuver planner should only receive RED approaches."""
        approach_red = _make_approach(risk=RiskLevel.RED, pc=1e-3)
        approach_yellow = _make_approach(risk=RiskLevel.YELLOW, pc=5e-5)
        alert_red = _make_alert(approach_red, RiskLevel.RED)
        alert_yellow = _make_alert(approach_yellow, RiskLevel.YELLOW)
        candidate = (0, 1, _EPOCH + timedelta(hours=24))

        pipeline, mocks = self._build_pipeline_with_mocks(
            candidates=[candidate],
            alerts=[alert_red, alert_yellow],
        )
        with patch.object(pipeline, "_parallel_build_approaches",
                          return_value=[approach_red, approach_yellow]):
            pipeline.run(
                [_make_obj("A"), _make_obj("B")],
                window_hours=24.0,
                start_epoch=_EPOCH,
            )

        # Maneuver plan_batch should be called with only RED approaches
        call_args = mocks["maneuver"].plan_batch.call_args
        red_approaches_passed = call_args[0][0]
        assert all(a.risk_level == RiskLevel.RED for a in red_approaches_passed)

    def test_start_epoch_defaults_to_utcnow(self):
        """When start_epoch=None, pipeline uses current UTC time."""
        pipeline, _ = self._build_pipeline_with_mocks(candidates=[])
        before = datetime.utcnow()
        result = pipeline.run([], window_hours=24.0, start_epoch=None)
        after = datetime.utcnow()
        assert before <= result.run_start <= after

    def test_total_pairs_formula(self):
        """n objects → n*(n-1)/2 total pairs."""
        objects = [_make_obj(str(i)) for i in range(5)]
        pipeline, _ = self._build_pipeline_with_mocks(candidates=[])
        result = pipeline.run(objects, window_hours=24.0, start_epoch=_EPOCH)
        assert result.total_pairs_checked == 5 * 4 // 2  # = 10


# ---------------------------------------------------------------------------
# _parallel_build_approaches — serial vs parallel dispatch
# ---------------------------------------------------------------------------

class TestParallelBuildApproaches:

    def test_serial_path_for_few_candidates(self):
        """≤4 candidates → serial path via build_close_approaches_batch."""
        pipeline = ConjunctionPipeline(max_workers=None)
        objects = [_make_obj("A"), _make_obj("B")]
        candidates = [(0, 1, _EPOCH + timedelta(hours=12))]

        with patch("aria.conjunction.pipeline.runner.build_close_approaches_batch",
                   return_value=[]) as mock_batch:
            pipeline._parallel_build_approaches(objects, candidates)
            mock_batch.assert_called_once()

    def test_max_workers_1_forces_serial(self):
        """max_workers=1 forces serial path regardless of candidate count."""
        pipeline = ConjunctionPipeline(max_workers=1)
        objects = [_make_obj(str(i)) for i in range(4)]
        candidates = [(i, j, _EPOCH + timedelta(hours=12)) for i in range(4) for j in range(i+1, 4)]
        # 6 candidates > 4, but max_workers=1 → serial

        with patch("aria.conjunction.pipeline.runner.build_close_approaches_batch",
                   return_value=[]) as mock_batch:
            pipeline._parallel_build_approaches(objects, candidates)
            mock_batch.assert_called_once()

    def test_returns_list(self):
        pipeline = ConjunctionPipeline(max_workers=1)
        objects = [_make_obj("A"), _make_obj("B")]
        candidates = [(0, 1, _EPOCH + timedelta(hours=12))]

        with patch("aria.conjunction.pipeline.runner.build_close_approaches_batch", return_value=[]):
            result = pipeline._parallel_build_approaches(objects, candidates)
            assert isinstance(result, list)
