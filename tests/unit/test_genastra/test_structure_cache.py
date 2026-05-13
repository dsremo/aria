"""Tests for LFU cache and structure cache."""

from __future__ import annotations

from aria.genastra.protein.structure_cache import LFUCache


class TestLFUCache:
    def test_basic_put_get(self) -> None:
        cache = LFUCache(capacity=3)
        cache.put("a", "value_a")
        assert cache.get("a") == "value_a"

    def test_miss_returns_none(self) -> None:
        cache = LFUCache(capacity=3)
        assert cache.get("missing") is None

    def test_evicts_least_frequent(self) -> None:
        cache = LFUCache(capacity=2)
        cache.put("a", "1")
        cache.put("b", "2")

        # Access 'a' more frequently
        cache.get("a")
        cache.get("a")

        # Insert 'c' — should evict 'b' (least frequent)
        cache.put("c", "3")

        assert cache.get("a") == "1"
        assert cache.get("b") is None
        assert cache.get("c") == "3"

    def test_evicts_oldest_on_tie(self) -> None:
        cache = LFUCache(capacity=2)
        cache.put("a", "1")
        cache.put("b", "2")

        # Both have frequency 1, 'a' is older → evict 'a'
        cache.put("c", "3")

        assert cache.get("a") is None
        assert cache.get("b") == "2"
        assert cache.get("c") == "3"

    def test_update_existing_key(self) -> None:
        cache = LFUCache(capacity=2)
        cache.put("a", "1")
        cache.put("a", "2")
        assert cache.get("a") == "2"
        assert len(cache) == 1

    def test_zero_capacity(self) -> None:
        cache = LFUCache(capacity=0)
        cache.put("a", "1")
        assert cache.get("a") is None
        assert len(cache) == 0

    def test_contains(self) -> None:
        cache = LFUCache(capacity=3)
        cache.put("a", "1")
        assert "a" in cache
        assert "b" not in cache

    def test_large_cache(self) -> None:
        cache = LFUCache(capacity=100)
        for i in range(200):
            cache.put(f"key_{i}", f"val_{i}")
        assert len(cache) == 100
