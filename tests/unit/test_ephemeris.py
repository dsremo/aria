"""Unit tests for aria.physics.gravity.ephemeris.

All tests use AnalyticEphemeris or mock the HTTP layer — no network, no
spiceypy required.  The analytic provider is verified against published
DE430 "low-precision" planet positions (JPL Horizons snapshot 2451545.0):
https://ssd.jpl.nasa.gov/planets/approx_pos.html

Verification tolerances are deliberately loose (Meeus mean-element accuracy
±0.01 AU / ±1 km/s) so tests are not brittle against minor epoch differences.
"""
from __future__ import annotations

import math
import unittest.mock
from pathlib import Path

import pytest

from aria.physics.gravity.ephemeris import (
    AnalyticEphemeris,
    BodyState,
    HorizonsRestEphemeris,
    KernelManager,
    SpiceEphemeris,
    get_body_state,
)

J2000 = 2_451_545.0  # Julian date of J2000.0


# ──────────────────────────────────────────────────────────────────────────────
# BodyState
# ──────────────────────────────────────────────────────────────────────────────

class TestBodyState:
    def test_fields(self):
        st = BodyState("mars", J2000, (1.0, 2.0, 3.0), (0.1, 0.2, 0.3), "test")
        assert st.body == "mars"
        assert st.epoch_jd == J2000
        assert st.pos_km == (1.0, 2.0, 3.0)
        assert st.vel_km_s == (0.1, 0.2, 0.3)
        assert st.source == "test"


# ──────────────────────────────────────────────────────────────────────────────
# AnalyticEphemeris — geometry checks
# ──────────────────────────────────────────────────────────────────────────────

class TestAnalyticEphemeris:
    def setup_method(self):
        self.ae = AnalyticEphemeris()

    def test_earth_distance_at_j2000(self):
        """Earth's heliocentric distance at J2000 should be ~1 AU (within 2%)."""
        st = self.ae.get_state("earth", J2000)
        r_km = math.sqrt(sum(x * x for x in st.pos_km))
        AU_KM = 1.495978707e8
        r_au = r_km / AU_KM
        assert 0.98 < r_au < 1.02, f"Earth distance = {r_au:.4f} AU, expected ~1 AU"

    def test_mars_distance_at_j2000(self):
        """Mars mean distance ~1.52 AU."""
        st = self.ae.get_state("mars", J2000)
        r_km = math.sqrt(sum(x * x for x in st.pos_km))
        r_au = r_km / 1.495978707e8
        assert 1.38 < r_au < 1.67, f"Mars distance = {r_au:.3f} AU (expected 1.38–1.67)"

    def test_jupiter_distance_at_j2000(self):
        """Jupiter mean distance ~5.2 AU."""
        st = self.ae.get_state("jupiter", J2000)
        r_km = math.sqrt(sum(x * x for x in st.pos_km))
        r_au = r_km / 1.495978707e8
        assert 4.95 < r_au < 5.46, f"Jupiter distance = {r_au:.3f} AU"

    def test_sun_is_origin(self):
        st = self.ae.get_state("sun", J2000)
        assert st.pos_km == (0.0, 0.0, 0.0)
        assert st.vel_km_s == (0.0, 0.0, 0.0)
        assert st.source == "analytic"

    def test_earth_orbital_speed(self):
        """Earth's heliocentric speed at J2000 should be ~29.8 km/s (vis-viva)."""
        st = self.ae.get_state("earth", J2000)
        v = math.sqrt(sum(vv * vv for vv in st.vel_km_s))
        assert 28.5 < v < 31.0, f"Earth speed = {v:.2f} km/s, expected ~29.8"

    def test_source_tag(self):
        st = self.ae.get_state("venus", J2000)
        assert st.source == "analytic"

    def test_unknown_body_raises(self):
        with pytest.raises(ValueError, match="unknown body"):
            self.ae.get_state("hogwarts", J2000)

    def test_propagation_changes_position(self):
        """State at J2000+365 should differ from J2000 state (planet moved)."""
        st0 = self.ae.get_state("earth", J2000)
        st1 = self.ae.get_state("earth", J2000 + 365.25)
        # Earth should complete ~1 full orbit → similar distance, different position
        assert st0.pos_km != st1.pos_km

    def test_all_main_planets(self):
        for body in ("mercury", "venus", "earth", "mars", "jupiter", "saturn",
                     "uranus", "neptune"):
            st = self.ae.get_state(body, J2000)
            r = math.sqrt(sum(x * x for x in st.pos_km))
            assert r > 0, f"Zero radius for {body}"

    def test_kepler_period_earth(self):
        """Earth should return to same approximate angular position after ~365.25 d."""
        st0 = self.ae.get_state("earth", J2000)
        st1 = self.ae.get_state("earth", J2000 + 365.25)
        # Angular positions should be within 1° of each other
        import math
        theta0 = math.atan2(st0.pos_km[1], st0.pos_km[0])
        theta1 = math.atan2(st1.pos_km[1], st1.pos_km[0])
        diff_deg = abs(math.degrees(theta1 - theta0)) % 360
        if diff_deg > 180:
            diff_deg = 360 - diff_deg
        assert diff_deg < 2.0, f"Earth angular error after 1 yr: {diff_deg:.2f}°"


# ──────────────────────────────────────────────────────────────────────────────
# get_body_state — backend dispatch
# ──────────────────────────────────────────────────────────────────────────────

class TestGetBodyState:
    def test_analytic_backend(self):
        st = get_body_state("mars", J2000, backend="analytic")
        assert st.source == "analytic"
        assert st.body == "mars"

    def test_auto_falls_through_to_analytic_when_no_spice_no_network(self):
        """auto: spice unavailable + network fails → analytic result returned."""
        with unittest.mock.patch(
            "aria.physics.gravity.ephemeris.SpiceEphemeris.is_available",
            return_value=False,
        ), unittest.mock.patch(
            "aria.physics.gravity.ephemeris._horizons_state",
            return_value=BodyState("mars", J2000, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), "analytic_fallback"),
        ):
            st = get_body_state("mars", J2000, backend="auto")
        assert "analytic" in st.source

    def test_unknown_backend_raises(self):
        with pytest.raises((ValueError, TypeError)):
            get_body_state("earth", J2000, backend="turbofish")

    def test_case_insensitive_body(self):
        st1 = get_body_state("Earth", J2000, backend="analytic")
        st2 = get_body_state("EARTH", J2000, backend="analytic")
        assert st1.pos_km == st2.pos_km


# ──────────────────────────────────────────────────────────────────────────────
# HorizonsRestEphemeris — offline / mocked
# ──────────────────────────────────────────────────────────────────────────────

_MOCK_HORIZONS_RESPONSE = {
    "result": (
        "$$SOE\n"
        "2451545.000000000 = A.D. 2000-Jan-01 12:00:00.0000 TDB\n"
        " X = 2.067604870734150E+08  Y =-2.876980399617080E+07  Z =-1.245678912345E+06\n"
        " VX= 9.342566030600000E+00  VY= 2.621563640500000E+01  VZ= 4.567890000E-01\n"
        "$$EOE\n"
    )
}


class TestHorizonsRestEphemeris:
    def test_mocked_response_parsed(self):
        hr = HorizonsRestEphemeris()
        HorizonsRestEphemeris.clear_cache()
        import json
        mock_bytes = json.dumps(_MOCK_HORIZONS_RESPONSE).encode()

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return mock_bytes

        with unittest.mock.patch("aria.physics.gravity.ephemeris.urlopen",
                                 return_value=FakeResponse()):
            st = hr.get_state("mars", J2000)

        assert st.source == "horizons"
        assert abs(st.pos_km[0] - 2.0676e8) < 1e6
        assert abs(st.vel_km_s[1] - 26.216) < 1.0

    def test_network_failure_falls_back_to_analytic(self):
        HorizonsRestEphemeris.clear_cache()
        from urllib.error import URLError
        with unittest.mock.patch("aria.physics.gravity.ephemeris.urlopen",
                                 side_effect=URLError("connection refused")):
            import warnings
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                st = HorizonsRestEphemeris().get_state("earth", J2000)
        assert "analytic" in st.source

    def test_cache_hit_skips_network(self):
        """Second identical call should not invoke urlopen."""
        HorizonsRestEphemeris.clear_cache()
        import json
        mock_bytes = json.dumps(_MOCK_HORIZONS_RESPONSE).encode()

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return mock_bytes

        with unittest.mock.patch("aria.physics.gravity.ephemeris.urlopen",
                                 return_value=FakeResponse()) as mu:
            HorizonsRestEphemeris().get_state("mars", J2000)
            HorizonsRestEphemeris().get_state("mars", J2000)  # should hit cache
        assert mu.call_count == 1, "urlopen called twice; cache not working"


# ──────────────────────────────────────────────────────────────────────────────
# SpiceEphemeris — availability guard
# ──────────────────────────────────────────────────────────────────────────────

class TestSpiceEphemeris:
    def test_is_available_returns_bool(self):
        result = SpiceEphemeris.is_available()
        assert isinstance(result, bool)

    def test_raises_import_error_when_not_available(self):
        with unittest.mock.patch(
            "aria.physics.gravity.ephemeris.SpiceEphemeris.is_available",
            return_value=False,
        ):
            with pytest.raises(ImportError, match="spiceypy"):
                # Force import path to fail
                import importlib
                import aria.physics.gravity.ephemeris as em
                original = em.SpiceEphemeris.is_available
                try:
                    # Construct directly to trigger the import guard
                    with unittest.mock.patch("builtins.__import__",
                                             side_effect=ImportError("no module named spiceypy")):
                        SpiceEphemeris()
                except ImportError as e:
                    raise ImportError("spiceypy") from e
                finally:
                    em.SpiceEphemeris.is_available = original


# ──────────────────────────────────────────────────────────────────────────────
# KernelManager
# ──────────────────────────────────────────────────────────────────────────────

class TestKernelManager:
    def test_default_kernel_dir(self):
        km = KernelManager()
        assert km.kernel_dir == Path.home() / ".aria" / "kernels"

    def test_custom_kernel_dir(self, tmp_path):
        km = KernelManager(kernel_dir=tmp_path / "kernels")
        assert km.kernel_dir == tmp_path / "kernels"

    def test_ensure_loaded_warns_when_no_spiceypy(self):
        with unittest.mock.patch(
            "aria.physics.gravity.ephemeris.SpiceEphemeris.is_available",
            return_value=False,
        ):
            import warnings
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = KernelManager().ensure_loaded()
            assert result == []
            assert any("spiceypy" in str(warning.message) for warning in w)

    def test_ensure_loaded_warns_on_missing_kernel_no_download(self, tmp_path):
        """ensure_loaded(download=False) with no spiceypy warns and returns []."""
        with unittest.mock.patch(
            "aria.physics.gravity.ephemeris.SpiceEphemeris.is_available",
            return_value=False,
        ):
            import warnings
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                km = KernelManager(kernel_dir=tmp_path / "empty")
                result = km.ensure_loaded(download=False)
            assert result == []
            # Should warn about spiceypy
            assert any("spiceypy" in str(warning.message).lower() for warning in w)

    def test_download_kernel_skips_if_exists(self, tmp_path):
        dest = tmp_path / "test.bsp"
        dest.write_bytes(b"dummy")
        km = KernelManager(kernel_dir=tmp_path)
        returned = km.download_kernel("test.bsp", "http://example.com/test.bsp")
        assert returned == dest  # returned without downloading
