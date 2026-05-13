"""Historical SPE catalog tests."""
from __future__ import annotations
import pytest
from aria.simulation.spe_catalog import (
    MAJOR_SPES, events_in_range, worst_case_fluence_per_cm2,
)


def test_catalog_has_notable_events():
    dates = [e.date for e in MAJOR_SPES]
    assert "1972-08-04" in dates    # Seminal Apollo-era event
    assert "1989-10-19" in dates    # Largest since 1972
    assert "2003-10-28" in dates    # Halloween storm
    assert "2012-03-07" in dates


def test_fluences_physically_sized():
    for e in MAJOR_SPES:
        assert e.peak_flux_pfu > 0
        assert e.fluence_per_cm2 > 0
        assert e.duration_hours > 0


def test_events_in_range_filter():
    events = events_in_range("2003-01-01", "2005-01-01")
    assert len(events) >= 3
    dates = [e.date for e in events]
    assert all("2003" in d or "2004" in d for d in dates)


def test_worst_case_scales_with_mission_duration():
    f_1yr = worst_case_fluence_per_cm2(1)
    f_11yr = worst_case_fluence_per_cm2(11)
    f_22yr = worst_case_fluence_per_cm2(22)
    assert f_11yr == f_1yr     # one cycle = baseline
    assert f_22yr > f_11yr
