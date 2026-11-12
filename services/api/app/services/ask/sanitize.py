"""Prompt-injection hardening for Ask Vergeo.

Two directions:

* **Into the model** — retrieved listing text is untrusted data. ``sanitize_doc_text``
  strips control characters, neutralises our fence markers (so a listing cannot
  "close" its block and smuggle instructions after it), removes every URL (the model
  never needs one to answer) and caps length.
* **Out of the model** — ``strip_foreign_urls`` removes any URL whose host is not on
  our domain allowlist from the answer text (markdown links keep their label), so a
  poisoned listing cannot make the assistant hand out a phishing link.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

DEFAULT_ALLOWED_LINK_HOSTS: tuple[str, ...] = ("vergeo5.com", "convergeo.com")

# Markdown link: [label](target)
_MD_LINK_RE = re.compile(r"\[([^\]\n]{0,200})\]\(\s*([^)\s]+)\s*\)")
# Bare URL: scheme://… or www.…  (stop at whitespace and common closing punctuation)
_URL_RE = re.compile(r"(?i)\b(?:https?://|ftp://|www\.)[^\s<>()\[\]{}\"']+")
# Scheme-less domains (evil.example/path) — only flagged when followed by a path or
# a well-known TLD, to avoid eating ordinary words like "e.g".
_BARE_DOMAIN_RE = re.compile(
    r"(?i)\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|co|zm|info|biz|xyz|top|app|link|ly|me)"
    r"(?:/[^\s<>()\[\]{}\"']*)?\b"
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")
_FENCE_RE = re.compile(r"<<<|>>>")
_TRAILING_PUNCT = ".,;:!?"


def allowed_link_hosts() -> tuple[str, ...]:
    raw = os.environ.get("ASK_ALLOWED_LINK_HOSTS", "").strip()
    if not raw:
        return DEFAULT_ALLOWED_LINK_HOSTS
    hosts = tuple(host.strip().lower().lstrip(".") for host in raw.split(",") if host.strip())
    return hosts or DEFAULT_ALLOWED_LINK_HOSTS


def _host_of(candidate: str) -> str | None:
    text = candidate.strip()
    if not re.match(r"(?i)^[a-z][a-z0-9+.-]*://", text):
        text = f"https://{text}"
    try:
        host = urlsplit(text).hostname
    except ValueError:
        return None
    return host.lower() if host else None


def is_allowed_url(candidate: str, *, hosts: tuple[str, ...] | None = None) -> bool:
    """True only for http(s) URLs on an allowlisted host (or a subdomain of one)."""
    allowed = hosts or allowed_link_hosts()
    text = candidate.strip()
    scheme_match = re.match(r"(?i)^([a-z][a-z0-9+.-]*):", text)
    if scheme_match and scheme_match.group(1).lower() not in {"http", "https"}:
        return False
    host = _host_of(text)
    if host is None:
        return False
    return any(host == base or host.endswith(f".{base}") for base in allowed)


def strip_foreign_urls(text: str, *, hosts: tuple[str, ...] | None = None) -> str:
    """Remove URLs not on our domain; keep markdown link labels."""
    allowed = hosts or allowed_link_hosts()

    def _md(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if is_allowed_url(target, hosts=allowed):
            return match.group(0)
        return label

    def _bare(match: re.Match[str]) -> str:
        url = match.group(0)
        trailing = ""
        while url and url[-1] in _TRAILING_PUNCT:
            trailing = url[-1] + trailing
            url = url[:-1]
        if is_allowed_url(url, hosts=allowed):
            return match.group(0)
        return trailing

    cleaned = _MD_LINK_RE.sub(_md, text)
    cleaned = _URL_RE.sub(_bare, cleaned)
    cleaned = _BARE_DOMAIN_RE.sub(_bare, cleaned)
    # Tidy whitespace left behind by removals without touching newlines.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" +([.,;:!?])", r"\1", cleaned)
    return cleaned.strip()


def sanitize_doc_text(text: str | None, *, limit: int) -> str:
    """Make retrieved listing text safe to embed in the model prompt as data."""
    if not text:
        return ""
    cleaned = _CONTROL_RE.sub(" ", text)
    cleaned = _FENCE_RE.sub(" ", cleaned)
    cleaned = _MD_LINK_RE.sub(lambda m: m.group(1), cleaned)
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if len(cleaned) > limit:
        cleaned = cleaned[: max(limit - 3, 0)] + "..."
    return cleaned


__all__ = [
    "DEFAULT_ALLOWED_LINK_HOSTS",
    "allowed_link_hosts",
    "is_allowed_url",
    "sanitize_doc_text",
    "strip_foreign_urls",
]
