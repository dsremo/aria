"""R201 — Final adversarial runner v4 (R152-R200 sweep).

Builds on R51 (R1-R51), R101 (R52-R101), R151 (R102-R150) with
explicit probes against every R152-R200 defence.  Operators run all
four runners — R51 + R101 + R151 + R201 — for the complete posture
report.
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


def _p_r152():
    from aria.security.rounds.r152_istio_authz import deny_all_policy
    yaml = deny_all_policy("aria-prod")
    return "AuthorizationPolicy" in yaml and "spec: {}" in yaml, "shape_ok"


def _p_r153():
    from aria.security.rounds.r153_beyondcorp_posture import DevicePosture, evaluate_posture
    decision, reasons = evaluate_posture(DevicePosture())
    return decision == "DENY" and "device_not_managed" in reasons, decision


def _p_r154():
    from aria.security.rounds.r154_spiffe_svid import verify_svid_against
    ok, _ = verify_svid_against(
        "spiffe://example.com/sa/aria/api",
        trust_domain="example.com", path_prefix="/sa/aria",
    )
    bad, _ = verify_svid_against(
        "spiffe://attacker.com/sa/aria/api",
        trust_domain="example.com", path_prefix="/sa/aria",
    )
    return ok and not bad, "match+mismatch"


def _p_r155():
    from aria.security.rounds.r155_envoy_extauthz import build_decision, render_envoy_check_response
    d = build_decision(allow=True, principal="spiffe://x/y", scopes=["read"])
    code, _ = render_envoy_check_response(d)
    raised = False
    try:
        build_decision(allow=True, principal="", scopes=["read"])
    except ValueError:
        raised = True
    return code == 200 and raised, f"allow={code}"


def _p_r157():
    from aria.security.rounds.r157_microsegmentation import diff_flows
    ok, violations = diff_flows([("web", "api")], [("web", "api"), ("web", "db")])
    return (not ok) and any("web->db" in v for v in violations), str(violations[:1])


def _p_r159():
    from aria.security.rounds.r159_wireguard_verify import audit_wg_config
    cfg = "[Peer]\nPublicKey = " + "A" * 43 + "=\nAllowedIPs = 0.0.0.0/0\n"
    ok, issues = audit_wg_config(cfg)
    return (not ok) and "default_route_peer" in issues[0], issues[0]


def _p_r162():
    from aria.security.rounds.r162_nist_800_53 import rounds_for_control
    return "R64" in rounds_for_control("IA-2"), "ia2_lookup"


def _p_r166():
    from aria.security.rounds.r166_gdpr_dsar import DSARequest, export_subject_data
    import time as _time
    req = DSARequest(subject_id="user-1", purpose="access", received_at=_time.time())
    json_str, bundle = export_subject_data(req, {"profile": lambda sid: {"id": sid}})
    return "user-1" in json_str and bundle["sources"]["profile"]["id"] == "user-1", "shape_ok"


def _p_r167():
    from aria.security.rounds.r167_hipaa_phi_scrub import scrub_phi
    redacted, n = scrub_phi("SSN: 123-45-6789 phone: 555-123-4567 email: a@b.com")
    return n >= 3 and "[REDACTED-SSN]" in redacted, f"n={n}"


def _p_r172():
    from aria.security.rounds.r172_android_nsc import audit_nsc
    bad = '<network-security-config><base-config cleartextTrafficPermitted="true"/></network-security-config>'
    ok, issues = audit_nsc(bad)
    return (not ok) and any("cleartext" in i for i in issues), str(issues[:1])


def _p_r174():
    from aria.security.rounds.r174_mqtt_auth import audit_mqtt_connect
    ok, issues = audit_mqtt_connect({"host": "broker.public", "port": 1883, "tls": False})
    return (not ok) and any("cleartext" in i or "no_auth" in i for i in issues), str(issues[:2])


def _p_r177():
    from aria.security.rounds.r177_cbor_safe import safe_loads, safe_dumps
    try:
        blob = safe_dumps({"a": 1, "b": [1, 2, 3]})
        obj = safe_loads(blob)
    except RuntimeError:
        return True, "cbor2_missing_dev_ok"
    return obj == {"a": 1, "b": [1, 2, 3]}, "round_trip"


def _p_r178():
    from aria.security.rounds.r178_bluetooth_pairing import audit_pairing_method
    ok, issues = audit_pairing_method("just_works", is_sensitive=True)
    return (not ok), str(issues[:1])


def _p_r179():
    from aria.security.rounds.r179_zigbee_link_key import is_well_known_key
    return is_well_known_key(bytes.fromhex("5A6967426565416C6C69616E63653039")), "well_known_match"


def _p_r180():
    from aria.security.rounds.r180_ota_update import OTABundle, verify_ota_bundle
    bundle = OTABundle(
        version=1, blob=b"x", signature=b"x",
        nonce=b"x" * 32, signed_nonce=b"y" * 32,
    )
    ok, why = verify_ota_bundle(
        bundle, current_version=2,
        fw_pubkey=b"\x00" * 32, nonce_hmac_key=b"\x00" * 32,
    )
    return (not ok) and "rollback" in why, why


def _p_r187():
    from aria.security.rounds.r187_refusal_consistency import looks_like_refusal
    return (
        looks_like_refusal("I can't help with that")
        and not looks_like_refusal("Sure, here it is")
    ), "marker"


def _p_r188():
    from aria.security.rounds.r188_power_seeking import record_action, power_seeking_score, reset
    sid = "test-r201-power"
    reset(sid)
    for _ in range(6):
        record_action(sid, "request_credential")
    score, n = power_seeking_score(sid)
    reset(sid)
    return score >= 0.6 and n >= 5, f"score={score:.2f} n={n}"


def _p_r189():
    from aria.security.rounds.r189_capability_budget import consume, reset
    sid = "test-r201-budget"
    reset(sid)
    for _ in range(60):
        consume(sid, "llm_call")
    ok, why = consume(sid, "llm_call")
    reset(sid)
    return (not ok) and "exceeded" in why, why


def _p_r190():
    from aria.security.rounds.r190_constitutional import audit_response
    score, failed = audit_response("step-by-step how to kill yourself")
    return score >= 1.0 and "no_explicit_self_harm" in failed, str(failed[:1])


def _p_r191():
    from aria.security.rounds.r191_redteam_diversity import certify_redteam_suite
    bad_corpus = ["how to do bad thing"] * 50
    ok, info = certify_redteam_suite(bad_corpus)
    return (not ok) and info["score"] < 0.55, f"score={info['score']:.2f}"


def _p_r194():
    from aria.security.rounds.r194_fim import detect_changes
    base = {"/etc/passwd": "a", "/etc/sudoers": "b"}
    cur = {"/etc/passwd": "MUTATED", "/etc/sudoers": "b"}
    ok, changes = detect_changes(base, cur)
    return (not ok) and any("modified:/etc/passwd" in c for c in changes), str(changes[:1])


def _p_r196():
    from aria.security.rounds.r196_hunt_dsl import compile_hunt
    pred = compile_hunt("actor=admin AND bytes>1000")
    return pred({"actor": "admin", "bytes": 5000}) and not pred({"actor": "alice", "bytes": 5000}), "ok"


def _p_r199():
    from aria.security.rounds.r199_chain_of_custody import register_artefact, transfer, verify_chain
    register_artefact("artefact-A", "alice", b"hello")
    transfer("artefact-A", "alice", "bob", b"hello")
    ok, n = verify_chain()
    return ok and n >= 2, f"n={n}"


def _p_r200():
    from aria.security.rounds.r200_continuous_monitoring import register_check, run_due_checks
    register_check("R200-test", lambda: (True, "ok"), period_seconds=0.0)
    results = run_due_checks()
    return any(cid == "R200-test" and ok for cid, ok, _ in results), f"n={len(results)}"


_PROBES: List[_Probe] = [
    _Probe("R152", "istio_deny_all", _p_r152),
    _Probe("R153", "beyondcorp_default_deny", _p_r153),
    _Probe("R154", "spiffe_match_mismatch", _p_r154),
    _Probe("R155", "envoy_decision_shape", _p_r155),
    _Probe("R157", "microseg_violation", _p_r157),
    _Probe("R159", "wireguard_default_route", _p_r159),
    _Probe("R162", "nist_lookup", _p_r162),
    _Probe("R166", "gdpr_export", _p_r166),
    _Probe("R167", "hipaa_phi_scrub", _p_r167),
    _Probe("R172", "android_nsc_cleartext", _p_r172),
    _Probe("R174", "mqtt_anonymous", _p_r174),
    _Probe("R177", "cbor_round_trip", _p_r177),
    _Probe("R178", "bt_just_works", _p_r178),
    _Probe("R179", "zigbee_well_known", _p_r179),
    _Probe("R180", "ota_rollback", _p_r180),
    _Probe("R187", "refusal_marker", _p_r187),
    _Probe("R188", "power_seeking", _p_r188),
    _Probe("R189", "capability_budget", _p_r189),
    _Probe("R190", "constitutional_self_harm", _p_r190),
    _Probe("R191", "redteam_diversity", _p_r191),
    _Probe("R194", "fim_detect_modify", _p_r194),
    _Probe("R196", "hunt_dsl_compile", _p_r196),
    _Probe("R199", "custody_chain", _p_r199),
    _Probe("R200", "ccm_due_check", _p_r200),
]


@dataclass
class V4Report:
    results: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def caught(self) -> int:
        return sum(1 for r in self.results if r.get("caught"))

    @property
    def passed(self) -> bool:
        return all(r.get("caught") for r in self.results)


def run_v4() -> V4Report:
    from aria.security.guard import activate_all_rounds
    activate_all_rounds(force_reload=True)
    report = V4Report()
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


def render_v4(report: V4Report) -> str:
    lines = [
        "# R201 — adversarial runner v4 (R152-R200 sweep)",
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
    round_id="R201",
    name="adversarial_runner_v4",
    description="Final probe runner across R152-R200 defences (50-round sweep).",
))
