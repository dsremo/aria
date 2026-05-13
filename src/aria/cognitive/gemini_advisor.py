"""Secondary cloud-LLM advisor — fallback when ANTHROPIC_API_KEY is unset.

Uses the `google-genai` SDK as a runtime dependency; the client reads
`GEMINI_API_KEY` from env. The advisor rotates across a ranked list of
free-tier model ids (override with `ARIA_GEMINI_MODELS` — comma-separated)
so a 429 / 503 on one model does not starve the advisor: the offending id
is cooled down and the next one answers.

Ordering prioritises the fastest lite tiers (sub-second first response
observed 2026-04-24) with heavier fallbacks behind them. Probes on this
date showed the lite tier returning clean JSON in ~500 ms; preview/thinking
tiers spent ~480 thinking tokens before the JSON body and are last resort.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Ranked rotation. The default list is read from the ARIA_GEMINI_MODELS
# env var (comma-separated) — lite tiers first because they have the
# highest RPM quota on the free tier and finish in under a second on
# ARIA-sized prompts. If unset, the rotation is empty and the advisor
# falls through to the rule-based path.
_MODELS: tuple[str, ...] = tuple(
    m.strip() for m in os.environ.get("ARIA_GEMINI_MODELS", "").split(",")
    if m.strip()
)

# Per-call wall-clock cap. Advisor is a UI poller (30 s cadence) so a
# 6 s ceiling keeps the UI responsive while leaving room for the full
# rotation to be attempted inside a single request. Value is a product
# decision — no published source.
_CALL_TIMEOUT_S = 6.0   # ESTIMATE — UX budget, not a published number

# When a model errors with 429 / 503 we park it for this long before
# re-trying. Matches the "Please retry in ~58 s" guidance Google returns
# on free-tier quota exhaustion (observed 2026-04-24).
_COOLDOWN_S = 65.0      # Google free-tier retry hint (~58 s) + margin

# Ceiling on response tokens. Thinking-tier preview models reserve hundreds
# of tokens for thought summaries before the JSON body — 1024 leaves room
# for the body while keeping cost predictable.
_MAX_OUTPUT_TOKENS = 1024  # empirical: thinking models burn ~500 tok before JSON

_SYSTEM_PROMPT = (
    "You are ARIA, the onboard decision AI of a generation ship. "
    "Given a live telemetry snapshot, emit STRICT JSON with these keys: "
    "severity (one of NOMINAL, WARNING, CRITICAL, EMERGENCY), "
    "summary (one short sentence, <= 140 chars), "
    "recommendation (multi-line action plan, each line prefixed with \"• \"), "
    "citations (list of snapshot keys, dot-notated, that justify the call). "
    "Be conservative. Cite exact numbers from the snapshot. "
    "Emit the bare JSON object — no markdown fences, no prose outside JSON."
)


@dataclass
class _ModelState:
    name: str
    cooldown_until: float = 0.0
    last_error: str = ""
    total_calls: int = 0
    total_failures: int = 0

    def available(self, now: float) -> bool:
        return now >= self.cooldown_until


@dataclass
class GeminiAdvisor:
    """Thin wrapper around google-genai with model rotation + cooldowns."""

    api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", "").strip())
    models: tuple[str, ...] = _MODELS
    _state: dict[str, _ModelState] = field(default_factory=dict)
    _client: Any = None

    def __post_init__(self) -> None:
        for m in self.models:
            self._state[m] = _ModelState(name=m)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _client_or_none(self) -> Any:
        """Lazy client. Returns None if SDK missing or key absent."""
        if self._client is not None:
            return self._client
        if not self.api_key:
            return None
        try:
            from google import genai  # type: ignore
        except ImportError:
            log.warning("google-genai SDK not installed; Gemini advisor disabled")
            return None
        # genai.Client honours GEMINI_API_KEY from env; pass explicit for clarity.
        self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _pick_models(self) -> list[str]:
        now = time.monotonic()
        live = [m for m in self.models if self._state[m].available(now)]
        if not live:  # everyone is cooling down — try anyway, least-recently-failed first
            live = sorted(self.models, key=lambda m: self._state[m].cooldown_until)
        return live

    async def decide(
        self,
        snapshot: dict[str, Any],
        focus: str = "",
        timeout_s: float = _CALL_TIMEOUT_S,
    ) -> dict[str, Any] | None:
        """Ask Gemini for a decision. Returns dict on success, None on total failure.

        The returned dict always has: severity, summary, recommendation, citations,
        source="gemini", model (which model answered), latency_ms.
        """
        client = self._client_or_none()
        if client is None:
            return None

        from google.genai import types  # type: ignore

        user_prompt = (
            (f"Focus: {focus}\n\n" if focus else "")
            + "Snapshot:\n" + json.dumps(snapshot, default=str)
        )
        cfg = types.GenerateContentConfig(
            temperature=0.2,         # low — want consistent engineering answers
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            system_instruction=_SYSTEM_PROMPT,
        )

        t0 = time.monotonic()
        last_err = ""
        for model in self._pick_models():
            st = self._state[model]
            st.total_calls += 1
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model,
                        contents=[user_prompt],
                        config=cfg,
                    ),
                    timeout=timeout_s,
                )
                text = (resp.text or "").strip()
                if not text:
                    raise RuntimeError("empty response body")
                data = json.loads(text)
                if not isinstance(data, dict) or "severity" not in data:
                    raise ValueError(f"malformed payload keys={list(data) if isinstance(data, dict) else type(data)}")
                data["source"] = "gemini"
                data["model"] = model
                data["latency_ms"] = int((time.monotonic() - t0) * 1000)
                return data
            except Exception as exc:  # noqa: BLE001 — rotate on any failure
                msg = f"{type(exc).__name__}: {str(exc)[:140]}"
                last_err = msg
                st.total_failures += 1
                st.last_error = msg
                # Quota / availability errors deserve a cooldown; other
                # failures (JSON parse, transient network) we simply skip.
                low = msg.lower()
                if ("429" in low or "503" in low
                        or "resource_exhausted" in low
                        or "unavailable" in low
                        or "quota" in low):
                    st.cooldown_until = time.monotonic() + _COOLDOWN_S
                log.warning("gemini advisor: %s failed — %s", model, msg)
                continue

        log.error("gemini advisor: all models failed (last=%s)", last_err)
        return None


_singleton: GeminiAdvisor | None = None


def get_gemini_advisor() -> GeminiAdvisor:
    """Process-wide singleton so cooldown state persists across polls."""
    global _singleton
    if _singleton is None:
        _singleton = GeminiAdvisor()
    return _singleton
