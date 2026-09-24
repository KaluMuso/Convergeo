"""Explicit verified-ingress fixture for in-memory payment consumer tests."""

from typing import Any

from app.services.payments.webhook_verify import (
    LencoWebhookVerifyResult,
    build_webhook_event_row,
)


def verified_webhook_row(row: dict[str, Any]) -> dict[str, Any]:
    proof = build_webhook_event_row(
        LencoWebhookVerifyResult(valid=True, event_id=row["event_id"], raw=row["raw"])
    )
    return {**row, **proof, "processed_at": row.get("processed_at")}
