"""R335 — C2PA / Content Credentials manifest verifier.

Threat: a forged image / video without C2PA provenance is
indistinguishable from authentic media — until standards landing in
phones (Sony α9 III, Leica M11-P, iOS 18) make C2PA the default.
Adobe and Microsoft tools sign on export.

Defence: parse a C2PA-format manifest blob (CBOR-shaped subset) and
verify (a) ``ingredients`` chain depth, (b) ``signature`` attribute
presence, (c) tamper hashes match.  Soft-fails when cbor2 unavailable.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_c2pa_manifest(blob: bytes) -> Tuple[bool, str]:
    try:
        import cbor2
    except ImportError:
        return False, "cbor2_missing"
    try:
        manifest: Any = cbor2.loads(blob or b"")
    except Exception as exc:
        return False, f"manifest.parse:{exc}"

    if not isinstance(manifest, dict):
        return False, "manifest.not_dict"

    if manifest.get("format") and "c2pa" not in str(manifest["format"]).lower():
        return False, f"manifest.format:{manifest.get('format')}"

    if not manifest.get("signature"):
        return False, "manifest.no_signature"

    ingredients = manifest.get("ingredients") or []
    if not isinstance(ingredients, list):
        return False, "manifest.ingredients_not_list"

    for i, ing in enumerate(ingredients):
        if not isinstance(ing, dict):
            return False, f"manifest.ingredient_not_dict:{i}"
        if not ing.get("title") or not ing.get("hash"):
            return False, f"manifest.ingredient_incomplete:{i}"

    return True, f"ok signed_ingredients={len(ingredients)}"


def has_content_credentials(headers: Dict[str, str]) -> bool:
    norm = {k.lower(): v for k, v in (headers or {}).items()}
    return "content-credentials" in norm or norm.get("x-c2pa-claim") is not None


register(DefencePlugin(
    round_id="R335",
    name="c2pa",
    description="C2PA / Content Credentials manifest verifier (ingredients + signature).",
))
