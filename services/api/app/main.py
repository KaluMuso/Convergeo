from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Callable
from typing import Any, cast

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.ratelimit_policies import assert_all_mutating_routes_covered
from app.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from app.logging import configure_logging
from app.middleware import RequestIdMiddleware
from app.middleware.security_headers import (
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    SecureHeadersMiddleware,
)
from app.settings import get_settings

logger = logging.getLogger(__name__)


def discover_routers() -> list[APIRouter]:
    routers: list[APIRouter] = []
    package = importlib.import_module("app.routers")
    for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        module = importlib.import_module(module_info.name)
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            routers.append(router)
    return routers


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    app = FastAPI(title="Vergeo5 API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        # Staging-only immutable Vercel Preview origins (RC-6 / PR-F3). Always
        # None outside ENV=staging — see Settings.cors_allow_origin_regex.
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=CORS_ALLOW_HEADERS,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecureHeadersMiddleware)

    exception_handler = cast(
        Callable[[Request, Any], JSONResponse],
        app_error_handler,
    )
    validation_handler = cast(
        Callable[[Request, Any], JSONResponse],
        validation_error_handler,
    )
    http_handler = cast(
        Callable[[Request, Any], JSONResponse],
        http_exception_handler,
    )

    app.add_exception_handler(AppError, exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_handler)

    for router in discover_routers():
        app.include_router(router)

    # Fail fast if any mutating route lacks a declared rate-limit policy.
    assert_all_mutating_routes_covered(app)

    return app


app = create_app()
