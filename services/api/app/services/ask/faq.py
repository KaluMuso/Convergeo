"""Static delivery / COD / escrow / payment FAQ for Ask Vergeo.

The copy itself lives in the ``ai`` i18n namespace (``ai.faq.<id>.q`` / ``.a``); the
API only returns keys, so every locale renders its own translation and no
user-facing string is hardcoded server-side. Matching is keyword based — no model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.base import StrictModel


class FaqRef(StrictModel):
    id: str
    question_key: str
    answer_key: str


@dataclass(frozen=True, slots=True)
class _FaqEntry:
    id: str
    patterns: tuple[re.Pattern[str], ...]


def _p(expr: str) -> re.Pattern[str]:
    return re.compile(expr, re.IGNORECASE)


# Order matters: the first entries win ties when several match.
_FAQ_ENTRIES: tuple[_FaqEntry, ...] = (
    _FaqEntry(
        "cod",
        (
            _p(r"\bcash\s+on\s+delivery\b"),
            _p(r"\bcod\b"),
            _p(r"\bpay\s+(?:on|at|upon)\s+(?:delivery|arrival|the\s+door)\b"),
            _p(r"\bpay\s+(?:in\s+)?cash\b"),
        ),
    ),
    _FaqEntry(
        "escrow",
        (
            _p(r"\bescrow\b"),
            _p(r"\b(?:is|are)\s+(?:my\s+)?(?:money|payment)s?\s+safe\b"),
            _p(r"\bheld\s+by\b"),
            _p(r"\bwhen\s+(?:does|do|is)\s+the\s+(?:vendor|seller)\s+(?:get\s+)?paid\b"),
            _p(r"\b(?:scam|fraud|trust(?:ed|worthy)?)\b"),
            _p(r"\bbuyer\s+protection\b"),
        ),
    ),
    _FaqEntry(
        "delivery",
        (
            _p(r"\bdeliver(?:y|ies|ed)?\b"),
            _p(r"\bshipping\b"),
            _p(r"\bdelivery\s+fee\b"),
            _p(r"\bhow\s+long\b.{0,30}\b(?:arrive|take|get\s+here)\b"),
        ),
    ),
    _FaqEntry(
        "pickup",
        (
            _p(r"\bpick\s*-?\s*up\b"),
            _p(r"\bcollect(?:ion)?\b.{0,20}\b(?:order|shop|store)\b"),
            _p(r"\boutside\s+lusaka\b"),
            _p(r"\b(?:ndola|kitwe|livingstone|chipata|kabwe|mongu|solwezi)\b.{0,20}\bdeliver"),
        ),
    ),
    _FaqEntry(
        "payment",
        (
            _p(r"\bmobile\s+money\b"),
            _p(r"\b(?:mtn|airtel|zamtel)\b"),
            _p(r"\bmomo\b"),
            _p(r"\bpayment\s+(?:method|option)s?\b"),
            _p(r"\bhow\s+(?:do|can)\s+i\s+pay\b"),
            _p(r"\b(?:visa|mastercard|card\s+payment)\b"),
        ),
    ),
    _FaqEntry(
        "returns",
        (
            _p(r"\brefund(?:s|ed)?\b"),
            _p(r"\breturn(?:s|ing)?\b.{0,20}\b(?:item|order|product|policy)\b"),
            _p(r"\breturn\s+policy\b"),
            _p(r"\b(?:damaged|broken|wrong\s+item|not\s+as\s+described)\b"),
            _p(r"\bdispute\b"),
        ),
    ),
)

FAQ_IDS: tuple[str, ...] = tuple(entry.id for entry in _FAQ_ENTRIES)


def faq_ref(faq_id: str) -> FaqRef:
    return FaqRef(
        id=faq_id,
        question_key=f"ai.faq.{faq_id}.q",
        answer_key=f"ai.faq.{faq_id}.a",
    )


def match_faq(query: str, *, limit: int = 2) -> list[FaqRef]:
    """Return up to ``limit`` FAQ entries whose patterns match ``query``."""
    text = " ".join(query.split())
    if not text:
        return []
    matches: list[FaqRef] = []
    for entry in _FAQ_ENTRIES:
        if any(pattern.search(text) for pattern in entry.patterns):
            matches.append(faq_ref(entry.id))
            if len(matches) >= limit:
                break
    return matches


__all__ = ["FAQ_IDS", "FaqRef", "faq_ref", "match_faq"]
