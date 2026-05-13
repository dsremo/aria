"""R50 — security guard library + breach-class regression tests.

Each ``test_*`` exercises a defence the 51-round audit identified.  The
tests double as a regression net so a future refactor can't silently
weaken the production hardening surface.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from aria.security.guard import (
    GuardError,
    HardenConfig,
    JSONTooDeep,
    PickleBlocked,
    SSRFBlocked,
    XMLDisallowed,
    ZipUnsafe,
    harden_aiohttp_app,
    mfa_admin_check,
    safe_json_loads,
    safe_pickle_block,
    safe_xml_fromstring,
    safe_yaml_load,
    safe_zip_extract,
    sanitise_for_log,
    validate_outbound_url,
)


@pytest.fixture(autouse=True)
def _isolate_guard_plugins():
    """Clear round-by-round plugins so they don't interfere with the
    guard-library tests that probe the bare-foundation behaviour.
    """
    from aria.security.plugins import clear_for_tests
    clear_for_tests()
    yield
    clear_for_tests()


# ── R15: SSRF — direct private IPs ─────────────────────────────────


class TestSSRFGuard:
    @pytest.mark.parametrize("url", [
        "http://169.254.169.254/latest/meta-data/",   # AWS metadata
        "http://metadata.google.internal/",
        "https://127.0.0.1/admin",
        "https://10.0.0.5/",
        "https://192.168.1.1/",
        "https://[::1]/",
    ])
    def test_blocks_private_targets(self, url):
        with pytest.raises(SSRFBlocked):
            validate_outbound_url(url, allowed_schemes=("http", "https"))

    def test_blocks_non_https_by_default(self):
        with pytest.raises(SSRFBlocked):
            validate_outbound_url("http://example.com/")

    def test_blocks_file_scheme(self):
        with pytest.raises(SSRFBlocked):
            validate_outbound_url(
                "file:///etc/passwd", allowed_schemes=("https",),
            )

    def test_allowlist_rejects_unlisted(self):
        with pytest.raises(SSRFBlocked):
            validate_outbound_url(
                "https://celestrak.org/x",
                host_allowlist=("ntrs.nasa.gov",),
            )

    def test_allowlist_accepts_subdomain(self, monkeypatch):
        # data.celestrak.org → suffix-match against celestrak.org.  We mock
        # DNS so the test does not require live internet (the lookup is the
        # post-allowlist step that proves the resolved IP isn't private).
        import socket as _socket

        def _fake_getaddrinfo(host, port, *_a, **_kw):
            return [(2, 1, 6, "", ("8.8.8.8", port or 0))]

        monkeypatch.setattr(_socket, "getaddrinfo", _fake_getaddrinfo)
        validate_outbound_url(
            "https://data.celestrak.org/x",
            host_allowlist=("celestrak.org",),
        )


# ── R12 / B301 / safe_pickle_block ─────────────────────────────────


class TestPickleBlocked:
    def test_always_raises(self):
        with pytest.raises(PickleBlocked):
            safe_pickle_block(b"<arbitrary pickle>")


# ── R13: XML XXE / DOCTYPE / billion-laughs ────────────────────────


class TestXMLGuard:
    def test_blocks_doctype(self):
        with pytest.raises(XMLDisallowed):
            safe_xml_fromstring(
                b"<!DOCTYPE foo [<!ENTITY x SYSTEM 'file:///etc/passwd'>]>"
                b"<a>&x;</a>"
            )

    def test_blocks_entity(self):
        with pytest.raises(XMLDisallowed):
            safe_xml_fromstring(
                b"<!ENTITY lol 'lol'><a>x</a>"
            )

    def test_accepts_normal_xml(self):
        root = safe_xml_fromstring(
            b"<a><b name='x'>1</b></a>"
        )
        assert root.tag == "a"


# ── R39: JSON depth — billion-objects DoS ──────────────────────────


class TestJSONGuard:
    def test_rejects_deep(self):
        deep = "{" * 200 + "1" + "}" * 200  # invalid JSON, but depth still bounds
        # Use a valid deeply-nested object instead:
        deep_obj = '{"a":' * 200 + "1" + "}" * 200
        with pytest.raises((JSONTooDeep, GuardError)):
            safe_json_loads(deep_obj, max_depth=64)

    def test_rejects_oversize(self):
        big = b"[" + b"1," * 1_000_000 + b"1]"
        with pytest.raises(GuardError):
            safe_json_loads(big, max_bytes=1024)

    def test_accepts_normal(self):
        assert safe_json_loads(b'{"a":1,"b":[2,3]}') == {"a": 1, "b": [2, 3]}


# ── R34: ZIP-slip + bomb ──────────────────────────────────────────


class TestZipGuard:
    def test_blocks_zip_slip(self, tmp_path):
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../../../../etc/passwd", "owned")
        dest = tmp_path / "out"
        with pytest.raises(ZipUnsafe):
            safe_zip_extract(archive, dest)

    def test_blocks_too_many_files(self, tmp_path):
        archive = tmp_path / "many.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for i in range(20):
                zf.writestr(f"f{i}.txt", "x")
        dest = tmp_path / "out"
        with pytest.raises(ZipUnsafe):
            safe_zip_extract(archive, dest, max_files=5)

    def test_blocks_decompression_bomb(self, tmp_path):
        archive = tmp_path / "bomb.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            # Highly compressible 1 MB of zeros — ratio >> 100×
            zf.writestr("zeros", b"\x00" * (1 << 20))
        dest = tmp_path / "out"
        with pytest.raises(ZipUnsafe):
            safe_zip_extract(archive, dest, max_ratio=10.0)

    def test_accepts_normal(self, tmp_path):
        archive = tmp_path / "ok.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("a.txt", "alpha")
            zf.writestr("b.txt", "beta")
        dest = tmp_path / "out"
        out = safe_zip_extract(archive, dest)
        assert sorted(out) == ["a.txt", "b.txt"]
        assert (dest / "a.txt").read_text() == "alpha"


# ── R46: log injection — CRLF, bidi, control chars ────────────────


class TestLogSanitiser:
    def test_strips_crlf(self):
        assert "\n" not in sanitise_for_log("hello\nINJECTED")
        assert "\r" not in sanitise_for_log("a\r\nb")

    def test_strips_bidi(self):
        # U+202E RTL-OVERRIDE — Trojan-source class CVE-2021-42574
        assert "‮" not in sanitise_for_log("legit‮mode")

    def test_strips_nul(self):
        assert "\x00" not in sanitise_for_log("a\x00b")

    def test_truncates(self):
        out = sanitise_for_log("x" * 10_000, max_len=128)
        assert out.endswith("...[trunc]")
        assert len(out) <= 128 + 16


# ── Snowflake-class breach (2024) — admin double-token ─────────────


class TestMFAAdminCheck:
    def setup_method(self, _method):
        for k in ("ARIA_ADMIN_TOKEN", "ARIA_ADMIN_OTP_SEED"):
            os.environ.pop(k, None)

    def teardown_method(self, _method):
        for k in ("ARIA_ADMIN_TOKEN", "ARIA_ADMIN_OTP_SEED"):
            os.environ.pop(k, None)

    def _fake_request(self, headers):
        class R:
            pass
        r = R()
        r.headers = headers
        return r

    def test_rejects_when_unconfigured(self):
        # No ARIA_ADMIN_TOKEN env var → always reject.
        assert not mfa_admin_check(self._fake_request({"X-ARIA-Admin-Token": "x"}))

    def test_rejects_wrong_primary(self):
        os.environ["ARIA_ADMIN_TOKEN"] = "real-admin-token"
        assert not mfa_admin_check(
            self._fake_request({"X-ARIA-Admin-Token": "wrong"})
        )

    def test_accepts_primary_only_in_soft_mode(self):
        # No OTP seed configured → soft mode (logged warning, but accepted).
        os.environ["ARIA_ADMIN_TOKEN"] = "tok"
        assert mfa_admin_check(
            self._fake_request({"X-ARIA-Admin-Token": "tok"})
        )

    def test_requires_otp_when_seed_set(self):
        import hmac as _hmac
        import time as _time
        os.environ["ARIA_ADMIN_TOKEN"] = "tok"
        os.environ["ARIA_ADMIN_OTP_SEED"] = "shared-seed"

        # Without OTP → reject.
        assert not mfa_admin_check(
            self._fake_request({"X-ARIA-Admin-Token": "tok"})
        )

        # Compute valid OTP for the current 30-s window.
        win = int(_time.time() // 30)
        otp = _hmac.new(b"shared-seed", str(win).encode(),
                        digestmod="sha256").hexdigest()[:8]
        assert mfa_admin_check(
            self._fake_request({
                "X-ARIA-Admin-Token": "tok",
                "X-ARIA-Admin-OTP": otp,
            })
        )


# ── R22 / R28 — aiohttp middleware: security headers + body cap ────


class TestHardenedApp:
    @pytest.mark.asyncio
    async def test_security_headers_applied(self):
        from aiohttp import web
        from aiohttp.test_utils import TestServer, TestClient

        async def handler(_req):
            return web.json_response({"ok": True})

        app = web.Application()
        app.router.add_get("/x", handler)
        harden_aiohttp_app(app)

        srv = TestServer(app)
        client = TestClient(srv)
        await client.start_server()
        try:
            resp = await client.get("/x")
            assert resp.status == 200
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
            assert resp.headers["X-Frame-Options"] == "DENY"
            assert "Strict-Transport-Security" in resp.headers
            # Audit MED — Referrer-Policy was tightened from no-referrer
            # to strict-origin-when-cross-origin so legitimate same-origin
            # navigation still works while cross-origin leakage is blocked.
            assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
            assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
            assert resp.headers["Cross-Origin-Embedder-Policy"] == "require-corp"
            assert "X-Request-Id" in resp.headers
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_method_guard_blocks_trace(self):
        from aiohttp import web
        from aiohttp.test_utils import TestServer, TestClient

        async def handler(_req):
            return web.json_response({"ok": True})

        app = web.Application()
        app.router.add_route("*", "/x", handler)
        harden_aiohttp_app(app)

        srv = TestServer(app)
        client = TestClient(srv)
        await client.start_server()
        try:
            resp = await client.request("TRACE", "/x")
            assert resp.status in (405, 501)
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_body_size_413(self):
        from aiohttp import web
        from aiohttp.test_utils import TestServer, TestClient

        async def handler(_req):
            return web.json_response({"ok": True})

        app = web.Application()
        app.router.add_post("/x", handler)
        harden_aiohttp_app(
            app, config=HardenConfig(max_request_bytes=1024),
        )

        srv = TestServer(app)
        client = TestClient(srv)
        await client.start_server()
        try:
            resp = await client.post(
                "/x", data=b"x" * 4096,
                headers={"Content-Length": "4096"},
            )
            assert resp.status == 413
        finally:
            await client.close()


# ── YAML safe_load ─────────────────────────────────────────────────


class TestYamlGuard:
    def test_safe_load_basic(self):
        assert safe_yaml_load("a: 1\nb: 2") == {"a": 1, "b": 2}

    def test_rejects_python_object_construct(self):
        # PyYAML's safe_load refuses arbitrary tag handlers
        import yaml
        with pytest.raises(yaml.YAMLError):
            safe_yaml_load("!!python/object/apply:os.system ['echo x']")
