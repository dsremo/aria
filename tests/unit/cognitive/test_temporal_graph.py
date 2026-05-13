"""Tests for the SQLite temporal knowledge graph.

Validates:
1.  add_node creates a node with auto-generated ID and current timestamp.
2.  get_node retrieves by ID; returns None for missing ID.
3.  get_or_create_node returns existing node on second call (no duplicate).
4.  update_node_properties merges without clobbering existing keys.
5.  invalidate_node sets invalidated_at; query_nodes(active_only) excludes it.
6.  add_edge creates a directed edge with correct from/to IDs.
7.  get_neighbors(direction="out") returns targets; direction="in" returns sources.
8.  get_neighbors(relation=X) filters to that relation.
9.  get_temporal_context returns nodes connected within the time window.
10. shortest_path finds the BFS path; returns None for disconnected nodes.
11. shortest_path returns single-node path when from == to.
12. close_edge sets valid_to; get_neighbors(active_only) excludes closed edges.
13. query_nodes filters by node_type, label_contains, since, active_only.
14. query_edges filters by relation and from_node.
15. stats() returns correct counts after add/invalidate.
16. TemporalGraph is isolated per-instance (":memory:" DB).
"""

from __future__ import annotations

import time

import pytest

from aria.memory.temporal_graph import GraphPath, TGEdge, TGNode, TemporalGraph


@pytest.fixture
def g():
    """Fresh in-memory graph per test."""
    return TemporalGraph(":memory:")


class TestNodeOperations:

    def test_add_node_returns_tgnode(self, g):
        n = g.add_node("episode", "battery_low")
        assert isinstance(n, TGNode)
        assert n.node_type == "episode"
        assert n.label == "battery_low"
        assert n.node_id  # non-empty

    def test_add_node_stores_properties(self, g):
        n = g.add_node("episode", "anomaly", {"severity": "HIGH", "value": 3.14})
        n2 = g.get_node(n.node_id)
        assert n2.properties["severity"] == "HIGH"
        assert abs(n2.properties["value"] - 3.14) < 1e-9

    def test_get_node_returns_none_for_missing(self, g):
        assert g.get_node("nonexistent_id") is None

    def test_get_or_create_returns_same_node(self, g):
        n1 = g.get_or_create_node("subsystem", "power")
        n2 = g.get_or_create_node("subsystem", "power")
        assert n1.node_id == n2.node_id

    def test_get_or_create_different_type_new_node(self, g):
        n1 = g.get_or_create_node("subsystem", "power")
        n2 = g.get_or_create_node("sensor", "power")  # different type, same label
        assert n1.node_id != n2.node_id

    def test_update_properties_merges(self, g):
        n = g.add_node("episode", "e1", {"a": 1, "b": 2})
        g.update_node_properties(n.node_id, {"b": 99, "c": 3})
        n2 = g.get_node(n.node_id)
        assert n2.properties["a"] == 1   # preserved
        assert n2.properties["b"] == 99  # updated
        assert n2.properties["c"] == 3   # added

    def test_invalidate_node_sets_timestamp(self, g):
        n = g.add_node("episode", "old_anomaly")
        g.invalidate_node(n.node_id)
        n2 = g.get_node(n.node_id)
        assert n2.invalidated_at is not None

    def test_active_only_excludes_invalidated(self, g):
        g.add_node("episode", "active_ep")
        n_old = g.add_node("episode", "old_ep")
        g.invalidate_node(n_old.node_id)
        active = g.query_nodes(node_type="episode", active_only=True)
        ids = [n.node_id for n in active]
        assert n_old.node_id not in ids

    def test_query_nodes_by_type(self, g):
        g.add_node("episode", "ep1")
        g.add_node("subsystem", "power")
        episodes = g.query_nodes(node_type="episode")
        assert all(n.node_type == "episode" for n in episodes)

    def test_query_nodes_label_contains(self, g):
        g.add_node("episode", "battery_low_soc")
        g.add_node("episode", "thermal_overheat")
        result = g.query_nodes(label_contains="battery")
        assert len(result) >= 1
        assert all("battery" in n.label for n in result)

    def test_query_nodes_since_filter(self, g):
        t_before = time.time() - 1.0
        g.add_node("episode", "recent", created_at=time.time())
        g.add_node("episode", "old", created_at=t_before - 100)
        recent = g.query_nodes(since=t_before)
        labels = [n.label for n in recent]
        assert "recent" in labels
        assert "old" not in labels


class TestEdgeOperations:

    def test_add_edge_returns_tgedge(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        edge = g.add_edge(n1, n2, "IN_SUBSYSTEM")
        assert isinstance(edge, TGEdge)
        assert edge.from_node == n1.node_id
        assert edge.to_node == n2.node_id
        assert edge.relation == "IN_SUBSYSTEM"

    def test_add_edge_with_string_ids(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        edge = g.add_edge(n1.node_id, n2.node_id, "IN_SUBSYSTEM")
        assert edge.from_node == n1.node_id

    def test_get_neighbors_outgoing(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        g.add_edge(n1, n2, "IN_SUBSYSTEM")
        nbrs = g.get_neighbors(n1, direction="out")
        nbr_ids = [n.node_id for n, _ in nbrs]
        assert n2.node_id in nbr_ids

    def test_get_neighbors_incoming(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        g.add_edge(n1, n2, "IN_SUBSYSTEM")
        nbrs = g.get_neighbors(n2, direction="in")
        nbr_ids = [n.node_id for n, _ in nbrs]
        assert n1.node_id in nbr_ids

    def test_get_neighbors_relation_filter(self, g):
        src = g.add_node("episode", "e1")
        target_a = g.add_node("subsystem", "power")
        target_b = g.add_node("decision", "load_shed")
        g.add_edge(src, target_a, "IN_SUBSYSTEM")
        g.add_edge(src, target_b, "RESOLVED_BY")

        in_sub = g.get_neighbors(src, relation="IN_SUBSYSTEM", direction="out")
        assert len(in_sub) == 1
        assert in_sub[0][0].node_id == target_a.node_id

    def test_close_edge_sets_valid_to(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        edge = g.add_edge(n1, n2, "IN_SUBSYSTEM")
        assert edge.valid_to is None
        g.close_edge(edge.edge_id)
        edge2 = g.get_edge(edge.edge_id)
        assert edge2.valid_to is not None

    def test_query_edges_by_relation(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("decision", "d1")
        n3 = g.add_node("subsystem", "power")
        g.add_edge(n1, n2, "RESOLVED_BY")
        g.add_edge(n1, n3, "IN_SUBSYSTEM")
        resolved = g.query_edges(relation="RESOLVED_BY")
        assert all(e.relation == "RESOLVED_BY" for e in resolved)

    def test_query_edges_from_node(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("episode", "e2")
        n3 = g.add_node("subsystem", "power")
        g.add_edge(n1, n3, "IN_SUBSYSTEM")
        g.add_edge(n2, n3, "IN_SUBSYSTEM")
        edges_from_n1 = g.query_edges(from_node=n1.node_id)
        assert all(e.from_node == n1.node_id for e in edges_from_n1)


class TestTemporalContext:

    def test_temporal_context_returns_connected_nodes(self, g):
        t_now = time.time()
        n_center = g.add_node("episode", "battery_low", created_at=t_now)
        n_power = g.add_node("subsystem", "power")
        g.add_edge(n_center, n_power, "IN_SUBSYSTEM", valid_from=t_now)

        ctx = g.get_temporal_context(n_center, window_s=300.0, at_time=t_now)
        ctx_ids = [n.node_id for n in ctx]
        assert n_power.node_id in ctx_ids

    def test_temporal_context_excludes_distant_events(self, g):
        t_now = time.time()
        n_center = g.add_node("episode", "e_now", created_at=t_now)
        n_old = g.add_node("episode", "e_old")
        # Edge from 1 hour ago
        g.add_edge(n_center, n_old, "SIMILAR_TO", valid_from=t_now - 3700)

        ctx = g.get_temporal_context(n_center, window_s=300.0, at_time=t_now)
        ctx_ids = [n.node_id for n in ctx]
        assert n_old.node_id not in ctx_ids

    def test_temporal_context_excludes_center_node(self, g):
        t_now = time.time()
        n = g.add_node("episode", "center", created_at=t_now)
        n2 = g.add_node("subsystem", "power")
        g.add_edge(n, n2, "IN_SUBSYSTEM", valid_from=t_now)

        ctx = g.get_temporal_context(n, window_s=300.0, at_time=t_now)
        assert n.node_id not in [x.node_id for x in ctx]


class TestShortestPath:

    def test_path_same_node(self, g):
        n = g.add_node("episode", "e1")
        path = g.shortest_path(n, n)
        assert path is not None
        assert len(path.nodes) == 1
        assert len(path.edges) == 0

    def test_path_direct_edge(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        g.add_edge(n1, n2, "IN_SUBSYSTEM")
        path = g.shortest_path(n1, n2)
        assert path is not None
        assert len(path.nodes) == 2
        assert len(path.edges) == 1

    def test_path_two_hops(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        n3 = g.add_node("decision", "load_shed")
        g.add_edge(n1, n2, "IN_SUBSYSTEM")
        g.add_edge(n2, n3, "TRIGGERED")
        path = g.shortest_path(n1, n3)
        assert path is not None
        assert len(path.nodes) == 3

    def test_path_no_connection_returns_none(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "unrelated")
        path = g.shortest_path(n1, n2)
        assert path is None

    def test_path_max_hops_limit(self, g):
        # Chain: n0 → n1 → n2 → n3 → n4; max_hops=2 shouldn't reach n4
        nodes = [g.add_node("episode", f"n{i}") for i in range(5)]
        for i in range(4):
            g.add_edge(nodes[i], nodes[i + 1], "PRECEDES")
        path = g.shortest_path(nodes[0], nodes[4], max_hops=2)
        assert path is None

    def test_path_weight_accumulates(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        g.add_edge(n1, n2, "IN_SUBSYSTEM", weight=3.5)
        path = g.shortest_path(n1, n2)
        assert abs(path.total_weight - 3.5) < 1e-9


class TestStats:

    def test_stats_initial_zero(self, g):
        s = g.stats()
        assert s["nodes_total"] == 0
        assert s["edges_total"] == 0

    def test_stats_after_adds(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        g.add_edge(n1, n2, "IN_SUBSYSTEM")
        s = g.stats()
        assert s["nodes_total"] == 2
        assert s["edges_total"] == 1
        assert s["nodes_active"] == 2
        assert s["edges_active"] == 1

    def test_stats_after_invalidate(self, g):
        n = g.add_node("episode", "e1")
        g.invalidate_node(n.node_id)
        s = g.stats()
        assert s["nodes_total"] == 1
        assert s["nodes_active"] == 0

    def test_stats_after_close_edge(self, g):
        n1 = g.add_node("episode", "e1")
        n2 = g.add_node("subsystem", "power")
        edge = g.add_edge(n1, n2, "IN_SUBSYSTEM")
        g.close_edge(edge.edge_id)
        s = g.stats()
        assert s["edges_active"] == 0
        assert s["edges_total"] == 1


class TestIsolation:

    def test_two_graphs_isolated(self):
        g1 = TemporalGraph(":memory:")
        g2 = TemporalGraph(":memory:")
        g1.add_node("episode", "e1")
        assert g2.stats()["nodes_total"] == 0
