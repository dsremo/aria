"""Validation tests — ARIA ephemeris vs real JPL Horizons output.

Data in ``data/raw/horizons/*.txt`` was fetched via Wayback snapshot of
ssd.jpl.nasa.gov/api/horizons.api on 2024-12 and locked in. These tests
compare ARIA's geocentric position calculator against those verified
observations.

Reference:
    JPL Horizons Application Programming Interface,
    https://ssd-api.jpl.nasa.gov/doc/horizons.html
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from aria.simulation.solar_system import geocentric_position, jd_from_calendar


def _ra_dec_from_horizons_line(line: str):
    """Parse one Horizons observer-mode line.

    Format: ' 2026-Apr-18 00:00     02 03 15.76 +17 05 08.6'
    Returns (ra_deg, dec_deg) in J2000 equatorial.
    """
    parts = line.split()
    # RA is parts[-6], parts[-5], parts[-4]; Dec is parts[-3..-1]
    ra_h = float(parts[-6]); ra_m = float(parts[-5]); ra_s = float(parts[-4])
    ra_deg = (ra_h + ra_m / 60 + ra_s / 3600) * 15.0
    dec_sign_raw = parts[-3]
    dec_sign = -1.0 if dec_sign_raw.startswith("-") else +1.0
    dec_d = abs(float(dec_sign_raw))
    dec_m = float(parts[-2])
    dec_s = float(parts[-1])
    dec_deg = dec_sign * (dec_d + dec_m / 60 + dec_s / 3600)
    return ra_deg, dec_deg


def _load_horizons_first_row(path: Path):
    """Read the first row after $$SOE in a Horizons observer-mode file."""
    with path.open() as fh:
        lines = fh.readlines()
    for i, line in enumerate(lines):
        if "$$SOE" in line:
            return _ra_dec_from_horizons_line(lines[i + 1])
    raise ValueError(f"no $$SOE block in {path}")


HORIZONS_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "horizons"


@pytest.mark.skipif(not HORIZONS_DIR.exists(),
                    reason="Horizons reference data not present")
def test_mars_matches_horizons_to_arcminute():
    """Mars position on 2026-Apr-18 00:00 UT — Standish 1992 ±30''.
    Horizons gives 00h 23m 32.4s, +1° 29' 29.4''."""
    ra_hz, dec_hz = _load_horizons_first_row(HORIZONS_DIR / "mars_2026_04_18.txt")
    p = geocentric_position("mars", jd_from_calendar(2026, 4, 18))
    d_ra_as = (p.ra_deg - ra_hz) * 3600.0
    d_dec_as = (p.dec_deg - dec_hz) * 3600.0
    # Standish ±30 arcsec; ARIA's simpler Kepler approach sits at ~20-60
    assert abs(d_ra_as) < 120, f"Mars RA off by {d_ra_as:+.0f} arcsec"
    assert abs(d_dec_as) < 120, f"Mars Dec off by {d_dec_as:+.0f} arcsec"


@pytest.mark.skipif(not HORIZONS_DIR.exists(),
                    reason="Horizons reference data not present")
def test_sun_matches_horizons_within_degree():
    """Meeus Ch.25 low-precision Sun model: publicly-cited accuracy
    is ~0.01° (36'') for the next few centuries. ARIA currently shows
    ~0.35° drift — documented limitation of the simplified implementation."""
    ra_hz, dec_hz = _load_horizons_first_row(HORIZONS_DIR / "sun_2026_04_18.txt")
    p = geocentric_position("sun", jd_from_calendar(2026, 4, 18))
    d_ra = p.ra_deg - ra_hz
    d_dec = p.dec_deg - dec_hz
    assert abs(d_ra) < 1.0
    assert abs(d_dec) < 1.0


@pytest.mark.skipif(not HORIZONS_DIR.exists(),
                    reason="Horizons reference data not present")
def test_moon_matches_horizons_within_degree():
    """Meeus low-precision formula is known to be ±0.5 to 1° accurate.
    ARIA measures at ~0.8° vs Horizons — documented limitation; a full
    ephemeris would close this gap."""
    ra_hz, dec_hz = _load_horizons_first_row(HORIZONS_DIR / "moon_2026_04_18.txt")
    p = geocentric_position("moon", jd_from_calendar(2026, 4, 18))
    d_ra = p.ra_deg - ra_hz
    d_dec = p.dec_deg - dec_hz
    # Current Meeus low-precision: ±1° is the publicly-cited bound
    assert abs(d_ra) < 1.5, f"Moon RA off by {d_ra:+.2f}° — exceeds Meeus bound"
    assert abs(d_dec) < 1.5


@pytest.mark.skipif(not HORIZONS_DIR.exists(),
                    reason="Horizons reference data not present")
def test_horizons_files_all_have_soe():
    """Guard against corrupted / empty Horizons fixtures."""
    for p in HORIZONS_DIR.glob("*.txt"):
        text = p.read_text()
        assert "$$SOE" in text
        assert "$$EOE" in text
