"""Tests for CCSDS CDM parser."""

from datetime import datetime

import numpy as np
import pytest

from aria.conjunction.pipeline.cdm_parser import ParsedCDM, _parse_datetime, parse_cdm

# ---------------------------------------------------------------------------
# Sample CDM text
# ---------------------------------------------------------------------------

SAMPLE_CDM = """\
CCSDS_CDM_VERS = 2.0
CREATION_DATE = 2024-03-15T10:00:00.000
ORIGINATOR = 18 SDS
MESSAGE_ID = CDM-20240315-001

TCA = 2024-03-16T14:30:00.000
MISS_DISTANCE = 1.234
RELATIVE_SPEED = 7.512
RELATIVE_POSITION_R = 0.500
RELATIVE_POSITION_T = 1.100
RELATIVE_POSITION_N = 0.200

COLLISION_PROBABILITY = 1.23e-04
COLLISION_PROBABILITY_METHOD = FOSTER-1992

OBJECT = OBJECT1
OBJECT_DESIGNATOR = 25544
OBJECT_NAME = ISS (ZARYA)
OBJECT_TYPE = PAYLOAD
X = 6780.0
Y = 100.0
Z = -200.0
X_DOT = 0.1
Y_DOT = 7.66
Z_DOT = 0.05
CR_R = 0.100
CT_R = 0.020
CT_T = 0.400
CN_R = 0.010
CN_T = 0.030
CN_N = 0.200

OBJECT = OBJECT2
OBJECT_DESIGNATOR = 99999
OBJECT_NAME = COSMOS 2251 DEB
OBJECT_TYPE = DEBRIS
X = 6781.0
Y = 101.2
Z = -199.5
X_DOT = -0.2
Y_DOT = -7.60
Z_DOT = 0.10
CR_R = 0.050
CT_R = 0.010
CT_T = 0.200
CN_R = 0.005
CN_T = 0.015
CN_N = 0.100
"""

MINIMAL_CDM = """\
CCSDS_CDM_VERS = 2.0
TCA = 2024-01-15T06:00:00
MISS_DISTANCE = 0.5
"""


# ---------------------------------------------------------------------------
# _parse_datetime
# ---------------------------------------------------------------------------

class TestParseDatetime:

    def test_fractional_seconds(self):
        dt = _parse_datetime("2024-03-15T10:00:00.500")
        assert dt.year == 2024
        assert dt.month == 3
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.microsecond == 500000

    def test_no_fractional_seconds(self):
        dt = _parse_datetime("2024-03-15T10:00:00")
        assert dt == datetime(2024, 3, 15, 10, 0, 0)

    def test_with_spaces_format(self):
        dt = _parse_datetime("2024-03-15 10:00:00.000")
        assert dt.year == 2024

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            _parse_datetime("not-a-date")

    def test_strips_whitespace(self):
        dt = _parse_datetime("  2024-03-15T10:00:00  ")
        assert dt.year == 2024


# ---------------------------------------------------------------------------
# parse_cdm — header fields
# ---------------------------------------------------------------------------

class TestParseCDMHeader:

    def test_version(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.ccsds_cdm_vers == "2.0"

    def test_creation_date(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.creation_date == datetime(2024, 3, 15, 10, 0, 0)

    def test_originator(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.originator == "18 SDS"

    def test_message_id(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.message_id == "CDM-20240315-001"

    def test_tca(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.tca == datetime(2024, 3, 16, 14, 30, 0)

    def test_miss_distance(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.miss_distance_km == pytest.approx(1.234)

    def test_relative_speed(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.relative_speed_km_s == pytest.approx(7.512)

    def test_relative_position_components(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.relative_position_r == pytest.approx(0.500)
        assert cdm.relative_position_t == pytest.approx(1.100)
        assert cdm.relative_position_n == pytest.approx(0.200)

    def test_collision_probability(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.collision_probability == pytest.approx(1.23e-4)

    def test_collision_probability_method(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.collision_probability_method == "FOSTER-1992"


# ---------------------------------------------------------------------------
# parse_cdm — object fields
# ---------------------------------------------------------------------------

class TestParseCDMObjects:

    def test_object1_designator(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.object1_designator == "25544"

    def test_object1_name(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.object1_name == "ISS (ZARYA)"

    def test_object1_type(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.object1_object_type == "PAYLOAD"

    def test_object2_designator(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.object2_designator == "99999"

    def test_object2_name(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.object2_name == "COSMOS 2251 DEB"

    def test_object2_type(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert cdm.object2_object_type == "DEBRIS"

    def test_object1_position(self):
        cdm = parse_cdm(SAMPLE_CDM)
        np.testing.assert_allclose(cdm.object1_position, [6780.0, 100.0, -200.0])

    def test_object1_velocity(self):
        cdm = parse_cdm(SAMPLE_CDM)
        np.testing.assert_allclose(cdm.object1_velocity, [0.1, 7.66, 0.05])

    def test_object2_position(self):
        cdm = parse_cdm(SAMPLE_CDM)
        np.testing.assert_allclose(cdm.object2_position, [6781.0, 101.2, -199.5])

    def test_object2_velocity(self):
        cdm = parse_cdm(SAMPLE_CDM)
        np.testing.assert_allclose(cdm.object2_velocity, [-0.2, -7.60, 0.10])

    def test_object1_covariance_diagonal(self):
        cdm = parse_cdm(SAMPLE_CDM)
        cov = cdm.object1_covariance_rtn
        assert cov.shape == (3, 3)
        assert cov[0, 0] == pytest.approx(0.100)  # CR_R
        assert cov[1, 1] == pytest.approx(0.400)  # CT_T
        assert cov[2, 2] == pytest.approx(0.200)  # CN_N

    def test_covariance_symmetric(self):
        cdm = parse_cdm(SAMPLE_CDM)
        cov = cdm.object1_covariance_rtn
        np.testing.assert_allclose(cov, cov.T)

    def test_object2_covariance(self):
        cdm = parse_cdm(SAMPLE_CDM)
        cov = cdm.object2_covariance_rtn
        assert cov[0, 0] == pytest.approx(0.050)
        assert cov[1, 0] == pytest.approx(0.010)
        assert cov[0, 1] == pytest.approx(0.010)  # symmetric


# ---------------------------------------------------------------------------
# parse_cdm — edge cases
# ---------------------------------------------------------------------------

class TestParseCDMEdgeCases:

    def test_minimal_cdm(self):
        cdm = parse_cdm(MINIMAL_CDM)
        assert cdm.ccsds_cdm_vers == "2.0"
        assert cdm.miss_distance_km == pytest.approx(0.5)
        assert cdm.tca == datetime(2024, 1, 15, 6, 0, 0)

    def test_empty_string(self):
        cdm = parse_cdm("")
        assert isinstance(cdm, ParsedCDM)
        assert cdm.miss_distance_km == 0.0

    def test_comment_lines_ignored(self):
        cdm_with_comments = "! This is a comment\nMISS_DISTANCE = 2.5\n! Another comment\n"
        cdm = parse_cdm(cdm_with_comments)
        assert cdm.miss_distance_km == pytest.approx(2.5)

    def test_blank_lines_ignored(self):
        cdm = parse_cdm("\n\n\nMISS_DISTANCE = 3.0\n\n")
        assert cdm.miss_distance_km == pytest.approx(3.0)

    def test_raw_fields_populated(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert "MISS_DISTANCE" in cdm.raw_fields
        assert "TCA" in cdm.raw_fields

    def test_unit_annotation_in_value_stripped(self):
        """Values like '1.234 [km]' should parse correctly."""
        cdm_with_units = "MISS_DISTANCE = 1.5 [km]\n"
        cdm = parse_cdm(cdm_with_units)
        assert cdm.miss_distance_km == pytest.approx(1.5)

    def test_returns_parsed_cdm_instance(self):
        cdm = parse_cdm(SAMPLE_CDM)
        assert isinstance(cdm, ParsedCDM)
