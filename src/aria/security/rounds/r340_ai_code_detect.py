"""R340 — AI-generated code detection.

Threat: code-suggestion tools sometimes hallucinate library calls
(typo-squat material), introduce subtle license violations, or
recreate copyrighted snippets.  Repos that don't track AI-generated
sections fail SLSA + audit.

Defence: a heuristic scorer that flags Python/JS files with markers
typical of AI-generated code — idealised docstrings on every
function, named parameters that mirror the prompt, oddly perfect
Sphinx-style documentation, hallucinated imports.
"""

from __future__ import annotations

import re
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_DOCSTRING_RE = re.compile(r'"""[\s\S]+?"""')
_IDEALISED_PARAGRAPHS = re.compile(
    r'(?:Args|Parameters|Returns|Raises)\s*:\s*\n\s+\w+\s*[\(:]', re.IGNORECASE,
)
_BANNED_NAMES = {
    "from utility_helpers import", "from common_utils import",
    "import super_libraries", "from helper_functions import",
}


def score_python_file(source: str) -> Tuple[float, str]:
    body = source or ""
    if len(body) < 200:
        return 0.0, "too_short"

    score = 0.0
    notes = []

    docstrings = _DOCSTRING_RE.findall(body)
    funcs = re.findall(r"^\s*def\s+\w+\s*\(", body, flags=re.MULTILINE)
    if funcs:
        ratio = min(1.0, len(docstrings) / max(1, len(funcs)))
        if ratio > 0.9 and len(funcs) > 3:
            score += 0.3
            notes.append(f"docstring_per_fn:{ratio:.2f}")
        idealised = sum(1 for d in docstrings if _IDEALISED_PARAGRAPHS.search(d))
        if idealised / max(1, len(docstrings)) > 0.5:
            score += 0.3
            notes.append("idealised_docstrings")

    if any(b in body for b in _BANNED_NAMES):
        score += 0.4
        notes.append("hallucinated_imports")

    todos = body.count("# TODO") + body.count("# todo")
    if todos == 0 and len(body) > 1500 and len(funcs) > 5:
        score += 0.1
        notes.append("zero_todos_in_large_file")

    return min(1.0, score), ",".join(notes) or "ok"


register(DefencePlugin(
    round_id="R340",
    name="ai_code_detect",
    description="AI-code heuristic scorer (docstring density + idealised paragraphs + hallucinated imports).",
))
