"""Ask Vergeo answer log: record what a customer was shown, then audit it.

``log_and_audit`` runs as a FastAPI background task after the response is sent, so
neither the insert nor the audit can slow down or break an answer. Every failure is
logged and swallowed.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from app.services.ask.audit import audit_answer
from app.services.ask.enrich import rows_of

if TYPE_CHECKING:
    from app.routers.ask import AskResponse
    from app.services.ask.citations import CitationRef

logger = logging.getLogger(__name__)

MAX_ANSWER_CHARS = 8000


def citation_entries(citations: list[CitationRef]) -> list[dict[str, Any]]:
    """The cited entities exactly as shown: kind, id, title, ngwee shown, seller."""
    return [
        {
            "kind": c.entity_kind,
            "id": c.entity_id,
            "title": c.title,
            "price_ngwee": c.price_min_ngwee,
            "price_max_ngwee": c.price_max_ngwee,
            "vendor_id": c.vendor_id,
            "slug": c.slug,
        }
        for c in citations
    ]


def _valid_uuid(value: str | None) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        return None


def log_answer(
    client: Any,
    *,
    response: AskResponse,
    user_id: str | None,
    guest_key: str | None,
    locale: str | None,
) -> tuple[str, list[dict[str, Any]]] | None:
    """Insert the answer row. Returns ``(answer_id, entries)`` or ``None`` on failure."""
    uid = _valid_uuid(user_id)
    entries = citation_entries(response.citations)
    row = {
        "user_id": uid,
        "guest_key": None if uid else (guest_key or "unknown")[:160],
        "locale": (locale or None) and locale[:16],
        "query": response.query[:500],
        "answer_text": response.answer[:MAX_ANSWER_CHARS],
        "model": response.model,
        "source": response.source,
        "intent": response.intent,
        "cached": response.cached,
        "refused": response.refused,
        "citations": entries,
    }
    try:
        inserted = rows_of(client.table("ask_answers").insert(row).execute())
    except Exception:  # noqa: BLE001 — logging must never break Ask
        logger.warning("Ask answer log insert failed (swallowed)", exc_info=True)
        return None
    if not inserted or not inserted[0].get("id"):
        return None
    return str(inserted[0]["id"]), entries


def log_and_audit(
    client: Any,
    *,
    response: AskResponse,
    user_id: str | None,
    guest_key: str | None,
    locale: str | None,
) -> str | None:
    """Background task: record the answer, then run the deterministic auditor on it."""
    try:
        logged = log_answer(
            client, response=response, user_id=user_id, guest_key=guest_key, locale=locale
        )
        if logged is None:
            return None
        answer_id, entries = logged
        return audit_answer(
            client,
            answer_id,
            query=response.query,
            answer_text=response.answer,
            entries=entries,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Ask answer log/audit failed (swallowed)", exc_info=True)
        return None
