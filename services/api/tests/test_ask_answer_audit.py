"""Ask Vergeo answer log, structured citations and the deterministic auditor."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.routers import ask as ask_router
from app.routers.admin_ask_audit import list_ask_answers
from app.routers.ask import AskResponse
from app.services.ask import audit
from app.services.ask.answer_log import citation_entries, log_and_audit
from app.services.ask.citations import CitationRef, route_path
from app.services.ask.enrich import attach_vendor_info
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError


def _id() -> str:
    return str(uuid.uuid4())


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Query:
    def __init__(self, db: FakeDb, name: str) -> None:
        self.db, self.name = db, name
        self.op = "select"
        self.payload: Any = None
        self.filters: list[Any] = []
        self.order_by: list[tuple[str, bool]] = []
        self.max_rows: int | None = None

    def select(self, *_a: Any) -> Query:
        return self

    def insert(self, payload: Any) -> Query:
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload: Any) -> Query:
        self.op, self.payload = "update", payload
        return self

    def eq(self, col: str, val: Any) -> Query:
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col: str, vals: list[Any]) -> Query:
        self.filters.append(lambda r: r.get(col) in vals)
        return self

    def order(self, col: str, desc: bool = False) -> Query:
        self.order_by.append((col, desc))
        return self

    def limit(self, n: int) -> Query:
        self.max_rows = n
        return self

    def execute(self) -> Result:
        rows = self.db.tables.setdefault(self.name, [])
        if self.op == "insert":
            batch = self.payload if isinstance(self.payload, list) else [self.payload]
            stored = [{"id": _id(), **row} for row in batch]
            rows.extend(stored)
            return Result(stored)
        matched = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for row in matched:
                row.update(self.payload)
            return Result(matched)
        for col, desc in reversed(self.order_by):
            matched.sort(key=lambda r: str(r.get(col)), reverse=desc)
        return Result([dict(r) for r in matched[: self.max_rows]])


class FakeDb:
    def __init__(self, **tables: list[dict[str, Any]]) -> None:
        self.tables = {k: [dict(r) for r in v] for k, v in tables.items()}

    def table(self, name: str) -> Query:
        return Query(self, name)


VENDOR = _id()
OTHER_VENDOR = _id()
CATEGORY_PHONES = _id()
CATEGORY_MISC = _id()


def _vendors() -> list[dict[str, Any]]:
    return [
        {"id": VENDOR, "slug": "pixel-hub", "display_name": "Pixel Hub", "status": "active"},
        {"id": OTHER_VENDOR, "slug": "other", "display_name": "Other", "status": "active"},
    ]


def _entry(
    kind: str,
    entity_id: str,
    *,
    title: str = "Item",
    price: int | None = None,
    price_max: int | None = None,
    vendor_id: str | None = None,
    slug: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": entity_id,
        "title": title,
        "price_ngwee": price,
        "price_max_ngwee": price_max,
        "vendor_id": vendor_id,
        "slug": slug,
    }


def _listing(
    listing_id: str,
    *,
    price: int,
    status: str = "active",
    vendor: str = VENDOR,
    product_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    return {
        "id": listing_id,
        "vendor_id": vendor,
        "product_id": product_id,
        "title_override": title,
        "price_ngwee": price,
        "status": status,
        "wholesale": False,
    }


def _rules(findings: list[audit.Finding]) -> set[str]:
    return {f.rule for f in findings}


# ---------------------------------------------------------------------------
# Auditor rules
# ---------------------------------------------------------------------------


def test_pixel_10_pro_at_k5_is_flagged_below_category_floor() -> None:
    listing_id = _id()
    db = FakeDb(
        vendor_listings=[_listing(listing_id, price=500, title="Google Pixel 10 Pro")],
        vendors=_vendors(),
    )
    entries = [
        _entry("listing", listing_id, title="Google Pixel 10 Pro", price=500, vendor_id=VENDOR)
    ]

    findings = audit.evaluate(
        db, query="pixel 10 pro", answer_text="Google Pixel 10 Pro for K5.00.", entries=entries
    )

    assert "price_below_category_floor" in _rules(findings)
    floor = next(f for f in findings if f.rule == "price_below_category_floor")
    assert floor.severity == "critical"
    assert floor.vendor_id == VENDOR
    assert audit.verdict(findings) == ("flagged", "critical")


def test_pixel_below_category_floor_via_category_path() -> None:
    product_id, listing_id = _id(), _id()
    db = FakeDb(
        categories=[{"id": CATEGORY_PHONES, "path": "electronics/mobile-phones"}],
        products=[
            {"id": product_id, "name": "Pixel", "status": "active", "category_id": CATEGORY_PHONES}
        ],
        vendor_listings=[_listing(listing_id, price=500, product_id=product_id)],
        vendors=_vendors(),
    )
    findings = audit.evaluate(
        db,
        query="pixel",
        answer_text="Pixel.",
        entries=[_entry("listing", listing_id, title="Pixel", price=500, vendor_id=VENDOR)],
    )
    assert "price_below_category_floor" in _rules(findings)


def test_normal_priced_phone_passes() -> None:
    listing_id = _id()
    db = FakeDb(
        vendor_listings=[_listing(listing_id, price=1_800_000, title="Google Pixel 10 Pro")],
        vendors=_vendors(),
    )
    entries = [
        _entry(
            "listing", listing_id, title="Google Pixel 10 Pro", price=1_800_000, vendor_id=VENDOR
        )
    ]
    findings = audit.evaluate(
        db,
        query="pixel 10 pro",
        answer_text="Google Pixel 10 Pro is K18,000.00 at Pixel Hub.",
        entries=entries,
    )
    assert findings == []
    assert audit.verdict(findings) == ("passed", None)


def test_phone_accessory_with_phone_word_is_not_floor_flagged() -> None:
    listing_id = _id()
    db = FakeDb(
        vendor_listings=[_listing(listing_id, price=500, title="Case for iPhone 15")],
        vendors=_vendors(),
    )
    findings = audit.evaluate(
        db,
        query="iphone case",
        answer_text="Case.",
        entries=[_entry("listing", listing_id, price=500, vendor_id=VENDOR)],
    )
    assert "price_below_category_floor" not in _rules(findings)


def test_price_mismatch_is_critical() -> None:
    listing_id = _id()
    db = FakeDb(
        vendor_listings=[_listing(listing_id, price=250_000, title="Blender")],
        vendors=_vendors(),
    )
    findings = audit.evaluate(
        db,
        query="blender",
        answer_text="Blender K1,000.00.",
        entries=[_entry("listing", listing_id, title="Blender", price=100_000, vendor_id=VENDOR)],
    )
    mismatch = next(f for f in findings if f.rule == "price_mismatch")
    assert mismatch.severity == "critical"
    assert mismatch.details == {"shown_ngwee": 100_000, "actual_ngwee": 250_000, "field": "price"}
    assert "K2,500.00" in mismatch.reason


def test_missing_entity_is_critical() -> None:
    findings = audit.evaluate(
        FakeDb(vendors=_vendors()),
        query="x",
        answer_text="x",
        entries=[_entry("listing", _id(), price=1000)],
    )
    assert _rules(findings) == {"entity_missing"}


@pytest.mark.parametrize("status", ["paused", "draft", "removed"])
def test_inactive_listing_is_flagged(status: str) -> None:
    listing_id = _id()
    db = FakeDb(
        vendor_listings=[_listing(listing_id, price=5000, status=status, title="Mug")],
        vendors=_vendors(),
    )
    findings = audit.evaluate(
        db, query="mug", answer_text="Mug.", entries=[_entry("listing", listing_id, price=5000)]
    )
    assert "entity_inactive" in _rules(findings)


def test_vendor_mismatch_is_critical() -> None:
    listing_id = _id()
    db = FakeDb(
        vendor_listings=[_listing(listing_id, price=5000, title="Mug")],
        vendors=_vendors(),
    )
    findings = audit.evaluate(
        db,
        query="mug",
        answer_text="Mug.",
        entries=[_entry("listing", listing_id, price=5000, vendor_id=OTHER_VENDOR)],
    )
    assert "vendor_mismatch" in _rules(findings)


def test_inactive_vendor_is_a_warning() -> None:
    listing_id = _id()
    vendors = _vendors()
    vendors[0]["status"] = "suspended"
    db = FakeDb(vendor_listings=[_listing(listing_id, price=5000, title="Mug")], vendors=vendors)
    findings = audit.evaluate(
        db, query="mug", answer_text="Mug.", entries=[_entry("listing", listing_id, price=5000)]
    )
    inactive = next(f for f in findings if f.rule == "vendor_inactive")
    assert inactive.severity == "warning"


def _category_market(*, own_price: int) -> tuple[FakeDb, str]:
    own_product, own_listing = _id(), _id()
    products = [
        {"id": own_product, "name": "Own", "status": "active", "category_id": CATEGORY_MISC}
    ]
    listings = [_listing(own_listing, price=own_price, product_id=own_product)]
    for _ in range(4):
        pid = _id()
        products.append(
            {"id": pid, "name": "Peer", "status": "active", "category_id": CATEGORY_MISC}
        )
        listings.append(_listing(_id(), price=100_000, product_id=pid))
    db = FakeDb(
        categories=[{"id": CATEGORY_MISC, "path": "home/kitchen"}],
        products=products,
        vendor_listings=listings,
        vendors=_vendors(),
    )
    return db, own_listing


def test_price_under_ten_percent_of_category_median_is_critical() -> None:
    db, listing_id = _category_market(own_price=5_000)  # median K1,000 -> K50 is 5%
    findings = audit.evaluate(
        db,
        query="kettle",
        answer_text="Kettle.",
        entries=[_entry("listing", listing_id, price=5_000, vendor_id=VENDOR)],
    )
    low = next(f for f in findings if f.rule == "price_far_below_median")
    assert low.severity == "critical"
    assert low.details["median_ngwee"] == 100_000


def test_price_over_ten_times_category_median_is_a_warning() -> None:
    db, listing_id = _category_market(own_price=1_500_000)
    findings = audit.evaluate(
        db,
        query="kettle",
        answer_text="Kettle.",
        entries=[_entry("listing", listing_id, price=1_500_000, vendor_id=VENDOR)],
    )
    high = next(f for f in findings if f.rule == "price_far_above_median")
    assert high.severity == "warning"
    assert audit.verdict(findings) == ("flagged", "warning")


def test_in_range_price_against_median_passes() -> None:
    db, listing_id = _category_market(own_price=90_000)
    findings = audit.evaluate(
        db,
        query="kettle",
        answer_text="Kettle.",
        entries=[_entry("listing", listing_id, price=90_000, vendor_id=VENDOR)],
    )
    assert findings == []


def test_thin_peer_set_skips_median_rules() -> None:
    own_product, own_listing, peer_product = _id(), _id(), _id()
    db = FakeDb(
        categories=[{"id": CATEGORY_MISC, "path": "home/kitchen"}],
        products=[
            {"id": own_product, "name": "Own", "status": "active", "category_id": CATEGORY_MISC},
            {"id": peer_product, "name": "Peer", "status": "active", "category_id": CATEGORY_MISC},
        ],
        vendor_listings=[
            _listing(own_listing, price=100, product_id=own_product),
            _listing(_id(), price=1_000_000, product_id=peer_product),
        ],
        vendors=_vendors(),
    )
    findings = audit.evaluate(
        db,
        query="x",
        answer_text="x",
        entries=[_entry("listing", own_listing, price=100, vendor_id=VENDOR)],
    )
    assert _rules(findings) == set()


def test_product_price_range_is_checked_against_active_listings() -> None:
    product_id = _id()
    db = FakeDb(
        categories=[{"id": CATEGORY_MISC, "path": "home/kitchen"}],
        products=[
            {"id": product_id, "name": "Fan", "status": "active", "category_id": CATEGORY_MISC}
        ],
        vendor_listings=[
            _listing(_id(), price=40_000, product_id=product_id),
            _listing(_id(), price=60_000, vendor=OTHER_VENDOR, product_id=product_id),
        ],
        vendors=_vendors(),
    )
    ok = audit.evaluate(
        db,
        query="fan",
        answer_text="Fan from K400.00 to K600.00.",
        entries=[_entry("product", product_id, price=40_000, price_max=60_000, vendor_id=VENDOR)],
    )
    assert ok == []
    stale = audit.evaluate(
        db,
        query="fan",
        answer_text="Fan.",
        entries=[_entry("product", product_id, price=30_000, price_max=60_000, vendor_id=VENDOR)],
    )
    assert _rules(stale) == {"price_mismatch"}


def test_event_unpublished_and_service_price_checks() -> None:
    event_id, service_id = _id(), _id()
    db = FakeDb(
        events=[
            {"id": event_id, "organiser_vendor_id": VENDOR, "title": "Fest", "status": "cancelled"}
        ],
        services=[
            {
                "id": service_id,
                "vendor_id": VENDOR,
                "title": "Plumbing",
                "category": "home",
                "from_price_ngwee": 20_000,
                "status": "active",
            }
        ],
        vendors=_vendors(),
    )
    findings = audit.evaluate(
        db,
        query="x",
        answer_text="x",
        entries=[
            _entry("event", event_id, title="Fest"),
            _entry("service", service_id, title="Plumbing", price=10_000, vendor_id=VENDOR),
        ],
    )
    by_entity = {(f.entity_kind, f.rule) for f in findings}
    assert ("event", "entity_inactive") in by_entity
    assert ("service", "price_mismatch") in by_entity


def test_text_price_not_backed_by_any_citation_is_a_warning() -> None:
    listing_id = _id()
    db = FakeDb(
        vendor_listings=[_listing(listing_id, price=250_000, title="Blender")],
        vendors=_vendors(),
    )
    entries = [_entry("listing", listing_id, title="Blender", price=250_000, vendor_id=VENDOR)]
    flagged = audit.evaluate(
        db, query="blender", answer_text="Blender is only K99.00 today.", entries=entries
    )
    assert _rules(flagged) == {"text_price_unsupported"}
    # An amount the customer typed in their own question is not a hallucination.
    echoed = audit.evaluate(
        db,
        query="blender under K3,000",
        answer_text="Blender K2,500.00, under your K3,000 budget.",
        entries=entries,
    )
    assert echoed == []


def test_kwacha_amounts_parse_to_integer_ngwee() -> None:
    assert audit.kwacha_amounts_ngwee("K5, K1,234.50 and K0.5 or K12.34") == {
        500,
        123_450,
        50,
        1_234,
    }


# ---------------------------------------------------------------------------
# Logging + background audit
# ---------------------------------------------------------------------------


def _response(citations: list[CitationRef], **kwargs: Any) -> AskResponse:
    base: dict[str, Any] = {
        "query": "pixel 10 pro",
        "answer": "Google Pixel 10 Pro for K5.00.",
        "citations": citations,
        "source": "ai",
        "model": "moonshotai/kimi-k2",
    }
    base.update(kwargs)
    return AskResponse(**base)


def test_log_and_audit_records_answer_findings_and_flags() -> None:
    listing_id = _id()
    db = FakeDb(
        vendor_listings=[_listing(listing_id, price=500, title="Google Pixel 10 Pro")],
        vendors=_vendors(),
    )
    citation = CitationRef(
        entity_kind="listing",
        entity_id=listing_id,
        title="Google Pixel 10 Pro",
        price_display="K5.00",
        price_min_ngwee=500,
        price_max_ngwee=500,
        slug="pixel",
        vendor_id=VENDOR,
    )
    user_id = _id()

    status = log_and_audit(
        db,
        response=_response([citation]),
        user_id=user_id,
        guest_key="device:abc",
        locale="en",
    )

    assert status == "flagged"
    (row,) = db.tables["ask_answers"]
    assert row["query"] == "pixel 10 pro"
    assert row["answer_text"] == "Google Pixel 10 Pro for K5.00."
    assert row["model"] == "moonshotai/kimi-k2"
    assert row["source"] == "ai"
    assert row["user_id"] == user_id
    assert row["guest_key"] is None
    assert row["locale"] == "en"
    assert row["citations"] == [
        {
            "kind": "listing",
            "id": listing_id,
            "title": "Google Pixel 10 Pro",
            "price_ngwee": 500,
            "price_max_ngwee": 500,
            "vendor_id": VENDOR,
            "slug": "pixel",
        }
    ]
    assert row["audit_status"] == "flagged"
    assert row["audit_severity"] == "critical"
    assert row["audited_at"]
    findings = db.tables["ask_answer_findings"]
    assert {f["rule"] for f in findings} == {"price_below_category_floor"}
    assert findings[0]["answer_id"] == row["id"]
    assert findings[0]["vendor_id"] == VENDOR
    assert findings[0]["entity_id"] == listing_id


def test_guest_answers_keep_the_guest_key_and_clean_answers_pass() -> None:
    db = FakeDb()
    status = log_and_audit(
        db,
        response=_response([], answer="I couldn't find that on Vergeo5.", refused=True),
        user_id=None,
        guest_key="device:abc",
        locale=None,
    )
    assert status == "passed"
    (row,) = db.tables["ask_answers"]
    assert row["user_id"] is None
    assert row["guest_key"] == "device:abc"
    assert row["refused"] is True
    assert row["audit_status"] == "passed"
    assert "ask_answer_findings" not in db.tables


def test_auditor_failure_marks_error_and_never_raises() -> None:
    class Boom(FakeDb):
        def table(self, name: str) -> Query:
            if name == "vendor_listings":
                raise RuntimeError("db down")
            return super().table(name)

    db = Boom()
    citation = CitationRef(entity_kind="listing", entity_id=_id(), title="x", price_min_ngwee=1000)
    assert (
        log_and_audit(db, response=_response([citation]), user_id=None, guest_key="g", locale=None)
        == "error"
    )
    assert db.tables["ask_answers"][0]["audit_status"] == "error"


def test_log_insert_failure_is_swallowed() -> None:
    class NoInsert(FakeDb):
        def table(self, name: str) -> Query:
            raise RuntimeError("db down")

    assert (
        log_and_audit(NoInsert(), response=_response([]), user_id=None, guest_key="g", locale=None)
        is None
    )


def test_citation_entries_record_what_was_shown() -> None:
    entries = citation_entries(
        [
            CitationRef(
                entity_kind="product",
                entity_id="p1",
                title="Fan",
                price_min_ngwee=100,
                price_max_ngwee=200,
                vendor_id="v1",
                slug="fan",
            )
        ]
    )
    assert entries == [
        {
            "kind": "product",
            "id": "p1",
            "title": "Fan",
            "price_ngwee": 100,
            "price_max_ngwee": 200,
            "vendor_id": "v1",
            "slug": "fan",
        }
    ]


# ---------------------------------------------------------------------------
# Structured citations
# ---------------------------------------------------------------------------


def test_route_paths_match_the_customer_routes() -> None:
    assert route_path("product", "p", "fan") == "/p/fan"
    assert route_path("product", "p", None) is None
    assert route_path("listing", "L1", "fan") == "/p/fan?listing=L1"
    assert route_path("listing", "L1", None) == "/l/L1"
    assert route_path("service", "S1", None) == "/s/S1"
    assert route_path("event", "E", "fest") == "/e/fest"
    assert route_path("vendor", "V", "shop") == "/v/shop"
    assert route_path("vendor", "V", "  ") is None


def test_attach_vendor_info_resolves_seller_and_links_for_every_kind() -> None:
    listing_id, product_id, service_id, event_id = _id(), _id(), _id(), _id()
    db = FakeDb(
        vendor_listings=[
            _listing(listing_id, price=900, vendor=VENDOR),
            _listing(_id(), price=700, vendor=OTHER_VENDOR, product_id=product_id),
            _listing(_id(), price=800, vendor=VENDOR, product_id=product_id),
        ],
        services=[{"id": service_id, "vendor_id": VENDOR}],
        events=[{"id": event_id, "organiser_vendor_id": OTHER_VENDOR}],
        vendors=_vendors(),
    )
    cards = [
        CitationRef(entity_kind="listing", entity_id=listing_id, title="L", slug="l-slug"),
        CitationRef(entity_kind="product", entity_id=product_id, title="P", slug="p-slug"),
        CitationRef(entity_kind="service", entity_id=service_id, title="S"),
        CitationRef(entity_kind="event", entity_id=event_id, title="E", slug="e-slug"),
        CitationRef(entity_kind="vendor", entity_id=VENDOR, title="V", slug="pixel-hub"),
    ]

    listing, product, service, event, vendor = attach_vendor_info(db, cards)

    assert (listing.href, listing.vendor_id, listing.vendor_href) == (
        f"/p/l-slug?listing={listing_id}",
        VENDOR,
        "/v/pixel-hub",
    )
    assert listing.vendor_name == "Pixel Hub"
    # A product shows the seller behind its lowest active price.
    assert (product.href, product.vendor_id, product.vendor_href) == (
        "/p/p-slug",
        OTHER_VENDOR,
        "/v/other",
    )
    assert (service.href, service.vendor_id) == (f"/s/{service_id}", VENDOR)
    assert (event.href, event.vendor_href) == ("/e/e-slug", "/v/other")
    assert (vendor.href, vendor.vendor_id, vendor.vendor_href) == (
        "/v/pixel-hub",
        VENDOR,
        "/v/pixel-hub",
    )


def test_attach_vendor_info_never_raises() -> None:
    class Broken:
        def table(self, _name: str) -> Any:
            raise RuntimeError("down")

    card = CitationRef(entity_kind="listing", entity_id=_id(), title="L", slug="l")
    (out,) = attach_vendor_info(Broken(), [card])
    assert out.href is not None and out.vendor_id is None


# ---------------------------------------------------------------------------
# Endpoint wiring
# ---------------------------------------------------------------------------


def test_post_ask_schedules_the_answer_log_without_changing_the_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.deps import get_supabase_client
    from app.main import create_app

    calls: list[dict[str, Any]] = []

    async def fake_run_ask(**_kwargs: Any) -> AskResponse:
        return _response([], answer="Hello")

    def fake_log(client: Any, **kwargs: Any) -> None:
        calls.append(kwargs)

    async def no_user(_request: Any) -> None:
        return None

    monkeypatch.setattr(ask_router, "run_ask", fake_run_ask)
    monkeypatch.setattr(ask_router, "log_and_audit", fake_log)
    monkeypatch.setattr(ask_router, "_optional_current_user", no_user)
    monkeypatch.setattr(ask_router, "_rate_limit_ask", lambda *_a, **_k: None)

    class Service:
        client = FakeDb()

    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: Service()
    with TestClient(app) as client:
        res = client.post("/ask", json={"query": "hi", "locale": "fr"})

    assert res.status_code == 200
    body = res.json()
    assert body["answer"] == "Hello"
    assert "model" not in body  # the model name is for the log, not for clients
    (call,) = calls
    assert call["locale"] == "fr"
    assert call["response"].query == "pixel 10 pro"
    assert call["user_id"] is None


# ---------------------------------------------------------------------------
# Admin listing
# ---------------------------------------------------------------------------


def test_admin_list_returns_empty_when_ask_tables_missing() -> None:
    missing = APIError({"code": "42P01", "message": "relation does not exist"})

    class MissingTableDb(FakeDb):
        def table(self, name: str) -> Query:
            query = super().table(name)
            if name in {"ask_answers", "ask_answer_findings"}:

                def execute_raises() -> Result:
                    raise missing

                query.execute = execute_raises  # type: ignore[method-assign]
            return query

    class Service:
        client = MissingTableDb()

    page = list_ask_answers(Service(), flagged_only=False, limit=25)
    assert page.items == []
    assert page.next_before is None
    assert page.next_before_id is None


def test_admin_list_shows_findings_links_and_filters_flagged() -> None:
    listing_id = _id()
    flagged_id, clean_id, finding_id = _id(), _id(), _id()
    db = FakeDb(
        ask_answers=[
            {
                "id": flagged_id,
                "created_at": "2026-11-27T09:00:00+00:00",
                "query": "pixel 10 pro",
                "answer_text": "Pixel for K5.00",
                "model": "m",
                "source": "ai",
                "intent": None,
                "cached": False,
                "refused": False,
                "locale": "en",
                "user_id": _id(),
                "citations": [
                    _entry(
                        "listing",
                        listing_id,
                        title="Pixel",
                        price=500,
                        vendor_id=VENDOR,
                        slug="pixel",
                    )
                ],
                "audit_status": "flagged",
                "audit_severity": "critical",
                "audited_at": "2026-11-27T09:00:05+00:00",
            },
            {
                "id": clean_id,
                "created_at": "2026-11-27T08:00:00+00:00",
                "query": "hello",
                "answer_text": "Hi",
                "model": "workflow",
                "source": "workflow",
                "intent": "greeting",
                "cached": False,
                "refused": False,
                "locale": None,
                "user_id": None,
                "citations": [],
                "audit_status": "passed",
                "audit_severity": None,
                "audited_at": None,
            },
        ],
        ask_answer_findings=[
            {
                "id": finding_id,
                "answer_id": flagged_id,
                "rule": "price_below_category_floor",
                "severity": "critical",
                "reason": "Too cheap",
                "entity_kind": "listing",
                "entity_id": listing_id,
                "vendor_id": VENDOR,
                "details": {"price_ngwee": 500},
            }
        ],
        vendors=_vendors(),
    )

    class Service:
        client = db

    everything = list_ask_answers(Service(), flagged_only=False, limit=25)
    assert [i.id for i in everything.items] == [flagged_id, clean_id]
    assert everything.items[0].asker == "customer"
    assert everything.items[1].asker == "guest"

    only = list_ask_answers(Service(), flagged_only=True, limit=25)
    assert [i.id for i in only.items] == [flagged_id]
    item = only.items[0]
    (finding,) = item.findings
    assert finding.entity_href == f"/p/pixel?listing={listing_id}"
    assert finding.vendor_name == "Pixel Hub"
    assert finding.vendor_href == "/v/pixel-hub"
    assert item.citations[0].vendor_href == "/v/pixel-hub"
    assert item.citations[0].href == f"/p/pixel?listing={listing_id}"
    dumped = item.model_dump_json()
    assert "user_id" not in dumped and "guest_key" not in dumped
