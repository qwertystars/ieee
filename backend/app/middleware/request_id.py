"""Request ID middleware — generates UUID4, sets X-Request-Id header."""

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.lib.logging_config import bind_context

HEADER_NAME = "X-Request-Id"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a UUID request ID to every request and response.

    If the incoming request has an X-Request-Id header, it is reused.
    Otherwise a new UUID4 is generated. The value is stored in
    request.state.request_id for downstream use and bound to the
    logging context var so all log records include it.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(HEADER_NAME) or str(uuid.uuid4())
        request.state.request_id = request_id
        bind_context(request_id=request_id)
        response = await call_next(request)
        response.headers[HEADER_NAME] = request_id
        return response


__all__ = ["HEADER_NAME", "RequestIDMiddleware"]
