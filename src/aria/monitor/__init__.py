"""ARIA Independent Monitor — §F-7 of FAILSAFE_ARCHITECTURE.md.

The monitor is a *separate, parallel* oversight system that watches the
primary controller's traffic and vetos / triggers safe-mode if anything
violates the constitution. Independence is the point:

  - Different code path (no shared imports with primary controllers)
  - Different process (run via aria.monitor.runner)
  - Different model family for cross-check (when LLM monitor enabled)
  - Three concurrent strategies with 2-of-3 consensus:
      1. Rule-based (this module is the deterministic baseline)
      2. Statistical anomaly detection (dsremo ensemble)
      3. Cross-model semantic check (different model)
  - Air-gapped audit trail — monitor's verdicts join the same
    hash-chained audit log so an attacker cannot rewrite them either.

The monitor never *executes* commands. Its only outputs are:
  - aria.monitor.heartbeat (frequent — primary safe-modes if it stops)
  - aria.monitor.veto.{seq}  (specific command vetoed)
  - aria.monitor.violation   (rule trip — request safe-mode)
  - aria.monitor.alert       (statistical or semantic concern)

Threats addressed: T-V-1 (AI watching itself), T-V-2 (correlated
compromise), T-V-3 (same-vendor), T-II-1/2/3/4 (LLM behavioural).
"""

from aria.monitor.rules import (
    RuleBasedMonitor,
    MonitorVerdict,
)
from aria.monitor.heartbeat import HeartbeatEmitter, HeartbeatWatcher

__all__ = [
    "RuleBasedMonitor",
    "MonitorVerdict",
    "HeartbeatEmitter",
    "HeartbeatWatcher",
]
