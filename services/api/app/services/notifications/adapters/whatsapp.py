"""WhatsApp Cloud API channel adapter (official Meta API only — no WAHA)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx
from app.services.notifications.adapters.base import (
    FailureKind,
    OutboxMessage,
    SendResult,
)
from app.services.notifications.templates.whatsapp import (
    DEFAULT_API_VERSION,
    WHATSAPP_ACCESS_TOKEN_ENV,
    WHATSAPP_API_VERSION_ENV,
    WHATSAPP_TOKEN_ENV,
    TemplateRenderError,
    build_cloud_api_template,
    render_whatsapp_template,
)

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com"

# Meta error subcodes mapped to permanent delivery failures.
_PERMANENT_ERROR_CODES: frozenset[int] = frozenset(
    {
        131026,  # recipient not on WhatsApp / blocked
        131047,  # re-engagement message not allowed
        132000,  # template param count mismatch
        132001,  # template does not exist / not approved
        132005,  # template hydration failed (bad params)
        132007,  # template format mismatch
        132012,  # template parameter invalid
        132015,  # template paused / disabled
        133010,  # phone number not registered
        100,  # invalid parameter (when paired with template errors)
    }
)

_RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


def _resolve_access_token(token_env: str) -> str:
    token = os.environ.get(token_env, "").strip()
    if not token and token_env == WHATSAPP_TOKEN_ENV:
        token = os.environ.get(WHATSAPP_ACCESS_TOKEN_ENV, "").strip()
    if not token:
        msg = f"{token_env} is not configured"
        raise TemplateRenderError(msg)
    return token


def _resolve_phone_number_id(phone_env: str) -> str:
    phone_number_id = os.environ.get(phone_env, "").strip()
    if not phone_number_id:
        msg = f"{phone_env} is not configured"
        raise TemplateRenderError(msg)
    return phone_number_id


def _resolve_api_version() -> str:
    raw = os.environ.get(WHATSAPP_API_VERSION_ENV, DEFAULT_API_VERSION)
    return raw.strip() or DEFAULT_API_VERSION


def classify_whatsapp_error(
    *,
    http_status: int | None,
    error_code: int | None,
    error_subcode: int | None,
    error_message: str | None,
) -> FailureKind:
    """Map Cloud API errors to retryable vs permanent failure taxonomy."""
    if http_status is not None and http_status in _RETRYABLE_HTTP_STATUS:
        return FailureKind.RETRYABLE

    code = error_subcode if error_subcode is not None else error_code
    if code is not None and code in _PERMANENT_ERROR_CODES:
        return FailureKind.PERMANENT

    lowered = (error_message or "").lower()
    if any(
        phrase in lowered
        for phrase in (
            "rate limit",
            "too many requests",
            "temporarily unavailable",
            "service unavailable",
            "internal error",
        )
    ):
        return FailureKind.RETRYABLE

    if any(
        phrase in lowered
        for phrase in (
            "template",
            "not a valid whatsapp user",
            "blocked",
            "opted out",
            "invalid phone",
            "parameter",
        )
    ):
        return FailureKind.PERMANENT

    if http_status is not None and 400 <= http_status < 500:
        return FailureKind.PERMANENT

    if http_status is not None and http_status >= 500:
        return FailureKind.RETRYABLE

    return FailureKind.RETRYABLE


def _extract_error_fields(body: Any) -> tuple[int | None, int | None, str | None]:
    if not isinstance(body, dict):
        return None, None, None
    error = body.get("error")
    if not isinstance(error, dict):
        return None, None, None
    code = error.get("code")
    subcode = error.get("error_subcode")
    message = error.get("message")
    parsed_code = int(code) if isinstance(code, int) else None
    parsed_subcode = int(subcode) if isinstance(subcode, int) else None
    parsed_message = str(message) if message is not None else None
    return parsed_code, parsed_subcode, parsed_message


@dataclass
class WhatsAppAdapter:
    """Send outbox messages via the official WhatsApp Cloud API."""

    client: httpx.AsyncClient | None = None
    phone_number_id: str | None = None
    access_token: str | None = None
    api_version: str | None = None

    async def send(self, message: OutboxMessage) -> SendResult:
        if message.channel != "whatsapp":
            return SendResult(
                success=False,
                failure_kind=FailureKind.PERMANENT,
                message="WhatsAppAdapter only handles whatsapp channel",
            )
        if not message.template:
            return SendResult(
                success=False,
                failure_kind=FailureKind.PERMANENT,
                message="missing template on outbox message",
            )

        try:
            rendered = render_whatsapp_template(message.template, message.payload)
            api_body = build_cloud_api_template(rendered)
            phone_number_id = self.phone_number_id or _resolve_phone_number_id(
                rendered.phone_number_id_env
            )
            access_token = self.access_token or _resolve_access_token(rendered.token_env)
            api_version = self.api_version or _resolve_api_version()
        except TemplateRenderError as exc:
            return SendResult(
                success=False,
                failure_kind=FailureKind.PERMANENT,
                message=str(exc),
            )

        url = f"{GRAPH_API_BASE}/{api_version}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        owns_client = self.client is None
        http = self.client or httpx.AsyncClient(timeout=15.0)
        try:
            response = await http.post(url, json=api_body, headers=headers)
            if response.is_success:
                logger.info(
                    "WhatsApp template sent",
                    extra={
                        "template": message.template,
                        "dedupe_key": message.dedupe_key,
                    },
                )
                return SendResult(success=True)

            error_code, error_subcode, error_message = _extract_error_fields(response.json())
            failure_kind = classify_whatsapp_error(
                http_status=response.status_code,
                error_code=error_code,
                error_subcode=error_subcode,
                error_message=error_message,
            )
            detail = error_message or response.text
            logger.warning(
                "WhatsApp send failed",
                extra={
                    "template": message.template,
                    "dedupe_key": message.dedupe_key,
                    "http_status": response.status_code,
                    "error_code": error_code,
                    "error_subcode": error_subcode,
                    "failure_kind": failure_kind,
                },
            )
            return SendResult(success=False, failure_kind=failure_kind, message=detail)
        except httpx.HTTPError as exc:
            logger.warning(
                "WhatsApp transport error",
                extra={"template": message.template, "dedupe_key": message.dedupe_key},
            )
            return SendResult(
                success=False,
                failure_kind=FailureKind.RETRYABLE,
                message=str(exc),
            )
        finally:
            if owns_client:
                await http.aclose()
