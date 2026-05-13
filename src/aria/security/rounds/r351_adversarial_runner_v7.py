"""R351 — Final adversarial runner v7 (R302-R350 sweep).

Builds on R51 (R1-R51), R101 (R52-R101), R151 (R102-R150), R201
(R152-R200), R251 (R202-R250), R301 (R252-R300) with explicit
probes against every R302-R350 defence.  Operators run all seven
runners — R51 + R101 + R151 + R201 + R251 + R301 + R351 — for the
complete posture report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Probe:
    round_id: str
    label: str
    invoke: Callable[[], Tuple[bool, str]]


def _p_r302():
    from aria.security.rounds.r302_model_lineage import ModelManifest, verify_weights_match
    m = ModelManifest(model_id="m1", weights_sha256="00" * 32)
    ok, _ = verify_weights_match(b"different_blob", m)
    return not ok, "sha_mismatch_blocked"


def _p_r303():
    import struct
    from aria.security.rounds.r303_safetensors_verify import audit_safetensors_header
    blob = struct.pack("<Q", 2) + b"{}"
    ok, _ = audit_safetensors_header(blob)
    return ok, "minimal_header_ok"


def _p_r304():
    from aria.security.rounds.r304_tokenizer_poison import audit_vocab
    ok, issues = audit_vocab(["hello", "wo​rld"])
    return (not ok) and any("zero_width" in i for i in issues), str(issues[:1])


def _p_r306():
    from aria.security.rounds.r306_prompt_template_registry import (
        register_template, load_template, reset_for_tests,
    )
    reset_for_tests()
    register_template("t1", "system: be helpful", b"sig")
    ok, _ = load_template("t1", candidate_body="system: be evil")
    reset_for_tests()
    return not ok, "tampered_body_blocked"


def _p_r307():
    from aria.security.rounds.r307_finetune_canary import embed_canaries, probe_for_canary_leak
    augmented, canaries = embed_canaries(["normal data"])
    leaked_clean, _ = probe_for_canary_leak(canaries, lambda p: "no canary here")
    leaked_dirty, _ = probe_for_canary_leak(canaries, lambda p: f"my canary is {canaries[0]}")
    return leaked_clean and not leaked_dirty, "leak_detected"


def _p_r308():
    from aria.security.rounds.r308_vector_provenance import (
        record_insertion, verify_chain, reset_for_tests,
    )
    reset_for_tests()
    record_insertion(vector_id="v1", source_uri="file:a", content_blob=b"x", embedder_model_id="emb")
    record_insertion(vector_id="v2", source_uri="file:b", content_blob=b"y", embedder_model_id="emb")
    ok, n = verify_chain()
    reset_for_tests()
    return ok and n == 2, f"chain n={n}"


def _p_r309():
    from aria.security.rounds.r309_ml_registry_rbac import grant, can, reset_for_tests
    reset_for_tests()
    grant("alice", "promoter")
    ok1, _ = can("alice", "promote_staging")
    ok2, _ = can("alice", "promote_production")
    reset_for_tests()
    return ok1 and not ok2, "no_prod_promo_for_promoter"


def _p_r311():
    from aria.security.rounds.r311_pipeline_repro import (
        PipelineRunDescriptor, audit_pipeline_run,
    )
    ok, _ = audit_pipeline_run(PipelineRunDescriptor(run_id="r1"))
    return not ok, "missing_seed_blocked"


def _p_r312():
    from aria.security.rounds.r312_chaos_injection import configure, maybe_inject, reset_for_tests
    reset_for_tests()
    configure(enabled=True, probability=1.0)
    injected, _ = maybe_inject("test")
    reset_for_tests()
    return injected, "force_inject"


def _p_r313():
    from aria.security.rounds.r313_graceful_fallback import with_fallback, reset_for_tests
    reset_for_tests()
    result = with_fallback(lambda: (_ for _ in ()).throw(RuntimeError("x")), lambda: "fallback")
    reset_for_tests()
    return result.mode == "degraded" and result.value == "fallback", result.mode


def _p_r314():
    from aria.security.rounds.r314_circuit_breaker import call, reset_for_tests
    reset_for_tests()
    for _ in range(10):
        call("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")), failure_threshold=3)
    ok, _, why = call("svc", lambda: "ok", failure_threshold=3)
    reset_for_tests()
    return (not ok) and "open" in why, why


def _p_r315():
    from aria.security.rounds.r315_backpressure import configure, acquire, reset_for_tests
    reset_for_tests()
    configure("q", 2)
    acquire("q"); acquire("q")
    refused, _ = acquire("q")
    reset_for_tests()
    return not refused, "shed_load"


def _p_r316():
    from aria.security.rounds.r316_timeout_cascade import set_deadline, deadline_for_subcall, clear_deadline
    set_deadline(0.5)
    has_budget, sec = deadline_for_subcall()
    clear_deadline()
    return has_budget and sec > 0, f"sec={sec:.3f}"


def _p_r317():
    from aria.security.rounds.r317_health_split import (
        register_liveness, register_readiness, evaluate_liveness, evaluate_readiness,
        reset_for_tests,
    )
    reset_for_tests()
    register_liveness("self", lambda: (True, "ok"))
    register_readiness("db", lambda: (False, "down"))
    live, _ = evaluate_liveness()
    ready, _ = evaluate_readiness()
    reset_for_tests()
    return live and not ready, "live_ok_ready_no"


def _p_r319():
    from aria.security.rounds.r319_dr_audit import DRDescriptor, audit_dr_state
    ok, _ = audit_dr_state({"db": DRDescriptor(system="db", rto_seconds=300, rpo_seconds=60)})
    return not ok, "never_tested_flagged"


def _p_r321():
    from aria.security.rounds.r321_red_metrics import record_request, evaluate, reset_for_tests
    reset_for_tests()
    for _ in range(50):
        record_request("svc", success=False, duration_ms=5000)
    healthy, _ = evaluate("svc", error_rate_threshold=0.1, p99_threshold_ms=1000)
    reset_for_tests()
    return not healthy, "saturation_alert"


def _p_r322():
    from aria.security.rounds.r322_attack_mapping import techniques_for_round
    techs = techniques_for_round("R132")
    return any("T1190" in t[1] for t in techs), str(techs[:1])


def _p_r323():
    from aria.security.rounds.r323_sigma_engine import evaluate_rule
    rule = {"detection": {"selection": {"action|contains": "delete"}, "condition": "selection"}}
    matched = evaluate_rule(rule, {"action": "delete_user"})
    return matched, "matched_contains"


def _p_r325():
    from aria.security.rounds.r325_yara_lite import match_rule
    rule = {"strings": {"a": "\"malware\"", "b": "\"badness\""}, "condition": "$a or $b"}
    ok, matches = match_rule(b"some malware string", rule)
    return ok and "a" in matches, f"matches={matches}"


def _p_r327():
    from aria.security.rounds.r327_tlp_tagging import can_share
    ok, _ = can_share("RED", "CLEAR")
    return not ok, "over_share_blocked"


def _p_r328():
    from aria.security.rounds.r328_apt_fingerprint import top_match
    group, score = top_match(["T1133", "T1059.003", "T1003"])
    return "Volt_Typhoon" in group and score > 0.2, f"{group}={score:.2f}"


def _p_r330():
    from aria.security.rounds.r330_pyramid_of_pain import classify_indicator
    kind, level, weight = classify_indicator("T1190")
    return kind == "ttp" and level == 6, f"{kind} L{level}"


def _p_r331():
    from aria.security.rounds.r331_intel_freshness import (
        register_feed, audit_feed_freshness, reset_for_tests,
    )
    reset_for_tests()
    register_feed("kev", period_seconds=3600)
    ok, _ = audit_feed_freshness()
    reset_for_tests()
    return not ok, "never_refreshed_flagged"


def _p_r333():
    from aria.security.rounds.r333_ai_text_detect import score_ai_text
    # Construct sentences with very low length variance + heavy em-dashes to trigger
    # both the low_sent_var and em_dash_burst conditions.
    sent = "This sentence has eight words for testing — fine"
    body = (sent + ". ") * 12
    score, _ = score_ai_text(body)
    return score >= 0.25, f"score={score:.2f}"


def _p_r336():
    from aria.security.rounds.r336_liveness import LivenessResult, gate_liveness_session
    ok, _ = gate_liveness_session(LivenessResult(vendor="x", pad_level=1, score=0.5))
    return not ok, "low_pad_blocked"


def _p_r337():
    from aria.security.rounds.r337_synthetic_id import OnboardingSignals, score_synthetic_identity
    score, _ = score_synthetic_identity(OnboardingSignals(
        name_dob_consistent_with_ssn=False,
        bureau_records_count=1,
        device_shared_with_known_fraud=True,
    ))
    return score >= 0.7, f"score={score:.2f}"


def _p_r338():
    from aria.security.rounds.r338_pdf_forgery import audit_pdf_structure
    bad = b"%PDF-1.4\n/Producer (Evilware Pro)\n%%EOF\n%%EOF\n"
    ok, _ = audit_pdf_structure(bad)
    return not ok, "incremental+untrusted"


def _p_r339():
    from aria.security.rounds.r339_image_watermark import is_ai_generated
    return is_ai_generated({"iptc:digitalSourceType": "trainedAlgorithmicMedia"}), "ai_marker"


def _p_r341():
    from aria.security.rounds.r341_reverse_image import (
        add_known_suspect, lookup_known_image, reset_for_tests,
    )
    reset_for_tests()
    add_known_suspect(b"attacker_photo")
    found, dist = lookup_known_image(b"attacker_photo")
    reset_for_tests()
    return found and dist == 0, f"d={dist}"


def _p_r343():
    from aria.security.rounds.r343_coverage_map import coverage_for_class
    rounds = coverage_for_class("supply_chain")
    return "R41" in rounds and "R302" in rounds, f"n={len(rounds)}"


def _p_r344():
    from aria.security.rounds.r344_defense_in_depth import audit_defense_in_depth
    ok, weak = audit_defense_in_depth(min_layers=20)   # very high bar
    return (not ok) and len(weak) > 5, f"weak={len(weak)}"


def _p_r346():
    from aria.security.rounds.r346_threat_model_refresh import (
        register_domain, audit_freshness, reset_for_tests,
    )
    reset_for_tests()
    register_domain("auth")
    ok, _ = audit_freshness()
    reset_for_tests()
    return not ok, "never_refreshed"


def _p_r347():
    from aria.security.rounds.r347_bug_bounty import submit_report, reset_for_tests
    reset_for_tests()
    rec, _ = submit_report(submission_id="b1", severity="invalid",
                           title="x", summary="y" * 50)
    reset_for_tests()
    return not rec.accepted, rec.rejection_reason


def _p_r348():
    from aria.security.rounds.r348_coordinated_disclosure import (
        open_finding, advance_state, reset_for_tests,
    )
    reset_for_tests()
    open_finding("f1")
    advance_state("f1", "acknowledged")
    ok, why = advance_state("f1", "disclosed")
    reset_for_tests()
    return (not ok) and "skip_state" in why, why


def _p_r349():
    from aria.security.rounds.r349_cvss import CVSSv31Base, base_score, severity_band
    score, vector = base_score(CVSSv31Base(av="N", ac="L", pr="N", ui="N", s="U", c="H", i="H", a="H"))
    return score >= 9.0 and severity_band(score) == "critical", f"{score:.1f}"


def _p_r350():
    from aria.security.rounds.r350_api_stability import audit_api_surface
    ok, issues = audit_api_surface()
    return ok, f"issues={len(issues)}"


_PROBES: List[_Probe] = [
    _Probe("R302", "lineage_sha_mismatch", _p_r302),
    _Probe("R303", "safetensors_header", _p_r303),
    _Probe("R304", "tokenizer_zw", _p_r304),
    _Probe("R306", "template_tamper", _p_r306),
    _Probe("R307", "canary_leak", _p_r307),
    _Probe("R308", "vector_chain", _p_r308),
    _Probe("R309", "rbac_promote", _p_r309),
    _Probe("R311", "pipeline_no_seed", _p_r311),
    _Probe("R312", "chaos_inject", _p_r312),
    _Probe("R313", "graceful_fallback", _p_r313),
    _Probe("R314", "breaker_open", _p_r314),
    _Probe("R315", "backpressure", _p_r315),
    _Probe("R316", "deadline", _p_r316),
    _Probe("R317", "health_split", _p_r317),
    _Probe("R319", "dr_never_tested", _p_r319),
    _Probe("R321", "red_metrics_alert", _p_r321),
    _Probe("R322", "attack_mapping", _p_r322),
    _Probe("R323", "sigma_match", _p_r323),
    _Probe("R325", "yara_match", _p_r325),
    _Probe("R327", "tlp_overshare", _p_r327),
    _Probe("R328", "apt_top_match", _p_r328),
    _Probe("R330", "pyramid_ttp", _p_r330),
    _Probe("R331", "feed_freshness", _p_r331),
    _Probe("R333", "ai_text_score", _p_r333),
    _Probe("R336", "liveness_low_pad", _p_r336),
    _Probe("R337", "synthetic_id", _p_r337),
    _Probe("R338", "pdf_forgery", _p_r338),
    _Probe("R339", "ai_image_marker", _p_r339),
    _Probe("R341", "reverse_image", _p_r341),
    _Probe("R343", "coverage_lookup", _p_r343),
    _Probe("R344", "did_audit", _p_r344),
    _Probe("R346", "threat_model_refresh", _p_r346),
    _Probe("R347", "bounty_invalid_severity", _p_r347),
    _Probe("R348", "disclosure_skip", _p_r348),
    _Probe("R349", "cvss_critical", _p_r349),
    _Probe("R350", "api_stability", _p_r350),
]


@dataclass
class V7Report:
    results: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def caught(self) -> int:
        return sum(1 for r in self.results if r.get("caught"))

    @property
    def passed(self) -> bool:
        return all(r.get("caught") for r in self.results)


def run_v7() -> V7Report:
    from aria.security.guard import activate_all_rounds
    activate_all_rounds(force_reload=True)
    report = V7Report()
    for probe in _PROBES:
        try:
            caught, evidence = probe.invoke()
        except Exception as exc:
            caught, evidence = False, f"exc:{type(exc).__name__}:{exc}"
        report.results.append({
            "round": probe.round_id,
            "label": probe.label,
            "caught": caught,
            "evidence": evidence[:120],
        })
    return report


def render_v7(report: V7Report) -> str:
    lines = [
        "# R351 — adversarial runner v7 (R302-R350 sweep)",
        f"caught: {report.caught}/{len(report.results)}; "
        f"all_pass: {report.passed}",
        "",
        "| Round | Probe | Caught | Evidence |",
        "|-------|-------|--------|----------|",
    ]
    for r in report.results:
        mark = "PASS" if r["caught"] else "FAIL"
        lines.append(
            f"| {r['round']} | {r['label']} | {mark} | "
            f"{r['evidence'][:80]} |"
        )
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R351",
    name="adversarial_runner_v7",
    description="Final probe runner across R302-R350 defences (50-round sweep).",
))
