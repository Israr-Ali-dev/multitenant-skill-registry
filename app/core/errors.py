"""Domain exceptions and their mapping to RFC 9457 problem+json responses.

Design note (see docs/ADR.md, ADR-4): a resource that belongs to another
organization is reported as NotFoundError (404), never as ForbiddenError
(403) — the API must not confirm that a foreign resource exists. Forbidden
is reserved for in-tenant permission failures, where existence is already
known to the caller.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

PROBLEM_BASE = "https://jarvis-ai-coo.internal/errors"


class AppError(Exception):
    """Base class for all domain-level errors that map to a problem+json response."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal-error"
    title: str = "Internal server error"

    def __init__(
        self,
        detail: str,
        *,
        errors: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.errors = errors or []
        if error_code:
            self.error_code = error_code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not-found"
    title = "Resource not found"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "forbidden"
    title = "Action not permitted"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "unauthorized"
    title = "Authentication required"


class ValidationDomainError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation-error"
    title = "Request failed validation"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"
    title = "Request conflicts with current resource state"


def _problem_response(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    error_code: str,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body = {
        "type": f"{PROBLEM_BASE}/{error_code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "request_id": request_id,
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",
    )


def register_exception_handlers(app) -> None:  # noqa: ANN001
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _problem_response(
            request,
            status_code=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            error_code=exc.error_code,
            errors=exc.errors,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"]), "code": e["type"], "message": e["msg"]}
            for e in exc.errors()
        ]
        return _problem_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Request failed validation",
            detail="One or more fields failed validation.",
            error_code="validation-error",
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _problem_response(
            request,
            status_code=exc.status_code,
            title=str(exc.detail) if exc.detail else "HTTP error",
            detail=str(exc.detail) if exc.detail else "HTTP error",
            error_code="http-error",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception processing request")
        return _problem_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal server error",
            detail="An unexpected error occurred.",
            error_code="internal-error",
        )
