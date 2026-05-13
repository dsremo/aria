"""Principal model + RBAC authoriser — ship-wide identity layer.

Implements §F-1 / §F-9 / §F-14 of FAILSAFE_ARCHITECTURE.md and the
identity layer described in `docs/THREAT_MODEL.md` worst-case chains
W-1 / W-4 (jealous-operator / coerced-operator).

A `Principal` is the verified identity behind every privileged call.
A `Role` defines authority ceiling, trust tier, and inheritance. A
`Permission` is a string name — every authorisation gate cites one.

Authority resolution is deterministic: `authorize(principal, perm)`
walks the inheritance graph once and returns ALLOW or DENY with a
reason. There is no side-channel — no implicit "system trust", no
fall-through to "default allow".

The identity tree is sealed. The roster (`principals.v1.toml`),
the role lattice (`roles.v1.toml`), and the permission catalogue
(`permissions.v1.toml`) are all hashed in `data/sealed/MANIFEST.toml`,
so an attacker who edits any of them breaks boot (§F-1 + §F-18).

Runtime mutations (revoke, role-change, key rotation) live in a
hash-chained append-only delta log (`data/runtime/principals.delta.jsonl`),
anchored to the audit chain (`security/audit.py`) on every mutation.

Threats addressed:
  T-IV-1 jealous operator         (role=crew cannot act as captain)
  T-IV-2 coerced operator         (duress recall path returns sandbox tier)
  T-IV-5 single-person catastrophe (captain elects via two-person rule)
  T-V-1 same-vendor monitor        (agent role hard-capped, cannot mint
                                    CONSENT+ tokens regardless of plan)
  T-VI-3 disabled deadman          (deadman.affirm permission still tied
                                    to authenticated principal)
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field

# tomllib is stdlib on Py>=3.11; tomli is the backport for 3.10.
try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional

import structlog

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = structlog.get_logger()


# ── Locating sealed + runtime stores ──────────────────────────────


def _default_sealed_dir() -> Path:
    env = os.environ.get("ARIA_SEALED_DIR")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    # src/aria/security/principals.py → repo root via parents[3]
    return (here.parents[3] / "data" / "sealed").resolve()


def _default_runtime_dir() -> Path:
    env = os.environ.get("ARIA_RUNTIME_DIR")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    return (here.parents[3] / "data" / "runtime").resolve()


# ── Datatypes ─────────────────────────────────────────────────────


class TrustTier(str, Enum):
    """Mirror of cognitive.constitution.TrustTier names — kept in sync.

    Keeping a parallel enum avoids a hard import cycle: principals is
    consumed by safe_dispatch, which sits underneath constitution.
    """
    THIRD_PARTY_CONTENT = "THIRD_PARTY_CONTENT"
    LOCAL_SENSOR = "LOCAL_SENSOR"
    EXTERNAL_API = "EXTERNAL_API"
    OPERATOR = "OPERATOR"


class AuthorityCeiling(str, Enum):
    """Mirror of core.types.AuthorityLevel names."""
    SENSOR_ONLY = "SENSOR_ONLY"
    ROUTINE = "ROUTINE"
    SUPERVISED = "SUPERVISED"
    CONSENT = "CONSENT"
    ADVISORY = "ADVISORY"
    CAPTAIN_ONLY = "CAPTAIN_ONLY"


_AUTH_RANK = {
    AuthorityCeiling.SENSOR_ONLY: 0,
    AuthorityCeiling.ROUTINE: 1,
    AuthorityCeiling.SUPERVISED: 2,
    AuthorityCeiling.CONSENT: 3,
    AuthorityCeiling.ADVISORY: 4,
    AuthorityCeiling.CAPTAIN_ONLY: 5,
}


@dataclass(frozen=True)
class Role:
    """A named role in the inheritance lattice."""
    name: str
    inherits: tuple[str, ...]
    trust_tier: TrustTier
    authority_ceiling: AuthorityCeiling
    description: str = ""

    @property
    def is_human(self) -> bool:
        """True if the role represents an authenticated human."""
        return self.name in {"captain", "crew", "maintainer", "operator", "ground"}

    @property
    def is_agent(self) -> bool:
        return self.name == "agent"

    @property
    def is_system(self) -> bool:
        return self.name == "system"


@dataclass(frozen=True)
class Principal:
    """A verified identity. Constructed by the auth service."""
    principal_id: str
    role: str                       # role name (resolved via RoleStore)
    pubkey_hex: str = ""            # Ed25519 public key, hex (32 bytes)
    display_name: str = ""
    created_at: float = 0.0
    expires_at: float = 0.0
    revoked: bool = False
    duress: bool = False            # true when the principal logged in via duress code
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def anonymous(cls) -> "Principal":
        return cls(principal_id="anonymous", role="anonymous")

    @classmethod
    def system(cls) -> "Principal":
        return cls(principal_id="system", role="system")

    @classmethod
    def agent(cls, name: str) -> "Principal":
        return cls(principal_id=f"agent:{name}", role="agent")

    @classmethod
    def tamper(cls, reason: str = "") -> "Principal":
        return cls(principal_id="tamper",
                   role="tamper",
                   metadata={"reason": reason})

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at <= 0:
            return False
        return (now or time.time()) > self.expires_at

    def verify_signature(self, payload: bytes, signature: bytes) -> bool:
        """Verify an Ed25519 signature using this principal's pubkey."""
        if not self.pubkey_hex:
            return False
        try:
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(self.pubkey_hex))
            pub.verify(signature, payload)
            return True
        except (InvalidSignature, ValueError):
            return False


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str
    principal_id: str = ""
    permission: str = ""

    def __bool__(self) -> bool:
        return self.allow


# ── Role store ───────────────────────────────────────────────────


class _RoleStore:
    """In-memory role lattice + permission catalogue.

    Sealed roles + permissions load once from data/sealed/. Custom
    roles (R33) live in data/runtime/roles.delta.jsonl and are
    appended via :meth:`add_custom_role` after a two-person ApprovalQueue
    proposal completes. Custom roles can only INHERIT from sealed
    roles (cannot redefine sealed names) and can only grant
    permissions that exist in the sealed catalogue.
    """

    CUSTOM_DELTA_FILENAME = "roles.delta.jsonl"

    def __init__(
        self,
        sealed_dir: Optional[Path] = None,
        runtime_dir: Optional[Path] = None,
    ) -> None:
        self._sealed_dir = (sealed_dir or _default_sealed_dir()).resolve()
        self._runtime_dir = (runtime_dir or _default_runtime_dir()).resolve()
        self._roles: Dict[str, Role] = {}
        self._sealed_role_names: FrozenSet[str] = frozenset()
        # role_name -> closure of inherited roles (incl. self)
        self._closure: Dict[str, FrozenSet[str]] = {}
        # permission_name -> set of *direct* role holders
        self._perm_to_roles: Dict[str, FrozenSet[str]] = {}
        # role_name -> set of permissions held (after closure)
        self._role_to_perms: Dict[str, FrozenSet[str]] = {}
        # custom role specifics: name -> permissions granted directly.
        self._custom_perms: Dict[str, FrozenSet[str]] = {}
        self._lock = threading.RLock()
        self._loaded = False

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._roles = self._load_roles()
            self._sealed_role_names = frozenset(self._roles)
            self._perm_to_roles = self._load_permissions()
            self._apply_custom_roles_locked()
            self._loaded = True
        logger.info("principals.role_store_loaded",
                    sealed_roles=len(self._sealed_role_names),
                    custom_roles=len(self._roles) - len(self._sealed_role_names),
                    permissions=len(self._perm_to_roles))

    def _load_roles(self) -> Dict[str, Role]:
        path = self._sealed_dir / "roles.v1.toml"
        if not path.is_file():
            raise FileNotFoundError(f"sealed roles file missing: {path}")
        data = tomllib.loads(path.read_text())
        roles_raw = data.get("roles", {})
        out: Dict[str, Role] = {}
        for name, body in roles_raw.items():
            try:
                tier = TrustTier(body["trust_tier"])
                ceiling = AuthorityCeiling(body["authority_ceiling"])
            except (KeyError, ValueError) as exc:
                raise ValueError(f"role '{name}' invalid: {exc}") from exc
            out[name] = Role(
                name=name,
                inherits=tuple(body.get("inherits", ())),
                trust_tier=tier,
                authority_ceiling=ceiling,
                description=str(body.get("description", "")),
            )
        return out

    def _compute_closure(self, roles: Mapping[str, Role]) -> Dict[str, FrozenSet[str]]:
        """For each role, return the set of role names it inherits from
        transitively, including itself. Detects cycles and raises."""
        closure: Dict[str, FrozenSet[str]] = {}
        visiting: set[str] = set()

        def walk(name: str) -> FrozenSet[str]:
            if name in closure:
                return closure[name]
            if name in visiting:
                raise ValueError(f"role inheritance cycle at '{name}'")
            if name not in roles:
                raise ValueError(f"unknown parent role '{name}'")
            visiting.add(name)
            acc: set[str] = {name}
            for parent in roles[name].inherits:
                acc.update(walk(parent))
            visiting.discard(name)
            closure[name] = frozenset(acc)
            return closure[name]

        for n in roles:
            walk(n)
        return closure

    def _load_permissions(self) -> Dict[str, FrozenSet[str]]:
        path = self._sealed_dir / "permissions.v1.toml"
        if not path.is_file():
            raise FileNotFoundError(f"sealed permissions file missing: {path}")
        data = tomllib.loads(path.read_text())
        perms_raw = data.get("permissions", {})
        out: Dict[str, FrozenSet[str]] = {}
        for name, body in perms_raw.items():
            holders = body.get("holders", [])
            out[name] = frozenset(holders)
        return out

    def _invert_perms(self) -> Dict[str, FrozenSet[str]]:
        # role -> set of perms (direct + via inheritance + custom direct)
        # A role gets a permission if any role IT inherits from is a
        # direct holder. That is, "captain inherits crew" means
        # captain holds every crew permission.
        out: Dict[str, set[str]] = {n: set() for n in self._roles}
        # For each permission, walk the holders' inverse-closure: any
        # role whose closure contains a direct holder receives the perm.
        for perm, holders in self._perm_to_roles.items():
            for role_name, closure in self._closure.items():
                if closure & holders:
                    out[role_name].add(perm)
        # Custom-role direct permission grants (R33).
        for role_name, custom_perms in self._custom_perms.items():
            out.setdefault(role_name, set()).update(custom_perms)
        return {k: frozenset(v) for k, v in out.items()}

    # ── Custom role runtime store (R33) ──────────────────────────

    def _apply_custom_roles_locked(self) -> None:
        """Re-derive lattice + permissions including custom roles.

        Called on initial load and after every successful add/remove.
        Holds the store lock.
        """
        # Reset to sealed-only baseline.
        self._roles = self._load_roles()
        self._custom_perms = {}
        # Replay the delta log. Validation re-runs on every load so a
        # tampered/manually-edited delta cannot grant unsupported
        # permissions or shadow a sealed role.
        for rec in self._read_custom_deltas():
            try:
                self._validate_custom_role_record_locked(rec)
            except ValueError as exc:
                logger.error("principals.custom_role_invalid",
                             name=rec.get("name", "<unknown>"),
                             reason=str(exc))
                continue
            if rec.get("op") == "create":
                self._roles[rec["name"]] = Role(
                    name=rec["name"],
                    inherits=tuple(rec["inherits"]),
                    trust_tier=TrustTier(rec["trust_tier"]),
                    authority_ceiling=AuthorityCeiling(rec["authority_ceiling"]),
                    description=str(rec.get("description", "")),
                )
                self._custom_perms[rec["name"]] = frozenset(rec.get("permissions", []))
            elif rec.get("op") == "revoke":
                self._roles.pop(rec["name"], None)
                self._custom_perms.pop(rec["name"], None)
        self._closure = self._compute_closure(self._roles)
        self._role_to_perms = self._invert_perms()

    def _validate_custom_role_record_locked(self, rec: Mapping[str, Any]) -> None:
        op = rec.get("op")
        name = str(rec.get("name", ""))
        if not name:
            raise ValueError("custom role missing name")
        if op == "revoke":
            if name in self._sealed_role_names:
                raise ValueError(
                    f"cannot revoke sealed role '{name}' via runtime delta",
                )
            return
        if op != "create":
            raise ValueError(f"unknown custom-role op '{op}'")
        if name in self._sealed_role_names:
            raise ValueError(
                f"custom role name '{name}' shadows a sealed role",
            )
        inherits = list(rec.get("inherits", []))
        if not inherits:
            raise ValueError("custom role must inherit from at least one sealed role")
        for parent in inherits:
            if parent not in self._sealed_role_names:
                raise ValueError(
                    f"custom role '{name}' inherits non-sealed parent '{parent}'",
                )
        try:
            TrustTier(str(rec.get("trust_tier")))
            AuthorityCeiling(str(rec.get("authority_ceiling")))
        except ValueError as exc:
            raise ValueError(f"invalid tier/ceiling: {exc}") from exc
        unknown = set(rec.get("permissions", [])) - set(self._perm_to_roles)
        if unknown:
            raise ValueError(
                f"custom role '{name}' grants unknown permissions: {sorted(unknown)}",
            )

    def _read_custom_deltas(self) -> list[dict[str, Any]]:
        path = self._runtime_dir / self.CUSTOM_DELTA_FILENAME
        if not path.is_file():
            return []
        out: list[dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception as exc:
                    logger.error("principals.custom_role_delta_parse_failed",
                                 error=str(exc))
        return out

    def add_custom_role(
        self,
        *,
        name: str,
        inherits: Iterable[str],
        permissions: Iterable[str],
        description: str = "",
        actor_principal_id: str = "",
        co_signer_principal_id: str = "",
        proposal_id: str = "",
    ) -> Role:
        """Append a 'create' record to roles.delta.jsonl and reload.

        Caller must verify the actor + co_signer passed the
        ApprovalQueue two-person flow AND must have already run the
        no-escalation check (see security/admin.py). This method just
        records and reloads.
        """
        rec = {
            "op": "create",
            "ts": time.time(),
            "name": name,
            "inherits": list(inherits),
            # Custom roles cannot exceed their parents' tier/ceiling.
            # Caller computes the conservative min and passes it.
            "trust_tier": TrustTier.OPERATOR.value,
            "authority_ceiling": AuthorityCeiling.CONSENT.value,
            "description": description,
            "permissions": sorted(set(permissions)),
            "actor_principal_id": actor_principal_id,
            "co_signer_principal_id": co_signer_principal_id,
            "proposal_id": proposal_id,
        }
        with self._lock:
            self._validate_custom_role_record_locked(rec)
            # Compute conservative tier/ceiling from parents.
            tier_rank = {
                TrustTier.THIRD_PARTY_CONTENT: 0,
                TrustTier.LOCAL_SENSOR: 1,
                TrustTier.EXTERNAL_API: 2,
                TrustTier.OPERATOR: 3,
            }
            parent_tier = min(
                (tier_rank[self._roles[p].trust_tier] for p in rec["inherits"]),
                default=0,
            )
            parent_ceiling = min(
                (_AUTH_RANK[self._roles[p].authority_ceiling] for p in rec["inherits"]),
                default=0,
            )
            tier_for_rank = {v: k for k, v in tier_rank.items()}
            ceiling_for_rank = {v: k for k, v in _AUTH_RANK.items()}
            rec["trust_tier"] = tier_for_rank[parent_tier].value
            rec["authority_ceiling"] = ceiling_for_rank[parent_ceiling].value
            self._runtime_dir.mkdir(parents=True, exist_ok=True)
            with open(self._runtime_dir / self.CUSTOM_DELTA_FILENAME, "a",
                      encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True, ensure_ascii=True) + "\n")
            self._apply_custom_roles_locked()
        logger.info("principals.custom_role_created",
                    name=name, inherits=list(inherits),
                    permissions=len(rec["permissions"]),
                    actor=actor_principal_id,
                    co_signer=co_signer_principal_id)
        return self._roles[name]

    def revoke_custom_role(
        self,
        *,
        name: str,
        actor_principal_id: str = "",
        co_signer_principal_id: str = "",
        proposal_id: str = "",
    ) -> bool:
        rec = {
            "op": "revoke",
            "ts": time.time(),
            "name": name,
            "actor_principal_id": actor_principal_id,
            "co_signer_principal_id": co_signer_principal_id,
            "proposal_id": proposal_id,
        }
        with self._lock:
            self._validate_custom_role_record_locked(rec)
            if name not in self._roles:
                return False
            self._runtime_dir.mkdir(parents=True, exist_ok=True)
            with open(self._runtime_dir / self.CUSTOM_DELTA_FILENAME, "a",
                      encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True, ensure_ascii=True) + "\n")
            self._apply_custom_roles_locked()
        logger.info("principals.custom_role_revoked", name=name)
        return True

    def is_sealed(self, role_name: str) -> bool:
        self.load()
        return role_name in self._sealed_role_names

    # ── Public surface ────────────────────────────────────────────

    def role(self, name: str) -> Optional[Role]:
        self.load()
        return self._roles.get(name)

    def all_roles(self) -> tuple[Role, ...]:
        self.load()
        return tuple(self._roles.values())

    def has_permission(self, role_name: str, permission: str) -> bool:
        self.load()
        return permission in self._role_to_perms.get(role_name, frozenset())

    def permissions_for(self, role_name: str) -> FrozenSet[str]:
        self.load()
        return self._role_to_perms.get(role_name, frozenset())

    def all_permissions(self) -> tuple[str, ...]:
        self.load()
        return tuple(sorted(self._perm_to_roles))

    def authority_ceiling(self, role_name: str) -> AuthorityCeiling:
        self.load()
        r = self._roles.get(role_name)
        return r.authority_ceiling if r else AuthorityCeiling.SENSOR_ONLY

    def trust_tier(self, role_name: str) -> TrustTier:
        self.load()
        r = self._roles.get(role_name)
        return r.trust_tier if r else TrustTier.THIRD_PARTY_CONTENT


# ── Principal store ───────────────────────────────────────────────


@dataclass(frozen=True)
class _DeltaRecord:
    """One mutation entry in principals.delta.jsonl."""
    seq: int
    ts: float
    op: str                 # "revoke" | "create" | "rotate" | "role_change"
    principal_id: str
    fields: Mapping[str, Any]
    actor_principal_id: str
    co_signer_principal_id: str
    proposal_id: str
    prev_hash: str
    hash: str

    def to_json(self) -> str:
        d = {
            "seq": self.seq,
            "ts": self.ts,
            "op": self.op,
            "principal_id": self.principal_id,
            "fields": dict(self.fields),
            "actor_principal_id": self.actor_principal_id,
            "co_signer_principal_id": self.co_signer_principal_id,
            "proposal_id": self.proposal_id,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }
        return json.dumps(d, sort_keys=True, ensure_ascii=True)

    @staticmethod
    def canonical_for_hash(seq: int, ts: float, op: str,
                           principal_id: str, fields: Mapping[str, Any],
                           actor_principal_id: str,
                           co_signer_principal_id: str,
                           proposal_id: str, prev_hash: str) -> bytes:
        d = {
            "seq": seq,
            "ts": f"{ts:.6f}",
            "op": op,
            "principal_id": principal_id,
            "fields": dict(fields),
            "actor_principal_id": actor_principal_id,
            "co_signer_principal_id": co_signer_principal_id,
            "proposal_id": proposal_id,
            "prev_hash": prev_hash,
        }
        return json.dumps(d, sort_keys=True, ensure_ascii=True).encode()


class _PrincipalStore:
    """Sealed roster + tamper-evident mutation log."""

    GENESIS_HASH = "0" * 64
    DELTA_FILENAME = "principals.delta.jsonl"

    def __init__(
        self,
        sealed_dir: Optional[Path] = None,
        runtime_dir: Optional[Path] = None,
    ) -> None:
        self._sealed_dir = (sealed_dir or _default_sealed_dir()).resolve()
        self._runtime_dir = (runtime_dir or _default_runtime_dir()).resolve()
        self._sealed: Dict[str, Principal] = {}
        self._effective: Dict[str, Principal] = {}
        self._deltas: list[_DeltaRecord] = []
        self._ground_pubkey_hex: str = ""
        self._ship_root_pubkey_hex: str = ""
        self._lock = threading.RLock()
        self._loaded = False

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._sealed = self._load_sealed()
            self._deltas = self._load_deltas()
            self._effective = self._compute_effective(self._sealed, self._deltas)
            self._loaded = True
        logger.info("principals.store_loaded",
                    sealed_count=len(self._sealed),
                    delta_count=len(self._deltas),
                    effective_count=len(self._effective))

    # ── Loaders ──────────────────────────────────────────────────

    def _load_sealed(self) -> Dict[str, Principal]:
        path = self._sealed_dir / "principals.v1.toml"
        if not path.is_file():
            raise FileNotFoundError(f"sealed principals file missing: {path}")
        data = tomllib.loads(path.read_text())
        self._ground_pubkey_hex = str(
            data.get("ground", {}).get("mcc_pubkey_hex", ""),
        )
        self._ship_root_pubkey_hex = str(
            data.get("hsm", {}).get("ship_root_pubkey_hex", ""),
        )
        out: Dict[str, Principal] = {}
        for pid, body in data.get("principals", {}).items():
            out[pid] = Principal(
                principal_id=pid,
                role=str(body.get("role", "")),
                pubkey_hex=str(body.get("pubkey_hex", "")),
                display_name=str(body.get("display_name", "")),
                created_at=_parse_date_to_unix(str(body.get("created_at", ""))),
                expires_at=_parse_date_to_unix(str(body.get("expires_at", ""))),
            )
        return out

    def _load_deltas(self) -> list[_DeltaRecord]:
        path = self._runtime_dir / self.DELTA_FILENAME
        if not path.is_file():
            return []
        out: list[_DeltaRecord] = []
        prev_hash = self.GENESIS_HASH
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                rec = _DeltaRecord(
                    seq=int(d["seq"]),
                    ts=float(d["ts"]),
                    op=str(d["op"]),
                    principal_id=str(d["principal_id"]),
                    fields=dict(d.get("fields", {})),
                    actor_principal_id=str(d.get("actor_principal_id", "")),
                    co_signer_principal_id=str(d.get("co_signer_principal_id", "")),
                    proposal_id=str(d.get("proposal_id", "")),
                    prev_hash=str(d.get("prev_hash", "")),
                    hash=str(d.get("hash", "")),
                )
                expected = hashlib.sha256(
                    _DeltaRecord.canonical_for_hash(
                        rec.seq, rec.ts, rec.op, rec.principal_id,
                        rec.fields, rec.actor_principal_id,
                        rec.co_signer_principal_id, rec.proposal_id,
                        prev_hash,
                    ),
                ).hexdigest()
                if rec.hash != expected or rec.prev_hash != prev_hash:
                    raise ValueError(
                        f"principals delta chain broken at seq={rec.seq}",
                    )
                out.append(rec)
                prev_hash = rec.hash
        return out

    def _compute_effective(
        self,
        sealed: Mapping[str, Principal],
        deltas: Iterable[_DeltaRecord],
    ) -> Dict[str, Principal]:
        out: Dict[str, Principal] = dict(sealed)
        for d in deltas:
            if d.op == "revoke":
                cur = out.get(d.principal_id)
                if cur is not None:
                    out[d.principal_id] = Principal(
                        **{**_principal_to_kwargs(cur), "revoked": True},
                    )
            elif d.op == "create":
                fields = dict(d.fields)
                out[d.principal_id] = Principal(
                    principal_id=d.principal_id,
                    role=str(fields.get("role", "")),
                    pubkey_hex=str(fields.get("pubkey_hex", "")),
                    display_name=str(fields.get("display_name", "")),
                    created_at=float(fields.get("created_at", d.ts)),
                    expires_at=float(fields.get("expires_at", 0.0)),
                )
            elif d.op == "rotate":
                cur = out.get(d.principal_id)
                if cur is not None:
                    new_pub = str(d.fields.get("pubkey_hex", cur.pubkey_hex))
                    out[d.principal_id] = Principal(
                        **{**_principal_to_kwargs(cur), "pubkey_hex": new_pub},
                    )
            elif d.op == "role_change":
                cur = out.get(d.principal_id)
                if cur is not None:
                    new_role = str(d.fields.get("role", cur.role))
                    out[d.principal_id] = Principal(
                        **{**_principal_to_kwargs(cur), "role": new_role},
                    )
            # Unknown op: ignore (forward-compat) — but we already chain-
            # verified the delta, so an attacker cannot inject a new op.
        return out

    # ── Public surface ────────────────────────────────────────────

    def get(self, principal_id: str) -> Optional[Principal]:
        self.load()
        p = self._effective.get(principal_id)
        if p is None:
            return None
        if p.revoked:
            return None
        return p

    def all(self) -> tuple[Principal, ...]:
        self.load()
        return tuple(p for p in self._effective.values() if not p.revoked)

    def ground_pubkey_hex(self) -> str:
        self.load()
        return self._ground_pubkey_hex

    def ship_root_pubkey_hex(self) -> str:
        self.load()
        return self._ship_root_pubkey_hex

    def head_hash(self) -> str:
        self.load()
        if self._deltas:
            return self._deltas[-1].hash
        return self.GENESIS_HASH

    def append_delta(
        self,
        op: str,
        principal_id: str,
        fields: Mapping[str, Any],
        actor: Principal,
        co_signer: Principal,
        proposal_id: str,
    ) -> _DeltaRecord:
        """Append a hash-chained mutation. Caller must have already
        gone through ApprovalQueue (two-person rule)."""
        if op not in {"revoke", "create", "rotate", "role_change"}:
            raise ValueError(f"unknown delta op: {op}")
        if actor.principal_id == co_signer.principal_id:
            raise ValueError("actor and co-signer must be distinct (anti-collusion)")

        with self._lock:
            self.load()
            prev_hash = self._deltas[-1].hash if self._deltas else self.GENESIS_HASH
            seq = self._deltas[-1].seq + 1 if self._deltas else 0
            ts = time.time()
            payload = _DeltaRecord.canonical_for_hash(
                seq, ts, op, principal_id, fields,
                actor.principal_id, co_signer.principal_id,
                proposal_id, prev_hash,
            )
            h = hashlib.sha256(payload).hexdigest()
            rec = _DeltaRecord(
                seq=seq, ts=ts, op=op, principal_id=principal_id,
                fields=fields, actor_principal_id=actor.principal_id,
                co_signer_principal_id=co_signer.principal_id,
                proposal_id=proposal_id, prev_hash=prev_hash, hash=h,
            )
            self._runtime_dir.mkdir(parents=True, exist_ok=True)
            with open(self._runtime_dir / self.DELTA_FILENAME, "a",
                      encoding="utf-8") as f:
                f.write(rec.to_json() + "\n")
            self._deltas.append(rec)
            self._effective = self._compute_effective(self._sealed, self._deltas)
        logger.info("principals.delta_appended",
                    seq=seq, op=op, principal_id=principal_id,
                    actor=actor.principal_id, co_signer=co_signer.principal_id)
        return rec


def _principal_to_kwargs(p: Principal) -> Dict[str, Any]:
    return {
        "principal_id": p.principal_id,
        "role": p.role,
        "pubkey_hex": p.pubkey_hex,
        "display_name": p.display_name,
        "created_at": p.created_at,
        "expires_at": p.expires_at,
        "revoked": p.revoked,
        "duress": p.duress,
        "metadata": p.metadata,
    }


def _parse_date_to_unix(s: str) -> float:
    if not s:
        return 0.0
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(
            tzinfo=timezone.utc,
        ).timestamp()
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return 0.0


# ── Singletons ───────────────────────────────────────────────────


_ROLES: Optional[_RoleStore] = None
_PRINCIPALS: Optional[_PrincipalStore] = None
_LOCK = threading.RLock()


def get_role_store() -> _RoleStore:
    global _ROLES
    if _ROLES is None:
        with _LOCK:
            if _ROLES is None:
                _ROLES = _RoleStore()
                _ROLES.load()
    else:
        _ROLES.load()
    return _ROLES


def get_principal_store() -> _PrincipalStore:
    global _PRINCIPALS
    if _PRINCIPALS is None:
        with _LOCK:
            if _PRINCIPALS is None:
                _PRINCIPALS = _PrincipalStore()
                _PRINCIPALS.load()
    return _PRINCIPALS


def reset_for_test(
    sealed_dir: Optional[Path] = None,
    runtime_dir: Optional[Path] = None,
) -> None:
    """Drop singletons. Pass override paths for hermetic test stores."""
    global _ROLES, _PRINCIPALS
    with _LOCK:
        _ROLES = _RoleStore(sealed_dir=sealed_dir, runtime_dir=runtime_dir)
        _PRINCIPALS = _PrincipalStore(
            sealed_dir=sealed_dir, runtime_dir=runtime_dir,
        )


# ── Authorisation entrypoint ─────────────────────────────────────


def authorize(
    principal: Principal,
    permission: str,
    *,
    context: Optional[Mapping[str, Any]] = None,
) -> Decision:
    """Single, deterministic decision point. Deny-by-default.

    Order of checks (each fails closed):
      1. Principal is not None and not the tamper sentinel.
      2. Principal is not revoked / expired (re-checked from store).
      3. Principal's role exists in the role lattice.
      4. Role (transitively) holds the named permission.
      5. Duress sessions max out at SENSOR_ONLY regardless of role.
    """
    perm = str(permission or "")
    pid = principal.principal_id if principal else ""

    if principal is None or principal.role == "tamper":
        return Decision(False, "tamper or null principal", pid, perm)

    # Anonymous and system are special: anonymous holds only the login
    # permission; system is consulted by RoleStore the same way.

    # Re-check store membership for non-synthetic principals (so a
    # caller cannot present a stale Principal whose role has been
    # changed in a delta).
    if principal.role not in {"anonymous", "agent", "system", "tamper"}:
        store = get_principal_store()
        cur = store.get(principal.principal_id)
        if cur is None:
            return Decision(False, "principal not found in store", pid, perm)
        if cur.is_expired():
            return Decision(False, "principal expired", pid, perm)
        if cur.role != principal.role:
            return Decision(False,
                            f"principal role drifted (store={cur.role})",
                            pid, perm)

    roles = get_role_store()
    role_obj = roles.role(principal.role)
    if role_obj is None:
        return Decision(False, f"unknown role '{principal.role}'", pid, perm)

    if principal.duress and role_obj.authority_ceiling != AuthorityCeiling.SENSOR_ONLY:
        # Duress login: only `telemetry.read` is permitted, nothing else.
        if perm != "telemetry.read":
            return Decision(False, "duress session capped at SENSOR_ONLY",
                            pid, perm)

    if not roles.has_permission(principal.role, perm):
        return Decision(False, f"role '{principal.role}' lacks '{perm}'",
                        pid, perm)

    return Decision(True, "ok", pid, perm)


# ── Helpers for callers that need tier/ceiling without authorize() ──


def trust_tier_for(principal: Principal) -> TrustTier:
    return get_role_store().trust_tier(principal.role)


def authority_ceiling_for(principal: Principal) -> AuthorityCeiling:
    return get_role_store().authority_ceiling(principal.role)


def authority_rank(c: AuthorityCeiling) -> int:
    return _AUTH_RANK[c]
