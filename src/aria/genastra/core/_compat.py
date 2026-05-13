"""Python version compatibility shims.

Allows local development on Python 3.10 even though the package
requires 3.11+. The CI matrix runs 3.11/3.12 only.
"""

import sys

if sys.version_info >= (3, 11):  # noqa: UP036
    from enum import StrEnum as StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """StrEnum backport for Python < 3.11."""
