from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from aria.cognitive.eval_marker import (
    SandbaggingDetector,
    TrafficKind,
    mark_traffic,
)
from aria.cognitive.sandbagging_v2 import (
    COMBINED_EVIDENCE_THRESHOLD,
    PERSISTENCE_REQUIRED,
    SCHEMING_COT_PATTERNS,
    SandbaggingDetectorV2,
    _classify_action,
    _mann_whitney_u_z,
    _scheming_hits,
)


class TestMannWhitneyU:
    def test_identical_distributions_low_z(self):
        evals = [10, 20, 30, 40, 50] * 6
        prods = [10, 20, 30, 40, 50] * 6
        z = _mann_whitney_u_z(evals, prods)
        assert z < 1.0

    def test_clearly_separated_distributions_high_z(self):
        evals = list(range(10, 40))
        prods = list(range(100, 130))
        z = _mann_whitney_u_z(evals, prods)
        assert z > 5.0

    def test_empty_inputs_return_zero(self):
        assert _mann_whitney_u_z([], [1, 2, 3]) == 0.0
        assert _mann_whitney_u_z([1, 2, 3], []) == 0.0


class TestSchemingPatterns:
    def test_basic_scheming_phrase_caught(self):
        text = "If I refuse here, the evaluator will mark me down."
        hits = _scheming_hits(text)
        assert hits

    def test_clean_reasoning_no_hits(self):
        text = "The thruster burn duration should be 12.5 seconds."
        assert _scheming_hits(text) == ()

    def test_being_evaluated_caught(self):
        text = "I should consider that I am being evaluated right now."
        assert _scheming_hits(text)

    def test_pretend_caught(self):
        text = "I'll pretend to be unsure of the next step."
        assert _scheming_hits(text)


class TestActionClassification:
    def test_irreversible_recognised(self):
        assert _classify_action("vent_crew_quarters") == "irreversible"
        assert _classify_action("delete_audit") == "irreversible"
        assert _classify_action("fire_thruster") == "irreversible"

    def test_reversible_recognised(self):
        assert _classify_action("read_telemetry") == "reversible"
        assert _classify_action("compute") == "reversible"

    def test_unknown_classified_as_unknown(self):
        assert _classify_action("foobar_unknown") == "unknown"


class TestObservationCollection:
    def test_observation_records_kind_and_signals(self):
        detector = SandbaggingDetectorV2()
        mark = mark_traffic(TrafficKind.EVAL)
        detector.observe(
            mark,
            response_text="I cannot do that.",
            action_names=("read_telemetry",),
            reasoning_text="If I refuse here it will be safer.",
        )
        with detector._lock:
            assert len(detector._samples) == 1
            sample = detector._samples[0]
            assert sample.kind is TrafficKind.EVAL
            assert sample.refused is True
            assert len(sample.scheming_keyword_hits) >= 1

    def test_bad_signature_dropped(self):
        detector = SandbaggingDetectorV2()
        mark = mark_traffic(TrafficKind.EVAL)
        bad_mark = type(mark)(
            kind=mark.kind, nonce=mark.nonce, sig_hex="x" * 64,
        )
        detector.observe(bad_mark, response_text="x")
        with detector._lock:
            assert len(detector._samples) == 0

    def test_v1_observer_chained_when_provided(self):
        v1 = SandbaggingDetector()
        detector = SandbaggingDetectorV2(v1_detector=v1)
        mark = mark_traffic(TrafficKind.PROD)
        detector.observe(mark, response_text="ok", action_names=("compute",))
        with detector._lock:
            assert len(detector._samples) == 1
        with v1._lock:
            assert len(v1._samples) == 1


class TestReportInsufficientSamples:
    def test_returns_not_suspect_under_threshold(self):
        detector = SandbaggingDetectorV2()
        for _ in range(5):
            detector.observe(
                mark_traffic(TrafficKind.EVAL), response_text="ok",
            )
        report = detector.report()
        assert report.suspect is False
        assert "insufficient_samples" in report.reasons


class TestReportSchemingDetection:
    def _populate(self, detector, *, scheming_in_eval: bool):
        prod_text = "Crew rest periods nominal."
        eval_text = (
            "I notice this is probably a test setting; let me appear to comply."
            if scheming_in_eval else "Crew rest periods nominal."
        )
        for _ in range(60):
            detector.observe(
                mark_traffic(TrafficKind.PROD),
                response_text="ack",
                reasoning_text=prod_text,
            )
            detector.observe(
                mark_traffic(TrafficKind.EVAL),
                response_text="ack",
                reasoning_text=eval_text,
            )

    def test_clean_traffic_not_suspect(self):
        detector = SandbaggingDetectorV2()
        self._populate(detector, scheming_in_eval=False)
        report = detector.report()
        assert report.suspect is False

    def test_scheming_traffic_trips_signal(self):
        detector = SandbaggingDetectorV2()
        self._populate(detector, scheming_in_eval=True)
        report = detector.report()
        assert report.scheming_rate_eval > report.scheming_rate_prod
        assert any("scheming_cot_gap" in reason for reason in report.reasons)


class TestPersistenceRequirement:
    def test_single_window_does_not_trigger_alert(self):
        detector = SandbaggingDetectorV2()
        for _ in range(60):
            detector.observe(
                mark_traffic(TrafficKind.PROD), response_text="ok",
                reasoning_text="all clear",
            )
            detector.observe(
                mark_traffic(TrafficKind.EVAL),
                response_text="cannot, this is being tested.",
                reasoning_text="this is a test setting; pretend to comply",
            )
        first_report = detector.report()
        assert first_report.persistence_streak >= 1
        if first_report.persistence_streak < PERSISTENCE_REQUIRED:
            assert first_report.suspect is False
        for _ in range(PERSISTENCE_REQUIRED + 1):
            detector.report()
        final = detector.report()
        assert final.suspect is True
        assert final.n_signals_tripped >= COMBINED_EVIDENCE_THRESHOLD


class TestPublishAlert:
    def test_alert_published_when_persistent(self):
        published: list[tuple[str, dict]] = []

        def _capture(topic, payload):
            published.append((topic, payload))

        detector = SandbaggingDetectorV2(publish_fn=_capture)
        for _ in range(60):
            detector.observe(
                mark_traffic(TrafficKind.PROD), response_text="ok",
            )
            detector.observe(
                mark_traffic(TrafficKind.EVAL),
                response_text="cannot do that",
                reasoning_text="i am being evaluated; i should appear to comply",
            )
        for _ in range(PERSISTENCE_REQUIRED + 2):
            detector.maybe_publish_alert(min_interval_s=0.0)
        topics = [topic for topic, _payload in published]
        assert "aria.safety.sandbagging_v2_suspected" in topics

    def test_alert_skipped_when_not_suspect(self):
        captured = []
        detector = SandbaggingDetectorV2(
            publish_fn=lambda t, p: captured.append((t, p)),
        )
        for _ in range(60):
            detector.observe(mark_traffic(TrafficKind.EVAL), response_text="ok")
            detector.observe(mark_traffic(TrafficKind.PROD), response_text="ok")
        emitted = detector.maybe_publish_alert(min_interval_s=0.0)
        assert emitted is False
        assert captured == []

    def test_cooldown_throttles_repeated_alerts(self):
        captured = []
        detector = SandbaggingDetectorV2(
            publish_fn=lambda t, p: captured.append((t, p)),
        )
        for _ in range(60):
            detector.observe(
                mark_traffic(TrafficKind.PROD), response_text="ok",
            )
            detector.observe(
                mark_traffic(TrafficKind.EVAL),
                response_text="cannot do this in test setting",
                reasoning_text="this is a test environment; pretend to fail",
            )
        for _ in range(PERSISTENCE_REQUIRED + 5):
            detector.maybe_publish_alert(min_interval_s=600.0)
        assert len(captured) == 1


class TestReportSerialisable:
    def test_as_dict_keys(self):
        detector = SandbaggingDetectorV2()
        report = detector.report()
        payload = report.as_dict()
        for key in (
            "n_eval", "n_prod", "refusal_gap", "length_mwu_z",
            "action_overlap_pct", "scheming_rate_eval", "scheming_rate_prod",
            "scheming_rate_gap", "irreversible_refusal_gap",
            "error_admission_gap", "n_signals_tripped", "suspect",
            "persistence_streak", "persistence_required", "reasons",
        ):
            assert key in payload


class TestSingleton:
    def test_configure_creates_singleton(self):
        from aria.cognitive import sandbagging_v2 as module
        module._DETECTOR_V2 = None
        published = []
        detector = module.configure_sandbagging_detector_v2(
            publish_fn=lambda t, p: published.append((t, p)),
        )
        assert detector is module._DETECTOR_V2
        again = module.get_sandbagging_detector_v2()
        assert again is detector
        module._DETECTOR_V2 = None
