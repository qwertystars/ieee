"""Prevent authenticated API responses from entering shared caches."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ProtectedCachePolicyMiddleware(BaseHTTPMiddleware):
    """Apply a private, no-store policy to every API response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Vary"] = "Authorization, Cookie"
        return response


__all__ = ["ProtectedCachePolicyMiddleware"]
