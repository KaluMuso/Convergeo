"""R02-P12b vendor licences API tests — no live DB (MagicMock/fake service client).

Failure paths are the point here: guest 401s, non-admin 403s, the pinned-pending
apply, duplicate-live 409, notes-required 422s, transition 409s, the no-oracle
badge, and the expiring-queue bounds.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.routers.vendor_licences import REGULATED_CLASSES, VENDOR_LICENCE_APPLY_POLICY
from fastapi.testclient import TestClient

ADMIN_USER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_USER_ID = "22222222-2222-2222-2222-222222222222"
OTHER_USER_ID = "33333333-3333-3333-3333-333333333333"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_VENDOR_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
UNKNOWN_VENDOR_ID = "99999999-9999-9999-9999-999999999999"
LICENCE_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
VALID_TOKEN = "valid.jwt.token"
# Commercially sensitive test value — the log-capture test asserts it never leaks.
SECRET_LICENCE_NUMBER = "ZM-PH-SECRET-9988"


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._offset: int = 0
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("gte", column, value))
        return self

    def lte(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("lte", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def offset(self, count: int) -> FakeQuery:
        self._offset = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            row.setdefault("id", f"{len(self._parent.rows):08x}-0000-0000-0000-000000000000")
            self._parent.rows.append(row)
            return MagicMock(data=[dict(row)])

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        rows = [dict(row) for row in self._parent.rows if self._matches(row)]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: str(row.get(column, "")), reverse=desc)
        rows = rows[self._offset :]
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "in" and row.get(column) not in set(value):
                return False
            if op == "gte" and not str(row.get(column, "")) >= str(value):
                return False
            if op == "lte" and not str(row.get(column, "")) <= str(value):
                return False
        return True


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeRpcQuery:
    def __init__(self, result: Any) -> None:
        self._result = result

    def execute(self) -> MagicMock:
        return MagicMock(data=self._result)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "vendor_licences": FakeTable(),
            "audit_log": FakeTable(),
        }
        # (vendor_id, class) -> bool; anything absent derives to False, exactly
        # like the real vendor_licence_is_valid RPC for an unknown vendor.
        self.valid_by_key: dict[tuple[str, str], bool] = {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def table(self, name: str) -> FakeTable:
        return self.tables[name]

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpcQuery:
        self.rpc_calls.append((name, dict(params)))
        assert name == "vendor_licence_is_valid"
        key = (str(params["p_vendor_id"]), str(params["p_class"]))
        return FakeRpcQuery(self.valid_by_key.get(key, False))


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    fake = FakeSupabaseClient()
    wrapper = MagicMock()
    wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    # The AdminAuditRecorder writes through its own client getter — point it at
    # the same fake so audit rows land in fake.tables["audit_log"].
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: wrapper)
    # Rate limiter passes by default; the 429 test overrides this.
    monkeypatch.setattr(
        "app.routers.vendor_licences.bump_rate_counter",
        lambda **_kwargs: (True, 0),
    )
    return fake


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )


def _mock_roles(monkeypatch: pytest.MonkeyPatch, roles_by_user: dict[str, frozenset[str]]) -> None:
    def fake_load(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return roles_by_user.get(user_id, frozenset())

    monkeypatch.setattr("app.core.auth._load_user_roles", fake_load)


def _as_vendor(monkeypatch: pytest.MonkeyPatch, user_id: str = VENDOR_USER_ID) -> None:
    _mock_verify(monkeypatch, user_id)
    _mock_roles(monkeypatch, {user_id: frozenset({"vendor"})})


def _as_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_verify(monkeypatch, ADMIN_USER_ID)
    _mock_roles(monkeypatch, {ADMIN_USER_ID: frozenset({"admin"})})


def _as_customer(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_verify(monkeypatch, OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"customer"})})


AUTH = {"Authorization": f"Bearer {VALID_TOKEN}"}


def _seed_vendor(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": VENDOR_USER_ID,
            "status": "active",
            "display_name": "Acme Pharmacy",
            "slug": "acme-pharmacy",
        }
    )


def _seed_licence(
    fake: FakeSupabaseClient,
    *,
    licence_id: str = LICENCE_ID,
    vendor_id: str = VENDOR_ID,
    regulated_class: str = "pharmacy",
    status: str = "pending",
    expires_on: str = "2030-01-01",
) -> dict[str, Any]:
    row = {
        "id": licence_id,
        "vendor_id": vendor_id,
        "regulated_class": regulated_class,
        "regulator": "ZAMRA",
        "licence_number": SECRET_LICENCE_NUMBER,
        "issued_on": "2025-01-01",
        "expires_on": expires_on,
        "document_path": "licences/acme/zamra.pdf",
        "status": status,
        "reviewer_notes": None,
        "verified_by": None,
        "verified_at": None,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    fake.tables["vendor_licences"].rows.append(row)
    return row


def _apply_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "regulated_class": "pharmacy",
        "regulator": "ZAMRA",
        "licence_number": SECRET_LICENCE_NUMBER,
        "issued_on": "2025-01-01",
        "expires_on": "2030-01-01",
        "document_path": "licences/acme/zamra.pdf",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Auth failure paths
# ---------------------------------------------------------------------------


class TestAuthGuards:
    def test_guest_401_on_vendor_routes(self, client: TestClient) -> None:
        post = client.post("/vendor/licences", json=_apply_body())
        get = client.get("/vendor/licences")
        assert post.status_code == 401
        assert get.status_code == 401
        assert post.json()["error"]["code"] == "unauthorized"

    def test_guest_401_on_admin_routes(self, client: TestClient) -> None:
        assert client.get("/admin/licences").status_code == 401
        assert client.get("/admin/licences/expiring").status_code == 401
        verify = client.post(
            f"/admin/licences/{LICENCE_ID}/verify",
            json={"reviewer_notes": None},
        )
        assert verify.status_code == 401

    def test_non_admin_403_on_admin_routes(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_customer(monkeypatch)
        assert client.get("/admin/licences", headers=AUTH).status_code == 403
        assert (
            client.post(
                f"/admin/licences/{LICENCE_ID}/verify",
                headers=AUTH,
                json={"reviewer_notes": None},
            ).status_code
            == 403
        )

    def test_authed_user_without_vendor_profile_403(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        # Has the vendor role but owns no vendors row — must not be able to apply.
        _as_vendor(monkeypatch, OTHER_USER_ID)
        response = client.post("/vendor/licences", headers=AUTH, json=_apply_body())
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Vendor apply — pinned pending, duplicates, allowlist, rate limit, no logging
# ---------------------------------------------------------------------------


class TestVendorApply:
    def test_apply_creates_pending(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_vendor(monkeypatch)
        _seed_vendor(fake_client)
        response = client.post("/vendor/licences", headers=AUTH, json=_apply_body())
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending"
        assert body["regulated_class"] == "pharmacy"
        rows = fake_client.tables["vendor_licences"].rows
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"

    def test_apply_pins_pending_even_when_body_smuggles_verified(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """The API pins status server-side; the DB guard trigger is tested elsewhere."""
        _as_vendor(monkeypatch)
        _seed_vendor(fake_client)
        smuggled = _apply_body(
            status="verified",
            verified_by=VENDOR_USER_ID,
            verified_at="2026-01-01T00:00:00Z",
        )
        response = client.post("/vendor/licences", headers=AUTH, json=smuggled)
        assert response.status_code == 201
        assert response.json()["status"] == "pending"
        rows = fake_client.tables["vendor_licences"].rows
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        assert rows[0].get("verified_by") is None
        assert not any(row.get("status") == "verified" for row in rows)

    def test_duplicate_live_application_409(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_vendor(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="pending")
        response = client.post("/vendor/licences", headers=AUTH, json=_apply_body())
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "licence.already_applied"
        # A verified licence is also "live" — same 409.
        fake_client.tables["vendor_licences"].rows[0]["status"] = "verified"
        again = client.post("/vendor/licences", headers=AUTH, json=_apply_body())
        assert again.status_code == 409

    def test_reapply_allowed_after_rejection(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_vendor(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="rejected")
        response = client.post("/vendor/licences", headers=AUTH, json=_apply_body())
        assert response.status_code == 201
        assert response.json()["status"] == "pending"

    def test_apply_unknown_class_422(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_vendor(monkeypatch)
        _seed_vendor(fake_client)
        response = client.post(
            "/vendor/licences",
            headers=AUTH,
            json=_apply_body(regulated_class="fireworks"),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "licence.unknown_class"
        assert fake_client.tables["vendor_licences"].rows == []

    def test_apply_rate_limited_429(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_vendor(monkeypatch)
        _seed_vendor(fake_client)
        monkeypatch.setattr(
            "app.routers.vendor_licences.bump_rate_counter",
            lambda **_kwargs: (False, 3600),
        )
        response = client.post("/vendor/licences", headers=AUTH, json=_apply_body())
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"
        assert fake_client.tables["vendor_licences"].rows == []

    def test_apply_policy_is_ten_per_day(self) -> None:
        assert VENDOR_LICENCE_APPLY_POLICY.limit == 10
        assert VENDOR_LICENCE_APPLY_POLICY.window == timedelta(days=1)

    def test_licence_number_never_logged(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The migration marks licence_number commercially sensitive: never log it."""
        _as_vendor(monkeypatch)
        _seed_vendor(fake_client)
        with caplog.at_level(logging.DEBUG):
            ok = client.post("/vendor/licences", headers=AUTH, json=_apply_body())
            dup = client.post("/vendor/licences", headers=AUTH, json=_apply_body())
        assert ok.status_code == 201
        assert dup.status_code == 409
        assert SECRET_LICENCE_NUMBER not in caplog.text

    def test_list_own_licences_only(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_vendor(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client)
        _seed_licence(
            fake_client,
            licence_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
            vendor_id=OTHER_VENDOR_ID,
            regulated_class="alcohol",
        )
        response = client.get("/vendor/licences", headers=AUTH)
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["vendor_id"] == VENDOR_ID


# ---------------------------------------------------------------------------
# Admin decisions — audited, human-only, guarded transitions
# ---------------------------------------------------------------------------


class TestAdminDecisions:
    def test_queue_lists_pending(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="pending")
        _seed_licence(
            fake_client,
            licence_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
            regulated_class="alcohol",
            status="verified",
        )
        response = client.get("/admin/licences", headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        assert [item["status"] for item in body["items"]] == ["pending"]
        assert body["items"][0]["vendor_display_name"] == "Acme Pharmacy"
        assert body["limit"] == 50
        assert body["offset"] == 0

    def test_verify_sets_fields_and_writes_audit_row(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="pending")
        response = client.post(
            f"/admin/licences/{LICENCE_ID}/verify",
            headers=AUTH,
            json={"reviewer_notes": "Checked against ZAMRA register"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "verified"
        assert body["verified_by"] == ADMIN_USER_ID
        assert body["verified_at"] is not None

        row = fake_client.tables["vendor_licences"].rows[0]
        assert row["status"] == "verified"
        assert row["verified_by"] == ADMIN_USER_ID

        audit_rows = fake_client.tables["audit_log"].rows
        assert len(audit_rows) == 1
        audit = audit_rows[0]
        assert audit["action"] == "admin.licence.verify"
        assert audit["actor"] == ADMIN_USER_ID
        assert audit["entity_type"] == "vendor_licence"
        assert audit["before"]["status"] == "pending"
        assert audit["after"]["status"] == "verified"
        # Audit rows are log-adjacent: the licence number must never appear.
        assert SECRET_LICENCE_NUMBER not in str(audit)

    def test_verify_already_revoked_409(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="revoked")
        response = client.post(
            f"/admin/licences/{LICENCE_ID}/verify",
            headers=AUTH,
            json={"reviewer_notes": None},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "licence.invalid_transition"
        assert fake_client.tables["vendor_licences"].rows[0]["status"] == "revoked"
        assert fake_client.tables["audit_log"].rows == []

    def test_reject_without_notes_422(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="pending")
        missing = client.post(f"/admin/licences/{LICENCE_ID}/reject", headers=AUTH, json={})
        too_short = client.post(
            f"/admin/licences/{LICENCE_ID}/reject",
            headers=AUTH,
            json={"reviewer_notes": "too short"},
        )
        assert missing.status_code == 422
        assert too_short.status_code == 422
        assert fake_client.tables["vendor_licences"].rows[0]["status"] == "pending"

    def test_reject_with_notes_records_decision(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="pending")
        response = client.post(
            f"/admin/licences/{LICENCE_ID}/reject",
            headers=AUTH,
            json={"reviewer_notes": "Number does not match the ZAMRA register"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
        row = fake_client.tables["vendor_licences"].rows[0]
        assert row["status"] == "rejected"
        assert row["reviewer_notes"] == "Number does not match the ZAMRA register"
        assert fake_client.tables["audit_log"].rows[0]["action"] == "admin.licence.reject"

    def test_revoke_verified_licence(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="verified")
        response = client.post(
            f"/admin/licences/{LICENCE_ID}/revoke",
            headers=AUTH,
            json={"reviewer_notes": "Regulator suspended this licence"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "revoked"
        assert fake_client.tables["audit_log"].rows[0]["action"] == "admin.licence.revoke"

    def test_revoke_pending_licence_409(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="pending")
        response = client.post(
            f"/admin/licences/{LICENCE_ID}/revoke",
            headers=AUTH,
            json={"reviewer_notes": "Regulator suspended this licence"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "licence.invalid_transition"

    def test_decision_on_missing_licence_404(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        response = client.post(
            f"/admin/licences/{LICENCE_ID}/verify",
            headers=AUTH,
            json={"reviewer_notes": None},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Expiring queue
# ---------------------------------------------------------------------------


class TestExpiringQueue:
    def test_days_bounds_are_422(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        assert client.get("/admin/licences/expiring?days=0", headers=AUTH).status_code == 422
        assert client.get("/admin/licences/expiring?days=9999", headers=AUTH).status_code == 422

    def test_expiring_window_contents(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_client: FakeSupabaseClient,
    ) -> None:
        _as_admin(monkeypatch)
        _seed_vendor(fake_client)
        today = datetime.now(UTC).date()
        _seed_licence(
            fake_client,
            licence_id="11110000-0000-0000-0000-000000000001",
            status="verified",
            expires_on=(today + timedelta(days=10)).isoformat(),
        )
        _seed_licence(
            fake_client,
            licence_id="11110000-0000-0000-0000-000000000002",
            regulated_class="alcohol",
            status="verified",
            expires_on=(today + timedelta(days=200)).isoformat(),
        )
        _seed_licence(
            fake_client,
            licence_id="11110000-0000-0000-0000-000000000003",
            regulated_class="food",
            status="verified",
            expires_on=(today - timedelta(days=1)).isoformat(),
        )
        _seed_licence(
            fake_client,
            licence_id="11110000-0000-0000-0000-000000000004",
            regulated_class="agrochemicals",
            status="pending",
            expires_on=(today + timedelta(days=5)).isoformat(),
        )
        response = client.get("/admin/licences/expiring?days=30", headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        assert body["days"] == 30
        assert [item["id"] for item in body["items"]] == ["11110000-0000-0000-0000-000000000001"]
        assert body["items"][0]["days_left"] == 10


# ---------------------------------------------------------------------------
# Public badge — boolean only, no oracle
# ---------------------------------------------------------------------------


class TestLicenceBadge:
    def test_valid_licence_true(self, client: TestClient, fake_client: FakeSupabaseClient) -> None:
        fake_client.valid_by_key[(VENDOR_ID, "pharmacy")] = True
        response = client.get(f"/vendors/{VENDOR_ID}/licence-badge?class=pharmacy")
        assert response.status_code == 200
        assert response.json() == {"valid": True}

    def test_boolean_only_never_leaks_details(
        self, client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        fake_client.valid_by_key[(VENDOR_ID, "pharmacy")] = True
        _seed_licence(fake_client, status="verified")
        response = client.get(f"/vendors/{VENDOR_ID}/licence-badge?class=pharmacy")
        assert set(response.json().keys()) == {"valid"}
        assert SECRET_LICENCE_NUMBER not in response.text

    def test_unknown_vendor_same_shape_as_invalid(
        self, client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        """No existence oracle: unknown vendor and known-but-invalid are identical."""
        # Known vendor with a licence that does NOT derive valid (e.g. pending).
        _seed_vendor(fake_client)
        _seed_licence(fake_client, status="pending")
        known_invalid = client.get(f"/vendors/{VENDOR_ID}/licence-badge?class=pharmacy")
        unknown = client.get(f"/vendors/{UNKNOWN_VENDOR_ID}/licence-badge?class=pharmacy")
        assert known_invalid.status_code == unknown.status_code == 200
        assert known_invalid.json() == unknown.json() == {"valid": False}

    def test_unknown_class_422(self, client: TestClient, fake_client: FakeSupabaseClient) -> None:
        response = client.get(f"/vendors/{VENDOR_ID}/licence-badge?class=fireworks")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "licence.unknown_class"
        # The allowlist is the single source of truth for both apply and badge.
        assert set(response.json()["error"]["details"]["allowed"]) == set(REGULATED_CLASSES)

    def test_badge_fails_closed_on_rpc_error(
        self,
        client: TestClient,
        fake_client: FakeSupabaseClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _boom(name: str, params: dict[str, Any]) -> FakeRpcQuery:
            raise RuntimeError("connection reset")

        monkeypatch.setattr(fake_client, "rpc", _boom)
        response = client.get(f"/vendors/{VENDOR_ID}/licence-badge?class=pharmacy")
        assert response.status_code == 200
        assert response.json() == {"valid": False}
