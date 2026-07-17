"""Direct service booking — synthesize a job + submitted quote, reuse the RFQ spine.

MONEY-CRITICAL BY REUSE. This module writes NO escrow/ledger/commission logic. A
booking creates a public.jobs row + a submitted public.job_quotes row at the
service's fixed booking price, then delegates to ``accept_quote`` (the RFQ deposit
money spine), which builds the deposit order + escrow. The customer pays the
deposit through the same checkout/payment path as an accepted RFQ quote, and
completion/balance/release reuse job_completion.

Idempotent per (customer, service, idempotency_key): the synthesized job/quote ids
are deterministic (uuid5), inserted ``ON CONFLICT DO NOTHING``, and ``accept_quote``
replays via its checkout-group idempotency key. A prior successful booking is
returned directly by the ``_load_existing_accept`` short-circuit, so a replay never
re-validates or re-charges.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from app.errors import AppError
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.rfq.engagement import (
    AcceptResult,
    _load_existing_accept,
    accept_quote,
)
from app.services.stock.claim import sql_uuid

# Fixed namespace for deterministic booking job/quote ids (idempotency).
BOOKING_NAMESPACE = uuid.UUID("6f9b7c2e-4d3a-5e1b-8c7d-2a1f0e9d8c7b")

MAX_NOTE_LEN = 2000


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def booking_ids(*, customer_id: str, service_id: str, idempotency_key: str) -> tuple[str, str]:
    """Deterministic (job_id, quote_id) so retries with the same key never duplicate."""
    base = f"{customer_id}:{service_id}:{idempotency_key}"
    job_id = str(uuid.uuid5(BOOKING_NAMESPACE, f"job:{base}"))
    quote_id = str(uuid.uuid5(BOOKING_NAMESPACE, f"quote:{base}"))
    return job_id, quote_id


def _load_service(client: ServiceRoleClient, service_id: str) -> dict[str, Any] | None:
    return _single_row(
        client.client.table("services")
        .select("id, vendor_id, category, title, status, bookable, booking_price_ngwee")
        .eq("id", service_id)
        .maybe_single()
        .execute()
    )


def _vendor_owner_id(client: ServiceRoleClient, vendor_id: str) -> str | None:
    row = _single_row(
        client.client.table("vendors")
        .select("owner_user_id")
        .eq("id", vendor_id)
        .maybe_single()
        .execute()
    )
    if row and row.get("owner_user_id"):
        return str(row["owner_user_id"])
    return None


def create_booking(
    service_client: ServiceRoleClient,
    *,
    service_id: str,
    customer_id: str,
    idempotency_key: str,
    note: str | None = None,
) -> AcceptResult:
    """Book a bookable service at its fixed price → deposit escrow via the RFQ spine."""
    job_id, quote_id = booking_ids(
        customer_id=customer_id, service_id=service_id, idempotency_key=idempotency_key
    )

    # Idempotent replay: a prior successful booking is returned as-is (no re-charge).
    existing = _load_existing_accept(quote_id)
    if existing is not None:
        return existing

    service = _load_service(service_client, service_id)
    if service is None:
        raise AppError(
            code="not_found",
            message="Service not found",
            http_status=404,
            details={"message_key": "services.errors.not_found"},
        )
    if service.get("status") != "active" or not service.get("bookable"):
        raise AppError(
            code="conflict",
            message="This service is not available for direct booking",
            http_status=409,
            details={"message_key": "services.booking.errors.notBookable"},
        )
    price = service.get("booking_price_ngwee")
    if not isinstance(price, int) or price <= 0:
        raise AppError(
            code="conflict",
            message="This service has no booking price",
            http_status=409,
            details={"message_key": "services.booking.errors.notBookable"},
        )

    vendor_id = str(service["vendor_id"])
    owner_id = _vendor_owner_id(service_client, vendor_id)
    if owner_id is not None and owner_id == customer_id:
        raise AppError(
            code="forbidden",
            message="You cannot book your own service",
            http_status=422,
            details={"message_key": "services.booking.errors.ownService"},
        )

    category = str(service["category"])
    title = str(service.get("title") or "")
    note_clean = (note or "").strip()[:MAX_NOTE_LEN]
    description = note_clean or f"Direct booking: {title}"

    script = f"""
BEGIN;
INSERT INTO public.jobs (id, customer_id, category, description, status)
VALUES ({sql_uuid(job_id, "job_id")}, {sql_uuid(customer_id, "customer_id")},
        {sql_literal(category)}, {sql_literal(description)}, 'open')
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.job_quotes (id, job_id, provider_vendor_id, amount_ngwee, status)
VALUES ({sql_uuid(quote_id, "quote_id")}, {sql_uuid(job_id, "job_id")},
        {sql_uuid(vendor_id, "vendor_id")}, {price}, 'submitted')
ON CONFLICT (id) DO NOTHING;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise AppError(
            code="internal_error",
            message="Failed to create booking",
            http_status=500,
            details={"error": result.error},
        )

    # Reuse the RFQ deposit money spine unchanged.
    return accept_quote(
        service_client, job_id=job_id, quote_id=quote_id, customer_id=customer_id
    )
