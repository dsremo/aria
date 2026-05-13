"""JPL SBDB + CAD integration tests.

Tests use unittest.mock.patch on urllib.request.urlopen so CI never
hits the live JPL endpoints. Two opt-in live probes (gated on
ARIA_RUN_LIVE_BACKTESTS=1) verify the integration against the real
upstream — they pull the next 60-day Earth close-approaches and
the orbital elements of (99942) Apophis as smoke-test cases.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from aria.integrations import jpl_sbdb as sbdb_mod


# ── Canned response fixtures ─────────────────────────────────────


_FAKE_CAD_PAYLOAD = {
    "signature": {"version": "1.5", "source": "NASA/JPL CAD"},
    "count": 2,
    "fields": [
        "des", "orbit_id", "jd", "cd", "dist", "dist_min", "dist_max",
        "v_rel", "v_inf", "t_sigma_f", "h",
    ],
    "data": [
        [
            "2024 BX1", "1", "2461022.5", "2026-Apr-30 12:34",
            "0.0023", "0.0022", "0.0024",
            "8.45", "8.32", "00:01", "21.5",
        ],
        [
            "(99942) Apophis", "591", "2462240.5",
            "2029-Apr-13 21:46",
            "0.000254", "0.000253", "0.000255",
            "7.42", "5.85", "00:00", "19.7",
        ],
    ],
}


_FAKE_SBDB_PAYLOAD = {
    "object": {
        "des": "99942",
        "fullname": "99942 Apophis (2004 MN4)",
        "spkid": "20099942",
        "neo": True,
        "pha": True,
    },
    "orbit": {
        "epoch": "2460200.5",
        "elements": [
            {"name": "a", "value": "0.9224"},
            {"name": "e", "value": "0.1914"},
            {"name": "i", "value": "3.339"},
            {"name": "om", "value": "203.95"},
            {"name": "w", "value": "126.66"},
            {"name": "ma", "value": "180.85"},
        ],
    },
    "phys_par": [
        {"name": "H", "value": "19.7"},
        {"name": "diameter", "value": "0.340"},
        {"name": "rot_per", "value": "30.56"},
    ],
}


@pytest.fixture
def isolated_client(tmp_path: Path):
    sbdb_mod.reset_for_test()
    return sbdb_mod.JplSbdbClient(cache_dir=tmp_path / "cache")


def _mock_urlopen(payload: dict):
    body = json.dumps(payload).encode("utf-8")
    response = io.BytesIO(body)
    response.status = 200

    class _Ctx:
        def __enter__(self):
            return response
        def __exit__(self, *_):
            return False

    return _Ctx()


# ── Close-Approach Data (CAD) parser ────────────────────────────


class TestCloseApproachParser:
    def test_parses_two_close_approaches(self, isolated_client):
        with patch.object(
            sbdb_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_CAD_PAYLOAD),
        ):
            approaches = isolated_client.close_approaches(
                date_min="2026-04-29", date_max="+30",
            )
        assert len(approaches) == 2

    def test_parses_apophis_record(self, isolated_client):
        with patch.object(
            sbdb_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_CAD_PAYLOAD),
        ):
            approaches = isolated_client.close_approaches()
        apophis = [
            a for a in approaches if "99942" in a.designation
        ][0]
        assert apophis.dist_au == pytest.approx(0.000254)
        assert apophis.v_rel_kmps == pytest.approx(7.42)
        assert apophis.h_mag == pytest.approx(19.7)
        assert apophis.cd_tca == "2029-Apr-13 21:46"

    def test_designation_normalized_to_string(self, isolated_client):
        with patch.object(
            sbdb_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_CAD_PAYLOAD),
        ):
            approaches = isolated_client.close_approaches()
        for a in approaches:
            assert isinstance(a.designation, str)

    def test_empty_response_returns_empty_list(self, isolated_client):
        empty = {"signature": {}, "count": 0, "fields": [], "data": []}
        with patch.object(
            sbdb_mod.request, "urlopen", return_value=_mock_urlopen(empty),
        ):
            approaches = isolated_client.close_approaches()
        assert approaches == []

    def test_malformed_row_does_not_crash_batch(self, isolated_client):
        partial = {
            **_FAKE_CAD_PAYLOAD,
            "data": [
                _FAKE_CAD_PAYLOAD["data"][0],
                ["broken-row"],   # truncated row, missing most fields
            ],
        }
        with patch.object(
            sbdb_mod.request, "urlopen", return_value=_mock_urlopen(partial),
        ):
            approaches = isolated_client.close_approaches()
        # Either both parse with logged failure or only the good row returns.
        assert len(approaches) >= 1
        assert approaches[0].designation == "2024 BX1"


# ── SBDB lookup parser ──────────────────────────────────────────


class TestSbdbLookupParser:
    def test_apophis_orbital_elements(self, isolated_client):
        with patch.object(
            sbdb_mod.request, "urlopen",
            return_value=_mock_urlopen(_FAKE_SBDB_PAYLOAD),
        ):
            apophis = isolated_client.lookup("99942")
        assert apophis is not None
        assert apophis.designation == "99942"
        assert "Apophis" in apophis.full_name
        assert apophis.semi_major_axis_au == pytest.approx(0.9224)
        assert apophis.eccentricity == pytest.approx(0.1914)
        assert apophis.inclination_deg == pytest.approx(3.339)
        assert apophis.diameter_km == pytest.approx(0.340)
        assert apophis.h_mag == pytest.approx(19.7)
        assert apophis.neo is True
        assert apophis.pha is True

    def test_lookup_missing_object_returns_none(self, isolated_client):
        empty = {"code": 200, "message": "no match"}
        with patch.object(
            sbdb_mod.request, "urlopen", return_value=_mock_urlopen(empty),
        ):
            result = isolated_client.lookup("not-a-real-designation")
        assert result is None


# ── Cache behaviour ─────────────────────────────────────────────


class TestCacheBehaviour:
    def test_cad_second_call_within_ttl_skips_network(
        self, isolated_client,
    ):
        call_count = {"n": 0}

        def _counting_urlopen(*args, **kwargs):
            call_count["n"] += 1
            return _mock_urlopen(_FAKE_CAD_PAYLOAD)

        with patch.object(
            sbdb_mod.request, "urlopen", side_effect=_counting_urlopen,
        ):
            isolated_client.close_approaches(date_min="2026-04-29")
            isolated_client.close_approaches(date_min="2026-04-29")
        assert call_count["n"] == 1

    def test_sbdb_lookup_caches_per_designation(self, isolated_client):
        call_count = {"n": 0}

        def _counting_urlopen(*args, **kwargs):
            call_count["n"] += 1
            return _mock_urlopen(_FAKE_SBDB_PAYLOAD)

        with patch.object(
            sbdb_mod.request, "urlopen", side_effect=_counting_urlopen,
        ):
            isolated_client.lookup("99942")
            isolated_client.lookup("99942")
        assert call_count["n"] == 1

    def test_distinct_queries_get_distinct_cache_files(
        self, tmp_path,
    ):
        client = sbdb_mod.JplSbdbClient(cache_dir=tmp_path / "cache")

        def _fresh_response(*args, **kwargs):
            # Build a NEW BytesIO per call (BytesIO is single-shot).
            return _mock_urlopen(_FAKE_CAD_PAYLOAD)

        with patch.object(
            sbdb_mod.request, "urlopen", side_effect=_fresh_response,
        ):
            client.close_approaches(date_min="2026-04-29", date_max="+30")
            client.close_approaches(date_min="2026-04-29", date_max="+60")

        cache_files = list(
            (tmp_path / "cache" / "cad.api").glob("*.json"),
        )
        assert len(cache_files) == 2


# ── Module singleton ────────────────────────────────────────────


def test_get_jpl_sbdb_client_is_singleton():
    sbdb_mod.reset_for_test()
    a = sbdb_mod.get_jpl_sbdb_client()
    b = sbdb_mod.get_jpl_sbdb_client()
    assert a is b


# ── Live-mode probes (opt-in) ───────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_BACKTESTS") != "1",
    reason="live JPL probe; gated on ARIA_RUN_LIVE_BACKTESTS=1",
)
def test_live_cad_returns_at_least_one_60_day_window(tmp_path):
    """Live probe — fetch next-60-day Earth close-approaches."""
    client = sbdb_mod.JplSbdbClient(cache_dir=tmp_path / "live")
    approaches = client.close_approaches(date_max="+60")
    assert len(approaches) >= 1
    assert all(a.designation for a in approaches)
    assert all(0.0 < a.dist_au < 0.5 for a in approaches)


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_BACKTESTS") != "1",
    reason="live JPL probe; gated on ARIA_RUN_LIVE_BACKTESTS=1",
)
def test_live_sbdb_lookup_apophis(tmp_path):
    """Live probe — fetch (99942) Apophis from JPL SBDB."""
    client = sbdb_mod.JplSbdbClient(cache_dir=tmp_path / "live")
    apophis = client.lookup("99942")
    assert apophis is not None
    assert "Apophis" in apophis.full_name or "99942" in apophis.full_name
    # Apophis published values: a≈0.92 AU, e≈0.19, i≈3.3°.
    assert 0.85 <= apophis.semi_major_axis_au <= 1.0
    assert 0.15 <= apophis.eccentricity <= 0.25
    assert 2.0 <= apophis.inclination_deg <= 5.0
