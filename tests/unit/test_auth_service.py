"""R32 Phase 2 — AuthService challenge/login/logout tests."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aria.security import principals as p
from aria.security import auth_service as auth
from aria.security.session_store import SessionStore


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"
DEV_KEYS = json.loads((REPO / "tests" / "fixtures" / "dev_keys.json").read_text())


def _privkey(name: str) -> Ed25519PrivateKey:
    seed = bytes.fromhex(DEV_KEYS[name]["priv_seed_hex"])
    return Ed25519PrivateKey.from_private_bytes(seed)


def _setup(tmp_path: Path) -> auth.AuthService:
    p.reset_for_test(sealed_dir=SEALED, runtime_dir=tmp_path)
    sessions = SessionStore(runtime_dir=tmp_path)
    auth.reset_for_test(sessions=sessions)
    return auth.get_auth_service()


class TestLoginHappyPath:
    def test_captain_can_login(self, tmp_path):
        svc = _setup(tmp_path)
        ch = svc.issue_challenge("captain.tau")
        sig = _privkey("captain.tau").sign(ch.signing_payload()).hex()
        s = svc.login("captain.tau", ch.nonce, sig)
        assert s.principal_id == "captain.tau"
        assert s.role == "captain"
        assert s.duress is False

    def test_crew_can_login(self, tmp_path):
        svc = _setup(tmp_path)
        ch = svc.issue_challenge("crew.alpha")
        sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
        s = svc.login("crew.alpha", ch.nonce, sig)
        assert s.role == "crew"

    def test_login_then_logout(self, tmp_path):
        # Round-2 audit NEW-HIGH-13 — logout returns None always so
        # the wire layer cannot use it as a token-validity oracle.
        # The actual revocation is observable only via the audit log
        # and the side-effect that subsequent ``get`` returns None.
        svc = _setup(tmp_path)
        ch = svc.issue_challenge("crew.alpha")
        sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
        s = svc.login("crew.alpha", ch.nonce, sig)
        assert svc.logout(s.token) is None
        # And presenting the same token to a get() now misses.
        from aria.security.session_store import get_session_store
        assert get_session_store().get(s.token) is None
        # Calling logout on an already-revoked / unknown token also
        # returns None — no oracle.
        assert svc.logout(s.token) is None
        assert svc.logout("0" * 64) is None


class TestLoginRejections:
    def test_unknown_principal(self, tmp_path):
        svc = _setup(tmp_path)
        ch = svc.issue_challenge("ghost.user")
        # Have to sign with *some* key — use a dev key, but it will fail
        # because ghost.user is not in the roster.
        sig = _privkey("captain.tau").sign(ch.signing_payload()).hex()
        with pytest.raises(auth.AuthError):
            svc.login("ghost.user", ch.nonce, sig)

    def test_wrong_signing_key(self, tmp_path):
        svc = _setup(tmp_path)
        ch = svc.issue_challenge("captain.tau")
        # Sign with crew.alpha's key, claim to be captain — must fail.
        sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
        with pytest.raises(auth.AuthError):
            svc.login("captain.tau", ch.nonce, sig)

    def test_replayed_challenge(self, tmp_path):
        svc = _setup(tmp_path)
        ch = svc.issue_challenge("crew.alpha")
        sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
        svc.login("crew.alpha", ch.nonce, sig)
        with pytest.raises(auth.AuthError):
            svc.login("crew.alpha", ch.nonce, sig)

    def test_swapped_challenge_principal(self, tmp_path):
        svc = _setup(tmp_path)
        # Issue a challenge for captain; try to use it for crew.
        ch = svc.issue_challenge("captain.tau")
        sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
        with pytest.raises(auth.AuthError):
            svc.login("crew.alpha", ch.nonce, sig)

    def test_malformed_signature(self, tmp_path):
        svc = _setup(tmp_path)
        ch = svc.issue_challenge("crew.alpha")
        with pytest.raises(auth.AuthError):
            svc.login("crew.alpha", ch.nonce, "not-hex!!!")


class TestDuressFlag:
    def test_duress_login_marks_session(self, tmp_path):
        svc = _setup(tmp_path)
        ch = svc.issue_challenge("crew.alpha")
        sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
        s = svc.login("crew.alpha", ch.nonce, sig, duress=True)
        assert s.duress is True

    def test_duress_principal_downgraded(self, tmp_path):
        svc = _setup(tmp_path)
        ch = svc.issue_challenge("crew.alpha")
        sig = _privkey("crew.alpha").sign(ch.signing_payload()).hex()
        s = svc.login("crew.alpha", ch.nonce, sig, duress=True)
        principal = auth.principal_from_session(s)
        # authorize() must refuse anything but telemetry.read.
        assert p.authorize(principal, "telemetry.read").allow
        assert not p.authorize(principal, "approval.sign").allow
        assert not p.authorize(principal, "kill_switch.assert").allow
