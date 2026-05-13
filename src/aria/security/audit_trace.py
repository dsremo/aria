"""audit_trace — CLI to walk the hash-chained audit log.

R34 Phase 5. Use cases:

    # All events for one incident, oldest first.
    python -m aria.security.audit_trace --incident-id inc_abc123def456

    # All warning+ events in the last hour.
    python -m aria.security.audit_trace --min-severity warning --since 3600

    # Verify the chain hasn't been tampered with.
    python -m aria.security.audit_trace --verify

    # Show chain status (head hash, entry count, log path, intact?).
    python -m aria.security.audit_trace --status

The CLI is read-only — it does not write to the chain. It exists so a
maintainer can investigate an incident from a terminal without spinning
up the dashboard.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from aria.security.audit import get_audit_log


def _format_entry(e: Any, *, json_out: bool) -> str:
    if json_out:
        return json.dumps({
            "seq": e.seq, "ts": e.timestamp,
            "event_type": e.event_type, "identity": e.identity,
            "action": e.action, "result": e.result,
            "details": e.details, "severity": e.severity,
            "source": e.source, "incident_id": e.incident_id,
            "trace_id": e.trace_id,
            "hash": e.hash_value, "prev_hash": e.prev_hash,
        }, ensure_ascii=False)
    ts = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
    sev = (e.severity or "info").upper().ljust(9)
    tid = f" {e.trace_id}" if e.trace_id else ""
    iid = f" {e.incident_id}" if e.incident_id else ""
    detail = json.dumps(e.details, ensure_ascii=False) if e.details else ""
    if len(detail) > 120:
        detail = detail[:117] + "…"
    return (f"#{e.seq:05d}  {ts}  {sev}{tid}{iid}  "
            f"{e.event_type:8s} {e.action:35s} → {e.result:10s} "
            f"by {e.identity}  {detail}")


def main() -> int:
    p = argparse.ArgumentParser(
        prog="aria.security.audit_trace",
        description="Walk the hash-chained audit log.",
    )
    p.add_argument("--incident-id", help="filter by incident_id")
    p.add_argument("--trace-id",
                   help="filter by trace_id (top-of-flow correlation key)")
    p.add_argument("--event-type", help="filter by event_type "
                   "(auth | authz | admin | bus | incident | …)")
    p.add_argument("--identity", help="filter by identity")
    p.add_argument("--min-severity",
                   choices=["info", "warning", "critical", "emergency"])
    p.add_argument("--since", type=float,
                   help="only entries newer than N seconds ago")
    p.add_argument("--limit", type=int, default=500,
                   help="max entries (default 500)")
    p.add_argument("--json", action="store_true",
                   help="JSON-per-line output for machine parsing")
    p.add_argument("--verify", action="store_true",
                   help="verify chain integrity and print result")
    p.add_argument("--status", action="store_true",
                   help="print chain head + size and exit")
    args = p.parse_args()

    log = get_audit_log()

    if args.status:
        st = log.chain_status()
        print(json.dumps(st, indent=2 if not args.json else None))
        return 0

    if args.verify:
        ok, broken_at = log.verify_chain()
        if ok:
            print("chain OK · entries={} · head={}".format(
                len(log), log.head_hash()))
            return 0
        print(f"chain BROKEN at seq={broken_at}", file=sys.stderr)
        return 1

    since = 0.0
    if args.since is not None:
        since = time.time() - float(args.since)
    entries = log.get_entries(
        event_type=args.event_type, identity=args.identity,
        since=since, limit=args.limit,
        incident_id=args.incident_id,
        trace_id=args.trace_id,
        min_severity=args.min_severity,
    )
    for e in entries:
        print(_format_entry(e, json_out=args.json))
    if not args.json:
        print(f"-- {len(entries)} entries · "
              f"head={log.head_hash()[:16]}…", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
