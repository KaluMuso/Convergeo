"""M18-P05 — vendor review of a WhatsApp intake draft, and the listing handoff.

What these tests are actually defending:

* an intake-born listing is **never** created active — the whole D35 lane is
  worthless if a WhatsApp message can publish something buyable;
* a vendor cannot open, edit, or submit another vendor's session, **including**
  with a valid deep link (the token is not the authorisation);
* a repeated submit produces one listing, not two;
* the KYC tier cap that governs hand-typed listings governs these too;
* a draft that cannot honestly become a listing (used condition, no price,
  tracked stock with no quantity) is refused with a stable reason rather than
  coerced into something publishable.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.intake import deeplink, handoff, state_machine
from fastapi.testclient import TestClient

VENDOR_USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_VENDOR_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SESSION_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
OTHER_SESSION_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
BINDING_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
VALID_TOKEN = "valid.jwt.token"


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str = "*", *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def is_(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("is", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "update"
        self._payload = payload
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "in" and row.get(column) not in value:
                return False
            if op == "is" and value == "null" and row.get(column) is not None:
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            row.setdefault("id", f"row-{len(self._parent.rows)}-{self._parent.name}")
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._op == "update":
            assert self._payload is not None
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._match(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        rows = [dict(row) for row in self._parent.rows if self._match(row)]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str = "*", *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeStorageBucket:
    def __init__(self) -> None:
        self.signed: list[str] = []

    def create_signed_url(self, path: str, ttl: int) -> dict[str, str]:
        self.signed.append(path)
        return {"signedURL": f"https://signed.example/{path}?ttl={ttl}"}


class FakeStorage:
    def __init__(self) -> None:
        self.bucket = FakeStorageBucket()

    def from_(self, name: str) -> FakeStorageBucket:
        return self.bucket


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}
        self.storage = FakeStorage()

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))


# --- Fixtures ---------------------------------------------------------------
@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    supabase = FakeSupabaseClient()
    wrapper = MagicMock()
    wrapper.client = supabase
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.vendor_intake.get_supabase_client", lambda: wrapper)
    # Rate limiting is proven elsewhere; here it must not need a DB RPC.
    monkeypatch.setattr(
        "app.routers.vendor_intake.bump_rate_counter",
        lambda **_kwargs: (True, 0),
    )
    return supabase


def _auth(monkeypatch: pytest.MonkeyPatch, user_id: str = VENDOR_USER_ID) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"vendor"}),
    )


def _seed(
    fake: FakeSupabaseClient,
    *,
    status: str = state_machine.READY_FOR_VENDOR_REVIEW,
    draft: dict[str, Any] | None = None,
) -> None:
    fake.table("vendors").rows.extend(
        [
            {
                "id": VENDOR_ID,
                "owner_user_id": VENDOR_USER_ID,
                "status": "active",
                "kyc_tier": 2,
                "display_name": "Acme Shop",
            },
            {
                "id": OTHER_VENDOR_ID,
                "owner_user_id": OTHER_USER_ID,
                "status": "active",
                "kyc_tier": 2,
                "display_name": "Rival Shop",
            },
        ]
    )
    fake.table("intake_sessions").rows.extend(
        [
            {
                "id": SESSION_ID,
                "vendor_id": VENDOR_ID,
                "binding_id": BINDING_ID,
                "status": status,
                "pending_requests": [],
                "listing_id": None,
                "last_activity_at": "2026-07-01T00:00:00+00:00",
            },
            {
                "id": OTHER_SESSION_ID,
                "vendor_id": OTHER_VENDOR_ID,
                "binding_id": BINDING_ID,
                "status": state_machine.READY_FOR_VENDOR_REVIEW,
                "pending_requests": [],
                "listing_id": None,
                "last_activity_at": "2026-07-01T00:00:00+00:00",
            },
        ]
    )
    fake.table("intake_draft_fields").rows.append(
        {
            "session_id": SESSION_ID,
            "title": "Samsung Fridge",
            "category_id": None,
            "price_ngwee": 350_000,
            "pricing_mode": "fixed",
            "quantity": None,
            "stock_mode": "always",
            "sale_unit": None,
            "condition": "new",
            "description": "Barely used",
            **(draft or {}),
        }
    )
    fake.table("intake_field_provenance").rows.append(
        {
            "session_id": SESSION_ID,
            "field_name": "price_ngwee",
            "source": "rule",
            "confidence": 0.9,
            "model_ref": None,
        }
    )
    # Cap machinery reads these.
    fake.table("vendor_listings")
    fake.table("orders")
    fake.table("platform_config").rows.append(
        {"key": "cod_cap_ngwee", "value": 50_000}
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def _stub_caps(monkeypatch: pytest.MonkeyPatch, *, listing_count: int = 0) -> None:
    """Real cap object, fake counts — the enforcement path stays under test."""
    from app.services.kyc.caps import VendorCapLimits, VendorQuota

    limits = VendorCapLimits(
        vendor_id=VENDOR_ID,
        kyc_tier=2,
        quota=VendorQuota(
            tier=2,
            max_listings=5,
            first_orders_cap_ngwee=None,
            first_orders_count=None,
            payout_velocity={},
        ),
        cod_cap_ngwee=50_000,
        listing_count=listing_count,
        order_count=0,
    )
    monkeypatch.setattr(
        "app.routers.vendor_intake.load_vendor_cap_limits_by_id",
        lambda *args, **kwargs: limits,
    )


def _stub_listing_creation(
    monkeypatch: pytest.MonkeyPatch, status: str = "draft"
) -> dict[str, Any]:
    """Record what the shared listing seam was asked to create."""
    captured: dict[str, Any] = {}

    from app.routers.vendor_listings import ListingCreateResponse

    def fake_create(service_client: Any, *, vendor: dict[str, Any], body: Any) -> Any:
        captured["vendor_id"] = vendor["id"]
        captured["body"] = body
        return ListingCreateResponse(
            listing_id="99999999-9999-9999-9999-999999999999",
            mode=body.mode,
            status=status,
            product_id=None,
            product_status=None,
            commission=None,
        )

    monkeypatch.setattr("app.routers.vendor_intake.create_listing_for_vendor", fake_create)
    return captured


# --- handoff: the draft -> listing translation ------------------------------
def test_handoff_never_publishes() -> None:
    request = handoff.build_listing_request(
        {"title": "Fridge", "price_ngwee": 350_000, "condition": "new", "stock_mode": "always"}
    )
    assert request.publish is False
    assert request.mode == "quick_list"


def test_handoff_refuses_used_condition() -> None:
    """A used item must not be silently relabelled "refurbished" for buyers."""
    with pytest.raises(handoff.DraftNotSubmittable) as exc:
        handoff.build_listing_request(
            {"title": "Fridge", "price_ngwee": 1000, "condition": "used"}
        )
    assert exc.value.details["reason"] == "unsupported_condition"


def test_handoff_refuses_zero_price() -> None:
    with pytest.raises(handoff.DraftNotSubmittable) as exc:
        handoff.build_listing_request(
            {"title": "Fridge", "price_ngwee": 0, "condition": "new"}
        )
    assert exc.value.details["reason"] == "invalid_price"


def test_handoff_refuses_non_integer_price() -> None:
    """A float price means the ngwee path was bypassed somewhere upstream."""
    with pytest.raises(handoff.DraftNotSubmittable) as exc:
        handoff.build_listing_request(
            {"title": "Fridge", "price_ngwee": 3500.5, "condition": "new"}
        )
    assert exc.value.details["reason"] == "invalid_price"


def test_handoff_refuses_incomplete_draft() -> None:
    with pytest.raises(handoff.DraftNotSubmittable) as exc:
        handoff.build_listing_request({"title": "Fridge", "condition": "new"})
    assert exc.value.details["missing"] == ["price_ngwee"]


def test_handoff_tracked_stock_requires_quantity() -> None:
    with pytest.raises(handoff.DraftNotSubmittable) as exc:
        handoff.build_listing_request(
            {
                "title": "Fridge",
                "price_ngwee": 1000,
                "condition": "new",
                "stock_mode": "tracked",
            }
        )
    assert exc.value.details["reason"] == "missing_quantity"


def test_handoff_tracked_stock_carries_quantity() -> None:
    request = handoff.build_listing_request(
        {
            "title": "Fridge",
            "price_ngwee": 1000,
            "condition": "new",
            "stock_mode": "tracked",
            "quantity": 4,
        }
    )
    assert request.stock_mode == "tracked"
    assert request.stock_qty == 4


def test_handoff_made_to_order_maps_to_always_available() -> None:
    request = handoff.build_listing_request(
        {
            "title": "Cake",
            "price_ngwee": 25_000,
            "condition": "new",
            "stock_mode": "made_to_order",
        }
    )
    assert request.stock_mode == "always_available"
    assert request.stock_qty is None


def test_handoff_preserves_exact_ngwee() -> None:
    """No rounding, no float, no currency maths anywhere in the handoff."""
    request = handoff.build_listing_request(
        {"title": "Fridge", "price_ngwee": 123_456_789, "condition": "new"}
    )
    assert request.price_ngwee == 123_456_789


# --- deep links -------------------------------------------------------------
def test_deeplink_stores_only_a_hash(fake: FakeSupabaseClient) -> None:
    wrapper = MagicMock()
    wrapper.client = fake
    token, _expires = deeplink.mint(wrapper, session_id=SESSION_ID)
    stored = fake.table("intake_deep_links").rows[0]
    assert token not in str(stored)
    assert stored["token_hash"] == deeplink.hash_token(token)


def test_deeplink_is_single_use(fake: FakeSupabaseClient) -> None:
    wrapper = MagicMock()
    wrapper.client = fake
    token, _ = deeplink.mint(wrapper, session_id=SESSION_ID)
    assert deeplink.redeem(wrapper, token=token) == SESSION_ID
    with pytest.raises(Exception) as exc:
        deeplink.redeem(wrapper, token=token)
    assert getattr(exc.value, "code", "") == "intake_link_invalid"


def test_deeplink_expires(fake: FakeSupabaseClient) -> None:
    wrapper = MagicMock()
    wrapper.client = fake
    token, _ = deeplink.mint(wrapper, session_id=SESSION_ID, ttl_seconds=60)
    later = datetime.now(UTC) + timedelta(seconds=61)
    with pytest.raises(Exception) as exc:
        deeplink.redeem(wrapper, token=token, now=later)
    assert getattr(exc.value, "code", "") == "intake_link_invalid"


def test_deeplink_unknown_token_is_indistinguishable(fake: FakeSupabaseClient) -> None:
    """Unknown, expired and spent must all look identical — no probing oracle."""
    wrapper = MagicMock()
    wrapper.client = fake
    with pytest.raises(Exception) as exc:
        deeplink.redeem(wrapper, token="never-minted")
    assert getattr(exc.value, "http_status", 0) == 404


# --- ownership --------------------------------------------------------------
def test_get_session_requires_auth(client: TestClient, fake: FakeSupabaseClient) -> None:
    _seed(fake)
    response = client.get(f"/vendor/intake/sessions/{SESSION_ID}")
    assert response.status_code == 401


def test_vendor_cannot_open_another_vendors_session(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _auth(monkeypatch)
    response = client.get(f"/vendor/intake/sessions/{OTHER_SESSION_ID}", headers=_headers())
    assert response.status_code == 403


def test_vendor_cannot_patch_another_vendors_draft(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _auth(monkeypatch)
    response = client.patch(
        f"/vendor/intake/sessions/{OTHER_SESSION_ID}/draft",
        headers=_headers(),
        json={"title": "Stolen"},
    )
    assert response.status_code == 403


def test_valid_link_for_another_vendors_session_still_403s(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The token is not the authorisation — this is the whole claim of the design."""
    _seed(fake)
    _auth(monkeypatch)
    wrapper = MagicMock()
    wrapper.client = fake
    token, _ = deeplink.mint(wrapper, session_id=OTHER_SESSION_ID)

    response = client.post(
        "/vendor/intake/links/redeem", headers=_headers(), json={"token": token}
    )
    assert response.status_code == 403


def test_redeeming_own_link_returns_the_session(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _auth(monkeypatch)
    wrapper = MagicMock()
    wrapper.client = fake
    token, _ = deeplink.mint(wrapper, session_id=SESSION_ID)

    response = client.post(
        "/vendor/intake/links/redeem", headers=_headers(), json={"token": token}
    )
    assert response.status_code == 200
    assert response.json()["id"] == SESSION_ID


# --- review surface ---------------------------------------------------------
def test_detail_exposes_provenance_and_signed_media(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    fake.table("intake_media").rows.append(
        {
            "id": "media-1",
            "session_id": SESSION_ID,
            "storage_path": f"intake/{VENDOR_ID}/{SESSION_ID}/hash",
            "mime_type": "image/jpeg",
            "width_px": 800,
            "height_px": 600,
        }
    )
    _auth(monkeypatch)

    body = client.get(f"/vendor/intake/sessions/{SESSION_ID}", headers=_headers()).json()
    assert body["provenance"] == [
        {
            "field_name": "price_ngwee",
            "source": "rule",
            "confidence": 0.9,
            "model_ref": None,
        }
    ]
    assert body["media"][0]["signed_url"].startswith("https://signed.example/")
    assert body["media"][0]["ttl_seconds"] == 600


def test_detail_survives_storage_outage(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead bucket must not blank the page the vendor needs to fix text fields."""
    _seed(fake)
    fake.table("intake_media").rows.append(
        {
            "id": "media-1",
            "session_id": SESSION_ID,
            "storage_path": "intake/x/y/z",
            "mime_type": "image/jpeg",
            "width_px": None,
            "height_px": None,
        }
    )

    def boom(path: str, ttl: int) -> dict[str, str]:
        raise RuntimeError("storage down")

    fake.storage.bucket.create_signed_url = boom  # type: ignore[method-assign]
    _auth(monkeypatch)

    response = client.get(f"/vendor/intake/sessions/{SESSION_ID}", headers=_headers())
    assert response.status_code == 200
    assert response.json()["media"][0]["signed_url"] is None


def test_patch_marks_fields_vendor_typed(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _auth(monkeypatch)

    response = client.patch(
        f"/vendor/intake/sessions/{SESSION_ID}/draft",
        headers=_headers(),
        json={"title": "Samsung RT38 Fridge", "price_ngwee": 400_000},
    )
    assert response.status_code == 200

    draft = fake.table("intake_draft_fields").rows[0]
    assert draft["title"] == "Samsung RT38 Fridge"
    assert draft["price_ngwee"] == 400_000

    sources = {
        row["field_name"]: row["source"] for row in fake.table("intake_field_provenance").rows
    }
    assert sources["title"] == "vendor_typed"
    # The rule-sourced price the vendor overrode is now theirs.
    assert sources["price_ngwee"] == "vendor_typed"


def test_patch_rejected_on_terminal_session(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake, status=state_machine.APPROVED)
    _auth(monkeypatch)
    response = client.patch(
        f"/vendor/intake/sessions/{SESSION_ID}/draft",
        headers=_headers(),
        json={"title": "Too late"},
    )
    assert response.status_code == 409


def test_list_sessions_shows_only_own(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _auth(monkeypatch)
    rows = client.get("/vendor/intake/sessions", headers=_headers()).json()
    assert [row["id"] for row in rows] == [SESSION_ID]


# --- submission -------------------------------------------------------------
def test_submit_creates_a_draft_listing_and_advances(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _auth(monkeypatch)
    _stub_caps(monkeypatch)
    captured = _stub_listing_creation(monkeypatch)

    response = client.post(
        f"/vendor/intake/sessions/{SESSION_ID}/submit", headers=_headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["listing_status"] == "draft"
    assert body["session_status"] == state_machine.PENDING_ADMIN_REVIEW
    assert body["already_submitted"] is False

    # The request handed to the shared seam must never ask to publish.
    assert captured["body"].publish is False
    assert captured["vendor_id"] == VENDOR_ID

    session = fake.table("intake_sessions").rows[0]
    assert session["listing_id"] == body["listing_id"]
    assert session["submitted_at"] is not None


def test_submit_is_idempotent(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake)
    _auth(monkeypatch)
    _stub_caps(monkeypatch)
    _stub_listing_creation(monkeypatch)

    first = client.post(f"/vendor/intake/sessions/{SESSION_ID}/submit", headers=_headers())
    second = client.post(f"/vendor/intake/sessions/{SESSION_ID}/submit", headers=_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["already_submitted"] is True
    assert second.json()["listing_id"] == first.json()["listing_id"]


def test_submit_blocked_by_kyc_listing_cap(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tier quota applies to intake exactly as it does to a typed listing."""
    _seed(fake)
    _auth(monkeypatch)
    _stub_caps(monkeypatch, listing_count=5)
    captured = _stub_listing_creation(monkeypatch)

    response = client.post(
        f"/vendor/intake/sessions/{SESSION_ID}/submit", headers=_headers()
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "listing_cap_exceeded"
    # Nothing was created — the cap is checked before the write, not after.
    assert captured == {}


def test_submit_requires_ready_state(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake, status=state_machine.NEEDS_DETAILS)
    _auth(monkeypatch)
    _stub_caps(monkeypatch)
    _stub_listing_creation(monkeypatch)

    response = client.post(
        f"/vendor/intake/sessions/{SESSION_ID}/submit", headers=_headers()
    )
    assert response.status_code == 409


def test_submit_refuses_when_seam_returns_active(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Belt and braces: if the shared seam ever published, fail loudly."""
    _seed(fake)
    _auth(monkeypatch)
    _stub_caps(monkeypatch)
    _stub_listing_creation(monkeypatch, status="active")

    response = client.post(
        f"/vendor/intake/sessions/{SESSION_ID}/submit", headers=_headers()
    )
    assert response.status_code == 500


def test_submit_of_used_condition_draft_is_refused(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(fake, draft={"condition": "used"})
    _auth(monkeypatch)
    _stub_caps(monkeypatch)
    _stub_listing_creation(monkeypatch)

    response = client.post(
        f"/vendor/intake/sessions/{SESSION_ID}/submit", headers=_headers()
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["reason"] == "unsupported_condition"


def test_interrupted_session_resumes_from_needs_details(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A vendor who filled the gap can move forward without losing prior work."""
    _seed(fake, status=state_machine.NEEDS_DETAILS, draft={"price_ngwee": None})
    _auth(monkeypatch)

    detail = client.get(f"/vendor/intake/sessions/{SESSION_ID}", headers=_headers()).json()
    assert detail["missing_fields"] == ["price_ngwee"]
    assert detail["submittable"] is False

    patched = client.patch(
        f"/vendor/intake/sessions/{SESSION_ID}/draft",
        headers=_headers(),
        json={"price_ngwee": 350_000},
    ).json()
    assert patched["missing_fields"] == []
    assert patched["submittable"] is True
    # Earlier extraction survived the interruption.
    assert patched["draft"]["title"] == "Samsung Fridge"


def test_pending_requests_are_rendered_as_keys_not_copy(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lane is inbound-only: follow-ups are data the vendor app translates."""
    _seed(fake, status=state_machine.NEEDS_DETAILS)
    fake.table("intake_sessions").rows[0]["pending_requests"] = [
        {"key": "intake.question.price_missing", "field_name": "price_ngwee", "params": {}}
    ]
    _auth(monkeypatch)

    body = client.get(f"/vendor/intake/sessions/{SESSION_ID}", headers=_headers()).json()
    assert body["pending_requests"][0]["key"] == "intake.question.price_missing"
