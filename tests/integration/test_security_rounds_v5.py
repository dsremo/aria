"""Per-round regression tests for R202 .. R251.

Mirrors the structure of test_security_rounds.py (R1-R51),
test_security_rounds_v2.py (R52-R101), test_security_rounds_v3.py
(R102-R151), and test_security_rounds_v4.py (R152-R201).
"""

from __future__ import annotations

import time

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


# Block V (R202-R211) — Quantum-resilient crypto depth


class TestR202MLDSA87:
    def test_keypair_returns_tuple(self):
        from aria.security.rounds.r202_ml_dsa_87 import keypair
        pk, sk, tag = keypair()
        assert tag in ("ml_dsa_87", "ml_dsa_87_alias", "ml_dsa_65_fallback", "unavailable")


class TestR203SLHDSA:
    def test_keypair_returns_tuple(self):
        from aria.security.rounds.r203_slh_dsa import keypair
        pk, sk, tag = keypair("small")
        assert tag in ("SPHINCS+-SHA2-128s-simple", "unavailable")


class TestR204CryptoAgility:
    def test_audit_clean(self):
        from aria.security.rounds.r204_crypto_agility import audit_manifest, render_manifest_md
        ok, _ = audit_manifest()
        assert ok
        md = render_manifest_md()
        assert "audit_seal" in md and "HMAC" in md

    def test_update_role(self):
        from aria.security.rounds.r204_crypto_agility import update_role, audit_manifest
        update_role("legacy_role", "MD5")
        ok, issues = audit_manifest()
        assert (not ok) and any("legacy_role" in i for i in issues)


class TestR205PQHybridTLS:
    def test_supports_returns_bool(self):
        from aria.security.rounds.r205_pq_hybrid_tls import runtime_hybrid_groups_supported
        ok, found = runtime_hybrid_groups_supported()
        assert isinstance(ok, bool) and isinstance(found, list)


class TestR206PQSSH:
    def test_weak_kex_flagged(self):
        from aria.security.rounds.r206_pq_ssh import audit_ssh_kex_line
        ok, _ = audit_ssh_kex_line("KexAlgorithms diffie-hellman-group14-sha1")
        assert not ok

    def test_recommended_first_kex_pq(self):
        from aria.security.rounds.r206_pq_ssh import recommended_kex_line, audit_ssh_kex_line
        rec = recommended_kex_line()
        ok, _ = audit_ssh_kex_line(rec)
        assert ok


class TestR207LatticeProbe:
    def test_returns_tuple(self):
        from aria.security.rounds.r207_lattice_probe import boot_check_lattice_runtime
        ok, why = boot_check_lattice_runtime()
        assert isinstance(ok, bool) and isinstance(why, str)


class TestR208TemplateAttackGuard:
    def test_jitter_call_returns_value(self):
        from aria.security.rounds.r208_template_attack_guard import jitter_call
        out = jitter_call(lambda x: x * 2, 5, jitter_us=10)
        assert out == 10


class TestR209QRNG:
    def test_seed_length(self):
        from aria.security.rounds.r209_qrng_interface import get_quantum_seed
        seed, source = get_quantum_seed(32)
        assert len(seed) == 32 and source


class TestR210Inventory:
    def test_register_and_overdue(self):
        from aria.security.rounds.r210_crypto_inventory import register_key, due_for_rotation, register_rotation
        register_key("k-1", "Ed25519", "audit_seal", rotation_period_days=1.0)
        overdue = due_for_rotation(now=time.time() + 365 * 86_400)
        assert any(k == "k-1" for k, _ in overdue)
        register_rotation("k-1", now=time.time() + 365 * 86_400)
        overdue2 = due_for_rotation(now=time.time() + 365 * 86_400)
        assert not any(k == "k-1" for k, _ in overdue2)


class TestR211Y2Q:
    def test_audit_returns_tuple(self):
        from aria.security.rounds.r211_y2q_tracker import audit_migration_progress
        rate, lag = audit_migration_progress()
        assert isinstance(rate, float) and isinstance(lag, list)


# Block W (R212-R221) — OT/SCADA


class TestR212Modbus:
    def test_safety_register_blocked(self):
        from aria.security.rounds.r212_modbus_audit import audit_modbus_request
        ok, issues = audit_modbus_request(
            function_code=6, slave_id=1, register_addr=100, count=1, via_tls=True,
            safety_critical_ranges=[(50, 150)],
        )
        assert (not ok) and any("safety" in i for i in issues)


class TestR213DNP3:
    def test_weak_session(self):
        from aria.security.rounds.r213_dnp3_secure_auth import audit_dnp3_session
        ok, issues = audit_dnp3_session({"sav_version": 3})
        assert (not ok) and len(issues) >= 2


class TestR214BACnet:
    def test_life_safety_blocked(self):
        from aria.security.rounds.r214_bacnet_audit import audit_bacnet_op
        ok, issues = audit_bacnet_op(
            service="WriteProperty", object_type="fire_panel", via_bacnet_sc=True,
        )
        assert (not ok) and any("life_safety" in i for i in issues)


class TestR215OPCUA:
    def test_none_in_prod_blocked(self, monkeypatch):
        monkeypatch.setenv("ARIA_ENV", "prod")
        from aria.security.rounds.r215_opcua_security import audit_opcua_endpoint
        ok, issues = audit_opcua_endpoint({
            "securityPolicyUri": "http://opcfoundation.org/UA/SecurityPolicy#None",
            "securityMode": "None",
        })
        assert (not ok) and any("policy_none_in_prod" in i for i in issues)


class TestR216ICSAnomaly:
    def test_out_of_bounds_flagged(self):
        from aria.security.rounds.r216_ics_anomaly import configure_tag, check_value
        configure_tag("flow", min_value=0.0, max_value=100.0, max_rate_per_second=10.0)
        ok, _ = check_value("flow", 200.0)
        assert not ok


class TestR217Purdue:
    def test_it_to_ot_flagged(self):
        from aria.security.rounds.r217_purdue_segmentation import audit_purdue_flow
        ok, issues = audit_purdue_flow([("corp", 4, "plc", 1)])
        assert (not ok) and any("IT_to_OT" in i for i in issues)


class TestR218SISAirgap:
    def test_outbound_refused_when_sis(self, monkeypatch):
        monkeypatch.setenv("ARIA_SIS_HOST", "true")
        from aria.security.rounds.r218_sis_airgap import refuse_outbound_if_sis
        ok, _ = refuse_outbound_if_sis("anywhere.com")
        assert not ok


class TestR219ProtocolWhitelist:
    def test_blocked_port(self):
        from aria.security.rounds.r219_protocol_whitelist import audit_zone_traffic
        ok, issues = audit_zone_traffic("L2_basic_control", [(22, "tcp", "host", "plc")])
        assert (not ok) and len(issues) >= 1


class TestR220Historian:
    def test_chain_verify(self):
        from aria.security.rounds.r220_historian_tamper import append_row, verify_chain, reset_for_tests
        reset_for_tests()
        rows = [append_row(i, f"tag_{i}", float(i)) for i in range(5)]
        ok, _ = verify_chain(rows)
        assert ok


class TestR221PLCFirmware:
    def test_cooldown_active(self, monkeypatch):
        from aria.security.rounds.r221_plc_firmware_sig import gate_plc_firmware_update
        ok, why = gate_plc_firmware_update(
            plc_id="plc-1", firmware_blob=b"x", signature=b"x",
            vendor_pubkey=b"\x00" * 32, two_person_token="",
        )
        assert (not ok)


# Block X (R222-R231) — Web3


class TestR222Reentrancy:
    def test_reentrancy_detected(self):
        from aria.security.rounds.r222_solidity_reentrancy import lint_solidity
        bad = ('contract C { function withdraw() public { '
               '(bool s,) = msg.sender.call{value:1}(""); '
               'balances[msg.sender] = 0; } }')
        ok, issues = lint_solidity(bad)
        assert (not ok) and any("reentrancy_risk" in i for i in issues)


class TestR223Proxy:
    def test_eoa_blocked(self):
        from aria.security.rounds.r223_proxy_upgrade_audit import UpgradeAdmin, audit_proxy_admin
        ok, issues = audit_proxy_admin(UpgradeAdmin(kind="eoa"))
        assert (not ok) and any("admin_is_eoa" in i for i in issues)


class TestR224Bridge:
    def test_replay_blocked(self):
        from aria.security.rounds.r224_bridge_replay import record_bridge_message, reset_for_tests
        reset_for_tests()
        ok1, _ = record_bridge_message("eth->bsc", b"msg-1")
        ok2, _ = record_bridge_message("eth->bsc", b"msg-1")
        assert ok1 and not ok2


class TestR225Wallet:
    def test_infinite_allowance(self):
        from aria.security.rounds.r225_wallet_phish import audit_sign_request
        ok, issues = audit_sign_request({
            "method": "approve", "args": {"amount": 2 ** 256 - 1},
            "domain": {"chainId": 1},
        })
        assert (not ok) and any("infinite" in i for i in issues)


class TestR226AddressPoison:
    def test_poisoning_detected(self):
        from aria.security.rounds.r226_address_poisoning import looks_poisoned
        real = "0x" + "abcd" + "1" * 32 + "ef34"
        fake = "0x" + "abcd" + "9" * 32 + "ef34"
        poisoned, _ = looks_poisoned(fake, [real])
        assert poisoned


class TestR227Oracle:
    def test_twap_clean(self):
        from aria.security.rounds.r227_oracle_price_guard import record_sample, get_safe_price
        for _ in range(10):
            record_sample("ETH", 2000.0)
        ok, _, _ = get_safe_price("ETH")
        assert ok


class TestR228ERC20:
    def test_infinite_allowance_blocked(self):
        from aria.security.rounds.r228_erc20_allowance import audit_approve
        ok, _ = audit_approve(2 ** 256 - 1)
        assert not ok


class TestR229MEV:
    def test_high_risk_swap(self):
        from aria.security.rounds.r229_mev_detect import score_mev_risk
        score, _ = score_mev_risk(
            tx_value_wei=10 ** 18, gas_price_gwei=2.0, is_swap=True,
            pool_liquidity_wei=100 * 10 ** 18, slippage_pct=2.0, mempool_pending=300,
        )
        assert score >= 0.5


class TestR230CrossChain:
    def test_replay_blocked(self):
        from aria.security.rounds.r230_cross_chain_msg import verify_cross_chain_message, reset_for_tests
        reset_for_tests()
        ok1, _ = verify_cross_chain_message(
            source_chain_id=1, source_address="0xabc", nonce=1,
            message_timestamp=time.time(), allowed_sources=[(1, "0xabc")],
        )
        ok2, _ = verify_cross_chain_message(
            source_chain_id=1, source_address="0xabc", nonce=1,
            message_timestamp=time.time(), allowed_sources=[(1, "0xabc")],
        )
        assert ok1 and not ok2


class TestR231HwWalletAttest:
    def test_no_attestation_chain(self):
        from aria.security.rounds.r231_hw_wallet_attest import HwWalletAttestation, verify_attestation
        a = HwWalletAttestation(
            vendor="ledger", model="nano", firmware_version="2.0.0",
            attestation_chain=[], challenge_response=b"",
        )
        ok, issues = verify_attestation(a, min_firmware="1.0.0")
        assert (not ok) and "hwwallet.empty_chain" in issues


# Block Y (R232-R241) — Privacy


class TestR232DPClamp:
    def test_budget_exhaustion(self):
        from aria.security.rounds.r232_dp_clamp import add_laplace_noise, reset_budgets
        reset_budgets()
        for _ in range(20):
            add_laplace_noise(1.0, sensitivity=1.0, epsilon=0.5, subject_id="u")
        _, _, reason = add_laplace_noise(1.0, sensitivity=1.0, epsilon=0.5, subject_id="u")
        assert reason == "dp.budget_exhausted"


class TestR233KAnonymity:
    def test_violation_detected(self):
        from aria.security.rounds.r233_k_anonymity import check_k_anonymity
        rows = [
            {"age": 25, "zip": "94110"}, {"age": 25, "zip": "94110"},
            {"age": 30, "zip": "94110"},
        ]
        ok, k, _ = check_k_anonymity(rows, quasi_identifiers=["age", "zip"], k=2)
        assert (not ok) and k == 1


class TestR234TorExit:
    def test_classify(self):
        from aria.security.rounds.r234_tor_exit_detect import (
            load_exit_list, classify_ip, reset_for_tests, risk_bump,
        )
        reset_for_tests()
        load_exit_list(["1.2.3.4"])
        is_anon, src = classify_ip("1.2.3.4")
        assert is_anon and src == "tor_exit"
        bump = risk_bump("1.2.3.4", sensitive_action=True)
        assert bump >= 0.4


class TestR235PIITokenize:
    def test_deterministic_distinct(self, monkeypatch):
        monkeypatch.setenv("ARIA_MASTER_KEY", "a" * 64)
        from aria.security.rounds.r235_pii_tokenize import tokenise
        t1, _ = tokenise("123-45-6789")
        t2, _ = tokenise("123-45-6789")
        t3, _ = tokenise("999-88-7777")
        assert t1 == t2 and t1 != t3
        assert "-" in t1 and len(t1) == len("123-45-6789")


class TestR236ModelInversion:
    def test_attack_detection(self):
        from aria.security.rounds.r236_model_inversion import (
            record_query, is_inversion_attack, reset_for_tests,
        )
        reset_for_tests("a")
        for _ in range(250):
            record_query("a")
        flag, _ = is_inversion_attack("a", threshold=200)
        assert flag


class TestR237MembershipInference:
    def test_clip_high_confidence(self):
        from aria.security.rounds.r237_membership_inference import clip_confidence
        out, clipped = clip_confidence({"a": 0.99, "b": 0.005, "c": 0.005}, max_top1=0.92)
        assert clipped and out["a"] == 0.92
        assert abs(sum(out.values()) - 1.0) < 1e-6


class TestR238FLGradient:
    def test_clip_l2(self):
        from aria.security.rounds.r238_fl_gradient_privacy import clip_l2
        clipped, original = clip_l2([10.0, 0.0, 0.0], max_norm=1.0)
        assert abs(sum(x * x for x in clipped) - 1.0) < 1e-6 and original == 10.0


class TestR239DataResidency:
    def test_violation(self):
        from aria.security.rounds.r239_data_residency import (
            configure_tenant, check_destination, reset_for_tests,
        )
        reset_for_tests()
        configure_tenant("acme-eu", ["EU-WEST-1"])
        ok, _ = check_destination("acme-eu", "us-east-1")
        assert not ok


class TestR240RTBF:
    def test_partial_completion(self):
        from aria.security.rounds.r240_rtbf_propagation import (
            register_erasure_request, record_erasure_complete, is_complete,
        )
        register_erasure_request("req-x", "u", ["a", "b"])
        record_erasure_complete("req-x", "a")
        done, outstanding = is_complete("req-x")
        assert (not done) and outstanding == ["b"]


class TestR241PrivacyBudget:
    def test_annual_ceiling(self):
        from aria.security.rounds.r241_privacy_budget import charge, reset_subject
        reset_subject("u")
        for _ in range(20):
            charge("u", 0.5)
        ok, _, reason = charge("u", 0.5)
        assert (not ok) and reason == "budget.annual_exceeded"


# Block Z (R242-R251) — Nation-grade ops


class TestR242Diode:
    def test_high_to_low_low_origin_blocked(self):
        from aria.security.rounds.r242_air_gap_diode import refuse_if_violates
        ok, _ = refuse_if_violates("high_to_low", source_high=False, dest_high=False)
        assert not ok


class TestR243TwoPersonCrypto:
    def test_quorum_path(self):
        from aria.security.rounds.r243_two_person_crypto import (
            open_ceremony, approve, is_approved, close_ceremony,
        )
        cid = open_ceremony("rotate_kek", quorum=2)
        approve(cid, "alice")
        ok1, _ = is_approved(cid)
        approve(cid, "bob")
        ok2, _ = is_approved(cid)
        close_ceremony(cid)
        assert (not ok1) and ok2

    def test_quorum_below_two_raises(self):
        from aria.security.rounds.r243_two_person_crypto import open_ceremony
        with pytest.raises(ValueError):
            open_ceremony("x", quorum=1)


class TestR244TokenEnrollment:
    def test_no_physical_presence_refused(self):
        from aria.security.rounds.r244_token_enrollment import begin_enrollment
        ok, _ = begin_enrollment(
            token_id="t", user_id="u", physical_presence=False,
            attestation_vendor="ledger",
        )
        assert not ok

    def test_privileged_requires_two_person(self):
        from aria.security.rounds.r244_token_enrollment import begin_enrollment, complete_enrollment
        begin_enrollment(
            token_id="t-priv", user_id="u", physical_presence=True,
            attestation_vendor="ledger", privileged=True,
        )
        ok, _ = complete_enrollment("t-priv", two_person_token="")
        assert not ok


class TestR245QKD:
    def test_unconfigured_returns_none(self):
        from aria.security.rounds.r245_qkd_interface import fetch_key_from_qkd, is_qkd_available
        key, why = fetch_key_from_qkd(key_id="k-1")
        assert key is None and "no_qkd" in why
        assert isinstance(is_qkd_available(), bool)


class TestR246InsiderUBA:
    def test_off_hours_score(self):
        from aria.security.rounds.r246_insider_uba import update_baseline, score_session
        for _ in range(10):
            update_baseline("u", hour_of_day=14, data_class="docs", volume_mb=10.0)
        score, _ = score_session("u", hour_of_day=3, data_class="docs", volume_mb=10.0)
        assert score >= 0.3


class TestR247Espionage:
    def test_combined_score(self):
        from aria.security.rounds.r247_espionage_indicator import (
            record_event, score_host, reset_for_tests,
        )
        reset_for_tests()
        for ind in ("staging_dir_growth", "credential_dump", "lateral_movement"):
            record_event("h", ind)
        score, _ = score_host("h")
        assert score >= 0.6


class TestR248CounterIntelDecoy:
    def test_canary_round_trip(self):
        from aria.security.rounds.r248_counterintel_decoy import (
            generate_decoy, is_canary, reset_for_tests,
        )
        reset_for_tests()
        a = generate_decoy("aws_credential")
        assert is_canary(a.canary)
        assert not is_canary("not-a-canary")


class TestR249FISMAHigh:
    def test_chain_records(self):
        from aria.security.rounds.r249_fisma_high_audit import (
            record_high_action, verify_fisma_chain, reset_for_tests,
        )
        reset_for_tests()
        ok, _ = record_high_action(
            actor="alice", source_ip="10.0.0.1", classification="secret",
            action="rotate_kek", target="kek-root", two_person_id="cer-1",
        )
        assert ok
        verify_ok, n = verify_fisma_chain()
        assert verify_ok and n >= 1

    def test_incomplete_record_refused(self):
        from aria.security.rounds.r249_fisma_high_audit import record_high_action
        ok, why = record_high_action(
            actor="", source_ip="10.0.0.1", classification="secret",
            action="x", target="y", two_person_id="z",
        )
        assert (not ok) and "incomplete" in why


class TestR250CryptoDestruction:
    def test_secure_erase_buffer(self):
        from aria.security.rounds.r250_crypto_destruction import secure_erase_buffer
        buf = bytearray(b"sensitive_secret_material")
        secure_erase_buffer(buf)
        assert all(b == 0 for b in buf)


class TestR251RunnerV5:
    def test_full_sweep(self):
        from aria.security.rounds.r251_adversarial_runner_v5 import run_v5, render_v5
        report = run_v5()
        assert report.passed, render_v5(report)
        assert report.caught >= 30
