"""Post-retrieval relevance guard for ``search_rrf`` hits.

``search_rrf`` fuses an FTS lane, a trigram lane and a vector lane. The vector lane
has no distance cutoff: it ranks the nearest 100 documents for *any* query, so a
short query such as ``t-shirt`` or ``phone`` pulls in unrelated documents (event
ticket tiers, vendor profiles) purely because they are the "least far" vectors. A
short query carries too little context for the semantic lane to be trusted on its
own, so for it a hit must also be a lexical (or near-typo) match.

The guard is deliberately conservative for long, natural-language queries (the
semantic lane is genuinely useful there) and for hits that already match lexically.
It also hides catalogue products that have no active vendor offer: the product
search document carries ``price_min_ngwee = NULL`` exactly when no active listing
from an active vendor exists, and such a product's page is a dead end.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.search import SearchHit

# Queries with at most this many significant tokens are "short": lexical match required.
SHORT_QUERY_MAX_TOKENS = 3
# Tokens shorter than this are noise ("a", "of", "to") and never count as evidence.
MIN_TOKEN_LENGTH = 2
# Typo tolerance for a query token against a document word (chitange ~ chitenge).
FUZZY_TOKEN_RATIO = 0.8
# Fuzzy comparison is only meaningful for tokens long enough to carry a typo.
MIN_FUZZY_TOKEN_LENGTH = 4

_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
# Longest-first so "plumbers" -> "plumb" rather than "plumber".
_SUFFIXES = ("ing", "ers", "er", "es", "s")
MIN_STEM_LENGTH = 3


def tokenize(text: str) -> list[str]:
    """Lower-cased alphanumeric tokens (``t-shirt`` -> ``t``, ``shirt``)."""
    return [token for token in _WORD_RE.findall(text.lower()) if token]


def significant_tokens(*queries: str) -> list[str]:
    seen: dict[str, None] = {}
    for query in queries:
        for token in tokenize(query):
            if len(token) >= MIN_TOKEN_LENGTH:
                seen.setdefault(token, None)
    return list(seen)


def stem(token: str) -> str:
    """Crude plural / agent-noun stem so "phones" and "plumber" match "phone"/"plumbing"."""
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= MIN_STEM_LENGTH:
            return token[: -len(suffix)]
    return token


def is_short_query(query: str) -> bool:
    tokens = significant_tokens(query)
    return 0 < len(tokens) <= SHORT_QUERY_MAX_TOKENS


def _hit_text(hit: SearchHit) -> str:
    parts = [hit.title, hit.body or "", hit.category_path or ""]
    parts.extend(hit.locale_terms or [])
    return " ".join(parts).lower()


def hit_matches_lexically(hit: SearchHit, tokens: list[str]) -> bool:
    """True when any query token appears in, or is a near-typo of, the hit's text."""
    if not tokens:
        return True
    haystack = _hit_text(hit)
    words = set(tokenize(haystack))
    # Compact form so "t-shirt" matches "tshirt" and "T Shirt" ("tshirt" vs "t shirt").
    compact = re.sub(r"[^a-z0-9]", "", haystack)
    for token in tokens:
        base = stem(token)
        if token in haystack or token in compact or base in haystack:
            return True
        if len(token) >= MIN_FUZZY_TOKEN_LENGTH:
            for word in words:
                if abs(len(word) - len(token)) <= 2 and (
                    SequenceMatcher(None, token, word).ratio() >= FUZZY_TOKEN_RATIO
                ):
                    return True
    return False


def has_active_offer(hit: SearchHit) -> bool:
    """Whether a hit is worth showing from the "is anything buyable?" angle.

    Only canonical *product* documents can be offer-less; services, events, vendors
    and per-listing documents are never dropped by this check.
    """
    if hit.entity_kind != "product":
        return True
    return hit.price_min_ngwee is not None


def apply_relevance_guard(
    hits: list[SearchHit],
    *,
    query: str,
    expanded_query: str = "",
) -> list[SearchHit]:
    """Drop offer-less catalogue products and, for short queries, non-lexical hits.

    ``query`` and ``expanded_query`` (synonym expansion, e.g. Bemba/Nyanja aliases)
    both contribute tokens, so a hit matching only through an alias still survives.
    """
    if not hits:
        return hits

    kept = [hit for hit in hits if has_active_offer(hit)]
    if not query.strip() or not is_short_query(query):
        return kept

    tokens = significant_tokens(query, expanded_query)
    return [hit for hit in kept if hit_matches_lexically(hit, tokens)]
