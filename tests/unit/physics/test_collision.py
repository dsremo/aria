"""Tests for collision detection — direct (O(N²)) and tree (spatial hash)."""
from __future__ import annotations

import time
import numpy as np
import pytest

from aria.physics.gravity.collision import (
    Particle,
    CollisionEvent,
    detect_collisions_direct,
    detect_collisions_tree,
    resolve_merge,
    resolve_bounce,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_particle(pos, vel=None, radius=1.0, mass=1.0):
    if vel is None:
        vel = np.zeros(3)
    p = Particle(
        pos=np.asarray(pos, dtype=float),
        vel=np.asarray(vel, dtype=float),
        mass=mass,
        radius=radius,
    )
    p.pos_prev = p.pos.copy()
    p.vel_prev = p.vel.copy()
    return p


# ── Tree method returns same results as direct ─────────────────────────────────

class TestTreeMatchesDirect:
    """detect_collisions_tree() must find exactly the same collisions as direct."""

    def _make_random_particles(self, n, rng, spread=1000.0, radius=5.0):
        ps = []
        for _ in range(n):
            pos = rng.uniform(-spread, spread, 3)
            vel = rng.uniform(-10, 10, 3)
            p = _make_particle(pos, vel, radius=radius)
            ps.append(p)
        return ps

    def test_no_collisions_empty(self):
        assert detect_collisions_tree([], 1.0) == []
        assert detect_collisions_tree([_make_particle([0, 0, 0])], 1.0) == []

    def test_single_obvious_collision(self):
        """Two particles on head-on collision course."""
        p1 = _make_particle([0, 0, 0], [1, 0, 0], radius=1.0)
        p2 = _make_particle([5, 0, 0], [-1, 0, 0], radius=1.0)
        evs_direct = detect_collisions_direct([p1, p2], 10.0)
        evs_tree = detect_collisions_tree([p1, p2], 10.0)
        assert len(evs_direct) == len(evs_tree) == 1
        assert evs_direct[0].i == evs_tree[0].i
        assert evs_direct[0].j == evs_tree[0].j

    def test_no_collision_diverging(self):
        p1 = _make_particle([0, 0, 0], [-5, 0, 0], radius=1.0)
        p2 = _make_particle([10, 0, 0], [5, 0, 0], radius=1.0)
        assert len(detect_collisions_tree([p1, p2], 10.0)) == 0

    def test_tree_matches_direct_small_random(self):
        rng = np.random.default_rng(42)
        for trial in range(5):
            ps = self._make_random_particles(30, rng, spread=200.0, radius=8.0)
            evs_d = detect_collisions_direct(ps, 1.0)
            evs_t = detect_collisions_tree(ps, 1.0)
            pairs_d = {(e.i, e.j) for e in evs_d}
            pairs_t = {(e.i, e.j) for e in evs_t}
            assert pairs_d == pairs_t, (
                f"Trial {trial}: direct={pairs_d} tree={pairs_t}"
            )

    def test_tree_matches_direct_dense_cluster(self):
        """Dense cluster — many collisions, stresses the grid bucketing."""
        rng = np.random.default_rng(7)
        ps = [_make_particle(rng.uniform(-20, 20, 3), rng.uniform(-5, 5, 3), radius=5.0)
              for _ in range(20)]
        pairs_d = {(e.i, e.j) for e in detect_collisions_direct(ps, 1.0)}
        pairs_t = {(e.i, e.j) for e in detect_collisions_tree(ps, 1.0)}
        assert pairs_d == pairs_t

    def test_all_zero_radius_and_speed(self):
        """Particles with zero radius/speed — no collisions expected."""
        ps = [_make_particle([i * 100.0, 0, 0], radius=0.0) for i in range(10)]
        assert detect_collisions_tree(ps, 1.0) == []


# ── Tree scales better than direct ────────────────────────────────────────────

class TestTreeScaling:
    def test_tree_faster_than_direct_for_sparse_N200(self):
        """For sparse debris (200 particles), tree should be ≥ 2× faster than direct."""
        rng = np.random.default_rng(99)
        ps = [_make_particle(rng.uniform(-1e6, 1e6, 3),
                             rng.uniform(-100, 100, 3), radius=5.0)
              for _ in range(200)]

        t0 = time.perf_counter()
        for _ in range(3):
            detect_collisions_direct(ps, 1.0)
        t_direct = (time.perf_counter() - t0) / 3

        t0 = time.perf_counter()
        for _ in range(3):
            detect_collisions_tree(ps, 1.0)
        t_tree = (time.perf_counter() - t0) / 3

        assert t_tree < t_direct, (
            f"Tree ({t_tree*1000:.1f}ms) should be faster than direct ({t_direct*1000:.1f}ms)"
        )


# ── Collision event correctness ────────────────────────────────────────────────

class TestCollisionEventProperties:
    def test_min_distance_non_negative(self):
        ps = [_make_particle([0, 0, 0], [1, 0, 0], radius=2.0),
              _make_particle([5, 0, 0], [-1, 0, 0], radius=2.0)]
        evs = detect_collisions_tree(ps, 10.0)
        assert len(evs) >= 1
        assert evs[0].min_distance >= 0.0

    def test_events_sorted_by_time(self):
        """Multiple collisions should be returned in chronological order."""
        p0 = _make_particle([0, 0, 0],  [1, 0, 0], radius=1.0)
        p1 = _make_particle([4, 0, 0],  [-1, 0, 0], radius=1.0)
        p2 = _make_particle([0, 0, 10], [0, 0, 1], radius=1.0)
        p3 = _make_particle([0, 0, 14], [0, 0, -1], radius=1.0)
        evs = detect_collisions_tree([p0, p1, p2, p3], 10.0)
        for k in range(len(evs) - 1):
            assert evs[k].t_collision <= evs[k + 1].t_collision

    def test_relative_speed_positive(self):
        ps = [_make_particle([0, 0, 0], [5, 0, 0], radius=1.0),
              _make_particle([8, 0, 0], [-5, 0, 0], radius=1.0)]
        evs = detect_collisions_tree(ps, 2.0)
        assert len(evs) >= 1
        assert evs[0].relative_speed > 0.0
