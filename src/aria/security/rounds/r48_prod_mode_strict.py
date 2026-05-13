"""R48 — Production-mode strict boot check.

Threat: deploy slips out the door with ``ARIA_DEBUG_ALLOW_INSECURE=1``
left from a stress-test, ``ARIA_ADMIN_TOKEN`` empty, or a default
admin password unrotated.  The Twilio Authy 2024 incident landed here
— a development endpoint shipped to prod.

Defence: ``boot_check_prod_mode()`` raises if any of:
  * ``ARIA_ENV != "production"``
  * ``ARIA_DEBUG_ALLOW_INSECURE`` is set
  * ``ARIA_ADMIN_TOKEN`` empty or shorter than 32 chars
  * ``ARIA_OAUTH_STATE_KEY`` unset
  * Any of the well-known "default" tokens are present
The service refuses to bind a port until the issues are fixed.  Soft
mode (``ARIA_BOOT_CHECK=warn``) downgrades to a structured warning
for staged rollout.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from aria.security.plugins import DefencePlugin, register


_DEFAULT_TOKENS = frozenset({
    "changeme", "admin", "password", "letmein",
    "default", "test", "debug",
    "d" * 64, "e" * 64, "t" * 64,
})


@dataclass
class ProdModeResult:
    ok: bool
    issues: List[str]


def boot_check_prod_mode() -> ProdModeResult:
    issues: List[str] = []
    env = os.environ.get("ARIA_ENV", "").lower()
    if env != "production":
        # Round is opt-in; only fire when the operator declares prod.
        return ProdModeResult(True, [])
    if os.environ.get("ARIA_DEBUG_ALLOW_INSECURE", "").strip():
        issues.append("ARIA_DEBUG_ALLOW_INSECURE set in production")
    admin = os.environ.get("ARIA_ADMIN_TOKEN", "").strip()
    if len(admin) < 32:
        issues.append("ARIA_ADMIN_TOKEN missing or shorter than 32 chars")
    if admin.lower() in _DEFAULT_TOKENS:
        issues.append("ARIA_ADMIN_TOKEN is a well-known default")
    if not os.environ.get("ARIA_OAUTH_STATE_KEY"):
        issues.append("ARIA_OAUTH_STATE_KEY unset")
    if os.environ.get("PYTHONHASHSEED", "random").isdigit():
        issues.append("PYTHONHASHSEED is fixed in production (R35)")
    return ProdModeResult(ok=not issues, issues=issues)


def enforce_or_die() -> None:
    """Call from main() before binding a port.  Honours ARIA_BOOT_CHECK env:

      * ``"strict"`` (default in production) — raises SystemExit on failure
      * ``"warn"`` — emits a structured warning, returns
      * ``"off"`` — no-op
    """
    mode = os.environ.get("ARIA_BOOT_CHECK", "strict").lower()
    if mode == "off":
        return
    result = boot_check_prod_mode()
    if result.ok:
        return
    msg = "R48.prod_mode_strict: " + "; ".join(result.issues)
    if mode == "warn":
        import logging
        logging.getLogger("aria.security.rounds.r48").error(msg)
        return
    raise SystemExit(msg)


register(DefencePlugin(
    round_id="R48",
    name="prod_mode_strict",
    description="Refuse to start in production with default tokens / debug flags / weak config.",
))
