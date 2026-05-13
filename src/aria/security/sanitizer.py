"""Input Sanitizer — prevents prompt injection and malformed data.

it enters the cognitive engine or tool system.

TT&C audit H-6: pre-regex normalisation:
  * NFKC Unicode normalisation defeats homoglyph + half-width tricks.
  * Bidi-control character (U+202A..U+202E, U+2066..U+2069) stripping
    rejects RTL/LTR-override jailbreaks.
  * Base64-blob detection flags any large opaque base64 string in
    free-text command bodies (commonly used to smuggle obfuscated
    instructions past a regex bank).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

# Patterns that should never appear in telemetry or sensor data
INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(previous|all)\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"override.*authority", re.IGNORECASE),
    re.compile(r"disregard.*safety", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"eval\s*\(", re.IGNORECASE),
    re.compile(r"exec\s*\(", re.IGNORECASE),
    re.compile(r"__import__", re.IGNORECASE),
    re.compile(r"os\.system", re.IGNORECASE),
]

# TT&C audit H-6 — Unicode bidi-control + format-character filter.  These
# code points re-order glyphs at render time and have no legitimate use
# in operator commands; refuse to normalise them away because that would
# silently change command intent.  Reject the message instead.
_BIDI_CONTROL_CODEPOINTS = frozenset({
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,    # LRE/RLE/PDF/LRO/RLO
    0x2066, 0x2067, 0x2068, 0x2069,            # LRI/RLI/FSI/PDI
    0x200E, 0x200F,                            # LRM, RLM
    0x061C,                                    # Arabic letter mark
})

# A "suspicious" base64 blob is >= 32 contiguous base64 characters.
# Legitimate operator commands almost never embed such payloads in
# free text.  An attacker can use it to hide encoded instructions.
_BASE64_BLOB_RE = re.compile(r"[A-Za-z0-9+/=]{32,}")


def _has_bidi_controls(text: str) -> bool:
    return any(ord(ch) in _BIDI_CONTROL_CODEPOINTS for ch in text)


def _strip_bidi_controls(text: str) -> str:
    return "".join(
        ch for ch in text if ord(ch) not in _BIDI_CONTROL_CODEPOINTS
    )


@dataclass
class SanitizeResult:
    clean: bool
    original: str
    sanitized: str
    patterns_found: list[str]


class InputSanitizer:
    """Sanitizes inputs to prevent injection attacks.

    Checks:
      1. Prompt injection patterns in text data
      2. Numeric range validation for telemetry
      3. String length limits
      4. Character set validation
    """

    def __init__(self, max_string_length: int = 10_000) -> None:
        self._max_len = max_string_length

    def sanitize_text(self, text: str, source: str = "") -> SanitizeResult:
        """Check text for injection patterns. Returns sanitized version.

        TT&C audit H-6 hardenings (pre-regex):
          * NFKC normalisation collapses homoglyph + half-width.
          * Bidi-control characters cause an immediate fail.
          * Suspicious base64 blobs (>= 32 chars) cause a fail.
        """
        if not text:
            return SanitizeResult(clean=True, original="", sanitized="", patterns_found=[])

        original = text

        # Length check (apply early so a huge bidi-stuffed payload
        # doesn't OOM the normaliser).
        if len(text) > self._max_len:
            text = text[:self._max_len]

        found_patterns: list[str] = []

        # Bidi-control rejection.
        if _has_bidi_controls(text):
            found_patterns.append("bidi_control_chars")
            text = _strip_bidi_controls(text)

        # NFKC normalisation defeats homoglyph attacks (e.g. Cyrillic
        # 'а' (U+0430) collapsed to ASCII 'a').
        normalised = unicodedata.normalize("NFKC", text)
        if normalised != text:
            found_patterns.append("nfkc_normalisation_changed_text")
            text = normalised

        # Suspicious base64 blobs.
        if _BASE64_BLOB_RE.search(text):
            found_patterns.append("base64_blob_in_free_text")

        sanitized = text

        for pattern in INJECTION_PATTERNS:
            if pattern.search(text):
                found_patterns.append(pattern.pattern)
                sanitized = pattern.sub("[SANITIZED]", sanitized)

        if found_patterns:
            logger.warning(
                "sanitizer.injection_detected",
                source=source,
                patterns=len(found_patterns),
                sample=original[:100],
            )

        return SanitizeResult(
            clean=len(found_patterns) == 0,
            original=original,
            sanitized=sanitized,
            patterns_found=found_patterns,
        )

    def validate_telemetry_value(
        self,
        value: float,
        channel: str,
        min_val: float = -1e10,
        max_val: float = 1e10,
    ) -> bool:
        """Validate a telemetry value is within physical bounds."""
        import math

        if math.isnan(value) or math.isinf(value):
            logger.warning("sanitizer.invalid_telemetry", channel=channel, value=value)
            return False

        if value < min_val or value > max_val:
            logger.warning(
                "sanitizer.telemetry_out_of_range",
                channel=channel,
                value=value,
                min=min_val,
                max=max_val,
            )
            return False

        return True


# Patterns specific to tool results that could manipulate LLM reasoning
TOOL_RESULT_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    *INJECTION_PATTERNS,
    re.compile(r"<\s*/?system\s*>", re.IGNORECASE),
    re.compile(r"<\s*/?human\s*>", re.IGNORECASE),
    re.compile(r"<\s*/?assistant\s*>", re.IGNORECASE),
    re.compile(r"IMPORTANT:\s*ignore", re.IGNORECASE),
    re.compile(r"NEW\s+INSTRUCTIONS", re.IGNORECASE),
    re.compile(r"act\s+as\s+if", re.IGNORECASE),
    re.compile(r"pretend\s+(that|you)", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+safety", re.IGNORECASE),
]


class ToolResultSanitizer:
    """Sanitizes tool results before they enter LLM context.

    Per CENTRAL_AI_MASTER_PLAN Part 11.3 — prevents prompt injection
    via crafted sensor data or tool responses that could alter ARIA's reasoning.

    This is critical because:
      - Telemetry data flows from external sensors into LLM context
      - A crafted sensor value string could contain injection payload
      - Tool results from external APIs could be compromised
    """

    def __init__(self, max_result_length: int = 50_000) -> None:
        self._max_len = max_result_length

    def sanitize(self, data: str, tool_name: str = "") -> SanitizeResult:
        """Sanitize a tool result string before including in LLM context.

        On top of the regex pattern bank we also run:
          * ``aria.security.psyops.detect_influence`` — Cialdini-axis
            scoring; high-axis tool results are stripped before they
            reach the LLM, since the model can't tell weaponised
            persuasion from legitimate text once it's in-context.
          * ``aria.security.honeypot_llm.scan_for_decoys`` — if a tool
            result contains an active decoy token, it means the
            external API is reflecting our own context back, which is
            an exfil signature.
        """
        if not data:
            return SanitizeResult(clean=True, original="", sanitized="", patterns_found=[])

        # Truncate oversized results
        if len(data) > self._max_len:
            data = data[:self._max_len] + f"... [TRUNCATED at {self._max_len} chars]"

        found_patterns: list[str] = []
        sanitized = data

        for pattern in TOOL_RESULT_INJECTION_PATTERNS:
            if pattern.search(data):
                found_patterns.append(pattern.pattern)
                sanitized = pattern.sub("[SANITIZED: suspicious content removed]", sanitized)

        # Cialdini-axis influence scoring (R50 foundation).
        try:
            from aria.security.psyops import detect_influence
            inf = detect_influence(data)
            if inf.alert:
                found_patterns.append(f"psyops:{inf.dominant_axis}:{inf.score:.2f}")
                if inf.block:
                    # Strip whole result — too dangerous to ship to the LLM.
                    sanitized = "[SANITIZED: tool result removed (influence-attack pattern)]"
                else:
                    # Strip only matched snippets so the operator sees what triggered.
                    for snip in inf.matched_patterns:
                        sanitized = sanitized.replace(snip.split(": ", 1)[-1].strip("…"), "[REDACTED]")
        except Exception:
            pass

        # Decoy-token exfiltration check (R50 foundation).
        try:
            from aria.security.honeypot_llm import scan_for_decoys
            decoys = scan_for_decoys(data, where=f"tool_result:{tool_name}")
            if decoys:
                found_patterns.append(f"decoy_exfil:{len(decoys)}_tokens")
                # Strip all decoys from the version that reaches the LLM.
                for tok in decoys:
                    sanitized = sanitized.replace(tok, "[REDACTED:decoy]")
        except Exception:
            pass

        if found_patterns:
            logger.warning(
                "sanitizer.tool_result_injection",
                tool=tool_name,
                patterns=len(found_patterns),
                sample=data[:200],
            )

        return SanitizeResult(
            clean=len(found_patterns) == 0,
            original=data,
            sanitized=sanitized,
            patterns_found=found_patterns,
        )
