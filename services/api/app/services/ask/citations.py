from __future__ import annotations

from app.schemas.base import NgweeInt, StrictModel
from app.services.ask.retrieve import RetrievedDoc
from app.services.ask.sanitize import strip_foreign_urls
from app.services.notifications.templates.whatsapp import format_k
from pydantic import Field

# Entity kinds whose customer route needs a resolved public slug. Listings are
# filtered to routable rows by ``attach_route_slugs`` (standalone → /l/{id});
# services route by UUID.
_SLUG_REQUIRED_KINDS = frozenset({"product", "event", "vendor"})
_ROUTABLE_KINDS = frozenset({"product", "listing", "service", "event", "vendor"})


class CitationRef(StrictModel):
    entity_kind: str
    entity_id: str
    title: str
    price_display: str | None = None
    # Public route slug; the customer app builds the href (searchResultHref).
    slug: str | None = None
    in_stock: bool | None = None
    distance_km: float | None = None
    # Integer ngwee behind ``price_display`` (the audit log records exactly what was shown).
    price_min_ngwee: NgweeInt | None = None
    price_max_ngwee: NgweeInt | None = None
    # Locale-less customer paths (``/p/{slug}``…); the app prefixes the locale.
    href: str | None = None
    # Seller behind the cited item, resolved by ``enrich.attach_vendor_info``.
    vendor_id: str | None = None
    vendor_name: str | None = None
    vendor_slug: str | None = None
    vendor_href: str | None = None


def route_path(kind: str, entity_id: str, slug: str | None) -> str | None:
    """Locale-less customer path for an entity (mirrors the customer ``searchResultHref``)."""
    clean = slug.strip() if isinstance(slug, str) and slug.strip() else None
    if kind == "product":
        return f"/p/{clean}" if clean else None
    if kind == "listing":
        return f"/p/{clean}?listing={entity_id}" if clean else f"/l/{entity_id}"
    if kind == "service":
        return f"/s/{clean or entity_id}"
    if kind == "event":
        return f"/e/{clean}" if clean else None
    if kind == "vendor":
        return f"/v/{clean}" if clean else None
    return None


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


def is_linkable(doc: RetrievedDoc) -> bool:
    """A citation card must open a real page — drop kinds/rows we cannot route."""
    if doc.entity_kind not in _ROUTABLE_KINDS:
        return False
    if doc.entity_kind in _SLUG_REQUIRED_KINDS:
        return bool(doc.slug and doc.slug.strip())
    return True


def citation_from_doc(doc: RetrievedDoc) -> CitationRef:
    return CitationRef(
        entity_kind=doc.entity_kind,
        entity_id=doc.entity_id,
        title=doc.title,
        price_display=_price_display(doc),
        slug=doc.slug,
        in_stock=doc.in_stock,
        distance_km=doc.distance_km,
        price_min_ngwee=doc.price_min_ngwee,
        price_max_ngwee=doc.price_max_ngwee,
        href=route_path(doc.entity_kind, doc.entity_id, doc.slug),
    )


def citations_from_docs(docs: list[RetrievedDoc], *, limit: int = 6) -> list[CitationRef]:
    """Ranked result cards for the workflow / fallback paths (no model involved)."""
    cards: list[CitationRef] = []
    seen: set[str] = set()
    for doc in docs:
        if doc.entity_id in seen or not is_linkable(doc):
            continue
        cards.append(citation_from_doc(doc))
        seen.add(doc.entity_id)
        if len(cards) >= limit:
            break
    return cards


def validate_citations(
    *,
    answer_text: str,
    cited_entity_ids: list[str],
    retrieved_docs: list[RetrievedDoc],
) -> ValidatedAnswer:
    """Keep only citations that were retrieved AND link to a real page.

    Also strips any URL in the answer text that is not on our domain (a poisoned
    listing must not be able to make the assistant hand out an off-site link).
    """
    docs_by_id = {doc.entity_id: doc for doc in retrieved_docs}

    validated_citations: list[CitationRef] = []
    seen: set[str] = set()
    for entity_id in cited_entity_ids:
        doc = docs_by_id.get(entity_id)
        if doc is None or entity_id in seen or not is_linkable(doc):
            continue
        validated_citations.append(citation_from_doc(doc))
        seen.add(entity_id)

    return ValidatedAnswer(
        answer_text=strip_foreign_urls(answer_text),
        citations=validated_citations,
    )
