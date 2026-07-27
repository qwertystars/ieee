"""Org context middleware — resolves org_id from JWT, never from client."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth.jwt import JWTError, decode_token
from app.lib.logging_config import bind_context


class OrgContextMiddleware(BaseHTTPMiddleware):
    """Extract org_id from the JWT Bearer token and store in request state.

    The org_id is NEVER trusted from the client body or query params.
    It is always resolved server-side from the signed JWT. If no token
    is present (unauthenticated route), org_id is None. The value is
    also bound to the logging context var for structured log correlation.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        org_id: str | None = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                payload = decode_token(token)
                org_id = payload.get("org_id")  # type: ignore[assignment]
            except JWTError:
                # Invalid/expired token — let get_current_user handle the 401.
                pass
        request.state.org_id = org_id
        bind_context(org_id=org_id)
        return await call_next(request)


__all__ = ["OrgContextMiddleware"]
