"""M18-P04 — inbound-only session progression for WAHA intake (D35).

This module decides *what a session still needs* and moves it through P01's
guarded transitions. It does **not** talk to the vendor.

Under the corrected D35 the lane is **strictly inbound-only**: there is no ack,
no reply, no outbound of any kind. "Asking a follow-up" therefore means
**recording a structured request on the intake record** — an i18n key plus
params in ``intake_sessions.pending_requests`` — which M18-P05's vendor app
renders when the vendor opens their deep link. The follow-up is data, not a
message. A future acknowledgement, if ever justified, must be a separately
designed official Cloud API/outbox capability.

The orchestrator never sets ``submitted`` or anything beyond it. Submission is
the vendor's explicit act in M18-P05.
"""

from __future__ import annotations

import logging
from typing import Any, Final, Protocol

from app.services.intake import extract as extract_rules
from app.services.intake import state_machine
from app.services.intake.schemas import (
    REQUIRED_FOR_REVIEW,
    ExtractionResult,
    FieldSource,
    OpenQuestion,
)

logger = logging.getLogger(__name__)

DRAFT_TABLE: Final = "intake_draft_fields"
PROVENANCE_TABLE: Final = "intake_field_provenance"
SESSIONS_TABLE: Final = "intake_sessions"

# Follow-up keys the vendor app resolves from its own `vendor.intake.*`
# namespace. No user-facing copy lives in the API.
QUESTION_KEYS: Final[dict[str, str]] = {
    "title": "intake.question.title_missing",
    "category_slug": "intake.question.category_missing",
    "price_ngwee": "intake.question.price_missing",
    "condition": "intake.question.condition_missing",
}

# Two drafts from the same vendor that agree on this much are near-identical.
_DUPLICATE_KEYS: Final[tuple[str, ...]] = ("title", "price_ngwee")


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _table(service_client: ServiceRoleClient, name: str) -> Any:
    return service_client.client.table(name)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def missing_required(result: ExtractionResult) -> list[str]:
    """Which review-blocking fields are still unresolved."""
    dumped = result.fields.model_dump()
    return [name for name in REQUIRED_FOR_REVIEW if dumped.get(name) in (None, "")]


def build_questions(result: ExtractionResult) -> list[OpenQuestion]:
    """Merge extraction's own questions with one per missing required field.

    Deliberately ordered and de-duplicated so the vendor app can render them
    one at a time rather than as a wall of demands.
    """
    questions: list[OpenQuestion] = list(result.questions)
    seen = {(q.key, q.field_name) for q in questions}

    for name in missing_required(result):
        key = QUESTION_KEYS.get(name)
        if key is None:
            continue
        identity = (key, name)
        if identity in seen:
            continue
        seen.add(identity)
        questions.append(OpenQuestion(key=key, field_name=name))

    return questions


def _persist_draft(
    service_client: ServiceRoleClient, *, session_id: str, result: ExtractionResult
) -> None:
    """Upsert the structured draft and its per-field provenance."""
    payload: dict[str, Any] = {"session_id": session_id}
    dumped = result.fields.model_dump()
    # category_slug is resolved to category_id by M18-P05 against the real
    # category tree; the draft table stores what we know now.
    for name, value in dumped.items():
        if name == "category_slug":
            continue
        payload[name] = value

    existing = _rows(
        _table(service_client, DRAFT_TABLE)
        .select("session_id")
        .eq("session_id", session_id)
        .maybe_single()
        .execute()
    )
    if existing:
        _table(service_client, DRAFT_TABLE).update(payload).eq(
            "session_id", session_id
        ).execute()
    else:
        _table(service_client, DRAFT_TABLE).insert(payload).execute()

    for entry in result.provenance:
        row = {
            "session_id": session_id,
            "field_name": entry.field_name,
            "source": entry.source.value,
            "confidence": entry.confidence,
            "model_ref": entry.model_ref,
        }
        prior = _rows(
            _table(service_client, PROVENANCE_TABLE)
            .select("session_id")
            .eq("session_id", session_id)
            .eq("field_name", entry.field_name)
            .maybe_single()
            .execute()
        )
        if prior:
            # A vendor correction (vendor_typed) must never be downgraded back
            # to rule/model by a later inbound message.
            if prior and str(prior[0].get("source")) == FieldSource.VENDOR_TYPED.value:
                continue
            _table(service_client, PROVENANCE_TABLE).update(row).eq(
                "session_id", session_id
            ).eq("field_name", entry.field_name).execute()
        else:
            _table(service_client, PROVENANCE_TABLE).insert(row).execute()


def _record_questions(
    service_client: ServiceRoleClient, *, session_id: str, questions: list[OpenQuestion]
) -> None:
    """Write follow-ups as DATA on the session. Nothing is sent anywhere."""
    _table(service_client, SESSIONS_TABLE).update(
        {"pending_requests": [q.model_dump() for q in questions]}
    ).eq("id", session_id).execute()


def find_duplicate_session(
    service_client: ServiceRoleClient, *, vendor_id: str, session_id: str, result: ExtractionResult
) -> str | None:
    """Return a near-identical earlier session for the same vendor, if any.

    A duplicate is *flagged for review*, never auto-merged and never
    auto-rejected — merging would silently destroy one of the vendor's drafts.
    """
    dumped = result.fields.model_dump()
    if any(dumped.get(key) in (None, "") for key in _DUPLICATE_KEYS):
        return None

    candidates = _rows(
        _table(service_client, DRAFT_TABLE)
        .select("session_id, title, price_ngwee")
        .eq("title", dumped["title"])
        .eq("price_ngwee", dumped["price_ngwee"])
        .execute()
    )
    for row in candidates:
        other = str(row.get("session_id") or "")
        if other and other != session_id:
            return other
    return None


def progress_session(
    service_client: ServiceRoleClient,
    *,
    session_id: str,
    vendor_id: str,
    text: str | None,
    category_slug: str | None = None,
    has_media: bool = False,
    model_payload: Any = None,
    model_ref: str = "",
    model_confidence: float | None = None,
) -> dict[str, Any]:
    """Extract, persist, and advance one intake session.

    Returns the session row. Sends nothing — see the module docstring.
    """
    result = extract_rules.extract_with_rules(
        text, category_slug=category_slug, has_media=has_media
    )

    # A model is optional and only fills gaps. If it is unavailable, over quota,
    # or kill-switched, the caller passes None and we proceed rules-only.
    if model_payload is not None:
        result = extract_rules.merge_model_suggestions(
            result, model_payload, model_ref=model_ref, confidence=model_confidence
        )

    _persist_draft(service_client, session_id=session_id, result=result)

    questions = build_questions(result)

    duplicate = find_duplicate_session(
        service_client, vendor_id=vendor_id, session_id=session_id, result=result
    )
    if duplicate is not None:
        questions.append(
            OpenQuestion(
                key="intake.question.possible_duplicate",
                params={"session_id": duplicate},
            )
        )

    if result.blocked:
        questions.append(
            OpenQuestion(
                key="intake.question.prohibited_class",
                params={"reason": result.prohibited_reason or "prohibited"},
            )
        )

    _record_questions(service_client, session_id=session_id, questions=questions)

    current = state_machine.load_session(service_client, session_id)
    from_status = str(current.get("status", ""))

    # A prohibited draft can never advance toward review, and a duplicate is
    # held for a human to look at rather than progressed automatically.
    ready = not questions and not result.blocked and duplicate is None
    target = (
        state_machine.READY_FOR_VENDOR_REVIEW if ready else state_machine.NEEDS_DETAILS
    )

    if from_status == target:
        return current

    if target not in state_machine.ALLOWED_TRANSITIONS.get(from_status, frozenset()):
        # Terminal or otherwise not advanceable — leave it alone rather than
        # forcing a transition the state machine forbids.
        logger.info("intake session not advanceable", extra={"session_id": session_id})
        return current

    return state_machine.transition(
        service_client, session_id=session_id, to_status=target
    )
