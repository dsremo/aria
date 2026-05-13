"""R273 — Database row-level security (RLS) policy audit.

Threat: a multi-tenant DB without RLS depends on the *application* to
filter ``WHERE tenant_id = ?`` correctly on every query.  One missing
WHERE clause = full cross-tenant breach.  Postgres + Snowflake + most
modern DBs offer RLS; uptake is low because configuration is brittle.

Defence: ``audit_rls_policies`` ingests a list of (table,
has_rls_enabled, force_rls, policies) tuples and refuses tables whose
RLS is disabled or whose policies allow USING (true).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class RLSTable:
    name: str
    rls_enabled: bool = False
    force_rls: bool = False
    policies: List[str] = field(default_factory=list)


def audit_rls_policies(tables: Iterable[RLSTable]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for t in tables:
        if not t.rls_enabled:
            issues.append(f"rls.disabled:{t.name}")
            continue
        if not t.force_rls:
            issues.append(f"rls.not_forced:{t.name}")
        if not t.policies:
            issues.append(f"rls.no_policies:{t.name}")
        for p in t.policies:
            if "using (true)" in p.lower() or "using true" in p.lower():
                issues.append(f"rls.permissive_using_true:{t.name}")
    return not issues, issues


def recommend_pg_policy(table: str, tenant_column: str = "tenant_id") -> str:
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {table}_tenant_isolation ON {table} "
        f"USING ({tenant_column} = current_setting('app.tenant_id')::uuid);"
    )


register(DefencePlugin(
    round_id="R273",
    name="row_level_security",
    description="DB row-level security audit; refuse disabled/not-forced/USING (true) policies.",
))
