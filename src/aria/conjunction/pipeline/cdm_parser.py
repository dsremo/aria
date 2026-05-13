"""
CCSDS Conjunction Data Message (CDM) parser.

Parses CDMs in KVN (Keyword-Value Notation) text format as received
from 18 SDS, Space-Track, or TraCSS.

Extracts:
  - TCA, miss distance, relative velocity
  - Object designators and names
  - State vectors for both objects
  - Covariance matrices (lower-triangle RTN)
  - Collision probability and method

Reference: CCSDS 508.0-B-1 (Conjunction Data Message)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np


@dataclass
class ParsedCDM:
    """Structured data extracted from a CCSDS CDM."""

    # Header
    ccsds_cdm_vers: str = ""
    creation_date: datetime | None = None
    originator: str = ""
    message_id: str = ""

    # Relative metadata
    tca: datetime | None = None
    miss_distance_km: float = 0.0
    relative_speed_km_s: float = 0.0
    relative_position_r: float = 0.0
    relative_position_t: float = 0.0
    relative_position_n: float = 0.0

    # Probability
    collision_probability: float = 0.0
    collision_probability_method: str = ""

    # Object 1
    object1_designator: str = ""
    object1_name: str = ""
    object1_object_type: str = ""
    object1_position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    object1_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    object1_covariance_rtn: np.ndarray = field(default_factory=lambda: np.zeros((3, 3)))
    object1_hard_body_radius_m: float = 0.0

    # Object 2
    object2_designator: str = ""
    object2_name: str = ""
    object2_object_type: str = ""
    object2_position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    object2_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    object2_covariance_rtn: np.ndarray = field(default_factory=lambda: np.zeros((3, 3)))
    object2_hard_body_radius_m: float = 0.0

    # Raw fields (for anything not explicitly parsed)
    raw_fields: dict = field(default_factory=dict)


def parse_cdm(text: str) -> ParsedCDM:
    """Parse a CCSDS CDM in KVN text format.

    Args:
        text: CDM text content

    Returns:
        ParsedCDM with extracted fields
    """
    cdm = ParsedCDM()
    current_object = 0  # 0=header, 1=object1, 2=object2

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("!"):
            continue

        # Parse KEY = VALUE
        match = re.match(r'^(\S+)\s*=\s*(.+?)(?:\s*\[.*\])?\s*$', line)
        if not match:
            continue

        key = match.group(1).upper()
        value = match.group(2).strip()

        # Store raw
        cdm.raw_fields[key] = value

        # Track which object section we're in
        if key == "OBJECT":
            if "1" in value or value == "OBJECT1":
                current_object = 1
            elif "2" in value or value == "OBJECT2":
                current_object = 2
            continue

        # Header fields
        if key == "CCSDS_CDM_VERS":
            cdm.ccsds_cdm_vers = value
        elif key == "CREATION_DATE":
            cdm.creation_date = _parse_datetime(value)
        elif key == "ORIGINATOR":
            cdm.originator = value
        elif key == "MESSAGE_ID":
            cdm.message_id = value
        elif key == "TCA":
            cdm.tca = _parse_datetime(value)
        elif key == "MISS_DISTANCE":
            cdm.miss_distance_km = float(value)
        elif key == "RELATIVE_SPEED":
            cdm.relative_speed_km_s = float(value)
        elif key == "RELATIVE_POSITION_R":
            cdm.relative_position_r = float(value)
        elif key == "RELATIVE_POSITION_T":
            cdm.relative_position_t = float(value)
        elif key == "RELATIVE_POSITION_N":
            cdm.relative_position_n = float(value)
        elif key == "COLLISION_PROBABILITY":
            cdm.collision_probability = float(value)
        elif key == "COLLISION_PROBABILITY_METHOD":
            cdm.collision_probability_method = value

        # Object-specific fields
        elif current_object == 1:
            _parse_object_field(cdm, key, value, 1)
        elif current_object == 2:
            _parse_object_field(cdm, key, value, 2)

    return cdm


def _parse_object_field(cdm: ParsedCDM, key: str, value: str, obj_num: int) -> None:
    """Parse a field belonging to object 1 or 2."""
    prefix = f"object{obj_num}_"

    if key == "OBJECT_DESIGNATOR":
        setattr(cdm, f"{prefix}designator", value)
    elif key == "OBJECT_NAME":
        setattr(cdm, f"{prefix}name", value)
    elif key == "OBJECT_TYPE":
        setattr(cdm, f"{prefix}object_type", value)

    # State vector
    pos = getattr(cdm, f"{prefix}position")
    vel = getattr(cdm, f"{prefix}velocity")
    if key == "X":
        pos[0] = float(value)
    elif key == "Y":
        pos[1] = float(value)
    elif key == "Z":
        pos[2] = float(value)
    elif key == "X_DOT":
        vel[0] = float(value)
    elif key == "Y_DOT":
        vel[1] = float(value)
    elif key == "Z_DOT":
        vel[2] = float(value)

    # RTN Covariance (lower triangle)
    cov = getattr(cdm, f"{prefix}covariance_rtn")
    cov_map = {
        "CR_R": (0, 0), "CT_R": (1, 0), "CT_T": (1, 1),
        "CN_R": (2, 0), "CN_T": (2, 1), "CN_N": (2, 2),
    }
    if key in cov_map:
        i, j = cov_map[key]
        cov[i, j] = float(value)
        cov[j, i] = float(value)  # symmetric


def _parse_datetime(s: str) -> datetime:
    """Parse CCSDS datetime format: YYYY-MM-DDTHH:MM:SS.SSS"""
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s}")
