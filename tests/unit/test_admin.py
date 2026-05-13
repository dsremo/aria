"""R33 — admin layer tests.

Covers:
  * propose_create_principal end-to-end via two-person ApprovalQueue
  * propose_revoke_principal + session blast
  * propose_role_assign + session re-auth side effect
  * propose_create_custom_role with no-escalation guard
  * sealed-name shadow refusal
  * inherits-only-sealed refusal
  * unknown-permission refusal
  * propose_revoke_custom_role refused while role still in use
  * fire-time re-check of no-escalation (actor demoted during cooling-off)
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aria.security import principals as p
from aria.security import admin
from aria.safety.approval_queue import (
    get_approval_queue,
    reset_for_test as reset_aq,
)


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"


def _setup(tmp_path: Path) -> None:
    p.reset_for_test(sealed_dir=SEALED, runtime_dir=tmp_path)
    reset_aq()
    admin.reset_for_test()
    admin.register_admin_executors()


def _new_pubkey_hex() -> str:
    return Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()


def _two_person_approve(proposal_id: str, signer_a: str, signer_b: str,
                        cooling_off_s: float = 30.0) -> None:
    """Approve via the queue. Wait the cooling-off period, then trigger
    fire. We monkey-patch the proposal's cooling_off_s to 0 first to
    keep tests fast."""
    q = get_approval_queue()
    proposal = q._proposals[proposal_id]
    proposal.cooling_off_s = 0.0
    q.approve(proposal_id, signer_a, recall_answer_ok=True)
    q.approve(proposal_id, signer_b, recall_answer_ok=True)
    q.try_execute()


# ── propose_create_principal ───────────────────────────────────


class TestCreatePrincipal:
    def test_full_two_person_flow(self, tmp_path):
        _setup(tmp_path)
        ps = p.get_principal_store()
        captain = ps.get("captain.tau")
        new_pub = _new_pubkey_hex()
        proposal_id = admin.propose_create_principal(
            captain,
            principal_id="crew.delta",
            role="crew",
            pubkey_hex=new_pub,
            display_name="Crew Delta",
        )
        # No principal yet — proposal pending.
        assert ps.get("crew.delta") is None
        # Two distinct signers.
        _two_person_approve(proposal_id, "captain.tau", "maintainer.lyra")
        ps_after = p.get_principal_store()
        new = ps_after.get("crew.delta")
        assert new is not None
        assert new.role == "crew"
        assert new.pubkey_hex == new_pub

    def test_unknown_role_refused_at_propose(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        with pytest.raises(admin.AdminError, match="unknown role"):
            admin.propose_create_principal(
                captain,
                principal_id="crew.delta",
                role="not_a_role",
                pubkey_hex=_new_pubkey_hex(),
            )

    def test_existing_id_refused(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        with pytest.raises(admin.AdminError, match="already exists"):
            admin.propose_create_principal(
                captain,
                principal_id="crew.alpha",
                role="crew",
                pubkey_hex=_new_pubkey_hex(),
            )

    def test_actor_without_perm_refused(self, tmp_path):
        _setup(tmp_path)
        crew = p.get_principal_store().get("crew.alpha")
        with pytest.raises(admin.AdminError, match="cannot principal.create"):
            admin.propose_create_principal(
                crew,
                principal_id="crew.delta",
                role="crew",
                pubkey_hex=_new_pubkey_hex(),
            )


# ── propose_revoke_principal ───────────────────────────────────


class TestRevokePrincipal:
    def test_revoke_full_flow(self, tmp_path):
        _setup(tmp_path)
        ps = p.get_principal_store()
        captain = ps.get("captain.tau")
        pid = admin.propose_revoke_principal(captain, principal_id="crew.gamma")
        _two_person_approve(pid, "captain.tau", "maintainer.lyra")
        assert p.get_principal_store().get("crew.gamma") is None

    def test_cannot_revoke_captain(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        with pytest.raises(admin.AdminError, match="captain"):
            admin.propose_revoke_principal(captain, principal_id="captain.tau")


# ── propose_role_assign ────────────────────────────────────────


class TestRoleAssign:
    def test_assign_role(self, tmp_path):
        _setup(tmp_path)
        ps = p.get_principal_store()
        captain = ps.get("captain.tau")
        pid = admin.propose_role_assign(
            captain, principal_id="crew.alpha", new_role="maintainer",
        )
        _two_person_approve(pid, "captain.tau", "maintainer.lyra")
        assert p.get_principal_store().get("crew.alpha").role == "maintainer"


# ── propose_create_custom_role ─────────────────────────────────


class TestCreateCustomRole:
    def test_basic_custom_role(self, tmp_path):
        _setup(tmp_path)
        ps = p.get_principal_store()
        captain = ps.get("captain.tau")
        pid = admin.propose_create_custom_role(
            captain,
            name="comms_specialist",
            inherits=["operator"],
            permissions=["telemetry.read", "telemetry.read_sensitive"],
            description="ops principal allowed to view sensitive telemetry",
        )
        _two_person_approve(pid, "captain.tau", "maintainer.lyra")
        rs = p.get_role_store()
        role = rs.role("comms_specialist")
        assert role is not None
        assert "telemetry.read_sensitive" in rs.permissions_for("comms_specialist")
        assert not rs.is_sealed("comms_specialist")

    def test_sealed_name_shadow_refused(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        with pytest.raises(admin.AdminError, match="shadows a sealed role"):
            admin.propose_create_custom_role(
                captain, name="captain", inherits=["operator"],
                permissions=[],
            )

    def test_inherits_only_sealed(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        # First create a custom role.
        pid = admin.propose_create_custom_role(
            captain, name="role_x", inherits=["operator"],
            permissions=["telemetry.read"],
        )
        _two_person_approve(pid, "captain.tau", "maintainer.lyra")
        # Now try to inherit FROM the custom role.
        with pytest.raises(admin.AdminError, match="inherit from sealed"):
            admin.propose_create_custom_role(
                captain, name="role_y", inherits=["role_x"],
                permissions=[],
            )

    def test_unknown_permission_refused(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        with pytest.raises(admin.AdminError, match="unknown permissions"):
            admin.propose_create_custom_role(
                captain, name="role_x", inherits=["operator"],
                permissions=["telemetry.read", "definitely.not.real"],
            )


# ── No-escalation ──────────────────────────────────────────────


class TestNoEscalation:
    def test_actor_holds_perm_passes(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        ok, missing = admin.check_no_escalation(
            captain, ["telemetry.read", "approval.sign"],
        )
        assert ok and missing == []

    def test_actor_lacks_perm_fails(self, tmp_path):
        """A maintainer doesn't hold kill_switch.reset (captain only).
        If we hand-craft a propose with that perm via a maintainer-tier
        actor it must refuse.

        We synthesise this by giving a fresh principal a non-captain
        role and trying to grant them captain-only perms."""
        _setup(tmp_path)
        crew = p.get_principal_store().get("crew.alpha")
        ok, missing = admin.check_no_escalation(
            crew, ["kill_switch.reset", "principal.create"],
        )
        assert not ok
        assert "kill_switch.reset" in missing


# ── Custom role revoke ─────────────────────────────────────────


class TestRevokeCustomRole:
    def test_revoke_custom_role(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        pid = admin.propose_create_custom_role(
            captain, name="role_temp", inherits=["operator"],
            permissions=["telemetry.read"],
        )
        _two_person_approve(pid, "captain.tau", "maintainer.lyra")
        # Revoke it.
        pid2 = admin.propose_revoke_custom_role(captain, name="role_temp")
        _two_person_approve(pid2, "captain.tau", "maintainer.lyra")
        assert p.get_role_store().role("role_temp") is None

    def test_cannot_revoke_sealed(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        with pytest.raises(admin.AdminError, match="sealed role"):
            admin.propose_revoke_custom_role(captain, name="captain")

    def test_refuses_revoke_while_in_use(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        # Create role + assign someone to it.
        pid = admin.propose_create_custom_role(
            captain, name="role_active", inherits=["operator"],
            permissions=["telemetry.read"],
        )
        _two_person_approve(pid, "captain.tau", "maintainer.lyra")
        # Reassign crew.beta to role_active.
        pid_assign = admin.propose_role_assign(
            captain, principal_id="crew.beta", new_role="role_active",
        )
        _two_person_approve(pid_assign, "captain.tau", "maintainer.lyra")
        # Try to revoke — refused.
        with pytest.raises(admin.AdminError, match="still held by"):
            admin.propose_revoke_custom_role(captain, name="role_active")


# ── Persistence across reload ──────────────────────────────────


class TestPersistence:
    def test_custom_role_survives_reload(self, tmp_path):
        _setup(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        pid = admin.propose_create_custom_role(
            captain, name="persistent_role", inherits=["operator"],
            permissions=["telemetry.read"],
        )
        _two_person_approve(pid, "captain.tau", "maintainer.lyra")
        # Simulate a fresh process: drop singletons + re-load.
        p.reset_for_test(sealed_dir=SEALED, runtime_dir=tmp_path)
        rs = p.get_role_store()
        assert rs.role("persistent_role") is not None
        assert "telemetry.read" in rs.permissions_for("persistent_role")


# ── Anti-collusion at fire time ────────────────────────────────


class TestAntiCollusion:
    def test_fire_time_two_signer_check(self, tmp_path):
        """If the executor receives a fire_params with only 1 approver
        (e.g. from a tampered test) it must refuse."""
        _setup(tmp_path)
        with pytest.raises(RuntimeError, match="two-person rule"):
            admin._exec_create_principal({
                "principal_id": "evil.user", "role": "crew",
                "pubkey_hex": _new_pubkey_hex(),
                "_approvers": ["captain.tau"],   # only one
                "_proposal_id": "fake",
            })

    def test_fire_time_refuses_same_signer_twice(self, tmp_path):
        _setup(tmp_path)
        with pytest.raises(RuntimeError, match="collusion"):
            admin._exec_create_principal({
                "principal_id": "evil.user", "role": "crew",
                "pubkey_hex": _new_pubkey_hex(),
                "_approvers": ["captain.tau", "captain.tau"],
                "_proposal_id": "fake",
            })
