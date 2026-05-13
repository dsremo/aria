"""XTCE parameter definition parser (CCSDS 660.1-G-2).

Supports XTCE 1.1, 1.2, and no-namespace variants used in the wild.
Parses with ``aria.security.guard.safe_xml_parse`` (defusedxml-backed —
rejects DOCTYPE / external-entity injection up-front).

Algorithm
---------
1. Parse XML → detect namespace from root tag (handles all three variants).
2. First pass  — build a type_map {type_name → _TypeInfo} from every
   *ParameterType element in the document (units + alarm ranges).
3. Second pass — walk the SpaceSystem hierarchy recursively; collect each
   Parameter, resolve its type, and tag it with the immediate parent
   SpaceSystem name as subsystem label.

Returns a list of ParameterDef dataclasses — one per telemetry parameter.

Supported XTCE nodes
--------------------
- SpaceSystem           → hierarchy / subsystem label
- TelemetryMetaData     → container for type + parameter sets
- ParameterTypeSet      → FloatParameterType, IntegerParameterType
  - UnitSet / Unit      → physical unit string
  - DefaultAlarm        → StaticAlarmRanges
    - WatchRange        → outer watch bounds (minInclusive / maxInclusive)
    - WarningRange      → tighter warning bounds
    - CautionRange      → alias for WarningRange (some YAMCS exports use this)
- ParameterSet / Parameter → name, parameterTypeRef, LongDescription
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import IO
import xml.etree.ElementTree as ET  # noqa: S405 (read access only — parsing routed through safe_xml_*)

from aria.security.guard import safe_xml_fromstring

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_XTCE_NS_CANDIDATES = [
    "urn:ccsds:schema:ndm:xtce",        # XTCE 1.1 (most common — ESA, YAMCS default)
    "urn:ccsds:schema:ndm:xtce-1.2",    # XTCE 1.2
    "http://www.omg.org/space/xtce",     # OMG variant (some older toolchains)
    "",                                  # no namespace
]


def _detect_ns(root: ET.Element) -> str:
    """Return the namespace URI from the root element tag, or '' if none."""
    tag = root.tag
    if tag.startswith("{"):
        return tag[1 : tag.index("}")]
    return ""


def _q(local: str, ns: str) -> str:
    """Qualify a local XML tag name with the given namespace (or leave bare)."""
    return f"{{{ns}}}{local}" if ns else local


def _parse_float_attr(el: ET.Element | None, attr: str) -> float | None:
    """Safely parse a float attribute from an element; return None if missing."""
    if el is None:
        return None
    raw = el.get(attr)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AlarmRange:
    """Inclusive [low, high] alarm boundary from XTCE StaticAlarmRanges."""
    low: float | None
    high: float | None

    def is_set(self) -> bool:
        return self.low is not None or self.high is not None


@dataclass(frozen=True)
class ParameterDef:
    """Single telemetry parameter extracted from an XTCE document.

    Attributes:
        name:          XTCE parameter name (as defined in ParameterSet).
        subsystem:     Immediate parent SpaceSystem name, lowercased.
                       Root-level parameters use the root SpaceSystem name.
        unit:          Physical unit string from UnitSet (empty if absent).
        watch_range:   Outer alarm boundary (WatchRange). None if not defined.
        warning_range: Inner alarm boundary (WarningRange/CautionRange). None if absent.
        description:   LongDescription text (empty if absent).
    """
    name: str
    subsystem: str
    unit: str
    watch_range: AlarmRange | None
    warning_range: AlarmRange | None
    description: str


# ---------------------------------------------------------------------------
# Internal type resolution
# ---------------------------------------------------------------------------

@dataclass
class _TypeInfo:
    unit: str
    watch: AlarmRange | None
    warning: AlarmRange | None


def _parse_range_el(el: ET.Element | None) -> AlarmRange | None:
    if el is None:
        return None
    low = _parse_float_attr(el, "minInclusive")
    high = _parse_float_attr(el, "maxInclusive")
    r = AlarmRange(low=low, high=high)
    return r if r.is_set() else None


def _build_type_map(root: ET.Element, ns: str) -> dict[str, _TypeInfo]:
    """Collect all FloatParameterType and IntegerParameterType definitions
    from the entire document into a lookup dict keyed by type name."""
    type_map: dict[str, _TypeInfo] = {}

    for tag in ("FloatParameterType", "IntegerParameterType"):
        for ptype in root.iter(_q(tag, ns)):
            type_name = ptype.get("name", "")
            if not type_name:
                continue

            # --- Unit ---
            unit = ""
            unit_set = ptype.find(_q("UnitSet", ns))
            if unit_set is not None:
                unit_el = unit_set.find(_q("Unit", ns))
                if unit_el is not None and unit_el.text:
                    unit = unit_el.text.strip()

            # --- Alarm ranges ---
            watch: AlarmRange | None = None
            warning: AlarmRange | None = None

            alarm_el = ptype.find(_q("DefaultAlarm", ns))
            if alarm_el is not None:
                ranges_el = alarm_el.find(_q("StaticAlarmRanges", ns))
                if ranges_el is not None:
                    watch = _parse_range_el(ranges_el.find(_q("WatchRange", ns)))
                    # "WarningRange" and "CautionRange" are both used by different tools.
                    # Must use `is None` — ET.Element is falsy when it has no children,
                    # so `find(...) or find(...)` silently drops a self-closing element.
                    warn_el = ranges_el.find(_q("WarningRange", ns))
                    if warn_el is None:
                        warn_el = ranges_el.find(_q("CautionRange", ns))
                    warning = _parse_range_el(warn_el)

            type_map[type_name] = _TypeInfo(unit=unit, watch=watch, warning=warning)

    return type_map


# ---------------------------------------------------------------------------
# SpaceSystem walker (recursive)
# ---------------------------------------------------------------------------

def _walk_space_system(
    el: ET.Element,
    ns: str,
    subsystem: str,
    type_map: dict[str, _TypeInfo],
) -> list[ParameterDef]:
    """Recursively collect ParameterDefs from a SpaceSystem element."""
    results: list[ParameterDef] = []

    # Parameters live inside TelemetryMetaData → ParameterSet
    tmd = el.find(_q("TelemetryMetaData", ns))
    if tmd is not None:
        param_set = tmd.find(_q("ParameterSet", ns))
        if param_set is not None:
            for param in param_set.findall(_q("Parameter", ns)):
                name = param.get("name", "").strip()
                if not name:
                    continue

                type_ref = param.get("parameterTypeRef", "")
                info = type_map.get(type_ref, _TypeInfo(unit="", watch=None, warning=None))

                desc_el = param.find(_q("LongDescription", ns))
                description = (desc_el.text or "").strip() if desc_el is not None else ""

                results.append(ParameterDef(
                    name=name,
                    subsystem=subsystem,
                    unit=info.unit,
                    watch_range=info.watch,
                    warning_range=info.warning,
                    description=description,
                ))

    # Recurse into child SpaceSystems — their subsystem label is their own name
    for child in el.findall(_q("SpaceSystem", ns)):
        child_name = child.get("name", subsystem).strip().lower() or subsystem
        results.extend(_walk_space_system(child, ns, child_name, type_map))

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_xtce(source: str | Path | IO[bytes] | bytes) -> list[ParameterDef]:
    """Parse an XTCE XML document and return one ParameterDef per parameter.

    Args:
        source: File path (str or Path), file-like bytes object (IO[bytes]),
                or raw bytes. Supports XTCE 1.1, 1.2, and no-namespace.

    Returns:
        List of ParameterDef, preserving document order. Empty list if the
        document has no parameters.

    Raises:
        ET.ParseError: Malformed XML.
        ValueError:    Source is empty or root element is not a SpaceSystem.
    """
    # Normalise everything to bytes first, then strip leading whitespace/BOM.
    # ElementTree requires <?xml?> to be at byte 0; files from YAMCS exports,
    # copy-paste, or textwrap.dedent in tests often have leading whitespace.
    if isinstance(source, (str, Path)):
        with open(source, "rb") as fh:
            raw: bytes = fh.read()
    elif isinstance(source, bytes):
        raw = source
    else:
        raw = source.read()

    raw = raw.lstrip()          # strip BOM, leading newlines, accidental indent
    if not raw:
        raise ValueError("XTCE source is empty")

    # Defused parse — XXE / external-entity / DTD declarations are rejected.
    root = safe_xml_fromstring(raw)
    ns = _detect_ns(root)

    # Validate root is a SpaceSystem (catches non-XTCE XML gracefully)
    local = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if local != "SpaceSystem":
        raise ValueError(
            f"Expected root element 'SpaceSystem', got '{local}'. "
            "Is this an XTCE document?"
        )

    # Root SpaceSystem name becomes the default subsystem for top-level params
    root_subsystem = root.get("name", "root").strip().lower() or "root"

    # Phase 1 — build type map from the entire document
    type_map = _build_type_map(root, ns)

    # Phase 2 — walk SpaceSystem hierarchy
    return _walk_space_system(root, ns, root_subsystem, type_map)
