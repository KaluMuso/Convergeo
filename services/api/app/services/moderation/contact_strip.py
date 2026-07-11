"""Pre-acceptance contact-info stripping (M11-P06).

Platform-disintermediation guard: before a quote is accepted, buyers and
providers must not exchange direct contact details (phone, WhatsApp, email)
so the transaction stays inside Vergeo5 escrow. This util detects Zambian
phone patterns (incl. spaced/dotted/spelled evasion), WhatsApp/`wa.me`
links and emails, replaces each hit with a server-side notice token, and
returns the stripped originals for moderation logging.

Prices such as ``K970`` / ``ZMW 1,200`` / ``50000 kwacha`` must survive —
the phone matcher only fires on Zambian-mobile-shaped digit runs and never
starts inside an alphanumeric currency prefix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Server-side token — the counterparty never sees the raw contact span.
# Kept out of services.json (owned by M11-P04 this wave); this constant is the
# single source for the placeholder used in cleaned quote messages.
NOTICE_TOKEN = "[contact hidden — keep chat on Vergeo5]"

# Email addresses.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# WhatsApp / wa.me deep links (with or without scheme).
_LINK_RE = re.compile(
    r"(?:https?://)?(?:wa\.me|(?:chat\.|api\.)?whatsapp\.com)/\S+",
    re.IGNORECASE,
)

# Spelled-out digit runs (evasion), e.g. "zero nine seven one two three ...".
# Requires >= 6 consecutive number-words so ordinary prose ("one or two") is safe.
_DIGIT_WORD = r"(?:zero|one|two|three|four|five|six|seven|eight|nine|oh|nought)"
_SPELLED_RE = re.compile(
    rf"\b(?:{_DIGIT_WORD}\b[\s,.\-]*){{6,}}",
    re.IGNORECASE,
)

# Digit-based phone candidate: a leading digit (optionally +) followed by >= 5
# groups of "up to 3 separators + a digit". The bounded separator run means two
# adjacent phone numbers are matched separately (not merged into one invalid
# blob), while "09 7 1 234 567" and "09.7.1.234.567" collapse to one hit.
# The lookbehind forbids starting inside an alphanumeric run, so a currency
# prefix like "K970" never yields a "970" candidate.
_PHONE_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9])\+?\d(?:[\s.\-]{0,3}\d){5,}")

# Belt-and-suspenders price guard: skip a candidate whose immediate prefix is a
# currency marker (covers "K 970" / "ZMW 970" where a space separates them).
_CURRENCY_PREFIX_RE = re.compile(r"(?:ZMW|K)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class StripResult:
    """Outcome of :func:`strip_contacts`."""

    clean_text: str
    stripped_spans: list[str]
    hit_count: int


def _digits_only(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def _is_zambian_phone(digits: str) -> bool:
    """True for Zambian mobile shapes; rejects prices / short numeric runs.

    Normalization is implicit: all separators are already stripped, so
    ``09 7 1 234 567`` and ``09.7.1.234.567`` reduce to the same digits.
    """
    if digits.startswith("260"):
        rest = digits[3:]
        return len(rest) == 9 and rest[0] in "79"
    if digits.startswith("0"):
        return len(digits) == 10 and digits[1] in "79"
    if len(digits) == 9 and digits[0] in "79":
        return True
    return False


def _phone_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _PHONE_CANDIDATE_RE.finditer(text):
        prefix = text[max(0, match.start() - 4) : match.start()]
        if _CURRENCY_PREFIX_RE.search(prefix):
            continue
        if not _is_zambian_phone(_digits_only(match.group())):
            continue
        spans.append((match.start(), match.end()))
    return spans


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def strip_contacts(text: str | None) -> StripResult:
    """Strip contact info from ``text``, replacing each hit with the notice token.

    Returns cleaned text, the raw stripped spans (for moderation logging), and
    the number of distinct hits. Overlapping matches (e.g. a phone inside a
    ``wa.me`` link) count once.
    """
    if not text:
        return StripResult(clean_text=text or "", stripped_spans=[], hit_count=0)

    spans: list[tuple[int, int]] = []
    for regex in (_EMAIL_RE, _LINK_RE, _SPELLED_RE):
        spans.extend((m.start(), m.end()) for m in regex.finditer(text))
    spans.extend(_phone_spans(text))

    if not spans:
        return StripResult(clean_text=text, stripped_spans=[], hit_count=0)

    merged = _merge_spans(spans)
    stripped_spans = [text[start:end].strip() for start, end in merged]

    parts: list[str] = []
    cursor = 0
    for start, end in merged:
        parts.append(text[cursor:start])
        parts.append(NOTICE_TOKEN)
        cursor = end
    parts.append(text[cursor:])

    return StripResult(
        clean_text="".join(parts),
        stripped_spans=stripped_spans,
        hit_count=len(merged),
    )
