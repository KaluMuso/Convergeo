"""Non-blocking listing price review signals for admin (shared floor config with @vergeo/config)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

REVIEW_FLAG_PRICE_BELOW_CATEGORY_FLOOR = "price_below_category_floor"

_ACCESSORY_WORDS = r"(case|cover|charger|cable|protector|glass|holder|stand|strap|adapter|pouch)"
TITLE_FLOORS: tuple[tuple[re.Pattern[str], int, str], ...] = (
    (
        re.compile(
            r"^(?!.*\b"
            + _ACCESSORY_WORDS
            + r"\b).*\b(iphone|pixel\s?\d+|galaxy\s?[sazn]\d+|smartphone)\b",
            re.IGNORECASE,
        ),
        30_000,
        "phone",
    ),
    (
        re.compile(
            r"^(?!.*\b" + _ACCESSORY_WORDS + r"\b).*\b(macbook|laptop|thinkpad|chromebook)\b",
            re.IGNORECASE,
        ),
        100_000,
        "laptop",
    ),
)

_FLOORS_JSON = Path(__file__).resolve().parent / "listing-category-price-floors.json"


@lru_cache
def _floor_config() -> tuple[tuple[str, int, str], ...]:
    raw: dict[str, Any] = json.loads(_FLOORS_JSON.read_text(encoding="utf-8"))
    rows = raw.get("categoryPathPrefixes") or []
    out: list[tuple[str, int, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        prefix = row.get("pathPrefix")
        floor = row.get("floorNgwee")
        label = row.get("label")
        if (
            isinstance(prefix, str)
            and prefix.strip()
            and isinstance(floor, int)
            and floor >= 0
            and isinstance(label, str)
        ):
            out.append((prefix.strip(), floor, label.strip()))
    return tuple(out)


def category_floor_ngwee(
    *,
    category_path: str | None,
    title: str | None,
) -> tuple[int, str] | None:
    path = (category_path or "").strip()
    for prefix, floor, _label in _floor_config():
        if path == prefix or path.startswith(prefix + "/"):
            return floor, prefix
    if title:
        for pattern, floor, label in TITLE_FLOORS:
            if pattern.search(title):
                return floor, f"title:{label}"
    return None


def listing_price_review_flags(
    *,
    price_ngwee: int | None,
    category_path: str | None,
    title: str | None,
) -> list[str]:
    if not isinstance(price_ngwee, int) or price_ngwee < 0:
        return []
    floor = category_floor_ngwee(category_path=category_path, title=title)
    if floor is None:
        return []
    if price_ngwee < floor[0]:
        return [REVIEW_FLAG_PRICE_BELOW_CATEGORY_FLOOR]
    return []