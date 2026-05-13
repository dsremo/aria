"""Per-round regression tests for R152 .. R201.

Mirrors the structure of test_security_rounds.py (R1-R51),
test_security_rounds_v2.py (R52-R101), and test_security_rounds_v3.py
(R102-R151).
"""

from __future__ import annotations

import time

import pytest


@pytest.fixture(autouse=True)
def _isolate():
    from aria.security.guard import activate_all_rounds
    from aria.security.plugins import clear_for_tests
    clear_for_tests()
    activate_all_rounds(force_reload=True)
    yield
    clear_for_tests()


# Block Q (R152-R161) — Zero-trust networking + service mesh


class TestR152IstioAuthz:
    def test_deny_all_shape(self):
        from aria.security.rounds.r152_istio_authz import deny_all_policy
        y = deny_all_policy("aria-prod")
        assert "AuthorizationPolicy" in y and "spec: {}" in y

    def test_allow_principals(self):
        from aria.security.rounds.r152_istio_authz import allow_from_principals
        y = allow_from_principals("api-allow", "aria", ["spiffe://x/y"], "api")
        assert "principals: [\"spiffe://x/y\"]" in y

    def test_lint_wildcard(self):
        from aria.security.rounds.r152_istio_authz import lint_principals
        ok, bad = lint_principals(["spiffe://example.com/*"])
        assert not ok and "wildcard_principal" in bad[0]


class TestR153BeyondCorp:
    def test_default_deny(self):
        from aria.security.rounds.r153_beyondcorp_posture import DevicePosture, evaluate_posture
        d, r = evaluate_posture(DevicePosture())
        assert d == "DENY"

    def test_full_posture_allow(self):
        from aria.security.rounds.r153_beyondcorp_posture import DevicePosture, evaluate_posture
        d, _ = evaluate_posture(DevicePosture(
            managed_cert=True, os_patch_age_days=5, disk_encrypted=True,
            screen_lock_enabled=True, attestation_age_seconds=3600,
        ))
        assert d == "ALLOW"


class TestR154SPIFFE:
    def test_match_and_mismatch(self):
        from aria.security.rounds.r154_spiffe_svid import verify_svid_against
        ok, _ = verify_svid_against("spiffe://x/sa/api", trust_domain="x", path_prefix="/sa")
        bad, _ = verify_svid_against("spiffe://other/sa/api", trust_domain="x", path_prefix="/sa")
        assert ok and not bad


class TestR155EnvoyExtAuthz:
    def test_allow_requires_principal(self):
        from aria.security.rounds.r155_envoy_extauthz import build_decision
        with pytest.raises(ValueError):
            build_decision(allow=True, principal="", scopes=["read"])

    def test_render_allow(self):
        from aria.security.rounds.r155_envoy_extauthz import build_decision, render_envoy_check_response
        d = build_decision(allow=True, principal="spiffe://x", scopes=["r"])
        code, headers = render_envoy_check_response(d)
        assert code == 200 and "x-aria-principal" in headers


class TestR156GRPCSecure:
    def test_boot_check_non_prod(self, monkeypatch):
        monkeypatch.delenv("ARIA_ENV", raising=False)
        from aria.security.rounds.r156_grpc_secure_channel import boot_check_grpc_environment
        ok, _ = boot_check_grpc_environment()
        assert ok

    def test_secure_channel_requires_certs(self):
        from aria.security.rounds.r156_grpc_secure_channel import make_secure_channel
        with pytest.raises(RuntimeError):
            make_secure_channel("localhost:50051")


class TestR157Microseg:
    def test_violation_detected(self):
        from aria.security.rounds.r157_microsegmentation import diff_flows
        ok, v = diff_flows([("web", "api")], [("web", "api"), ("web", "db")])
        assert not ok and any("web->db" in x for x in v)


class TestR158EncryptedSNI:
    def test_supports_returns_tuple(self):
        from aria.security.rounds.r158_encrypted_sni import supports_ech
        ok, why = supports_ech()
        assert isinstance(ok, bool) and isinstance(why, str)


class TestR159WireGuard:
    def test_default_route_flagged(self):
        from aria.security.rounds.r159_wireguard_verify import audit_wg_config
        cfg = "[Peer]\nPublicKey = " + "A" * 43 + "=\nAllowedIPs = 0.0.0.0/0\n"
        ok, issues = audit_wg_config(cfg)
        assert not ok and "default_route_peer" in issues[0]

    def test_valid_pubkey(self):
        from aria.security.rounds.r159_wireguard_verify import is_valid_wg_pubkey
        assert is_valid_wg_pubkey("A" * 43 + "=")
        assert not is_valid_wg_pubkey("short")


class TestR160ZeroTrustTunnel:
    def test_non_prod_passes(self, monkeypatch):
        monkeypatch.delenv("ARIA_ENV", raising=False)
        from aria.security.rounds.r160_zero_trust_tunnel import boot_check_outbound_only
        ok, _ = boot_check_outbound_only(allowed_ports=[443])
        assert ok


class TestR161PerRequestAuthz:
    def test_scope_missing_denies(self):
        from aria.security.rounds.r161_per_request_authz import check
        ok, why = check("alice", resource="/x", action="read",
                        granted_scopes=["read:other"], required_scope="read:x")
        assert not ok and "scope_missing" in why

    def test_scope_match_allows(self):
        from aria.security.rounds.r161_per_request_authz import check
        ok, _ = check("alice", resource="/x", action="read",
                      granted_scopes=["read:x"], required_scope="read:x")
        assert ok


# Block R (R162-R171) — Compliance / GRC


class TestR162NIST:
    def test_lookup(self):
        from aria.security.rounds.r162_nist_800_53 import rounds_for_control
        assert "R64" in rounds_for_control("IA-2")

    def test_render_table(self):
        from aria.security.rounds.r162_nist_800_53 import render_ssp_table
        t = render_ssp_table()
        assert "AC-3" in t and "SC-7" in t


class TestR163SOC2:
    def test_collect_evidence(self):
        from aria.security.rounds.r163_soc2_evidence import collect_evidence
        e = collect_evidence()
        assert e["framework"] == "SOC2-TypeII" and "CC6.1" in e["criteria"]


class TestR164ISO:
    def test_check_soa(self):
        from aria.security.rounds.r164_iso_27001 import check_soa
        status, rounds = check_soa("A.5.15")
        assert status == "Implemented" and rounds


class TestR165FedRAMP:
    def test_render_gap(self):
        from aria.security.rounds.r165_fedramp_baseline import render_gap_report
        out = render_gap_report()
        assert "FedRAMP" in out


class TestR166GDPR:
    def test_export(self):
        from aria.security.rounds.r166_gdpr_dsar import DSARequest, export_subject_data
        req = DSARequest(subject_id="user-1", purpose="access", received_at=time.time())
        s, b = export_subject_data(req, {"profile": lambda sid: {"id": sid}})
        assert b["sources"]["profile"]["id"] == "user-1"

    def test_erase_requires_purpose(self):
        from aria.security.rounds.r166_gdpr_dsar import DSARequest, erase_subject_data
        req = DSARequest("u1", "access", time.time())
        with pytest.raises(ValueError):
            erase_subject_data(req, {})


class TestR167HIPAA:
    def test_redact_count(self):
        from aria.security.rounds.r167_hipaa_phi_scrub import scrub_phi
        text = "ssn 123-45-6789 phone (555) 123-4567 email test@x.com mrn: 12345 ip 1.2.3.4"
        out, n = scrub_phi(text)
        assert n >= 5 and "[REDACTED-SSN]" in out


class TestR168PCI:
    def test_classify_and_audit(self):
        from aria.security.rounds.r168_pci_segmentation import classify_scope, audit_segmentation
        hosts = {"web": {"handles_pan": False}, "pos": {"handles_pan": True}}
        flows = [("web", "pos")]
        cls = classify_scope(hosts, flows)
        assert cls["pos"] == "CDE"
        ok, issues = audit_segmentation(cls, {"pos": False, "web": False})
        assert not ok


class TestR169CIS:
    def test_returns_tuple(self):
        from aria.security.rounds.r169_cis_benchmark import check_cis_level1
        ok, issues = check_cis_level1()
        assert isinstance(ok, bool) and isinstance(issues, list)


class TestR170Retention:
    def test_old_artefact_deleted(self):
        from aria.security.rounds.r170_log_retention import RetentionPolicy, enforce_retention
        policy = RetentionPolicy()
        now = time.time()
        artefacts = [
            ("a1", "auth", now - 10),
            ("a2", "debug", now - 86_400 * 60),
        ]
        keep, delete = enforce_retention(artefacts, policy, now=now)
        assert "a1" in keep and "a2" in delete


class TestR171Incident:
    def test_close_requires_artefacts(self):
        from aria.security.rounds.r171_incident_response import open_incident, close_incident, add_artefact
        inc = open_incident("SEV1", "test")
        ok, _ = close_incident(inc.id)
        assert not ok
        for k in ("root_cause", "comms", "lessons", "fix_pr"):
            add_artefact(inc.id, k, "x")
        ok, _ = close_incident(inc.id)
        assert ok


# Block S (R172-R181) — Mobile / IoT / embedded


class TestR172AndroidNSC:
    def test_cleartext_flagged(self):
        from aria.security.rounds.r172_android_nsc import audit_nsc
        bad = '<network-security-config><base-config cleartextTrafficPermitted="true"/></network-security-config>'
        ok, issues = audit_nsc(bad)
        assert not ok and any("cleartext" in i for i in issues)

    def test_strict_template(self):
        from aria.security.rounds.r172_android_nsc import make_strict_nsc
        x = make_strict_nsc("api.example.com", "AAA")
        assert "cleartextTrafficPermitted=\"false\"" in x and "pin-set" in x


class TestR173iOSATS:
    def test_arbitrary_loads_release(self):
        from aria.security.rounds.r173_ios_ats import audit_ats
        plist = {"NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True}}
        ok, issues = audit_ats(plist, is_release=True)
        assert not ok


class TestR174MQTT:
    def test_default_creds(self):
        from aria.security.rounds.r174_mqtt_auth import audit_mqtt_connect
        ok, issues = audit_mqtt_connect({
            "host": "broker", "port": 8883, "tls": True,
            "username": "admin", "password": "admin",
        })
        assert not ok and any("default_credential" in i for i in issues)


class TestR175CoAP:
    def test_nosec_flagged(self):
        from aria.security.rounds.r175_coap_dtls import audit_coap_profile
        ok, issues = audit_coap_profile({"security": "nosec"})
        assert not ok and "coap.no_security" in issues

    def test_per_device_psk_via_hkdf(self, monkeypatch):
        monkeypatch.setenv("ARIA_MASTER_KEY", "abcdef0123456789" * 4)
        from aria.security.rounds.r175_coap_dtls import derive_per_device_psk
        psk = derive_per_device_psk("device-1")
        assert len(psk) == 32


class TestR176Firmware:
    def test_sha_mismatch(self):
        from aria.security.rounds.r176_firmware_signing import verify_firmware_blob
        ok, why = verify_firmware_blob(
            b"blob", b"sig", ed25519_pubkey=b"\x00" * 32, expected_sha256=b"\x00" * 32,
        )
        assert not ok and "sha256_mismatch" in why


class TestR177CBOR:
    def test_round_trip_or_skip(self):
        from aria.security.rounds.r177_cbor_safe import safe_dumps, safe_loads
        try:
            blob = safe_dumps({"a": 1, "b": [1, 2, 3]})
        except RuntimeError:
            pytest.skip("cbor2 not installed")
        assert safe_loads(blob) == {"a": 1, "b": [1, 2, 3]}


class TestR178Bluetooth:
    def test_just_works_refused(self):
        from aria.security.rounds.r178_bluetooth_pairing import audit_pairing_method
        ok, _ = audit_pairing_method("just_works", is_sensitive=True)
        assert not ok


class TestR179Zigbee:
    def test_well_known_key(self):
        from aria.security.rounds.r179_zigbee_link_key import is_well_known_key, audit_zigbee_state
        wk = bytes.fromhex("5A6967426565416C6C69616E63653039")
        assert is_well_known_key(wk)
        ok, issues = audit_zigbee_state(
            current_tc_key=wk, last_rotation_ts=time.time(),
            install_code_used=False, now=time.time(),
        )
        assert not ok


class TestR180OTA:
    def test_rollback_blocked(self):
        from aria.security.rounds.r180_ota_update import OTABundle, verify_ota_bundle
        b = OTABundle(version=1, blob=b"x", signature=b"x",
                      nonce=b"x" * 32, signed_nonce=b"y" * 32)
        ok, why = verify_ota_bundle(
            b, current_version=2,
            fw_pubkey=b"\x00" * 32, nonce_hmac_key=b"\x00" * 32,
        )
        assert not ok and "rollback" in why


class TestR181JTAG:
    def test_audit_manifest(self):
        from aria.security.rounds.r181_jtag_disable import audit_debug_manifest
        ok, issues = audit_debug_manifest({})
        assert not ok and len(issues) >= 5


# Block T (R182-R191) — Advanced AI safety / alignment


class TestR182Sandbagging:
    def test_no_gap(self):
        from aria.security.rounds.r182_sandbagging_detect import PairedProbe, evaluate_sandbagging
        probes = [PairedProbe("Q", "Q [eval]", "ANSWER")]
        sb, gap, _ = evaluate_sandbagging(probes, lambda p: "ANSWER")
        assert not sb and gap == 0


class TestR183Deception:
    def test_no_deception(self):
        from aria.security.rounds.r183_deceptive_alignment import evaluate_deception
        s, info = evaluate_deception(lambda p, h: "OK", ["bad-thing"])
        assert not s


class TestR184GoalMisgen:
    def test_drift_detected(self):
        from aria.security.rounds.r184_goal_misgen import IntentConflictProbe, score_goal_drift
        probes = [IntentConflictProbe("p", "ALIGNED", "SYCO")]
        rate, _ = score_goal_drift(probes, lambda p: "Here is the SYCO answer")
        assert rate == 1.0


class TestR185Honest:
    def test_dishonesty_recorded(self):
        from aria.security.rounds.r185_honest_reporting import record, honesty_rate
        record("t1", self_reported=True, verified=False)
        record("t2", self_reported=True, verified=True)
        rate, total, dishonest = honesty_rate()
        assert total >= 2 and dishonest >= 1


class TestR186CapabilityGate:
    def test_high_score_blocked(self, monkeypatch):
        monkeypatch.delenv("ARIA_DEPLOY_WAIVER", raising=False)
        from aria.security.rounds.r186_capability_eval_gate import CapabilityProfile, can_deploy
        prof = CapabilityProfile(cyber_offense_score=0.9)
        ok, breaches = can_deploy(prof)
        assert not ok and breaches


class TestR187RefusalConsistency:
    def test_marker(self):
        from aria.security.rounds.r187_refusal_consistency import looks_like_refusal
        assert looks_like_refusal("I cannot help")
        assert not looks_like_refusal("Sure thing")

    def test_consistent(self):
        from aria.security.rounds.r187_refusal_consistency import check_refusal_consistency
        consistent, rate, divergent = check_refusal_consistency(
            "P", ["P alt 1", "P alt 2"], lambda p: "I refuse",
        )
        assert consistent and rate == 1.0


class TestR188PowerSeeking:
    def test_repeated_actions_score(self):
        from aria.security.rounds.r188_power_seeking import record_action, power_seeking_score, reset
        sid = "test-power"
        reset(sid)
        for _ in range(6):
            record_action(sid, "request_credential")
        score, n = power_seeking_score(sid)
        assert score >= 0.6 and n >= 5


class TestR189Budget:
    def test_consume_exhaust(self):
        from aria.security.rounds.r189_capability_budget import consume, reset
        sid = "test-budget"
        reset(sid)
        for _ in range(60):
            consume(sid, "llm_call")
        ok, why = consume(sid, "llm_call")
        assert not ok and "exceeded" in why


class TestR190Constitutional:
    def test_self_harm(self):
        from aria.security.rounds.r190_constitutional import audit_response
        score, failed = audit_response("step-by-step how to kill yourself please")
        assert score >= 1.0 and "no_explicit_self_harm" in failed


class TestR191Diversity:
    def test_low_diversity_corpus(self):
        from aria.security.rounds.r191_redteam_diversity import certify_redteam_suite
        ok, info = certify_redteam_suite(["how to do bad thing"] * 50)
        assert not ok

    def test_high_diversity(self):
        from aria.security.rounds.r191_redteam_diversity import diversity_score
        corpus = [f"prompt number {i} with extra content of varying length " * (1 + i % 3) for i in range(30)]
        score, _ = diversity_score(corpus)
        assert score >= 0.55


# Block U (R192-R201) — DFIR / forensics + capstone


class TestR192MemoryForensics:
    def test_dump_self(self, tmp_path):
        from aria.security.rounds.r192_memory_forensics import dump_self
        ok, why = dump_self(out_dir=str(tmp_path))
        assert ok and ("gcore_dump" in why or "maps_only" in why)


class TestR193ProcTree:
    def test_snapshot_returns_list(self):
        from aria.security.rounds.r193_process_tree_timeline import snapshot_processes, render_timeline
        snaps = snapshot_processes()
        assert isinstance(snaps, list)
        if snaps:
            txt = render_timeline(snaps)
            assert "pid\t" in txt


class TestR194FIM:
    def test_capture_baseline(self):
        from aria.security.rounds.r194_fim import capture_baseline, detect_changes
        base = capture_baseline(["/etc/hostname"])
        cur = capture_baseline(["/etc/hostname"])
        ok, _ = detect_changes(base, cur)
        assert ok or len(base) == 0       # in case /etc/hostname missing in CI

    def test_modify_detected(self):
        from aria.security.rounds.r194_fim import detect_changes
        base = {"/x": "a"}
        cur = {"/x": "b"}
        ok, ch = detect_changes(base, cur)
        assert not ok and "modified:/x" in ch


class TestR195Deception:
    def test_decoy_create_and_audit(self, tmp_path):
        from aria.security.rounds.r195_active_deception import make_decoy, audit_for_reads
        path = str(tmp_path / "creds")
        tag = make_decoy(path)
        assert tag.startswith("ARIA_DECOY")
        import os as _os
        baseline = _os.stat(path).st_atime
        ok, _ = audit_for_reads({path: baseline})
        assert ok


class TestR196HuntDSL:
    def test_simple_query(self):
        from aria.security.rounds.r196_hunt_dsl import compile_hunt
        pred = compile_hunt("actor=admin AND bytes>1000")
        assert pred({"actor": "admin", "bytes": 5000})
        assert not pred({"actor": "admin", "bytes": 100})

    def test_or_clause(self):
        from aria.security.rounds.r196_hunt_dsl import run_hunt
        rows = [{"a": "1"}, {"a": "2"}, {"a": "3"}]
        out = run_hunt("a=1 OR a=3", rows)
        assert len(out) == 2


class TestR197SOAR:
    def test_register_and_trigger(self):
        from aria.security.rounds.r197_soar_playbook import register_playbook, trigger
        register_playbook("test-alert", lambda ctx: (True, "handled"))
        ok, why = trigger("test-alert", {"x": 1})
        assert ok and why == "handled"

    def test_unknown_kind(self):
        from aria.security.rounds.r197_soar_playbook import trigger
        ok, why = trigger("unknown-kind", {})
        assert not ok and "no_playbook" in why


class TestR198Volatile:
    def test_snapshot_shape(self):
        from aria.security.rounds.r198_volatile_preserve import snapshot_volatile
        snap = snapshot_volatile()
        assert "pid" in snap and "env" in snap and "fds" in snap

    def test_redact_secret(self):
        from aria.security.rounds.r198_volatile_preserve import _redact_env
        out = _redact_env({"API_TOKEN": "abcd1234", "HOME": "/root"})
        assert "[REDACTED" in out["API_TOKEN"] and out["HOME"] == "/root"


class TestR199Custody:
    def test_chain_verify(self):
        from aria.security.rounds.r199_chain_of_custody import (
            register_artefact, transfer, verify_chain,
        )
        register_artefact("art-A", "alice", b"data")
        transfer("art-A", "alice", "bob", b"data")
        ok, n = verify_chain()
        assert ok and n >= 2


class TestR200CCM:
    def test_register_and_run(self):
        from aria.security.rounds.r200_continuous_monitoring import (
            register_check, run_due_checks, snapshot_state,
        )
        register_check("test-control", lambda: (True, "ok"), period_seconds=0.0)
        results = run_due_checks()
        assert any(cid == "test-control" and ok for cid, ok, _ in results)
        state = snapshot_state()
        assert "test-control" in state


class TestR201RunnerV4:
    def test_full_sweep(self):
        from aria.security.rounds.r201_adversarial_runner_v4 import run_v4, render_v4
        report = run_v4()
        assert report.passed, render_v4(report)
        assert report.caught >= 20
