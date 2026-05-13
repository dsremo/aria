"""R45 — SpaceTrack session helper tests (no network).

These tests verify the offline behaviour: env-var contract,
rate-limit accounting, and TLE-line extraction.  Live-network tests
are deliberately not included because they would (a) hit the
SpaceTrack rate limit during CI runs and (b) tie the test pass/fail
state to credential availability.

The live-network round-trip is exercised by
`scripts/refresh_iridium_cosmos_tles.py` which is run manually when
TLEs need refreshing.
"""

from __future__ import annotations

import os

import pytest

from aria.conjunction.data import spacetrack_session as sts


# ── Env-var contract ───────────────────────────────────────────


class TestEnvVarContract:
    def test_missing_env_raises(self, monkeypatch):
        monkeypatch.delenv("SPACETRACK_USERNAME", raising=False)
        monkeypatch.delenv("SPACETRACK_PASSWORD", raising=False)
        with pytest.raises(sts.SpaceTrackAuthError):
            sts.SpaceTrackSession()

    def test_explicit_args_override_env(self, monkeypatch):
        monkeypatch.delenv("SPACETRACK_USERNAME", raising=False)
        monkeypatch.delenv("SPACETRACK_PASSWORD", raising=False)
        # Should not raise — explicit args satisfy the contract.
        s = sts.SpaceTrackSession(username="u", password="p")
        assert s._username == "u"
        assert s._password == "p"

    def test_base_url_default(self, monkeypatch):
        monkeypatch.delenv("SPACETRACK_BASE_URL", raising=False)
        s = sts.SpaceTrackSession(username="u", password="p")
        assert s._base_url == "https://www.space-track.org"

    def test_base_url_override(self, monkeypatch):
        monkeypatch.setenv(
            "SPACETRACK_BASE_URL", "https://staging.space-track.org/",
        )
        s = sts.SpaceTrackSession(username="u", password="p")
        # Trailing slash stripped.
        assert s._base_url == "https://staging.space-track.org"


# ── Rate limiting ──────────────────────────────────────────────


class TestRateLimit:
    def test_minute_window_tracks_calls(self):
        s = sts.SpaceTrackSession(username="u", password="p")
        for _ in range(5):
            s._enforce_rate_limit()
        assert len(s._minute_window) == 5

    def test_hour_window_caps_at_ceiling(self):
        """If the hour window is at the ceiling, the next call raises."""
        s = sts.SpaceTrackSession(username="u", password="p")
        # Pre-fill the hour window above ceiling (skip past minute prune).
        import time
        now = time.time()
        s._hour_window = [now] * sts.RATE_LIMIT_RPH
        s._minute_window = []
        with pytest.raises(sts.SpaceTrackRateLimitError):
            s._enforce_rate_limit()


# ── TLE-line extraction ────────────────────────────────────────


class TestTLEExtract:
    def test_extracts_lines(self):
        record = {
            "TLE_LINE1": "1 24946U 97051C   ...",
            "TLE_LINE2": "2 24946  86.39 ...",
        }
        l1, l2 = sts.SpaceTrackSession.tle_lines(
            sts.SpaceTrackSession, record,
        )
        assert l1.startswith("1 24946")
        assert l2.startswith("2 24946")

    def test_missing_line_raises(self):
        with pytest.raises(sts.SpaceTrackError):
            sts.SpaceTrackSession.tle_lines(
                sts.SpaceTrackSession,
                {"TLE_LINE1": "x"},   # line2 missing
            )


# ── TOML render ────────────────────────────────────────────────


class TestTOMLRender:
    def test_renders_full_block(self):
        d = {
            "primary_norad_id": "24946",
            "primary_name": "IRIDIUM 33",
            "primary_line1": "1 24946U ...",
            "primary_line2": "2 24946 ...",
            "secondary_norad_id": "22675",
            "secondary_name": "COSMOS 2251",
            "secondary_line1": "1 22675U ...",
            "secondary_line2": "2 22675 ...",
        }
        text = sts._render_iridium_cosmos_toml(d)
        assert 'primary_norad_id   = "24946"' in text
        assert 'secondary_norad_id  = "22675"' in text
        assert "truth_collision         = true" in text
