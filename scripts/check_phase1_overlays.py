#!/usr/bin/env python3
"""Validate bem/nya Phase-1 critical overlays against English.

Checks:
1. Every critical key is present in the locale overlay
2. ICU placeholder names match English
3. Value != English unless allowlisted
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MSG = ROOT / "packages" / "i18n" / "messages"

# Mirror packages/i18n/src/phase1-critical.ts
PHASE1_CRITICAL_LOCALES = ("bem", "nya")
PHASE1_CRITICAL_PREFIXES: dict[str, list[str]] = {
    "common": ["app", "common", "theme", "greeting", "offline", "install"],
    "nav": ["skipToContent", "shop", "marketing", "account", "auth"],
    "catalog": [
        "home.meta",
        "home.nav",
        "home.hero",
        "home.trust",
        "home.demo",
        "home.categories",
        "home.rails",
        "home.sellCta",
        "browseCategories",
        "plp.title",
        "plp.defaultCategory",
        "plp.breadcrumbAria",
        "plp.results",
        "plp.emptyTitle",
        "plp.emptyBody",
        "plp.unavailableTitle",
        "plp.unavailableBody",
        "plp.card",
        "plp.loadMore",
        "plp.loading",
        "pdp",
        "returnableBadge",
    ],
    "search": [
        "title",
        "placeholder",
        "submit",
        "recent",
        "tabs",
        "noResults",
        "unavailable",
        "invalid",
        "suggestionTerms",
        "suggestions",
        "categories",
        "askVergeo",
        "results",
        "input",
        "pagination",
        "result",
    ],
    "checkout": [
        "cart",
        "checkout.pageTitle",
        "checkout.stepAnnouncement",
        "checkout.doneIndicator",
        "checkout.steps",
        "checkout.payment",
        "checkout.review",
        "checkout.pending",
        "checkout.ussd",
        "checkout.card",
        "checkout.emptyCart",
        "checkout.error",
        "checkout.loading",
        "checkout.stockUnavailable",
        "checkout.reservationExpired",
    ],
    "orders": [
        "title",
        "empty",
        "list",
        "detail.title",
        "detail.back",
        "detail.orderId",
        "detail.vendor",
        "detail.total",
        "status",
        "timeline",
        "escrow",
        "errors",
    ],
    "account": ["title", "nav", "locales", "common"],
    "marketing": ["notFound", "error"],
}

PHASE1_ENGLISH_ALLOWLIST = {
    "Vergeo5",
    "MTN",
    "Airtel",
    "Zamtel",
    "Lenco",
    "WhatsApp",
    "SMS",
    "PIN",
    "QR",
    "COD",
    "USSD",
    "MoMo",
    "Offline",
    "404",
    "500",
    "✓",
    "-",
    "+",
    "K",
    # Locale labels that stay as English / native endonyms
    "English",
    "Français",
    "中文",
    "Bemba",
    "Nyanja",
    "French",
    "Chinese",
    "Zambia",
    "Lusaka",
}


def flatten(obj: Any, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        if k == "__fallback":
            continue
        p = f"{prefix}.{k}" if prefix else k
        if isinstance(v, str):
            out[p] = v
        elif isinstance(v, dict):
            out.update(flatten(v, p))
    return out


def matches(key: str, prefixes: list[str]) -> bool:
    return any(key == p or key.startswith(p + ".") for p in prefixes)


def extract_icu_placeholders(template: str) -> list[str]:
    found: set[str] = set()
    for match in re.finditer(r"\{(\w+)(?:,[^}]*)?\}", template):
        found.add(match.group(1))
    return sorted(found)


def is_unexpected_english_fallback(en_value: str, locale_value: str) -> bool:
    en = en_value.strip()
    loc = locale_value.strip()
    if len(loc) == 0:
        return True
    if loc in PHASE1_ENGLISH_ALLOWLIST:
        return False
    if en == loc:
        without = re.sub(r"\{[^}]+\}", "", en).strip()
        if len(without) == 0:
            return False
        if without in PHASE1_ENGLISH_ALLOWLIST:
            return False
        # Pure punctuation / placeholder wrappers e.g. "×{qty}", "({count})", "{a} ({b})"
        if re.fullmatch(r"[×xX\s(){}\[\]0-9#.,:_/-]+", without):
            return False
        if re.fullmatch(r"[×xX\s{}0-9#.,:_-]+", en):
            return False
        return True
    return False


def main() -> int:
    errors: list[str] = []
    for locale in PHASE1_CRITICAL_LOCALES:
        for ns, prefixes in PHASE1_CRITICAL_PREFIXES.items():
            en = flatten(json.loads((MSG / "en" / f"{ns}.json").read_text(encoding="utf-8")))
            loc = flatten(json.loads((MSG / locale / f"{ns}.json").read_text(encoding="utf-8")))
            critical = sorted(k for k in en if matches(k, prefixes))
            for key in critical:
                en_val = en[key]
                if key not in loc:
                    errors.append(f"{locale}/{ns}: MISSING {key}")
                    continue
                loc_val = loc[key]
                en_ph = extract_icu_placeholders(en_val)
                loc_ph = extract_icu_placeholders(loc_val)
                if en_ph != loc_ph:
                    errors.append(
                        f"{locale}/{ns}: ICU mismatch {key}: en={en_ph} loc={loc_ph}"
                    )
                if is_unexpected_english_fallback(en_val, loc_val):
                    errors.append(
                        f"{locale}/{ns}: EN-identical {key}: {loc_val!r}"
                    )

    if errors:
        print(f"FAIL: {len(errors)} issue(s)")
        for e in errors:
            print(f"  {e}")
        return 1
    print("OK: all Phase-1 critical keys present, ICU matched, not accidental English")
    return 0


if __name__ == "__main__":
    sys.exit(main())
