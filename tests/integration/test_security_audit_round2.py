"""Round-2 + round-3 security audit (2026-04-27) — wiring tests.

Each test below exercises one of the audit fixes end-to-end so that a
future regression (the original failure mode of "added but not wired")
is caught immediately.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aria.security.auth import (
    AuthResult,
    CommandAuthenticator,
    CommandCredential,
    mint_internal_channel_token,
    reset_internal_channel_token_for_test,
)


# ── auth.py ──────────────────────────────────────────────────────


class TestAuthHardening:
    SECRET = "z" * 64    # 64-char high-entropy ASCII (passes the floor)

    def _auth(self) -> CommandAuthenticator:
        return CommandAuthenticator(shared_secret=self.SECRET)

    def test_no_session_token_rejected(self):
        a = self._auth()
        result = a.authenticate(CommandCredential(issuer="captain"))
        assert result == AuthResult.REJECTED_IDENTITY

    def test_agent_prefix_in_issuer_does_not_bypass(self):
        """Round-2 audit NEW-CRIT-1 — the legacy ``agent:`` issuer
        prefix must no longer fast-path."""
        a = self._auth()
        result = a.authenticate(CommandCredential(issuer="agent:malicious"))
        assert result == AuthResult.REJECTED_IDENTITY

    def test_create_session_refuses_agent_namespace(self):
        a = self._auth()
        with pytest.raises(ValueError):
            a.create_session("agent:foo")

    def test_internal_channel_token_required_for_internal_path(self):
        reset_internal_channel_token_for_test()
        a = self._auth()
        # No token minted yet — the wire credential carrying random
        # bytes must reject.
        result = a.authenticate(CommandCredential(
            issuer="agent:internal",
            internal_channel_token=b"\x00" * 32,
        ))
        assert result == AuthResult.REJECTED_IDENTITY
        # After minting, only the exact bytes accept.
        tok = mint_internal_channel_token()
        assert tok != b"\x00" * 32
        result = a.authenticate(CommandCredential(
            issuer="agent:internal",
            internal_channel_token=tok,
        ))
        assert result == AuthResult.ACCEPTED
        result = a.authenticate(CommandCredential(
            issuer="agent:internal",
            internal_channel_token=b"\x01" * 32,
        ))
        assert result == AuthResult.REJECTED_IDENTITY
        reset_internal_channel_token_for_test()

    def test_issuer_bound_to_session(self):
        """Round-2 audit NEW-CRIT-2."""
        a = self._auth()
        token = a.create_session("captain")
        assert a.issuer_for_session(token) == "captain"

    def test_zero_counter_rejected(self):
        """Round-2 audit NEW-CRIT-5."""
        a = self._auth()
        token = a.create_session("captain")
        cred = CommandCredential(
            issuer="captain", session_token=token,
            command_counter=0, timestamp=__import__("time").time(),
            signature=a.sign_command(""),
        )
        assert a.authenticate(cred, "") == AuthResult.REJECTED_REPLAY

    def test_zero_timestamp_rejected(self):
        """Round-2 audit NEW-CRIT-5."""
        a = self._auth()
        token = a.create_session("captain")
        cred = CommandCredential(
            issuer="captain", session_token=token,
            command_counter=1, timestamp=0,
            signature=a.sign_command("X"),
        )
        assert a.authenticate(cred, "X") == AuthResult.REJECTED_EXPIRED

    def test_empty_signature_rejected(self):
        """Round-2 audit NEW-CRIT-5."""
        import time as _t
        a = self._auth()
        token = a.create_session("captain")
        cred = CommandCredential(
            issuer="captain", session_token=token,
            command_counter=1, timestamp=_t.time(),
            signature="",
        )
        assert a.authenticate(cred, "X") == AuthResult.REJECTED_SIGNATURE

    def test_future_dated_command_rejected(self):
        """Round-2 audit NEW-CRIT-6."""
        import time as _t
        a = self._auth()
        token = a.create_session("captain")
        cred = CommandCredential(
            issuer="captain", session_token=token,
            command_counter=1, timestamp=_t.time() + 600,    # 10 min in future
            signature=a.sign_command("X"),
        )
        assert a.authenticate(cred, "X") == AuthResult.REJECTED_EXPIRED

    def test_session_dict_bounded(self):
        """Round-2 audit NEW-HIGH-2 — bounded LRU."""
        a = CommandAuthenticator(shared_secret=self.SECRET, max_active_sessions=5)
        for i in range(10):
            a.create_session(f"u{i}")
        # Max five remain active.
        active = sum(1 for i in range(10)
                     if a.issuer_for_session(f"sentinel-{i}") is not None)
        # Just check internal table cap.
        assert len(a._active_sessions) <= 5    # noqa: SLF001


# ── session_store.py ─────────────────────────────────────────────


class TestSessionStoreHardening:
    def test_revoked_log_stores_hash_not_token(self, tmp_path: Path):
        """Round-2 audit NEW-HIGH-1."""
        from aria.security.session_store import SessionStore
        s = SessionStore(runtime_dir=tmp_path)
        sess = s.create("crew.alpha", "crew")
        s.revoke(sess.token)
        log = (tmp_path / "sessions_revoked.jsonl").read_text()
        assert sess.token not in log
        assert "token_hash" in log

    def test_session_fail_closed_on_empty_fingerprint_when_bound(self, tmp_path: Path):
        """Round-2 audit NEW-HIGH-4."""
        from aria.security.session_store import SessionStore
        s = SessionStore(runtime_dir=tmp_path)
        sess = s.create("crew.alpha", "crew",
                        client_ip_hash="ip16", client_ua_hash="ua16")
        # Same fingerprint passes.
        assert s.touch(sess.token, ip_hash="ip16", ua_hash="ua16") is not None
        # Empty IP from header-strip rejects.
        assert s.touch(sess.token, ip_hash="", ua_hash="ua16") is None
        # Different IP rejects.
        assert s.touch(sess.token, ip_hash="other", ua_hash="ua16") is None

    def test_fingerprint_constant_time_compare(self, tmp_path: Path):
        """Round-2 audit NEW-MED-2 — uses hmac.compare_digest."""
        from aria.security.session_store import Session
        s = Session(
            token="t", principal_id="p", role="crew",
            created_at=0, last_seen_at=0, last_seen_monotonic=1,
            expires_at=2 ** 32, idle_window_s=3600, duress=False,
            client_ip_hash="abc", client_ua_hash="xyz",
        )
        assert s.matches_client(ip_hash="abc", ua_hash="xyz") is True
        assert s.matches_client(ip_hash="abx", ua_hash="xyz") is False

    def test_revoked_log_trimmed_on_load(self, tmp_path: Path):
        """Round-2 audit NEW-HIGH-3 — old revocation entries are
        dropped on load."""
        from aria.security.session_store import SessionStore
        path = tmp_path / "sessions_revoked.jsonl"
        path.write_text(
            '{"token_hash":"abc","reason":"old","expires_at":1}\n'
            '{"token_hash":"def","reason":"new","expires_at":99999999999}\n'
        )
        s = SessionStore(runtime_dir=tmp_path)
        assert "abc" not in s._revoked    # noqa: SLF001
        assert "def" in s._revoked    # noqa: SLF001

    def test_counter_persists_across_restart(self, tmp_path: Path):
        """Round-2 audit NEW-HIGH-5 + round-3 audit R3-HIGH-4 — flush
        is now coalesced; a graceful-shutdown caller must invoke
        ``flush_counters`` to commit pending increments to disk."""
        from aria.security.session_store import SessionStore
        s = SessionStore(runtime_dir=tmp_path)
        sess = s.create("crew.alpha", "crew")
        s.increment_counter(sess.token)
        s.increment_counter(sess.token)
        s.flush_counters()    # graceful shutdown
        # Cold-restart: a new SessionStore loads counters from disk.
        s2 = SessionStore(runtime_dir=tmp_path)
        sess2 = s2.create("crew.alpha", "crew")
        # New session for the same principal starts above the
        # persisted counter.
        assert sess2.command_counter >= 2


# ── middleware.py ────────────────────────────────────────────────


class TestMiddlewareWiring:
    def test_unmapped_route_default_is_deny(self):
        """Round-2 audit NEW-HIGH-15 — unmapped routes resolve to a
        sentinel permission that no role holds."""
        from aria.security.middleware import (
            UNMAPPED_ROUTE_PERMISSION,
            make_route_permission_middleware,
        )
        # Constructing with the default (deny) sentinel must succeed.
        mw = make_route_permission_middleware({}, enforced=True)
        assert mw is not None
        # The sentinel itself isn't granted to any role.
        from aria.security.principals import Principal, authorize
        d = authorize(Principal.anonymous(), UNMAPPED_ROUTE_PERMISSION)
        assert not d.allow

    def test_route_perm_refuses_enforced_false_in_production(self, monkeypatch):
        """Round-2 audit NEW-HIGH-16."""
        from aria.security.middleware import make_route_permission_middleware
        monkeypatch.setenv("ARIA_ENV", "prod")
        with pytest.raises(RuntimeError):
            make_route_permission_middleware({}, enforced=False)
        monkeypatch.delenv("ARIA_ENV", raising=False)


# ── auth_service.py ──────────────────────────────────────────────


class TestAuthServiceRateLimit:
    def test_challenge_rate_limited_per_principal(self, tmp_path: Path):
        """Round-2 audit NEW-HIGH-14."""
        from aria.security.auth_service import (
            AuthService, ChallengeRateLimited,
        )
        from aria.security.session_store import SessionStore
        svc = AuthService(sessions=SessionStore(runtime_dir=tmp_path))
        # Burst more challenges than the per-principal bucket allows.
        for _ in range(30):
            svc.issue_challenge("crew.alpha")
        with pytest.raises(ChallengeRateLimited):
            svc.issue_challenge("crew.alpha")


# ── screener service.py ─────────────────────────────────────────


class TestScreenerHardening:
    def test_xff_ignored_without_trusted_proxies(self, monkeypatch):
        """Round-2 audit NEW-CRIT-4 — XFF is honoured ONLY when the
        immediate peer is on the ARIA_TRUSTED_PROXIES allow-list.
        Verified at the module level by checking the helper."""
        from aria.products.conjunction_screener.service import (
            _trusted_proxies_from_env,
        )
        monkeypatch.delenv("ARIA_TRUSTED_PROXIES", raising=False)
        assert _trusted_proxies_from_env() == []

    def test_search_window_clamped(self):
        """Round-2 audit NEW-HIGH-12."""
        from aria.products.conjunction_screener.service import _request_to_obj
        l1 = "1 24946U 97051C   09040.74440185  .00000114  00000-0  35055-4 0  4373"
        l2 = "2 24946  86.3938 124.4685 0002131  79.4630 280.6878 14.34219697598149"
        body = {
            "primary": {"norad_id": "X", "line1": l1, "line2": l2},
            "secondaries": [],
            "search_window_minutes": 1_000_000,
        }
        with pytest.raises(ValueError):
            _request_to_obj(body)

    def test_radius_must_be_finite(self):
        """Round-2 audit NEW-HIGH-8."""
        from aria.products.conjunction_screener.service import _request_to_obj
        l1 = "1 24946U 97051C   09040.74440185  .00000114  00000-0  35055-4 0  4373"
        l2 = "2 24946  86.3938 124.4685 0002131  79.4630 280.6878 14.34219697598149"
        body = {
            "primary": {"norad_id": "X", "line1": l1, "line2": l2,
                        "radius_m": float("inf")},
            "secondaries": [],
        }
        with pytest.raises(ValueError):
            _request_to_obj(body)

    def test_request_id_is_random(self):
        """Round-2 audit NEW-MED-8 — request_id is not derivable from
        (start_iso + norad_id)."""
        from aria.products.conjunction_screener.service import (
            ConjunctionScreenerService, ScreenRequest, TLEPayload,
        )
        l1 = "1 25544U 98067A   24310.50000000  .00010000  00000-0  18000-3 0  9991"
        l2 = "2 25544  51.6400 100.0000 0008000  80.0000 280.0000 15.49000000300008"
        primary = TLEPayload(norad_id="25544", name="X", line1=l1, line2=l2)
        req = ScreenRequest(primary=primary, secondaries=[])
        ids = {ConjunctionScreenerService().screen(req).request_id for _ in range(8)}
        assert len(ids) == 8


# ── tenants.py ───────────────────────────────────────────────────


class TestTenantStoreHardening:
    def test_at_rest_format_is_hmac(self, tmp_path: Path):
        """Round-2 audit NEW-HIGH-6."""
        from aria.products.conjunction_screener.tenants import TenantStore
        s = TenantStore(tmp_path / "t.sqlite3")
        t = s.create_tenant("acme")
        got = s.get("acme")
        assert got.api_key_hex.startswith("hmac:")

    def test_weak_operator_key_rejected(self, tmp_path: Path):
        """Round-2 audit NEW-HIGH-6."""
        from aria.products.conjunction_screener.tenants import TenantStore
        s = TenantStore(tmp_path / "t.sqlite3")
        with pytest.raises(ValueError):
            s.create_tenant("acme", api_key_hex="aaaaaaaa")    # too short

    def test_record_usage_validates_tenant(self, tmp_path: Path):
        """Round-2 audit NEW-MED-7."""
        from aria.products.conjunction_screener.tenants import TenantStore
        s = TenantStore(tmp_path / "t.sqlite3")
        # Unknown tenant — no row inserted, no exception.
        s.record_usage("does-not-exist", "screen", n_pairs=1)
        assert s.usage_summary("does-not-exist")["request_count"] == 0

    def test_usage_clamps_negative_values(self, tmp_path: Path):
        """Round-2 audit NEW-MED-16."""
        from aria.products.conjunction_screener.tenants import TenantStore
        s = TenantStore(tmp_path / "t.sqlite3")
        s.create_tenant("acme")
        s.record_usage("acme", "screen", n_pairs=-100, elapsed_ms=-50.0)
        summary = s.usage_summary("acme")
        assert summary["pair_count"] == 0    # clamped to 0


# ── guard.py ─────────────────────────────────────────────────────


class TestGuardHardening:
    def test_negative_content_length_rejected(self):
        """Round-2 audit NEW-HIGH-20 — exercised at the helper level
        because spinning a TestServer is heavyweight."""
        from aiohttp.test_utils import make_mocked_request
        from aria.security.guard import make_body_size_middleware
        import asyncio

        async def handler(request):
            from aiohttp import web
            return web.Response(text="ok")

        async def call_with_cl(cl_value: str):
            req = make_mocked_request("POST", "/x", headers={"Content-Length": cl_value})
            mw = make_body_size_middleware(max_bytes=1024)
            return await mw(req, handler)

        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(call_with_cl("-1"))
            assert r1.status == 400
            r2 = loop.run_until_complete(call_with_cl("99999"))
            assert r2.status == 413
        finally:
            loop.close()

    def test_is_production_recognises_aliases(self, monkeypatch):
        """Round-2 audit NEW-HIGH-17."""
        from aria.security.env import is_production
        for value in ("prod", "production", "live", "PROD", "Production"):
            monkeypatch.setenv("ARIA_ENV", value)
            assert is_production()
        for value in ("dev", "test", "staging", ""):
            monkeypatch.setenv("ARIA_ENV", value)
            assert not is_production()
        monkeypatch.delenv("ARIA_ENV", raising=False)

    def test_hsts_preload_off_by_default(self, monkeypatch):
        """Round-2 audit NEW-LOW-5."""
        monkeypatch.delenv("ARIA_HSTS_PRELOAD", raising=False)
        from aria.security.guard import _security_headers
        h = _security_headers()
        assert "preload" not in h["Strict-Transport-Security"]


# ── auth_middleware fingerprint wiring (NEW-CRIT-3) ─────────────


class TestSessionFingerprintWiring:
    def test_session_bound_at_login_via_auth_service(self, tmp_path: Path,
                                                    monkeypatch):
        """Round-2 audit NEW-CRIT-3 — AuthService.login() now stores
        fingerprint hashes on the Session, and the SessionStore
        rejects subsequent touches from a different client."""
        import json
        from aria.security import principals as p
        from aria.security import auth_service as auth
        from aria.security.session_store import (
            SessionStore, fingerprint_ip, fingerprint_ua,
        )
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        repo = Path(__file__).resolve().parents[2]
        sealed = repo / "data" / "sealed"
        dev_keys = json.loads((repo / "tests" / "fixtures" / "dev_keys.json").read_text())
        priv = Ed25519PrivateKey.from_private_bytes(
            bytes.fromhex(dev_keys["crew.alpha"]["priv_seed_hex"]),
        )
        p.reset_for_test(sealed_dir=sealed, runtime_dir=tmp_path)
        sessions = SessionStore(runtime_dir=tmp_path)
        auth.reset_for_test(sessions=sessions)
        svc = auth.get_auth_service()
        ch = svc.issue_challenge("crew.alpha")
        sig = priv.sign(ch.signing_payload()).hex()
        s = svc.login("crew.alpha", ch.nonce, sig,
                      client_ip="10.0.0.1", client_ua="Mozilla/5.0")
        assert s.client_ip_hash == fingerprint_ip("10.0.0.1")
        assert s.client_ua_hash == fingerprint_ua("Mozilla/5.0")
        assert s.pubkey_fingerprint != ""
        # Same fingerprint -> ok.
        assert sessions.touch(
            s.token,
            ip_hash=fingerprint_ip("10.0.0.1"),
            ua_hash=fingerprint_ua("Mozilla/5.0"),
        ) is not None
        # Different fingerprint -> rejected.
        assert sessions.touch(
            s.token,
            ip_hash=fingerprint_ip("10.0.0.2"),
            ua_hash=fingerprint_ua("Mozilla/5.0"),
        ) is None


# ────────────────────────────────────────────────────────────────
# Round-3 audit (2026-04-27 R3) — wiring tests for the new fixes.
# ────────────────────────────────────────────────────────────────


class TestRound3InternalChannelTokenIsOneShot:
    def test_mint_is_one_shot(self):
        """Round-3 audit R3-CRIT-1 / R3-CRIT-2 — mint may be called at
        most once per process; subsequent callers get a RuntimeError
        and CANNOT retrieve the token bytes."""
        reset_internal_channel_token_for_test()
        try:
            tok = mint_internal_channel_token()
            assert isinstance(tok, bytes) and len(tok) == 32
            with pytest.raises(RuntimeError):
                mint_internal_channel_token()
        finally:
            reset_internal_channel_token_for_test()

    def test_verify_only_returns_bool(self):
        """Round-3 audit R3-CRIT-2 — the verification API never
        returns the token bytes themselves."""
        from aria.security.auth import verify_internal_channel_token
        reset_internal_channel_token_for_test()
        try:
            assert verify_internal_channel_token(b"\x00" * 32) is False
            tok = mint_internal_channel_token()
            assert verify_internal_channel_token(tok) is True
            assert verify_internal_channel_token(b"\x01" * 32) is False
            assert verify_internal_channel_token(b"") is False
        finally:
            reset_internal_channel_token_for_test()


class TestRound3PubkeyFingerprintFailClosed:
    def test_pubkey_missing_raises(self):
        """Round-3 audit R3-CRIT-3 — empty pubkey raises (no silent ``"".)"""
        from aria.security.auth_service import _pubkey_fingerprint
        with pytest.raises(ValueError):
            _pubkey_fingerprint("")

    def test_pubkey_bad_hex_raises(self):
        from aria.security.auth_service import _pubkey_fingerprint
        with pytest.raises(ValueError):
            _pubkey_fingerprint("not-hex")


class TestRound3IssueRateDictsBounded:
    def test_issue_by_pid_lru_bounded(self, tmp_path: Path):
        """Round-3 audit R3-HIGH-1."""
        import aria.security.auth_service as auth_mod
        from aria.security.session_store import SessionStore
        # Patch the module-level cap to a small value for the test.
        original_cap = auth_mod._MAX_RATE_LIMITER_KEYS
        auth_mod._MAX_RATE_LIMITER_KEYS = 16
        try:
            svc = auth_mod.AuthService(sessions=SessionStore(runtime_dir=tmp_path))
            for i in range(64):
                # Each principal_id distinct → would grow the dict
                # forever under the previous defaultdict.
                try:
                    svc.issue_challenge(f"pid-{i}", client_ip=f"10.0.0.{i % 200}")
                except auth_mod.ChallengeRateLimited:
                    pass
            assert len(svc._issue_by_pid) <= auth_mod._MAX_RATE_LIMITER_KEYS    # noqa: SLF001
            assert len(svc._issue_by_ip) <= auth_mod._MAX_RATE_LIMITER_KEYS    # noqa: SLF001
        finally:
            auth_mod._MAX_RATE_LIMITER_KEYS = original_cap


class TestRound3PerIpUnauthOnly:
    @pytest.mark.asyncio
    async def test_authed_request_does_not_consume_unauth_bucket(self, tmp_path: Path):
        """Round-3 audit R3-HIGH-2 — many authed tenants behind a
        shared NAT shouldn't get throttled by the unauth budget."""
        from aiohttp.test_utils import TestServer, TestClient
        from aria.products.conjunction_screener.service import (
            create_app, UNAUTH_RATE_PER_MIN_PER_IP,
        )
        from aria.products.conjunction_screener.tenants import TenantStore
        store = TenantStore(tmp_path / "t.sqlite3")
        t = store.create_tenant("acme",
                                rate_limit_per_min=UNAUTH_RATE_PER_MIN_PER_IP * 4,
                                rate_limit_per_day=10_000)
        app = create_app(tenant_store=store, admin_token_hex="A" * 64)
        srv = TestServer(app)
        client = TestClient(srv)
        await client.start_server()
        try:
            # Submit 2x the unauth budget under valid auth headers —
            # all should succeed because authed traffic does NOT touch
            # the unauth bucket.
            for _ in range(UNAUTH_RATE_PER_MIN_PER_IP * 2):
                r = await client.get(
                    "/v1/usage",
                    headers={"X-ARIA-Token": t.api_key_hex},
                )
                assert r.status == 200, await r.text()
        finally:
            await client.close()


class TestRound3CorsWildcardRefusedInProduction:
    def test_runtime_check_refuses_cors_wildcard(self, monkeypatch):
        """Round-3 audit R3-HIGH-7."""
        from aria.security.guard import runtime_check_environment
        # Build a baseline that passes the other prod gates so we can
        # isolate the CORS-wildcard finding.
        monkeypatch.setenv("ARIA_ENV", "prod")
        monkeypatch.setenv("ARIA_HOST", "127.0.0.1")
        monkeypatch.setenv("ARIA_AUTH_REQUIRED", "1")
        monkeypatch.setenv("ARIA_TENANT_KEY_HMAC_HEX", "a" * 64)
        monkeypatch.setenv("ARIA_CORS_ORIGIN", "*")
        result = runtime_check_environment()
        assert any("CORS" in i or "cors" in i.lower() for i in result.issues)
        # Specific allowlist passes.
        monkeypatch.setenv("ARIA_CORS_ORIGIN", "https://app.example.com")
        result = runtime_check_environment()
        assert all("CORS" not in i and "cors" not in i.lower() for i in result.issues)

    def test_runtime_check_refuses_zero_zero_zero_zero_trusted_proxy(self, monkeypatch):
        """Round-3 audit R3-HIGH-7."""
        from aria.security.guard import runtime_check_environment
        monkeypatch.setenv("ARIA_ENV", "prod")
        monkeypatch.setenv("ARIA_HOST", "127.0.0.1")
        monkeypatch.setenv("ARIA_AUTH_REQUIRED", "1")
        monkeypatch.setenv("ARIA_TENANT_KEY_HMAC_HEX", "a" * 64)
        monkeypatch.setenv("ARIA_TRUSTED_PROXIES", "0.0.0.0/0")
        result = runtime_check_environment()
        assert any("0.0.0.0/0" in i for i in result.issues)


class TestRound3SafeStorageLengthLeakClosed:
    """Round-3 audit R3-HIGH-10 — the wrapper hides sensitive keys
    from ``length()`` and ``key()`` so an XSS payload cannot use them
    to enumerate token-like keys."""

    def test_typescript_file_filters_sensitive_in_length(self):
        path = (Path(__file__).resolve().parents[2]
                / "web" / "src" / "safeStorage.ts")
        text = path.read_text()
        # The implementation must iterate keys and skip sensitive ones
        # rather than returning ``window.localStorage.length`` raw.
        assert "if (k && !SENSITIVE_KEY_RE.test(k)) n += 1" in text
        # And ``key(index)`` must skip sensitive ones too.
        assert "if (!k || SENSITIVE_KEY_RE.test(k)) continue" in text


class TestRound3CounterFlushIsAtomic:
    def test_flush_counters_is_durable(self, tmp_path: Path):
        """Round-3 audit R3-HIGH-4."""
        from aria.security.session_store import SessionStore
        s = SessionStore(runtime_dir=tmp_path)
        sess = s.create("crew.beta", "crew")
        for _ in range(3):
            s.increment_counter(sess.token)
        s.flush_counters()
        # File exists, contents readable, mode 0o600.
        path = tmp_path / "session_counters.json"
        assert path.is_file()
        import json
        d = json.loads(path.read_text())
        assert d.get("crew.beta", 0) >= 3
        # 0o600 perms (Linux only).
        if os.name == "posix":
            mode = path.stat().st_mode & 0o777
            assert mode == 0o600


