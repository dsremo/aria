"""R76 — Use-after-free hint via Python __del__ poisoning.

Threat: in CPython, ``__del__`` is called when refcount hits zero.  A
buggy callback can resurrect an object after free; subsequent use is
UAF.  Recent: aiohttp had a UAF-class bug in 2023 streaming responses.
For the cFS C bridge (Block I) the ASAN flag below catches it
instrumentally.

Defence: a small ``track_lifetime(obj)`` helper that wraps an object's
``__del__`` to mark a "freed" state in a TLS map; if any subsequent
attribute access happens, raise.  This is a debugging / CI tool, not
production code (the overhead is non-trivial).
"""

from __future__ import annotations

import threading
import weakref
from typing import Any

from aria.security.plugins import DefencePlugin, register


_FREED: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
_LOCK = threading.Lock()


def track_lifetime(obj: Any, *, label: str = "") -> Any:
    """Wrap ``obj`` so any attribute access after its declared free
    raises ``UseAfterFree``.  Returns ``obj`` unchanged for chaining.
    Caller declares free via ``mark_freed(obj)``."""

    class _Tracked(type(obj)):                           # type: ignore[misc]
        def __getattribute__(self, name):
            with _LOCK:
                if id(self) in _FREED:
                    raise UseAfterFree(
                        f"R76: use-after-free on {label or type(self).__name__}",
                    )
            return type(obj).__getattribute__(self, name)
    # Re-class the instance.  Only safe for plain Python objects; bail on slots/C.
    try:
        obj.__class__ = _Tracked
    except (TypeError, AttributeError):
        return obj            # untrackable
    return obj


def mark_freed(obj: Any) -> None:
    with _LOCK:
        _FREED[id(obj)] = obj


class UseAfterFree(RuntimeError):
    """Raised when a tracked object is touched after being marked freed."""


register(DefencePlugin(
    round_id="R76",
    name="use_after_free_hint",
    description="Python lifetime tracker; raise UseAfterFree on post-free access.",
))
