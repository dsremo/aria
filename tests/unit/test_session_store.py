"""R32 Phase 2 — session store tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from aria.security.session_store import (
    SessionStore,
    DEFAULT_IDLE_WINDOW_S,
    DEFAULT_ABSOLUTE_WINDOW_S,
)


def _store(tmp_path: Path, **kw) -> SessionStore:
    return SessionStore(runtime_dir=tmp_path, **kw)


class TestCreateAndGet:
    def test_create_returns_distinct_tokens(self, tmp_path):
        s = _store(tmp_path)
        a = s.create("captain.tau", "captain")
        b = s.create("captain.tau", "captain")
        assert a.token != b.token
        assert len(a.token) == 64  # 32 bytes hex

    def test_get_returns_same_session(self, tmp_path):
        s = _store(tmp_path)
        sess = s.create("crew.alpha", "crew")
        assert s.get(sess.token) is not None
        assert s.get(sess.token).principal_id == "crew.alpha"

    def test_get_unknown_token_returns_none(self, tmp_path):
        s = _store(tmp_path)
        assert s.get("0" * 64) is None


class TestExpiry:
    def test_idle_expiry(self, tmp_path):
        # 1 s idle window for the test.
        s = _store(tmp_path, idle_window_s=1.0, absolute_window_s=60.0)
        sess = s.create("crew.alpha", "crew")
        time.sleep(1.5)
        assert s.get(sess.token) is None

    def test_absolute_expiry(self, tmp_path):
        s = _store(tmp_path, idle_window_s=60.0, absolute_window_s=1.0)
        sess = s.create("crew.alpha", "crew")
        time.sleep(1.5)
        assert s.get(sess.token) is None

    def test_touch_extends_idle(self, tmp_path):
        s = _store(tmp_path, idle_window_s=1.0, absolute_window_s=60.0)
        sess = s.create("crew.alpha", "crew")
        time.sleep(0.5)
        s.touch(sess.token)
        time.sleep(0.7)   # would have idle-expired without touch
        assert s.get(sess.token) is not None


class TestRevocation:
    def test_revoke(self, tmp_path):
        s = _store(tmp_path)
        sess = s.create("crew.alpha", "crew")
        assert s.revoke(sess.token)
        assert s.get(sess.token) is None

    def test_revoked_token_persists_across_reload(self, tmp_path):
        s = _store(tmp_path)
        sess = s.create("crew.alpha", "crew")
        s.revoke(sess.token)
        # New store loads revocation log.
        s2 = _store(tmp_path)
        assert s2.get(sess.token) is None

    def test_revoke_all_for_principal(self, tmp_path):
        s = _store(tmp_path)
        a = s.create("crew.alpha", "crew")
        b = s.create("crew.alpha", "crew")
        c = s.create("crew.beta", "crew")
        n = s.revoke_all_for_principal("crew.alpha")
        assert n == 2
        assert s.get(a.token) is None
        assert s.get(b.token) is None
        assert s.get(c.token) is not None


class TestDuress:
    def test_duress_session_caps_lifetime(self, tmp_path):
        s = _store(tmp_path,
                   idle_window_s=DEFAULT_IDLE_WINDOW_S,
                   absolute_window_s=DEFAULT_ABSOLUTE_WINDOW_S)
        sess = s.create("crew.alpha", "crew", duress=True)
        # Duress caps at 30 s — much smaller than the default windows.
        assert (sess.expires_at - sess.created_at) <= 30.5
        assert sess.idle_window_s <= 30.5
        assert sess.duress is True


class TestCounter:
    def test_increment_counter_monotonic(self, tmp_path):
        s = _store(tmp_path)
        sess = s.create("crew.alpha", "crew")
        c1 = s.increment_counter(sess.token)
        c2 = s.increment_counter(sess.token)
        c3 = s.increment_counter(sess.token)
        assert c1 == 1 and c2 == 2 and c3 == 3

    def test_increment_after_revoke_returns_none(self, tmp_path):
        s = _store(tmp_path)
        sess = s.create("crew.alpha", "crew")
        s.revoke(sess.token)
        assert s.increment_counter(sess.token) is None
