from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx
from app.services.notifications.adapters.base import (
    ChannelAdapter,
    FailureKind,
    OutboxMessage,
    SendResult,
)

logger = logging.getLogger(__name__)

AT_API_KEY_ENV = "AT_API_KEY"
AT_USERNAME_ENV = "AT_USERNAME"
AT_SENDER_ID_ENV = "AT_SENDER_ID"
AT_MESSAGING_URL = "https://api.africastalking.com/version1/messaging"

GSM7_SINGLE_SEGMENT_SEPTETS = 160
GSM7_EXTENDED_CHARS = frozenset("^{}\\[~]|€")

GSM7_BASIC_CHARS = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)


def gsm7_septet_length(text: str) -> int:
    """Return GSM-7 septet count (extended chars count as 2)."""
    length = 0
    for char in text:
        if char in GSM7_BASIC_CHARS:
            length += 1
        elif char in GSM7_EXTENDED_CHARS:
            length += 2
        else:
            length += 1
    return length


def truncate_gsm7(
    text: str,
    *,
    max_septets: int = GSM7_SINGLE_SEGMENT_SEPTETS,
    link: str | None = None,
) -> tuple[str, bool]:
    """Truncate text to fit within max_septets; append link when truncated."""
    if link is None:
        if gsm7_septet_length(text) <= max_septets:
            return text, False
        budget = max_septets - 1
        truncated = _truncate_to_septets(text, budget)
        return f"{truncated}…", True

    link_suffix = f" {link}"
    link_len = gsm7_septet_length(link_suffix)
    if link_len >= max_septets:
        return link[: max_septets - 1] + "…", True

    body_budget = max_septets - link_len
    if gsm7_septet_length(text) <= body_budget:
        return text, False

    truncated = _truncate_to_septets(text, max(body_budget - 1, 0))
    return f"{truncated}…{link_suffix}", True


def _truncate_to_septets(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    result: list[str] = []
    used = 0
    for char in text:
        char_len = 2 if char in GSM7_EXTENDED_CHARS else 1
        if used + char_len > budget:
            break
        result.append(char)
        used += char_len
    return "".join(result)


def _map_at_error(status_code: int, body: dict[str, Any] | None) -> FailureKind:
    if status_code in {400, 401, 403, 404, 422}:
        return FailureKind.PERMANENT
    if status_code == 429:
        return FailureKind.RETRYABLE
    if status_code >= 500:
        return FailureKind.RETRYABLE
    message = ""
    if body:
        recipients = body.get("SMSMessageData", {}).get("Recipients", [])
        if isinstance(recipients, list) and recipients:
            first = recipients[0]
            if isinstance(first, dict):
                message = str(first.get("status") or first.get("message") or "")
    if "invalid" in message.lower() or "rejected" in message.lower():
        return FailureKind.PERMANENT
    return FailureKind.RETRYABLE


@dataclass
class AfricasTalkingSmsAdapter:
    """Africa's Talking SMS ChannelAdapter with GSM-7 truncation."""

    api_key: str
    username: str
    sender_id: str
    client: httpx.AsyncClient | None = None

    @classmethod
    def from_env(cls, *, client: httpx.AsyncClient | None = None) -> AfricasTalkingSmsAdapter:
        api_key = os.environ.get(AT_API_KEY_ENV, "").strip()
        username = os.environ.get(AT_USERNAME_ENV, "").strip()
        sender_id = os.environ.get(AT_SENDER_ID_ENV, "").strip()
        if not api_key or not username or not sender_id:
            raise ValueError(
                f"{AT_API_KEY_ENV}, {AT_USERNAME_ENV}, and {AT_SENDER_ID_ENV} are required"
            )
        return cls(api_key=api_key, username=username, sender_id=sender_id, client=client)

    async def send(self, message: OutboxMessage) -> SendResult:
        to = str(message.payload.get("phone") or message.payload.get("to") or "").strip()
        if not to:
            return SendResult(
                success=False,
                failure_kind=FailureKind.PERMANENT,
                message="missing phone recipient",
            )

        body_text = str(
            message.payload.get("body")
            or message.payload.get("text")
            or message.payload.get("message")
            or ""
        ).strip()
        if not body_text:
            return SendResult(
                success=False,
                failure_kind=FailureKind.PERMANENT,
                message="missing SMS body",
            )

        link = message.payload.get("link")
        link_str = str(link).strip() if link else None
        truncated_body, was_truncated = truncate_gsm7(body_text, link=link_str)

        owns_client = self.client is None
        http = self.client or httpx.AsyncClient(timeout=15.0)
        try:
            response = await http.post(
                AT_MESSAGING_URL,
                headers={
                    "apiKey": self.api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "username": self.username,
                    "to": to,
                    "message": truncated_body,
                    "from": self.sender_id,
                },
            )
            parsed: dict[str, Any] | None = None
            try:
                raw = response.json()
                if isinstance(raw, dict):
                    parsed = raw
            except ValueError:
                parsed = None

            if response.status_code >= 400:
                failure_kind = _map_at_error(response.status_code, parsed)
                return SendResult(
                    success=False,
                    failure_kind=failure_kind,
                    message=f"AT HTTP {response.status_code}",
                )

            recipients = (
                parsed.get("SMSMessageData", {}).get("Recipients", [])
                if parsed
                else []
            )
            if isinstance(recipients, list) and recipients:
                first = recipients[0]
                if isinstance(first, dict):
                    status = str(first.get("status", "")).lower()
                    if status in {"failed", "rejected", "invalidphonenumber"}:
                        return SendResult(
                            success=False,
                            failure_kind=FailureKind.PERMANENT,
                            message=str(first.get("message") or status),
                        )

            logger.info(
                "Africa's Talking SMS sent",
                extra={
                    "channel": "sms",
                    "dedupe_key": message.dedupe_key,
                    "truncated": was_truncated,
                    "septets": gsm7_septet_length(truncated_body),
                },
            )
            return SendResult(success=True, message="truncated" if was_truncated else None)
        except httpx.TimeoutException:
            return SendResult(
                success=False,
                failure_kind=FailureKind.RETRYABLE,
                message="AT timeout",
            )
        except httpx.HTTPError as exc:
            return SendResult(
                success=False,
                failure_kind=FailureKind.RETRYABLE,
                message=str(exc),
            )
        finally:
            if owns_client:
                await http.aclose()


def build_sms_adapter(*, client: httpx.AsyncClient | None = None) -> ChannelAdapter:
    return AfricasTalkingSmsAdapter.from_env(client=client)
