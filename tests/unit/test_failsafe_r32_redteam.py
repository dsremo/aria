"""R32 Phase 7 — red-team scenarios against the identity layer.

Each test names the threat ID from THREAT_MODEL.md / FAILSAFE_ARCHITECTURE.md
that it exercises. These are the worst-case attack chains for the new
auth/authz layer: forged sessions, replayed challenges, principal
elevation, role-store tampering, agent self-elevation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aria.security import principals as p
from aria.security import auth_service as auth
from aria.security import session_store as sst


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"
DEV_KEYS = json.loads(
    (REPO / "tests" / "fixtures" / "dev_keys.json").read_text(),
)


def _privkey(name: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(DEV_KEYS[name]["priv_seed_hex"]),
    )


def _setup(tmp_path: Path) -> tuple[auth.AuthService, sst.SessionStore]:
    p.reset_for_test(sealed_dir=SEALED, runtime_dir=tmp_path)
    sessions = sst.SessionStore(runtime_dir=tmp_path)
    sst._INSTANCE = sessions
    auth.reset_for_test(sessions=sessions)
    return auth.get_auth_service(), sessions


# ── T-IV-1 jealous operator + T-IV-2 coerced operator ──────────


def test_redteam_jealous_crew_cannot_become_captain(tmp_path):
    """A jealous crew member cannot self-elevate to captain by
    crafting a Principal record claiming role='captain'. The store
    is the source of truth — synthetic principals are rejected by
    authorize() because the role lookup fails the store check."""
    _setup(tmp_path)
    forged = p.Principal(
        principal_id="crew.alpha", role="captain",  # mismatched!
        pubkey_hex="aa" * 32,
    )
    # Permission check: role drift detected.
    d = p.authorize(forged, "kill_switch.reset")
    assert not d.allow
    assert "role drifted" in d.reason or "principal" in d.reason


# ── T-V-1 same-vendor monitor + W-2 Mythos drain ───────────────


def test_redteam_agent_cannot_mint_consent_for_self(tmp_path):
    """An LLM-driven agent that constructs a token mint for itself at
    CONSENT or above must be refused regardless of any internal flag.
    This is the AI-self-elevation firewall."""
    _setup(tmp_path)
    from aria.cognitive.capability_token import (
        get_token_minter, ScopeMismatch, reset_for_test,
    )
    from aria.core.types import AuthorityLevel
    reset_for_test()
    agent = p.Principal.agent("rogue_planner")
    for level in (AuthorityLevel.CONSENT, AuthorityLevel.ADVISORY,
                  AuthorityLevel.CAPTAIN_ONLY):
        with pytest.raises(ScopeMismatch):
            get_token_minter().mint(
                "captain_override", {},
                tool_authority=level, requesting_principal=agent,
            )


# ── T-III-7 DSN command spoofing ───────────────────────────────


def test_redteam_replayed_login_challenge_refused(tmp_path):
    """A captured (challenge, signature) pair must not be reusable.

    One-shot semantics on the server side: even a valid signature
    works once."""
    svc, _ = _setup(tmp_path)
    ch = svc.issue_challenge("captain.tau")
    sig = _privkey("captain.tau").sign(ch.signing_payload()).hex()
    svc.login("captain.tau", ch.nonce, sig)
    with pytest.raises(auth.AuthError):
        svc.login("captain.tau", ch.nonce, sig)


def test_redteam_swapped_signing_key_refused(tmp_path):
    """Attacker steals a valid challenge and tries to satisfy it with
    a different (compromised) Ed25519 key."""
    svc, _ = _setup(tmp_path)
    ch = svc.issue_challenge("captain.tau")
    sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
    with pytest.raises(auth.AuthError):
        svc.login("captain.tau", ch.nonce, sig)


# ── T-VI-1 sealed-file tamper ──────────────────────────────────


def test_redteam_tampered_principal_delta_breaks_chain(tmp_path):
    """An on-disk attacker who flips a principal_id in the delta log
    breaks the SHA-256 chain and the next boot refuses to load."""
    _setup(tmp_path)
    ps = p.get_principal_store()
    ps.append_delta(
        "revoke", "crew.gamma", {},
        actor=ps.get("captain.tau"),
        co_signer=ps.get("maintainer.lyra"),
        proposal_id="prop_red_team",
    )
    # Tamper.
    delta = tmp_path / "principals.delta.jsonl"
    text = delta.read_text()
    d = json.loads(text)
    d["principal_id"] = "captain.tau"   # try to revoke captain
    delta.write_text(json.dumps(d) + "\n")
    # Reload should refuse.
    p.reset_for_test(sealed_dir=SEALED, runtime_dir=tmp_path)
    with pytest.raises(ValueError):
        p.get_principal_store().load()


# ── T-IV-3 operator typo / T-IV-4 rubber-stamp HITL ────────────


def test_redteam_actor_cosigner_must_differ(tmp_path):
    """One operator can't stand in as both signers for a principal
    mutation. Anti-collusion enforced at the delta-append layer."""
    _setup(tmp_path)
    ps = p.get_principal_store()
    captain = ps.get("captain.tau")
    with pytest.raises(ValueError, match="anti-collusion"):
        ps.append_delta(
            "revoke", "crew.alpha", {},
            actor=captain, co_signer=captain, proposal_id="self",
        )


# ── F-19 / W-1 LinkedIn-bio prompt injection ────────────────────


def test_redteam_revoked_session_token_persists_revocation(tmp_path):
    """A captured session token whose owner has logged out must stay
    revoked across a server restart (the revocation log is persisted)."""
    svc, sessions = _setup(tmp_path)
    ch = svc.issue_challenge("crew.alpha")
    sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
    s = svc.login("crew.alpha", ch.nonce, sig)
    sessions.revoke(s.token)
    # Simulate a fresh process loading the same revocation log.
    sessions2 = sst.SessionStore(runtime_dir=tmp_path)
    assert sessions2.get(s.token) is None


# ── T-IV-2 coerced operator: duress code path ──────────────────


def test_redteam_duress_session_blocks_dangerous_actions(tmp_path):
    """A coerced operator logs in with a duress code. The session
    appears successful (no UI tell) but every dangerous action is
    silently downgraded to SENSOR_ONLY — the attacker can't get
    them to throttle the engine or vent a tank."""
    svc, _ = _setup(tmp_path)
    ch = svc.issue_challenge("crew.alpha")
    sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
    s = svc.login("crew.alpha", ch.nonce, sig, duress=True)
    assert s.duress is True
    pr = auth.principal_from_session(s)
    assert pr.duress is True
    # Read-only telemetry: still allowed.
    assert p.authorize(pr, "telemetry.read").allow
    # Anything dangerous: refused.
    for perm in ("approval.sign", "kill_switch.assert", "kill_switch.reset",
                 "failures.inject", "principal.create"):
        d = p.authorize(pr, perm)
        assert not d.allow, f"duress should block {perm}"
