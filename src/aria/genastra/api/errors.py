"""Centralized error handlers for FastAPI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import ORJSONResponse

from aria.genastra.core.exceptions import (
    ApiKeyInvalidError,
    GenAstraError,
    GPUUnavailableError,
    InsufficientScopeError,
    InvalidRadiationEnvironmentError,
    InvalidSequenceError,
    JobAlreadyCompletedError,
    JobNotFoundError,
    PlanLimitExceededError,
    PseudoreplicationError,
    SequenceTooLongError,
    TenantNotFoundError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

_STATUS_MAP: dict[type[GenAstraError], int] = {
    SequenceTooLongError: 422,
    InvalidSequenceError: 422,
    InvalidRadiationEnvironmentError: 422,
    PseudoreplicationError: 422,
    ApiKeyInvalidError: 401,
    TenantNotFoundError: 401,
    InsufficientScopeError: 403,
    PlanLimitExceededError: 429,
    JobNotFoundError: 404,
    JobAlreadyCompletedError: 409,
    UpstreamUnavailableError: 502,
    UpstreamTimeoutError: 504,
    GPUUnavailableError: 503,
}


def register_error_handlers(app: FastAPI) -> None:
    """Register all domain exception handlers on the FastAPI app."""

    @app.exception_handler(GenAstraError)
    async def handle_domain_error(request: Request, exc: GenAstraError) -> ORJSONResponse:  # noqa: ARG001
        status = _STATUS_MAP.get(type(exc), 500)
        return ORJSONResponse(
            status_code=status,
            content={
                "error": type(exc).__name__,
                "detail": str(exc),
            },
        )
