from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.base import StrictModel

# Major-unit ZMW amounts in user text → ngwee (integer).
_K_AMOUNT_RE = re.compile(
    r"(?:k\s*|kwacha\s*)?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_UNDER_RE = re.compile(
    r"\b(?:under|below|less\s+than|cheaper\s+than|max(?:imum)?)\b",
    re.IGNORECASE,
)
_OVER_RE = re.compile(
    r"\b(?:over|above|more\s+than|at\s+least|min(?:imum)?)\b",
    re.IGNORECASE,
)
_BETWEEN_RE = re.compile(
    r"\bbetween\b",
    re.IGNORECASE,
)

_CATEGORY_KEYWORDS: dict[str, str] = {
    "phone": "electronics/mobile-phones",
    "phones": "electronics/mobile-phones",
    "smartphone": "electronics/mobile-phones",
    "laptop": "electronics/laptops-computers",
    "chitenge": "fashion-beauty/chitenge-fabric",
    "chitange": "fashion-beauty/chitenge-fabric",
    "dress": "fashion-beauty/womens-clothing",
    "kitchen": "home-living/kitchenware",
    "electronics": "electronics",
    "event": "events",
    "events": "events",
    "service": "services",
    "services": "services",
}

_LOCATION_KEYWORDS: tuple[str, ...] = (
    "lusaka",
    "ndola",
    "kitwe",
    "livingstone",
    "chipata",
    "kabwe",
    "mongu",
    "solwezi",
)


class AskFilters(StrictModel):
    price_min_ngwee: int | None = None
    price_max_ngwee: int | None = None
    category_path: str | None = None
    location_term: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractedFilters:
    filters: AskFilters
    search_query: str


def _parse_amount_to_ngwee(raw: str) -> int:
    cleaned = raw.replace(",", "")
    if "." in cleaned:
        major, minor = cleaned.split(".", 1)
        major_units = int(major or "0")
        minor_padded = (minor + "00")[:2]
        return major_units * 100 + int(minor_padded)
    return int(cleaned) * 100


def _extract_price_bounds(query: str) -> tuple[int | None, int | None]:
    lowered = query.lower()
    amounts = [_parse_amount_to_ngwee(match.group(1)) for match in _K_AMOUNT_RE.finditer(lowered)]
    if not amounts:
        return None, None

    if _BETWEEN_RE.search(lowered) and len(amounts) >= 2:
        low, high = sorted(amounts[:2])
        return low, high

    if _UNDER_RE.search(lowered):
        return None, amounts[0]

    if _OVER_RE.search(lowered):
        return amounts[0], None

    if len(amounts) == 1:
        # Single price mention without qualifier — treat as soft max for "K500 phones".
        return None, amounts[0]

    if len(amounts) >= 2:
        low, high = sorted(amounts[:2])
        return low, high

    return None, None


def _extract_category_path(query: str) -> str | None:
    tokens = re.findall(r"[a-z]+", query.lower())
    for token in tokens:
        if token in _CATEGORY_KEYWORDS:
            return _CATEGORY_KEYWORDS[token]
    return None


def _extract_location_term(query: str) -> str | None:
    lowered = query.lower()
    for location in _LOCATION_KEYWORDS:
        if location in lowered:
            return location
    return None


def extract_filters(query: str) -> ExtractedFilters:
    """Heuristic structured filter extraction from natural-language ask queries."""
    trimmed = query.strip()
    price_min, price_max = _extract_price_bounds(trimmed)
    category_path = _extract_category_path(trimmed)
    location_term = _extract_location_term(trimmed)

    search_query = trimmed
    if location_term and location_term not in search_query.lower():
        search_query = f"{search_query} {location_term}"

    return ExtractedFilters(
        filters=AskFilters(
            price_min_ngwee=price_min,
            price_max_ngwee=price_max,
            category_path=category_path,
            location_term=location_term,
        ),
        search_query=search_query.strip(),
    )
