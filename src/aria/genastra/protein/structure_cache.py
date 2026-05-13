"""Structure cache: S3 storage + LFU local cache.

Panel 6 (IIT CS) critique: LRU is insufficient — use LFU because human
proteome proteins are queried 100x more than obscure metagenomics hits.

S3 key schema: structures/{tenant_id}/{sequence_hash}/{model_version}/structure.pdb
"""

from __future__ import annotations

from collections import OrderedDict

import structlog

from aria.genastra.core.constants import STRUCTURE_CACHE_MAX_LOCAL

logger = structlog.get_logger()


class LFUCache:
    """Least-Frequently-Used cache with O(1) get/put.

    Evicts the least frequently accessed entry when capacity is reached.
    On frequency tie, evicts the oldest entry (FIFO within frequency bucket).
    """

    def __init__(self, capacity: int = STRUCTURE_CACHE_MAX_LOCAL) -> None:
        self.capacity = capacity
        self._cache: dict[str, str] = {}  # key -> value
        self._freq: dict[str, int] = {}  # key -> frequency
        self._freq_buckets: dict[int, OrderedDict[str, None]] = {}  # freq -> ordered set of keys
        self._min_freq: int = 0

    def get(self, key: str) -> str | None:
        """Get a cached value, incrementing its frequency."""
        if key not in self._cache:
            return None

        self._increment_freq(key)
        return self._cache[key]

    def put(self, key: str, value: str) -> None:
        """Cache a value. Evicts LFU entry if at capacity."""
        if self.capacity <= 0:
            return

        if key in self._cache:
            self._cache[key] = value
            self._increment_freq(key)
            return

        if len(self._cache) >= self.capacity:
            self._evict()

        self._cache[key] = value
        self._freq[key] = 1
        self._min_freq = 1
        if 1 not in self._freq_buckets:
            self._freq_buckets[1] = OrderedDict()
        self._freq_buckets[1][key] = None

    def _increment_freq(self, key: str) -> None:
        freq = self._freq[key]
        self._freq[key] = freq + 1

        # Remove from current bucket
        del self._freq_buckets[freq][key]
        if not self._freq_buckets[freq]:
            del self._freq_buckets[freq]
            if self._min_freq == freq:
                self._min_freq = freq + 1

        # Add to new bucket
        new_freq = freq + 1
        if new_freq not in self._freq_buckets:
            self._freq_buckets[new_freq] = OrderedDict()
        self._freq_buckets[new_freq][key] = None

    def _evict(self) -> None:
        if self._min_freq not in self._freq_buckets:
            return
        bucket = self._freq_buckets[self._min_freq]
        evict_key, _ = bucket.popitem(last=False)  # FIFO within bucket
        if not bucket:
            del self._freq_buckets[self._min_freq]
        del self._cache[evict_key]
        del self._freq[evict_key]

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        return key in self._cache


class StructureCache:
    """Two-tier structure cache: LFU in-memory + S3 persistent storage."""

    def __init__(
        self,
        s3_bucket: str,
        s3_client: object | None = None,
        local_capacity: int = STRUCTURE_CACHE_MAX_LOCAL,
    ) -> None:
        self.s3_bucket = s3_bucket
        self._s3 = s3_client
        self._local = LFUCache(capacity=local_capacity)

    def _s3_key(self, tenant_id: str, sequence_hash: str, model_version: str) -> str:
        return f"structures/{tenant_id}/{sequence_hash}/{model_version}/structure.pdb"

    def _cache_key(self, tenant_id: str, sequence_hash: str, model_version: str) -> str:
        return f"{tenant_id}:{sequence_hash}:{model_version}"

    async def get(self, tenant_id: str, sequence_hash: str, model_version: str) -> str | None:
        """Look up a structure. Checks local cache first, then S3."""
        cache_key = self._cache_key(tenant_id, sequence_hash, model_version)

        # Check local LFU cache
        local = self._local.get(cache_key)
        if local is not None:
            logger.debug("structure_cache_hit", layer="local", hash=sequence_hash[:12])
            return local

        # Check S3
        if self._s3 is not None:
            s3_key = self._s3_key(tenant_id, sequence_hash, model_version)
            try:
                response = self._s3.get_object(Bucket=self.s3_bucket, Key=s3_key)
                pdb_string = response["Body"].read().decode("utf-8")
                # Promote to local cache
                self._local.put(cache_key, pdb_string)
                logger.debug("structure_cache_hit", layer="s3", hash=sequence_hash[:12])
                return pdb_string
            except Exception:  # noqa: S110, BLE001
                pass

        return None

    async def put(
        self,
        tenant_id: str,
        sequence_hash: str,
        model_version: str,
        pdb_string: str,
    ) -> str | None:
        """Store a structure in both local cache and S3.

        Returns the S3 key if stored, None if S3 is unavailable.
        """
        cache_key = self._cache_key(tenant_id, sequence_hash, model_version)
        self._local.put(cache_key, pdb_string)

        s3_key: str | None = None
        if self._s3 is not None:
            s3_key = self._s3_key(tenant_id, sequence_hash, model_version)
            try:
                self._s3.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=pdb_string.encode("utf-8"),
                    ContentType="chemical/x-pdb",
                )
                logger.debug("structure_cache_stored_s3", hash=sequence_hash[:12])
            except Exception:
                logger.warning("structure_cache_s3_failed", hash=sequence_hash[:12])
                s3_key = None

        return s3_key

    def generate_presigned_url(self, s3_key: str, expiry_seconds: int = 3600) -> str | None:
        """Generate a pre-signed URL for downloading a structure from S3."""
        if self._s3 is None:
            return None
        try:
            return self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.s3_bucket, "Key": s3_key},
                ExpiresIn=expiry_seconds,
            )
        except Exception:
            return None
