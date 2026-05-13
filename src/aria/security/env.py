"""Environment-mode helpers.

Round-2 audit NEW-HIGH-17 closed an inconsistency where some modules
checked ``ARIA_ENV == "production"`` and others ``ARIA_ENV == "prod"``,
so an operator setting one value passed half the boot checks and
silently failed the other half.

This module is the single source of truth.  Replace every direct
``os.environ.get("ARIA_ENV")`` comparison with ``is_production()``.
"""

from __future__ import annotations

import os

# Set of strings that mean "this is production-equivalent."  Adding a
# new alias here also picks up every consumer of ``is_production()``.
_PRODUCTION_VALUES = {"prod", "production", "live", "mainnet"}
_STAGING_VALUES = {"stage", "staging", "preprod", "pre-prod"}


def aria_env() -> str:
    """Return ``ARIA_ENV`` lower-cased, with surrounding whitespace stripped.

    Useful for tests + structured-log output.  Empty string when unset.
    """
    return (os.environ.get("ARIA_ENV") or "").strip().lower()


def is_production() -> bool:
    """True when ARIA_ENV indicates a production-equivalent deployment."""
    return aria_env() in _PRODUCTION_VALUES


def is_staging() -> bool:
    return aria_env() in _STAGING_VALUES


def require_production_secret(name: str) -> str:
    """Read ``name`` from the env, raising in production when missing."""
    val = os.environ.get(name) or ""
    if is_production() and not val:
        raise RuntimeError(
            f"env.require_production_secret — {name} required in production"
        )
    return val
