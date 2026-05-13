"""R274 — Stored procedure permission audit.

Threat: stored procedures with ``SECURITY DEFINER`` (Postgres) or
``EXECUTE AS OWNER`` (SQL Server) run with the procedure-creator's
privileges.  If the proc takes user input and concatenates into
dynamic SQL, every caller becomes a privilege-escalation lever.

Defence: parse a procedure definition (Postgres pl/pgsql heuristic)
and refuse SECURITY DEFINER procs that build dynamic SQL via EXECUTE.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFINER_RE = re.compile(r"\bSECURITY\s+DEFINER\b", re.IGNORECASE)
_INVOKER_RE = re.compile(r"\bSECURITY\s+INVOKER\b", re.IGNORECASE)
_DYNAMIC_EXEC_RE = re.compile(
    r"\bEXECUTE\s+(?:format\s*\(|['\"][^'\"]*?['\"]\s*\|\|)",
    re.IGNORECASE | re.DOTALL,
)
_SET_SEARCH_PATH_RE = re.compile(r"\bSET\s+search_path", re.IGNORECASE)


def audit_proc_definition(definition: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    body = definition or ""
    if _DEFINER_RE.search(body):
        if _DYNAMIC_EXEC_RE.search(body):
            issues.append("proc.definer_with_dynamic_sql")
        if not _SET_SEARCH_PATH_RE.search(body):
            issues.append("proc.definer_without_set_search_path")
    if not _DEFINER_RE.search(body) and not _INVOKER_RE.search(body):
        issues.append("proc.security_clause_missing")
    return not issues, issues


register(DefencePlugin(
    round_id="R274",
    name="stored_proc_perm",
    description="DB stored-procedure audit: refuse DEFINER + dynamic SQL without SET search_path.",
))
