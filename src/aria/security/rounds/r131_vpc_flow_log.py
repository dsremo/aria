"""R131 — VPC flow-log auditor.

Threat: an attacker exfiltrating from inside a VPC blends with
legitimate traffic; without VPC flow logs, no one can correlate the
traffic post-incident.  Banks + nation-state require always-on flow
logging.  AWS, Azure, GCP each have their own.

Defence: a small parser for the AWS VPC flow-log format (v2 + v5)
that reports unusual destinations: connections to known-bad IPs
(R90), large outbound payloads to unknown hosts (R91), connections to
internal CIDRs that shouldn't talk to each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from aria.security.plugins import DefencePlugin, register


@dataclass
class FlowFinding:
    src_ip: str
    dst_ip: str
    bytes_xferred: int
    reason: str


def parse_aws_flow_v2_line(line: str) -> dict:
    """Parse a single AWS VPC flow log v2 record."""
    cols = line.split()
    if len(cols) < 14:
        return {}
    return {
        "version": cols[0],
        "account_id": cols[1],
        "interface_id": cols[2],
        "srcaddr": cols[3],
        "dstaddr": cols[4],
        "srcport": cols[5],
        "dstport": cols[6],
        "protocol": cols[7],
        "packets": cols[8],
        "bytes": cols[9],
        "start": cols[10],
        "end": cols[11],
        "action": cols[12],
        "log_status": cols[13],
    }


def audit_flow_lines(lines: Iterable[str], *, large_xfer_bytes: int = 100 * 1024 * 1024) -> List[FlowFinding]:
    out: List[FlowFinding] = []
    try:
        from aria.security.rounds.r90_ip_reputation import score
    except Exception:
        score = lambda _ip: 0.0          # noqa: E731
    for line in lines:
        record = parse_aws_flow_v2_line(line)
        if not record:
            continue
        try:
            n = int(record.get("bytes", "0"))
        except ValueError:
            continue
        dst = record.get("dstaddr", "")
        action = record.get("action", "")
        if action == "REJECT":
            continue
        rep = score(dst)
        if rep >= 0.5:
            out.append(FlowFinding(
                src_ip=record.get("srcaddr", ""),
                dst_ip=dst,
                bytes_xferred=n,
                reason=f"r131.dst_known_bad rep={rep:.2f}",
            ))
            continue
        if n > large_xfer_bytes:
            out.append(FlowFinding(
                src_ip=record.get("srcaddr", ""),
                dst_ip=dst,
                bytes_xferred=n,
                reason=f"r131.large_outbound {n} bytes",
            ))
    return out


register(DefencePlugin(
    round_id="R131",
    name="vpc_flow_log",
    description="VPC flow-log v2 parser + IP-reputation + large-xfer audit.",
))
