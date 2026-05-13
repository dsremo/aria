"""Domain exceptions for GenAstra."""

from __future__ import annotations


class GenAstraError(Exception):
    """Base exception for all GenAstra errors."""


# ── Validation ─────────────────────────────────────────────────────

class SequenceTooLongError(GenAstraError):
    """Protein sequence exceeds the GPU memory limit."""

    def __init__(self, length: int, max_length: int) -> None:
        self.length = length
        self.max_length = max_length
        super().__init__(
            f"Sequence length {length} exceeds maximum {max_length} residues. "
            f"ESMFold requires O(L²) GPU memory; sequences above {max_length} "
            f"will cause out-of-memory on A10G (24 GB)."
        )


class InvalidSequenceError(GenAstraError):
    """Protein sequence contains invalid characters."""

    def __init__(self, invalid_chars: set[str]) -> None:
        self.invalid_chars = invalid_chars
        super().__init__(f"Invalid amino acid characters: {invalid_chars}")


class InvalidRadiationEnvironmentError(GenAstraError):
    """Radiation environment parameters are physically invalid."""


# ── Upstream ───────────────────────────────────────────────────────

class UpstreamUnavailableError(GenAstraError):
    """External API is unavailable (circuit breaker open)."""

    def __init__(self, service: str) -> None:
        self.service = service
        super().__init__(f"Upstream service '{service}' is unavailable (circuit breaker open)")


class UpstreamTimeoutError(GenAstraError):
    """External API call timed out."""

    def __init__(self, service: str, timeout_s: float) -> None:
        self.service = service
        self.timeout_s = timeout_s
        super().__init__(f"Upstream service '{service}' timed out after {timeout_s}s")


# ── Tenant / Auth ──────────────────────────────────────────────────

class TenantNotFoundError(GenAstraError):
    """Tenant does not exist."""


class ApiKeyInvalidError(GenAstraError):
    """API key is invalid, expired, or revoked."""


class PlanLimitExceededError(GenAstraError):
    """Tenant has exceeded their plan's usage limit."""

    def __init__(self, resource: str, limit: int, current: int) -> None:
        self.resource = resource
        self.limit = limit
        self.current = current
        super().__init__(f"Plan limit exceeded for {resource}: {current}/{limit}")


class InsufficientScopeError(GenAstraError):
    """API key lacks the required scope for this operation."""


# ── Jobs ───────────────────────────────────────────────────────────

class JobNotFoundError(GenAstraError):
    """Job does not exist or belongs to a different tenant."""


class JobAlreadyCompletedError(GenAstraError):
    """Cannot cancel a completed or failed job."""


# ── Science ────────────────────────────────────────────────────────

class PseudoreplicationError(GenAstraError):
    """DESeq2 sample independence assumption violated.

    Spaceflight experiments often pool biological replicates from the same
    organism pool. This is pseudoreplication if not handled correctly.
    """


class InsufficientSamplesError(GenAstraError):
    """Not enough samples per condition for statistical analysis."""

    def __init__(self, condition: str, count: int, minimum: int) -> None:
        super().__init__(
            f"Condition '{condition}' has {count} samples, minimum required is {minimum}"
        )


class GPUUnavailableError(GenAstraError):
    """GPU worker is not available for inference."""
