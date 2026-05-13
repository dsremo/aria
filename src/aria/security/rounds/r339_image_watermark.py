"""R339 — Image watermark verification (Stable Signature class).

Threat: AI-generated images with no watermark blend into authentic
content; the SynthID, Stable Signature, and IPTC Digital Source
Type fields are early proposals that responsible providers embed.

Defence: a metadata-pass that looks for a known watermark marker
(IPTC ``digitalSourceType``, EXIF ``Comment`` patterns, custom XMP
namespace).  Soft helper — confidence depends on the upstream
generator cooperating.
"""

from __future__ import annotations

from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_AI_DIGITAL_SOURCE_VALUES = {
    "trainedAlgorithmicMedia",
    "compositeWithTrainedAlgorithmicMedia",
    "algorithmicMedia",
}


def detect_watermark_metadata(metadata: dict) -> Tuple[str, str]:
    """Returns (source, evidence).  source ∈ {ai, ai_assisted, human, unknown}."""
    md = metadata or {}
    iptc = md.get("iptc:digitalSourceType") or md.get("digitalSourceType") or ""
    if isinstance(iptc, str) and iptc.split(":")[-1] in _AI_DIGITAL_SOURCE_VALUES:
        return "ai", f"iptc:{iptc}"
    xmp = md.get("xmp:c2pa.synthesised") or md.get("c2pa:synthesised")
    if xmp:
        return "ai", f"c2pa.synthesised:{xmp}"
    exif_comment = (md.get("EXIF:UserComment") or md.get("UserComment") or "")
    if isinstance(exif_comment, str) and any(
        marker in exif_comment.lower() for marker in ("synthid", "stable_signature", "ai-generated")
    ):
        return "ai", f"exif:{exif_comment[:64]}"
    if md.get("c2pa:digitalSourceType") == "humanEdits":
        return "ai_assisted", "c2pa:humanEdits"
    if md.get("xmp:dc.creator") and not iptc:
        return "human", "creator_present"
    return "unknown", ""


def is_ai_generated(metadata: dict) -> bool:
    src, _ = detect_watermark_metadata(metadata)
    return src == "ai"


register(DefencePlugin(
    round_id="R339",
    name="image_watermark",
    description="Image-metadata watermark detector (IPTC digitalSourceType + C2PA + EXIF).",
))
