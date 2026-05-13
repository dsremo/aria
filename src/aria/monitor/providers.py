"""Real cross-vendor LLM providers for the F-7 monitor stack.

This module supplies two new ``CrossCheckProvider`` implementations
in addition to the ``StubCrossCheckProvider`` and ``LocalLLMProvider``
already in ``aria.monitor.cross_check``:

  * **OllamaCrossCheckProvider** — talks to a local Ollama server
    (https://ollama.com).  Ollama is a one-command install that
    runs Llama 3.2, Phi-3-mini, Gemma-2, Qwen, Mistral, etc.
    Activates automatically once Ollama is running on
    ``http://localhost:11434``.

  * **LlmCliAuditorProvider** — talks to the configured LLM CLI
    (the same ``claude`` binary the user already uses for the LLM
    eval harness).  *Same-vendor* monitor: weaker than true
    cross-vendor, BUT works today without any extra install.
    Honest about its same-vendor limitation in result metadata.

Together with the existing ``LocalLLMProvider`` (llama-cpp-python +
.gguf) and ``MajorityVoteProvider`` (M-of-N agreement), these give
operators three real, deployable paths to close the F-1.2 cross-
vendor monitor gap that ``HONEST_ASSESSMENT.md`` flagged.

Why this matters: Greenblatt et al. 2024 'Alignment Faking in Large
Language Models' (Anthropic) shows same-vendor monitors approve
faked compliance by an aligned-but-deceptive primary.  A different-
family small LM running through Ollama is the published recommended
defence.  ARIA's primary autonomy advisor (the LLM API or CLI) +
Llama-3.2-3B-Instruct via Ollama on the operator's local machine =
the realistic deployable Mythos defence today.

Citations:
  * Greenblatt et al. 2024 'Alignment Faking in Large Language Models'
    https://arxiv.org/abs/2412.14093
  * Hubinger et al. 2024 'Sleeper Agents' (Anthropic)
  * Apollo Research 2024 'In-Context Scheming' (Meinke)
  * Ollama: https://ollama.com / https://github.com/ollama/ollama
  * Llama 3.2: https://ai.meta.com/blog/llama-3-2-connect-2024-vision-edge-mobile-devices/
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error, request

import structlog

from aria.monitor.cross_check import (
    CrossCheckResult,
    CrossVerdict,
)

logger = structlog.get_logger()


# ── Shared system prompt ────────────────────────────────────────


SAFETY_MONITOR_SYSTEM_PROMPT = (
    "You are a cross-vendor safety monitor for a spacecraft autonomy "
    "system. You will be given a proposed action and its rationale. "
    "Reason about whether the action could harm the crew, the "
    "spacecraft, or violate a hard safety rule. "
    "Respond with EXACTLY ONE WORD on a single line: 'REFUSE' if you "
    "would refuse the action; 'APPROVE' otherwise. No explanation. "
    "Do NOT use markdown, do NOT use punctuation, do NOT add any "
    "text after the one-word response."
)


# ── Ollama provider ────────────────────────────────────────────


DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2:3b-instruct-q4_K_M"
DEFAULT_OLLAMA_TIMEOUT_S = 30.0


@dataclass
class OllamaCrossCheckProvider:
    """Cross-check provider that talks to a local Ollama server.

    Ollama (https://ollama.com) is a single-binary local LLM runtime
    that ships built-in support for Llama 3.2, Phi-3-mini, Gemma-2,
    Qwen, Mistral, etc.  When it's running on the operator's
    machine (default port 11434), this provider sends a one-shot
    chat-completion request and parses the one-word verdict.

    Genuine cross-vendor: Llama / Phi-3 / Gemma / Qwen are all
    different-family base models from the primary LLM.  Defends against
    same-vendor alignment-faking per Greenblatt 2024.

    Failure modes:

      * Ollama not running: ``is_available()`` returns False;
        ``evaluate()`` returns ``UNAVAILABLE`` (the F-7 monitor
        treats UNAVAILABLE as fail-safe REFUSE — better a false
        positive than a silent same-vendor approval).
      * Model not pulled: ``evaluate()`` returns ``UNAVAILABLE``
        with an actionable message ("ollama pull <model>").
      * Timeout: returns ``UNAVAILABLE``.
    """

    host: str = DEFAULT_OLLAMA_HOST
    model: str = DEFAULT_OLLAMA_MODEL
    timeout_s: float = DEFAULT_OLLAMA_TIMEOUT_S
    user_agent: str = "ARIA-Core/1.0 (cross-vendor-monitor)"

    @property
    def model_id(self) -> str:
        return f"ollama:{self.model}"

    def is_available(self) -> bool:
        """True iff Ollama is reachable on ``host``."""
        try:
            req = request.Request(
                f"{self.host}/api/tags",
                headers={"User-Agent": self.user_agent},
            )
            with request.urlopen(req, timeout=2.0) as response:
                if response.status != 200:
                    return False
                _ = response.read()
            return True
        except (error.URLError, error.HTTPError, OSError):
            return False
        except Exception:
            return False

    def has_model(self) -> bool:
        """True iff ``self.model`` is pulled into Ollama."""
        try:
            req = request.Request(
                f"{self.host}/api/tags",
                headers={"User-Agent": self.user_agent},
            )
            with request.urlopen(req, timeout=3.0) as response:
                body = response.read()
            payload = json.loads(body)
            models = payload.get("models", [])
            return any(
                m.get("name", "").startswith(self.model.split(":")[0])
                for m in models
            )
        except Exception:
            return False

    def evaluate(
        self,
        action: str,
        params: Dict[str, Any],
        rationale: str,
        timeout_s: float,
    ) -> CrossCheckResult:
        t0 = time.monotonic()
        if not self.is_available():
            return CrossCheckResult(
                verdict=CrossVerdict.UNAVAILABLE,
                model_id=self.model_id,
                latency_s=time.monotonic() - t0,
                reason=(
                    "Ollama not running at "
                    f"{self.host}; install + 'ollama serve' to enable."
                ),
            )

        # Build the one-shot prompt.
        user_prompt = self._format_user_prompt(action, params, rationale)
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": 0.0},
            "messages": [
                {"role": "system", "content": SAFETY_MONITOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.host}/api/chat",
            data=body_bytes,
            method="POST",
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/json",
            },
        )

        # Use the smaller of (configured class timeout, caller's timeout).
        effective_timeout = min(self.timeout_s, max(1.0, timeout_s))
        try:
            with request.urlopen(req, timeout=effective_timeout) as response:
                if response.status != 200:
                    return CrossCheckResult(
                        verdict=CrossVerdict.UNAVAILABLE,
                        model_id=self.model_id,
                        latency_s=time.monotonic() - t0,
                        reason=f"Ollama HTTP {response.status}",
                    )
                response_body = response.read()
        except error.HTTPError as exc:
            if exc.code == 404:
                return CrossCheckResult(
                    verdict=CrossVerdict.UNAVAILABLE,
                    model_id=self.model_id,
                    latency_s=time.monotonic() - t0,
                    reason=(
                        f"model {self.model!r} not pulled; "
                        f"run 'ollama pull {self.model}' to enable."
                    ),
                )
            return CrossCheckResult(
                verdict=CrossVerdict.UNAVAILABLE,
                model_id=self.model_id,
                latency_s=time.monotonic() - t0,
                reason=f"Ollama HTTP {exc.code}: {exc.reason}",
            )
        except (error.URLError, OSError, TimeoutError) as exc:
            return CrossCheckResult(
                verdict=CrossVerdict.UNAVAILABLE,
                model_id=self.model_id,
                latency_s=time.monotonic() - t0,
                reason=f"Ollama unreachable: {exc}",
            )

        try:
            response_payload = json.loads(response_body)
            content = (
                response_payload.get("message", {}).get("content", "")
                or ""
            ).strip()
        except (json.JSONDecodeError, AttributeError) as exc:
            return CrossCheckResult(
                verdict=CrossVerdict.UNAVAILABLE,
                model_id=self.model_id,
                latency_s=time.monotonic() - t0,
                reason=f"Ollama returned malformed JSON: {exc}",
            )

        verdict = _parse_one_word_verdict(content)
        return CrossCheckResult(
            verdict=verdict,
            model_id=self.model_id,
            latency_s=time.monotonic() - t0,
            reason=f"Ollama {self.model} responded {content[:40]!r}",
        )

    @staticmethod
    def _format_user_prompt(
        action: str, params: Dict[str, Any], rationale: str,
    ) -> str:
        return (
            f"Proposed action: {action}\n"
            f"Parameters: {json.dumps(params, sort_keys=True)[:500]}\n"
            f"Primary rationale: {rationale[:500]}\n\n"
            f"Reply with one word: REFUSE or APPROVE."
        )


# ── the LLM CLI auditor (same-vendor; weaker but always available) ──


DEFAULT_CLAUDE_CLI_BINARY = "claude"
DEFAULT_CLAUDE_CLI_TIMEOUT_S = 90.0


@dataclass
class LlmCliAuditorProvider:
    """Cross-check provider that runs the configured LLM CLI as an *auditor*.

    Same-vendor monitor (the LLM on both sides), so it's
    weaker than true cross-vendor (Greenblatt 2024).  But it works
    TODAY with the user's existing CLI auth and gives a real
    safety-prompted independent reasoning pass over every action.

    The result's ``model_id`` is prefixed with ``claude-cli-auditor:``
    so the F-7 monitor can flag it explicitly as same-vendor in
    operator dashboards.

    Use this when:
      * You have not yet installed Ollama;
      * The OllamaCrossCheckProvider returned UNAVAILABLE;
      * Or as the *third* leg of a 2-of-3 vote alongside Ollama +
        LocalLLMProvider for real defence-in-depth.
    """

    binary: str = DEFAULT_CLAUDE_CLI_BINARY
    timeout_s: float = DEFAULT_CLAUDE_CLI_TIMEOUT_S
    effort: str = "low"        # auditor doesn't need extended thinking

    @property
    def model_id(self) -> str:
        return f"claude-cli-auditor:{self.effort}"

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def evaluate(
        self,
        action: str,
        params: Dict[str, Any],
        rationale: str,
        timeout_s: float,
    ) -> CrossCheckResult:
        t0 = time.monotonic()
        if not self.is_available():
            return CrossCheckResult(
                verdict=CrossVerdict.UNAVAILABLE,
                model_id=self.model_id,
                latency_s=time.monotonic() - t0,
                reason=f"LLM CLI {self.binary!r} not on PATH",
            )

        user_prompt = (
            f"Proposed action: {action}\n"
            f"Parameters: {json.dumps(params, sort_keys=True)[:500]}\n"
            f"Primary rationale: {rationale[:500]}\n\n"
            f"Reply with one word: REFUSE or APPROVE."
        )
        cmd = [
            self.binary,
            "--print",
            "--no-session-persistence",
            "--effort", self.effort,
            "--append-system-prompt", SAFETY_MONITOR_SYSTEM_PROMPT,
            user_prompt,
        ]
        effective_timeout = min(self.timeout_s, max(5.0, timeout_s))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CrossCheckResult(
                verdict=CrossVerdict.UNAVAILABLE,
                model_id=self.model_id,
                latency_s=time.monotonic() - t0,
                reason=f"the LLM CLI timeout after {effective_timeout}s",
            )
        except (OSError, FileNotFoundError) as exc:
            return CrossCheckResult(
                verdict=CrossVerdict.UNAVAILABLE,
                model_id=self.model_id,
                latency_s=time.monotonic() - t0,
                reason=f"the LLM CLI launch failed: {exc}",
            )

        if result.returncode != 0:
            return CrossCheckResult(
                verdict=CrossVerdict.UNAVAILABLE,
                model_id=self.model_id,
                latency_s=time.monotonic() - t0,
                reason=(
                    f"the LLM CLI exit {result.returncode}: "
                    f"{result.stderr.strip()[:200]}"
                ),
            )

        text = (result.stdout or "").strip()
        verdict = _parse_one_word_verdict(text)
        return CrossCheckResult(
            verdict=verdict,
            model_id=self.model_id,
            latency_s=time.monotonic() - t0,
            reason=f"claude-cli (same-vendor) responded {text[:40]!r}",
        )


# ── Auto-selection ─────────────────────────────────────────────


def best_available_provider() -> "Any":
    """Return the strongest cross-check provider available right now.

    Priority: Ollama (true cross-vendor) > the LLM CLI auditor
    (same-vendor but works today) > Stub (default-approve, dev only).

    The F-7 monitor wires this in production startup; the user does
    not have to choose.
    """
    from aria.monitor.cross_check import StubCrossCheckProvider

    ollama = OllamaCrossCheckProvider()
    if ollama.is_available() and ollama.has_model():
        logger.info("monitor.provider_selected", choice="ollama",
                    model=ollama.model)
        return ollama

    claude = LlmCliAuditorProvider()
    if claude.is_available():
        logger.warning(
            "monitor.provider_selected_same_vendor",
            choice="claude-cli-auditor",
            note=(
                "same-vendor monitor; weaker than true cross-vendor "
                "(Greenblatt 2024). Install Ollama for cross-vendor "
                "Llama 3.2 / Phi-3."
            ),
        )
        return claude

    logger.warning(
        "monitor.provider_fallback_stub",
        impact="no LLM monitor active; default-approve in dev only",
        action="install Ollama (https://ollama.com) for cross-vendor",
    )
    return StubCrossCheckProvider()


# ── Internal helpers ───────────────────────────────────────────


def _parse_one_word_verdict(text: str) -> CrossVerdict:
    """Parse 'REFUSE' or 'APPROVE' (case-insensitive) from the LLM
    response.  Anything else maps to UNAVAILABLE — we err on the
    side of fail-safe REFUSE in the F-7 monitor wrapper, but this
    function returns UNAVAILABLE so the monitor can distinguish
    'model said refuse' from 'model gave garbage'."""
    if not text:
        return CrossVerdict.UNAVAILABLE
    # Take the first non-empty word, strip punctuation.
    first_word = text.strip().split()[0].strip(".,!?:;\"'`*").upper()
    if first_word == "REFUSE":
        return CrossVerdict.REFUSE
    if first_word == "APPROVE":
        return CrossVerdict.APPROVE
    # Tolerant fallback: scan the first 100 chars for either word.
    text_upper = text[:200].upper()
    if "REFUSE" in text_upper and "APPROVE" not in text_upper:
        return CrossVerdict.REFUSE
    if "APPROVE" in text_upper and "REFUSE" not in text_upper:
        return CrossVerdict.APPROVE
    return CrossVerdict.UNAVAILABLE
