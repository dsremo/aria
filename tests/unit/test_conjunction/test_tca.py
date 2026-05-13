"""Tests for TCA (Time of Closest Approach) finder."""

from datetime import datetime

import numpy as np

from aria.conjunction.conjunction.miss_distance import compute_miss_distance
from aria.conjunction.conjunction.tca_finder import TCAFinder
from aria.conjunction.data.tle_parser import TLEParser

# ISS TLE (2008 epoch, known valid checksums)
ISS_LINE1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
ISS_LINE2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"


class TestTCAFinder:
    """Test TCA refinement using Brent's method."""

    def setup_method(self):
        self.iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS")
        self.finder = TCAFinder(coarse_step_s=10.0, search_window_minutes=30.0)

    def test_self_conjunction(self):
        """An object should have zero distance from itself at any time."""
        epoch = self.iss.elements.epoch
        miss, rtn, _, speed, _, _ = compute_miss_distance(self.iss, self.iss, epoch)
        assert miss < 1e-6  # essentially zero

    def test_tca_finder_returns_results(self):
        """TCA finder should return at least one result for a reasonable window."""
        epoch = self.iss.elements.epoch
        results = self.finder.find_tca(self.iss, self.iss, epoch)
        assert len(results) >= 1
        # Self-conjunction → distance should be ~0
        _, dist = results[0]
        assert dist < 0.001


class TestMissDistance:
    def test_rtn_components(self):
        """RTN components should sum (in quadrature) to total miss distance."""
        epoch = datetime(2024, 2, 14, 12, 0, 0)
        iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2)

        miss, rtn, _, speed, _, _ = compute_miss_distance(iss, iss, epoch, check_tle_age=False)

        # RTN magnitude should equal total miss distance
        rtn_mag = float(np.linalg.norm(rtn))
        assert abs(rtn_mag - miss) < 1e-6
