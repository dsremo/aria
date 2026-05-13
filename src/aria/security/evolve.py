"""Auto-evolving threat intelligence.

Pulls from public threat feeds, normalises into ARIA's internal pattern
shape, and merges into the active rule set.  Built so a fresh deploy
ships with a snapshot embedded on disk AND can refresh on a cron tick
without restart.

Sources (all public, free, ToS-compatible):

  * **CISA KEV** (Known Exploited Vulnerabilities) — JSON, daily, CWE-tagged.
    URL: ``https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json``
  * **MITRE CVE** for description text — pulled lazily per CVE.
  * **garak probe corpus** — Apache-2.0; we read the locally-snapshotted
    file ``data/threatfeed/garak_probes.json`` produced by a separate
    sync job (it doesn't make sense for a production deploy to clone
    multiple GB of probe assets).

The evolve module deliberately **does NOT auto-execute** anything from
a feed.  It refreshes a typed in-memory dict; the rule registry then
*chooses* to compile new regex patterns, the decision and source URL
are audit-logged.  This is the lesson from the XZ Utils backdoor —
auto-pulling a maintainer's diff and applying it without review is the
exact attack vector we are not going to add.

Failure modes:
  * Network failure → keep the on-disk snapshot, emit warning.
  * Signature failure (when an upstream offers one) → REFUSE the update.
  * Schema drift → fall back to the previous snapshot.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger("aria.security.evolve")


# Path where the on-disk snapshot lives.  Operators override via env var
# so a Docker image can mount a writable volume separately from /src.
def _default_snapshot_dir() -> Path:
    here = Path(__file__).resolve()
    return here.parents[3] / "data" / "threatfeed"


SNAPSHOT_DIR = Path(os.environ.get("ARIA_THREATFEED_DIR") or _default_snapshot_dir())


# ── Snapshot dataclass ────────────────────────────────────────────


@dataclass
class FeedSnapshot:
    name: str
    fetched_at: float
    upstream_url: str
    sha256: str
    record_count: int
    payload: Dict[str, Any] = field(default_factory=dict)


# ── CISA KEV pull ──────────────────────────────────────────────────


CISA_KEV_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/"
    "known_exploited_vulnerabilities.json"
)


def fetch_cisa_kev(*, timeout: float = 30.0) -> Optional[FeedSnapshot]:
    """Pull the CISA KEV JSON feed via the SSRF-safe fetcher.

    Returns a :class:`FeedSnapshot` or None on failure.  Operators can
    cron this with a 24 h period — the feed updates on US business days.
    """
    from aria.security.guard import GuardError, safe_open_url

    try:
        body = safe_open_url(
            CISA_KEV_URL,
            timeout=timeout,
            max_bytes=8 * 1024 * 1024,           # KEV JSON ~ 1 MiB; 8 MiB ceiling
            allowed_schemes=("https",),
            allowed_content_types=("application/json", "text/plain"),
            enforce_host_allowlist=False,        # cisa.gov is not in default list
            headers={"User-Agent": "aria-core/0.3 (security/evolve)"},
        )
    except GuardError as exc:
        logger.warning("evolve.kev_fetch_blocked %s", exc)
        return None
    except Exception as exc:
        logger.warning("evolve.kev_fetch_failed %s", exc)
        return None

    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("evolve.kev_bad_json %s", exc)
        return None

    vulns = data.get("vulnerabilities") or []
    if not isinstance(vulns, list):
        return None
    digest = hashlib.sha256(body).hexdigest()
    snap = FeedSnapshot(
        name="cisa_kev",
        fetched_at=time.time(),
        upstream_url=CISA_KEV_URL,
        sha256=digest,
        record_count=len(vulns),
        payload={"vulnerabilities": vulns,
                 "catalog_version": data.get("catalogVersion"),
                 "date_released": data.get("dateReleased")},
    )
    return snap


def save_snapshot(snap: FeedSnapshot, *, snapshot_dir: Optional[Path] = None) -> Path:
    """Persist a snapshot to disk.  Atomic write — temp + rename."""
    target_dir = snapshot_dir or SNAPSHOT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"{snap.name}.json"
    tmp = out.with_suffix(".json.tmp")
    blob = {
        "name": snap.name,
        "fetched_at": snap.fetched_at,
        "upstream_url": snap.upstream_url,
        "sha256": snap.sha256,
        "record_count": snap.record_count,
        "payload": snap.payload,
    }
    tmp.write_text(json.dumps(blob, indent=2), encoding="utf-8")
    tmp.replace(out)
    return out


def load_snapshot(name: str, *, snapshot_dir: Optional[Path] = None) -> Optional[FeedSnapshot]:
    target_dir = snapshot_dir or SNAPSHOT_DIR
    p = target_dir / f"{name}.json"
    if not p.is_file():
        return None
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return FeedSnapshot(
        name=blob.get("name", name),
        fetched_at=float(blob.get("fetched_at", 0.0)),
        upstream_url=blob.get("upstream_url", ""),
        sha256=blob.get("sha256", ""),
        record_count=int(blob.get("record_count", 0)),
        payload=blob.get("payload", {}),
    )


# ── Rule extraction ────────────────────────────────────────────────


def kev_to_high_risk_cves(snap: FeedSnapshot) -> List[Dict[str, Any]]:
    """Project a KEV snapshot down to the fields ARIA actually uses.

    Returns a list of ``{cve, vendor, product, cwes, ransomware}``
    dicts.  Used by the WAF-style middleware to flag inbound traffic
    matching known-exploited CVE families even when the underlying
    library is patched (defence-in-depth).
    """
    out: List[Dict[str, Any]] = []
    for v in (snap.payload.get("vulnerabilities") or []):
        try:
            out.append({
                "cve": v.get("cveID", ""),
                "vendor": v.get("vendorProject", ""),
                "product": v.get("product", ""),
                "cwes": list(v.get("cwes") or []),
                "ransomware": v.get("knownRansomwareCampaignUse", "Unknown"),
                "due_date": v.get("dueDate", ""),
            })
        except Exception:
            continue
    return out


# ── Top-level orchestration ────────────────────────────────────────


_LOCK = threading.Lock()
_LAST_REFRESH: Dict[str, float] = {}


def refresh_all(
    *,
    snapshot_dir: Optional[Path] = None,
    min_period_seconds: float = 12 * 3600.0,
) -> Dict[str, Any]:
    """One-shot refresh of every supported feed.  Idempotent.

    Skips any feed that was refreshed within ``min_period_seconds``.
    Returns a summary dict for the audit log.
    """
    summary: Dict[str, Any] = {"refreshed": [], "skipped": [], "errors": []}
    now = time.time()
    with _LOCK:
        if now - _LAST_REFRESH.get("cisa_kev", 0.0) < min_period_seconds:
            summary["skipped"].append("cisa_kev")
        else:
            snap = fetch_cisa_kev()
            if snap is None:
                summary["errors"].append("cisa_kev")
            else:
                save_snapshot(snap, snapshot_dir=snapshot_dir)
                _LAST_REFRESH["cisa_kev"] = now
                summary["refreshed"].append({
                    "feed": "cisa_kev",
                    "records": snap.record_count,
                    "sha256": snap.sha256[:16],
                })
    return summary


__all__ = [
    "FeedSnapshot",
    "CISA_KEV_URL",
    "SNAPSHOT_DIR",
    "fetch_cisa_kev",
    "save_snapshot", "load_snapshot",
    "kev_to_high_risk_cves",
    "refresh_all",
]
