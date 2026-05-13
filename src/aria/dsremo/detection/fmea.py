"""FMEA (Failure Modes and Effects Analysis) traceability.

Maps detected anomalies to specific failure modes so operators know
what physical failure the anomaly suggests.

Example:
    "CUSUM fired on battery_voltage" → "FM-PWR-003: Battery cell capacity degradation"

The mapping is configurable per mission via YAML.  Default mappings cover
common spacecraft subsystems (EPS, ADCS, thermal, comms).
"""

from __future__ import annotations

# Default FMEA mapping: (subsystem, parameter_pattern) → failure mode ID + description.
# parameter_pattern uses simple prefix matching.
FMEA_MAP: dict[tuple[str, str], dict] = {
    # ── EPS (Electrical Power System) ──
    ("eps", "battery_voltage"):  {"id": "FM-PWR-001", "desc": "Battery cell voltage anomaly",
                                   "effect": "Potential power bus collapse"},
    ("eps", "battery_current"):  {"id": "FM-PWR-002", "desc": "Battery current anomaly",
                                   "effect": "Possible short circuit or load imbalance"},
    ("eps", "battery_temp"):     {"id": "FM-PWR-003", "desc": "Battery thermal anomaly",
                                   "effect": "Risk of thermal runaway"},
    ("eps", "solar"):            {"id": "FM-PWR-004", "desc": "Solar array performance degradation",
                                   "effect": "Reduced power generation capacity"},
    ("eps", "bus_voltage"):      {"id": "FM-PWR-005", "desc": "Power bus voltage anomaly",
                                   "effect": "Potential downstream subsystem impact"},
    # ── ADCS (Attitude Determination & Control) ──
    ("adcs", "wheel_speed"):     {"id": "FM-ACS-001", "desc": "Reaction wheel speed anomaly",
                                   "effect": "Attitude control degradation"},
    ("adcs", "pointing_error"):  {"id": "FM-ACS-002", "desc": "Pointing error exceedance",
                                   "effect": "Payload pointing accuracy loss"},
    ("adcs", "gyro"):            {"id": "FM-ACS-003", "desc": "Gyroscope drift anomaly",
                                   "effect": "Attitude knowledge degradation"},
    # ── Thermal ──
    ("thermal", "panel_temp"):   {"id": "FM-THM-001", "desc": "Panel temperature anomaly",
                                   "effect": "Possible thermal control failure"},
    ("thermal", "electronics"):  {"id": "FM-THM-002", "desc": "Electronics bay thermal anomaly",
                                   "effect": "Risk of component overheating"},
    # ── Comms ──
    ("comms", "signal_strength"):{"id": "FM-COM-001", "desc": "Signal strength anomaly",
                                   "effect": "Link margin reduction"},
    ("comms", "bit_error"):      {"id": "FM-COM-002", "desc": "Bit error rate anomaly",
                                   "effect": "Data quality degradation"},
}

# Custom mission FMEA loaded from config
_custom_fmea: dict[tuple[str, str], dict] = {}


def lookup_failure_mode(subsystem: str, parameter: str) -> dict | None:
    """Look up the FMEA failure mode for a (subsystem, parameter) pair.

    Uses prefix matching on parameter name.

    Returns:
        {"id": "FM-XXX-NNN", "desc": "...", "effect": "..."} or None.
    """
    # Check custom first
    for (ss, prefix), fm in _custom_fmea.items():
        if subsystem == ss and parameter.startswith(prefix):
            return fm
    # Then defaults
    for (ss, prefix), fm in FMEA_MAP.items():
        if subsystem == ss and parameter.startswith(prefix):
            return fm
    return None


def register_failure_mode(
    subsystem: str, parameter_prefix: str,
    fm_id: str, description: str, effect: str,
) -> None:
    """Register a custom failure mode mapping."""
    _custom_fmea[(subsystem, parameter_prefix)] = {
        "id": fm_id, "desc": description, "effect": effect,
    }
