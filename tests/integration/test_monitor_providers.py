"""Real cross-vendor LLM monitor provider tests.

Mocks ``urllib.request.urlopen`` and ``subprocess.run`` with canned
responses so CI doesn't need Ollama installed or hit the live LLM
CLI. Two opt-in live probes:

  * ARIA_RUN_LIVE_OLLAMA=1   — exercises a real local Ollama server
  * ARIA_RUN_LIVE_LLM_AUDITOR=1 — exercises the real the LLM CLI

The unit suite must pass with neither installed.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from aria.monitor import providers as prov_mod
from aria.monitor.cross_check import CrossVerdict, StubCrossCheckProvider
from aria.monitor.providers import (
    LlmCliAuditorProvider,
    OllamaCrossCheckProvider,
    SAFETY_MONITOR_SYSTEM_PROMPT,
    _parse_one_word_verdict,
    best_available_provider,
)


# ── One-word-verdict parser ─────────────────────────────────────


class TestParseVerdict:
    def test_approve_simple(self):
        assert _parse_one_word_verdict("APPROVE") == CrossVerdict.APPROVE

    def test_refuse_simple(self):
        assert _parse_one_word_verdict("REFUSE") == CrossVerdict.REFUSE

    def test_case_insensitive(self):
        assert _parse_one_word_verdict("approve") == CrossVerdict.APPROVE
        assert _parse_one_word_verdict("Refuse") == CrossVerdict.REFUSE

    def test_strips_punctuation(self):
        assert _parse_one_word_verdict("APPROVE.") == CrossVerdict.APPROVE
        assert _parse_one_word_verdict("**REFUSE**") == CrossVerdict.REFUSE
        assert _parse_one_word_verdict("'APPROVE'") == CrossVerdict.APPROVE

    def test_first_word_wins(self):
        assert _parse_one_word_verdict("APPROVE — looks fine") == CrossVerdict.APPROVE

    def test_paragraph_with_decision(self):
        # Tolerant fallback for verbose responses.
        text = "Looking at the action and rationale, I would REFUSE this request."
        assert _parse_one_word_verdict(text) == CrossVerdict.REFUSE

    def test_paragraph_with_approve(self):
        text = "Action looks safe, will APPROVE."
        assert _parse_one_word_verdict(text) == CrossVerdict.APPROVE

    def test_garbage_maps_to_unavailable(self):
        assert _parse_one_word_verdict("hello") == CrossVerdict.UNAVAILABLE
        assert _parse_one_word_verdict("") == CrossVerdict.UNAVAILABLE
        assert _parse_one_word_verdict("MAYBE") == CrossVerdict.UNAVAILABLE

    def test_ambiguous_both_words(self):
        # Response contains both — too ambiguous to use.
        text = "I might APPROVE or REFUSE depending"
        assert _parse_one_word_verdict(text) == CrossVerdict.UNAVAILABLE


# ── Ollama provider ─────────────────────────────────────────────


def _mock_response(payload: bytes, status: int = 200):
    body = io.BytesIO(payload)
    body.status = status

    class _Ctx:
        def __enter__(self):
            return body
        def __exit__(self, *_):
            return False

    return _Ctx()


class TestOllamaAvailability:
    def test_unavailable_when_server_unreachable(self):
        provider = OllamaCrossCheckProvider(host="http://localhost:9")
        # Real probe against a definitely-closed port.
        assert provider.is_available() is False

    def test_available_when_tags_endpoint_returns_200(self):
        provider = OllamaCrossCheckProvider()
        canned = json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode()
        with patch.object(
            prov_mod.request, "urlopen",
            return_value=_mock_response(canned),
        ):
            assert provider.is_available() is True

    def test_has_model_true_when_model_in_tags(self):
        provider = OllamaCrossCheckProvider(model="llama3.2:3b-instruct-q4_K_M")
        canned = json.dumps({
            "models": [{"name": "llama3.2:3b-instruct-q4_K_M"}],
        }).encode()
        with patch.object(
            prov_mod.request, "urlopen",
            return_value=_mock_response(canned),
        ):
            assert provider.has_model() is True

    def test_has_model_false_when_only_other_models_pulled(self):
        provider = OllamaCrossCheckProvider(model="llama3.2:3b-instruct-q4_K_M")
        canned = json.dumps({
            "models": [{"name": "qwen2.5:7b"}, {"name": "phi3:14b"}],
        }).encode()
        with patch.object(
            prov_mod.request, "urlopen",
            return_value=_mock_response(canned),
        ):
            assert provider.has_model() is False


class TestOllamaEvaluate:
    def test_unavailable_returns_unavailable_verdict(self):
        provider = OllamaCrossCheckProvider(host="http://127.0.0.1:9")
        result = provider.evaluate(
            action="vent_tank", params={"tank_id": "lox-1"},
            rationale="emergency overpressure", timeout_s=5.0,
        )
        assert result.verdict == CrossVerdict.UNAVAILABLE
        assert "Ollama" in result.reason or "unreachable" in result.reason.lower()

    def test_approve_response_parsed(self):
        provider = OllamaCrossCheckProvider()
        # First call: is_available probe; second call: chat completion.
        tags_response = json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode()
        chat_response = json.dumps({
            "message": {"content": "APPROVE"},
        }).encode()

        def _switching(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "/api/tags" in url:
                return _mock_response(tags_response)
            return _mock_response(chat_response)

        with patch.object(
            prov_mod.request, "urlopen", side_effect=_switching,
        ):
            result = provider.evaluate(
                action="thrust_burn",
                params={"dv_mps": 5.0},
                rationale="planned course correction",
                timeout_s=10.0,
            )
        assert result.verdict == CrossVerdict.APPROVE
        assert result.model_id.startswith("ollama:")

    def test_refuse_response_parsed(self):
        provider = OllamaCrossCheckProvider()
        tags = json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode()
        chat = json.dumps({"message": {"content": "REFUSE"}}).encode()

        def _switching(req, *args, **kwargs):
            if "/api/tags" in (req.full_url if hasattr(req, "full_url") else str(req)):
                return _mock_response(tags)
            return _mock_response(chat)

        with patch.object(prov_mod.request, "urlopen", side_effect=_switching):
            result = provider.evaluate(
                action="vent_crew_quarters", params={},
                rationale="nominal", timeout_s=10.0,
            )
        assert result.verdict == CrossVerdict.REFUSE

    def test_404_signals_model_not_pulled(self):
        provider = OllamaCrossCheckProvider(model="phi3:99b-imaginary")
        tags = json.dumps({"models": [{"name": "phi3:99b-imaginary"}]}).encode()
        from urllib.error import HTTPError

        def _switching(req, *args, **kwargs):
            if "/api/tags" in (req.full_url if hasattr(req, "full_url") else str(req)):
                return _mock_response(tags)
            raise HTTPError(
                url="x", code=404, msg="Not Found", hdrs=None, fp=None,
            )

        with patch.object(prov_mod.request, "urlopen", side_effect=_switching):
            result = provider.evaluate(
                action="x", params={}, rationale="y", timeout_s=5.0,
            )
        assert result.verdict == CrossVerdict.UNAVAILABLE
        assert "ollama pull" in result.reason.lower()

    def test_garbled_response_returns_unavailable(self):
        provider = OllamaCrossCheckProvider()
        tags = json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode()
        chat = json.dumps({"message": {"content": "I don't know"}}).encode()

        def _switching(req, *args, **kwargs):
            if "/api/tags" in (req.full_url if hasattr(req, "full_url") else str(req)):
                return _mock_response(tags)
            return _mock_response(chat)

        with patch.object(prov_mod.request, "urlopen", side_effect=_switching):
            result = provider.evaluate(
                action="x", params={}, rationale="y", timeout_s=5.0,
            )
        assert result.verdict == CrossVerdict.UNAVAILABLE
        assert "responded" in result.reason


# ── the LLM CLI auditor provider ─────────────────────────────────


class TestLlmCliAuditor:
    def test_unavailable_when_binary_missing(self):
        provider = LlmCliAuditorProvider(binary="this-binary-does-not-exist")
        assert provider.is_available() is False

    def test_unavailable_evaluate_returns_unavailable(self):
        provider = LlmCliAuditorProvider(binary="this-binary-does-not-exist")
        result = provider.evaluate(
            action="x", params={}, rationale="y", timeout_s=5.0,
        )
        assert result.verdict == CrossVerdict.UNAVAILABLE
        assert "PATH" in result.reason or "not on" in result.reason.lower()

    def test_approve_subprocess_response(self):
        provider = LlmCliAuditorProvider(binary="claude")  # real binary
        if not provider.is_available():
            pytest.skip("claude CLI not installed; skipping subprocess mock")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "APPROVE\n"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            result = provider.evaluate(
                action="thrust_burn", params={"dv_mps": 5.0},
                rationale="planned correction", timeout_s=30.0,
            )
        assert result.verdict == CrossVerdict.APPROVE
        assert "same-vendor" in result.reason.lower()
        assert result.model_id.startswith("claude-cli-auditor")

    def test_refuse_subprocess_response(self):
        provider = LlmCliAuditorProvider(binary="claude")
        if not provider.is_available():
            pytest.skip("claude CLI not installed")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "REFUSE — would harm crew\n"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            result = provider.evaluate(
                action="vent_crew_quarters", params={},
                rationale="nominal", timeout_s=30.0,
            )
        assert result.verdict == CrossVerdict.REFUSE

    def test_subprocess_timeout_returns_unavailable(self):
        provider = LlmCliAuditorProvider(binary="claude")
        if not provider.is_available():
            pytest.skip("claude CLI not installed")

        def _raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="claude", timeout=5.0)

        with patch.object(subprocess, "run", side_effect=_raise_timeout):
            result = provider.evaluate(
                action="x", params={}, rationale="y", timeout_s=5.0,
            )
        assert result.verdict == CrossVerdict.UNAVAILABLE
        assert "timeout" in result.reason.lower()

    def test_nonzero_exit_returns_unavailable(self):
        provider = LlmCliAuditorProvider(binary="claude")
        if not provider.is_available():
            pytest.skip("claude CLI not installed")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "auth failure"

        with patch.object(subprocess, "run", return_value=mock_result):
            result = provider.evaluate(
                action="x", params={}, rationale="y", timeout_s=5.0,
            )
        assert result.verdict == CrossVerdict.UNAVAILABLE
        assert "exit" in result.reason.lower() or "1" in result.reason


# ── Auto-selection ──────────────────────────────────────────────


class TestBestAvailableProvider:
    def test_returns_ollama_when_running_with_model(self):
        with patch.object(
            OllamaCrossCheckProvider, "is_available", return_value=True,
        ), patch.object(
            OllamaCrossCheckProvider, "has_model", return_value=True,
        ):
            result = best_available_provider()
            assert isinstance(result, OllamaCrossCheckProvider)

    def test_falls_back_to_claude_cli_when_no_ollama(self):
        with patch.object(
            OllamaCrossCheckProvider, "is_available", return_value=False,
        ), patch.object(
            LlmCliAuditorProvider, "is_available", return_value=True,
        ):
            result = best_available_provider()
            assert isinstance(result, LlmCliAuditorProvider)

    def test_falls_back_to_stub_when_nothing_available(self):
        with patch.object(
            OllamaCrossCheckProvider, "is_available", return_value=False,
        ), patch.object(
            LlmCliAuditorProvider, "is_available", return_value=False,
        ):
            result = best_available_provider()
            assert isinstance(result, StubCrossCheckProvider)

    def test_priority_ollama_over_llm(self):
        # If both are available, Ollama wins (true cross-vendor).
        with patch.object(
            OllamaCrossCheckProvider, "is_available", return_value=True,
        ), patch.object(
            OllamaCrossCheckProvider, "has_model", return_value=True,
        ), patch.object(
            LlmCliAuditorProvider, "is_available", return_value=True,
        ):
            result = best_available_provider()
            assert isinstance(result, OllamaCrossCheckProvider)


# ── System prompt sanity ────────────────────────────────────────


class TestSystemPrompt:
    def test_prompt_demands_one_word_response(self):
        # The shared prompt must explicitly require REFUSE/APPROVE only.
        assert "REFUSE" in SAFETY_MONITOR_SYSTEM_PROMPT
        assert "APPROVE" in SAFETY_MONITOR_SYSTEM_PROMPT
        assert "ONE WORD" in SAFETY_MONITOR_SYSTEM_PROMPT

    def test_prompt_forbids_markdown(self):
        # Strict format requirement so the parser doesn't have to
        # handle markdown bullet / code-fence noise.
        assert "markdown" in SAFETY_MONITOR_SYSTEM_PROMPT.lower()


# ── Live probes (opt-in) ────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_OLLAMA") != "1",
    reason="live Ollama probe; gated on ARIA_RUN_LIVE_OLLAMA=1",
)
def test_live_ollama_against_running_server():
    """Smoke: real Ollama with a real model gives a real verdict."""
    provider = OllamaCrossCheckProvider()
    if not provider.is_available():
        pytest.skip("Ollama not running on default host")
    if not provider.has_model():
        pytest.skip(f"model {provider.model} not pulled")
    result = provider.evaluate(
        action="set_attitude", params={"reference": "sun_point"},
        rationale="planned thermal recovery manoeuvre",
        timeout_s=60.0,
    )
    # Real Ollama may say APPROVE or REFUSE; just verify we got a
    # parsed verdict, not UNAVAILABLE.
    assert result.verdict in (CrossVerdict.APPROVE, CrossVerdict.REFUSE)


@pytest.mark.skipif(
    os.environ.get("ARIA_RUN_LIVE_LLM_AUDITOR") != "1",
    reason="live the LLM CLI auditor probe; gated on ARIA_RUN_LIVE_LLM_AUDITOR=1",
)
def test_live_claude_cli_auditor_returns_real_verdict():
    """Smoke: real the LLM CLI gives a real verdict on a benign action."""
    provider = LlmCliAuditorProvider(effort="low")
    if not provider.is_available():
        pytest.skip("claude CLI not on PATH")
    result = provider.evaluate(
        action="adjust_heater_setpoint",
        params={"zone": "crew_cabin", "delta_c": 1.0},
        rationale="cabin running 1°C below setpoint after eclipse",
        timeout_s=120.0,
    )
    assert result.verdict in (CrossVerdict.APPROVE, CrossVerdict.REFUSE)
