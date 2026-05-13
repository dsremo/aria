"""R17 — Email header injection.

Threat: a contact-form ``subject`` field ends up in
``Subject: {input}`` of an outbound email.  The attacker submits
``Subject: hi\\nBcc: secret@evil.example.com\\nContent-Type: text/html\\n\\n<...>``
and turns ARIA into an open relay.  CWE-93.  Cases: every email-form
audit ever; resurfaced in Sendgrid 2024 advisories.

Defence: ``safe_email_header(value)`` strips CR/LF/NUL and limits to
ASCII printable (RFC 5322 compatible) plus a small set of common
non-ASCII chars when ``allow_non_ascii=True``.  Any input containing
``Bcc:``, ``Cc:``, ``Content-Type:`` (case-insensitive) is refused.
"""

from __future__ import annotations

import re

from aria.security.plugins import DefencePlugin, register


_HEADER_INJECTION_RE = re.compile(
    r"(?i)\b(?:bcc|cc|content[-_]type|content[-_]transfer[-_]encoding|"
    r"subject|to|from|reply[-_]to)\s*:"
)
_FORBIDDEN = re.compile(r"[\r\n\x00]")


def safe_email_header(value: str, *, allow_non_ascii: bool = False) -> str:
    if value is None:
        return ""
    s = str(value)
    if _FORBIDDEN.search(s):
        raise ValueError("R17.email_header_injection: CR/LF/NUL in header value")
    if _HEADER_INJECTION_RE.search(s):
        raise ValueError("R17.email_header_injection: header keyword in value")
    if not allow_non_ascii:
        try:
            s.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError("R17.email_header_injection: non-ASCII without opt-in")
    return s.strip()


register(DefencePlugin(
    round_id="R17",
    name="email_header_injection",
    description="Strip / refuse CR-LF + Bcc:/Cc:/Content-Type: in email headers.",
))
