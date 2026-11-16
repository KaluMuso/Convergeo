"""n8n daily tick: redact gift recipients' details once the gift is finished (DPA).

A recipient's phone and the gift message exist only to deliver one gift. Thirty
days after every order of the checkout is completed or cancelled (or at once if
the checkout expired unpaid) they are wiped; the name stays so the payer's
order history still reads "Gift for Mary". Idempotent: redacted rows are skipped.
"""

from __future__ import annotations

import secrets

from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.errors import AppError
from app.services.orders.audit import run_sql_script
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

router = APIRouter(prefix="/internal/gifts", tags=["internal-gifts"])

_INTERNAL_TOKEN_ENV = "INTERNAL_BIRTHDAY_TOKEN"
_DEFAULT_INTERNAL_TOKEN = "dev-internal-birthday"
RETENTION_DAYS = 30

REDACT_SQL = f"""
WITH due AS (
  SELECT g.checkout_group_id
  FROM public.gift_details g
  JOIN public.checkout_groups cg ON cg.id = g.checkout_group_id
  WHERE g.redacted_at IS NULL
    AND (
      cg.status IN ('expired', 'abandoned')
      OR (
        EXISTS (SELECT 1 FROM public.orders o WHERE o.checkout_group_id = g.checkout_group_id)
        AND NOT EXISTS (
          SELECT 1 FROM public.orders o
          WHERE o.checkout_group_id = g.checkout_group_id
            AND (o.status NOT IN ('completed', 'cancelled')
                 OR o.updated_at > now() - interval '{RETENTION_DAYS} days')
        )
      )
    )
  FOR UPDATE OF g SKIP LOCKED
)
UPDATE public.gift_details g
SET recipient_phone = NULL, message = NULL, redacted_at = timezone('utc', now())
FROM due
WHERE g.checkout_group_id = due.checkout_group_id
RETURNING g.checkout_group_id::text;
"""


async def require_internal_gift_token(request: Request) -> None:
    try:
        expected = resolve_internal_token(_INTERNAL_TOKEN_ENV, dev_default=_DEFAULT_INTERNAL_TOKEN)
    except InternalTokenMisconfigured as exc:
        raise AppError(code="configuration_error", message=str(exc), http_status=503) from exc
    provided = request.headers.get("X-Internal-Token")
    if not provided or not secrets.compare_digest(provided, expected):
        raise AppError(
            code="unauthorized", message="Invalid or missing internal token", http_status=401
        )


class GiftRedactResult(BaseModel):
    redacted: int


@router.post(
    "/redact-tick",
    response_model=GiftRedactResult,
    dependencies=[Depends(require_internal_gift_token)],
)
def redact_finished_gifts() -> GiftRedactResult:
    result = run_sql_script(REDACT_SQL)
    if not result.ok:
        raise AppError(code="gift_redact_failed", message="Gift redaction failed", http_status=503)
    return GiftRedactResult(redacted=len(result.rows))
