"""
CCSDS 508.0-B-1 Conjunction Data Message (CDM) writer.

P1 FIX (Panel 1 ESA): The system ingested CDMs but could not produce them.
Operators need CDMs in CCSDS 508.0-B-1 format to share with satellite operators
and to interoperate with AGI STK, CARA, and national SSA systems.

Supports Key-Value Notation (KVN) format (Section 4 of the standard).
XML format (Annex A) is planned but not implemented here.

Reference: CCSDS 508.0-B-1 "Conjunction Data Message", June 2013.
Available: https://public.ccsds.org/Pubs/508x0b1e2s.pdf

CDM structure:
  HEADER block  — version, classification, creation date, originator
  RELATIVE_METADATA block  — TCA, miss distance, Pc, screening criteria
  OBJECT 1 block  — orbit state, covariance for primary object
  OBJECT 2 block  — orbit state, covariance for secondary object
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CdmObject:
    """Orbital state and metadata for one conjunction object."""

    # Identification
    object_designator: str        # NORAD catalog number or international designator
    object_name: str              # Common name
    international_designator: str = "UNKNOWN"
    object_type: str = "PAYLOAD"  # PAYLOAD | ROCKET BODY | DEBRIS | UNKNOWN

    # Ephemeris
    ref_frame: str = "ITRF"           # reference frame
    gravity_model: str = "EGM-96: 36D 36O"
    atmospheric_model: str = "JACCHIA 70 DCA"
    n_body_perturbations: str = "MOON, SUN"
    solar_rad_pressure: bool = True
    earth_tides: bool = False
    intrack_thrust: bool = False

    # State vector at TCA (ECI, J2000, km and km/s)
    x_km: float = 0.0
    y_km: float = 0.0
    z_km: float = 0.0
    x_dot_km_s: float = 0.0
    y_dot_km_s: float = 0.0
    z_dot_km_s: float = 0.0

    # Covariance (RTN frame, km², km²/s, km²/s²)
    # Upper triangle: CR_R, CT_R, CT_T, CN_R, CN_T, CN_N,
    #                 CRDOT_R, CRDOT_T, CRDOT_N, CRDOT_RDOT,
    #                 CTDOT_R, CTDOT_T, CTDOT_N, CTDOT_RDOT, CTDOT_TDOT,
    #                 CNDOT_R, CNDOT_T, CNDOT_N, CNDOT_RDOT, CNDOT_TDOT, CNDOT_NDOT
    covariance: list[float] = field(default_factory=lambda: [0.0] * 21)

    # Physical properties
    area_m2: float | None = None          # cross-sectional area (m²)
    mass_kg: float | None = None
    cd_area_over_mass: float | None = None  # (m²/kg) for drag
    cr_area_over_mass: float | None = None  # (m²/kg) for SRP


@dataclass
class CdmMessage:
    """Complete CDM message for one conjunction event."""

    # Header
    ccsds_cdm_vers: str = "1.0"
    comment: str = ""
    creation_date: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    originator: str = "CONJUNCTION-PREDICTION-SYSTEM"
    message_for: str = ""
    message_id: str = ""

    # Relative metadata
    tca: datetime | None = None                   # Time of Closest Approach
    miss_distance_km: float = 0.0
    relative_speed_km_s: float = 0.0
    relative_position_r_km: float = 0.0          # Radial
    relative_position_t_km: float = 0.0          # Transverse
    relative_position_n_km: float = 0.0          # Normal
    relative_velocity_r_km_s: float = 0.0
    relative_velocity_t_km_s: float = 0.0
    relative_velocity_n_km_s: float = 0.0

    # Probability of collision
    collision_probability: float = 0.0
    collision_probability_method: str = "FOSTER-1992"  # or ALFANO-2005, CHAN-1997

    # Screening criteria used to identify this conjunction
    start_screen_period: datetime | None = None
    stop_screen_period: datetime | None = None
    collision_percentile: float | None = None    # screening Pc threshold

    # Objects
    object1: CdmObject = field(default_factory=CdmObject)
    object2: CdmObject = field(default_factory=CdmObject)

    # P2-E6 (Wertz): If both objects are active satellites, coordination is required.
    # CCSDS 508.0-B-1 §5.3 recommends documenting Object 2 maneuvering capability
    # so the primary operator knows whether to expect a coordinated response.
    object2_maneuverable: bool = False
    object2_operator_contact: str | None = None  # e.g. "ops@starlink.com" or "USSPACECOM"


def write_cdm_kvn(msg: CdmMessage) -> str:
    """Serialize a CdmMessage to CCSDS 508.0-B-1 KVN format.

    Args:
        msg: CdmMessage to serialize.

    Returns:
        CDM string in Key-Value Notation, ready to transmit or store.
    """
    lines: list[str] = []

    def kv(key: str, value: Any, comment: str = "") -> None:
        if value is None:
            return
        val_str = _format_value(key, value)
        if comment:
            lines.append(f"{key:<35} = {val_str:<30} [COMMENT: {comment}]")
        else:
            lines.append(f"{key:<35} = {val_str}")

    def section(name: str) -> None:
        lines.append("")
        lines.append(f"CCSDS_CDM_VERS                      = {msg.ccsds_cdm_vers}")

    # ── HEADER ────────────────────────────────────────────────────────
    section("HEADER")
    kv("CCSDS_CDM_VERS", msg.ccsds_cdm_vers)
    if msg.comment:
        lines.append(f"COMMENT {msg.comment}")
    kv("CREATION_DATE", _fmt_datetime(msg.creation_date))
    kv("ORIGINATOR", msg.originator)
    if msg.message_for:
        kv("MESSAGE_FOR", msg.message_for)
    if msg.message_id:
        kv("MESSAGE_ID", msg.message_id)

    # ── RELATIVE METADATA ─────────────────────────────────────────────
    lines.append("")
    lines.append("COMMENT Relative metadata / conjunction data")
    kv("TCA", _fmt_datetime(msg.tca) if msg.tca else "UNKNOWN")
    kv("MISS_DISTANCE", f"{msg.miss_distance_km:.3f}", "km")
    kv("RELATIVE_SPEED", f"{msg.relative_speed_km_s:.6f}", "km/s")
    kv("RELATIVE_POSITION_R", f"{msg.relative_position_r_km:.3f}", "km")
    kv("RELATIVE_POSITION_T", f"{msg.relative_position_t_km:.3f}", "km")
    kv("RELATIVE_POSITION_N", f"{msg.relative_position_n_km:.3f}", "km")
    kv("RELATIVE_VELOCITY_R", f"{msg.relative_velocity_r_km_s:.6f}", "km/s")
    kv("RELATIVE_VELOCITY_T", f"{msg.relative_velocity_t_km_s:.6f}", "km/s")
    kv("RELATIVE_VELOCITY_N", f"{msg.relative_velocity_n_km_s:.6f}", "km/s")
    if msg.start_screen_period:
        kv("START_SCREEN_PERIOD", _fmt_datetime(msg.start_screen_period))
    if msg.stop_screen_period:
        kv("STOP_SCREEN_PERIOD", _fmt_datetime(msg.stop_screen_period))
    if msg.collision_percentile is not None:
        kv("COLLISION_PERCENTILE", f"{msg.collision_percentile:.0f}")
    kv("COLLISION_PROBABILITY", f"{msg.collision_probability:.6e}")
    kv("COLLISION_PROBABILITY_METHOD", msg.collision_probability_method)

    # P2-E6: Object 2 maneuvering capability (CCSDS 508.0-B-1 §5.3)
    if msg.object2_maneuverable:
        lines.append("COMMENT Object 2 is maneuverable — coordination may be required")
        lines.append(f"{'OBJECT2_MANEUVERABLE':<35} = YES")
    else:
        lines.append(f"{'OBJECT2_MANEUVERABLE':<35} = NO")
    if msg.object2_operator_contact:
        lines.append(f"{'OBJECT2_OPERATOR_CONTACT':<35} = {msg.object2_operator_contact}")

    # ── OBJECT 1 ──────────────────────────────────────────────────────
    _write_object_block(lines, msg.object1, object_number=1)

    # ── OBJECT 2 ──────────────────────────────────────────────────────
    _write_object_block(lines, msg.object2, object_number=2)

    return "\n".join(lines) + "\n"


def _write_object_block(lines: list[str], obj: CdmObject, object_number: int) -> None:
    """Write the OBJECT N block to the KVN line list."""
    lines.append("")
    lines.append(f"COMMENT Object {object_number}")
    lines.append(f"{'OBJECT':<35} = OBJECT{object_number}")
    lines.append(f"{'OBJECT_DESIGNATOR':<35} = {obj.object_designator}")
    lines.append(f"{'CATALOG_NAME':<35} = SATCAT")
    lines.append(f"{'OBJECT_NAME':<35} = {obj.object_name}")
    lines.append(f"{'INTERNATIONAL_DESIGNATOR':<35} = {obj.international_designator}")
    lines.append(f"{'OBJECT_TYPE':<35} = {obj.object_type}")
    lines.append(f"{'REF_FRAME':<35} = {obj.ref_frame}")
    lines.append(f"{'GRAVITY_MODEL':<35} = {obj.gravity_model}")
    lines.append(f"{'ATMOSPHERIC_MODEL':<35} = {obj.atmospheric_model}")
    lines.append(f"{'N_BODY_PERTURBATIONS':<35} = {obj.n_body_perturbations}")
    lines.append(f"{'SOLAR_RAD_PRESSURE':<35} = {'YES' if obj.solar_rad_pressure else 'NO'}")
    lines.append(f"{'EARTH_TIDES':<35} = {'YES' if obj.earth_tides else 'NO'}")
    lines.append(f"{'INTRACK_THRUST':<35} = {'YES' if obj.intrack_thrust else 'NO'}")

    # State vector
    lines.append("COMMENT State vector / covariance in RTN frame")
    lines.append(f"{'X':<35} = {obj.x_km:.6f} [km]")
    lines.append(f"{'Y':<35} = {obj.y_km:.6f} [km]")
    lines.append(f"{'Z':<35} = {obj.z_km:.6f} [km]")
    lines.append(f"{'X_DOT':<35} = {obj.x_dot_km_s:.9f} [km/s]")
    lines.append(f"{'Y_DOT':<35} = {obj.y_dot_km_s:.9f} [km/s]")
    lines.append(f"{'Z_DOT':<35} = {obj.z_dot_km_s:.9f} [km/s]")

    # Covariance upper triangle (21 elements per CCSDS 508.0-B-1 Section 4.3)
    cov_keys = [
        "CR_R", "CT_R", "CT_T", "CN_R", "CN_T", "CN_N",
        "CRDOT_R", "CRDOT_T", "CRDOT_N", "CRDOT_RDOT",
        "CTDOT_R", "CTDOT_T", "CTDOT_N", "CTDOT_RDOT", "CTDOT_TDOT",
        "CNDOT_R", "CNDOT_T", "CNDOT_N", "CNDOT_RDOT", "CNDOT_TDOT", "CNDOT_NDOT",
    ]
    cov = obj.covariance if len(obj.covariance) == 21 else [0.0] * 21
    for key, val in zip(cov_keys, cov):
        lines.append(f"{key:<35} = {val:.9e}")

    # Physical properties
    if obj.area_m2 is not None:
        lines.append(f"{'AREA_PC':<35} = {obj.area_m2:.4f} [m**2]")
    if obj.mass_kg is not None:
        lines.append(f"{'MASS':<35} = {obj.mass_kg:.4f} [kg]")
    if obj.cd_area_over_mass is not None:
        lines.append(f"{'CD_AREA_OVER_MASS':<35} = {obj.cd_area_over_mass:.6f} [m**2/kg]")
    if obj.cr_area_over_mass is not None:
        lines.append(f"{'CR_AREA_OVER_MASS':<35} = {obj.cr_area_over_mass:.6f} [m**2/kg]")


def _fmt_datetime(dt: datetime) -> str:
    """Format datetime in CCSDS ISO 8601 format: YYYY-DDD THH:MM:SS.sss."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    doy = dt.timetuple().tm_yday
    ms = dt.microsecond // 1000
    return f"{dt.year}-{doy:03d}T{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}.{ms:03d}"


def _format_value(key: str, value: Any) -> str:
    if isinstance(value, float) and math.isfinite(value):
        return f"{value}"
    return str(value)


def cdm_from_conjunction(
    primary: Any,
    secondary: Any,
    tca: datetime,
    miss_distance_km: float,
    probability_of_collision: float,
    relative_speed_km_s: float = 0.0,
    rtn_position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rtn_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
    method: str = "FOSTER-1992",
    originator: str = "CONJUNCTION-PREDICTION-SYSTEM",
) -> CdmMessage:
    """Convenience constructor: build a CdmMessage from conjunction assessment output.

    Args:
        primary: SpaceObject for Object 1.
        secondary: SpaceObject for Object 2.
        tca: Time of Closest Approach.
        miss_distance_km: Miss distance at TCA (km).
        probability_of_collision: Pc value.
        relative_speed_km_s: Relative speed at TCA (km/s).
        rtn_position: (R, T, N) miss vector (km).
        rtn_velocity: (R_dot, T_dot, N_dot) relative velocity (km/s).
        method: Pc computation method string.
        originator: Organization originating the CDM.

    Returns:
        CdmMessage ready for write_cdm_kvn().
    """
    now = datetime.now(tz=timezone.utc)

    obj1 = CdmObject(
        object_designator=getattr(primary, "norad_id", "UNKNOWN"),
        object_name=getattr(primary, "name", "UNKNOWN"),
        object_type=str(getattr(primary, "object_type", "UNKNOWN")).upper(),
    )
    obj2 = CdmObject(
        object_designator=getattr(secondary, "norad_id", "UNKNOWN"),
        object_name=getattr(secondary, "name", "UNKNOWN"),
        object_type=str(getattr(secondary, "object_type", "UNKNOWN")).upper(),
    )

    return CdmMessage(
        creation_date=now,
        originator=originator,
        message_id=f"{primary.norad_id}-{secondary.norad_id}-{now.strftime('%Y%m%dT%H%M%S')}",
        tca=tca,
        miss_distance_km=miss_distance_km,
        relative_speed_km_s=relative_speed_km_s,
        relative_position_r_km=rtn_position[0],
        relative_position_t_km=rtn_position[1],
        relative_position_n_km=rtn_position[2],
        relative_velocity_r_km_s=rtn_velocity[0],
        relative_velocity_t_km_s=rtn_velocity[1],
        relative_velocity_n_km_s=rtn_velocity[2],
        collision_probability=probability_of_collision,
        collision_probability_method=method,
        object1=obj1,
        object2=obj2,
    )
