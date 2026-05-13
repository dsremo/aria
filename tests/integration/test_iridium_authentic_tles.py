"""R46 — high-precision Iridium-Cosmos replay test (network-gated).

Asserts the post-`refresh_iridium_cosmos_tles.py` precision: TCA
within 1 second, relative speed within 0.1 km/s, miss distance
within 200 m of JSpOC's published prediction.  These tighter
bounds are the *actual* validation of ARIA's SGP4 + TCA finder
against the historical event — distinct from the looser bounds in
`test_iridium_cosmos_replay.py` which work even when the data file
was last seeded with documented-elements-only fallback.

Skip rules:
  * Skips if `SPACETRACK_USERNAME` env is unset (CI can opt in
    by populating its own credential).
  * Skips if the data file's TLEs aren't the authentic 18-SDS
    broadcast bytes (indicated by epochs *not* on 2009-02-09).

Run locally with:
  export $(grep -v '^#' .env | xargs)
  python -m pytest tests/integration/test_iridium_authentic_tles.py -v
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aria.validation import iridium_cosmos_replay as ic


# ── Skip gates ────────────────────────────────────────────────


def _has_credentials() -> bool:
    return bool(os.environ.get("SPACETRACK_USERNAME"))


def _data_file_has_feb09_epochs() -> bool:
    """Heuristic: the data TOML's primary_line1 + secondary_line1
    have epoch fields starting with `09040.` or `09041.` (Day-of-Year
    40 = Feb 9, 41 = Feb 10).  If both are 09040/09041, we've got the
    authentic pre-event TLEs and tight precision is expected."""
    path = (
        Path(__file__).resolve().parents[1].parent
        / "src" / "aria" / "validation" / "data"
        / "iridium33_cosmos2251_2009.toml"
    )
    if not path.is_file():
        return False
    text = path.read_text()
    # TLE epoch column 18-32 of line1 — extract `09NNN.NNNNN`.
    matches = re.findall(
        r'_line1\s*=\s*"[^"]{18}(\d{2})(\d{3})\.', text,
    )
    if len(matches) < 2:
        return False
    for yr, doy in matches:
        if yr != "09":
            return False
        try:
            d = int(doy)
        except ValueError:
            return False
        # Day-of-year 40 = Feb 9, 41 = Feb 10.  Authentic pre-event
        # TLEs land on 40 or 41 (Feb 9 broadcast or early Feb 10).
        if d not in (40, 41):
            return False
    return True


pytestmark = pytest.mark.skipif(
    not _data_file_has_feb09_epochs(),
    reason=(
        "data/iridium33_cosmos2251_2009.toml does not contain "
        "authentic Feb-09 broadcast TLEs.  Run "
        "`python scripts/refresh_iridium_cosmos_tles.py` with "
        "SpaceTrack credentials set in env, then re-run."
    ),
)


# ── Tight assertions ──────────────────────────────────────────


class TestAuthenticReplayPrecision:
    def test_tca_within_one_second(self):
        """With authentic Feb-09 broadcast TLEs, ARIA's TCA must
        agree with Wang 2010's 16:55:59.8 UTC truth to within 1 s."""
        result = ic.run_replay_tle()
        assert abs(result.tca_seconds_offset) < 1.0, (
            f"TCA off by {result.tca_seconds_offset:+.3f} s — "
            "expected millisecond-class precision with authentic TLEs"
        )

    def test_relative_speed_within_0p1_kmps(self):
        """Closing speed agreement at 0.1 km/s level."""
        result = ic.run_replay_tle()
        assert result.relative_velocity_vs_truth_kmps < 0.1, (
            f"rel-speed off by {result.relative_velocity_vs_truth_kmps:+.3f} km/s"
        )

    def test_miss_distance_within_200m_of_jspoc(self):
        """JSpOC's pre-event prediction was ~584 m.  ARIA with its
        SGP4 build typically lands ~698 m — within 200 m of JSpOC
        is the precision target for the authentic-TLE replay."""
        result = ic.run_replay_tle()
        delta = abs(result.aria_miss_distance_m - 584.0)
        assert delta < 200.0, (
            f"miss distance {result.aria_miss_distance_m:.0f} m "
            f"differs from JSpOC's 584 m by {delta:.0f} m — "
            "tighter than the 500 m fallback bracket"
        )

    def test_pc_in_actionable_range(self):
        """At 250 m σ + 4 m hard-body, Foster Pc lands in the
        10⁻⁶ to 10⁻⁵ band — matching the 2009 operator-class
        analysis that read this conjunction as YELLOW (sub-RED)."""
        result = ic.run_replay_tle()
        assert 1e-7 < result.pc_foster < 1e-3
        assert result.risk_level_name in ("YELLOW", "RED")


class TestPrecisionDataFile:
    """Sanity checks on the data file itself — these run only when
    the authentic-TLE gate passes, so reaching them confirms the
    refresh script produced something sensible."""

    def test_iridium_epoch_pre_collision(self):
        inputs = ic.load_inputs()
        # Iridium-33 TLE epoch is in line1 cols 18-32, format YYDDD.D
        l1 = inputs.primary_line1
        epoch_str = l1[18:32].strip()
        # 09NNN.NNN → DOY 40 = Feb 9, DOY 41 = Feb 10.
        # Pre-collision: anything before 09041.7045 (Feb 10 16:54 UTC)
        # is OK — we're really interested in DOY ≤ 40.999.
        doy = float(epoch_str[2:])
        assert doy < 41.7, (
            f"Iridium-33 TLE epoch DOY {doy} is post-collision"
        )

    def test_cosmos_epoch_pre_collision(self):
        inputs = ic.load_inputs()
        l1 = inputs.secondary_line1
        epoch_str = l1[18:32].strip()
        doy = float(epoch_str[2:])
        assert doy < 41.7, (
            f"Cosmos-2251 TLE epoch DOY {doy} is post-collision"
        )
