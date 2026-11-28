from __future__ import annotations

import html
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx
from app.core.sentry import scrub
from app.services.notifications.adapters.base import (
    ChannelAdapter,
    FailureKind,
    OutboxMessage,
    SendResult,
)
from app.services.payments.money import ngwee_to_major_str

logger = logging.getLogger(__name__)

RESEND_API_KEY_ENV = "RESEND_API_KEY"
RESEND_SENDER_DOMAIN_ENV = "RESEND_SENDER_DOMAIN"
RESEND_REPLY_TO_ENV = "RESEND_REPLY_TO"
RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_SENDER_DOMAIN = "mail.vergeo5.com"
DEFAULT_REPLY_TO = "support@vergeo5.com"


@dataclass(frozen=True)
class EmailStream:
    """One filterable mail stream: fixed sender name, mailbox and subject prefix.

    King, 28 Nov 2026: every email we send carries a consistent sender and subject
    prefix so it can be filtered. Only the sender and prefix are standardised; the
    friendly subject wording after the prefix stays per template. Ops alerts
    ("Vergeo5 Alerts" <alerts@...>, "[Vergeo5 Alert P0]") are sent by n8n, not here.
    """

    display_name: str
    local_part: str
    subject_prefix: str

    def sender(self, domain: str) -> str:
        return f"{self.display_name} <{self.local_part}@{domain}>"


ORDERS_STREAM = EmailStream("Vergeo5 Orders", "orders", "[Vergeo5 Order]")
PAYMENTS_STREAM = EmailStream("Vergeo5 Payments", "payments", "[Vergeo5 Payment]")
VENDORS_STREAM = EmailStream("Vergeo5 Vendors", "vendors", "[Vergeo5 Vendor]")

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
    # Courier dispatch v1: the body is the same pre-rendered message the admin
    # board offers as "Copy message" (app.services.dispatch.message).
    "courier_dispatch_request": {
        "en": {
            "subject_key": "notifications.email.courier_dispatch_request.subject",
            "subject": "Vergeo5 delivery request {order_id}",
            "body_key": "notifications.email.courier_dispatch_request.body",
            "body": ("<p>New delivery job from Vergeo5.</p><p>{dispatch_message}</p>"),
        },
    },
    "dispatch_stale_alert": {
        "en": {
            "subject_key": "notifications.email.dispatch_stale_alert.subject",
            "subject": "Dispatch {order_id} not accepted",
            "body_key": "notifications.email.dispatch_stale_alert.body",
            "body": (
                "<p>Dispatch for order {order_id} is still waiting for courier acceptance.</p>"
            ),
        },
    },
    "service_quote_accepted": {
        "en": {
            "subject_key": "notifications.email.service_quote_accepted.subject",
            "subject": "Your Vergeo5 quote was accepted",
            "body_key": "notifications.email.service_quote_accepted.body",
            "body": (
                "<p>Good news — a customer accepted your quote.</p>"
                "<p><strong>Deposit secured:</strong> K{deposit}</p>"
                "<p><strong>Job total:</strong> K{total}</p>"
                "<p>The deposit is held safely by Vergeo5 escrow. "
                "Open Vergeo5 to start the job.</p>"
            ),
        },
    },
    "rfq_quoted": {
        "en": {
            "subject_key": "notifications.email.rfq_quoted.subject",
            "subject": "You received a quote on Vergeo5",
            "body_key": "notifications.email.rfq_quoted.body",
            "body": (
                "<p>A provider sent you a quote of <strong>K{quote_price}</strong>.</p>"
                "<p>Open the Vergeo5 app to review and accept it.</p>"
            ),
        },
    },
    "import_quote_ready": {
        "en": {
            "subject_key": "notifications.email.import_quote_ready.subject",
            "subject": "Your import quote is ready",
            "body_key": "notifications.email.import_quote_ready.body",
            "body": (
                "<p>We prepared a landed-cost estimate for <strong>{import_title}</strong>: "
                "about <strong>K{import_total}</strong> in total.</p>"
                "<p>This is an estimate, not an offer. Open Source in the Convergeo "
                "vendor app to see the full breakdown.</p>"
            ),
        },
    },
    "order_cancelled": {
        "en": {
            "subject_key": "notifications.email.order_cancelled.subject",
            "subject": "Your Vergeo5 order {order_id} was cancelled",
            "body_key": "notifications.email.order_cancelled.body",
            "body": (
                "<p>Your order was cancelled.</p>"
                "<p><strong>Order:</strong> {order_id}</p>"
                "<p>{refund_detail}</p>"
            ),
        },
    },
    "payment_failed": {
        "en": {
            "subject_key": "notifications.email.payment_failed.subject",
            "subject": "Your Vergeo5 payment did not go through",
            "body_key": "notifications.email.payment_failed.body",
            "body": (
                "<p>Your payment of K{amount} did not go through.</p>"
                "<p>If you were charged, please contact support and we will sort it out.</p>"
                "<p>You can try again: {retry_url}</p>"
            ),
        },
    },
    "order_completed": {
        "en": {
            "subject_key": "notifications.email.order_completed.subject",
            "subject": "Your Vergeo5 order {order_id} is complete",
            "body_key": "notifications.email.order_completed.body",
            "body": (
                "<p>Your order {order_id} is complete.</p>"
                "<p>Thank you for shopping with Vergeo5.</p>"
            ),
        },
    },
    "ticket_issued": {
        "en": {
            "subject_key": "notifications.email.ticket_issued.subject",
            "subject": "Your ticket for {event_title} is ready",
            "body_key": "notifications.email.ticket_issued.body",
            "body": (
                "<p>Your ticket for <strong>{event_title}</strong> is ready.</p>"
                "<p>Open My tickets in the Vergeo5 app and show the QR code at the door.</p>"
            ),
        },
    },
    "dispute_opened": {
        "en": {
            "subject_key": "notifications.email.dispute_opened.subject",
            "subject": "A dispute was opened on order {order_id}",
            "body_key": "notifications.email.dispute_opened.body",
            "body": (
                "<p>A customer opened a dispute on order {order_id}.</p>"
                "<p>Open the vendor app to read the details and respond.</p>"
            ),
        },
    },
    "dispute_resolved": {
        "en": {
            "subject_key": "notifications.email.dispute_resolved.subject",
            "subject": "The dispute on order {order_id} is resolved",
            "body_key": "notifications.email.dispute_resolved.body",
            "body": (
                "<p>The dispute on order {order_id} is resolved.</p><p>{resolution_summary}</p>"
            ),
        },
    },
    "payout_sent": {
        "en": {
            "subject_key": "notifications.email.payout_sent.subject",
            "subject": "Your Vergeo5 payout of K{amount} is on its way",
            "body_key": "notifications.email.payout_sent.body",
            "body": (
                "<p>Your payout of K{amount} is on its way to your {destination_label}.</p>"
                "<p>It should arrive shortly. Thank you for selling on Vergeo5.</p>"
            ),
        },
    },
    "payout_failed": {
        "en": {
            "subject_key": "notifications.email.payout_failed.subject",
            "subject": "Your Vergeo5 payout of K{amount} could not be sent",
            "body_key": "notifications.email.payout_failed.body",
            "body": (
                "<p>Your payout of K{amount} could not be sent.</p>"
                "<p>{failure_hint}</p>"
                "<p>We will retry once your details are correct.</p>"
            ),
        },
    },
}


# Which stream each template belongs to. Every template must be listed (a test
# enforces it), so a new template cannot silently go out under the wrong sender.
TEMPLATE_STREAMS: dict[str, EmailStream] = {
    # Payments, payouts, refunds.
    "payment_receipt": PAYMENTS_STREAM,
    "payment_received": PAYMENTS_STREAM,
    "payment_failed": PAYMENTS_STREAM,
    "payout_sent": PAYMENTS_STREAM,
    "payout_failed": PAYMENTS_STREAM,
    # KYC and vendor/business account.
    "kyc_approved": VENDORS_STREAM,
    "kyc_rejected": VENDORS_STREAM,
    "business_verified": VENDORS_STREAM,
    "business_rejected": VENDORS_STREAM,
    # Orders, tickets, services/RFQ, delivery, disputes.
    "order_receipt": ORDERS_STREAM,
    "order_confirmed": ORDERS_STREAM,
    "order_shipped": ORDERS_STREAM,
    "order_ready_pickup": ORDERS_STREAM,
    "order_delivered": ORDERS_STREAM,
    "order_cancelled": ORDERS_STREAM,
    "order_completed": ORDERS_STREAM,
    "vendor_new_order": ORDERS_STREAM,
    "rfq_job_broadcast": ORDERS_STREAM,
    "rfq_quoted": ORDERS_STREAM,
    "service_quote_accepted": ORDERS_STREAM,
    "import_quote_ready": ORDERS_STREAM,
    "courier_dispatch_request": ORDERS_STREAM,
    "dispatch_stale_alert": ORDERS_STREAM,
    "ticket_issued": ORDERS_STREAM,
    "dispute_opened": ORDERS_STREAM,
    "dispute_resolved": ORDERS_STREAM,
}


def email_stream_for(template: str | None) -> EmailStream:
    """Stream for a template; unknown templates render as payment_receipt, so match that."""
    name = template if template in EMAIL_TEMPLATES else "payment_receipt"
    return TEMPLATE_STREAMS.get(name, ORDERS_STREAM)


def _format_amount(payload: dict[str, Any]) -> str:
    for key in ("amount_ngwee", "total_ngwee"):
        value = payload.get(key)
        if isinstance(value, int):
            return ngwee_to_major_str(value)
    amount = payload.get("amount")
    if amount is not None:
        return str(amount)
    return "0.00"


def _ngwee_field(payload: dict[str, Any], key: str) -> str:
    """Integer-ngwee payload field → major-unit string, or '0.00' when absent."""
    value = payload.get(key)
    return ngwee_to_major_str(value) if isinstance(value, int) else "0.00"


def render_email_html(
    template: str | None,
    *,
    locale: str = "en",
    payload: dict[str, Any],
) -> tuple[str, str, str, str]:
    """Render subject + HTML from i18n-keyed template registry.

    The subject carries the stream prefix, e.g. ``[Vergeo5 Order] Your Vergeo5 order ...``.
    """
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
        "quote_price": html.escape(_ngwee_field(payload, "quote_price_ngwee")),
        "import_title": html.escape(str(payload.get("title") or "your import request")),
        "import_total": html.escape(_ngwee_field(payload, "total_ngwee")),
        "refund_detail": html.escape(
            str(payload.get("refund_detail") or "If you already paid, we will handle your refund.")
        ),
        "retry_url": html.escape(str(payload.get("retry_url") or "open the Vergeo5 app")),
        "event_title": html.escape(str(payload.get("event_title") or "your event")),
        "resolution_summary": html.escape(
            str(payload.get("resolution_summary") or "Open the app to see the outcome.")
        ),
        "destination_label": html.escape(
            str(payload.get("destination_label") or "mobile money number")
        ),
        "failure_hint": html.escape(
            str(payload.get("failure_hint") or "Please check your payout number in the vendor app.")
        ),
        "deposit": html.escape(_ngwee_field(payload, "deposit_ngwee")),
        "total": html.escape(_ngwee_field(payload, "total_job_ngwee")),
        "dispatch_message": "<br>".join(
            html.escape(line) for line in str(payload.get("dispatch_message") or "").splitlines()
        ),
    }
    stream = email_stream_for(template_name)
    subject = f"{stream.subject_prefix} {strings['subject'].format(**vars_map)}"
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


_RESEND_TAG_INVALID = re.compile(r"[^A-Za-z0-9_-]")


def _resend_tag_value(value: str) -> str:
    """Resend tag names/values allow only ASCII letters, digits, underscore and dash.

    i18n keys like ``notifications.email.kyc.approved.subject`` contain dots and make
    Resend answer 422 validation_error, so map every other character to ``_``.
    """
    return _RESEND_TAG_INVALID.sub("_", value)[:256] or "unknown"


def _map_resend_error(status_code: int) -> FailureKind:
    if status_code in {400, 401, 403, 404, 422}:
        return FailureKind.PERMANENT
    if status_code in {429, 500, 502, 503, 504}:
        return FailureKind.RETRYABLE
    return FailureKind.RETRYABLE


def _mask_email_address(email: str) -> str:
    """Mask recipient for logs — never emit the full local-part."""
    normalized = email.strip()
    if not normalized or "@" not in normalized:
        return "***"
    local, _, domain = normalized.partition("@")
    if not local:
        masked_local = "***"
    elif len(local) == 1:
        masked_local = "*"
    else:
        masked_local = f"{local[0]}***"
    return f"{masked_local}@{domain}"


def _format_resend_error_detail(response: httpx.Response) -> str:
    """Build a short, scrubbed summary of Resend's error JSON (max 500 chars)."""
    status = response.status_code
    name = ""
    message = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            name = str(payload.get("name") or "").strip()
            message = str(payload.get("message") or "").strip()
    except (ValueError, TypeError):
        message = (response.text or "").strip()

    parts: list[str] = [f"status={status}"]
    if name:
        parts.append(f"name={name}")
    if message:
        parts.append(f"message={message}")
    detail = str(scrub("; ".join(parts)))
    if len(detail) > 500:
        return detail[:499] + "…"
    return detail


@dataclass
class ResendEmailAdapter:
    """Resend email ChannelAdapter with i18n-keyed HTML templates."""

    api_key: str
    sender_domain: str = DEFAULT_SENDER_DOMAIN
    reply_to: str = DEFAULT_REPLY_TO
    client: httpx.AsyncClient | None = None

    @classmethod
    def from_env(cls, *, client: httpx.AsyncClient | None = None) -> ResendEmailAdapter:
        api_key = os.environ.get(RESEND_API_KEY_ENV, "").strip()
        if not api_key:
            raise ValueError(f"{RESEND_API_KEY_ENV} is required")
        # The sender domain must be verified in Resend. Rollback: RESEND_SENDER_DOMAIN=vergeo5.com.
        sender_domain = (
            os.environ.get(RESEND_SENDER_DOMAIN_ENV, "").strip() or DEFAULT_SENDER_DOMAIN
        )
        reply_to = os.environ.get(RESEND_REPLY_TO_ENV, "").strip() or DEFAULT_REPLY_TO
        return cls(api_key=api_key, sender_domain=sender_domain, reply_to=reply_to, client=client)

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
                    "from": email_stream_for(message.template).sender(self.sender_domain),
                    "to": [to],
                    "reply_to": self.reply_to,
                    "subject": subject,
                    "html": html_body,
                    "tags": [
                        {
                            "name": "template",
                            "value": _resend_tag_value(message.template or "payment_receipt"),
                        },
                        {"name": "subject_key", "value": _resend_tag_value(subject_key)},
                        {"name": "body_key", "value": _resend_tag_value(body_key)},
                    ],
                },
            )
            if response.status_code >= 400:
                failure_kind = _map_resend_error(response.status_code)
                error_detail = _format_resend_error_detail(response)
                logger.warning(
                    "Resend send failed",
                    extra={
                        "channel": "email",
                        "template": message.template,
                        "dedupe_key": message.dedupe_key,
                        "recipient": _mask_email_address(to),
                        "http_status": response.status_code,
                        "failure_kind": failure_kind,
                        "resend_error": error_detail,
                    },
                )
                return SendResult(
                    success=False,
                    failure_kind=failure_kind,
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
