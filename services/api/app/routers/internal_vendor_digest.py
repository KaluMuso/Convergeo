"""Internal weekly seller digest (proposal E3; flag ``vendor_weekly_digest``).

n8n calls this Monday 08:00 Lusaka. Computation and enqueue live in
``private.vendor_weekly_digest`` (migration 20261116020100): one WhatsApp outbox
row + one in-app vendor notification per active vendor with activity, keyed by
vendor + ISO week so a retried tick never sends twice. Inactive vendors are skipped.
"""

from __future__ import annotations

import json
from typing import Any

from app.errors import AppError
from app.routers.internal_digest import require_internal_digest_token
from app.services.db import run_sql_script
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

router = APIRouter(prefix="/internal/vendor-digest", tags=["internal-vendor-digest"])

FLAG = "vendor_weekly_digest"


class VendorDigestRunOut(BaseModel):
    enabled: bool
    sent: bool
    vendors: list[dict[str, Any]]


def _flag_on() -> bool:
    result = run_sql_script(
        "SELECT coalesce((SELECT enabled FROM public.feature_flags"
        f" WHERE flag = '{FLAG}'), false)::text;"
    )
    return bool(result.ok and result.rows and result.rows[0].strip() == "true")


def run_vendor_digest(*, send: bool) -> VendorDigestRunOut:
    if not _flag_on():
        return VendorDigestRunOut(enabled=False, sent=False, vendors=[])
    send_sql = "true" if send else "false"
    result = run_sql_script(
        f"SELECT d::text FROM private.vendor_weekly_digest(timezone('utc', now()), {send_sql}) d;"
    )
    if not result.ok:
        raise AppError(code="vendor_digest_failed", message=result.error or "", http_status=503)
    vendors = [json.loads(row) for row in result.rows if row.strip()]
    return VendorDigestRunOut(enabled=True, sent=send, vendors=vendors)


@router.post(
    "/weekly",
    response_model=VendorDigestRunOut,
    dependencies=[Depends(require_internal_digest_token)],
)
async def weekly_vendor_digest(dry_run: bool = Query(default=False)) -> VendorDigestRunOut:
    return run_vendor_digest(send=not dry_run)
