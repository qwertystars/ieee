"""Global error handler — returns {error: {code, message, request_id}}."""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.error_handler")


def _request_id(request: Request) -> str:
    """Get request_id from state, or 'unknown' if not set."""
    return getattr(request.state, "request_id", "unknown")


def _error_body(code: str, message: str, request_id: str) -> dict:
    """Build the standard error response body."""
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        rid = _request_id(request)
        code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            422: "validation_error",
            429: "rate_limited",
        }
        code = code_map.get(exc.status_code, f"error_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, message, rid),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        rid = _request_id(request)
        return JSONResponse(
            status_code=422,
            content=_error_body(
                "validation_error", "Request validation failed", rid
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        rid = _request_id(request)
        logger.exception("Unhandled exception [request_id=%s]: %s", rid, exc)
        return JSONResponse(
            status_code=500,
            content=_error_body(
                "internal_error", "An internal server error occurred", rid
            ),
        )


__all__ = ["register_error_handlers"]
