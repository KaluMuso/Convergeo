"""Workflow-first intent router for Ask Vergeo.

Deterministic intents are answered WITHOUT the LLM (no quota, no spend):

* ``order_status`` — "where is my order" for a signed-in user (own orders only)
* ``faq``          — delivery / COD / escrow / payment / pickup / returns (static i18n)
* ``near_me``      — "X near me" (geo-reranked search) or "shops near me" (branches)
* ``cheapest``     — "cheapest X" (search, sorted by lowest price)
* ``price_stock``  — "how much is X" / "is X in stock"

Answers are returned as i18n keys + params (``ai.intent.*``) so the UI renders them in
the viewer's locale; ``answer_text`` is an English rendering for non-UI API clients.
Anything not matched falls through to the RAG + LLM path.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast

from app.schemas.base import StrictModel
from app.services.ask.citations import CitationRef, citations_from_docs
from app.services.ask.faq import FaqRef, match_faq
from app.services.ask.filters import extract_filters
from app.services.ask.retrieve import RetrievedDoc, top_k
from app.services.notifications.templates.whatsapp import format_k

logger = logging.getLogger(__name__)

WorkflowRetriever = Callable[..., Awaitable[list[RetrievedDoc]]]


class Intent(StrEnum):
    ORDER_STATUS = "order_status"
    FAQ = "faq"
    NEAR_ME = "near_me"
    CHEAPEST = "cheapest"
    PRICE_STOCK = "price_stock"
    NONE = "none"


def _p(expr: str) -> re.Pattern[str]:
    return re.compile(expr, re.IGNORECASE)


_ORDER_PATTERNS = (
    _p(r"\b(?:my|our)\s+(?:last\s+|latest\s+|recent\s+)?(?:order|parcel|package|purchase)s?\b"),
    _p(r"\border\s+(?:status|number|tracking|update)\b"),
    _p(r"\btrack(?:ing)?\b.{0,20}\b(?:order|parcel|package)\b"),
    _p(r"\bwhere\s+is\s+my\b"),
    _p(r"\bord-[a-z0-9]{3,}\b"),
)
_NEAR_PATTERNS = (
    _p(r"\bnear\s*(?:me|by|here|my\s+(?:location|area|place))\b"),
    _p(r"\bnearby\b"),
    _p(r"\b(?:close\s+to|around)\s+me\b"),
    _p(r"\b(?:closest|nearest)\b"),
)
_CHEAPEST_PATTERNS = (
    _p(r"\bcheap(?:est|er)?\b"),
    _p(r"\blowest\s+(?:price|cost)\b"),
    _p(r"\bleast\s+expensive\b"),
    _p(r"\bmost\s+affordable\b"),
    _p(r"\bbest\s+price\b"),
)
_PRICE_PATTERNS = (
    _p(r"\bhow\s+much\b"),
    _p(r"\bprice\s+(?:of|for)\b"),
    _p(r"\bwhat(?:'s|\s+is)\s+the\s+(?:price|cost)\b"),
    _p(r"\b(?:price|cost)\s*\??\s*$"),
    _p(r"\bcost\s+of\b"),
)
_STOCK_PATTERNS = (
    _p(r"\bin\s+stock\b"),
    _p(r"\bout\s+of\s+stock\b"),
    _p(r"\b(?:still\s+)?availab(?:le|ility)\b"),
    _p(r"\bdo\s+you\s+(?:have|sell|stock)\b"),
)

# Phrases removed to get the product terms ("how much is the itel a70" → "itel a70").
_STRIP_PHRASES = tuple(
    _p(expr)
    for expr in (
        r"\bnear\s*(?:me|by|here|my\s+(?:location|area|place))\b",
        r"\bnearby\b",
        r"\b(?:close\s+to|around)\s+me\b",
        r"\b(?:closest|nearest)\b",
        r"\bcheap(?:est|er)?\b",
        r"\blowest\s+(?:price|cost)\b",
        r"\bleast\s+expensive\b",
        r"\bmost\s+affordable\b",
        r"\bbest\s+price\b",
        r"\bhow\s+much\s+(?:is|are|does|do|for|would)?\b",
        r"\bwhat(?:'s|\s+is)\s+the\s+(?:price|cost)\s+(?:of|for)?\b",
        r"\b(?:price|cost)\s+(?:of|for)\b",
        r"\bin\s+stock\b",
        r"\bout\s+of\s+stock\b",
        r"\b(?:still\s+)?availab(?:le|ility)\b",
        r"\bdo\s+you\s+(?:have|sell|stock)\b",
        r"\b(?:can\s+i|where\s+(?:can|do)\s+i)\s+(?:buy|get|find)\b",
    )
)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "it",
        "its",
        "of",
        "for",
        "me",
        "my",
        "i",
        "you",
        "please",
        "pls",
        "plz",
        "any",
        "some",
        "what",
        "whats",
        "which",
        "show",
        "find",
        "get",
        "buy",
        "cost",
        "costs",
        "price",
        "prices",
        "much",
        "does",
        "do",
        "on",
        "at",
        "to",
        "in",
        "and",
        "or",
        "there",
        "here",
        "one",
        "ones",
        "available",
        "shop",
        "shops",
        "store",
        "stores",
        "vendor",
        "vendors",
        "seller",
        "sellers",
        "place",
        "places",
        "where",
        "can",
        "with",
        "now",
        "today",
        "currently",
    }
)
_LOCATION_SHOP_WORDS = frozenset({"shop", "shops", "store", "stores", "vendor", "vendors"})
# Words that belong to the FAQ topics themselves — "how much is delivery" is a FAQ,
# not a product search for "delivery".
_FAQ_VOCAB = frozenset(
    {
        "delivery",
        "deliver",
        "delivered",
        "deliveries",
        "shipping",
        "fee",
        "fees",
        "charge",
        "charges",
        "cod",
        "cash",
        "escrow",
        "refund",
        "refunds",
        "return",
        "returns",
        "pickup",
        "pick",
        "up",
        "collect",
        "collection",
        "payment",
        "payments",
        "pay",
        "mobile",
        "money",
        "momo",
        "mtn",
        "airtel",
        "zamtel",
        "card",
        "cards",
        "visa",
        "mastercard",
        "lusaka",
        "ndola",
        "kitwe",
        "livingstone",
        "chipata",
        "kabwe",
        "mongu",
        "solwezi",
        "zambia",
        "safe",
        "work",
        "works",
        "long",
        "take",
        "takes",
        "how",
        "when",
        "why",
        "who",
        "will",
        "be",
        "time",
        "policy",
        "dispute",
        "damaged",
        "broken",
        "wrong",
        "item",
        "order",
        "orders",
    }
)


@dataclass(frozen=True, slots=True)
class IntentMatch:
    intent: Intent
    terms: str
    stock_question: bool = False
    faq: tuple[FaqRef, ...] = ()


class OrderRef(StrictModel):
    id: str
    ref: str
    status: str
    status_key: str
    fulfilment: str | None = None
    created_at: str | None = None


@dataclass(slots=True)
class WorkflowResult:
    intent: Intent
    answer_key: str
    answer_text: str
    answer_params: dict[str, str | int] = field(default_factory=dict)
    citations: list[CitationRef] = field(default_factory=list)
    faq: list[FaqRef] = field(default_factory=list)
    orders: list[OrderRef] = field(default_factory=list)
    needs_location: bool = False
    sign_in_required: bool = False


KNOWN_ORDER_STATUSES = frozenset(
    {
        "placed",
        "confirmed",
        "processing",
        "ready",
        "shipped",
        "delivered",
        "completed",
        "cancelled",
    }
)


def _any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def product_terms(query: str) -> str:
    """Strip intent phrases + stopwords, keeping product/location words."""
    text = query
    for pattern in _STRIP_PHRASES:
        text = pattern.sub(" ", text)
    tokens = re.findall(r"[0-9a-zA-Z][0-9a-zA-Z'+.-]*", text)
    kept = [
        token.strip(".'")
        for token in tokens
        if token.lower().strip(".'") not in _STOPWORDS and token.strip(".'")
    ]
    return " ".join(kept).strip()


def _looks_like_product_search(query: str) -> bool:
    extracted = extract_filters(query)
    filters = extracted.filters
    return bool(
        filters.category_path
        or filters.price_min_ngwee is not None
        or filters.price_max_ngwee is not None
    )


def classify(query: str) -> IntentMatch:
    """Pick the single deterministic intent for ``query`` (or ``NONE``)."""
    text = " ".join(query.split())
    if not text:
        return IntentMatch(Intent.NONE, "")

    if _any(_ORDER_PATTERNS, text):
        return IntentMatch(Intent.ORDER_STATUS, "")

    faq = tuple(match_faq(text))
    shopping_signal = (
        _any(_NEAR_PATTERNS, text)
        or _any(_CHEAPEST_PATTERNS, text)
        or _any(_PRICE_PATTERNS, text)
        or _looks_like_product_search(text)
    )
    terms = product_terms(text)
    non_faq_terms = [token for token in terms.lower().split() if token not in _FAQ_VOCAB]
    if faq and (not shopping_signal or not non_faq_terms):
        return IntentMatch(Intent.FAQ, "", faq=faq)

    if _any(_NEAR_PATTERNS, text):
        return IntentMatch(Intent.NEAR_ME, terms, faq=faq)
    if _any(_CHEAPEST_PATTERNS, text) and terms:
        return IntentMatch(Intent.CHEAPEST, terms, faq=faq)
    stock_question = _any(_STOCK_PATTERNS, text)
    if (_any(_PRICE_PATTERNS, text) or stock_question) and terms:
        return IntentMatch(Intent.PRICE_STOCK, terms, stock_question=stock_question, faq=faq)
    return IntentMatch(Intent.NONE, terms, faq=faq)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _price_text(doc: RetrievedDoc) -> str | None:
    if doc.price_min_ngwee is None:
        return format_k(doc.price_max_ngwee) if doc.price_max_ngwee is not None else None
    return format_k(doc.price_min_ngwee)


async def _search(
    retriever: WorkflowRetriever,
    client: Any,
    *,
    terms: str,
    limit: int,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> list[RetrievedDoc]:
    extracted = extract_filters(terms)
    return await retriever(
        client,
        query=extracted.search_query,
        filters=extracted.filters,
        limit=limit,
        use_embedding=False,
        user_lat=user_lat,
        user_lng=user_lng,
    )


def _handle_faq(match: IntentMatch) -> WorkflowResult:
    return WorkflowResult(
        intent=Intent.FAQ,
        answer_key="ai.intent.faq",
        answer_text="Here's how that works on Vergeo5.",
        faq=list(match.faq),
    )


def _handle_order_status(client: Any, *, user_id: str | None) -> WorkflowResult:
    if user_id is None:
        return WorkflowResult(
            intent=Intent.ORDER_STATUS,
            answer_key="ai.intent.orderSignIn",
            answer_text="Sign in to see your order status.",
            sign_in_required=True,
        )

    # Service client + explicit customer_id filter = the caller's own orders only.
    response = (
        client.table("orders")
        .select("id, status, fulfilment, created_at")
        .eq("customer_id", user_id)
        .order("created_at", desc=True)
        .limit(3)
        .execute()
    )
    orders: list[OrderRef] = []
    for row in _rows(response):
        order_id = row.get("id")
        if not order_id:
            continue
        status = str(row.get("status") or "")
        status_key = status if status in KNOWN_ORDER_STATUSES else "unknown"
        orders.append(
            OrderRef(
                id=str(order_id),
                ref=str(order_id).split("-")[0].upper(),
                status=status,
                status_key=f"ai.orderStatus.{status_key}",
                fulfilment=str(row["fulfilment"]) if row.get("fulfilment") else None,
                created_at=str(row["created_at"]) if row.get("created_at") else None,
            )
        )

    if not orders:
        return WorkflowResult(
            intent=Intent.ORDER_STATUS,
            answer_key="ai.intent.orderNone",
            answer_text="You don't have any orders yet.",
        )
    return WorkflowResult(
        intent=Intent.ORDER_STATUS,
        answer_key="ai.intent.orderLatest",
        answer_text=f"Your latest order is {orders[0].status}.",
        answer_params={"count": len(orders)},
        orders=orders,
    )


async def _handle_price_stock(
    retriever: WorkflowRetriever, client: Any, match: IntentMatch
) -> WorkflowResult | None:
    docs = await _search(retriever, client, terms=match.terms, limit=6)
    cards = citations_from_docs(docs, limit=4)
    if not cards:
        return None
    linkable = {card.entity_id for card in cards}
    top = next(doc for doc in docs if doc.entity_id in linkable)
    price = _price_text(top)
    params: dict[str, str | int] = {"title": top.title}
    if price is not None:
        params["price"] = price

    if top.in_stock is False:
        key, text = "ai.intent.outOfStock", f"{top.title} is currently out of stock."
    elif match.stock_question and top.in_stock is True:
        if price is not None:
            key, text = "ai.intent.inStockPrice", f"{top.title} is in stock at {price}."
        else:
            key, text = "ai.intent.inStock", f"{top.title} is in stock."
    elif price is not None:
        key, text = "ai.intent.price", f"{top.title} costs {price}."
    else:
        key, text = "ai.intent.priceUnknown", f"See {top.title} for the current price."

    return WorkflowResult(
        intent=Intent.PRICE_STOCK,
        answer_key=key,
        answer_text=text,
        answer_params=params,
        citations=cards,
    )


async def _handle_cheapest(
    retriever: WorkflowRetriever, client: Any, match: IntentMatch
) -> WorkflowResult | None:
    docs = await _search(retriever, client, terms=match.terms, limit=20)
    priced = [doc for doc in docs if doc.price_min_ngwee is not None]
    priced.sort(key=lambda doc: (cast(int, doc.price_min_ngwee), -doc.rrf_score))
    cards = citations_from_docs(priced, limit=5)
    if not cards:
        return None
    top = next(doc for doc in priced if doc.entity_id == cards[0].entity_id)
    price = _price_text(top) or ""
    return WorkflowResult(
        intent=Intent.CHEAPEST,
        answer_key="ai.intent.cheapest",
        answer_text=f"The lowest price for {match.terms} is {top.title} at {price}.",
        answer_params={"query": match.terms, "title": top.title, "price": price},
        citations=cards,
    )


def _nearby_vendor_cards(client: Any, *, lat: float, lng: float) -> list[CitationRef]:
    from app.services.search.nearby import run_nearby

    nearby = run_nearby(client, lat=lat, lng=lng, page_size=6)
    cards: list[CitationRef] = []
    seen: set[str] = set()
    for branch in nearby.results:
        if branch.vendor_id in seen or not branch.vendor_slug:
            continue
        seen.add(branch.vendor_id)
        cards.append(
            CitationRef(
                entity_kind="vendor",
                entity_id=branch.vendor_id,
                title=branch.vendor_name,
                slug=branch.vendor_slug,
                distance_km=branch.distance_km,
            )
        )
    return cards


async def _handle_near_me(
    retriever: WorkflowRetriever,
    client: Any,
    match: IntentMatch,
    *,
    lat: float | None,
    lng: float | None,
) -> WorkflowResult:
    if lat is None or lng is None:
        return WorkflowResult(
            intent=Intent.NEAR_ME,
            answer_key="ai.intent.nearMeNeedsLocation",
            answer_text="Share your location to see what's near you.",
            needs_location=True,
        )

    content_terms = " ".join(
        token for token in match.terms.split() if token.lower() not in _LOCATION_SHOP_WORDS
    )
    if not content_terms:
        cards = _nearby_vendor_cards(client, lat=lat, lng=lng)
        return WorkflowResult(
            intent=Intent.NEAR_ME,
            answer_key="ai.intent.nearbyVendors" if cards else "ai.intent.nearMeNone",
            answer_text="Here are vendors near you." if cards else "Nothing found near you yet.",
            citations=cards,
        )

    docs = await _search(
        retriever, client, terms=content_terms, limit=10, user_lat=lat, user_lng=lng
    )
    with_distance = [doc for doc in docs if doc.distance_km is not None]
    without = [doc for doc in docs if doc.distance_km is None]
    with_distance.sort(key=lambda doc: cast(float, doc.distance_km))
    cards = citations_from_docs([*with_distance, *without], limit=6)
    return WorkflowResult(
        intent=Intent.NEAR_ME,
        answer_key="ai.intent.nearMe" if cards else "ai.intent.nearMeNone",
        answer_text=(
            f"Closest matches for {content_terms}." if cards else "Nothing found near you yet."
        ),
        answer_params={"query": content_terms},
        citations=cards,
    )


async def run_workflow(
    client: Any,
    *,
    query: str,
    user_id: str | None,
    lat: float | None = None,
    lng: float | None = None,
    retriever: WorkflowRetriever | None = None,
) -> WorkflowResult | None:
    """Answer a deterministic intent, or return None to fall through to the LLM."""
    match = classify(query)
    search = retriever or top_k
    if match.intent is Intent.ORDER_STATUS:
        return _handle_order_status(client, user_id=user_id)
    if match.intent is Intent.FAQ:
        return _handle_faq(match)
    if match.intent is Intent.NEAR_ME:
        return await _handle_near_me(search, client, match, lat=lat, lng=lng)
    if match.intent is Intent.CHEAPEST:
        return await _handle_cheapest(search, client, match)
    if match.intent is Intent.PRICE_STOCK:
        return await _handle_price_stock(search, client, match)
    return None


async def fallback_results(
    client: Any,
    *,
    query: str,
    retriever: WorkflowRetriever | None = None,
    limit: int = 6,
) -> tuple[list[CitationRef], list[FaqRef]]:
    """Ranked keyword search results + FAQ matches; never raises."""
    faq = match_faq(query)
    search = retriever or top_k
    try:
        extracted = extract_filters(product_terms(query) or query)
        docs = await search(
            client,
            query=extracted.search_query,
            filters=extracted.filters,
            limit=limit,
            use_embedding=False,
        )
        cards = citations_from_docs(docs, limit=limit)
    except Exception:  # noqa: BLE001 — the fallback must render even if search is down
        logger.warning("Ask fallback search failed", exc_info=True)
        cards = []
    return cards, faq


__all__ = [
    "Intent",
    "IntentMatch",
    "OrderRef",
    "WorkflowResult",
    "classify",
    "fallback_results",
    "product_terms",
    "run_workflow",
]
