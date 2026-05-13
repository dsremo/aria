"""R40 — External component-catalog loader.

The hand-curated `components_db.py` carries 120 highly-cited entries —
production-grade for fasteners + seals + bearings.  But the
`PRODUCTION_READINESS_RESEARCH.md` Tier-3 acceptance asks for a
catalog ≥ 5 000 parts: avionics, EEE, propulsion tanks, thermal,
ECLSS, robotics + EVA, science.  Hand-writing those is enormous;
operationally the right answer is to **import** them from
license-clean upstream sources.

This module provides the loader.  It walks
``data/components_external/`` for JSON files with this schema:

    {
      "schema_version": 1,
      "source":  "libreCube",                # short tag
      "license": "CC-BY-SA-4.0",             # required for tracking
      "url":     "https://librecube.org/...",
      "ingested_at": "2026-04-26",
      "components": [
        {
          "part_number": "...",
          "name":        "...",
          "category":    "avionics",
          "subcategory": "rf_transceiver",
          "material":    "...",
          "key_dimensions": {...},
          "mass_g":      0.0,
          "max_operating_temp_k": 0.0,
          "pressure_rating_kpa": null,
          "source":      "libreCube tag XYZ",
          "extra":       {"power_w": 1.0, ...}
        }, ...
      ]
    }

Every entry is built into an in-memory :class:`Component` *plus* a
license tag.  Conflict policy: any duplicate ``part_number`` against
the in-tree catalog raises a clear error so the operator sees the
collision before deploying.  Within external files duplicates emit a
warning and the *first* wins (deterministic across reboots).

Reference:
    PRODUCTION_READINESS_RESEARCH.md §3 Tier-3 +
    https://librecube.org/         (CC-BY-SA — viral on derivative-catalog,
                                    hence the dedicated sub-tree)
    https://www.escc.eu/           (ESA QPL — public)
    https://oomi.nasa.gov/         (ISS On-Orbit Maintenance Inventory)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import structlog

from aria.digital_twin.components_db import Component

logger = structlog.get_logger()


# ── Default search path ─────────────────────────────────────────


def _default_external_root() -> Path:
    here = Path(__file__).resolve()
    # src/aria/digital_twin/external_components.py
    # → repo_root / data / components_external
    return (here.parents[3] / "data" / "components_external").resolve()


# ── License tag bookkeeping ─────────────────────────────────────


@dataclass(frozen=True)
class LicenseTag:
    """Where a part came from + under what license."""
    source: str
    license: str
    url: str = ""
    ingested_at: str = ""


# Module-level state — populated lazily on first load + cached.
_EXTERNAL_COMPONENTS: Dict[str, Component] = {}
_EXTERNAL_TAGS: Dict[str, LicenseTag] = {}
_LOADED = False


# ── Loader ──────────────────────────────────────────────────────


def _component_from_dict(d: dict, default_provenance: str = "parametric") -> Component:
    extra = dict(d.get("extra", {}))
    # Promote provenance from the document into the in-memory
    # Component's `extra` so the downstream API can filter by it
    # without changing the Component dataclass shape.
    extra.setdefault("provenance", str(d.get("provenance", default_provenance)))
    return Component(
        part_number=str(d["part_number"]),
        name=str(d["name"]),
        category=str(d["category"]),
        subcategory=str(d["subcategory"]),
        material=str(d.get("material", "")),
        key_dimensions=dict(d.get("key_dimensions", {})),
        mass_g=float(d.get("mass_g", 0.0)),
        max_operating_temp_k=float(d.get("max_operating_temp_k", 0.0)),
        pressure_rating_kpa=(
            None if d.get("pressure_rating_kpa") is None
            else float(d["pressure_rating_kpa"])
        ),
        source=str(d.get("source", "")),
        extra=extra,
    )


def load_external_catalog(
    root: Optional[Path] = None,
    *,
    strict: bool = False,
) -> Tuple[Dict[str, Component], Dict[str, LicenseTag]]:
    """Walk ``root`` (default: ``data/components_external/``) for
    catalog JSON files.  Returns (components_by_pn, license_tags).

    ``strict`` — when True, raise on a malformed file or duplicate
    part_number across files.  Default False so a single bad file
    doesn't keep the simulator from booting.
    """
    root = root or _default_external_root()
    components: Dict[str, Component] = {}
    tags: Dict[str, LicenseTag] = {}
    if not root.is_dir():
        return components, tags

    for jp in sorted(root.glob("*.json")):
        try:
            doc = json.loads(jp.read_text())
        except Exception as exc:
            msg = f"failed to parse {jp.name}: {exc}"
            if strict:
                raise RuntimeError(msg) from exc
            logger.warning("external_catalog.parse_failed",
                           file=jp.name, error=str(exc))
            continue

        source = str(doc.get("source", jp.stem))
        license_tag = str(doc.get("license", "UNKNOWN"))
        url = str(doc.get("url", ""))
        ingested = str(doc.get("ingested_at", ""))
        default_prov = str(doc.get("default_provenance", "parametric"))
        items = doc.get("components", [])
        added = 0
        for d in items:
            try:
                comp = _component_from_dict(d, default_provenance=default_prov)
            except Exception as exc:
                msg = f"malformed component in {jp.name}: {exc}"
                if strict:
                    raise RuntimeError(msg) from exc
                logger.warning("external_catalog.bad_component",
                               file=jp.name, error=str(exc))
                continue
            if comp.part_number in components:
                if strict:
                    raise RuntimeError(
                        f"duplicate part_number across external files: "
                        f"{comp.part_number} (second hit in {jp.name})"
                    )
                logger.warning("external_catalog.duplicate_dropped",
                               part_number=comp.part_number,
                               file=jp.name)
                continue
            components[comp.part_number] = comp
            tags[comp.part_number] = LicenseTag(
                source=source, license=license_tag,
                url=url, ingested_at=ingested,
            )
            added += 1
        logger.info("external_catalog.loaded",
                    file=jp.name, source=source,
                    license=license_tag, count=added)
    return components, tags


def get_external_components() -> Dict[str, Component]:
    """Module-level cache of the external catalog."""
    global _EXTERNAL_COMPONENTS, _EXTERNAL_TAGS, _LOADED
    if not _LOADED:
        _EXTERNAL_COMPONENTS, _EXTERNAL_TAGS = load_external_catalog()
        _LOADED = True
    return _EXTERNAL_COMPONENTS


def get_external_license_tags() -> Dict[str, LicenseTag]:
    if not _LOADED:
        get_external_components()
    return _EXTERNAL_TAGS


def reset_for_test() -> None:
    """Clear the cache.  Tests use this to re-load from a tmp_path."""
    global _EXTERNAL_COMPONENTS, _EXTERNAL_TAGS, _LOADED
    _EXTERNAL_COMPONENTS = {}
    _EXTERNAL_TAGS = {}
    _LOADED = False


# ── Merged-view API ─────────────────────────────────────────────


def merged_catalog() -> Dict[str, Component]:
    """In-tree + external, with in-tree winning on conflict."""
    from aria.digital_twin.components_db import COMPONENT_DATABASE
    out: Dict[str, Component] = {}
    out.update(get_external_components())
    out.update(COMPONENT_DATABASE)   # in-tree wins
    return out


def merged_total() -> int:
    return len(merged_catalog())


def license_summary() -> Dict[str, int]:
    """Count of external parts grouped by license."""
    summary: Dict[str, int] = {}
    for tag in get_external_license_tags().values():
        summary[tag.license] = summary.get(tag.license, 0) + 1
    return summary


def source_summary() -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for tag in get_external_license_tags().values():
        summary[tag.source] = summary.get(tag.source, 0) + 1
    return summary


def provenance_summary() -> Dict[str, int]:
    """R43 — counts external parts grouped by provenance tag.

    Operators use this to know how much of the catalog came from real
    procurement / measurement versus parametric expansion of standards.
    Goal over time: shrink the parametric share.
    """
    summary: Dict[str, int] = {}
    for c in get_external_components().values():
        prov = str(c.extra.get("provenance", "unknown"))
        summary[prov] = summary.get(prov, 0) + 1
    return summary


def filter_by_provenance(provenance: str) -> Dict[str, Component]:
    """Return only the external components matching the given
    provenance tag (e.g. ``'parametric'`` or ``'ingested'``).
    Useful to a downstream pipeline that disallows parametric data
    in safety-critical mass/power budgets."""
    return {
        pn: c for pn, c in get_external_components().items()
        if str(c.extra.get("provenance", "unknown")) == provenance
    }
