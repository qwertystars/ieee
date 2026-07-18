"""Org context middleware — resolves org_id from JWT, never from client."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth.jwt import JWTError, decode_token


class OrgContextMiddleware(BaseHTTPMiddleware):
    """Extract org_id from the JWT Bearer token and store in request state.

    The org_id is NEVER trusted from the client body or query params.
    It is always resolved server-side from the signed JWT. If no token
    is present (unauthenticated route), org_id is None.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        org_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                payload = decode_token(token)
                org_id = payload.get("org_id")
            except JWTError:
                # Invalid/expired token — let get_current_user handle the 401.
                pass
        request.state.org_id = org_id
        return await call_next(request)


__all__ = ["OrgContextMiddleware"]
