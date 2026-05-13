"""
CCSDS Conjunction Data Message (CDM) v2.0 writer.

Outputs CDMs in KVN (Keyword-Value Notation) text format,
the standard interchange format for conjunction assessment data.

Reference: CCSDS 508.0-B-1 (Conjunction Data Message)
"""

from __future__ import annotations

from datetime import datetime

from aria.conjunction.core.types import CloseApproach


class CDMWriter:
    """Generate CCSDS CDM v2.0 in KVN text format."""

    def __init__(self, originator: str = "DSREMO"):
        self.originator = originator
        self._msg_counter = 0

    def write(self, approach: CloseApproach) -> str:
        """Generate a CDM string for a close approach event.

        Args:
            approach: CloseApproach with computed Pc and states

        Returns:
            CDM in CCSDS KVN text format
        """
        self._msg_counter += 1
        now = datetime.utcnow()

        pc = approach.probability_of_collision or 0.0
        pc_method = "FOSTER-1992"

        lines = [
            "CCSDS_CDM_VERS                     = 2.0",
            "",
            "! ===== HEADER =====",
            f"CREATION_DATE                      = {_fmt_epoch(now)}",
            f"ORIGINATOR                         = {self.originator}",
            f"MESSAGE_ID                         = {self.originator}-{self._msg_counter:06d}",
            f"TCA                                = {_fmt_epoch(approach.tca)}",
            f"MISS_DISTANCE                      = {approach.miss_distance_km:.6f} [km]",
            "",
            "! ===== RELATIVE STATE =====",
            f"RELATIVE_SPEED                     = {approach.relative_velocity_km_s:.6f} [km/s]",
            f"RELATIVE_POSITION_R                = {approach.miss_distance_rtn[0]:.6f} [km]",
            f"RELATIVE_POSITION_T                = {approach.miss_distance_rtn[1]:.6f} [km]",
            f"RELATIVE_POSITION_N                = {approach.miss_distance_rtn[2]:.6f} [km]",
            "",
            "! ===== COLLISION PROBABILITY =====",
            f"COLLISION_PROBABILITY              = {pc:.10e}",
            f"COLLISION_PROBABILITY_METHOD        = {pc_method}",
            "",
            "! ===== OBJECT 1 (PRIMARY) =====",
            "OBJECT                             = OBJECT1",
            f"OBJECT_DESIGNATOR                  = {approach.primary.norad_id}",
            "CATALOG_NAME                       = SATCAT",
            f"OBJECT_NAME                        = {approach.primary.name}",
            f"INTERNATIONAL_DESIGNATOR           = {_intl_designator(approach.primary.tle_line1)}",
            f"OBJECT_TYPE                        = {approach.primary.object_type.value}",
        ]

        # Primary state at TCA
        if approach.primary_state:
            s = approach.primary_state
            lines.extend([
                f"EPOCH                              = {_fmt_epoch(s.epoch)}",
                f"X                                  = {s.position[0]:.6f} [km]",
                f"Y                                  = {s.position[1]:.6f} [km]",
                f"Z                                  = {s.position[2]:.6f} [km]",
                f"X_DOT                              = {s.velocity[0]:.9f} [km/s]",
                f"Y_DOT                              = {s.velocity[1]:.9f} [km/s]",
                f"Z_DOT                              = {s.velocity[2]:.9f} [km/s]",
            ])

        lines.extend([
            "",
            "! ===== OBJECT 2 (SECONDARY) =====",
            "OBJECT                             = OBJECT2",
            f"OBJECT_DESIGNATOR                  = {approach.secondary.norad_id}",
            "CATALOG_NAME                       = SATCAT",
            f"OBJECT_NAME                        = {approach.secondary.name}",
            f"INTERNATIONAL_DESIGNATOR           = {_intl_designator(approach.secondary.tle_line1)}",  # noqa: E501
            f"OBJECT_TYPE                        = {approach.secondary.object_type.value}",
        ])

        # Secondary state at TCA
        if approach.secondary_state:
            s = approach.secondary_state
            lines.extend([
                f"EPOCH                              = {_fmt_epoch(s.epoch)}",
                f"X                                  = {s.position[0]:.6f} [km]",
                f"Y                                  = {s.position[1]:.6f} [km]",
                f"Z                                  = {s.position[2]:.6f} [km]",
                f"X_DOT                              = {s.velocity[0]:.9f} [km/s]",
                f"Y_DOT                              = {s.velocity[1]:.9f} [km/s]",
                f"Z_DOT                              = {s.velocity[2]:.9f} [km/s]",
            ])

        lines.append("")
        return "\n".join(lines)

    def write_many(self, approaches: list[CloseApproach]) -> list[str]:
        """Generate CDMs for multiple approaches."""
        return [self.write(a) for a in approaches]


def _fmt_epoch(dt: datetime) -> str:
    """Format datetime as CCSDS epoch string: YYYY-MM-DDTHH:MM:SS.SSS"""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def _intl_designator(tle_line1: str) -> str:
    """Extract international designator from TLE line 1 (columns 9-17)."""
    try:
        return tle_line1[9:17].strip()
    except (IndexError, AttributeError):
        return "UNKNOWN"
