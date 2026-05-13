"""R70 — Strict SAML assertion validation.

Threat: Microsoft SAML XML-signature-wrapping (XSW) and "Golden SAML"
(SolarWinds 2020 supply-chain) and the broader CVE-2022-21824 class
let an attacker who controls a single signed assertion forge unrelated
identities.  The defence is meticulous schema-strict validation:
exactly one assertion, unmodified canonical form, signed-element
covers the whole assertion.

Defence: this round ships the XSW pre-flight: parses the assertion
with our defused XML parser (R-foundation `safe_xml_fromstring`),
counts ``Assertion`` elements (must be 1), checks that the
``Signature`` element wraps the assertion root, and compares the
``ID`` attribute referenced in the signature to the ID of the actual
assertion element.  Real cryptographic signature verify is delegated
to the operator's existing IdP library; this round is the structural
gate that catches XSW BEFORE the verify.
"""

from __future__ import annotations

from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def preflight_xsw(saml_xml: bytes) -> Tuple[bool, List[str]]:
    """Return ``(safe, issues)``.  Safe = passes XSW pre-flight."""
    issues: List[str] = []
    try:
        from aria.security.guard import XMLDisallowed, safe_xml_fromstring
        try:
            root = safe_xml_fromstring(saml_xml)
        except XMLDisallowed as exc:
            return False, [f"xml_disallowed:{exc}"]
    except ImportError:
        return False, ["safe_xml_fromstring_unavailable"]

    # Find every Assertion element
    ns = "{urn:oasis:names:tc:SAML:2.0:assertion}"
    sig_ns = "{http://www.w3.org/2000/09/xmldsig#}"
    assertions = root.findall(f".//{ns}Assertion")
    if len(assertions) != 1:
        issues.append(f"assertion_count={len(assertions)} (expected 1)")
        return False, issues
    a = assertions[0]
    a_id = a.get("ID")
    if not a_id:
        issues.append("assertion_missing_id")

    # Find the Signature; its Reference URI must point to the assertion ID
    sigs = a.findall(f".//{sig_ns}Signature")
    if len(sigs) != 1:
        issues.append(f"signature_count={len(sigs)} (expected 1)")
        return False, issues
    refs = sigs[0].findall(f".//{sig_ns}Reference")
    if not refs:
        issues.append("no_reference_in_signature")
        return False, issues
    uri = refs[0].get("URI", "").lstrip("#")
    if uri != (a_id or ""):
        issues.append(f"signature_targets_wrong_id ref={uri!r} assertion={a_id!r}")
        return False, issues

    # Detect XSW: are there ANY Assertion-shaped fragments outside the canonical one?
    same_tag_anywhere = root.findall(f".//{ns}Assertion")
    if len(same_tag_anywhere) > 1:
        issues.append(f"extra_assertion_fragments={len(same_tag_anywhere)}")
        return False, issues

    return True, issues


register(DefencePlugin(
    round_id="R70",
    name="saml_assertion",
    description="SAML XSW pre-flight: 1 assertion, signature targets assertion ID.",
))
