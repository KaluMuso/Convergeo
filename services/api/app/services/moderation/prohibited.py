"""Prohibited-category + keyword screen (M15-P08).

Zambia geo-fence (D8): certain categories/goods may not be listed on Vergeo5 —
salaula (used clothing), used phones, alcohol, pharma/prescription drugs, live
animals, and cement / heavy aggregates. This module is the single, reusable,
I/O-free screen enforced at every listing create/edit and CSV/JSON import entry
point so there is no bypass path.

Two layers:

* **Category block** — a config/constant set of prohibited category slugs
  (``PROHIBITED_CATEGORIES``). The caller may pass a category slug when it has
  one; product categories are additionally gated by the ``categories.prohibited``
  DB flag, so this layer is a defence-in-depth complement, not the only guard.
* **Keyword block** — a seed set of phrases (``PROHIBITED_KEYWORDS``) matched
  against the title + description. Matching is case- and diacritic-insensitive
  and anchored on word boundaries, so ``ALCOHOL``/``álcohol`` are caught while
  benign substrings (``placement`` for "cement", ``aggregated`` for "aggregate")
  never false-trigger. A trailing optional ``s`` catches simple plurals.

No ML/AI moderation, no network, no float/money — pure string logic.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Config/constant category slugs that may never be listed. Normalized to the
# same slug form used by ``_normalize_category`` (lowercase, hyphen-separated).
PROHIBITED_CATEGORIES: frozenset[str] = frozenset(
    {
        "salaula",
        "used-clothing",
        "used-phones",
        "used-phone",
        "alcohol",
        "pharma",
        "pharmaceuticals",
        "prescription-drugs",
        "live-animals",
        "livestock",
        "cement",
        "heavy-aggregates",
        "aggregates",
    }
)

# Seed set of prohibited phrases (single- or multi-word). Kept small and
# explicit; extend via config later. Each phrase is matched with flexible inner
# whitespace and an optional trailing plural "s".
PROHIBITED_KEYWORDS: frozenset[str] = frozenset(
    {
        "salaula",
        "used clothing",
        "used phone",
        "second hand phone",
        "alcohol",
        "beer",
        "spirits",
        "whisky",
        "vodka",
        "wine",
        "pharma",
        "pharmaceutical",
        "prescription drug",
        "prescription medicine",
        "antibiotic",
        "codeine",
        "tramadol",
        "live animal",
        "livestock",
        "cement",
        "heavy aggregate",
        "aggregate",
        "ballast",
    }
)


@dataclass(frozen=True)
class ProhibitedResult:
    """Outcome of :func:`screen_listing`."""

    allowed: bool
    reason: str | None = None
    matched: str | None = None


def _strip_diacritics(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize_text(value: str | None) -> str:
    """Lowercase, strip diacritics, collapse whitespace."""
    if not value:
        return ""
    stripped = _strip_diacritics(value).lower()
    return re.sub(r"\s+", " ", stripped).strip()


def _normalize_category(value: str | None) -> str:
    """Normalize a category identifier to slug form (``used phones`` → ``used-phones``)."""
    normalized = _normalize_text(value)
    if not normalized:
        return ""
    return re.sub(r"[\s_]+", "-", normalized)


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    words = _normalize_text(keyword).split()
    inner = r"\s+".join(re.escape(word) for word in words)
    # Word-boundary anchored; optional trailing plural on the final word.
    return re.compile(rf"\b{inner}s?\b")


# Precompiled once at import — the screen does no work per call beyond matching.
_KEYWORD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (keyword, _keyword_pattern(keyword)) for keyword in sorted(PROHIBITED_KEYWORDS)
)


def screen_listing(
    title: str | None = None,
    description: str | None = None,
    category: str | None = None,
) -> ProhibitedResult:
    """Screen a listing's category + text against the prohibited config.

    Returns a :class:`ProhibitedResult`; ``allowed`` is ``False`` with a
    ``reason`` (``"category"`` or ``"keyword"``) and the ``matched`` token when
    the listing hits a prohibited category or keyword.
    """
    category_slug = _normalize_category(category)
    if category_slug and category_slug in PROHIBITED_CATEGORIES:
        return ProhibitedResult(allowed=False, reason="category", matched=category_slug)

    haystack = _normalize_text(" ".join(part for part in (title, description) if part))
    if haystack:
        for keyword, pattern in _KEYWORD_PATTERNS:
            if pattern.search(haystack):
                return ProhibitedResult(allowed=False, reason="keyword", matched=keyword)

    return ProhibitedResult(allowed=True)
