"""R32 Phase 4 — failsafe layer hardening tests.

Covers:
  * kill_switch.physical_key_reset Ed25519 signature verification
  * safe_dispatch / safe_dispatch_check with principal-derived trust tier
  * principal-aware audit + downgrade for agent vs human callers
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aria.security import principals as p


REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "sealed"
DEV_KEYS = json.loads(
    (REPO / "tests" / "fixtures" / "dev_keys.json").read_text(),
)


def _privkey(name: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(DEV_KEYS[name]["priv_seed_hex"]),
    )


# ── F-17 kill switch — Ed25519 signature on physical_key_reset ─────


class TestKillSwitchSigVerify:
    def setup_method(self):
        from aria.safety.kill_switch import reset_for_test
        reset_for_test()
        # Need the principal store loaded so the kill switch can read
        # the ship_root pubkey.
        p.reset_for_test(sealed_dir=SEALED)

    def test_reset_with_valid_sig_succeeds(self):
        from aria.safety.kill_switch import get_kill_switch
        ks = get_kill_switch()
        ks.assert_kill("hw_pin_4", "e-stop")
        # Sign the canonical reset payload with the ship-HSM private key.
        payload = f"kill_reset|{ks.asserted_at}".encode()
        sig = _privkey("ship_root").sign(payload).hex()
        assert ks.physical_key_reset(sig) is True
        assert ks.is_asserted() is False

    def test_reset_with_bad_sig_refused(self):
        from aria.safety.kill_switch import get_kill_switch
        ks = get_kill_switch()
        ks.assert_kill("hw_pin_4", "e-stop")
        # Sign with the wrong key (captain key) — must fail.
        payload = f"kill_reset|{ks.asserted_at}".encode()
        sig = _privkey("captain.tau").sign(payload).hex()
        assert ks.physical_key_reset(sig) is False
        assert ks.is_asserted() is True

    def test_reset_with_empty_sig_refused(self):
        from aria.safety.kill_switch import get_kill_switch
        ks = get_kill_switch()
        ks.assert_kill("hw_pin_4", "e-stop")
        assert ks.physical_key_reset("") is False
        assert ks.is_asserted() is True

    def test_reset_with_malformed_sig_refused(self):
        from aria.safety.kill_switch import get_kill_switch
        ks = get_kill_switch()
        ks.assert_kill("hw_pin_4", "e-stop")
        assert ks.physical_key_reset("not-hex-zzz") is False
        assert ks.is_asserted() is True

    def test_legacy_verify_false_path(self):
        """The verify=False back-compat path lets pre-R32 tests pass
        without supplying a real signature. Production callers MUST
        leave verify=True."""
        from aria.safety.kill_switch import get_kill_switch
        ks = get_kill_switch()
        ks.assert_kill("hw_pin_4", "e-stop")
        assert ks.physical_key_reset("anything", verify=False) is True
        assert ks.is_asserted() is False


# ── safe_dispatch — principal-derived trust tier ────────────────


class TestSafeDispatchPrincipal:
    def setup_method(self):
        from aria.cognitive.constitution import reset_for_test as reset_cs
        from aria.safety.kill_switch import reset_for_test as reset_ks
        from aria.safety.approval_queue import reset_for_test as reset_aq
        reset_cs()
        reset_ks()
        reset_aq()
        p.reset_for_test(sealed_dir=SEALED)

    def test_agent_principal_downgrades_tier(self):
        """When a Principal.agent() is passed, the constitution sees
        LOCAL_SENSOR (not OPERATOR) and refuses safety-critical actions.

        Concretely: vent_crew_quarters is in forbidden_actions so it's
        always DENIED — but the *reason* differs by tier. With
        agent-tier, even gated actions get DENIED for tier-too-low."""
        from aria.cognitive.safe_dispatch import (
            safe_dispatch_check, DispatchKind,
        )
        agent = p.Principal.agent("propulsion")
        outcome = safe_dispatch_check(
            agent_name="propulsion", action="throttle_engine",
            params={"fraction": 0.5},
            principal=agent,
        )
        # throttle_engine is gated. With tier 2 (LOCAL_SENSOR) <
        # min_tier_for_safety_critical=3, the constitution returns DENY.
        assert outcome.kind is DispatchKind.DENIED
        assert "tier" in outcome.reason.lower()

    def test_captain_principal_can_propose_gated(self):
        """A captain principal hits OPERATOR tier so a gated action
        becomes GATED (not DENIED) — the proper queue-and-approve flow."""
        from aria.cognitive.safe_dispatch import (
            safe_dispatch_check, DispatchKind,
        )
        ps = p.get_principal_store()
        captain = ps.get("captain.tau")
        outcome = safe_dispatch_check(
            agent_name="bridge", action="throttle_engine",
            params={"fraction": 0.5},
            principal=captain,
        )
        assert outcome.kind is DispatchKind.GATED
        assert outcome.proposal_id

    def test_no_principal_uses_explicit_trust_tier(self):
        """Backwards-compat path: callers that don't pass principal
        keep their explicit trust_tier argument honoured."""
        from aria.cognitive.constitution import TrustTier
        from aria.cognitive.safe_dispatch import (
            safe_dispatch_check, DispatchKind,
        )
        outcome = safe_dispatch_check(
            agent_name="bridge", action="throttle_engine",
            params={"fraction": 0.5},
            trust_tier=TrustTier.OPERATOR,
        )
        assert outcome.kind is DispatchKind.GATED


# ── F-6 capability-token RBAC ──────────────────────────────────


class TestCapabilityTokenRBAC:
    def setup_method(self):
        from aria.cognitive.capability_token import reset_for_test
        reset_for_test()
        p.reset_for_test(sealed_dir=SEALED)

    def test_agent_cannot_mint_consent_token(self):
        """Hard cap: agent role refused at CONSENT or above."""
        from aria.cognitive.capability_token import (
            get_token_minter, ScopeMismatch,
        )
        from aria.core.types import AuthorityLevel
        agent = p.Principal.agent("planner")
        with pytest.raises(ScopeMismatch, match="hard cap"):
            get_token_minter().mint(
                "vent_tank", {"tank_id": "lox-1"},
                tool_authority=AuthorityLevel.CONSENT,
                requesting_principal=agent,
            )

    def test_agent_cannot_mint_captain_only(self):
        from aria.cognitive.capability_token import (
            get_token_minter, ScopeMismatch,
        )
        from aria.core.types import AuthorityLevel
        agent = p.Principal.agent("planner")
        with pytest.raises(ScopeMismatch):
            get_token_minter().mint(
                "captain_override", {},
                tool_authority=AuthorityLevel.CAPTAIN_ONLY,
                requesting_principal=agent,
            )

    def test_agent_can_mint_routine(self):
        """Below CONSENT, the role permission table decides.

        Wiring audit Pass 3 F1.14 (sealed-manifest update) granted the
        ``agent`` role ``mint_token.{sensor_only,routine,supervised}``
        per its ``authority_ceiling="SUPERVISED"`` in roles.v1.toml.
        Agents now mint ROUTINE tokens with a real Principal — the
        AI-self-elevation firewall still refuses CONSENT-or-higher
        (covered by ``test_agent_blocked_at_consent`` above), but
        ROUTINE is its valid tier.
        """
        from aria.cognitive.capability_token import get_token_minter
        from aria.core.types import AuthorityLevel
        agent = p.Principal.agent("planner")
        encoded = get_token_minter().mint(
            "eps_get_power_budget", {"include_history": False},
            tool_authority=AuthorityLevel.ROUTINE,
            requesting_principal=agent,
        )
        assert encoded
        assert "agent:planner" in encoded

    def test_captain_can_mint_captain_only(self):
        from aria.cognitive.capability_token import get_token_minter
        from aria.core.types import AuthorityLevel
        captain = p.get_principal_store().get("captain.tau")
        tok = get_token_minter().mint(
            "captain_override", {},
            tool_authority=AuthorityLevel.CAPTAIN_ONLY,
            requesting_principal=captain,
        )
        assert isinstance(tok, str) and len(tok) > 0

    def test_crew_can_mint_consent(self):
        """Crew holds mint_token.consent; can mint at CONSENT tier."""
        from aria.cognitive.capability_token import get_token_minter
        from aria.core.types import AuthorityLevel
        crew = p.get_principal_store().get("crew.alpha")
        tok = get_token_minter().mint(
            "schedule_maneuver", {"phase": "burn"},
            tool_authority=AuthorityLevel.CONSENT,
            requesting_principal=crew,
        )
        assert isinstance(tok, str)

    def test_crew_cannot_mint_captain_only(self):
        from aria.cognitive.capability_token import (
            get_token_minter, ScopeMismatch,
        )
        from aria.core.types import AuthorityLevel
        crew = p.get_principal_store().get("crew.alpha")
        with pytest.raises(ScopeMismatch):
            get_token_minter().mint(
                "captain_override", {},
                tool_authority=AuthorityLevel.CAPTAIN_ONLY,
                requesting_principal=crew,
            )

    def test_token_issuer_stamped_with_principal(self):
        """When a principal is supplied, the token's issuer field
        carries 'role:principal_id' so audit can attribute exactly."""
        import json as _j
        from aria.cognitive.capability_token import (
            get_token_minter, CapabilityToken,
        )
        from aria.core.types import AuthorityLevel
        captain = p.get_principal_store().get("captain.tau")
        tok = get_token_minter().mint(
            "captain_override", {},
            tool_authority=AuthorityLevel.CAPTAIN_ONLY,
            requesting_principal=captain,
        )
        decoded = CapabilityToken.decode(tok)
        assert decoded.issuer == "captain:captain.tau"

    def test_back_compat_no_principal_no_check(self):
        """Pre-R32 callers (no principal arg) still work; no RBAC
        applied in that case."""
        from aria.cognitive.capability_token import get_token_minter
        tok = get_token_minter().mint(
            "any_tool", {"x": 1},
        )
        assert isinstance(tok, str)
