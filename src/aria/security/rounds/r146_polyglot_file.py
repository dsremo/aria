"""R146 — Polyglot file detection (PNG+JS, PDF+ZIP, image+HTML).

Threat: a file that is simultaneously a valid PNG (via the magic
bytes the image renderer reads) AND valid JavaScript (via the parser
the browser reads) lets an attacker bypass MIME-type filters.  See
SHAttered (2017), the 2024 Polyglot ZIP-PDF advisory, and the
ImageMagick coder vulns.

Defence: ``detect_polyglot(blob)`` checks the leading bytes against
multiple format signatures + scans the body for foreign magic bytes
in unexpected positions.  Returns a list of every format the blob
could be parsed as.
"""

from __future__ import annotations

from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_MAGIC = {
    b"\x89PNG\r\n\x1a\n":      "png",
    b"GIF87a":                  "gif",
    b"GIF89a":                  "gif",
    b"\xff\xd8\xff":            "jpeg",
    b"%PDF-":                   "pdf",
    b"PK\x03\x04":              "zip",
    b"PK\x05\x06":              "zip_empty",
    b"PK\x07\x08":              "zip_split",
    b"\x1f\x8b\x08":            "gzip",
    b"<?xml":                   "xml",
    b"<!DOCTYPE":               "html_or_xml",
    b"<html":                   "html",
    b"<svg":                    "svg",
    b"\x7fELF":                 "elf",
    b"MZ":                      "pe",
    b"#!":                      "shebang",
    b"<script":                 "script_tag",
}


def detect_polyglot(blob: bytes) -> Tuple[bool, List[str]]:
    """Return ``(is_polyglot, [formats])``.  Polyglot iff > 1 format claims."""
    if not blob:
        return False, []
    formats: List[str] = []
    head = blob[:512]
    for sig, name in _MAGIC.items():
        if head.startswith(sig):
            formats.append(f"head:{name}")
    # Search for foreign magic anywhere in the first 4 KiB
    body = blob[:4096]
    for sig, name in _MAGIC.items():
        if sig in body[len(sig):]:        # skip head
            formats.append(f"body:{name}")
    formats = list(dict.fromkeys(formats))    # dedupe preserve order
    return len(formats) > 1, formats


register(DefencePlugin(
    round_id="R146",
    name="polyglot_file",
    description="Detect files matching > 1 format (head magic + body scan).",
))
