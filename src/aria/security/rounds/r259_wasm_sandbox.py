"""R259 — WebAssembly sandbox audit.

Threat: WebAssembly modules from third-party CDNs (analytics, A/B
tooling) execute with full memory + CPU access in the browser.  A
malicious or compromised wasm bypasses traditional XSS scanners.

Defence: enforce wasm execution only via instantiated module from a
SHA-256-pinned origin; refuse ``WebAssembly.compileStreaming`` from
non-pinned URLs.  Server-side audit of an HTML/JS payload refuses
inline ``new WebAssembly`` calls with non-bound buffers.
"""

from __future__ import annotations

import re
from typing import List, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_WASM_INSTANTIATE_RE = re.compile(
    r'WebAssembly\.(?:instantiate|compile)(?:Streaming)?\s*\(\s*(?:fetch\s*\(\s*["\']([^"\']+)["\']\s*\))?',
    re.IGNORECASE,
)
_RAW_BUFFER_RE = re.compile(
    r'new\s+WebAssembly\.(?:Module|Instance)\s*\(\s*new\s+(?:Uint8Array|ArrayBuffer)',
    re.IGNORECASE,
)


def audit_wasm_in_js(source: str, *, pinned_origins: Set[str] = None) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    pinned_origins = {o.rstrip("/") for o in (pinned_origins or set())}
    for m in _WASM_INSTANTIATE_RE.finditer(source or ""):
        url = m.group(1) or ""
        if not url:
            issues.append("wasm.compile_without_origin")
            continue
        origin = "/".join(url.split("/", 3)[:3])
        if origin not in pinned_origins:
            issues.append(f"wasm.unpinned_origin:{origin}")
    if _RAW_BUFFER_RE.search(source or ""):
        issues.append("wasm.raw_buffer_instantiate")
    return not issues, issues


register(DefencePlugin(
    round_id="R259",
    name="wasm_sandbox",
    description="WebAssembly sandbox audit: refuse unpinned origins + raw-buffer instantiation.",
))
