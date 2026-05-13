"""Tests for tenant context propagation via asyncio ContextVar.

All tests are pure unit tests — no DB required.
"""

from __future__ import annotations

import asyncio

import pytest

from aria.dsremo.core.tenant import get_tenant, set_tenant


class TestGetTenant:
    def test_default_is_default(self):
        """Without any setup, tenant is always 'default'."""
        assert get_tenant() == "default"

    def test_set_then_get(self):
        set_tenant("acme-corp")
        assert get_tenant() == "acme-corp"
        # Reset for other tests
        set_tenant("default")

    def test_set_empty_string(self):
        """Empty string is a valid tenant ID (edge case — middleware enforces non-empty)."""
        set_tenant("")
        assert get_tenant() == ""
        set_tenant("default")

    def test_set_multiple_times(self):
        """Last set wins within the same task."""
        set_tenant("alpha")
        set_tenant("beta")
        set_tenant("gamma")
        assert get_tenant() == "gamma"
        set_tenant("default")


class TestTenantIsolation:
    """ContextVar is asyncio task-scoped — tasks must not bleed context."""

    @pytest.mark.asyncio
    async def test_tasks_get_independent_copies(self):
        """Two concurrent tasks each see only their own tenant."""
        results: dict[str, str] = {}

        async def task_a():
            set_tenant("tenant-a")
            await asyncio.sleep(0)   # yield so task_b can run
            results["a"] = get_tenant()

        async def task_b():
            set_tenant("tenant-b")
            await asyncio.sleep(0)
            results["b"] = get_tenant()

        await asyncio.gather(task_a(), task_b())

        assert results["a"] == "tenant-a"
        assert results["b"] == "tenant-b"

    @pytest.mark.asyncio
    async def test_child_task_inherits_parent_context(self):
        """A child task created with asyncio.create_task inherits the parent's
        ContextVar snapshot at creation time, but mutations in the child do NOT
        flow back to the parent."""
        set_tenant("parent-tenant")

        child_saw: list[str] = []
        parent_after: list[str] = []

        async def child():
            child_saw.append(get_tenant())   # should see parent's value
            set_tenant("child-tenant")       # mutation stays in child

        task = asyncio.create_task(child())
        await task

        parent_after.append(get_tenant())    # parent unchanged

        assert child_saw[0] == "parent-tenant"
        assert parent_after[0] == "parent-tenant"

        set_tenant("default")

    @pytest.mark.asyncio
    async def test_default_tenant_in_new_task(self):
        """A fresh task with no setup returns 'default'."""
        result: list[str] = []

        async def fresh_task():
            result.append(get_tenant())

        await asyncio.create_task(fresh_task())
        assert result[0] == "default"

    @pytest.mark.asyncio
    async def test_concurrent_tenants_do_not_interfere(self):
        """100 concurrent tasks each set a unique tenant — verify no cross-contamination."""
        N = 100
        results: list[str] = [""] * N

        async def worker(i: int):
            tenant = f"tenant-{i:03d}"
            set_tenant(tenant)
            await asyncio.sleep(0)
            results[i] = get_tenant()

        await asyncio.gather(*(worker(i) for i in range(N)))

        for i in range(N):
            assert results[i] == f"tenant-{i:03d}", (
                f"Task {i} saw wrong tenant: {results[i]}"
            )
