"""R32 Phase 1 — principal model + RBAC tests.

Covers:
  * sealed identity files load + verify
  * role inheritance closure
  * permission inheritance via the lattice
  * authorize() decision matrix (allow + deny paths)
  * principal-store delta log: append, hash chain, replay tamper detection
  * synthetic principals (anonymous, system, agent, tamper)
  * duress flag downgrades all permissions to telemetry.read
  * agent role hard cap (cannot mint CONSENT+ tokens)
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from aria.security import principals as p


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"


def _fresh_runtime(tmp_path: Path) -> Path:
    d = tmp_path / "runtime"
    d.mkdir()
    return d


def _reset(tmp_path: Path) -> None:
    p.reset_for_test(sealed_dir=SEALED, runtime_dir=_fresh_runtime(tmp_path))


# ── sealed file load ───────────────────────────────────────────


class TestSealedLoad:
    def test_role_store_loads(self, tmp_path):
        _reset(tmp_path)
        rs = p.get_role_store()
        names = {r.name for r in rs.all_roles()}
        assert {"captain", "crew", "maintainer", "operator", "ground",
                "reader", "agent", "system", "anonymous", "tamper"} <= names

    def test_principal_store_loads(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        roster = {pr.principal_id: pr.role for pr in ps.all()}
        assert roster["captain.tau"] == "captain"
        assert roster["crew.alpha"] == "crew"
        assert roster["maintainer.lyra"] == "maintainer"
        assert roster["ground.mcc"] == "ground"

    def test_pinned_keys_load(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        # 64-char hex Ed25519 pubkeys.
        assert len(ps.ground_pubkey_hex()) == 64
        assert len(ps.ship_root_pubkey_hex()) == 64


# ── role closure + permission inheritance ──────────────────────


class TestRoleClosure:
    def test_captain_inherits_crew_perms(self, tmp_path):
        _reset(tmp_path)
        rs = p.get_role_store()
        # crew holds approval.sign; captain inherits crew → captain holds it.
        assert rs.has_permission("crew", "approval.sign")
        assert rs.has_permission("captain", "approval.sign")

    def test_captain_inherits_maintainer_perms(self, tmp_path):
        _reset(tmp_path)
        rs = p.get_role_store()
        assert rs.has_permission("maintainer", "sealed_prompt.flash")
        assert rs.has_permission("captain", "sealed_prompt.flash")

    def test_operator_does_not_inherit_captain(self, tmp_path):
        _reset(tmp_path)
        rs = p.get_role_store()
        assert not rs.has_permission("operator", "principal.create")
        assert not rs.has_permission("operator", "kill_switch.reset")

    def test_anonymous_holds_only_login(self, tmp_path):
        _reset(tmp_path)
        rs = p.get_role_store()
        perms = rs.permissions_for("anonymous")
        assert "auth.session.create" in perms
        assert "approval.sign" not in perms
        assert "telemetry.read" not in perms

    def test_agent_role_does_not_inherit_human(self, tmp_path):
        _reset(tmp_path)
        rs = p.get_role_store()
        assert not rs.has_permission("agent", "approval.sign")
        assert not rs.has_permission("agent", "mint_token.consent")
        assert not rs.has_permission("agent", "principal.create")

    def test_authority_ceilings(self, tmp_path):
        _reset(tmp_path)
        rs = p.get_role_store()
        assert rs.authority_ceiling("captain") == p.AuthorityCeiling.CAPTAIN_ONLY
        assert rs.authority_ceiling("crew") == p.AuthorityCeiling.ADVISORY
        assert rs.authority_ceiling("agent") == p.AuthorityCeiling.SUPERVISED
        assert rs.authority_ceiling("anonymous") == p.AuthorityCeiling.SENSOR_ONLY


# ── authorize() ─────────────────────────────────────────────────


class TestAuthorize:
    def test_anonymous_can_login(self, tmp_path):
        _reset(tmp_path)
        d = p.authorize(p.Principal.anonymous(), "auth.session.create")
        assert d.allow

    def test_anonymous_cannot_sign(self, tmp_path):
        _reset(tmp_path)
        d = p.authorize(p.Principal.anonymous(), "approval.sign")
        assert not d.allow

    def test_captain_can_reset_kill_switch(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        captain = ps.get("captain.tau")
        assert captain is not None
        d = p.authorize(captain, "kill_switch.reset")
        assert d.allow

    def test_crew_cannot_reset_kill_switch(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        crew = ps.get("crew.alpha")
        d = p.authorize(crew, "kill_switch.reset")
        assert not d.allow

    def test_maintainer_can_flash_sealed(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        m = ps.get("maintainer.lyra")
        d = p.authorize(m, "sealed_prompt.flash")
        assert d.allow

    def test_crew_cannot_flash_sealed(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        c = ps.get("crew.beta")
        d = p.authorize(c, "sealed_prompt.flash")
        assert not d.allow

    def test_unknown_permission_denied(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        captain = ps.get("captain.tau")
        d = p.authorize(captain, "definitely.not.a.real.perm")
        assert not d.allow

    def test_tamper_principal_denied(self, tmp_path):
        _reset(tmp_path)
        d = p.authorize(p.Principal.tamper("forged sig"), "telemetry.read")
        assert not d.allow

    def test_null_principal_denied(self, tmp_path):
        _reset(tmp_path)
        d = p.authorize(None, "telemetry.read")  # type: ignore[arg-type]
        assert not d.allow

    def test_agent_cannot_mint_consent_tokens(self, tmp_path):
        """Hardest invariant: agent role must NEVER hold
        mint_token.consent / mint_token.advisory / mint_token.captain_only.
        Defends T-V-1 and the AI-self-elevation chain (W-2)."""
        _reset(tmp_path)
        agent = p.Principal.agent("planner")
        for perm in ("mint_token.consent", "mint_token.advisory",
                     "mint_token.captain_only", "approval.sign"):
            d = p.authorize(agent, perm)
            assert not d.allow, f"agent should not hold {perm}"


# ── duress downgrade ───────────────────────────────────────────


class TestDuress:
    def test_duress_session_can_only_read_telemetry(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        c = ps.get("crew.alpha")
        # Synthetic duress copy — same identity, duress flag set.
        coerced = p.Principal(
            principal_id=c.principal_id, role=c.role,
            pubkey_hex=c.pubkey_hex, display_name=c.display_name,
            created_at=c.created_at, expires_at=c.expires_at,
            duress=True,
        )
        # Read telemetry: still allowed.
        assert p.authorize(coerced, "telemetry.read").allow
        # Everything else is denied.
        assert not p.authorize(coerced, "approval.sign").allow
        assert not p.authorize(coerced, "kill_switch.assert").allow


# ── delta log + chain ─────────────────────────────────────────


class TestDeltaLog:
    def test_append_revoke_delta(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        actor = ps.get("captain.tau")
        co = ps.get("maintainer.lyra")
        rec = ps.append_delta(
            "revoke", "crew.gamma", {},
            actor=actor, co_signer=co, proposal_id="prop_test_1",
        )
        assert rec.seq == 0
        assert rec.prev_hash == "0" * 64
        assert len(rec.hash) == 64
        # Now revoked principal should disappear.
        assert ps.get("crew.gamma") is None
        # Head hash advances.
        assert ps.head_hash() == rec.hash

    def test_anti_collusion_actor_eq_signer_rejected(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        actor = ps.get("captain.tau")
        with pytest.raises(ValueError):
            ps.append_delta(
                "revoke", "crew.beta", {},
                actor=actor, co_signer=actor, proposal_id="x",
            )

    def test_chain_persists_across_reload(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        actor = ps.get("captain.tau")
        co = ps.get("maintainer.orion")
        ps.append_delta("revoke", "crew.alpha", {},
                        actor=actor, co_signer=co, proposal_id="prop_42")
        # Reload from disk.
        # NOTE: re-use the same runtime dir.
        rt = ps._runtime_dir
        p.reset_for_test(sealed_dir=SEALED, runtime_dir=rt)
        ps2 = p.get_principal_store()
        assert ps2.get("crew.alpha") is None
        assert ps2.get("crew.beta").role == "crew"

    def test_tampered_delta_breaks_chain(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        actor = ps.get("captain.tau")
        co = ps.get("maintainer.lyra")
        ps.append_delta("revoke", "crew.gamma", {},
                        actor=actor, co_signer=co, proposal_id="prop_x")
        # Tamper the delta file: change the principal_id but keep the hash.
        rt = ps._runtime_dir
        delta_path = rt / "principals.delta.jsonl"
        text = delta_path.read_text()
        d = json.loads(text.strip())
        d["principal_id"] = "captain.tau"  # malicious — try to revoke captain
        delta_path.write_text(json.dumps(d) + "\n")
        # Reload should refuse.
        p.reset_for_test(sealed_dir=SEALED, runtime_dir=rt)
        with pytest.raises(ValueError):
            p.get_principal_store().load()

    def test_unknown_op_rejected_at_append(self, tmp_path):
        _reset(tmp_path)
        ps = p.get_principal_store()
        actor = ps.get("captain.tau")
        co = ps.get("maintainer.lyra")
        with pytest.raises(ValueError):
            ps.append_delta("nuke_everything", "crew.alpha", {},
                            actor=actor, co_signer=co, proposal_id="evil")


# ── trust tier helpers ────────────────────────────────────────


class TestTierHelpers:
    def test_captain_tier(self, tmp_path):
        _reset(tmp_path)
        captain = p.get_principal_store().get("captain.tau")
        assert p.trust_tier_for(captain) == p.TrustTier.OPERATOR
        assert p.authority_ceiling_for(captain) == p.AuthorityCeiling.CAPTAIN_ONLY

    def test_anonymous_tier(self, tmp_path):
        _reset(tmp_path)
        a = p.Principal.anonymous()
        assert p.trust_tier_for(a) == p.TrustTier.THIRD_PARTY_CONTENT
        assert p.authority_ceiling_for(a) == p.AuthorityCeiling.SENSOR_ONLY

    def test_agent_tier_hard_capped(self, tmp_path):
        _reset(tmp_path)
        a = p.Principal.agent("planner")
        assert p.trust_tier_for(a) == p.TrustTier.LOCAL_SENSOR
        # The agent's authority ceiling stops at SUPERVISED — never CONSENT+.
        rank = p.authority_rank(p.authority_ceiling_for(a))
        assert rank < p.authority_rank(p.AuthorityCeiling.CONSENT)
