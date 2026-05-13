"""R43 — pullers that fetch real external catalogs over the network.

What this script does
---------------------

When run with internet access, it fetches the actual upstream dumps
from libreCube, ESCC QPL, ISS OOMI, NASA cFS, etc., and emits
``data/components_external/*_ingested_v1.json`` files **alongside**
the parametric ones.  Each fetched record is tagged
``provenance: "ingested"`` so downstream filters can prefer ingested
over parametric.

Without internet access this script prints a per-source action
manifest naming exactly what to fetch, the URL, the licence, and the
schema-mapping rule.  Use that as a checklist for a network-enabled
machine to do the actual download.

Why each source matters
-----------------------

* **libreCube (CC-BY-SA-4.0)** — open cubesat hardware reference.  The
  closest thing to a maintained, peer-reviewed cubesat parts catalog.
  Roughly 1 200 line items.  *Viral on derivative-catalog* — kept in
  ``avionics_libreCube_v1_ingested.json`` only.
* **ESCC QPL (ESA public)** — qualified parts list for ESA missions.
  ~ 2 800 line items across EEE, mechanical, thermal.
* **ISS OOMI (NASA public)** — On-Orbit Maintenance Inventory.  ~ 1 800
  line items.  Real flown hardware on a real station.
* **NASA cFS / F-Prime / GMAT (Apache-2.0)** — flight-software
  components.  We track app names, version, and the known-flown list.
* **Spacetrack / DLA-LandMaritime QPL (US public)** — alternate
  EEE parts data, useful as a cross-check on ESCC.

Usage
-----

::

    # Dry-run (no network needed) — prints the action manifest:
    python scripts/ingest_external_catalogs.py --dry-run

    # Real run (needs network):
    python scripts/ingest_external_catalogs.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def out_dir() -> Path:
    return repo_root() / "data" / "components_external"


# ── Source manifest ─────────────────────────────────────────────


@dataclass
class IngestSource:
    name: str
    url: str
    license: str
    description: str
    schema_mapper: str        # name of fn in this module
    max_records_estimate: int
    dependency_note: str = ""


SOURCES: List[IngestSource] = [
    IngestSource(
        name="librecube_ingested_v1",
        url="https://librecube.org/api/parts.json",
        license="CC-BY-SA-4.0",
        description="libreCube cubesat parts reference",
        schema_mapper="map_librecube",
        max_records_estimate=1200,
        dependency_note="JSON; map fields {pn, name, mass, power} → ARIA",
    ),
    IngestSource(
        name="escc_qpl_ingested_v1",
        url="https://escies.org/labels/qpl/component-search-export.csv",
        license="ESA-public",
        description="ESCC qualified-parts list (EEE + mechanical)",
        schema_mapper="map_escc_qpl",
        max_records_estimate=2800,
        dependency_note="CSV; map columns to ARIA Component schema",
    ),
    IngestSource(
        name="iss_oomi_ingested_v1",
        url="https://oomi.nasa.gov/api/inventory.json",
        license="NASA-public",
        description="ISS On-Orbit Maintenance Inventory",
        schema_mapper="map_oomi",
        max_records_estimate=1800,
        dependency_note=(
            "Auth token may be required; if not, fall back to "
            "the ISS OOMI quarterly snapshot CSV bundled at "
            "https://oomi.nasa.gov/snapshots/latest.csv"
        ),
    ),
    IngestSource(
        name="cfs_apps_ingested_v1",
        url="https://api.github.com/orgs/nasa/repos?per_page=100&type=public",
        license="Apache-2.0",
        description="NASA cFS + F-Prime + GMAT public app list",
        schema_mapper="map_github_repo",
        max_records_estimate=200,
        dependency_note=(
            "GitHub REST API; filter by repo prefix (cFS_, fprime, "
            "GMAT-).  Records map to category=software, "
            "subcategory=flight_app/ground_tool"
        ),
    ),
    IngestSource(
        name="dla_landmaritime_qpl_ingested_v1",
        url="https://landandmaritimeapps.dla.mil/Programs/MilSpec/qpl_export.json",
        license="US-public",
        description="DLA Land & Maritime QPL (DSCC alternate)",
        schema_mapper="map_dla_qpl",
        max_records_estimate=900,
        dependency_note="JSON or paginated HTML; treat as cross-check on ESCC",
    ),
]


# ── Mappers ─────────────────────────────────────────────────────


def map_librecube(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map libreCube records → ARIA Component dicts."""
    out: List[Dict[str, Any]] = []
    for r in records:
        pn = str(r.get("partNumber") or r.get("pn") or "").strip()
        if not pn:
            continue
        out.append({
            "part_number": f"LIBRECUBE-{pn}",
            "name": str(r.get("name", pn)),
            "category": str(r.get("category", "avionics")),
            "subcategory": str(r.get("subcategory", "misc")),
            "material": str(r.get("material", "PCB + EEE")),
            "key_dimensions": dict(r.get("dimensions") or {}),
            "mass_g": float(r.get("mass_g") or 0.0),
            "max_operating_temp_k": float(r.get("max_temp_k") or 358.0),
            "pressure_rating_kpa": None,
            "source": f"libreCube part {pn}",
            "extra": {
                "license_source": "libreCube",
                "power_w": float(r.get("power_w") or 0.0),
                "vendor": str(r.get("vendor", "")),
            },
            "provenance": "ingested",
        })
    return out


def map_escc_qpl(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map ESCC QPL CSV rows → ARIA Component dicts."""
    out: List[Dict[str, Any]] = []
    for r in records:
        pn = str(r.get("PART_NUMBER") or r.get("ESCC") or "").strip()
        if not pn:
            continue
        out.append({
            "part_number": f"ESCC-{pn}",
            "name": str(r.get("DESCRIPTION", pn)),
            "category": str(r.get("CATEGORY", "electrical")),
            "subcategory": str(r.get("SUBCATEGORY", "qualified")),
            "material": str(r.get("MATERIAL", "")),
            "key_dimensions": {},
            "mass_g": float(r.get("MASS_G") or 0.0),
            "max_operating_temp_k": float(r.get("TMAX_K") or 358.0),
            "pressure_rating_kpa": None,
            "source": f"ESCC QPL {pn}",
            "extra": {
                "manufacturer": str(r.get("MANUFACTURER", "")),
                "qualification_class": str(r.get("CLASS", "")),
            },
            "provenance": "ingested",
        })
    return out


def map_oomi(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map ISS OOMI inventory rows → ARIA Component dicts."""
    out: List[Dict[str, Any]] = []
    for r in records:
        pn = str(r.get("ORU_ID") or r.get("part_number") or "").strip()
        if not pn:
            continue
        out.append({
            "part_number": f"OOMI-{pn}",
            "name": str(r.get("nomenclature") or r.get("name", pn)),
            "category": "eclss",
            "subcategory": str(r.get("subsystem", "misc")),
            "material": "",
            "key_dimensions": {},
            "mass_g": float(r.get("mass_kg", 0.0)) * 1000.0,
            "max_operating_temp_k": 333.0,
            "pressure_rating_kpa": None,
            "source": f"ISS OOMI {pn}",
            "extra": {
                "installed_count": int(r.get("count_on_iss") or 1),
                "subsystem": str(r.get("subsystem", "")),
            },
            "provenance": "ingested",
        })
    return out


def map_github_repo(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map GitHub repo metadata → software Component dicts."""
    out: List[Dict[str, Any]] = []
    keep_prefixes = ("cFS", "fprime", "GMAT", "F-Prime")
    for r in records:
        name = str(r.get("name", ""))
        if not any(name.startswith(p) for p in keep_prefixes):
            continue
        out.append({
            "part_number": f"GH-{name.upper()}",
            "name": str(r.get("description") or name),
            "category": "software",
            "subcategory": (
                "flight_app" if name.lower().startswith("cfs")
                or name.lower().startswith(("fprime", "f-prime"))
                else "ground_tool"
            ),
            "material": "(software)",
            "key_dimensions": {},
            "mass_g": 0.0,
            "max_operating_temp_k": 0.0,
            "pressure_rating_kpa": None,
            "source": f"GitHub {r.get('full_name')}",
            "extra": {
                "version": str(r.get("default_branch", "")),
                "html_url": str(r.get("html_url", "")),
                "stars": int(r.get("stargazers_count") or 0),
            },
            "provenance": "ingested",
        })
    return out


def map_dla_qpl(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map DLA Land & Maritime QPL rows → ARIA Component dicts."""
    out: List[Dict[str, Any]] = []
    for r in records:
        pn = str(r.get("part_number") or "").strip()
        if not pn:
            continue
        out.append({
            "part_number": f"DLA-{pn}",
            "name": str(r.get("description", pn)),
            "category": str(r.get("category", "electrical")),
            "subcategory": str(r.get("subcategory", "qualified")),
            "material": "",
            "key_dimensions": {},
            "mass_g": 0.0,
            "max_operating_temp_k": 358.0,
            "pressure_rating_kpa": None,
            "source": f"DLA Land&Maritime QPL {pn}",
            "extra": {
                "manufacturer": str(r.get("manufacturer", "")),
                "spec": str(r.get("spec", "")),
            },
            "provenance": "ingested",
        })
    return out


MAPPERS: Dict[str, Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = {
    "map_librecube": map_librecube,
    "map_escc_qpl": map_escc_qpl,
    "map_oomi": map_oomi,
    "map_github_repo": map_github_repo,
    "map_dla_qpl": map_dla_qpl,
}


# ── Network fetch ───────────────────────────────────────────────


def _fetch_json(url: str, timeout_s: float = 30.0) -> Optional[List[Dict[str, Any]]]:
    """HTTP GET → parse JSON.  Returns None on error.  Imports requests
    lazily so the script still runs in dry-run mode without it."""
    try:
        import requests
    except ImportError:
        print(f"  ! requests not installed; skipping network fetch")
        return None
    try:
        r = requests.get(url, timeout=timeout_s, headers={
            "User-Agent": "ARIA/R43 catalog-ingest",
        })
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("results", "items", "components", "data"):
                if isinstance(data.get(key), list):
                    return data[key]
        return None
    except Exception as exc:
        print(f"  ! fetch failed: {exc}")
        return None


# ── Driver ──────────────────────────────────────────────────────


def write_ingested(name: str, source: IngestSource, mapped: List[Dict[str, Any]]) -> Path:
    out = out_dir() / f"{name}.json"
    doc = {
        "schema_version": 1,
        "source": source.description,
        "license": source.license,
        "url": source.url,
        "ingested_at": time.strftime("%Y-%m-%d"),
        "default_provenance": "ingested",
        "ingested_by": "scripts/ingest_external_catalogs.py",
        "components": mapped,
    }
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return out


def run_dry() -> int:
    print("R43 catalog-ingest manifest (dry-run — no network calls)")
    print("=" * 64)
    for s in SOURCES:
        print()
        print(f"  source: {s.name}")
        print(f"    description : {s.description}")
        print(f"    url         : {s.url}")
        print(f"    license     : {s.license}")
        print(f"    est records : {s.max_records_estimate}")
        print(f"    mapper      : {s.schema_mapper}")
        if s.dependency_note:
            print(f"    notes       : {s.dependency_note}")
    print()
    print("Run without --dry-run on a network-enabled machine to fetch.")
    return 0


def run_real() -> int:
    out_dir().mkdir(parents=True, exist_ok=True)
    summary: Dict[str, int] = {}
    for s in SOURCES:
        print(f"[ingest] {s.name} <- {s.url}")
        records = _fetch_json(s.url)
        if records is None:
            print(f"  - skipped (no data)")
            summary[s.name] = 0
            continue
        mapper = MAPPERS.get(s.schema_mapper)
        if mapper is None:
            print(f"  - no mapper {s.schema_mapper}; skipping")
            summary[s.name] = 0
            continue
        mapped = mapper(records)
        out_path = write_ingested(s.name, s, mapped)
        summary[s.name] = len(mapped)
        print(f"  - wrote {len(mapped)} parts → {out_path}")
    print()
    total = sum(summary.values())
    print(f"Total ingested: {total} parts across {len(summary)} files")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="print the action manifest, don't hit network")
    args = parser.parse_args()
    return run_dry() if args.dry_run else run_real()


if __name__ == "__main__":
    raise SystemExit(main())
