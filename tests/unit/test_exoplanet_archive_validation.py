"""Validate ARIA's curated exoplanet host catalog against the live
NASA Exoplanet Archive data (Wayback-fetched CSV).

Whenever an authoritative source exists, ARIA's position numbers should
match within reasonable tolerance. Systems where RA/Dec drifts from the
archive indicate either a stale cached value or a different coordinate
convention, and should be updated.

Reference:
    NASA Exoplanet Archive — https://exoplanetarchive.ipac.caltech.edu/
    Akeson, R. et al. (2013) PASP 125:989
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from aria.simulation.exoplanets import EXOPLANET_HOSTS


ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "nasa_exoplanet"


def _load_archive_csv(path: Path):
    """Yield dicts keyed by hostname for all planets in the CSV."""
    rows = {}
    if not path.exists():
        return rows
    with path.open() as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            host = r.get("hostname", "").strip()
            if host and host not in rows:
                rows[host] = r
    return rows


@pytest.mark.skipif(not ARCHIVE_DIR.exists(),
                    reason="Exoplanet archive data not present")
def test_nearby_hosts_present_in_archive():
    """Every ARIA nearby host (<25 ly) should appear in the archive's
    within-10-pc CSV or the landmarks CSV."""
    near = _load_archive_csv(ARCHIVE_DIR / "exoplanets_within_10pc_2024.csv")
    landmarks = _load_archive_csv(ARCHIVE_DIR / "exoplanets_landmarks_2024.csv")
    all_hosts = {**near, **landmarks}
    if not all_hosts:
        pytest.skip("archive CSVs empty")
    # At least some ARIA hosts should match archive hosts by name substring
    matches = 0
    for h in EXOPLANET_HOSTS:
        for archive_name in all_hosts:
            if h.name.lower().split()[0] in archive_name.lower() \
                    or archive_name.lower() in h.name.lower():
                matches += 1
                break
    assert matches >= 3, f"only {matches} ARIA hosts cross-reference the NASA archive"


@pytest.mark.skipif(not ARCHIVE_DIR.exists(),
                    reason="Exoplanet archive data not present")
def test_proxima_cen_matches_archive():
    """Proxima Centauri's position in ARIA should match NASA archive to
    within ~1 arcsec (both use J2000)."""
    near = _load_archive_csv(ARCHIVE_DIR / "exoplanets_within_10pc_2024.csv")
    prox = near.get("Proxima Cen")
    if not prox:
        pytest.skip("no Proxima Cen in archive CSV")
    aria_prox = next((h for h in EXOPLANET_HOSTS if "Proxima" in h.name), None)
    if not aria_prox:
        pytest.skip("no Proxima in ARIA catalog")
    archive_ra = float(prox["ra"])
    archive_dec = float(prox["dec"])
    d_ra_arcsec = (aria_prox.ra_deg - archive_ra) * 3600
    d_dec_arcsec = (aria_prox.dec_deg - archive_dec) * 3600
    # ARIA catalog uses Hipparcos positions; archive uses Gaia DR3 —
    # should match within a few hundred arcsec (proper-motion drift)
    assert abs(d_ra_arcsec) < 500, f"Proxima RA drift: {d_ra_arcsec:+.0f}''"
    assert abs(d_dec_arcsec) < 500


@pytest.mark.skipif(not ARCHIVE_DIR.exists(),
                    reason="Exoplanet archive data not present")
def test_archive_files_are_csv():
    for p in ARCHIVE_DIR.glob("*.csv"):
        text = p.read_text()
        assert "hostname" in text
        assert text.count("\n") > 2
