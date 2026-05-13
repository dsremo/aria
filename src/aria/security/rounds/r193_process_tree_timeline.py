"""R193 — Process-tree timeline reconstruction.

Threat: post-incident, the analyst needs to know which parent spawned
which child, when, with what argv.  Without per-process exec records
the timeline is reconstructed from log fragments — slow + error-prone.

Defence: walk /proc, capture (pid, ppid, exe, cmdline, start_time)
for every process and emit a sorted timeline.  Operator runs it on
incident detection.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from aria.security.plugins import DefencePlugin, register


@dataclass
class ProcSnapshot:
    pid: int
    ppid: int
    exe: str
    cmdline: str
    start_jiffies: int


def snapshot_processes() -> List[ProcSnapshot]:
    out: List[ProcSnapshot] = []
    proc = Path("/proc")
    if not proc.exists():
        return out
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            stat_txt = (entry / "stat").read_text()
            cmdline = (entry / "cmdline").read_text().replace("\x00", " ").strip()
            try:
                exe = os.readlink(entry / "exe")
            except OSError:
                exe = ""
        except OSError:
            continue
        # /proc/[pid]/stat: pid (comm) state ppid ... starttime is field 22
        rparen = stat_txt.rfind(")")
        if rparen < 0:
            continue
        rest = stat_txt[rparen + 2:].split()
        if len(rest) < 22:
            continue
        ppid = int(rest[1])
        start_jiffies = int(rest[19])
        out.append(ProcSnapshot(pid, ppid, exe, cmdline, start_jiffies))
    out.sort(key=lambda p: (p.start_jiffies, p.pid))
    return out


def render_timeline(snaps: List[ProcSnapshot]) -> str:
    lines = ["pid\tppid\tstart_jiffies\texe\tcmdline"]
    for s in snaps:
        lines.append(f"{s.pid}\t{s.ppid}\t{s.start_jiffies}\t{s.exe}\t{s.cmdline[:200]}")
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R193",
    name="process_tree_timeline",
    description="Capture per-process parent/cmdline/start-time and emit forensic timeline.",
))
