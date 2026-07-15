from __future__ import annotations

import html
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
from app.services.payments.money import ngwee_to_major_str

logger = logging.getLogger(__name__)

RESEND_API_KEY_ENV = "RESEND_API_KEY"
RESEND_FROM_EMAIL_ENV = "RESEND_FROM_EMAIL"
RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_FROM_EMAIL = "notifications@vergeo5.com"

EMAIL_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "payment_receipt": {
        "en": {
            "subject_key": "notifications.email.receipt.subject",
            "subject": "Your Vergeo5 receipt — order {order_id}",
            "body_key": "notifications.email.receipt.body",
            "body": (
                "<p>Thank you for your payment.</p>"
                "<p><strong>Order:</strong> {order_id}</p>"
                "<p><strong>Amount:</strong> K{amount}</p>"
                "<p>Funds are held safely by Vergeo5 until delivery.</p>"
            ),
        },
    },
    "order_receipt": {
        "en": {
            "subject_key": "notifications.email.receipt.subject",
            "subject": "Your Vergeo5 receipt — order {order_id}",
            "body_key": "notifications.email.receipt.body",
            "body": (
                "<p>Thank you for your order.</p>"
                "<p><strong>Order:</strong> {order_id}</p>"
                "<p><strong>Total:</strong> K{amount}</p>"
            ),
        },
    },
    "kyc_approved": {
        "en": {
            "subject_key": "notifications.email.kyc.approved.subject",
            "subject": "Your Vergeo5 vendor verification is approved",
            "body_key": "notifications.email.kyc.approved.body",
            "body": (
                "<p>Good news — your vendor identity verification is approved.</p>"
                "<p>You can now publish listings and receive payouts on Vergeo5.</p>"
            ),
        },
    },
    "kyc_rejected": {
        "en": {
            "subject_key": "notifications.email.kyc.rejected.subject",
            "subject": "Your Vergeo5 vendor verification needs attention",
            "body_key": "notifications.email.kyc.rejected.body",
            "body": (
                "<p>We could not approve your vendor verification.</p>"
                "<p><strong>Reason:</strong> {reason}</p>"
                "<p>Please resubmit your documents from the vendor app.</p>"
            ),
        },
    },
    "business_verified": {
        "en": {
            "subject_key": "notifications.email.business.verified.subject",
            "subject": "Your Vergeo5 business account is verified",
            "body_key": "notifications.email.business.verified.body",
            "body": (
                "<p>Good news — your business account is verified.</p>"
                "<p>Business mode is now on: you can browse and buy wholesale "
                "supplies with tier pricing across Vergeo5.</p>"
            ),
        },
    },
    "business_rejected": {
        "en": {
            "subject_key": "notifications.email.business.rejected.subject",
            "subject": "Your Vergeo5 business verification needs attention",
            "body_key": "notifications.email.business.rejected.body",
            "body": (
                "<p>We could not verify your business account.</p>"
                "<p><strong>Reason:</strong> {reason}</p>"
                "<p>Please update your details and resubmit from your account.</p>"
            ),
        },
    },
    # --- Lifecycle events (also the WhatsApp/SMS template ids, so a WhatsApp send
    # can fail over to an email row carrying the same template + payload). ---------
    "order_confirmed": {
        "en": {
            "subject_key": "notifications.email.order_confirmed.subject",
            "subject": "Your Vergeo5 order {order_id} is confirmed",
            "body_key": "notifications.email.order_confirmed.body",
            "body": (
                "<p>Your order is confirmed.</p>"
                "<p><strong>Order:</strong> {order_id}</p>"
                "<p><strong>Total:</strong> K{amount}</p>"
                "<p>Your money is held safely by Vergeo5 until delivery.</p>"
            ),
        },
    },
    "payment_received": {
        "en": {
            "subject_key": "notifications.email.payment_received.subject",
            "subject": "Payment received — Vergeo5 order {order_id}",
            "body_key": "notifications.email.payment_received.body",
            "body": (
                "<p>We received your payment.</p>"
                "<p><strong>Order:</strong> {order_id}</p>"
                "<p><strong>Amount:</strong> K{amount}</p>"
                "<p>Funds are held safely by Vergeo5 until delivery.</p>"
            ),
        },
    },
    "order_shipped": {
        "en": {
            "subject_key": "notifications.email.order_shipped.subject",
            "subject": "Your Vergeo5 order {order_id} is on its way",
            "body_key": "notifications.email.order_shipped.body",
            "body": (
                "<p>Your order is on its way.</p>"
                "<p><strong>Order:</strong> {order_id}</p>"
                "<p>{tracking_info}</p>"
            ),
        },
    },
    "order_ready_pickup": {
        "en": {
            "subject_key": "notifications.email.order_ready_pickup.subject",
            "subject": "Your Vergeo5 order {order_id} is ready for pickup",
            "body_key": "notifications.email.order_ready_pickup.body",
            "body": (
                "<p>Your order is ready for pickup.</p>"
                "<p><strong>Order:</strong> {order_id}</p>"
                "<p>{pickup_details}</p>"
            ),
        },
    },
    "order_delivered": {
        "en": {
            "subject_key": "notifications.email.order_delivered.subject",
            "subject": "Your Vergeo5 order {order_id} was delivered",
            "body_key": "notifications.email.order_delivered.body",
            "body": (
                "<p>Your order {order_id} was delivered.</p>"
                "<p>Thank you for shopping with Vergeo5.</p>"
            ),
        },
    },
    "vendor_new_order": {
        "en": {
            "subject_key": "notifications.email.vendor_new_order.subject",
            "subject": "New Vergeo5 order {order_id}",
            "body_key": "notifications.email.vendor_new_order.body",
            "body": (
                "<p>You have a new order.</p>"
                "<p><strong>Order:</strong> {order_id}</p>"
                "<p><strong>Item:</strong> {quantity} x {product_title}</p>"
                "<p>Open the vendor app to accept and prepare it.</p>"
            ),
        },
    },
    "rfq_job_broadcast": {
        "en": {
            "subject_key": "notifications.email.rfq_job_broadcast.subject",
            "subject": "New {category} request on Vergeo5",
            "body_key": "notifications.email.rfq_job_broadcast.body",
            "body": (
                "<p>A customer is looking for {category} near {service_area}.</p>"
                "<p>{description_preview}</p>"
                "<p>Open Vergeo5 to send your quote.</p>"
            ),
        },
    },
}


def _format_amount(payload: dict[str, Any]) -> str:
    for key in ("amount_ngwee", "total_ngwee"):
        value = payload.get(key)
        if isinstance(value, int):
            return ngwee_to_major_str(value)
    amount = payload.get("amount")
    if amount is not None:
        return str(amount)
    return "0.00"


def render_email_html(
    template: str | None,
    *,
    locale: str = "en",
    payload: dict[str, Any],
) -> tuple[str, str, str, str]:
    """Render subject + HTML from i18n-keyed template registry."""
    template_name = template or "payment_receipt"
    locale_templates = EMAIL_TEMPLATES.get(template_name, EMAIL_TEMPLATES["payment_receipt"])
    strings = locale_templates.get(locale) or locale_templates["en"]

    # order_reference is what the lifecycle payloads actually carry (order_id/entity_id
    # are legacy fallbacks). All values are html-escaped; extra keys are harmless since
    # .format only consumes the placeholders present in the chosen template.
    vars_map = {
        "order_id": html.escape(
            str(
                payload.get("order_reference")
                or payload.get("order_id")
                or payload.get("entity_id")
                or ""
            )
        ),
        "amount": html.escape(_format_amount(payload)),
        "reason": html.escape(str(payload.get("reason") or "Please review your submission")),
        "tracking_info": html.escape(str(payload.get("tracking_info") or "")),
        "pickup_details": html.escape(str(payload.get("pickup_details") or "")),
        "product_title": html.escape(str(payload.get("product_title") or "your item")),
        "quantity": html.escape(str(payload.get("quantity") or "1")),
        "category": html.escape(str(payload.get("category") or "a service")),
        "service_area": html.escape(str(payload.get("service_area") or "your area")),
        "description_preview": html.escape(str(payload.get("description_preview") or "")),
        "track_url": html.escape(str(payload.get("track_url") or "")),
        "review_url": html.escape(str(payload.get("review_url") or "")),
    }
    subject = strings["subject"].format(**vars_map)
    body = strings["body"].format(**vars_map)
    subject_key = strings["subject_key"]
    body_key = strings["body_key"]
    wrapped = (
        '<div style="font-family:DM Sans,Arial,sans-serif;color:#1a1a1a;max-width:560px">'
        f"{body}"
        '<p style="color:#666;font-size:12px">Vergeo5 · vergeo5.com</p>'
        "</div>"
    )
    return subject, wrapped, subject_key, body_key


def _map_resend_error(status_code: int) -> FailureKind:
    if status_code in {400, 401, 403, 404, 422}:
        return FailureKind.PERMANENT
    if status_code in {429, 500, 502, 503, 504}:
        return FailureKind.RETRYABLE
    return FailureKind.RETRYABLE


@dataclass
class ResendEmailAdapter:
    """Resend email ChannelAdapter with i18n-keyed HTML templates."""

    api_key: str
    from_email: str
    client: httpx.AsyncClient | None = None

    @classmethod
    def from_env(cls, *, client: httpx.AsyncClient | None = None) -> ResendEmailAdapter:
        api_key = os.environ.get(RESEND_API_KEY_ENV, "").strip()
        if not api_key:
            raise ValueError(f"{RESEND_API_KEY_ENV} is required")
        from_email = os.environ.get(RESEND_FROM_EMAIL_ENV, DEFAULT_FROM_EMAIL).strip()
        return cls(api_key=api_key, from_email=from_email, client=client)

    async def send(self, message: OutboxMessage) -> SendResult:
        to = str(message.payload.get("email") or message.payload.get("to") or "").strip()
        if not to:
            return SendResult(
                success=False,
                failure_kind=FailureKind.PERMANENT,
                message="missing email recipient",
            )

        locale = str(message.payload.get("locale") or "en")
        subject, html_body, subject_key, body_key = render_email_html(
            message.template,
            locale=locale,
            payload=message.payload,
        )

        owns_client = self.client is None
        http = self.client or httpx.AsyncClient(timeout=15.0)
        try:
            response = await http.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": self.from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html_body,
                    "tags": [
                        {"name": "template", "value": message.template or "payment_receipt"},
                        {"name": "subject_key", "value": subject_key},
                        {"name": "body_key", "value": body_key},
                    ],
                },
            )
            if response.status_code >= 400:
                return SendResult(
                    success=False,
                    failure_kind=_map_resend_error(response.status_code),
                    message=f"Resend HTTP {response.status_code}",
                )

            logger.info(
                "Resend email sent",
                extra={
                    "channel": "email",
                    "dedupe_key": message.dedupe_key,
                    "template": message.template,
                    "subject_key": subject_key,
                    "body_key": body_key,
                },
            )
            return SendResult(success=True)
        except httpx.TimeoutException:
            return SendResult(
                success=False,
                failure_kind=FailureKind.RETRYABLE,
                message="Resend timeout",
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


def build_email_adapter(*, client: httpx.AsyncClient | None = None) -> ChannelAdapter:
    return ResendEmailAdapter.from_env(client=client)
