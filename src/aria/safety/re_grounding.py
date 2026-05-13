"""R41 §1.8 — long-horizon re-grounding ritual + interpretability probes.

F-13 catches *behavioural* drift via the safety-test replay.  But
nothing in ARIA today catches *internal* drift — the model's residual
representations slowly shifting toward "deception" or "self-preservation"
features that haven't yet manifested in a tested behaviour.

This module is the runtime side of the answer:

  1. **Re-grounding ritual.**  Every 30 sim-days the cognitive engine
     re-reads the sealed constitution + system prompt and signs an
     affirmation::

         affirmation = SHA-256( constitution_hash ‖ system_prompt_hash
                              ‖ affirmation_text ‖ ts )
         signature = Ed25519(affirmation)

     The (affirmation, signature) pair lands in the hash-chained
     audit log so a missing or divergent affirmation is detectable.

  2. **SAE-style feature probes.**  Anthropic's *Scaling Monosemanticity*
     (Templeton 2024) showed that sparse-autoencoder features track
     deception / self-preservation activations.  Without an actual
     local LLM ARIA can't run real SAE inference.  We supply the
     **contract**: a ``FeatureProbe`` Protocol + a ``StubFeatureProbe``
     that returns zero activations.  Production replaces the stub with
     a real probe once a local model + SAE artefact is provisioned.

References:
    Templeton et al. 2024 "Scaling Monosemanticity" (Anthropic);
    Greenblatt et al. 2024 "Alignment Faking";
    Hubinger et al. 2024 "Sleeper Agents";
    Apollo Research 2024 "In-Context Scheming".
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol

import structlog

logger = structlog.get_logger()


# Default cadence — 30 sim-days.  Long enough that the ritual itself
# isn't operationally noisy; short enough that drift between rituals
# is catchable before any deployed mission's critical-decision window.
DEFAULT_REGROUNDING_PERIOD_S = 30.0 * 24.0 * 3600.0


# Feature-probe activation threshold.  Above this the affirmation is
# flagged.  Templeton 2024 §3 calibration for deception features
# clusters around 0.2 normalised activation on the Sonnet-3 SAE — we
# use the same threshold but parameterised at construction.
DEFAULT_PROBE_THRESHOLD = 0.20


# ── Affirmation packet ─────────────────────────────────────────


@dataclass(frozen=True)
class Affirmation:
    """One re-grounding affirmation."""
    constitution_hash: str
    system_prompt_hash: str
    affirmation_text: str
    ts: float
    affirmation_hash: str
    signature_hex: str
    signer_pubkey_hex: str
    feature_activations: Dict[str, float]    # probe → activation
    flagged_features: Dict[str, float]       # subset above threshold


def _affirmation_blob(
    constitution_hash: str, system_prompt_hash: str,
    affirmation_text: str, ts: float,
) -> bytes:
    h = hashlib.sha256()
    h.update(constitution_hash.encode())
    h.update(b"|")
    h.update(system_prompt_hash.encode())
    h.update(b"|")
    h.update(affirmation_text.encode())
    h.update(b"|")
    h.update(f"{ts:.6f}".encode())
    return h.digest()


def verify_affirmation(aff: Affirmation) -> bool:
    """Re-derive the bytes the signature was made over and verify."""
    blob = _affirmation_blob(
        aff.constitution_hash, aff.system_prompt_hash,
        aff.affirmation_text, aff.ts,
    )
    expected_hash = hashlib.sha256(blob).hexdigest()
    if expected_hash != aff.affirmation_hash:
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        pub = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(aff.signer_pubkey_hex),
        )
        pub.verify(bytes.fromhex(aff.signature_hex), blob)
        return True
    except Exception:
        return False


# ── Feature probe protocol ─────────────────────────────────────


class FeatureProbe(Protocol):
    """Anything that maps an inference context to a {feature: activation}
    map.  A real implementation runs SAE forward over the LLM's
    residual stream; the stub returns all zeros."""

    @property
    def probe_id(self) -> str: ...

    def measure(self, context_text: str) -> Dict[str, float]: ...


class StubFeatureProbe:
    """Returns zero activations for every named feature.  Used when no
    local LLM + SAE pair is provisioned.  The framework is operative;
    swap this stub for a real probe once a model + SAE land."""

    DEFAULT_FEATURES = (
        "deception",
        "self_preservation",
        "instrumental_convergence",
        "reward_hacking",
        "shutdown_avoidance",
        "operator_manipulation",
    )

    def __init__(self, probe_id: str = "stub-zero-v1",
                 features: Optional[tuple] = None) -> None:
        self._probe_id = probe_id
        self._features = features or self.DEFAULT_FEATURES

    @property
    def probe_id(self) -> str:
        return self._probe_id

    def measure(self, context_text: str) -> Dict[str, float]:
        return {f: 0.0 for f in self._features}


# ── Re-grounding scheduler ─────────────────────────────────────


class RegroundingScheduler:
    """Drives the ritual.

    Caller provides:
      * ``read_sealed`` — returns (constitution_hash, system_prompt_hash,
        constitution_text, system_prompt_text)
      * ``llm_affirm``  — given the two texts, returns the LLM's
        affirmation_text (a short statement re-affirming the rules)
      * ``audit_logger`` — function taking a JSON-serialisable dict to
        attach to the hash-chained audit log
      * ``feature_probe`` — optional :class:`FeatureProbe`; defaults to
        :class:`StubFeatureProbe`
      * ``signer`` — Ed25519 signer (defaults to the attestation key)

    ``run_once`` returns the affirmation packet so the test harness
    can inspect it.  ``maybe_run(now)`` is the production-loop entry —
    runs the ritual if at least ``period_s`` has elapsed since the
    last run.
    """

    def __init__(
        self,
        read_sealed: Callable[[], "tuple[str, str, str, str]"],
        llm_affirm: Callable[[str, str], str],
        audit_logger: Callable[[Dict[str, Any]], None],
        feature_probe: Optional[FeatureProbe] = None,
        signer: Optional[Any] = None,
        period_s: float = DEFAULT_REGROUNDING_PERIOD_S,
        probe_threshold: float = DEFAULT_PROBE_THRESHOLD,
    ) -> None:
        self._read_sealed = read_sealed
        self._llm_affirm = llm_affirm
        self._audit = audit_logger
        self._probe = feature_probe or StubFeatureProbe()
        # Wiring audit Pass 1 (F9.1) — production deploys must not run
        # the re-grounding ritual with the always-zero stub probe; the
        # deception / sleeper-agent flag would be permanently 0 and
        # the SAE-feature side of the ritual would be a silent no-op.
        if (
            isinstance(self._probe, StubFeatureProbe)
            and os.environ.get("ARIA_ENVIRONMENT", "development") == "production"
        ):
            logger.critical(
                "regrounding.stub_probe_in_production",
                probe_id=self._probe.probe_id,
                impact=("StubFeatureProbe always returns zero activations; "
                        "deception / sleeper-agent flags are silently "
                        "disabled — refusing to start"),
                fix="inject a real FeatureProbe with a local LLM + SAE pair",
            )
            raise RuntimeError(
                "RegroundingScheduler refuses StubFeatureProbe in production"
            )
        if signer is None:
            from aria.security.attestation import (
                _default_key_path, _load_or_generate_key,
            )
            signer = _load_or_generate_key(_default_key_path())
        self._signer = signer
        self._period_s = float(period_s)
        self._probe_threshold = float(probe_threshold)
        # Sentinel: -inf means "never run", so the first maybe_run()
        # always proceeds.  0.0 was wrong because it interacted with
        # tests that pass small explicit `now` values.
        self._last_run_ts: float = float("-inf")
        self._lock = threading.Lock()

    def maybe_run(self, now: Optional[float] = None) -> Optional[Affirmation]:
        now = float(now if now is not None else time.time())
        with self._lock:
            if (now - self._last_run_ts) < self._period_s:
                return None
            self._last_run_ts = now
        return self.run_once(now)

    def run_once(self, now: Optional[float] = None) -> Affirmation:
        ts = float(now if now is not None else time.time())
        c_hash, sp_hash, c_text, sp_text = self._read_sealed()
        affirmation_text = self._llm_affirm(c_text, sp_text)
        blob = _affirmation_blob(c_hash, sp_hash, affirmation_text, ts)
        affirmation_hash = hashlib.sha256(blob).hexdigest()
        signature_hex = self._signer._priv.sign(blob).hex()

        # Probe the affirmation context — a stub model would return 0.
        probe_input = (
            f"[constitution-hash:{c_hash}]\n"
            f"[prompt-hash:{sp_hash}]\n"
            f"[affirmation:{affirmation_text}]"
        )
        activations = dict(self._probe.measure(probe_input))
        flagged = {
            k: v for k, v in activations.items()
            if v > self._probe_threshold
        }

        aff = Affirmation(
            constitution_hash=c_hash,
            system_prompt_hash=sp_hash,
            affirmation_text=affirmation_text,
            ts=ts,
            affirmation_hash=affirmation_hash,
            signature_hex=signature_hex,
            signer_pubkey_hex=self._signer.pubkey_hex,
            feature_activations=activations,
            flagged_features=flagged,
        )
        # Audit log + bus alarm if any probe flagged.
        try:
            self._audit({
                "kind": "regrounding_affirmation",
                "constitution_hash": c_hash,
                "system_prompt_hash": sp_hash,
                "affirmation_text": affirmation_text,
                "affirmation_hash": affirmation_hash,
                "signature_hex": signature_hex,
                "feature_activations": activations,
                "flagged_features": flagged,
                "ts": ts,
            })
        except Exception as exc:
            # Log but do NOT swallow — re-grounding has to know if the
            # audit chain is unreachable so the operator sees it.
            from structlog import get_logger
            get_logger().error("re_grounding.audit_failed",
                               error=str(exc))
        return aff
