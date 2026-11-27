"""Deterministic auditor for logged Ask Vergeo answers.

Runs after the answer has been shown (background task), never on the request path.
Every rule is a plain comparison against the live marketplace rows, so a verdict is
reproducible and explainable to the admin who has to contact the vendor:

* ``entity_missing``        cited entity no longer exists (or never did)
* ``entity_inactive``       cited entity is not live (draft/paused/removed/cancelled…)
* ``vendor_inactive``       the seller behind a cited item is not active
* ``vendor_mismatch``       cited seller is not the item's actual seller
* ``price_mismatch``        price shown to the customer differs from the real current
                            price (a hallucination or a stale index)
* ``price_below_category_floor``  below a hard per-category floor (a phone at K5)
* ``price_far_below_median``      under 10% of the median active price in the category
* ``price_far_above_median``      over 10x the median active price in the category
* ``text_price_unsupported``      a Kwacha amount in the answer text that no cited
                                  item (and not the question) accounts for

Money is integer ngwee throughout; amounts parsed from text go through ``Decimal``.
"""

from __future__ import annotations

import logging
import re
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.ask.enrich import rows_of

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

# A peer set smaller than this is too thin for a meaningful median.
MIN_PEERS_FOR_MEDIAN = 3
LOW_MEDIAN_RATIO = Decimal("0.10")
HIGH_MEDIAN_MULTIPLE = 10
MAX_PEER_ROWS = 1000

# Hard per-category floors (ngwee). First matching category-path prefix wins. Conservative
# on purpose: these catch a flagrant mispricing, not a bargain.
CATEGORY_FLOORS_NGWEE: tuple[tuple[str, int], ...] = (
    ("electronics/mobile-phones", 30_000),  # K300
    ("electronics/laptops-computers", 100_000),  # K1,000
    ("electronics/cameras", 20_000),  # K200
    ("electronics/tvs-audio", 10_000),  # K100
)

_ACCESSORY_WORDS = r"(case|cover|charger|cable|protector|glass|holder|stand|strap|adapter|pouch)"
# Title fallback for listings that have no canonical category (standalone listings).
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

_KWACHA_RE = re.compile(r"(?<![A-Za-z0-9])K\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?![\d])")


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    reason: str
    entity_kind: str | None = None
    entity_id: str | None = None
    vendor_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class LiveEntity:
    kind: str
    entity_id: str
    found: bool = False
    active: bool = False
    status: str | None = None
    title: str | None = None
    vendor_ids: set[str] = field(default_factory=set)
    vendor_id: str | None = None
    vendor_active: bool | None = None
    price_min: int | None = None
    price_max: int | None = None
    category_path: str | None = None
    category_id: str | None = None
    service_category: str | None = None
    product_id: str | None = None


def _uuid_or_none(value: Any) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


# ---------------------------------------------------------------------------
# Live data
# ---------------------------------------------------------------------------


def _ids(entries: list[dict[str, Any]], kind: str) -> list[str]:
    return sorted({str(e["id"]) for e in entries if e.get("kind") == kind and e.get("id")})


def load_live(client: Any, entries: list[dict[str, Any]]) -> dict[tuple[str, str], LiveEntity]:
    """Fetch the current state of every cited entity (one query per kind)."""
    live: dict[tuple[str, str], LiveEntity] = {}
    for entry in entries:
        kind, entity_id = str(entry.get("kind")), str(entry.get("id"))
        live[(kind, entity_id)] = LiveEntity(kind=kind, entity_id=entity_id)

    listing_ids = _ids(entries, "listing")
    product_ids = set(_ids(entries, "product"))
    listing_rows: dict[str, dict[str, Any]] = {}
    if listing_ids:
        for row in rows_of(
            client.table("vendor_listings")
            .select("id, vendor_id, product_id, title_override, price_ngwee, status")
            .in_("id", listing_ids)
            .execute()
        ):
            listing_rows[str(row["id"])] = row
            if row.get("product_id"):
                product_ids.add(str(row["product_id"]))

    product_rows: dict[str, dict[str, Any]] = {}
    category_rows: dict[str, dict[str, Any]] = {}
    if product_ids:
        for row in rows_of(
            client.table("products")
            .select("id, name, status, category_id")
            .in_("id", sorted(product_ids))
            .execute()
        ):
            product_rows[str(row["id"])] = row
        category_ids = sorted(
            {str(r["category_id"]) for r in product_rows.values() if r.get("category_id")}
        )
        if category_ids:
            for row in rows_of(
                client.table("categories").select("id, path").in_("id", category_ids).execute()
            ):
                category_rows[str(row["id"])] = row

    # Active, retail listings per cited product: the price/seller set a card can show.
    product_listings: dict[str, list[dict[str, Any]]] = {}
    cited_products = _ids(entries, "product")
    if cited_products:
        for row in rows_of(
            client.table("vendor_listings")
            .select("product_id, vendor_id, price_ngwee")
            .in_("product_id", cited_products)
            .eq("status", "active")
            .eq("wholesale", False)
            .limit(MAX_PEER_ROWS)
            .execute()
        ):
            product_listings.setdefault(str(row["product_id"]), []).append(row)

    service_rows: dict[str, dict[str, Any]] = {}
    if _ids(entries, "service"):
        for row in rows_of(
            client.table("services")
            .select("id, vendor_id, title, category, from_price_ngwee, status")
            .in_("id", _ids(entries, "service"))
            .execute()
        ):
            service_rows[str(row["id"])] = row

    event_rows: dict[str, dict[str, Any]] = {}
    if _ids(entries, "event"):
        for row in rows_of(
            client.table("events")
            .select("id, organiser_vendor_id, title, status")
            .in_("id", _ids(entries, "event"))
            .execute()
        ):
            event_rows[str(row["id"])] = row

    vendor_ids: set[str] = set(_ids(entries, "vendor"))
    vendor_ids |= {str(r["vendor_id"]) for r in listing_rows.values() if r.get("vendor_id")}
    vendor_ids |= {str(r["vendor_id"]) for r in service_rows.values() if r.get("vendor_id")}
    vendor_ids |= {
        str(r["organiser_vendor_id"]) for r in event_rows.values() if r.get("organiser_vendor_id")
    }
    vendor_ids |= {
        str(r["vendor_id"])
        for rows in product_listings.values()
        for r in rows
        if r.get("vendor_id")
    }
    vendor_rows: dict[str, dict[str, Any]] = {}
    if vendor_ids:
        for row in rows_of(
            client.table("vendors")
            .select("id, status, display_name")
            .in_("id", sorted(vendor_ids))
            .execute()
        ):
            vendor_rows[str(row["id"])] = row

    def set_vendor(item: LiveEntity, vendor_id: Any) -> None:
        if not vendor_id:
            return
        item.vendor_id = str(vendor_id)
        item.vendor_ids.add(str(vendor_id))
        vendor = vendor_rows.get(str(vendor_id))
        item.vendor_active = None if vendor is None else vendor.get("status") == "active"

    def set_category(item: LiveEntity, product_id: Any) -> None:
        product = product_rows.get(str(product_id)) if product_id else None
        if product is None:
            return
        item.product_id = str(product["id"])
        item.category_id = str(product["category_id"]) if product.get("category_id") else None
        category = category_rows.get(item.category_id) if item.category_id else None
        item.category_path = category.get("path") if category else None

    for (kind, entity_id), item in live.items():
        if kind == "listing":
            listing_row = listing_rows.get(entity_id)
            if listing_row is None:
                continue
            item.found = True
            item.status = listing_row.get("status")
            item.active = listing_row.get("status") == "active"
            title = listing_row.get("title_override")
            item.title = title if isinstance(title, str) and title.strip() else None
            item.price_min = item.price_max = _int_or_none(listing_row.get("price_ngwee"))
            set_vendor(item, listing_row.get("vendor_id"))
            set_category(item, listing_row.get("product_id"))
            if item.title is None and item.product_id:
                item.title = product_rows[item.product_id].get("name")
        elif kind == "product":
            product_row = product_rows.get(entity_id)
            if product_row is None:
                continue
            item.found = True
            item.status = product_row.get("status")
            item.title = product_row.get("name")
            listings = product_listings.get(entity_id, [])
            item.active = product_row.get("status") == "active" and bool(listings)
            if product_row.get("status") == "active" and not listings:
                item.status = "no_active_listings"
            prices = [p for p in (_int_or_none(r.get("price_ngwee")) for r in listings) if p]
            item.price_min = min(prices) if prices else None
            item.price_max = max(prices) if prices else None
            for r in listings:
                if r.get("vendor_id"):
                    item.vendor_ids.add(str(r["vendor_id"]))
            cheapest = min(listings, key=lambda r: r.get("price_ngwee") or 0, default=None)
            set_vendor(item, cheapest.get("vendor_id") if cheapest else None)
            item.vendor_ids |= {str(r["vendor_id"]) for r in listings if r.get("vendor_id")}
            set_category(item, entity_id)
        elif kind == "service":
            service_row = service_rows.get(entity_id)
            if service_row is None:
                continue
            item.found = True
            item.status = service_row.get("status")
            item.active = service_row.get("status") == "active"
            item.title = service_row.get("title")
            item.price_min = item.price_max = _int_or_none(service_row.get("from_price_ngwee"))
            item.service_category = service_row.get("category")
            set_vendor(item, service_row.get("vendor_id"))
        elif kind == "event":
            event_row = event_rows.get(entity_id)
            if event_row is None:
                continue
            item.found = True
            item.status = event_row.get("status")
            item.active = event_row.get("status") == "published"
            item.title = event_row.get("title")
            set_vendor(item, event_row.get("organiser_vendor_id"))
        elif kind == "vendor":
            vendor_row = vendor_rows.get(entity_id)
            if vendor_row is None:
                continue
            item.found = True
            item.status = vendor_row.get("status")
            item.active = vendor_row.get("status") == "active"
            item.title = vendor_row.get("display_name")
            item.vendor_id = entity_id
            item.vendor_ids.add(entity_id)
            item.vendor_active = item.active
    return live


def peer_median_ngwee(client: Any, item: LiveEntity) -> tuple[int | None, int]:
    """Median active retail price of *other* items in the same category, and peer count."""
    prices: list[int] = []
    if item.kind in ("product", "listing") and item.category_id:
        products = rows_of(
            client.table("products")
            .select("id")
            .eq("category_id", item.category_id)
            .eq("status", "active")
            .limit(MAX_PEER_ROWS)
            .execute()
        )
        peer_products = [str(r["id"]) for r in products if str(r["id"]) != item.product_id]
        if peer_products:
            for row in rows_of(
                client.table("vendor_listings")
                .select("price_ngwee")
                .in_("product_id", peer_products)
                .eq("status", "active")
                .eq("wholesale", False)
                .limit(MAX_PEER_ROWS)
                .execute()
            ):
                price = _int_or_none(row.get("price_ngwee"))
                if price:
                    prices.append(price)
    elif item.kind == "service" and item.service_category:
        for row in rows_of(
            client.table("services")
            .select("id, from_price_ngwee")
            .eq("category", item.service_category)
            .eq("status", "active")
            .limit(MAX_PEER_ROWS)
            .execute()
        ):
            price = _int_or_none(row.get("from_price_ngwee"))
            if price and str(row.get("id")) != item.entity_id:
                prices.append(price)
    if len(prices) < MIN_PEERS_FOR_MEDIAN:
        return None, len(prices)
    return int(statistics.median(prices)), len(prices)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def format_ngwee(value: int) -> str:
    kwacha, ngwee = divmod(value, 100)
    return f"K{kwacha:,}.{ngwee:02d}"


def category_floor(item: LiveEntity) -> tuple[int, str] | None:
    path = item.category_path or ""
    for prefix, floor in CATEGORY_FLOORS_NGWEE:
        if path == prefix or path.startswith(prefix + "/"):
            return floor, prefix
    if item.title:
        for pattern, floor, label in TITLE_FLOORS:
            if pattern.search(item.title):
                return floor, f"title:{label}"
    return None


def price_findings(
    entry: dict[str, Any], item: LiveEntity, median: tuple[int | None, int]
) -> list[Finding]:
    out: list[Finding] = []
    kind, entity_id = item.kind, item.entity_id
    title = item.title or entry.get("title") or entity_id
    shown_min = _int_or_none(entry.get("price_ngwee"))
    shown_max = _int_or_none(entry.get("price_max_ngwee"))

    def mismatch(label: str, shown: int, real: int | None) -> Finding:
        real_text = format_ngwee(real) if real is not None else "no price on record"
        return Finding(
            rule="price_mismatch",
            severity="critical",
            reason=(
                f'Ask Vergeo showed {format_ngwee(shown)} ({label}) for "{title}" but the '
                f"current price is {real_text}."
            ),
            entity_kind=kind,
            entity_id=entity_id,
            vendor_id=item.vendor_id,
            details={"shown_ngwee": shown, "actual_ngwee": real, "field": label},
        )

    if shown_min is not None and shown_min != item.price_min:
        out.append(mismatch("price", shown_min, item.price_min))
    if (
        shown_max is not None
        and shown_max != shown_min
        and item.kind == "product"
        and shown_max != item.price_max
    ):
        out.append(mismatch("max price", shown_max, item.price_max))

    real = item.price_min if item.price_min is not None else shown_min
    if real is None:
        return out

    floor = category_floor(item)
    if floor is not None and real < floor[0]:
        out.append(
            Finding(
                rule="price_below_category_floor",
                severity="critical",
                reason=(
                    f'"{title}" is priced at {format_ngwee(real)}, below the '
                    f"{format_ngwee(floor[0])} minimum plausible price for its category "
                    "(likely a placeholder, typo or scam listing)."
                ),
                entity_kind=kind,
                entity_id=entity_id,
                vendor_id=item.vendor_id,
                details={"price_ngwee": real, "floor_ngwee": floor[0], "floor_key": floor[1]},
            )
        )

    median_ngwee, peers = median
    if median_ngwee:
        if Decimal(real) < Decimal(median_ngwee) * LOW_MEDIAN_RATIO:
            out.append(
                Finding(
                    rule="price_far_below_median",
                    severity="critical",
                    reason=(
                        f'"{title}" at {format_ngwee(real)} is under 10% of the category median '
                        f"({format_ngwee(median_ngwee)} across {peers} active listings)."
                    ),
                    entity_kind=kind,
                    entity_id=entity_id,
                    vendor_id=item.vendor_id,
                    details={"price_ngwee": real, "median_ngwee": median_ngwee, "peers": peers},
                )
            )
        elif real > median_ngwee * HIGH_MEDIAN_MULTIPLE:
            out.append(
                Finding(
                    rule="price_far_above_median",
                    severity="warning",
                    reason=(
                        f'"{title}" at {format_ngwee(real)} is over 10x the category median '
                        f"({format_ngwee(median_ngwee)} across {peers} active listings)."
                    ),
                    entity_kind=kind,
                    entity_id=entity_id,
                    vendor_id=item.vendor_id,
                    details={"price_ngwee": real, "median_ngwee": median_ngwee, "peers": peers},
                )
            )
    return out


def kwacha_amounts_ngwee(text: str) -> set[int]:
    """Every ``K1,234.56`` style amount in ``text`` as integer ngwee."""
    amounts: set[int] = set()
    for match in _KWACHA_RE.finditer(text or ""):
        whole = match.group(1).replace(",", "")
        frac = (match.group(2) or "0").ljust(2, "0")
        try:
            amounts.add(int(Decimal(whole) * 100 + Decimal(frac)))
        except (InvalidOperation, ValueError):
            continue
    return amounts


def text_price_findings(
    *, query: str, answer_text: str, entries: list[dict[str, Any]]
) -> list[Finding]:
    """Flag Kwacha amounts in the prose that no cited item (or the question) explains."""
    priced = [e for e in entries if _int_or_none(e.get("price_ngwee")) is not None]
    if not priced:
        return []
    known: set[int] = set()
    for entry in priced:
        known.add(int(entry["price_ngwee"]))
        if _int_or_none(entry.get("price_max_ngwee")) is not None:
            known.add(int(entry["price_max_ngwee"]))
    known |= kwacha_amounts_ngwee(query)
    stray = sorted(kwacha_amounts_ngwee(answer_text) - known)
    if not stray:
        return []
    shown = ", ".join(format_ngwee(v) for v in stray[:5])
    return [
        Finding(
            rule="text_price_unsupported",
            severity="warning",
            reason=(
                f"The answer text quotes {shown}, which matches no cited item's price "
                "(possible hallucinated price)."
            ),
            details={"amounts_ngwee": stray[:10]},
        )
    ]


def evaluate(
    client: Any, *, query: str, answer_text: str, entries: list[dict[str, Any]]
) -> list[Finding]:
    """Run every rule for one logged answer. Raises only on a data-access failure."""
    findings: list[Finding] = []
    if not entries:
        return findings
    live = load_live(client, entries)
    median_cache: dict[tuple[str, str | None], tuple[int | None, int]] = {}
    for entry in entries:
        kind, entity_id = str(entry.get("kind")), str(entry.get("id"))
        item = live[(kind, entity_id)]
        title = item.title or entry.get("title") or entity_id
        if not item.found:
            findings.append(
                Finding(
                    rule="entity_missing",
                    severity="critical",
                    reason=f'Ask Vergeo cited {kind} "{title}" which does not exist.',
                    entity_kind=kind,
                    entity_id=entity_id,
                    vendor_id=_uuid_or_none(entry.get("vendor_id")),
                )
            )
            continue
        if not item.active:
            findings.append(
                Finding(
                    rule="entity_inactive",
                    severity="critical",
                    reason=(
                        f'Ask Vergeo cited {kind} "{title}" which is not live '
                        f"(status: {item.status or 'unknown'})."
                    ),
                    entity_kind=kind,
                    entity_id=entity_id,
                    vendor_id=item.vendor_id,
                    details={"status": item.status},
                )
            )
        cited_vendor = _uuid_or_none(entry.get("vendor_id"))
        if cited_vendor and item.vendor_ids and cited_vendor not in item.vendor_ids:
            findings.append(
                Finding(
                    rule="vendor_mismatch",
                    severity="critical",
                    reason=(f'Ask Vergeo attributed "{title}" to a vendor that does not sell it.'),
                    entity_kind=kind,
                    entity_id=entity_id,
                    vendor_id=item.vendor_id,
                    details={"cited_vendor_id": cited_vendor},
                )
            )
        if kind != "vendor" and item.vendor_active is False:
            findings.append(
                Finding(
                    rule="vendor_inactive",
                    severity="warning",
                    reason=f'The seller behind "{title}" is not active on the marketplace.',
                    entity_kind=kind,
                    entity_id=entity_id,
                    vendor_id=item.vendor_id,
                )
            )
        if kind in ("listing", "product", "service"):
            cache_key = (kind, item.category_id or item.service_category)
            if cache_key not in median_cache:
                median_cache[cache_key] = (
                    peer_median_ngwee(client, item) if cache_key[1] else (None, 0)
                )
            findings.extend(price_findings(entry, item, median_cache[cache_key]))
    findings.extend(text_price_findings(query=query, answer_text=answer_text, entries=entries))
    return findings


def verdict(findings: list[Finding]) -> tuple[str, str | None]:
    """(audit_status, audit_severity) for a finished audit."""
    flagged = [f for f in findings if SEVERITY_RANK.get(f.severity, 0) >= SEVERITY_RANK["warning"]]
    if not flagged:
        return "passed", None
    worst = max(flagged, key=lambda f: SEVERITY_RANK[f.severity])
    return "flagged", worst.severity


def audit_answer(
    client: Any, answer_id: str, *, query: str, answer_text: str, entries: list[dict[str, Any]]
) -> str:
    """Audit one logged answer, persist findings + verdict, return the audit_status."""
    try:
        findings = evaluate(client, query=query, answer_text=answer_text, entries=entries)
        if findings:
            client.table("ask_answer_findings").insert(
                [
                    {
                        "answer_id": answer_id,
                        "rule": f.rule,
                        "severity": f.severity,
                        "reason": f.reason[:600],
                        "entity_kind": f.entity_kind,
                        "entity_id": _uuid_or_none(f.entity_id),
                        "vendor_id": _uuid_or_none(f.vendor_id),
                        "details": f.details,
                    }
                    for f in findings
                ]
            ).execute()
        status, severity = verdict(findings)
    except Exception:  # noqa: BLE001 — an auditor bug must never surface to customers
        logger.warning("Ask answer audit failed for %s", answer_id, exc_info=True)
        status, severity = "error", None
    try:
        client.table("ask_answers").update(
            {
                "audit_status": status,
                "audit_severity": severity,
                "audited_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", answer_id).execute()
    except Exception:  # noqa: BLE001
        logger.warning("Ask answer audit verdict write failed for %s", answer_id, exc_info=True)
    return status
