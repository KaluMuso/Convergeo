"""2026-11 admin governance at the API layer (DB-free).

D2 finance.operate, D3 finance tiles, the audit-log viewer (audit.read, masking),
admin account deactivation, denied-attempt audit rows, audit enrichment, support PII
masking and the delivery-partner consent gate. Route reachability for every identity
is covered exhaustively by tests/test_admin_role_route_matrix.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.admin_audit import AdminAuditRecorder
from app.core.auth import (
    ADMIN_PERMISSIONS,
    CurrentUser,
    admin_permissions_for_request,
    get_current_user,
    load_admin_permissions,
)
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.routers import admin_dashboards
from app.routers.admin_audit_log import MASK, mask_pii
from app.routers.admin_support import ContextCardOut, mask_phone
from app.services.dispatch import service as dispatch_service
from app.supabase_client import get_supabase_service_client
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

USER = "00000000-0000-0000-0000-0000000000a1"
TARGET = "00000000-0000-0000-0000-0000000000b2"


class Recorder:
    """Chainable PostgREST fake that records inserts and returns canned rows."""

    def __init__(self, rows: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.rows = rows or {}
        self.inserts: list[tuple[str, dict[str, Any]]] = []
        self.rpcs: list[tuple[str, dict[str, Any]]] = []
        self.rpc_error: APIError | None = None
        self.client = self
        self.auth = SimpleNamespace(
            admin=SimpleNamespace(
                get_user_by_id=lambda uid: SimpleNamespace(
                    user=SimpleNamespace(email=f"{uid[-2:]}@example.test")
                )
            )
        )

    def table(self, name: str) -> Any:
        recorder = self
        query = MagicMock()
        for method in (
            "select", "in_", "eq", "neq", "order", "limit", "or_", "is_", "ilike", "range",
            "gte", "lte", "gt", "lt", "like", "update", "delete", "maybe_single",
        ):  # fmt: skip
            getattr(query, method).return_value = query

        def insert(payload: dict[str, Any]) -> Any:
            recorder.inserts.append((name, payload))
            query.execute.return_value = SimpleNamespace(data=[{"id": "row-1", **payload}])
            return query

        query.insert.side_effect = insert
        query.execute.return_value = SimpleNamespace(data=self.rows.get(name, []), count=0)
        return query

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        self.rpcs.append((name, params))
        if self.rpc_error is not None:
            error = self.rpc_error

            def boom() -> Any:
                raise error

            return SimpleNamespace(execute=boom)
        return SimpleNamespace(
            execute=lambda: SimpleNamespace(data={"user_id": params.get("p_target")})
        )


def _client(
    monkeypatch: pytest.MonkeyPatch,
    roles: frozenset[str],
    permissions: tuple[str, ...] = (),
    rows: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[TestClient, Recorder]:
    fake = Recorder({"admin_roles": [{"permissions": list(permissions)}], **(rows or {})})
    app = create_app()
    user = CurrentUser(id=USER, roles=roles, token="t")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_supabase_client] = lambda: fake
    app.dependency_overrides[get_supabase_service_client] = lambda: fake
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: fake)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: fake)
    return TestClient(app, raise_server_exceptions=False), fake


# ---------------------------------------------------------------------------
# Permission vocabulary
# ---------------------------------------------------------------------------


def test_new_permissions_exist_and_map_to_routes() -> None:
    assert {
        "finance.operate",
        "services.manage",
        "support.manage",
        "logistics.manage",
        "audit.read",
    } <= ADMIN_PERMISSIONS
    assert admin_permissions_for_request("/admin/refunds/execute", "POST") == {"finance.operate"}
    assert admin_permissions_for_request(
        "/admin/orders/{order_id}/cod/confirm-collection", "POST"
    ) == {"finance.operate"}
    assert admin_permissions_for_request("/admin/disputes", "GET") == {
        "finance.read",
        "finance.operate",
        "support.manage",
    }
    assert admin_permissions_for_request("/admin/dispatch/board", "GET") == {"logistics.manage"}
    assert admin_permissions_for_request("/admin/audit-log", "GET") == {"audit.read"}
    # Platform controls stay unmapped: only the unrestricted roles reach them.
    assert admin_permissions_for_request("/admin/config/commissions/{category_key}", "PATCH") == (
        frozenset()
    )


def test_admin_role_does_not_imply_audit_read_but_superadmin_does() -> None:
    fake = Recorder()
    admin = load_admin_permissions(
        CurrentUser(id=USER, roles=frozenset({"admin"}), token="t"),
        fake,  # type: ignore[arg-type]
    )
    superadmin = load_admin_permissions(
        CurrentUser(id=USER, roles=frozenset({"superadmin"}), token="t"),
        fake,  # type: ignore[arg-type]
    )
    assert "audit.read" not in admin and "finance.operate" in admin
    assert superadmin == ADMIN_PERMISSIONS


# ---------------------------------------------------------------------------
# D3 — finance tiles require finance.read
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_dashboard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    admin_dashboards.clear_dashboard_cache()
    payload = admin_dashboards.DashboardOut.model_validate(
        {
            "gmv_ngwee": 12_500,
            "orders_by_status": {},
            "payout_liabilities": {
                "escrow_held_ngwee": 900,
                "released_unpaid_ngwee": 100,
                "total_ngwee": 1000,
            },
            "reconciliation": {"status": "unknown"},
            "counts": {"vendors": 1, "listings": 2, "products": 3},
            "ai_usage": {"data_available": True, "flagged": False, "cap_usd": 15},
            "funnel": {
                "checkout_started": 0,
                "checkout_completed": 0,
                "orders_placed": 0,
                "orders_completed": 0,
            },
            "cached_at": "2026-11-13T10:00:00Z",
        }
    )
    monkeypatch.setattr(admin_dashboards, "build_dashboard", lambda _client: payload)
    monkeypatch.setattr(
        admin_dashboards, "_latest_reconciliation", lambda _client: payload.reconciliation
    )
    yield
    admin_dashboards.clear_dashboard_cache()


def test_analytics_only_role_gets_no_finance_tiles(
    monkeypatch: pytest.MonkeyPatch, fixed_dashboard: None
) -> None:
    client, _ = _client(monkeypatch, frozenset({"rbac_analyst"}), ("analytics.read",))
    body = client.get("/admin/dashboard").json()
    assert body["payout_liabilities"] is None and body["reconciliation"] is None
    assert body["finance_visible"] is False
    assert body["gmv_ngwee"] == 12_500  # order value stays visible to analytics


@pytest.mark.parametrize(
    "roles,permissions",
    [
        (frozenset({"rbac_cfo"}), ("analytics.read", "finance.read")),
        (frozenset({"admin"}), ()),
        (frozenset({"superadmin"}), ()),
    ],
)
def test_finance_holders_see_finance_tiles(
    monkeypatch: pytest.MonkeyPatch,
    fixed_dashboard: None,
    roles: frozenset[str],
    permissions: tuple[str, ...],
) -> None:
    client, _ = _client(monkeypatch, roles, permissions)
    body = client.get("/admin/dashboard").json()
    assert body["payout_liabilities"]["total_ngwee"] == 1000
    assert body["finance_visible"] is True


# ---------------------------------------------------------------------------
# Audit-log viewer
# ---------------------------------------------------------------------------

AUDIT_ROW = {
    "id": "a1",
    "at": "2026-11-13T09:00:00Z",
    "actor": USER,
    "actor_roles": ["admin"],
    "action": "admin.disputes.decide",
    "entity_type": "dispute",
    "entity_id": TARGET,
    "outcome": "success",
    "request_id": "req-9",
    "reason": "refund approved",
    "before": {"status": "open", "customer_phone": "+260971234567"},
    "after": {"contact": {"email": "a@b.co", "name": "Mwila"}, "amount_ngwee": 5000},
}


def test_mask_pii_masks_nested_personal_data() -> None:
    masked = mask_pii(AUDIT_ROW["after"])
    assert masked == {"contact": {"email": MASK, "name": MASK}, "amount_ngwee": 5000}
    assert mask_pii({"note": "+260971234567"}) == {"note": MASK}
    assert mask_pii({"status": "open", "ids": ["x"]}) == {"status": "open", "ids": ["x"]}


@pytest.mark.parametrize(
    "roles,permissions,status",
    [
        (frozenset({"superadmin"}), (), 200),
        (frozenset({"rbac_auditor"}), ("audit.read",), 200),
        (frozenset({"admin"}), (), 403),
        (frozenset({"rbac_cfo"}), ("finance.read", "finance.operate"), 403),
        (frozenset({"moderator"}), (), 403),
        (frozenset({"customer"}), (), 403),
    ],
)
def test_audit_log_access(
    monkeypatch: pytest.MonkeyPatch,
    roles: frozenset[str],
    permissions: tuple[str, ...],
    status: int,
) -> None:
    client, _ = _client(monkeypatch, roles, permissions, rows={"audit_log": [AUDIT_ROW]})
    response = client.get("/admin/audit-log")
    assert response.status_code == status, response.text
    if status == 200:
        item = response.json()["items"][0]
        assert item["before"]["customer_phone"] == MASK
        assert item["after"]["contact"]["email"] == MASK
        assert item["actor_roles"] == ["admin"] and item["request_id"] == "req-9"


def test_audit_log_rejects_bad_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client(monkeypatch, frozenset({"superadmin"}))
    assert client.get("/admin/audit-log?action=admin%25").status_code == 422
    assert client.get("/admin/audit-log?actor=not-a-uuid").status_code == 422
    assert (
        client.get("/admin/audit-log?from=2026-11-13T00:00:00Z&to=2026-11-01T00:00:00Z").status_code
        == 422
    )


# ---------------------------------------------------------------------------
# Denied attempts and audit enrichment
# ---------------------------------------------------------------------------


def test_denied_operator_attempt_is_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _client(monkeypatch, frozenset({"rbac_analyst"}), ("analytics.read",))
    assert client.post("/admin/refunds/execute", json={}).status_code == 403
    denied = [row for table, row in fake.inserts if table == "audit_log"]
    assert denied and denied[0]["outcome"] == "denied"
    assert denied[0]["after"] == {"method": "POST", "route": "/admin/refunds/execute"}
    assert denied[0]["actor_roles"] == ["rbac_analyst"]


def test_customer_probe_is_not_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _client(monkeypatch, frozenset({"customer"}))
    assert client.post("/admin/refunds/execute", json={}).status_code == 403
    assert not [row for table, row in fake.inserts if table == "audit_log"]


def test_recorder_writes_role_request_and_reason() -> None:
    fake = Recorder()
    recorder = AdminAuditRecorder(
        USER,
        fake,  # type: ignore[arg-type]
        actor_roles=frozenset({"rbac_cfo", "customer"}),
        request_id="req-1",
    )
    recorder.record(
        action="admin.orders.escrow",
        entity_type="order",
        entity_id=TARGET,
        before=None,
        after={"operation": "release"},
        reason="  customer confirmed delivery  ",
    )
    _, row = fake.inserts[0]
    assert row["actor_roles"] == ["customer", "rbac_cfo"]
    assert row["request_id"] == "req-1"
    assert row["reason"] == "customer confirmed delivery"
    assert "outcome" not in row  # the column default records 'success'


# ---------------------------------------------------------------------------
# Admin accounts (superadmin only)
# ---------------------------------------------------------------------------


def test_accounts_directory_lists_admins_with_names_and_emails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(
        monkeypatch,
        frozenset({"superadmin"}),
        rows={
            "user_roles": [
                {"user_id": TARGET, "role": "admin"},
                {"user_id": TARGET, "role": "customer"},
                {"user_id": USER, "role": "superadmin"},
                {"user_id": "00000000-0000-0000-0000-0000000000c3", "role": "customer"},
            ],
            "profiles": [{"id": TARGET, "display_name": "Chanda"}],
        },
    )
    accounts = client.get("/admin/accounts").json()["accounts"]
    assert [a["user_id"] for a in accounts] == [USER, TARGET]
    target = accounts[1]
    assert target["roles"] == ["admin"] and target["display_name"] == "Chanda"
    assert target["email"] == "b2@example.test"


def test_deactivate_calls_the_audited_function(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _client(monkeypatch, frozenset({"superadmin"}))
    response = client.post(
        f"/admin/accounts/{TARGET}/deactivate",
        json={"reason": "left the team", "confirmation": "DEACTIVATE"},
    )
    assert response.status_code == 200, response.text
    name, params = fake.rpcs[0]
    assert name == "deactivate_admin_account"
    assert params["p_actor"] == USER and params["p_target"] == TARGET
    assert params["p_reason"] == "left the team"


@pytest.mark.parametrize(
    "roles,body,status",
    [
        (frozenset({"admin"}), {"reason": "x" * 5, "confirmation": "DEACTIVATE"}, 403),
        (frozenset({"superadmin"}), {"reason": "x" * 5, "confirmation": "yes"}, 422),
        (frozenset({"superadmin"}), {"reason": "", "confirmation": "DEACTIVATE"}, 422),
    ],
)
def test_deactivate_refusals(
    monkeypatch: pytest.MonkeyPatch, roles: frozenset[str], body: dict[str, str], status: int
) -> None:
    client, fake = _client(monkeypatch, roles)
    assert client.post(f"/admin/accounts/{TARGET}/deactivate", json=body).status_code == status
    assert not fake.rpcs


def test_superadmin_cannot_deactivate_self(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _client(monkeypatch, frozenset({"superadmin"}))
    response = client.post(
        f"/admin/accounts/{USER}/deactivate",
        json={"reason": "testing", "confirmation": "DEACTIVATE"},
    )
    assert response.status_code == 422 and not fake.rpcs


def test_last_superadmin_maps_to_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _client(monkeypatch, frozenset({"superadmin"}))
    fake.rpc_error = APIError({"code": "23514", "message": "Cannot remove the last superadmin"})
    response = client.post(
        f"/admin/accounts/{TARGET}/deactivate",
        json={"reason": "rotation", "confirmation": "DEACTIVATE"},
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Support role sees masked phone numbers
# ---------------------------------------------------------------------------


def test_mask_phone_keeps_prefix_and_last_three() -> None:
    assert mask_phone("+260971234567") == "+260••••••567"
    assert mask_phone(None) is None


def test_support_role_lookup_is_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    card = {
        "customer": {
            "id": TARGET,
            "phone": "+260971234567",
            "display_name": "Mwila",
            "locale": "en",
        },
        "orders": [],
        "open_orders_count": 0,
        "latest_order_status": None,
    }
    monkeypatch.setattr(
        "app.routers.admin_support._lookup_support",
        lambda _client, _q: [ContextCardOut.model_validate(card)],
    )
    support, _ = _client(monkeypatch, frozenset({"rbac_support"}), ("support.manage",))
    masked = support.get("/admin/support/lookup?q=mwila").json()["matches"][0]
    assert masked["customer"]["phone"] == "+260••••••567"
    admin, _ = _client(monkeypatch, frozenset({"admin"}))
    full = admin.get("/admin/support/lookup?q=mwila").json()["matches"][0]
    assert full["customer"]["phone"] == "+260971234567"


# ---------------------------------------------------------------------------
# Delivery-partner consent (Zambia DPA)
# ---------------------------------------------------------------------------


def test_consent_defaults_to_not_given(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client(monkeypatch, frozenset({"customer"}))
    body = client.get("/account/consents/delivery-partner").json()
    assert body["granted"] is False and body["recorded_at"] is None


def test_consent_is_recorded_with_version_and_source(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _client(monkeypatch, frozenset({"customer"}))
    response = client.put(
        "/account/consents/delivery-partner",
        json={"granted": True, "source": "checkout", "version": "2026-11-13"},
    )
    assert response.status_code == 200, response.text
    table, row = fake.inserts[0]
    assert table == "privacy_consents"
    assert row == {
        "user_id": USER,
        "purpose": "delivery_partner_share",
        "version": "2026-11-13",
        "granted": True,
        "source": "checkout",
    }
    assert response.json()["granted"] is True


def test_consent_rejects_an_unknown_notice_version(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _client(monkeypatch, frozenset({"customer"}))
    response = client.put(
        "/account/consents/delivery-partner",
        json={"granted": True, "source": "settings", "version": "2020-01-01"},
    )
    assert response.status_code == 422 and not fake.inserts


def test_courier_dispatch_requires_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    order = {
        "order_id": TARGET,
        "status": "confirmed",
        "fulfilment": "delivery",
        "cod": True,
        "paid": False,
        "delivery_consent": False,
        "cod_amount_ngwee": 0,
    }
    monkeypatch.setattr(dispatch_service, "load_order_dispatch_context", lambda _id: order)
    monkeypatch.setattr(dispatch_service, "DISPATCHABLE_ORDER_STATUSES", frozenset({"confirmed"}))
    courier_loaded = MagicMock()
    monkeypatch.setattr(dispatch_service, "load_courier", courier_loaded)
    with pytest.raises(AppError) as refused:
        dispatch_service.create_dispatch(order_id=TARGET, courier_partner_id=USER, actor_id=USER)
    assert refused.value.code == "delivery_consent_required"
    assert refused.value.http_status == 409
    courier_loaded.assert_not_called()  # refused before any courier detail is read


def test_courier_message_is_withheld_after_withdrawal(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatch = SimpleNamespace(
        order_id=TARGET, courier_partner_id=USER, cod_amount_ngwee=0, courier_reference=None
    )
    monkeypatch.setattr(dispatch_service, "fetch_dispatch", lambda _id: dispatch)
    monkeypatch.setattr(dispatch_service, "load_courier", lambda _id: {"name": "Courier"})
    monkeypatch.setattr(
        dispatch_service,
        "load_order_dispatch_context",
        lambda _id: {"delivery_consent": False, "customer_phone": "+260971234567"},
    )
    with pytest.raises(AppError) as refused:
        dispatch_service.build_dispatch_message("d1")
    assert refused.value.code == "delivery_consent_required"
