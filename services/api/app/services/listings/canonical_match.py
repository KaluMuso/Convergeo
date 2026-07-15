"""Canonical-product match suggestions for CSV bulk import (M12-P06).

Given a vendor's listing title, suggest existing canonical products it might
attach to, so a bulk-imported listing can join the price-comparison view
("N vendors selling this product") instead of living as an unattached
standalone listing. Matches are SUGGESTIONS only — a listing is never
auto-attached; the vendor confirms in the import preview or supplies an
explicit `product_id` column. This mirrors the "admin confirms every merge"
moderation stance (M13-P03).

The trigram similarity mirrors PostgreSQL `pg_trgm.similarity(text, text)`
(same algorithm as `app.routers.admin_products.pg_trgm_similarity`, kept as a
small local copy so this service does not import a router module).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_MATCH_THRESHOLD = 0.3
DEFAULT_SUGGESTION_LIMIT = 3
# An exact (normalized) alias hit is a strong signal even when the trigram
# overlap of the surface strings is modest.
ALIAS_EXACT_SCORE = 0.95


class _TableClient(Protocol):
    def table(self, name: str) -> Any: ...


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    if len(padded) < 3:
        return set()
    return {padded[index : index + 3] for index in range(len(padded) - 2)}


def similarity(left: str, right: str) -> float:
    """pg_trgm similarity of two ALREADY-normalized strings (0.0–1.0)."""
    if left == right:
        return 1.0 if left else 0.0
    left_trigrams = _trigrams(left)
    right_trigrams = _trigrams(right)
    if not left_trigrams or not right_trigrams:
        return 0.0
    shared = len(left_trigrams & right_trigrams)
    return shared / max(len(left_trigrams), len(right_trigrams))


@dataclass(frozen=True, slots=True)
class CanonicalCandidate:
    product_id: str
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CanonicalSuggestion:
    product_id: str
    name: str
    score: float


def suggest_matches(
    title: str,
    candidates: list[CanonicalCandidate],
    *,
    limit: int = DEFAULT_SUGGESTION_LIMIT,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> list[CanonicalSuggestion]:
    """Top canonical matches for a listing title, best score first."""
    normalized_title = _normalize(title)
    if not normalized_title:
        return []

    scored: list[CanonicalSuggestion] = []
    for candidate in candidates:
        score = similarity(normalized_title, _normalize(candidate.name))
        for alias in candidate.aliases:
            normalized_alias = _normalize(alias)
            if not normalized_alias:
                continue
            if normalized_alias == normalized_title:
                score = max(score, ALIAS_EXACT_SCORE)
            else:
                score = max(score, similarity(normalized_title, normalized_alias))
        if score >= threshold:
            scored.append(
                CanonicalSuggestion(
                    product_id=candidate.product_id,
                    name=candidate.name,
                    score=round(score, 4),
                )
            )

    # Deterministic order: score desc, then name for stable ties.
    scored.sort(key=lambda item: (-item.score, item.name))
    return scored[:limit]


def load_active_candidates(client: _TableClient) -> list[CanonicalCandidate]:
    """Load active canonical products for matching (small catalog at launch)."""
    response = (
        client.table("products").select("id, name, aliases").eq("status", "active").execute()
    )
    data = getattr(response, "data", None)
    rows = data if isinstance(data, list) else []

    candidates: list[CanonicalCandidate] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        product_id = row.get("id")
        name = row.get("name")
        if not isinstance(product_id, str) or not isinstance(name, str):
            continue
        aliases_raw = row.get("aliases")
        aliases = (
            tuple(str(alias) for alias in aliases_raw if isinstance(alias, str))
            if isinstance(aliases_raw, list)
            else ()
        )
        candidates.append(
            CanonicalCandidate(product_id=product_id, name=name, aliases=aliases)
        )
    return candidates
