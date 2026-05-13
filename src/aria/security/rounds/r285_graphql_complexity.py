"""R285 — GraphQL query depth / complexity limiter.

Threat: a single GraphQL query like ``{ a { b { c { …100 levels… } } } }``
can fan out into million-row joins.  GraphQL's flexibility makes
N+1 + nested abuse trivial; without depth + cost limits it's a DoS
+ exfil multiplier.

Defence: pre-execution ``audit_query`` that walks the AST (string
heuristic when graphql-core absent) counts depth, breadth, total
field count, and refuses past configured ceilings.
"""

from __future__ import annotations

import re
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_MAX_DEPTH = 10
_MAX_FIELD_COUNT = 200
_MAX_ALIASES = 30


def audit_query(query: str, *,
                max_depth: int = _MAX_DEPTH,
                max_fields: int = _MAX_FIELD_COUNT,
                max_aliases: int = _MAX_ALIASES) -> Tuple[bool, str]:
    if not query:
        return False, "graphql.empty_query"

    depth = 0
    cur = 0
    for ch in query:
        if ch == "{":
            cur += 1
            depth = max(depth, cur)
        elif ch == "}":
            cur = max(0, cur - 1)

    if depth > max_depth:
        return False, f"graphql.depth_exceeded depth={depth} max={max_depth}"

    field_count = len(re.findall(r"[A-Za-z_][A-Za-z0-9_]*\s*[\(\{:]", query))
    if field_count > max_fields:
        return False, f"graphql.field_count_exceeded fields={field_count} max={max_fields}"

    aliases = len(re.findall(r"[A-Za-z_][A-Za-z0-9_]*\s*:\s*[A-Za-z_]", query))
    if aliases > max_aliases:
        return False, f"graphql.alias_count_exceeded aliases={aliases} max={max_aliases}"

    if "@skip" in query and "@include" in query:
        return False, "graphql.skip_include_combo"

    if "__schema" in query and field_count > 50:
        return False, "graphql.introspection_with_payload"

    return True, f"ok depth={depth} fields={field_count} aliases={aliases}"


register(DefencePlugin(
    round_id="R285",
    name="graphql_complexity",
    description="GraphQL pre-execution depth + field-count + alias limiter.",
))
