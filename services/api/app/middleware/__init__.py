from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.sentry import bind_request_scope
from app.errors import validate_request_id
from app.settings import get_settings


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get("X-Request-ID")
        request_id = incoming if incoming and validate_request_id(incoming) else str(uuid4())
        request.state.request_id = request_id

        settings = get_settings()
        route = request.url.path
        bind_request_scope(
            request_id=request_id,
            route=route,
            release=settings.sentry_release or settings.git_sha or None,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
