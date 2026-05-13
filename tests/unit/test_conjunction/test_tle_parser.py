"""Tests for TLE parsing, Alpha-5 encoding, and orbital element extraction."""

import math

import pytest

from aria.conjunction.data.tle_parser import (
    TLEParseError,
    TLEParser,
    _mean_to_true_anomaly,
    _tle_checksum,
    decode_alpha5,
    encode_alpha5,
)

# ISS (ZARYA) — known valid TLE with correct checksums
ISS_NAME = "ISS (ZARYA)"
ISS_LINE1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
ISS_LINE2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"

# Vanguard 1 — oldest satellite still in orbit, well-known TLE
VANGUARD_LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
VANGUARD_LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


class TestAlpha5:
    """Test Alpha-5 numbering scheme."""

    def test_standard_id(self):
        assert decode_alpha5("25544") == 25544

    def test_alpha5_encoding(self):
        assert decode_alpha5("A1234") == 101234  # A=10, 10*10000 + 1234

    def test_alpha5_high(self):
        assert decode_alpha5("Z9999") == 359999  # Z=35

    def test_encode_standard(self):
        assert encode_alpha5(25544) == "25544"

    def test_encode_extended(self):
        assert encode_alpha5(101234) == "A1234"

    def test_roundtrip(self):
        for original in [25544, 99999, 100000, 101234, 200000, 359999]:
            encoded = encode_alpha5(original)
            decoded = decode_alpha5(encoded)
            assert decoded == original, f"Roundtrip failed for {original}"

    def test_invalid_alpha5(self):
        with pytest.raises(TLEParseError):
            decode_alpha5("")

    def test_leading_zeros(self):
        assert decode_alpha5("00001") == 1


class TestChecksum:
    """Test TLE checksum computation."""

    def test_iss_line1_checksum(self):
        assert _tle_checksum(ISS_LINE1) == int(ISS_LINE1[68])

    def test_iss_line2_checksum(self):
        assert _tle_checksum(ISS_LINE2) == int(ISS_LINE2[68])


class TestTLEParser:
    """Test TLE parsing into SpaceObject."""

    def test_parse_iss(self):
        obj = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name=ISS_NAME)

        assert obj.norad_id == "25544"
        assert obj.name == ISS_NAME
        assert obj.satellite is not None
        assert obj.elements is not None

    def test_iss_orbital_elements(self):
        obj = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2)
        e = obj.elements

        # ISS: ~340 km altitude (2008 epoch), ~51.6° inclination, nearly circular
        assert 6650 < e.semi_major_axis < 6850  # ~6720 km
        assert e.eccentricity < 0.01  # nearly circular
        assert abs(math.degrees(e.inclination) - 51.6) < 0.5
        assert e.perigee_altitude > 250  # km
        assert e.apogee_altitude < 500  # km
        assert 88 < e.period_minutes < 95  # ~91-92 minutes

    def test_iss_apogee_perigee(self):
        obj = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2)
        e = obj.elements

        # Perigee < Apogee (always)
        assert e.perigee_radius < e.apogee_radius
        # Both above Earth's surface
        assert e.perigee_altitude > 0
        assert e.apogee_altitude > 0

    def test_parse_invalid_line1(self):
        with pytest.raises(TLEParseError):
            TLEParser.parse_tle("INVALID LINE", ISS_LINE2)

    def test_parse_bad_checksum(self):
        bad_line1 = ISS_LINE1[:-1] + "0"  # corrupt checksum
        with pytest.raises(TLEParseError):
            TLEParser.parse_tle(bad_line1, ISS_LINE2, validate_checksum=True)

    def test_skip_checksum(self):
        bad_line1 = ISS_LINE1[:-1] + "0"
        # Should not raise when validation is disabled
        obj = TLEParser.parse_tle(bad_line1, ISS_LINE2, validate_checksum=False)
        assert obj.norad_id == "25544"

    def test_parse_multi_tle_3line(self):
        tle_text = f"""{ISS_NAME}
{ISS_LINE1}
{ISS_LINE2}"""
        objects = TLEParser.parse_multi_tle(tle_text)
        assert len(objects) == 1
        assert objects[0].name == ISS_NAME

    def test_parse_multi_tle_2line(self):
        tle_text = f"""{ISS_LINE1}
{ISS_LINE2}"""
        objects = TLEParser.parse_multi_tle(tle_text)
        assert len(objects) == 1

    def test_parse_multi_tle_multiple(self):
        tle_text = f"""{ISS_NAME}
{ISS_LINE1}
{ISS_LINE2}
VANGUARD 1
{VANGUARD_LINE1}
{VANGUARD_LINE2}"""
        objects = TLEParser.parse_multi_tle(tle_text)
        assert len(objects) == 2


class TestKeplerEquation:
    """Test mean anomaly → true anomaly conversion."""

    def test_circular_orbit(self):
        # For e=0, true anomaly = mean anomaly
        for M in [0, 0.5, 1.0, 3.14, 5.0]:
            nu = _mean_to_true_anomaly(M, 0.0)
            assert abs(nu - M) < 1e-10

    def test_known_values(self):
        # e=0.5, M=π → E should be π → ν should be π
        nu = _mean_to_true_anomaly(math.pi, 0.5)
        assert abs(nu - math.pi) < 1e-10

    def test_high_eccentricity(self):
        # Should converge even for high eccentricity
        nu = _mean_to_true_anomaly(1.0, 0.9)
        assert 0 < nu < 2 * math.pi
