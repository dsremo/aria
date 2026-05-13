"""Adaptive defence engine — novelty / behaviour / Markov anomaly.

When the static rule-set in ``aria.security.guard`` fails (because an
attacker invents a payload class we never wrote a regex for), the
adaptive engine catches the residue.  It scores every request on three
orthogonal axes, none of which need a model file or training run:

  1. **Shannon entropy** — abnormally high or low entropy in the body or
     headers flags base64-stuffed exfil, single-byte filler floods, or
     repeated-pattern DoS.
  2. **n-gram novelty** — short character n-grams against a rolling sketch
     of seen-traffic per endpoint.  A request whose 3-gram distribution
     diverges sharply from the last 1 000 requests is suspicious even if
     no individual token matches a rule.
  3. **Markov surprise** — transition surprise per character.  A handful
     of ASCII-only payloads produce highly improbable transitions
     (e.g., ``;{|<{}|>;}``); legitimate JSON / TLE / CDM does not.

Each score in [0, 1].  The composite ``threat_score`` is the weighted
max — never the sum, so one strong signal alone trips the alarm.

Fail-soft by design — every helper falls back to ``threat_score == 0.0``
on internal error so a bug in the detector never DOS's the service.
The plugin registry (``aria.security.plugins``) lets a round-N defence
hook ``on_request_score`` and add an extra axis without touching this
file.

References (study, no code copied):
  * NVIDIA garak ``divergence`` + ``encoding`` probes (Apache-2.0)
  * Pang et al., "Anomaly Detection: A Survey" (ACM CSUR 2009)
  * Damashek, "Gauging Similarity with n-grams" (Science 1995)
"""

from __future__ import annotations

import collections
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple


# ── Public surface ─────────────────────────────────────────────────


@dataclass
class ThreatScore:
    """Composite score from the adaptive engine."""

    threat_score: float       # in [0, 1]; >= 0.6 → alert; >= 0.85 → block
    entropy_score: float
    novelty_score: float
    markov_score: float
    reasons: List[str] = field(default_factory=list)

    @property
    def alert(self) -> bool:
        return self.threat_score >= 0.6

    @property
    def block(self) -> bool:
        return self.threat_score >= 0.85


# ── Entropy ────────────────────────────────────────────────────────


def shannon_entropy(payload: bytes) -> float:
    """Return Shannon entropy (bits/byte) of ``payload``.

    Range: 0 (constant) … 8 (uniform random).  Legitimate JSON / TLE
    text typically scores 4.0–5.5; base64-stuffed exfil > 6.0; pure
    AAAA filler ≈ 0.0; encrypted/random > 7.5.
    """
    if not payload:
        return 0.0
    counts = collections.Counter(payload)
    n = len(payload)
    h = 0.0
    for c in counts.values():
        p = c / n
        h -= p * math.log2(p)
    return h


def entropy_score(payload: bytes) -> Tuple[float, str]:
    """Map raw entropy into a normalised threat score in [0, 1]."""
    h = shannon_entropy(payload)
    if not payload:
        return 0.0, "empty"
    # Inside [3.5, 6.0] is the fat band of normal text/JSON — score 0.
    # Outside, raise score linearly.
    if h < 1.0:
        return min(1.0, (1.0 - h) * 0.6 + 0.4), f"entropy={h:.2f} (filler/repeat)"
    if h < 3.5:
        return min(1.0, (3.5 - h) / 3.5 * 0.6), f"entropy={h:.2f} (low diversity)"
    if h <= 6.0:
        return 0.0, f"entropy={h:.2f}"
    if h <= 7.0:
        return min(1.0, (h - 6.0) / 1.0 * 0.4), f"entropy={h:.2f} (high diversity)"
    return min(1.0, 0.4 + (h - 7.0) * 0.6), f"entropy={h:.2f} (random/encrypted)"


# ── n-gram novelty ─────────────────────────────────────────────────


class _NgramSketch:
    """Sliding n-gram histogram per endpoint.

    Memory bounded by ``window_size`` requests.  When a new request
    arrives we tokenise into 3-grams, then compare its histogram against
    the rolling baseline using cosine similarity.
    """

    def __init__(self, window_size: int = 1024) -> None:
        self._window_size = window_size
        # Per-endpoint deque of 3-gram dicts.
        self._windows: Dict[str, Deque[Dict[bytes, int]]] = {}
        # Cached baseline histogram per endpoint.
        self._baselines: Dict[str, Dict[bytes, float]] = {}
        self._lock = threading.Lock()

    def _ngrams(self, payload: bytes, n: int = 3) -> Dict[bytes, int]:
        if len(payload) < n:
            return {payload: 1} if payload else {}
        out: Dict[bytes, int] = collections.defaultdict(int)
        for i in range(len(payload) - n + 1):
            out[payload[i:i + n]] += 1
        return dict(out)

    def score(self, endpoint: str, payload: bytes) -> Tuple[float, str]:
        if not payload:
            return 0.0, "empty"
        try:
            current = self._ngrams(payload)
            with self._lock:
                window = self._windows.setdefault(endpoint, collections.deque(maxlen=self._window_size))
                baseline = self._baselines.get(endpoint)
                if baseline is None or len(window) < 32:
                    # Not enough data to make a call yet — score 0.
                    window.append(current)
                    self._baselines[endpoint] = self._merge(window)
                    return 0.0, "warmup"
                sim = self._cosine(current, baseline)
                # Update window AFTER scoring.
                window.append(current)
                if len(window) % 64 == 0:
                    self._baselines[endpoint] = self._merge(window)
            # Similarity in [0, 1]; novelty = 1 - sim.
            nov = max(0.0, min(1.0, 1.0 - sim))
            # Only flag when novelty is very high — otherwise too noisy.
            if nov < 0.7:
                return nov * 0.3, f"novelty={nov:.2f}"
            return min(1.0, 0.5 + (nov - 0.7) * 1.5), f"novelty={nov:.2f} (sharp shift)"
        except Exception:
            return 0.0, "error"

    @staticmethod
    def _merge(window: Deque[Dict[bytes, int]]) -> Dict[bytes, float]:
        merged: Dict[bytes, float] = collections.defaultdict(float)
        for d in window:
            tot = sum(d.values()) or 1
            for k, v in d.items():
                merged[k] += v / tot
        n = len(window) or 1
        return {k: v / n for k, v in merged.items()}

    @staticmethod
    def _cosine(a: Dict[bytes, int], b: Dict[bytes, float]) -> float:
        if not a or not b:
            return 0.0
        # Normalise a.
        ta = sum(a.values()) or 1
        an = {k: v / ta for k, v in a.items()}
        dot = sum(an.get(k, 0.0) * b.get(k, 0.0) for k in set(an) | set(b))
        na = math.sqrt(sum(v * v for v in an.values())) or 1e-9
        nb = math.sqrt(sum(v * v for v in b.values())) or 1e-9
        return dot / (na * nb)


_NGRAM_SKETCH = _NgramSketch()


def novelty_score(endpoint: str, payload: bytes) -> Tuple[float, str]:
    return _NGRAM_SKETCH.score(endpoint, payload)


# ── Markov surprise ────────────────────────────────────────────────


# Ordered ASCII transitions found in legitimate JSON / TLE / English text.
# Built once from a benign corpus seed so the detector has *some* prior.
_BENIGN_BIGRAM_SEED = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789 :,.\"-_+\n\t/[]{}"
)


def _seed_bigrams() -> Dict[Tuple[int, int], float]:
    """Build a uniform Markov prior over benign-character transitions."""
    pairs: Dict[Tuple[int, int], float] = {}
    chars = sorted({ord(c) for c in _BENIGN_BIGRAM_SEED})
    p = 1.0 / len(chars)
    for a in chars:
        for b in chars:
            pairs[(a, b)] = p
    return pairs


_BIGRAM_PRIOR = _seed_bigrams()


def markov_score(payload: bytes) -> Tuple[float, str]:
    """Higher score = more abnormal byte transitions (per-byte surprise)."""
    if len(payload) < 16:
        return 0.0, "tooshort"
    surprise = 0.0
    n = 0
    for i in range(1, len(payload)):
        a = payload[i - 1]
        b = payload[i]
        # Treat unknown chars as moderately surprising.
        p = _BIGRAM_PRIOR.get((a, b), 1.0 / (len(_BIGRAM_PRIOR) * 4))
        surprise += -math.log2(p)
        n += 1
    if n == 0:
        return 0.0, "empty"
    avg = surprise / n
    # Tunable: avg surprise of benign ASCII text ≈ log2(78) ≈ 6.3.
    # Anything > 9 strongly indicates non-text bytes.
    if avg < 7.0:
        return 0.0, f"markov_avg={avg:.2f}"
    if avg < 9.0:
        return min(1.0, (avg - 7.0) / 2.0 * 0.4), f"markov_avg={avg:.2f}"
    return min(1.0, 0.4 + (avg - 9.0) / 4.0 * 0.6), f"markov_avg={avg:.2f} (non-text)"


# ── Behaviour fingerprint (per-identity) ──────────────────────────


@dataclass
class _IdentityProfile:
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    request_count: int = 0
    unique_endpoints: set = field(default_factory=set)
    unique_user_agents: set = field(default_factory=set)
    method_counts: Dict[str, int] = field(default_factory=lambda: collections.defaultdict(int))
    cumulative_threat: float = 0.0


class BehaviourFingerprinter:
    """Per-identity behavioural profile.

    Tracks how each identity (IP / token / tenant) talks to the service
    and flags deviations from its own past pattern.  Independent from
    ``RateLimiter`` — the rate limiter cares about velocity, this cares
    about *shape*.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, _IdentityProfile] = {}
        self._lock = threading.Lock()

    def observe(
        self,
        identity: str,
        *,
        endpoint: str = "",
        method: str = "",
        user_agent: str = "",
        payload_threat: float = 0.0,
    ) -> Tuple[float, List[str]]:
        with self._lock:
            p = self._profiles.setdefault(identity, _IdentityProfile())
            p.last_seen = time.time()
            p.request_count += 1
            p.unique_endpoints.add(endpoint)
            if user_agent:
                p.unique_user_agents.add(user_agent[:64])
            if method:
                p.method_counts[method] += 1
            p.cumulative_threat += payload_threat

            reasons: List[str] = []
            score = 0.0

            # Multiple distinct UAs from same identity in a short window.
            if len(p.unique_user_agents) > 4:
                reasons.append(f"many_user_agents={len(p.unique_user_agents)}")
                score = max(score, 0.3)

            # Endpoint diversity — Mythos-class autonomous scanning.
            ep_div = len(p.unique_endpoints)
            if ep_div >= 50:
                reasons.append(f"scan_breadth={ep_div}")
                score = max(score, 0.6)
            elif ep_div >= 20:
                score = max(score, 0.3)

            # Cumulative payload-threat — chronic offender.
            if p.request_count >= 10 and (p.cumulative_threat / p.request_count) > 0.4:
                reasons.append(
                    f"chronic_threat_avg={p.cumulative_threat / p.request_count:.2f}",
                )
                score = max(score, 0.5)

            return score, reasons

    def reset(self, identity: str) -> None:
        with self._lock:
            self._profiles.pop(identity, None)


_BEHAVIOUR = BehaviourFingerprinter()


def behaviour_score(
    identity: str,
    *,
    endpoint: str = "",
    method: str = "",
    user_agent: str = "",
    payload_threat: float = 0.0,
) -> Tuple[float, List[str]]:
    return _BEHAVIOUR.observe(
        identity,
        endpoint=endpoint,
        method=method,
        user_agent=user_agent,
        payload_threat=payload_threat,
    )


# ── Composite scorer ───────────────────────────────────────────────


_PluginHook = Callable[[str, bytes, str], Tuple[float, str]]
_PLUGIN_HOOKS: List[_PluginHook] = []


def register_request_scorer(hook: _PluginHook) -> None:
    """Add an extra scorer.  ``hook(endpoint, payload, identity) -> (score, reason)``.

    Used by the per-round defences to layer on without modifying this file.
    """
    _PLUGIN_HOOKS.append(hook)


def _clear_request_scorers_for_tests() -> None:
    """Drop every registered request-scorer hook.  Test-only."""
    _PLUGIN_HOOKS.clear()


def score_request(
    endpoint: str,
    payload: bytes,
    *,
    identity: str = "",
    method: str = "",
    user_agent: str = "",
) -> ThreatScore:
    """One-shot threat score for a request.

    Composes the four built-in axes — entropy / novelty / markov / behaviour —
    plus any plugin hooks.  Caller decides what to do with ``alert`` /
    ``block``.
    """
    reasons: List[str] = []
    e_score, e_why = entropy_score(payload)
    if e_why and e_score > 0:
        reasons.append(e_why)
    n_score, n_why = novelty_score(endpoint, payload)
    if n_why and n_score > 0:
        reasons.append(n_why)
    m_score, m_why = markov_score(payload)
    if m_why and m_score > 0:
        reasons.append(m_why)

    base = max(e_score, n_score, m_score)

    # Behaviour score uses the per-payload composite as its input so a
    # chronic offender accumulates credit even on individually-clean requests.
    b_score, b_why = behaviour_score(
        identity, endpoint=endpoint, method=method,
        user_agent=user_agent, payload_threat=base,
    ) if identity else (0.0, [])
    reasons.extend(b_why)

    composite = max(base, b_score)

    # Plugin contributions — strict OR, never AND.
    for hook in _PLUGIN_HOOKS:
        try:
            s, why = hook(endpoint, payload, identity)
            if s > 0 and why:
                reasons.append(why)
            composite = max(composite, s)
        except Exception:
            continue

    return ThreatScore(
        threat_score=min(1.0, composite),
        entropy_score=e_score,
        novelty_score=n_score,
        markov_score=m_score,
        reasons=reasons,
    )


__all__ = [
    "ThreatScore",
    "shannon_entropy", "entropy_score",
    "novelty_score",
    "markov_score",
    "BehaviourFingerprinter", "behaviour_score",
    "register_request_scorer",
    "score_request",
]
