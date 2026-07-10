from __future__ import annotations

from app.schemas.base import StrictModel
from app.services.ask.retrieve import RetrievedDoc
from app.services.notifications.templates.whatsapp import format_k
from pydantic import Field


class CitationRef(StrictModel):
    entity_kind: str
    entity_id: str
    title: str
    price_display: str | None = None


class ValidatedAnswer(StrictModel):
    answer_text: str
    citations: list[CitationRef] = Field(default_factory=list)


def _price_display(doc: RetrievedDoc) -> str | None:
    if doc.price_min_ngwee is None and doc.price_max_ngwee is None:
        return None
    if doc.price_min_ngwee is not None and doc.price_max_ngwee is not None:
        if doc.price_min_ngwee == doc.price_max_ngwee:
            return format_k(doc.price_min_ngwee)
        return f"{format_k(doc.price_min_ngwee)} – {format_k(doc.price_max_ngwee)}"
    if doc.price_min_ngwee is not None:
        return f"from {format_k(doc.price_min_ngwee)}"
    if doc.price_max_ngwee is not None:
        return f"up to {format_k(doc.price_max_ngwee)}"
    return None


def validate_citations(
    *,
    answer_text: str,
    cited_entity_ids: list[str],
    retrieved_docs: list[RetrievedDoc],
) -> ValidatedAnswer:
    """Strip any cited entity_id that was not present in the retrieved set."""
    allowed_ids = {doc.entity_id for doc in retrieved_docs}
    docs_by_id = {doc.entity_id: doc for doc in retrieved_docs}

    validated_citations: list[CitationRef] = []
    seen: set[str] = set()
    for entity_id in cited_entity_ids:
        if entity_id not in allowed_ids or entity_id in seen:
            continue
        doc = docs_by_id[entity_id]
        validated_citations.append(
            CitationRef(
                entity_kind=doc.entity_kind,
                entity_id=doc.entity_id,
                title=doc.title,
                price_display=_price_display(doc),
            )
        )
        seen.add(entity_id)

    return ValidatedAnswer(answer_text=answer_text, citations=validated_citations)
