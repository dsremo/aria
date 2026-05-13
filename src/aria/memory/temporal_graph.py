"""Temporal knowledge graph for ARIA's long-term mission memory.

A knowledge graph answers questions that flat episode lists cannot:
  - "What subsystem anomalies occurred near this battery failure?"
  - "Which decision patterns are connected to the current sensor readings?"
  - "What was the causal chain leading to the CO2 scrubber alarm?"

The temporal dimension records when each relationship was valid, so the
graph accurately captures changing mission state across a multi-year cruise.

Architecture
------------
Storage: SQLite (zero-dep, single-file, crash-safe).
Nodes: entities — subsystems, sensors, episodes, decisions, crew actions.
Edges: directed, time-stamped relationships between nodes.
       Each edge has valid_from/valid_to (None = currently valid).

Schema::

    tg_nodes  (node_id PK, node_type, label, properties JSON,
               created_at REAL, invalidated_at REAL NULL)
    tg_edges  (edge_id PK, from_node → tg_nodes, to_node → tg_nodes,
               relation TEXT, weight REAL, valid_from REAL,
               valid_to REAL NULL, properties JSON)

Key relations (not enumerated; free-form text for extensibility):
    CAUSED_BY        anomaly A triggered by event B
    RESOLVED_BY      anomaly A resolved by decision D
    DETECTED_BY      event detected by sensor S
    IN_SUBSYSTEM     event belongs to subsystem S
    CORRELATES_WITH  sensor A and sensor B co-vary over window W
    PRECEDES         event A happened before and is linked to event B
    SIMILAR_TO       this episode resembles historical episode H (by type/context)
    AFFECTS          decision D affects subsystem S

Usage::

    from aria.memory.temporal_graph import TemporalGraph
    g = TemporalGraph("data/mission_graph.db")

    # Record an anomaly
    anom = g.add_node("episode", "battery_soc_low", {"severity": "HIGH"})
    power = g.get_or_create_node("subsystem", "power")
    g.add_edge(anom, power, "IN_SUBSYSTEM")

    # Record the decision that resolved it
    dec = g.add_node("decision", "load_shed_tier1", {"action": "load_shedding"})
    g.add_edge(dec, anom, "RESOLVED_BY")

    # Query: what happened to the power subsystem in the last hour?
    nodes = g.get_temporal_context(power, window_s=3600)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class TGNode:
    """A node in the temporal knowledge graph."""
    node_id: str
    node_type: str        # "episode", "subsystem", "sensor", "decision", "fact"
    label: str
    properties: dict[str, Any]
    created_at: float     # Unix timestamp
    invalidated_at: Optional[float] = None   # None = still valid


@dataclass
class TGEdge:
    """A directed, time-stamped edge between two graph nodes."""
    edge_id: str
    from_node: str
    to_node: str
    relation: str         # free-form relation type (CAUSED_BY, RESOLVED_BY, ...)
    weight: float
    valid_from: float     # Unix timestamp
    valid_to: Optional[float] = None  # None = currently valid
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphPath:
    """A path through the graph: sequence of (node, edge) pairs."""
    nodes: list[TGNode]
    edges: list[TGEdge]
    total_weight: float


# ── SQLite schema ─────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS tg_nodes (
    node_id         TEXT PRIMARY KEY,
    node_type       TEXT NOT NULL,
    label           TEXT NOT NULL,
    properties      TEXT NOT NULL DEFAULT '{}',
    created_at      REAL NOT NULL,
    invalidated_at  REAL
);

CREATE TABLE IF NOT EXISTS tg_edges (
    edge_id     TEXT PRIMARY KEY,
    from_node   TEXT NOT NULL,
    to_node     TEXT NOT NULL,
    relation    TEXT NOT NULL,
    weight      REAL NOT NULL DEFAULT 1.0,
    valid_from  REAL NOT NULL,
    valid_to    REAL,
    properties  TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tg_edges_from    ON tg_edges(from_node);
CREATE INDEX IF NOT EXISTS idx_tg_edges_to      ON tg_edges(to_node);
CREATE INDEX IF NOT EXISTS idx_tg_edges_time    ON tg_edges(valid_from);
CREATE INDEX IF NOT EXISTS idx_tg_nodes_type    ON tg_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_tg_nodes_label   ON tg_nodes(label);
"""


# ── Main class ────────────────────────────────────────────────────────────────

class TemporalGraph:
    """SQLite-backed temporal knowledge graph for ARIA mission memory.

    Thread-safe: a reentrant lock serialises all writes; reads use
    separate connections via check_same_thread=False.

    Args:
        db_path: Path to the SQLite file. Use ":memory:" for testing.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_DDL)
            self._conn.commit()

    # ── Node operations ───────────────────────────────────────────────────────

    def add_node(
        self,
        node_type: str,
        label: str,
        properties: Optional[dict[str, Any]] = None,
        node_id: Optional[str] = None,
        created_at: Optional[float] = None,
    ) -> TGNode:
        """Insert a new node and return it.

        Args:
            node_type: Category ("episode", "subsystem", "sensor", etc.).
            label: Human-readable identifier (not unique).
            properties: Arbitrary JSON-serialisable metadata.
            node_id: Override the auto-generated UUID.
            created_at: Override the current timestamp.

        Returns:
            TGNode with the persisted node_id and created_at.
        """
        nid = node_id or uuid.uuid4().hex[:16]
        ts = created_at or time.time()
        props = json.dumps(properties or {})
        with self._lock:
            self._conn.execute(
                "INSERT INTO tg_nodes (node_id, node_type, label, properties, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (nid, node_type, label, props, ts),
            )
            self._conn.commit()
        return TGNode(
            node_id=nid,
            node_type=node_type,
            label=label,
            properties=properties or {},
            created_at=ts,
        )

    def get_or_create_node(
        self,
        node_type: str,
        label: str,
        properties: Optional[dict[str, Any]] = None,
    ) -> TGNode:
        """Return the existing node with (type, label) or create it.

        Matches on (node_type, label) — the first match wins.  Use this
        for stable entities like subsystems and sensors whose identity is
        fixed across sessions.
        """
        existing = self._find_node_by_type_label(node_type, label)
        if existing:
            return existing
        return self.add_node(node_type, label, properties)

    def get_node(self, node_id: str) -> Optional[TGNode]:
        """Fetch a node by ID, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM tg_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        return self._row_to_node(row) if row else None

    def invalidate_node(self, node_id: str, at: Optional[float] = None) -> None:
        """Soft-delete a node by setting its invalidated_at timestamp."""
        ts = at or time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE tg_nodes SET invalidated_at = ? WHERE node_id = ?",
                (ts, node_id),
            )
            self._conn.commit()

    def update_node_properties(
        self, node_id: str, properties: dict[str, Any]
    ) -> None:
        """Merge new properties into a node (shallow update)."""
        node = self.get_node(node_id)
        if node is None:
            raise KeyError(f"Node {node_id!r} not found")
        merged = {**node.properties, **properties}
        with self._lock:
            self._conn.execute(
                "UPDATE tg_nodes SET properties = ? WHERE node_id = ?",
                (json.dumps(merged), node_id),
            )
            self._conn.commit()

    # ── Edge operations ───────────────────────────────────────────────────────

    def add_edge(
        self,
        from_node: str | TGNode,
        to_node: str | TGNode,
        relation: str,
        weight: float = 1.0,
        properties: Optional[dict[str, Any]] = None,
        valid_from: Optional[float] = None,
        valid_to: Optional[float] = None,
    ) -> TGEdge:
        """Insert a directed edge between two nodes.

        Args:
            from_node: Source node ID or TGNode.
            to_node: Target node ID or TGNode.
            relation: Relationship label (CAUSED_BY, RESOLVED_BY, ...).
            weight: Edge weight (default 1.0; higher = stronger relation).
            properties: Additional metadata dict.
            valid_from: Start of validity window (default now).
            valid_to: End of validity window (default None = open).

        Returns:
            TGEdge with the persisted edge_id.
        """
        fid = from_node.node_id if isinstance(from_node, TGNode) else from_node
        tid = to_node.node_id if isinstance(to_node, TGNode) else to_node
        eid = uuid.uuid4().hex[:16]
        ts = valid_from or time.time()
        props = json.dumps(properties or {})
        with self._lock:
            self._conn.execute(
                "INSERT INTO tg_edges"
                " (edge_id, from_node, to_node, relation, weight,"
                "  valid_from, valid_to, properties)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, fid, tid, relation, weight, ts, valid_to, props),
            )
            self._conn.commit()
        return TGEdge(
            edge_id=eid,
            from_node=fid,
            to_node=tid,
            relation=relation,
            weight=weight,
            valid_from=ts,
            valid_to=valid_to,
            properties=properties or {},
        )

    def close_edge(self, edge_id: str, at: Optional[float] = None) -> None:
        """Set the valid_to timestamp on an edge (mark as no longer active)."""
        ts = at or time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE tg_edges SET valid_to = ? WHERE edge_id = ?",
                (ts, edge_id),
            )
            self._conn.commit()

    def get_edge(self, edge_id: str) -> Optional[TGEdge]:
        """Fetch an edge by ID, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM tg_edges WHERE edge_id = ?", (edge_id,)
        ).fetchone()
        return self._row_to_edge(row) if row else None

    # ── Graph queries ─────────────────────────────────────────────────────────

    def get_neighbors(
        self,
        node: str | TGNode,
        relation: Optional[str] = None,
        direction: str = "out",
        at_time: Optional[float] = None,
        limit: int = 50,
    ) -> list[tuple[TGNode, TGEdge]]:
        """Return adjacent nodes and the connecting edge.

        Args:
            node: Source node ID or TGNode.
            relation: Filter by edge relation type (None = all).
            direction: "out" (from_node = node), "in" (to_node = node),
                       or "both".
            at_time: Return only edges valid at this Unix timestamp
                     (None = all edges including historical).
            limit: Maximum results.

        Returns:
            List of (TGNode, TGEdge) pairs.
        """
        nid = node.node_id if isinstance(node, TGNode) else node
        params: list[Any] = []
        clauses: list[str] = []

        # Direction filter
        if direction == "out":
            clauses.append("e.from_node = ?")
            params.append(nid)
            join_col = "e.to_node"
        elif direction == "in":
            clauses.append("e.to_node = ?")
            params.append(nid)
            join_col = "e.from_node"
        else:  # both
            clauses.append("(e.from_node = ? OR e.to_node = ?)")
            params.extend([nid, nid])
            join_col = "CASE WHEN e.from_node = ? THEN e.to_node ELSE e.from_node END"
            params.append(nid)

        if relation:
            clauses.append("e.relation = ?")
            params.append(relation)
        if at_time is not None:
            clauses.append("e.valid_from <= ?")
            params.append(at_time)
            clauses.append("(e.valid_to IS NULL OR e.valid_to >= ?)")
            params.append(at_time)

        where = " AND ".join(clauses)

        # nosec B608 — column names + join expression are literal strings
        # built in this function from a fixed allow-list; values bind via ?
        # Build query differently for "both" direction due to CASE expression
        if direction == "both":
            sql = (
                "SELECT n.*, e.edge_id, e.from_node, e.to_node, e.relation, "
                "e.weight, e.valid_from, e.valid_to, e.properties AS eprops "
                "FROM tg_edges e "
                f"JOIN tg_nodes n ON n.node_id = {join_col} "
                f"WHERE {where} AND n.invalidated_at IS NULL LIMIT ?"  # nosec B608
            )
        else:
            sql = (
                "SELECT n.*, e.edge_id, e.from_node, e.to_node, e.relation, "
                "e.weight, e.valid_from, e.valid_to, e.properties AS eprops "
                "FROM tg_edges e "
                f"JOIN tg_nodes n ON n.node_id = {join_col} "
                f"WHERE {where} AND n.invalidated_at IS NULL LIMIT ?"  # nosec B608
            )
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()

        result = []
        for row in rows:
            node_obj = TGNode(
                node_id=row["node_id"],
                node_type=row["node_type"],
                label=row["label"],
                properties=json.loads(row["properties"]),
                created_at=row["created_at"],
                invalidated_at=row["invalidated_at"],
            )
            edge_obj = TGEdge(
                edge_id=row["edge_id"],
                from_node=row["from_node"],
                to_node=row["to_node"],
                relation=row["relation"],
                weight=row["weight"],
                valid_from=row["valid_from"],
                valid_to=row["valid_to"],
                properties=json.loads(row["eprops"]),
            )
            result.append((node_obj, edge_obj))
        return result

    def get_temporal_context(
        self,
        node: str | TGNode,
        window_s: float = 300.0,
        at_time: Optional[float] = None,
    ) -> list[TGNode]:
        """Return all nodes connected within a time window.

        Finds all nodes reachable via edges whose valid_from falls within
        [t - window_s, t + window_s] where t = at_time (default now).
        Returns the connected nodes, not the edges.

        Args:
            node: Anchor node.
            window_s: Half-width of the time window [seconds].
            at_time: Center time (default now).

        Returns:
            List of TGNode objects within the temporal window.
        """
        nid = node.node_id if isinstance(node, TGNode) else node
        t = at_time or time.time()
        t_lo, t_hi = t - window_s, t + window_s

        rows = self._conn.execute(
            """
            SELECT DISTINCT n.*
            FROM tg_edges e
            JOIN tg_nodes n ON (n.node_id = e.from_node OR n.node_id = e.to_node)
            WHERE (e.from_node = ? OR e.to_node = ?)
              AND e.valid_from BETWEEN ? AND ?
              AND n.node_id != ?
              AND n.invalidated_at IS NULL
            """,
            (nid, nid, t_lo, t_hi, nid),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def shortest_path(
        self,
        from_node: str | TGNode,
        to_node: str | TGNode,
        max_hops: int = 5,
    ) -> Optional[GraphPath]:
        """BFS shortest path between two nodes in the active (valid) graph.

        Only traverses edges with valid_to IS NULL (currently active).
        Returns None if no path exists within max_hops.
        """
        fid = from_node.node_id if isinstance(from_node, TGNode) else from_node
        tid = to_node.node_id if isinstance(to_node, TGNode) else to_node

        if fid == tid:
            node = self.get_node(fid)
            return GraphPath(nodes=[node], edges=[], total_weight=0.0) if node else None

        # BFS over active edges
        visited: set[str] = {fid}
        queue: list[tuple[str, list[TGNode], list[TGEdge], float]] = []
        start = self.get_node(fid)
        if not start:
            return None
        queue.append((fid, [start], [], 0.0))

        while queue:
            cur_id, path_nodes, path_edges, path_weight = queue.pop(0)
            if len(path_edges) >= max_hops:
                continue

            neighbors = self.get_neighbors(cur_id, direction="both", limit=100)
            for nbr_node, edge in neighbors:
                if edge.valid_to is not None:
                    continue  # skip historical edges
                if nbr_node.node_id in visited:
                    continue
                new_nodes = path_nodes + [nbr_node]
                new_edges = path_edges + [edge]
                new_weight = path_weight + edge.weight

                if nbr_node.node_id == tid:
                    return GraphPath(
                        nodes=new_nodes,
                        edges=new_edges,
                        total_weight=new_weight,
                    )
                visited.add(nbr_node.node_id)
                queue.append((nbr_node.node_id, new_nodes, new_edges, new_weight))

        return None

    def query_nodes(
        self,
        node_type: Optional[str] = None,
        label_contains: Optional[str] = None,
        since: Optional[float] = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[TGNode]:
        """Flexible node query by type, label, and time filters.

        Args:
            node_type: Filter to this node type.
            label_contains: Case-insensitive substring match on label.
            since: Return nodes created after this Unix timestamp.
            active_only: Exclude invalidated nodes (default True).
            limit: Maximum results.

        Returns:
            Matching TGNode objects ordered by created_at descending.
        """
        clauses, params = [], []
        if node_type:
            clauses.append("node_type = ?")
            params.append(node_type)
        if label_contains:
            clauses.append("LOWER(label) LIKE ?")
            params.append(f"%{label_contains.lower()}%")
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since)
        if active_only:
            clauses.append("invalidated_at IS NULL")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM tg_nodes {where} ORDER BY created_at DESC LIMIT ?",  # nosec B608 (column names are literal; values bound via ?)
            params,
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def query_edges(
        self,
        relation: Optional[str] = None,
        from_node: Optional[str] = None,
        to_node: Optional[str] = None,
        active_only: bool = False,
        limit: int = 100,
    ) -> list[TGEdge]:
        """Query edges by relation, endpoints, or active status."""
        clauses, params = [], []
        if relation:
            clauses.append("relation = ?")
            params.append(relation)
        if from_node:
            clauses.append("from_node = ?")
            params.append(from_node)
        if to_node:
            clauses.append("to_node = ?")
            params.append(to_node)
        if active_only:
            clauses.append("valid_to IS NULL")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM tg_edges {where} ORDER BY valid_from DESC LIMIT ?",  # nosec B608 (column names are literal; values bound via ?)
            params,
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    # ── Statistics ────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Return node and edge counts."""
        n_total = self._conn.execute("SELECT COUNT(*) FROM tg_nodes").fetchone()[0]
        n_active = self._conn.execute(
            "SELECT COUNT(*) FROM tg_nodes WHERE invalidated_at IS NULL"
        ).fetchone()[0]
        e_total = self._conn.execute("SELECT COUNT(*) FROM tg_edges").fetchone()[0]
        e_active = self._conn.execute(
            "SELECT COUNT(*) FROM tg_edges WHERE valid_to IS NULL"
        ).fetchone()[0]
        return {
            "nodes_total": n_total,
            "nodes_active": n_active,
            "edges_total": e_total,
            "edges_active": e_active,
        }

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _find_node_by_type_label(
        self, node_type: str, label: str
    ) -> Optional[TGNode]:
        row = self._conn.execute(
            "SELECT * FROM tg_nodes WHERE node_type = ? AND label = ?"
            " AND invalidated_at IS NULL LIMIT 1",
            (node_type, label),
        ).fetchone()
        return self._row_to_node(row) if row else None

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> TGNode:
        return TGNode(
            node_id=row["node_id"],
            node_type=row["node_type"],
            label=row["label"],
            properties=json.loads(row["properties"]),
            created_at=row["created_at"],
            invalidated_at=row["invalidated_at"],
        )

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> TGEdge:
        return TGEdge(
            edge_id=row["edge_id"],
            from_node=row["from_node"],
            to_node=row["to_node"],
            relation=row["relation"],
            weight=row["weight"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            properties=json.loads(row["properties"]),
        )
