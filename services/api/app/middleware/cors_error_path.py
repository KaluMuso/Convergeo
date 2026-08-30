"""Guarantee CORS headers on responses CORSMiddleware never sees.

Starlette always prepends its own `ServerErrorMiddleware` *outside every
user-added middleware* (`Starlette.build_middleware_stack()`), and installs a
handler registered for the bare `Exception` type there rather than on the
inner `ExceptionMiddleware`. `app.main.create_app()` registers exactly such a
handler (`unhandled_exception_handler`, for `Exception`), so any exception not
caught by a more specific handler (`AppError` / `RequestValidationError` /
`StarletteHTTPException` — all handled by the inner `ExceptionMiddleware`, so
those responses flow back through `CORSMiddleware` normally) produces a
response built and sent by `ServerErrorMiddleware` directly, bypassing
`CORSMiddleware`'s header injection entirely.

To a browser this looks identical to a CORS rejection — no
Access-Control-Allow-Origin header at all — even though the origin is one the
API actually allows and the request has nothing to do with CORS policy. This
was the confirmed mechanism behind staging E2E run #55's misleading
"blocked by CORS" failures on `/cart/items` (and the same class of bug for
any other unhandled exception in a staging/production-CORS-scoped route,
including the bump_rate_counter/`/discovery/home` failure from the same run).

`CorsErrorPathMiddleware` is a raw ASGI wrapper applied *outside* the fully
built Starlette app (in `app.main`, around the module-level `app` object
`uvicorn` actually serves — not inside `create_app()`, so every test that
calls `create_app()` directly keeps getting the unwrapped FastAPI instance
unchanged). Sitting outside means it also wraps `ServerErrorMiddleware`, so
it sees every response, including ones that never touched `CORSMiddleware`.

It duplicates only origin-matching (mirroring
`starlette.middleware.cors.CORSMiddleware.is_allowed_origin`) — never
`allow_origins=["*"]`, since credentialed requests forbid the wildcard and
this repo never uses it. It never rewrites a response that already carries
`Access-Control-Allow-Origin` (the normal path, already handled correctly by
CORSMiddleware) and never adds anything for a disallowed origin — only fills
the gap for a response that skipped CORSMiddleware. It touches headers only:
the body, status code, and structured error payload `ServerErrorMiddleware`
already produced are untouched, and nothing here suppresses or alters
server-side exception logging (that already happened inside
`unhandled_exception_handler`/`ServerErrorMiddleware` before this wrapper
ever sees the outgoing response).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class CorsErrorPathMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        allow_origins: Iterable[str] = (),
        allow_origin_regex: str | None = None,
    ) -> None:
        self.app = app
        self.allow_origins = list(allow_origins)
        self.allow_origin_regex = re.compile(allow_origin_regex) if allow_origin_regex else None

    def is_allowed_origin(self, origin: str) -> bool:
        if self.allow_origin_regex is not None and self.allow_origin_regex.fullmatch(origin):
            return True
        return origin in self.allow_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origin = Headers(scope=scope).get("origin")
        if origin is None or not self.is_allowed_origin(origin):
            await self.app(scope, receive, send)
            return

        async def send_with_cors_fallback(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                # CORSMiddleware already ran and set this on every response
                # that reached it — never overwrite that (a well-formed
                # AppError/HTTPException/validation response, or a normal
                # 2xx). Only a response that bypassed it entirely (the
                # ServerErrorMiddleware path) arrives here without it.
                if "access-control-allow-origin" not in headers:
                    headers["Access-Control-Allow-Origin"] = origin
                    headers["Access-Control-Allow-Credentials"] = "true"
                    headers.add_vary_header("Origin")
            await send(message)

        await self.app(scope, receive, send_with_cors_fallback)
