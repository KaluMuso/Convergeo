"""Enquiry-threads API (R02-P13b, D37) — two-party fence, no-oracle 404s, outbox.

No live DB: MagicMock/fake service-client chains per tests/test_cart.py and
tests/test_service_reviews.py conventions. The schema-side fence (RLS, CHECK,
guard trigger) is proven in tests/rls/test_matrix.py; this file proves the API
half — vendor derived server-side from the subject, outsiders indistinguishable
from nonexistence, closed threads refusing writes, bodies screened and masked,
and notifications that never carry message content.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.moderation.contact_strip import NOTICE_TOKEN
from fastapi import FastAPI
from fastapi.testclient import TestClient

CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B = "22222222-2222-2222-2222-222222222222"
VENDOR_OWNER = "33333333-3333-3333-3333-333333333333"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_ID = "10101010-1010-1010-1010-101010101010"
WHOLESALE_LISTING_ID = "20202020-2020-2020-2020-202020202020"
EVENT_ID = "30303030-3030-3030-3030-303030303030"
ABSENT_UUID = "99999999-9999-9999-9999-999999999999"


@pytest.fixture(autouse=True)
def _allow_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.enquiries.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._neq: list[tuple[str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._eq.append((column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQuery:
        self._neq.append((column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
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
        for column, value in self._eq:
            if row.get(column) != value:
                return False
        for column, value in self._neq:
            if row.get(column) == value:
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert isinstance(self._payload, dict)
            if self._parent.name == "enquiry_threads":
                # Emulate enquiry_threads_one_open_per_subject (partial unique
                # index on non-closed threads) so the race path stays honest.
                for existing in self._parent.rows:
                    if (
                        existing.get("customer_id") == self._payload.get("customer_id")
                        and existing.get("subject_kind") == self._payload.get("subject_kind")
                        and existing.get("subject_id") == self._payload.get("subject_id")
                        and existing.get("status") != "closed"
                    ):
                        raise RuntimeError(
                            "duplicate key value violates unique constraint "
                            '"enquiry_threads_one_open_per_subject"'
                        )
            row = dict(self._payload)
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        matched = [row for row in self._parent.rows if self._match(row)]
        if self._op == "update":
            assert isinstance(self._payload, dict)
            for row in matched:
                row.update(self._payload)
            return MagicMock(data=[dict(row) for row in matched])

        rows = matched
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=list(rows))


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable(name)
        return self.tables[name]


class _Wrapper:
    def __init__(self, client: FakeClient) -> None:
        self.client = client


def _make_client(*, user_id: str, fake: FakeClient) -> TestClient:
    app: FastAPI = create_app()

    async def override_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, roles=frozenset({"customer"}), token="test-token")

    def override_service_client() -> _Wrapper:
        return _Wrapper(fake)

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_supabase_client] = override_service_client
    return TestClient(app, raise_server_exceptions=False)


def _seed_vendor_and_subjects(fake: FakeClient) -> None:
    fake.table("vendors").rows.append({"id": VENDOR_ID, "owner_user_id": VENDOR_OWNER})
    fake.table("vendor_listings").rows.append(
        {"id": LISTING_ID, "vendor_id": VENDOR_ID, "status": "active", "wholesale": False}
    )
    fake.table("vendor_listings").rows.append(
        {
            "id": WHOLESALE_LISTING_ID,
            "vendor_id": VENDOR_ID,
            "status": "active",
            "wholesale": True,
        }
    )
    fake.table("events").rows.append(
        {"id": EVENT_ID, "organiser_vendor_id": VENDOR_ID, "status": "draft"}
    )


def _open_enquiry(
    client: TestClient,
    *,
    subject_kind: str = "listing",
    subject_id: str = LISTING_ID,
    body: str = "Is this available in blue?",
) -> Any:
    return client.post(
        "/enquiries",
        json={"subject_kind": subject_kind, "subject_id": subject_id, "body": body},
    )


@pytest.fixture
def fake() -> FakeClient:
    fake = FakeClient()
    _seed_vendor_and_subjects(fake)
    return fake


# ---------------------------------------------------------------------------
# Guests: 401 on every endpoint
# ---------------------------------------------------------------------------


class TestGuestIsRefusedEverywhere:
    @pytest.mark.parametrize(
        ("method", "path", "payload"),
        [
            (
                "POST",
                "/enquiries",
                {"subject_kind": "listing", "subject_id": LISTING_ID, "body": "hi"},
            ),
            ("GET", "/enquiries", None),
            ("GET", f"/enquiries/{ABSENT_UUID}/messages", None),
            ("POST", f"/enquiries/{ABSENT_UUID}/messages", {"body": "hi"}),
            ("POST", f"/enquiries/{ABSENT_UUID}/close", None),
        ],
    )
    def test_guest_gets_401(self, method: str, path: str, payload: dict[str, Any] | None) -> None:
        with TestClient(create_app(), raise_server_exceptions=False) as client:
            response = client.request(method, path, json=payload)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


# ---------------------------------------------------------------------------
# Creating threads — the D37 fence at the API layer
# ---------------------------------------------------------------------------


class TestCreateEnquiry:
    def test_customer_opens_thread_on_listing(self, fake: FakeClient) -> None:
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        response = _open_enquiry(client)
        assert response.status_code == 201
        payload = response.json()
        # The vendor is derived from the subject row, never from the request.
        assert payload["thread"]["vendor_id"] == VENDOR_ID
        assert payload["thread"]["customer_id"] == CUSTOMER_A
        assert payload["thread"]["status"] == "open"
        assert payload["reused_existing_thread"] is False
        assert payload["message"]["sender_role"] == "customer"
        assert len(fake.table("enquiry_threads").rows) == 1
        assert len(fake.table("enquiry_messages").rows) == 1

    def test_client_cannot_name_a_counterparty(self, fake: FakeClient) -> None:
        """The request schema has no vendor/recipient field at all — strict
        models reject an attempt to smuggle one in (C2C unrepresentable)."""
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        response = client.post(
            "/enquiries",
            json={
                "subject_kind": "listing",
                "subject_id": LISTING_ID,
                "body": "hi",
                "vendor_id": VENDOR_ID,
            },
        )
        assert response.status_code == 422

    def test_subject_that_is_actually_a_user_id_is_404(self, fake: FakeClient) -> None:
        """A thread whose counterparty is another customer cannot be caused:
        a user id is not a subject row, so resolution fails closed."""
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        response = _open_enquiry(client, subject_id=CUSTOMER_B)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "enquiry.subject_not_found"
        assert fake.table("enquiry_threads").rows == []

    def test_unpublished_event_subject_is_404(self, fake: FakeClient) -> None:
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        response = _open_enquiry(client, subject_kind="event", subject_id=EVENT_ID)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "enquiry.subject_not_found"

    def test_wholesale_subject_404_matches_absent_subject_for_consumer(
        self, fake: FakeClient
    ) -> None:
        """D36: the enquiry endpoint must not become the wholesale existence
        oracle the catalog closed — identical envelope to a nonexistent id."""
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        wholesale = _open_enquiry(client, subject_id=WHOLESALE_LISTING_ID)
        absent = _open_enquiry(client, subject_id=ABSENT_UUID)
        assert wholesale.status_code == absent.status_code == 404
        wholesale_error = wholesale.json()["error"]
        absent_error = absent.json()["error"]
        assert wholesale_error["code"] == absent_error["code"]
        assert wholesale_error["message"] == absent_error["message"]
        assert wholesale_error["details"] == absent_error["details"]

    def test_vendor_owner_cannot_enquire_about_own_listing(self, fake: FakeClient) -> None:
        client = _make_client(user_id=VENDOR_OWNER, fake=fake)
        response = _open_enquiry(client)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "enquiry.own_subject"
        assert fake.table("enquiry_threads").rows == []

    def test_reopen_appends_to_existing_open_thread(self, fake: FakeClient) -> None:
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        first = _open_enquiry(client)
        assert first.status_code == 201
        second = _open_enquiry(client, body="Any update?")
        assert second.status_code == 200
        assert second.json()["reused_existing_thread"] is True
        assert second.json()["thread"]["id"] == first.json()["thread"]["id"]
        assert len(fake.table("enquiry_threads").rows) == 1
        assert len(fake.table("enquiry_messages").rows) == 2

    def test_unique_index_race_appends_instead_of_500(
        self, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even if the pre-check misses (concurrent create), the unique-index
        violation is recovered by appending — never a 500."""
        from app.routers import enquiries as enquiries_module

        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        assert _open_enquiry(client).status_code == 201

        real_fetch = enquiries_module._fetch_open_thread
        calls = {"count": 0}

        def flaky_fetch(service_client: Any, **kwargs: Any) -> dict[str, Any] | None:
            calls["count"] += 1
            if calls["count"] == 1:
                return None  # simulated race: pre-check sees nothing
            return real_fetch(service_client, **kwargs)

        monkeypatch.setattr(enquiries_module, "_fetch_open_thread", flaky_fetch)
        response = _open_enquiry(client, body="Racing you")
        assert response.status_code == 200
        assert response.json()["reused_existing_thread"] is True
        assert len(fake.table("enquiry_threads").rows) == 1
        assert len(fake.table("enquiry_messages").rows) == 2

    def test_closed_thread_does_not_block_a_new_one(self, fake: FakeClient) -> None:
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        first = _open_enquiry(client)
        thread_id = first.json()["thread"]["id"]
        assert client.post(f"/enquiries/{thread_id}/close").status_code == 200
        second = _open_enquiry(client, body="New question")
        assert second.status_code == 201
        assert second.json()["thread"]["id"] != thread_id
        assert len(fake.table("enquiry_threads").rows) == 2

    def test_body_over_2000_chars_is_422(self, fake: FakeClient) -> None:
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        response = _open_enquiry(client, body="a" * 2001)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_whitespace_only_body_is_422(self, fake: FakeClient) -> None:
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        response = _open_enquiry(client, body="   ")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Untrusted bodies — screened and contact-masked via the existing helpers
# ---------------------------------------------------------------------------


class TestBodyModeration:
    def test_prohibited_content_is_rejected(self, fake: FakeClient) -> None:
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        response = _open_enquiry(client, body="Do you sell tramadol in bulk?")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "enquiry.prohibited_content"
        assert fake.table("enquiry_messages").rows == []

    def test_contact_details_are_masked_not_stored(self, fake: FakeClient) -> None:
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        response = _open_enquiry(client, body="Call me on 0971234567 for a deal")
        assert response.status_code == 201
        stored = fake.table("enquiry_messages").rows[0]["body"]
        assert "0971234567" not in stored
        assert NOTICE_TOKEN in stored
        assert "0971234567" not in response.json()["message"]["body"]


# ---------------------------------------------------------------------------
# Two-party isolation — the 404 is no existence oracle
# ---------------------------------------------------------------------------


class TestTwoPartyIsolation:
    def test_outsider_404_is_identical_to_nonexistent_thread(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        thread_id = _open_enquiry(customer_a).json()["thread"]["id"]

        customer_b = _make_client(user_id=CUSTOMER_B, fake=fake)
        real_thread = customer_b.get(f"/enquiries/{thread_id}/messages")
        ghost_thread = customer_b.get(f"/enquiries/{ABSENT_UUID}/messages")

        assert real_thread.status_code == ghost_thread.status_code == 404
        real_error = real_thread.json()["error"]
        ghost_error = ghost_thread.json()["error"]
        assert real_error["code"] == ghost_error["code"] == "enquiry.not_found"
        assert real_error["message"] == ghost_error["message"]
        assert real_error["details"] == ghost_error["details"]

    def test_outsider_cannot_post_close_or_read(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        thread_id = _open_enquiry(customer_a).json()["thread"]["id"]

        customer_b = _make_client(user_id=CUSTOMER_B, fake=fake)
        assert (
            customer_b.post(
                f"/enquiries/{thread_id}/messages", json={"body": "let me in"}
            ).status_code
            == 404
        )
        assert customer_b.post(f"/enquiries/{thread_id}/close").status_code == 404
        assert len(fake.table("enquiry_messages").rows) == 1

    def test_both_parties_read_the_thread(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        thread_id = _open_enquiry(customer_a).json()["thread"]["id"]

        vendor = _make_client(user_id=VENDOR_OWNER, fake=fake)
        assert customer_a.get(f"/enquiries/{thread_id}/messages").status_code == 200
        assert vendor.get(f"/enquiries/{thread_id}/messages").status_code == 200

    def test_thread_list_is_scoped_to_the_caller(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        _open_enquiry(customer_a)

        vendor = _make_client(user_id=VENDOR_OWNER, fake=fake)
        customer_b = _make_client(user_id=CUSTOMER_B, fake=fake)
        assert len(customer_a.get("/enquiries").json()["items"]) == 1
        assert len(vendor.get("/enquiries").json()["items"]) == 1
        assert customer_b.get("/enquiries").json()["items"] == []


# ---------------------------------------------------------------------------
# Replies + close
# ---------------------------------------------------------------------------


class TestRepliesAndClose:
    def test_vendor_reply_succeeds_and_marks_answered(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        thread_id = _open_enquiry(customer_a).json()["thread"]["id"]

        vendor = _make_client(user_id=VENDOR_OWNER, fake=fake)
        response = vendor.post(f"/enquiries/{thread_id}/messages", json={"body": "Yes, in stock"})
        assert response.status_code == 201
        payload = response.json()
        assert payload["message"]["sender_role"] == "vendor"
        assert payload["thread"]["status"] == "answered"
        stored_thread = fake.table("enquiry_threads").rows[0]
        assert stored_thread["status"] == "answered"

    def test_reply_to_closed_thread_is_409(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        thread_id = _open_enquiry(customer_a).json()["thread"]["id"]
        assert customer_a.post(f"/enquiries/{thread_id}/close").status_code == 200

        vendor = _make_client(user_id=VENDOR_OWNER, fake=fake)
        response = vendor.post(f"/enquiries/{thread_id}/messages", json={"body": "Too late?"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "enquiry.closed"
        assert len(fake.table("enquiry_messages").rows) == 1

    def test_either_party_may_close(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        first_id = _open_enquiry(customer_a).json()["thread"]["id"]
        assert customer_a.post(f"/enquiries/{first_id}/close").json()["status"] == "closed"

        second_id = _open_enquiry(customer_a, body="Another question").json()["thread"]["id"]
        vendor = _make_client(user_id=VENDOR_OWNER, fake=fake)
        assert vendor.post(f"/enquiries/{second_id}/close").json()["status"] == "closed"


# ---------------------------------------------------------------------------
# Notifications — outbox only, and never the message body
# ---------------------------------------------------------------------------


class TestNotifications:
    def test_new_thread_enqueues_vendor_notification(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        _open_enquiry(customer_a, body="Secret question about stock")
        rows = fake.table("notification_outbox").rows
        assert len(rows) == 1
        assert rows[0]["template"] == "enquiry_opened"
        assert rows[0]["channel"] == "whatsapp"
        assert rows[0]["payload"]["vendor_id"] == VENDOR_ID

    def test_vendor_reply_enqueues_customer_notification(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        thread_id = _open_enquiry(customer_a).json()["thread"]["id"]
        vendor = _make_client(user_id=VENDOR_OWNER, fake=fake)
        vendor.post(f"/enquiries/{thread_id}/messages", json={"body": "Reply text"})
        templates = [row["template"] for row in fake.table("notification_outbox").rows]
        assert templates == ["enquiry_opened", "enquiry_reply"]

    def test_outbox_payload_never_contains_the_body(self, fake: FakeClient) -> None:
        """Message content is private correspondence — the off-platform
        notification only says a message exists (D37)."""
        marker = "Secret question about stock"
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        thread_id = _open_enquiry(customer_a, body=marker).json()["thread"]["id"]
        vendor = _make_client(user_id=VENDOR_OWNER, fake=fake)
        vendor.post(f"/enquiries/{thread_id}/messages", json={"body": "Reply " + marker})
        for row in fake.table("notification_outbox").rows:
            assert "body" not in row["payload"]
            assert marker not in str(row["payload"])

    def test_customer_followup_does_not_renotify(self, fake: FakeClient) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        _open_enquiry(customer_a)
        _open_enquiry(customer_a, body="Follow-up")
        assert len(fake.table("notification_outbox").rows) == 1


# ---------------------------------------------------------------------------
# Rate limiting — the router enforces the per-user ceiling in-process
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_thread_creation_over_user_limit_is_429(
        self, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def deny_user_scope(**kwargs: Any) -> tuple[bool, int]:
            if str(kwargs.get("scope", "")).startswith("enquiries_user_"):
                return (False, 42)
            return (True, 0)

        monkeypatch.setattr("app.routers.enquiries.bump_rate_counter", deny_user_scope)
        client = _make_client(user_id=CUSTOMER_A, fake=fake)
        response = _open_enquiry(client)
        assert response.status_code == 429
        error = response.json()["error"]
        assert error["code"] == "rate_limited"
        assert error["details"]["retry_after"] == 42
        assert fake.table("enquiry_threads").rows == []

    def test_message_ip_limit_is_enforced(
        self, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        customer_a = _make_client(user_id=CUSTOMER_A, fake=fake)
        thread_id = _open_enquiry(customer_a).json()["thread"]["id"]

        def deny_ip_scope(**kwargs: Any) -> tuple[bool, int]:
            if str(kwargs.get("scope", "")).startswith("enquiries_ip_"):
                return (False, 7)
            return (True, 0)

        monkeypatch.setattr("app.routers.enquiries.bump_rate_counter", deny_ip_scope)
        response = customer_a.post(f"/enquiries/{thread_id}/messages", json={"body": "spam"})
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"
        assert len(fake.table("enquiry_messages").rows) == 1
