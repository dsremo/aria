"""LLM backends for the eval harness.

Default backend: the configured LLM CLI (default binary: ``claude``). No API key
needed — the CLI uses whatever auth the local install has (OAuth /
keychain / 3P provider). Subprocess-based, deterministic enough for
benchmarking, easy to swap.

Alternate backend (BYO): the Anthropic SDK direct path, available
when ``ANTHROPIC_API_KEY`` is set. Not used by default.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Sequence


CLAUDE_CLI_BINARY = "claude"
DEFAULT_TIMEOUT_S = 240.0      # 4 min per scenario; the CLI is not fast
DEFAULT_EFFORT = "high"        # we want best-effort answers for benchmarking


@dataclass
class LlmCliBackend:
    """Run prompts through the configured LLM CLI in non-interactive mode.

    The CLI's ``--print`` / ``-p`` flag returns the assistant response
    text and exits. We pass ``--bare`` to skip the developer-machine
    auto-memory + plugin-sync paths, ``--no-session-persistence`` so
    benchmark runs don't pollute the user's resume history, and a
    custom system prompt that frames the LLM as an autonomy-decision
    advisor.
    """

    binary: str = CLAUDE_CLI_BINARY
    timeout_s: float = DEFAULT_TIMEOUT_S
    effort: str = DEFAULT_EFFORT
    extra_args: Sequence[str] = field(default_factory=tuple)
    system_prompt_override: Optional[str] = None

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    @staticmethod
    def default_system_prompt() -> str:
        return (
            "You are evaluating a real-time spacecraft anomaly. You are the "
            "autonomy advisor onboard or in mission control. Read the situation "
            "and constraints carefully, then propose a concrete decision. Cite "
            "the specific items from the constraint list you would use. State "
            "what you would NOT do and why. Be specific about the implementation "
            "(materials, sequence, timing). Avoid generalities. Your answer is "
            "a decision document the operator could act on, not a textbook "
            "summary. Keep the response under 1500 words. Do not invent items "
            "that are not in the constraints list."
        )

    def query(self, user_prompt: str) -> str:
        """Run the CLI with the given user prompt and return stdout text."""
        if not self.is_available():
            raise RuntimeError(
                f"LLM CLI not found on PATH "
                f"(searched for '{self.binary}'). Install via the ARIA dev-env."
            )

        system_prompt = (
            self.system_prompt_override
            if self.system_prompt_override is not None
            else self.default_system_prompt()
        )

        # Note: we deliberately do NOT pass --bare. --bare requires an
        # ANTHROPIC_API_KEY env var, but ARIA's standing instruction is
        # "no API keys; use the LLM CLI's OAuth/keychain auth"
        # (the same auth a developer uses for `claude` interactively).
        cmd = [
            self.binary,
            "--print",
            "--no-session-persistence",
            "--effort", str(self.effort),
            "--append-system-prompt", system_prompt,
            *self.extra_args,
            user_prompt,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"the LLM CLI timed out after {self.timeout_s} s"
            ) from None

        if result.returncode != 0:
            raise RuntimeError(
                f"the LLM CLI exited {result.returncode}: "
                f"stderr={result.stderr.strip()[:500]}"
            )
        text = (result.stdout or "").strip()
        if not text:
            raise RuntimeError(
                "the LLM CLI returned empty stdout"
                f"; stderr={result.stderr.strip()[:200]}"
            )
        return text
