"""R16 — CSV / spreadsheet formula injection.

Threat: ARIA exports a tenant-scoped report as CSV.  An attacker who
controls a string field ships ``=cmd|'/c calc'!A1`` or
``@SUM(1+1)*cmd|'/c notepad'!A1``.  When the spreadsheet is opened in
Excel / LibreOffice / Google Sheets, the formula executes (DDE on
Windows; HYPERLINK exfil on every platform).  CWE-1236.

Defence: ``escape_csv_field(value)`` prefixes a single quote (Excel's
text-coercion guard) when the field starts with the four classic
formula triggers ``= + - @`` — and any cell whose first byte is a
control character.  Also surfaces a ``safe_writerow(row)`` helper that
applies the escape to every column.
"""

from __future__ import annotations

import csv
import io
from typing import Iterable, List

from aria.security.plugins import DefencePlugin, register


_FORMULA_TRIGGERS = ("=", "+", "-", "@")
_CONTROL_FIRST_BYTES = tuple(chr(c) for c in range(0x00, 0x09)) + (
    "\t", "\n", "\r", "\x0b", "\x0c",
)


def escape_csv_field(value) -> str:
    """Return ``value`` coerced to text-safe form for spreadsheet apps.

    The rule: prepend ``'`` (single quote) when the first character
    triggers formula execution.  Pure-text fields are unchanged.
    Non-string values are stringified first.
    """
    if value is None:
        return ""
    s = str(value)
    if not s:
        return s
    first = s[0]
    if first in _FORMULA_TRIGGERS or first in _CONTROL_FIRST_BYTES:
        return "'" + s
    return s


def safe_writerow(writer, row: Iterable) -> None:
    """csv.writer-compatible row writer that escapes every cell."""
    writer.writerow([escape_csv_field(c) for c in row])


def emit_csv(rows: List[Iterable], *, header: List[str] | None = None) -> str:
    """Return a CSV blob with every cell escaped against formula attacks."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if header is not None:
        safe_writerow(w, header)
    for row in rows:
        safe_writerow(w, row)
    return buf.getvalue()


register(DefencePlugin(
    round_id="R16",
    name="csv_injection",
    description="Quote-prefix CSV cells whose first char triggers formula execution.",
))
