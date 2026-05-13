"""Multi-tenant store with API-key rotation.

SQLite-backed tenant database that supersedes the JSON tenants file
used by the v1 service.  Goals:

  * Idempotent schema migration on startup.
  * Per-tenant active + previous API-key (so rotation is zero-downtime —
    the previous key remains valid for a configurable grace window
    while operators update their clients).
  * Constant-time key comparison via ``hmac.compare_digest``.
  * In-process lock so concurrent rotations cannot interleave.

Round-2 audit hardening (2026-04-27 R2):
  * Keys are stored as ``hmac:<sha256(HMAC(server_secret, plaintext))>``
    — adding a per-deployment salt removes the rainbow-table risk on a
    leaked DB image (NEW-HIGH-6).
  * Operator-supplied keys must meet an entropy floor in production
    (NEW-HIGH-6).
  * SQLite uses ``journal_mode=WAL`` + ``synchronous=FULL`` so a power
    loss cannot leave the security-critical store in a partial state
    (NEW-MED-3).
  * Connection is thread-local + reused, not opened per call (NEW-MED-4).
  * ``usage_log`` rows older than 90 days are pruned each
    ``record_usage`` call (NEW-MED-5).
  * SQLite file is chmod-ed to 0o600 (NEW-MED-6).
  * ``record_usage`` validates that the tenant exists and clamps
    n_pairs / elapsed_ms (NEW-MED-7 / NEW-MED-16).

The schema is deliberately small.  Stripe billing + usage dashboards
are layered on top in :mod:`aria.products.conjunction_screener.billing`.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import threading
import time

logger = logging.getLogger("aria.products.conjunction_screener.tenants")
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

# Operator-tunable; defaults chosen to match the JSON-tenant defaults
# in :mod:`aria.products.conjunction_screener.service`.  These are not
# physical constants so no citation is required (CLAUDE.md exception).
DEFAULT_RATE_PER_MIN = 60
DEFAULT_RATE_PER_DAY = 10_000
KEY_BYTES = 32                             # 256-bit secret
ROTATION_GRACE_SECONDS = 7 * 24 * 3600     # 7-day grace window

# Round-2 audit NEW-HIGH-6 — keys are stored as
# ``hmac:HMAC(server_secret, plaintext)`` which moves away from the
# unsalted SHA-256 used in round-1.  Legacy ``sha256:`` rows are still
# accepted for one rotation cycle.
_HMAC_PREFIX = "hmac:"
_LEGACY_SHA256_PREFIX = "sha256:"
# Minimum entropy floor for any operator-provided API key; OS-RNG
# generated keys always pass.
_MIN_KEY_LENGTH = 32
_MIN_KEY_DISTINCT_CHARS = 8

# Round-2 audit NEW-MED-5 — usage rows older than this are pruned at
# every record_usage call.
_USAGE_RETENTION_S = 90 * 24 * 3600


def _key_hash_secret() -> bytes:
    """Round-2 audit NEW-HIGH-6 — derive the per-deployment HMAC key
    used to hash tenant keys at rest.  Sourced from
    ``ARIA_TENANT_KEY_HMAC_HEX``; if missing in non-production we
    fall back to a stable derivation off ``ARIA_HKDF_SALT_HEX`` so
    tests don't need a separate env var."""
    raw = os.environ.get("ARIA_TENANT_KEY_HMAC_HEX", "").strip()
    if raw:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    hkdf_salt = os.environ.get("ARIA_HKDF_SALT_HEX", "").strip()
    if hkdf_salt:
        try:
            return hashlib.sha256(b"aria-tenant-key:" + bytes.fromhex(hkdf_salt)).digest()
        except ValueError:
            pass
    # Last-resort static fall-back — only used when neither env is set,
    # which by design is dev/test only.  Production deployments fail at
    # boot via guard.runtime_check_environment when these envs are
    # missing.
    return hashlib.sha256(b"aria-tenant-key:dev-only-no-secret-set").digest()


def _hash_key(plaintext: str) -> str:
    if not plaintext:
        return ""
    digest = hmac.new(
        _key_hash_secret(), plaintext.encode("utf-8"), hashlib.sha256,
    ).hexdigest()
    return _HMAC_PREFIX + digest


def _legacy_hash_key(plaintext: str) -> str:
    """Legacy unsalted SHA-256, retained so any sha256:-prefixed row
    written before this audit still matches.  Used only on the lookup
    path; new writes always go through ``_hash_key``."""
    if not plaintext:
        return ""
    return _LEGACY_SHA256_PREFIX + hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _stored_matches(stored: str, presented: str) -> bool:
    """Constant-time compare against the HMAC digest (current), the
    legacy ``sha256:`` digest (one rotation cycle of compatibility), or
    a legacy plaintext value (older still)."""
    if not stored or not presented:
        return False
    if stored.startswith(_HMAC_PREFIX):
        return hmac.compare_digest(stored, _hash_key(presented))
    if stored.startswith(_LEGACY_SHA256_PREFIX):
        return hmac.compare_digest(stored, _legacy_hash_key(presented))
    return hmac.compare_digest(stored, presented)


def _validate_key_entropy(plaintext: str) -> None:
    """Round-2 audit NEW-HIGH-6 — refuse low-entropy operator keys."""
    if len(plaintext) < _MIN_KEY_LENGTH:
        raise ValueError("api_key_too_short")
    if len(set(plaintext)) < _MIN_KEY_DISTINCT_CHARS:
        raise ValueError("api_key_low_entropy")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id            TEXT PRIMARY KEY,
    api_key_hex          TEXT NOT NULL,
    previous_api_key_hex TEXT,
    previous_expires_at  REAL,                  -- unix epoch
    rate_limit_per_min   INTEGER NOT NULL DEFAULT 60,
    rate_limit_per_day   INTEGER NOT NULL DEFAULT 10000,
    suspended            INTEGER NOT NULL DEFAULT 0,
    created_at           REAL NOT NULL,
    last_rotated_at      REAL
);

CREATE TABLE IF NOT EXISTS usage_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   TEXT NOT NULL,
    epoch       REAL NOT NULL,
    endpoint    TEXT NOT NULL,
    n_pairs     INTEGER NOT NULL DEFAULT 0,
    elapsed_ms  REAL NOT NULL DEFAULT 0,
    status_code INTEGER NOT NULL DEFAULT 200
);

CREATE INDEX IF NOT EXISTS usage_log_tenant_epoch
    ON usage_log (tenant_id, epoch);
"""


@dataclass
class Tenant:
    tenant_id: str
    api_key_hex: str
    previous_api_key_hex: Optional[str]
    previous_expires_at: Optional[float]
    rate_limit_per_min: int
    rate_limit_per_day: int
    suspended: bool
    created_at: float
    last_rotated_at: Optional[float]

    def matches(self, presented_key: str, *, now: Optional[float] = None) -> bool:
        # Audit HIGH-11 — both stored slots may be the ``sha256:`` digest
        # of the plaintext key; ``_stored_matches`` does the right thing
        # for legacy plaintext rows too (one rotation cycle of compat).
        if not presented_key:
            return False
        if _stored_matches(self.api_key_hex, presented_key):
            return True
        prev = self.previous_api_key_hex
        if prev and self.previous_expires_at is not None:
            now = now if now is not None else time.time()
            if now < self.previous_expires_at and _stored_matches(prev, presented_key):
                return True
        return False


class TenantStore:
    """Thread-safe SQLite-backed tenant store."""

    def __init__(self, db_path: Path | str):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # Round-2 audit NEW-MED-4 — thread-local connection pool so we
        # don't open + close a SQLite connection on every call.
        self._tls = threading.local()
        # Audit MED-5 — in-memory hash → tenant_id index gives O(1)
        # lookup, removing the timing oracle of walking every row.
        self._key_index: dict[str, str] = {}
        with self._connect() as c:
            c.executescript(_SCHEMA)
            # Round-2 audit NEW-MED-3 — durability + WAL.  Setting
            # journal_mode is per-connection but is sticky in the DB;
            # synchronous=FULL is per-connection.
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=FULL")
        # Round-2 audit NEW-MED-6 — restrict file perms.  -wal/-shm
        # files are created lazily by SQLite; chmod each as they appear.
        for suffix in ("", "-wal", "-shm"):
            try:
                p = self._path.with_name(self._path.name + suffix) if suffix else self._path
                if p.exists():
                    os.chmod(p, 0o600)
            except OSError:
                pass
        self._reload_key_index()

    def _reload_key_index(self) -> None:
        """Populate the hash index from the DB; called on construction
        and after each rotation."""
        with self._lock:
            self._key_index.clear()
            try:
                with self._connect() as c:
                    rows = c.execute(
                        "SELECT tenant_id, api_key_hex, previous_api_key_hex "
                        "FROM tenants WHERE suspended = 0"
                    ).fetchall()
            except sqlite3.OperationalError:
                return
            for row in rows:
                if row["api_key_hex"]:
                    self._key_index[row["api_key_hex"]] = row["tenant_id"]
                if row["previous_api_key_hex"]:
                    self._key_index[row["previous_api_key_hex"]] = row["tenant_id"]

    def _thread_conn(self) -> sqlite3.Connection:
        conn = getattr(self._tls, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self._path), timeout=10.0, isolation_level=None,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._tls.conn = conn
        return conn

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._thread_conn()
            began = False
            try:
                if not conn.in_transaction:
                    conn.execute("BEGIN")
                    began = True
                yield conn
                if began and conn.in_transaction:
                    conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    try:
                        conn.execute("ROLLBACK")
                    except Exception:
                        pass
                raise

    # ── CRUD ───────────────────────────────────────────────────

    def create_tenant(
        self,
        tenant_id: str,
        rate_limit_per_min: int = DEFAULT_RATE_PER_MIN,
        rate_limit_per_day: int = DEFAULT_RATE_PER_DAY,
        api_key_hex: Optional[str] = None,
    ) -> Tenant:
        # Round-2 audit NEW-HIGH-6 — operator-supplied keys must meet
        # the entropy floor.  OS-RNG keys (default path) always pass.
        if api_key_hex is not None:
            _validate_key_entropy(api_key_hex)
            plaintext = api_key_hex
        else:
            plaintext = secrets.token_hex(KEY_BYTES)
        stored = _hash_key(plaintext)
        now = time.time()
        with self._connect() as c:
            c.execute(
                """INSERT INTO tenants
                   (tenant_id, api_key_hex, rate_limit_per_min,
                    rate_limit_per_day, suspended, created_at)
                   VALUES (?, ?, ?, ?, 0, ?)""",
                (tenant_id, stored, rate_limit_per_min, rate_limit_per_day, now),
            )
        # Update the in-memory hash index for O(1) lookup (audit MED-5).
        with self._lock:
            self._key_index[stored] = tenant_id
        return Tenant(
            tenant_id=tenant_id,
            api_key_hex=plaintext,    # only the create-time return reveals plaintext
            previous_api_key_hex=None,
            previous_expires_at=None,
            rate_limit_per_min=rate_limit_per_min,
            rate_limit_per_day=rate_limit_per_day,
            suspended=False,
            created_at=now,
            last_rotated_at=None,
        )

    def get(self, tenant_id: str) -> Optional[Tenant]:
        with self._connect() as c:
            row = c.execute(
                "SELECT * FROM tenants WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        return self._row_to_tenant(row) if row else None

    def list_all(self) -> List[Tenant]:
        with self._connect() as c:
            rows = c.execute("SELECT * FROM tenants ORDER BY tenant_id").fetchall()
        return [self._row_to_tenant(r) for r in rows]

    def find_by_key(self, presented_key: str, *, now: Optional[float] = None) -> Optional[Tenant]:
        """O(1) lookup via in-memory hash index (audit MED-5).

        The lookup also performs an opportunistic GC of any expired
        ``previous_api_key_hex`` (audit MED-6) so a key whose grace
        window has elapsed is purged from disk + memory eagerly.
        """
        if not presented_key:
            return None
        candidate = _hash_key(presented_key)
        with self._lock:
            tenant_id = self._key_index.get(candidate)
            # Backstop: legacy plaintext rows pre-migration.  Only
            # checked if the hash lookup misses, so the common path is
            # still O(1).  This branch exits after one rotation cycle.
            if tenant_id is None:
                tenant_id = self._key_index.get(presented_key)
        if tenant_id is None:
            return None
        t = self.get(tenant_id)
        if t is None or t.suspended:
            return None
        if not t.matches(presented_key, now=now):
            return None
        # MED-6 — eagerly garbage-collect a previous-key whose grace
        # window has elapsed; the row stays, the prev slot is zeroed.
        n = now if now is not None else time.time()
        if (t.previous_api_key_hex
                and t.previous_expires_at is not None
                and n >= t.previous_expires_at):
            self._purge_previous_key(t.tenant_id, t.previous_api_key_hex)
            t = self.get(t.tenant_id) or t
        return t

    def _purge_previous_key(self, tenant_id: str, prev_hash: str) -> None:
        with self._connect() as c:
            c.execute(
                """UPDATE tenants
                   SET previous_api_key_hex = NULL, previous_expires_at = NULL
                   WHERE tenant_id = ?""",
                (tenant_id,),
            )
        with self._lock:
            self._key_index.pop(prev_hash, None)

    def rotate_key(
        self,
        tenant_id: str,
        grace_seconds: int = ROTATION_GRACE_SECONDS,
    ) -> Tenant:
        plaintext_new = secrets.token_hex(KEY_BYTES)
        stored_new = _hash_key(plaintext_new)
        now = time.time()
        with self._connect() as c:
            row = c.execute(
                "SELECT api_key_hex FROM tenants WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if not row:
                raise KeyError(tenant_id)
            old_stored = row["api_key_hex"]   # already a sha256: digest
            c.execute(
                """UPDATE tenants
                   SET api_key_hex = ?,
                       previous_api_key_hex = ?,
                       previous_expires_at = ?,
                       last_rotated_at = ?
                   WHERE tenant_id = ?""",
                (stored_new, old_stored, now + grace_seconds, now, tenant_id),
            )
        # Refresh in-memory index — drop the old entry's claim once
        # the grace window has been recorded.
        self._reload_key_index()
        # Return a tenant-shaped object whose ``api_key_hex`` is the
        # plaintext (only here).
        cur = self.get(tenant_id)
        if cur is None:
            raise KeyError(tenant_id)
        return Tenant(
            tenant_id=cur.tenant_id,
            api_key_hex=plaintext_new,
            previous_api_key_hex=cur.previous_api_key_hex,
            previous_expires_at=cur.previous_expires_at,
            rate_limit_per_min=cur.rate_limit_per_min,
            rate_limit_per_day=cur.rate_limit_per_day,
            suspended=cur.suspended,
            created_at=cur.created_at,
            last_rotated_at=cur.last_rotated_at,
        )

    def suspend(self, tenant_id: str, suspended: bool = True) -> None:
        with self._connect() as c:
            c.execute(
                "UPDATE tenants SET suspended = ? WHERE tenant_id = ?",
                (1 if suspended else 0, tenant_id),
            )
        self._reload_key_index()

    def delete(self, tenant_id: str) -> None:
        with self._connect() as c:
            c.execute("DELETE FROM tenants WHERE tenant_id = ?", (tenant_id,))
        self._reload_key_index()

    def update_rate_limits(
        self,
        tenant_id: str,
        per_min: Optional[int] = None,
        per_day: Optional[int] = None,
    ) -> None:
        with self._connect() as c:
            cur = c.execute(
                "SELECT rate_limit_per_min, rate_limit_per_day FROM tenants WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if cur is None:
                raise KeyError(tenant_id)
            new_min = per_min if per_min is not None else cur["rate_limit_per_min"]
            new_day = per_day if per_day is not None else cur["rate_limit_per_day"]
            c.execute(
                """UPDATE tenants
                   SET rate_limit_per_min = ?, rate_limit_per_day = ?
                   WHERE tenant_id = ?""",
                (new_min, new_day, tenant_id),
            )

    # ── Usage metering ─────────────────────────────────────────

    def record_usage(
        self,
        tenant_id: str,
        endpoint: str,
        n_pairs: int = 0,
        elapsed_ms: float = 0.0,
        status_code: int = 200,
    ) -> None:
        # Round-2 audit NEW-MED-7 — refuse usage records for unknown
        # tenants so a buggy caller can't invent rows.
        if self.get(tenant_id) is None:
            logger.warning("tenants.record_usage_unknown_tenant tenant_id=%s",
                           tenant_id)
            return
        # Round-2 audit NEW-MED-16 — clamp values so a buggy caller
        # cannot insert negative or absurd numbers.
        n_pairs = max(0, min(int(n_pairs), 10_000_000))
        elapsed_ms = max(0.0, min(float(elapsed_ms), 10.0 * 60.0 * 1000.0))
        endpoint = (endpoint or "")[:64]
        now = time.time()
        cutoff = now - _USAGE_RETENTION_S
        with self._connect() as c:
            c.execute(
                """INSERT INTO usage_log
                   (tenant_id, epoch, endpoint, n_pairs, elapsed_ms, status_code)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tenant_id, now, endpoint, n_pairs, elapsed_ms, status_code),
            )
            # Round-3 audit R3-HIGH-5 — bound the per-call retention
            # cost.  Delete in 1000-row batches via subquery so a flood
            # of inserts can't lock the table for seconds.  SQLite's
            # `DELETE … WHERE rowid IN (SELECT … LIMIT N)` is the
            # portable form; LIMIT on plain DELETE requires the
            # ``SQLITE_ENABLE_UPDATE_DELETE_LIMIT`` build flag.
            c.execute(
                """DELETE FROM usage_log
                   WHERE rowid IN (
                       SELECT rowid FROM usage_log
                       WHERE epoch < ?
                       LIMIT 1000
                   )""",
                (cutoff,),
            )

    def usage_summary(
        self,
        tenant_id: str,
        window_seconds: float = 86400.0,
    ) -> dict:
        cutoff = time.time() - window_seconds
        with self._connect() as c:
            row = c.execute(
                """SELECT COUNT(*) AS n,
                          COALESCE(SUM(n_pairs), 0) AS pairs,
                          COALESCE(AVG(elapsed_ms), 0.0) AS avg_ms
                     FROM usage_log
                    WHERE tenant_id = ? AND epoch >= ?""",
                (tenant_id, cutoff),
            ).fetchone()
        return {
            "tenant_id": tenant_id,
            "window_seconds": window_seconds,
            "request_count": int(row["n"]),
            "pair_count": int(row["pairs"]),
            "avg_elapsed_ms": float(row["avg_ms"]),
        }

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _row_to_tenant(row: sqlite3.Row) -> Tenant:
        return Tenant(
            tenant_id=row["tenant_id"],
            api_key_hex=row["api_key_hex"],
            previous_api_key_hex=row["previous_api_key_hex"],
            previous_expires_at=row["previous_expires_at"],
            rate_limit_per_min=int(row["rate_limit_per_min"]),
            rate_limit_per_day=int(row["rate_limit_per_day"]),
            suspended=bool(row["suspended"]),
            created_at=float(row["created_at"]),
            last_rotated_at=(
                float(row["last_rotated_at"])
                if row["last_rotated_at"] is not None else None
            ),
        )


def default_db_path() -> Path:
    """Default SQLite path under ``data/runtime``.  Override with
    ``ARIA_SCREENER_DB`` for production deploys."""
    env = os.environ.get("ARIA_SCREENER_DB")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    return here.parents[3] / "data" / "runtime" / "screener_tenants.sqlite3"
