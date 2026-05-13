"""Admin layer — principal management + custom roles via two-person rule.

Implements the R33 admin/RBAC management layer on top of:

  - ApprovalQueue (F-9) — every admin mutation is a two-person proposal
    with cooling-off and audit trail
  - PrincipalStore — append-only hash-chained delta log
  - RoleStore — sealed-only at boot; custom roles appended at runtime
    via ``add_custom_role`` (this module) after a successful proposal

The flow for every admin action:

  1. The authorising principal calls one of the ``propose_*`` helpers
     here. We:
     a) verify the actor holds the relevant permission
     b) for custom roles, verify NO PRIVILEGE ESCALATION — the actor
        cannot grant permissions they do not themselves hold
     c) propose the action through ApprovalQueue.propose()

  2. A second principal signs via the existing
     POST /api/safety/approve flow (or two more, for higher gates).

  3. After cooling-off elapses, ApprovalQueue fires the executor
     registered here. The executor:
     a) re-extracts the approvers from the proposal (passed via
        ``_approvers`` in fire_params)
     b) validates the approvers still exist + still hold the relevant
        permission (defends against role changes during cooling-off)
     c) appends the principal-delta or roles-delta record

The two-step (propose → sign) flow keeps anti-collusion intact:
ApprovalQueue.approve() refuses the same operator_id signing twice.
The admin endpoint maps the authenticated session principal to the
operator_id automatically.

R33 — see docs/NEXT_STEPS.md.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

import structlog

from aria.safety.approval_queue import get_approval_queue
from aria.security.principals import (
    AuthorityCeiling,
    Principal,
    TrustTier,
    authorize,
    get_principal_store,
    get_role_store,
)

logger = structlog.get_logger()


# ── Constants ──────────────────────────────────────────────────────


# Admin actions are all sensitive enough to demand the standard
# two-person + cooling-off envelope. Each is conservative; tighter
# thresholds (e.g. shorter cooling-off for benign role list changes)
# can be added as new action names if usage demands it.
DEFAULT_REQUIRED_SIGNERS = 2
DEFAULT_COOLING_OFF_S = 30.0
DEFAULT_UNDO_WINDOW_S = 60.0
DEFAULT_LIFETIME_S = 600.0   # 10 min — proposals expire if not signed

ADMIN_ACTIONS: tuple[str, ...] = (
    "principal.create",
    "principal.revoke",
    "role.assign",
    "role.create_custom",
    "role.revoke_custom",
)


# ── Errors ─────────────────────────────────────────────────────────


class AdminError(RuntimeError):
    """Raised when an admin proposal cannot be created. The message is
    safe to surface to the operator UI."""


# ── No-escalation helper ──────────────────────────────────────────


def check_no_escalation(
    actor: Principal,
    permissions_to_grant: Iterable[str],
) -> tuple[bool, list[str]]:
    """An admin must hold every permission they want to grant via a
    custom role. Returns (ok, missing_permissions).

    Re-checked at executor fire time to defend against an actor's
    role being demoted between propose and execute.
    """
    role_store = get_role_store()
    actor_perms = role_store.permissions_for(actor.role)
    perms = set(permissions_to_grant)
    missing = sorted(perms - actor_perms)
    return (len(missing) == 0, missing)


# ── Proposal helpers ──────────────────────────────────────────────


def propose_create_principal(
    actor: Principal,
    *,
    principal_id: str,
    role: str,
    pubkey_hex: str,
    display_name: str = "",
) -> str:
    """Propose adding a new principal with the given Ed25519 pubkey
    + role. Returns proposal_id."""
    if not principal_id or not principal_id.replace("_", "").replace(".", "").isalnum():
        raise AdminError("principal_id must be alphanumeric (with . or _)")
    decision = authorize(actor, "principal.create")
    if not decision.allow:
        raise AdminError(f"actor cannot principal.create: {decision.reason}")
    if get_role_store().role(role) is None:
        raise AdminError(f"unknown role '{role}'")
    if len(pubkey_hex) != 64:
        raise AdminError("pubkey_hex must be 32-byte hex (64 chars)")
    try:
        bytes.fromhex(pubkey_hex)
    except ValueError as exc:
        raise AdminError(f"pubkey_hex not valid hex: {exc}") from exc
    if get_principal_store().get(principal_id) is not None:
        raise AdminError(f"principal '{principal_id}' already exists")
    return get_approval_queue().propose(
        action="principal.create",
        params={
            "principal_id": principal_id,
            "role": role,
            "pubkey_hex": pubkey_hex,
            "display_name": display_name or principal_id,
        },
        proposer=actor.principal_id,
        required_signers=DEFAULT_REQUIRED_SIGNERS,
        cooling_off_s=DEFAULT_COOLING_OFF_S,
        undo_window_s=DEFAULT_UNDO_WINDOW_S,
        lifetime_s=DEFAULT_LIFETIME_S,
        rule_id="principal.create",
        reason=f"create {principal_id} as {role}",
    )


def propose_revoke_principal(
    actor: Principal,
    *,
    principal_id: str,
) -> str:
    decision = authorize(actor, "principal.revoke")
    if not decision.allow:
        raise AdminError(f"actor cannot principal.revoke: {decision.reason}")
    target = get_principal_store().get(principal_id)
    if target is None:
        raise AdminError(f"principal '{principal_id}' not found or already revoked")
    if target.role == "captain":
        raise AdminError(
            "cannot revoke the captain via principal.revoke — "
            "use captain.elect to re-elect first",
        )
    return get_approval_queue().propose(
        action="principal.revoke",
        params={"principal_id": principal_id},
        proposer=actor.principal_id,
        required_signers=DEFAULT_REQUIRED_SIGNERS,
        cooling_off_s=DEFAULT_COOLING_OFF_S,
        undo_window_s=DEFAULT_UNDO_WINDOW_S,
        lifetime_s=DEFAULT_LIFETIME_S,
        rule_id="principal.revoke",
        reason=f"revoke {principal_id}",
    )


def propose_role_assign(
    actor: Principal,
    *,
    principal_id: str,
    new_role: str,
) -> str:
    decision = authorize(actor, "role.assign")
    if not decision.allow:
        raise AdminError(f"actor cannot role.assign: {decision.reason}")
    target = get_principal_store().get(principal_id)
    if target is None:
        raise AdminError(f"principal '{principal_id}' not found")
    if get_role_store().role(new_role) is None:
        raise AdminError(f"unknown role '{new_role}'")
    if target.role == new_role:
        raise AdminError(f"principal already in role '{new_role}'")
    if target.role == "captain":
        raise AdminError(
            "captain re-election uses captain.elect, not role.assign",
        )
    return get_approval_queue().propose(
        action="role.assign",
        params={"principal_id": principal_id, "new_role": new_role,
                "old_role": target.role},
        proposer=actor.principal_id,
        required_signers=DEFAULT_REQUIRED_SIGNERS,
        cooling_off_s=DEFAULT_COOLING_OFF_S,
        undo_window_s=DEFAULT_UNDO_WINDOW_S,
        lifetime_s=DEFAULT_LIFETIME_S,
        rule_id="role.assign",
        reason=f"reassign {principal_id} from {target.role} to {new_role}",
    )


def propose_create_custom_role(
    actor: Principal,
    *,
    name: str,
    inherits: Sequence[str],
    permissions: Sequence[str],
    description: str = "",
) -> str:
    """Custom role lives in roles.delta.jsonl.

    Constraints (see docstring at the top of this module):
      - cannot shadow a sealed role name
      - must inherit from at least one sealed role
      - granted permissions must exist in the sealed catalogue
      - actor must hold every permission they want to grant
        (no privilege escalation)
    """
    decision = authorize(actor, "role.create_custom")
    if not decision.allow:
        raise AdminError(f"actor cannot role.create_custom: {decision.reason}")
    if not name or not name.replace("_", "").isalnum():
        raise AdminError("custom role name must be alphanumeric")
    role_store = get_role_store()
    if role_store.is_sealed(name):
        raise AdminError(f"name '{name}' shadows a sealed role")
    if role_store.role(name) is not None:
        raise AdminError(f"custom role '{name}' already exists")
    if not inherits:
        raise AdminError("custom role must inherit from at least one sealed role")
    for parent in inherits:
        if not role_store.is_sealed(parent):
            raise AdminError(
                f"custom roles can only inherit from sealed roles "
                f"(got '{parent}')",
            )
    all_perms = set(role_store.all_permissions())
    unknown = set(permissions) - all_perms
    if unknown:
        raise AdminError(
            f"unknown permissions: {sorted(unknown)}",
        )
    ok, missing = check_no_escalation(actor, permissions)
    if not ok:
        raise AdminError(
            f"no-escalation refusal: actor lacks {missing}",
        )
    return get_approval_queue().propose(
        action="role.create_custom",
        params={
            "name": name,
            "inherits": list(inherits),
            "permissions": list(permissions),
            "description": description,
            "actor_principal_id_for_recheck": actor.principal_id,
        },
        proposer=actor.principal_id,
        required_signers=DEFAULT_REQUIRED_SIGNERS,
        cooling_off_s=DEFAULT_COOLING_OFF_S,
        undo_window_s=DEFAULT_UNDO_WINDOW_S,
        lifetime_s=DEFAULT_LIFETIME_S,
        rule_id="role.create_custom",
        reason=f"create custom role '{name}' inheriting {list(inherits)}",
    )


def propose_revoke_custom_role(
    actor: Principal,
    *,
    name: str,
) -> str:
    decision = authorize(actor, "role.revoke_custom")
    if not decision.allow:
        raise AdminError(f"actor cannot role.revoke_custom: {decision.reason}")
    role_store = get_role_store()
    if role_store.is_sealed(name):
        raise AdminError(
            f"cannot revoke sealed role '{name}' via runtime delta",
        )
    if role_store.role(name) is None:
        raise AdminError(f"custom role '{name}' not found")
    # Refuse if any active principal currently holds this role.
    holders = [p.principal_id for p in get_principal_store().all()
               if p.role == name]
    if holders:
        raise AdminError(
            f"role '{name}' still held by {holders}; revoke or reassign first",
        )
    return get_approval_queue().propose(
        action="role.revoke_custom",
        params={"name": name},
        proposer=actor.principal_id,
        required_signers=DEFAULT_REQUIRED_SIGNERS,
        cooling_off_s=DEFAULT_COOLING_OFF_S,
        undo_window_s=DEFAULT_UNDO_WINDOW_S,
        lifetime_s=DEFAULT_LIFETIME_S,
        rule_id="role.revoke_custom",
        reason=f"revoke custom role '{name}'",
    )


# ── Executors (fire after two-person + cooling-off) ───────────────


def _resolve_two_signers(
    fire_params: Dict[str, Any],
) -> tuple[Principal, Principal]:
    """Pull the two distinct approvers out of fire_params and re-fetch
    them from the live PrincipalStore. Raises if either is missing or
    revoked."""
    approvers: List[str] = list(fire_params.get("_approvers") or [])
    if len(approvers) < 2:
        raise RuntimeError(
            "admin executor: two-person rule violated at fire time "
            f"({len(approvers)} signer(s))",
        )
    if approvers[0] == approvers[1]:
        raise RuntimeError("admin executor: collusion (same signer twice)")
    ps = get_principal_store()
    actor = ps.get(approvers[0])
    co = ps.get(approvers[1])
    if actor is None or co is None:
        raise RuntimeError(
            f"admin executor: approver(s) no longer in store "
            f"({approvers[0]!r}, {approvers[1]!r})",
        )
    return actor, co


def _exec_create_principal(fire_params: Dict[str, Any]) -> None:
    actor, co = _resolve_two_signers(fire_params)
    ps = get_principal_store()
    fields = {
        "role": fire_params["role"],
        "pubkey_hex": fire_params["pubkey_hex"],
        "display_name": fire_params.get("display_name", fire_params["principal_id"]),
        "created_at": time.time(),
    }
    ps.append_delta(
        "create", fire_params["principal_id"], fields,
        actor=actor, co_signer=co,
        proposal_id=fire_params.get("_proposal_id", ""),
    )


def _exec_revoke_principal(fire_params: Dict[str, Any]) -> None:
    actor, co = _resolve_two_signers(fire_params)
    ps = get_principal_store()
    ps.append_delta(
        "revoke", fire_params["principal_id"], {},
        actor=actor, co_signer=co,
        proposal_id=fire_params.get("_proposal_id", ""),
    )
    # Defence in depth: revoke any active sessions for the principal.
    try:
        from aria.security.session_store import get_session_store
        n = get_session_store().revoke_all_for_principal(
            fire_params["principal_id"], reason="principal.revoke",
        )
        logger.info("admin.principal_revoked",
                    principal_id=fire_params["principal_id"],
                    sessions_killed=n)
    except Exception as exc:
        logger.error("admin.session_revoke_failed", error=str(exc))


def _exec_role_assign(fire_params: Dict[str, Any]) -> None:
    actor, co = _resolve_two_signers(fire_params)
    ps = get_principal_store()
    ps.append_delta(
        "role_change", fire_params["principal_id"],
        {"role": fire_params["new_role"]},
        actor=actor, co_signer=co,
        proposal_id=fire_params.get("_proposal_id", ""),
    )
    # Defence in depth: revoke existing sessions so the principal must
    # re-auth and pick up the new role.
    try:
        from aria.security.session_store import get_session_store
        get_session_store().revoke_all_for_principal(
            fire_params["principal_id"], reason="role.assign",
        )
    except Exception as exc:
        logger.error("admin.role_assign_session_revoke_failed", error=str(exc))


def _exec_create_custom_role(fire_params: Dict[str, Any]) -> None:
    actor, co = _resolve_two_signers(fire_params)
    # Re-run no-escalation against the LIVE actor — defends against an
    # actor demoted between propose and fire.
    ok, missing = check_no_escalation(actor, fire_params.get("permissions", []))
    if not ok:
        raise RuntimeError(
            f"no-escalation re-check failed at fire time: actor lacks {missing}",
        )
    role_store = get_role_store()
    role_store.add_custom_role(
        name=fire_params["name"],
        inherits=fire_params["inherits"],
        permissions=fire_params.get("permissions", []),
        description=fire_params.get("description", ""),
        actor_principal_id=actor.principal_id,
        co_signer_principal_id=co.principal_id,
        proposal_id=fire_params.get("_proposal_id", ""),
    )


def _exec_revoke_custom_role(fire_params: Dict[str, Any]) -> None:
    actor, co = _resolve_two_signers(fire_params)
    role_store = get_role_store()
    role_store.revoke_custom_role(
        name=fire_params["name"],
        actor_principal_id=actor.principal_id,
        co_signer_principal_id=co.principal_id,
        proposal_id=fire_params.get("_proposal_id", ""),
    )


# ── Registration ──────────────────────────────────────────────────


_REGISTERED = False
_REGISTER_LOCK = threading.Lock()


def register_admin_executors() -> None:
    """Wire admin executors into the global ApprovalQueue. Idempotent."""
    global _REGISTERED
    with _REGISTER_LOCK:
        if _REGISTERED:
            return
        q = get_approval_queue()
        q.register_executor("principal.create", _exec_create_principal)
        q.register_executor("principal.revoke", _exec_revoke_principal)
        q.register_executor("role.assign", _exec_role_assign)
        q.register_executor("role.create_custom", _exec_create_custom_role)
        q.register_executor("role.revoke_custom", _exec_revoke_custom_role)
        _REGISTERED = True
    logger.info("admin.executors_registered", actions=ADMIN_ACTIONS)


def reset_for_test() -> None:
    """Clear the registered flag. Only for tests."""
    global _REGISTERED
    with _REGISTER_LOCK:
        _REGISTERED = False
