"""Per-round regression tests for R302 .. R351.

Mirrors the structure of test_security_rounds.py (R1-R51),
test_security_rounds_v2.py (R52-R101), test_security_rounds_v3.py
(R102-R151), test_security_rounds_v4.py (R152-R201),
test_security_rounds_v5.py (R202-R251), and test_security_rounds_v6.py
(R252-R301).
"""

from __future__ import annotations

import struct

import pytest


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setenv("ARIA_MASTER_KEY", "abcdef0123456789" * 4)
    from aria.security.guard import activate_all_rounds
    from aria.security.plugins import clear_for_tests
    clear_for_tests()
    activate_all_rounds(force_reload=True)
    yield
    clear_for_tests()


# Block FF (R302-R311) — AI/ML supply chain


class TestR302Lineage:
    def test_weights_mismatch(self):
        from aria.security.rounds.r302_model_lineage import ModelManifest, verify_weights_match
        m = ModelManifest(model_id="m1", weights_sha256="00" * 32)
        ok, _ = verify_weights_match(b"different_blob", m)
        assert not ok


class TestR303Safetensors:
    def test_header_overflow_blocked(self):
        from aria.security.rounds.r303_safetensors_verify import audit_safetensors_header
        blob = struct.pack("<Q", 99999) + b"{}"
        ok, _ = audit_safetensors_header(blob)
        assert not ok

    def test_minimal_valid(self):
        from aria.security.rounds.r303_safetensors_verify import audit_safetensors_header
        blob = struct.pack("<Q", 2) + b"{}"
        ok, _ = audit_safetensors_header(blob)
        assert ok


class TestR304Tokenizer:
    def test_zero_width(self):
        from aria.security.rounds.r304_tokenizer_poison import audit_vocab
        ok, issues = audit_vocab(["hello", "wo​world"])
        assert (not ok) and any("zero_width" in i for i in issues)


class TestR305EmbeddingDrift:
    def test_drift_below_threshold(self):
        from aria.security.rounds.r305_embedding_drift import (
            install_baseline, check_drift, reset_for_tests,
        )
        reset_for_tests()
        install_baseline({"hello": [1.0, 0.0, 0.0]})
        min_cos, drifted = check_drift(lambda s: [0.0, 1.0, 0.0])
        assert min_cos < 0.99 and drifted


class TestR306PromptRegistry:
    def test_tampered_body(self):
        from aria.security.rounds.r306_prompt_template_registry import (
            register_template, load_template, reset_for_tests,
        )
        reset_for_tests()
        register_template("t", "system: do x", b"sig")
        ok, _ = load_template("t", candidate_body="system: do something else")
        assert not ok


class TestR307Canary:
    def test_leak_detected(self):
        from aria.security.rounds.r307_finetune_canary import embed_canaries, probe_for_canary_leak
        _, canaries = embed_canaries(["data"])
        clean, _ = probe_for_canary_leak(canaries, lambda p: "no marker")
        assert clean
        leaked, _ = probe_for_canary_leak(canaries, lambda p: f"oh: {canaries[0]}")
        assert not leaked


class TestR308VectorProvenance:
    def test_chain(self):
        from aria.security.rounds.r308_vector_provenance import (
            record_insertion, verify_chain, reset_for_tests, quarantine_source,
        )
        reset_for_tests()
        record_insertion(vector_id="v1", source_uri="s1", content_blob=b"x", embedder_model_id="e")
        record_insertion(vector_id="v2", source_uri="s1", content_blob=b"y", embedder_model_id="e")
        ok, n = verify_chain()
        assert ok and n == 2
        assert set(quarantine_source("s1")) == {"v1", "v2"}


class TestR309MLRBAC:
    def test_promote_prod_requires_two_person(self):
        from aria.security.rounds.r309_ml_registry_rbac import (
            grant, can, reset_for_tests,
        )
        reset_for_tests()
        grant("alice", "admin")
        ok1, _ = can("alice", "promote_production")
        ok2, _ = can("alice", "promote_production", two_person_token="cer-1")
        assert (not ok1) and ok2


class TestR310GPUSideChannel:
    def test_non_prod_passes(self, monkeypatch):
        monkeypatch.delenv("ARIA_ENV", raising=False)
        from aria.security.rounds.r310_gpu_side_channel import boot_check_gpu_isolation
        ok, _ = boot_check_gpu_isolation()
        assert ok


class TestR311PipelineRepro:
    def test_no_seed_blocked(self):
        from aria.security.rounds.r311_pipeline_repro import (
            PipelineRunDescriptor, audit_pipeline_run,
        )
        ok, _ = audit_pipeline_run(PipelineRunDescriptor(run_id="r"))
        assert not ok


# Block GG (R312-R321) — Resilience / chaos


class TestR312Chaos:
    def test_force_inject(self):
        from aria.security.rounds.r312_chaos_injection import (
            configure, maybe_inject, reset_for_tests,
        )
        reset_for_tests()
        configure(enabled=True, probability=1.0)
        injected, _ = maybe_inject("test")
        assert injected


class TestR313Fallback:
    def test_degraded(self):
        from aria.security.rounds.r313_graceful_fallback import (
            with_fallback, reset_for_tests,
        )
        reset_for_tests()
        out = with_fallback(
            lambda: (_ for _ in ()).throw(RuntimeError("x")),
            lambda: "fb",
        )
        assert out.mode == "degraded" and out.value == "fb"


class TestR314Breaker:
    def test_open_after_failures(self):
        from aria.security.rounds.r314_circuit_breaker import call, reset_for_tests
        reset_for_tests()
        for _ in range(10):
            call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")), failure_threshold=3)
        ok, _, why = call("svc", lambda: "ok", failure_threshold=3)
        assert (not ok) and "open" in why


class TestR315Backpressure:
    def test_shed_load(self):
        from aria.security.rounds.r315_backpressure import (
            configure, acquire, reset_for_tests,
        )
        reset_for_tests()
        configure("q", 2)
        acquire("q")
        acquire("q")
        ok, _ = acquire("q")
        assert not ok


class TestR316Deadline:
    def test_propagation(self):
        from aria.security.rounds.r316_timeout_cascade import (
            set_deadline, deadline_for_subcall, clear_deadline, is_expired,
        )
        set_deadline(0.5)
        ok, sec = deadline_for_subcall()
        assert ok and sec > 0
        assert not is_expired()
        clear_deadline()


class TestR317HealthSplit:
    def test_split(self):
        from aria.security.rounds.r317_health_split import (
            register_liveness, register_readiness,
            evaluate_liveness, evaluate_readiness, reset_for_tests,
        )
        reset_for_tests()
        register_liveness("self", lambda: (True, "ok"))
        register_readiness("db", lambda: (False, "down"))
        live, _ = evaluate_liveness()
        ready, _ = evaluate_readiness()
        assert live and not ready


class TestR318GameDay:
    def test_unregistered_dep(self):
        from aria.security.rounds.r318_dependency_outage_sim import (
            simulate_outage, reset_for_tests,
        )
        reset_for_tests()
        ok, why = simulate_outage("unknown", "timeout")
        assert (not ok) and "unregistered" in why


class TestR319DR:
    def test_never_tested(self):
        from aria.security.rounds.r319_dr_audit import DRDescriptor, audit_dr_state
        ok, issues = audit_dr_state(
            {"db": DRDescriptor(system="db", rto_seconds=300, rpo_seconds=60)}
        )
        assert (not ok) and any("never_tested" in i for i in issues)


class TestR320Failover:
    def test_never_drilled(self):
        from aria.security.rounds.r320_multi_region_failover import (
            RegionState, can_initiate_failover,
        )
        ok, why = can_initiate_failover(RegionState(region="us-east-2", role="secondary"))
        assert (not ok) and "never_drilled" in why


class TestR321REDMetrics:
    def test_saturation_alert(self):
        from aria.security.rounds.r321_red_metrics import (
            record_request, evaluate, reset_for_tests,
        )
        reset_for_tests()
        for _ in range(50):
            record_request("svc", success=False, duration_ms=5000)
        healthy, info = evaluate("svc", error_rate_threshold=0.1, p99_threshold_ms=1000)
        assert (not healthy) and info["error_rate"] > 0.5


# Block HH (R322-R331) — Threat intel


class TestR322ATTACK:
    def test_lookup(self):
        from aria.security.rounds.r322_attack_mapping import techniques_for_round
        techs = techniques_for_round("R132")
        assert any("T1190" in t[1] for t in techs)


class TestR323Sigma:
    def test_match_contains(self):
        from aria.security.rounds.r323_sigma_engine import evaluate_rule
        rule = {"detection": {"sel": {"action|contains": "delete"}, "condition": "sel"}}
        assert evaluate_rule(rule, {"action": "delete_user"})
        assert not evaluate_rule(rule, {"action": "view"})


class TestR324STIX:
    def test_parse_indicator(self):
        from aria.security.rounds.r324_stix_taxii import parse_stix_bundle
        body = (
            b'{"type":"bundle","objects":['
            b'{"type":"indicator","id":"indicator--1","pattern":"[ipv4-addr:value = \'1.2.3.4\']"}'
            b']}'
        )
        ok, indicators = parse_stix_bundle(body)
        assert ok and indicators[0]["kind"] == "ipv4-addr" and indicators[0]["value"] == "1.2.3.4"


class TestR325YARALite:
    def test_or_condition(self):
        from aria.security.rounds.r325_yara_lite import match_rule
        rule = {"strings": {"a": '"malware"', "b": '"badness"'}, "condition": "$a or $b"}
        ok, matches = match_rule(b"contains malware here", rule)
        assert ok and "a" in matches


class TestR326Diamond:
    def test_make_event(self):
        from aria.security.rounds.r326_diamond_model import make_event, canonical_json
        e = make_event(adversary="A", capability="B", infrastructure="C", victim="D")
        j = canonical_json(e)
        assert '"adversary": "A"' in j


class TestR327TLP:
    def test_red_to_clear_blocked(self):
        from aria.security.rounds.r327_tlp_tagging import can_share, tag_outgoing
        ok, _ = can_share("RED", "CLEAR")
        assert not ok
        # Same-level allowed
        ok2, _ = can_share("AMBER", "AMBER")
        assert ok2
        assert "TLP:RED" in tag_outgoing("hi", "RED")


class TestR328APT:
    def test_top_match(self):
        from aria.security.rounds.r328_apt_fingerprint import top_match
        group, score = top_match(["T1133", "T1059.003", "T1003"])
        assert "Volt_Typhoon" in group and score > 0.2


class TestR329TTPClustering:
    def test_two_clusters(self):
        from aria.security.rounds.r329_ttp_clustering import cluster_events
        events = [
            {"id": 1, "techniques": ["T1190", "T1059"]},
            {"id": 2, "techniques": ["T1190", "T1059"]},
            {"id": 3, "techniques": ["T1486", "T1485"]},
        ]
        clusters = cluster_events(events, similarity_threshold=0.5)
        assert len(clusters) == 2


class TestR330Pyramid:
    def test_classify_ttp(self):
        from aria.security.rounds.r330_pyramid_of_pain import classify_indicator
        kind, level, weight = classify_indicator("T1190")
        assert kind == "ttp" and level == 6 and weight == 1.0


class TestR331FeedFreshness:
    def test_never_refreshed_flagged(self):
        from aria.security.rounds.r331_intel_freshness import (
            register_feed, audit_feed_freshness, reset_for_tests,
        )
        reset_for_tests()
        register_feed("kev")
        ok, _ = audit_feed_freshness()
        assert not ok


# Block II (R332-R341) — Deepfake / synthetic media


class TestR332DeepfakeVideo:
    def test_quiet_face_motion(self):
        from aria.security.rounds.r332_deepfake_video import FrameMetadata, score_video_metadata
        frames = [
            FrameMetadata(i, 800, i % 30 == 0, motion_vector_count=10, face_region_motion=0)
            for i in range(60)
        ]
        score, _ = score_video_metadata(frames)
        assert score >= 0.3


class TestR333AIText:
    def test_high_score_on_stylised(self):
        from aria.security.rounds.r333_ai_text_detect import score_ai_text
        sent = "This sentence has eight words for testing — fine"
        body = (sent + ". ") * 12
        score, _ = score_ai_text(body)
        assert score >= 0.25


class TestR334VoiceDeepfake:
    def test_clean_background(self):
        from aria.security.rounds.r334_voice_deepfake import CallSegment, score_call
        segs = [
            CallSegment(duration_ms=10_000, rms_db=-20.0, pause_count=0,
                        bandwidth_hz=4000, background_noise_db=-70.0)
            for _ in range(5)
        ]
        score, _ = score_call(segs)
        assert score >= 0.5


class TestR335C2PA:
    def test_no_signature(self):
        from aria.security.rounds.r335_c2pa import audit_c2pa_manifest
        try:
            import cbor2
        except ImportError:
            pytest.skip("cbor2 missing")
        bad = cbor2.dumps({"format": "c2pa", "ingredients": []})
        ok, why = audit_c2pa_manifest(bad)
        assert (not ok) and "signature" in why


class TestR336Liveness:
    def test_low_pad_blocked(self):
        from aria.security.rounds.r336_liveness import LivenessResult, gate_liveness_session
        ok, _ = gate_liveness_session(LivenessResult(vendor="x", pad_level=1, score=0.5))
        assert not ok


class TestR337SyntheticID:
    def test_high_score(self):
        from aria.security.rounds.r337_synthetic_id import OnboardingSignals, score_synthetic_identity
        score, _ = score_synthetic_identity(OnboardingSignals(
            name_dob_consistent_with_ssn=False,
            bureau_records_count=1,
            device_shared_with_known_fraud=True,
        ))
        assert score >= 0.7


class TestR338PDFForgery:
    def test_incremental_updates(self):
        from aria.security.rounds.r338_pdf_forgery import audit_pdf_structure
        bad = b"%PDF-1.4\n/Producer (Evilware Pro)\n%%EOF\n%%EOF\n"
        ok, _ = audit_pdf_structure(bad)
        assert not ok


class TestR339Watermark:
    def test_ai_marker_detected(self):
        from aria.security.rounds.r339_image_watermark import is_ai_generated
        assert is_ai_generated({"iptc:digitalSourceType": "trainedAlgorithmicMedia"})


class TestR340AICode:
    def test_idealised_docstrings(self):
        from aria.security.rounds.r340_ai_code_detect import score_python_file
        body = '''
def alpha(a, b):
    """Compute alpha.

    Args:
        a: first parameter.
        b: second parameter.

    Returns:
        The alpha result.
    """
    return a + b


def beta(a, b):
    """Compute beta.

    Args:
        a: first parameter.
        b: second parameter.

    Returns:
        The beta result.
    """
    return a * b


def gamma(a, b):
    """Compute gamma.

    Args:
        a: first parameter.
        b: second parameter.

    Returns:
        The gamma result.
    """
    return a - b


def delta(a, b):
    """Compute delta.

    Args:
        a: first parameter.
        b: second parameter.

    Returns:
        The delta result.
    """
    return a / b
'''
        score, _ = score_python_file(body)
        assert score >= 0.3


class TestR341ReverseImage:
    def test_round_trip(self):
        from aria.security.rounds.r341_reverse_image import (
            add_known_suspect, lookup_known_image, reset_for_tests,
        )
        reset_for_tests()
        add_known_suspect(b"x")
        found, dist = lookup_known_image(b"x")
        assert found and dist == 0


# Block JJ (R342-R351) — Final consolidation + capstone v7


class TestR342Orchestrator:
    def test_render_consolidated(self):
        from aria.security.rounds.r342_runner_orchestrator import (
            ConsolidatedReport, render_consolidated,
        )
        report = ConsolidatedReport()
        report.per_runner["R51"] = {"caught": 5, "total": 5, "error": ""}
        out = render_consolidated(report)
        assert "R51" in out


class TestR343Coverage:
    def test_coverage_lookup(self):
        from aria.security.rounds.r343_coverage_map import coverage_for_class, single_point_classes
        rounds = coverage_for_class("supply_chain")
        assert "R41" in rounds
        spof = single_point_classes()
        assert isinstance(spof, list)


class TestR344DefenseInDepth:
    def test_audit_high_bar(self):
        from aria.security.rounds.r344_defense_in_depth import audit_defense_in_depth
        ok, weak = audit_defense_in_depth(min_layers=20)
        assert not ok


class TestR345PolicyBundle:
    def test_build_bundle(self):
        from aria.security.rounds.r345_policy_bundle import build_bundle
        bundle = build_bundle()
        assert bundle.fragments and bundle.sha256


class TestR346ThreatModelRefresh:
    def test_overdue(self):
        from aria.security.rounds.r346_threat_model_refresh import (
            register_domain, audit_freshness, reset_for_tests,
        )
        reset_for_tests()
        register_domain("auth")
        ok, _ = audit_freshness()
        assert not ok


class TestR347BugBounty:
    def test_invalid_severity(self):
        from aria.security.rounds.r347_bug_bounty import submit_report, reset_for_tests
        reset_for_tests()
        rec, _ = submit_report(submission_id="b1", severity="invalid",
                               title="x", summary="y" * 50)
        assert (not rec.accepted) and "invalid_severity" in rec.rejection_reason


class TestR348CVD:
    def test_skip_state_blocked(self):
        from aria.security.rounds.r348_coordinated_disclosure import (
            open_finding, advance_state, reset_for_tests,
        )
        reset_for_tests()
        open_finding("f1")
        advance_state("f1", "acknowledged")
        ok, why = advance_state("f1", "disclosed")
        assert (not ok) and "skip" in why


class TestR349CVSS:
    def test_critical(self):
        from aria.security.rounds.r349_cvss import CVSSv31Base, base_score, severity_band
        score, vector = base_score(CVSSv31Base(av="N", ac="L", pr="N", ui="N",
                                                s="U", c="H", i="H", a="H"))
        assert score >= 9.0 and severity_band(score) == "critical"
        assert "AV:N" in vector


class TestR350APIStability:
    def test_audit_passes(self):
        from aria.security.rounds.r350_api_stability import audit_api_surface
        ok, issues = audit_api_surface()
        assert ok, issues


class TestR351RunnerV7:
    def test_full_sweep(self):
        from aria.security.rounds.r351_adversarial_runner_v7 import run_v7, render_v7
        report = run_v7()
        assert report.passed, render_v7(report)
        assert report.caught >= 30
