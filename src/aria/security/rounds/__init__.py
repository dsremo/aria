"""Round-by-round defences (R1 ... R51).

Each module under this package registers a :class:`DefencePlugin` with
:mod:`aria.security.plugins`.  Importing this package triggers every
registration in dependency-free order; the canonical entry point is
``aria.security.guard.activate_all_rounds()``.

Every round is named ``rNN_short_topic.py`` for grep-ability and is a
self-contained ~30–80 LoC module:

  1. One paragraph **threat** description tied to a real CVE / breach.
  2. The detection function(s).
  3. A single ``register(DefencePlugin(round_id="RN", ...))`` call.

Tests live in ``tests/integration/test_security_rounds.py``.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import List

logger = logging.getLogger("aria.security.rounds")


def activate_all(*, force_reload: bool = False) -> List[str]:
    """Import every ``rNN_*`` module in this package.  Returns the list
    of round IDs successfully loaded.

    When called repeatedly after ``aria.security.plugins.clear_for_tests()``,
    pass ``force_reload=True`` so each round module re-runs its
    ``register(...)`` call (Python caches imports otherwise).
    """
    import sys
    loaded: List[str] = []
    pkg = importlib.import_module(__name__)
    for info in pkgutil.iter_modules(pkg.__path__):
        if not info.name.startswith("r") or "_" not in info.name:
            continue
        full = f"{__name__}.{info.name}"
        try:
            mod = sys.modules.get(full)
            if mod is None:
                importlib.import_module(full)
            elif force_reload:
                importlib.reload(mod)
            loaded.append(info.name.split("_", 1)[0].upper())
        except Exception as exc:           # pragma: no cover
            logger.warning(
                "rounds.load_failed module=%s err=%s", info.name, exc,
            )
    return loaded


__all__ = ["activate_all"]
