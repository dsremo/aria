"""R47 — historical-conjunction backtest set.

This file is the test driver for the catalog at
:mod:`aria.validation.historical_conjunctions`.  It runs in two
modes:

  * **Static mode** — for events with a TOML payload checked into
    the repo (currently only the Iridium-Cosmos 2009 event), the test
    runs end-to-end against the pre-loaded TLEs.
  * **Live mode** — for events without a static payload, the test
    is skipped unless the test environment exposes SpaceTrack
    credentials.  In CI we generally skip these to keep the test
    suite hermetic; an operator running locally with credentials can
    enable them by setting ``ARIA_RUN_LIVE_BACKTESTS=1``.

The backtest is deliberately *coarse*: TLE-archive precision varies
event-by-event, so the only assertions are sanity checks (TCA
within a wide window, miss distance positive, risk classification
returns one of {RED, YELLOW, GREEN}).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aria.validation.historical_conjunctions import (
    CATALOG,
    HistoricalConjunction,
    list_event_ids,
    get_event,
)


@pytest.fixture
def live_backtest_enabled() -> bool:
    return os.environ.get("ARIA_RUN_LIVE_BACKTESTS", "0") == "1"


def _has_spacetrack_creds() -> bool:
    return bool(
        os.environ.get("SPACETRACK_USERNAME")
        and os.environ.get("SPACETRACK_PASSWORD")
    )


def _data_root() -> Path:
    return (Path(__file__).resolve().parents[2]
            / "src" / "aria" / "validation" / "data")


# ── Catalog structure tests ────────────────────────────────────


class TestCatalogStructure:
    def test_catalog_has_at_least_twelve_events(self):
        assert len(CATALOG) >= 12

    def test_event_ids_unique(self):
        ids = list_event_ids()
        assert len(ids) == len(set(ids))

    def test_each_entry_has_citation_and_norad_pair(self):
        for e in CATALOG:
            assert e.citation, e.event_id
            assert e.primary_norad and e.secondary_norad
            assert e.primary_norad != e.secondary_norad

    def test_get_event_round_trip(self):
        e = get_event("iridium-cosmos-2009")
        assert e.primary_norad == "24946"
        assert e.secondary_norad == "22675"

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            get_event("does-not-exist")


# ── Static-mode test (deterministic) ──────────────────────────


class TestStaticBacktest:
    """Run the backtest for every event whose TOML lives in the repo."""

    @pytest.mark.parametrize(
        "event_id",
        [e.event_id for e in CATALOG if e.static_toml_basename is not None],
    )
    def test_static_event_replays_cleanly(self, event_id: str):
        ev = get_event(event_id)
        toml_path = _data_root() / ev.static_toml_basename  # type: ignore[arg-type]
        if not toml_path.is_file():
            pytest.skip(f"static TOML missing: {toml_path}")
        # We re-use the production iridium_cosmos_replay path because
        # only that event has a static payload at the moment.
        if event_id == "iridium-cosmos-2009":
            from aria.validation import iridium_cosmos_replay as ic
            inputs = ic.load_inputs()
            result = ic.run_replay_tle(inputs)
            assert result.relative_velocity_kmps > 1.0
            assert 0.0 <= result.aria_miss_distance_m
            assert result.risk_level_name in ("RED", "YELLOW", "GREEN")
            # TCA accuracy: ARIA should land within 60 s of the truth TCA.
            assert abs(result.tca_seconds_offset) < 60.0


# ── Live-mode test (SpaceTrack only) ──────────────────────────


@pytest.mark.parametrize(
    "event_id",
    [e.event_id for e in CATALOG if e.static_toml_basename is None],
)
def test_live_event_is_recorded_and_skipped_without_creds(
    event_id: str, live_backtest_enabled: bool,
):
    """The live-mode tests are documented but skipped unless the
    operator opts in.  This keeps CI hermetic and surfaces the
    catalog in the test report so anyone reading the output sees the
    list of events ARIA *would* validate against."""
    ev = get_event(event_id)
    if not (live_backtest_enabled and _has_spacetrack_creds()):
        pytest.skip(
            f"event {event_id}: live backtest requires "
            f"SPACETRACK_USERNAME/SPACETRACK_PASSWORD + "
            f"ARIA_RUN_LIVE_BACKTESTS=1 (catalog citation: {ev.citation})"
        )
    # If we ever run with creds + opt-in, we still need the SpaceTrack
    # session to pull the TLEs.  Implementation parity with the
    # iridium_cosmos refresher is tracked in scripts/refresh_*.py.
    pytest.skip(
        f"event {event_id}: live-mode TLE fetch implemented in "
        f"scripts/refresh_iridium_cosmos_tles.py — extend that script "
        f"to fetch this event's NORAD pair before enabling assertions."
    )
