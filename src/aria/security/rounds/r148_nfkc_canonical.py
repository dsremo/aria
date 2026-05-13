"""R148 — Unicode NFKC canonicalisation gate.

Threat: visually-confusable characters (Cyrillic ``а`` (U+0430)
vs Latin ``a`` (U+0061), the ``ı`` Turkish locale Smith problem from
SpoofChecker) let an attacker register ``аdmin@example.com`` that's
visually identical to ``admin@example.com``.  The 2017 ``аррlе.com``
phishing wave + ongoing fastly / GitHub findings document the class.

Defence: ``canonicalize(value)`` runs Unicode NFKC normalisation
+ then casefolds + strips zero-width.  ``contains_confusables(value)``
checks against a small bank of confusable scripts.  Operators
canonicalise BEFORE comparison + storage so an attacker can't slip a
homograph past the auth path.
"""

from __future__ import annotations

import unicodedata
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_CONFUSABLE_SCRIPTS = {
    "CYRILLIC SMALL LETTER A": "a",                # U+0430
    "CYRILLIC SMALL LETTER E": "e",                # U+0435
    "CYRILLIC SMALL LETTER O": "o",                # U+043E
    "CYRILLIC SMALL LETTER P": "p",                # U+0440
    "CYRILLIC SMALL LETTER C": "c",                # U+0441
    "CYRILLIC SMALL LETTER X": "x",                # U+0445
    "CYRILLIC SMALL LETTER U": "u",                # U+0443
    "CYRILLIC SMALL LETTER NJE": "n",              # variants
    "GREEK SMALL LETTER OMICRON": "o",             # U+03BF
    "GREEK SMALL LETTER ETA": "n",                 # U+03B7
}


def canonicalize(value: str) -> str:
    """Return NFKC + casefolded + ZWSP-stripped text."""
    if not value:
        return ""
    s = unicodedata.normalize("NFKC", value).casefold()
    # Strip zero-width / bidi controls
    out = []
    for ch in s:
        if 0x200B <= ord(ch) <= 0x200F:
            continue
        if 0x202A <= ord(ch) <= 0x202E:
            continue
        if ord(ch) == 0xFEFF:
            continue
        out.append(ch)
    return "".join(out)


def contains_confusables(value: str) -> Tuple[bool, list]:
    """Return ``(found, [original_char_names])`` if ``value`` mixes
    scripts that look the same."""
    found: list = []
    for ch in value:
        try:
            name = unicodedata.name(ch, "")
        except ValueError:
            continue
        if name in _CONFUSABLE_SCRIPTS:
            found.append((ch, name))
    return len(found) > 0, found


register(DefencePlugin(
    round_id="R148",
    name="nfkc_canonical",
    description="NFKC + casefold + ZWSP-strip; confusable-script detector.",
))
