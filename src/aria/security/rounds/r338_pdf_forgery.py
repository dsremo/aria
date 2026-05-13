"""R338 — PDF document forgery detection (metadata + structure).

Threat: contracts, IDs, bank statements forged in Photoshop or PDF
editors leave structural fingerprints — incremental update objects,
mismatched producer/creator fields, missing /Sig dictionary on
documents claiming digital signature.

Defence: structural audit of a PDF blob (no parsing of arbitrary
streams — just header / trailer scan).  Flags incremental updates,
missing signatures on ``/Type /Sig`` claims, and producer/creator
mismatches against vendor allow-lists.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_TRUSTED_PRODUCERS = {
    "adobe acrobat", "microsoft word", "libreoffice", "google docs",
    "pdfkit", "weasyprint", "wkhtmltopdf",
}


def audit_pdf_structure(blob: bytes) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if len(blob) < 64 or not blob.startswith(b"%PDF-"):
        return False, ["pdf.not_pdf"]

    # Count incremental updates (each ends with %%EOF)
    eof_count = blob.count(b"%%EOF")
    if eof_count > 1:
        issues.append(f"pdf.incremental_updates:{eof_count - 1}")

    # Producer + Creator metadata lines
    producer_match = re.search(rb"/Producer\s*\(([^)]{1,200})\)", blob)
    creator_match = re.search(rb"/Creator\s*\(([^)]{1,200})\)", blob)
    producer = (producer_match.group(1).decode("latin-1", errors="ignore") if producer_match else "").lower()
    creator = (creator_match.group(1).decode("latin-1", errors="ignore") if creator_match else "").lower()

    if producer and not any(t in producer for t in _TRUSTED_PRODUCERS):
        issues.append(f"pdf.untrusted_producer:{producer[:64]}")
    if creator and producer and creator.split()[0] not in producer and producer.split()[0] not in creator:
        issues.append("pdf.producer_creator_mismatch")

    # /Sig claim without /Contents key (missing signature value)
    if b"/Type /Sig" in blob and b"/Contents" not in blob:
        issues.append("pdf.sig_claim_no_contents")

    # ModifyDate before CreationDate
    cdate = re.search(rb"/CreationDate\s*\(D:(\d{14})", blob)
    mdate = re.search(rb"/ModDate\s*\(D:(\d{14})", blob)
    if cdate and mdate and mdate.group(1) < cdate.group(1):
        issues.append("pdf.mod_before_creation")

    return not issues, issues


register(DefencePlugin(
    round_id="R338",
    name="pdf_forgery",
    description="PDF structural audit: incremental updates + producer + signature claims.",
))
