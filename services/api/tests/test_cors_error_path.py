"""CorsErrorPathMiddleware — allowed-origin generic 500s must carry CORS headers.

Run #55 proved the mechanism this closes: an unhandled exception (registered
for the bare `Exception` type) is handled by Starlette's ServerErrorMiddleware,
which sits *outside* every user-added middleware including CORSMiddleware —
so that response reaches the browser with no Access-Control-Allow-Origin at
all, even from an allowed origin, and the browser reports it as a CORS
failure instead of surfacing the real error.

These tests build a minimal isolated Starlette/FastAPI app that reproduces
the exact layering app.main.create_app() uses (CORSMiddleware +
app.add_exception_handler(Exception, ...)), so the middleware's own
origin-matching and header-fallback logic is proven independent of any
specific route's bug.
"""

from __future__ import annotations

from app.middleware.cors_error_path import CorsErrorPathMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "https://convergeo-customer-abc123xy-vergeo-projects.vercel.app"
DISALLOWED_ORIGIN = "https://evil.example.com"
PREVIEW_REGEX = r"^https://convergeo-(customer|vendor|admin)-[a-z0-9-]+-vergeo-projects\.vercel\.app$"


async def _generic_exception_handler(request: object, exc: Exception) -> JSONResponse:
    # Mirrors app.errors.unhandled_exception_handler's contract: generic,
    # safe body — never a stack trace or the exception's own message.
    return JSONResponse(status_code=500, content={"error": {"code": "internal_error"}})


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://vergeo5.com"],
        allow_origin_regex=PREVIEW_REGEX,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_exception_handler(Exception, _generic_exception_handler)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("unexpected — simulates an unhandled app bug")

    @app.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    return app


def _wrapped_client() -> TestClient:
    app = _build_test_app()
    wrapped = CorsErrorPathMiddleware(
        app,
        allow_origins=["https://vergeo5.com"],
        allow_origin_regex=PREVIEW_REGEX,
    )
    return TestClient(wrapped, raise_server_exceptions=False)


def _unwrapped_client() -> TestClient:
    return TestClient(_build_test_app(), raise_server_exceptions=False)


class TestCorsErrorPathMiddleware:
    def test_unwrapped_app_loses_cors_headers_on_generic_500(self) -> None:
        """Proves the bug exists without the wrapper (sanity check for the fix below)."""
        response = _unwrapped_client().get("/boom", headers={"Origin": ALLOWED_ORIGIN})
        assert response.status_code == 500
        assert "access-control-allow-origin" not in {k.lower() for k in response.headers}

    def test_allowed_origin_generic_500_gets_exact_cors_headers(self) -> None:
        response = _wrapped_client().get("/boom", headers={"Origin": ALLOWED_ORIGIN})
        assert response.status_code == 500
        assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert response.headers["access-control-allow-credentials"] == "true"
        # Safe, generic body — no stack trace, no exception message.
        body = response.json()
        assert body == {"error": {"code": "internal_error"}}
        assert "RuntimeError" not in response.text
        assert "unexpected — simulates" not in response.text

    def test_disallowed_origin_generic_500_gets_no_acao(self) -> None:
        response = _wrapped_client().get("/boom", headers={"Origin": DISALLOWED_ORIGIN})
        assert response.status_code == 500
        assert "access-control-allow-origin" not in {k.lower() for k in response.headers}

    def test_exact_allowlisted_origin_also_covered(self) -> None:
        response = _wrapped_client().get("/boom", headers={"Origin": "https://vergeo5.com"})
        assert response.status_code == 500
        assert response.headers["access-control-allow-origin"] == "https://vergeo5.com"

    def test_normal_endpoint_behavior_unchanged(self) -> None:
        response = _wrapped_client().get("/ok", headers={"Origin": ALLOWED_ORIGIN})
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        # CORSMiddleware itself set this — the wrapper must not duplicate or alter it.
        assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert response.headers["access-control-allow-credentials"] == "true"

    def test_no_origin_header_passes_through_untouched(self) -> None:
        response = _wrapped_client().get("/boom")
        assert response.status_code == 500
        assert "access-control-allow-origin" not in {k.lower() for k in response.headers}

    def test_wrapper_never_overwrites_an_already_cors_decorated_response(self) -> None:
        """AppError/HTTPException-class responses already flow through CORSMiddleware
        correctly (inner ExceptionMiddleware) — the wrapper must be a no-op there,
        not risk ever setting a second, conflicting ACAO value."""

        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[],
            allow_origin_regex=PREVIEW_REGEX,
            allow_credentials=True,
            allow_methods=["GET"],
            allow_headers=["Content-Type"],
        )

        @app.get("/handled-error")
        def handled_error() -> None:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="bad request")

        wrapped = CorsErrorPathMiddleware(
            app,
            allow_origins=[],
            allow_origin_regex=PREVIEW_REGEX,
        )
        client = TestClient(wrapped, raise_server_exceptions=False)
        response = client.get("/handled-error", headers={"Origin": ALLOWED_ORIGIN})
        assert response.status_code == 400
        # Exactly one ACAO value, set by CORSMiddleware itself.
        assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
