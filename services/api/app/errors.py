from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic_core import PydanticCustomError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}


def build_error_envelope(
    *,
    code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        return request_id
    return "unknown"


def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = get_request_id(request)
    return JSONResponse(
        status_code=exc.http_status,
        content=build_error_envelope(
            code=exc.code,
            message=exc.message,
            request_id=request_id,
            details=exc.details,
        ),
        headers={"X-Request-ID": request_id},
    )


def field_value_error(field: str, message: str, code: str | None = None) -> PydanticCustomError:
    """A validator error that names the request field it belongs to.

    Pydantic model-level validators otherwise report ``loc=("body",)``; carrying
    the field in ``ctx`` lets :func:`validation_error_handler` return
    field-level errors the client can render next to the right input.
    """
    return PydanticCustomError(
        "field_error",
        message.replace("{", "(").replace("}", ")"),
        {"field": field, "code": code or field},
    )


def _field_errors_from_validation(errors: list[Any]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        ctx = error.get("ctx")
        field: str | None = None
        code: str | None = None
        if isinstance(ctx, dict) and isinstance(ctx.get("field"), str):
            field = str(ctx["field"])
            code = str(ctx.get("code") or field)
        else:
            loc = [part for part in error.get("loc", ()) if isinstance(part, str)]
            if loc and loc[0] in {"body", "query", "path"}:
                loc = loc[1:]
            if loc:
                field = ".".join(loc)
        message = str(error.get("msg", "Invalid value"))
        message = message.removeprefix("Value error, ")
        fields.append(
            {
                "field": field or "_form",
                "code": code or str(error.get("type", "invalid")),
                "message": message,
            }
        )
    return fields


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = get_request_id(request)
    return JSONResponse(
        status_code=422,
        content=build_error_envelope(
            code="validation_error",
            message="Request validation failed",
            request_id=request_id,
            # jsonable_encoder keeps the payload JSON-safe: a value_error raised by a
            # field/model validator (e.g. NgweeInt float rejection) carries the raw
            # exception in ``ctx``, which json.dumps cannot serialize — without this
            # such validation errors surface as a 500 instead of a 422.
            details={
                "errors": jsonable_encoder(exc.errors()),
                "fields": _field_errors_from_validation(jsonable_encoder(exc.errors())),
            },
        ),
        headers={"X-Request-ID": request_id},
    )


def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = get_request_id(request)
    # FastAPI can call this after the active except block has ended. Log only
    # code locations and type; exception messages may contain payment data.
    logger.error(
        "Unhandled exception",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "exception_type": f"{type(exc).__module__}.{type(exc).__qualname__}",
            "exception_frames": [
                f"{Path(frame.f_code.co_filename).name}:{line}:{frame.f_code.co_name}"
                for frame, line in traceback.walk_tb(exc.__traceback__)
            ][-16:],
        },
    )

    return JSONResponse(
        status_code=500,
        content=build_error_envelope(
            code="internal_error",
            message="An unexpected error occurred",
            request_id=request_id,
        ),
        headers={"X-Request-ID": request_id},
    )


def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = get_request_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_envelope(
            code="http_error",
            message=str(exc.detail),
            request_id=request_id,
        ),
        headers={"X-Request-ID": request_id},
    )


def validate_request_id(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False
