"""GET /checkout/groups/{id}: owner-scoped ticket / service-deposit checkout summary."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

OWNER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
GROUP = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ORDER = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
ITEM = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
VENDOR = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
JOB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
QUOTE = "ffffffff-ffff-4fff-8fff-ffffffffffff"
EVENT = "99999999-9999-4999-8999-999999999999"
INSTANCE = "88888888-8888-4888-8888-888888888888"
TTYPE = "77777777-7777-4777-8777-777777777777"


class FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, list(values)))
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def execute(self) -> MagicMock:
        out = []
        for row in self._rows:
            ok = True
            for op, column, value in self._filters:
                cell = row.get(column)
                if (op == "eq" and cell != value) or (op == "in" and cell not in value):
                    ok = False
            if ok:
                out.append(dict(row))
        if self._limit is not None:
            out = out[: self._limit]
        return MagicMock(data=out)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.tables.setdefault(name, []))


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    wrapper = MagicMock()
    wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.checkout_group.bump_rate_counter", lambda **_kwargs: (True, 0))
    monkeypatch.setattr("app.routers.checkout_group.payments_enabled", lambda: True)
    monkeypatch.setattr(
        "app.core.auth._load_user_roles", lambda uid, service_client: frozenset({"customer"})
    )
    return client


@pytest.fixture
def api() -> Generator[TestClient, None, None]:
    with TestClient(create_app()) as client:
        yield client


def _as(monkeypatch: pytest.MonkeyPatch, user_id: str) -> dict[str, str]:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    return {"Authorization": "Bearer t"}


def _seed_spine(fake: FakeClient, *, kind: str, status: str = "pending", fee: int = 0) -> None:
    unit = 15_000 if kind == "ticket" else 120_000
    qty = 2 if kind == "ticket" else 1
    fake.tables["checkout_groups"] = [
        {
            "id": GROUP,
            "customer_id": OWNER,
            "status": status,
            "subtotal_ngwee": unit * qty,
            "delivery_fee_ngwee": 0,
            "platform_fee_ngwee": fee,
            "total_ngwee": unit * qty + fee,
        }
    ]
    fake.tables["orders"] = [
        {
            "id": ORDER,
            "checkout_group_id": GROUP,
            "customer_id": OWNER,
            "vendor_id": VENDOR,
            "cod": False,
        }
    ]
    fake.tables["order_items"] = [
        {
            "id": ITEM,
            "order_id": ORDER,
            "item_kind": kind,
            "qty": qty,
            "unit_price_ngwee": unit,
            "title_snapshot": "Jazz Night — VIP" if kind == "ticket" else None,
        }
    ]
    if kind == "ticket":
        fake.tables["order_item_tickets"] = [
            {"order_item_id": ITEM, "ticket_type_id": TTYPE, "instance_id": INSTANCE}
        ]
        fake.tables["ticket_types"] = [{"id": TTYPE, "name": "VIP", "event_id": EVENT}]
        fake.tables["event_instances"] = [
            {"id": INSTANCE, "event_id": EVENT, "starts_at": "2026-12-01T18:00:00+00:00"}
        ]
        fake.tables["events"] = [
            {"id": EVENT, "title": "Jazz Night", "slug": "jazz-night", "venue": "Lusaka"}
        ]
    else:
        fake.tables["order_item_services"] = [
            {"order_item_id": ITEM, "job_id": JOB, "quote_id": QUOTE}
        ]
        fake.tables["jobs"] = [{"id": JOB, "category": "plumbing"}]
        fake.tables["vendors"] = [{"id": VENDOR, "display_name": "Mwila Plumbing"}]


def test_ticket_group_summary_includes_tier_and_buyer_fee(
    fake: FakeClient, api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_spine(fake, kind="ticket", fee=1_500)
    res = api.get(f"/checkout/groups/{GROUP}", headers=_as(monkeypatch, OWNER))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "ticket"
    assert body["payable"] is True and body["expired"] is False
    assert body["order_id"] == ORDER
    assert body["subtotal_ngwee"] == 30_000
    assert body["platform_fee_ngwee"] == 1_500
    assert body["total_ngwee"] == 31_500
    assert body["event"]["title"] == "Jazz Night"
    assert body["event"]["starts_at"].startswith("2026-12-01")
    assert body["lines"][0]["ticket_type_name"] == "VIP"
    assert body["lines"][0]["qty"] == 2
    assert body["lines"][0]["line_total_ngwee"] == 30_000
    assert body["available_methods"] == ["momo", "card"]
    assert body["service"] is None


def test_service_deposit_summary_uses_group_total_verbatim(
    fake: FakeClient, api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_spine(fake, kind="service_deposit")
    res = api.get(f"/checkout/groups/{GROUP}", headers=_as(monkeypatch, OWNER))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "service_deposit"
    assert body["total_ngwee"] == 120_000
    assert body["service"] == {
        "job_id": JOB,
        "quote_id": QUOTE,
        "vendor_id": VENDOR,
        "vendor_name": "Mwila Plumbing",
        "category": "plumbing",
    }
    assert body["event"] is None


def test_non_owner_gets_403(
    fake: FakeClient, api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_spine(fake, kind="ticket")
    res = api.get(f"/checkout/groups/{GROUP}", headers=_as(monkeypatch, OTHER))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forbidden"
    assert "total_ngwee" not in res.text


def test_order_owned_by_someone_else_is_403(
    fake: FakeClient, api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_spine(fake, kind="ticket")
    fake.tables["orders"][0]["customer_id"] = OTHER
    res = api.get(f"/checkout/groups/{GROUP}", headers=_as(monkeypatch, OWNER))
    assert res.status_code == 403


def test_unauthenticated_is_rejected(fake: FakeClient, api: TestClient) -> None:
    _seed_spine(fake, kind="ticket")
    res = api.get(f"/checkout/groups/{GROUP}")
    assert res.status_code == 401


def test_missing_group_is_404_and_bad_id_is_422(
    fake: FakeClient, api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _as(monkeypatch, OWNER)
    assert api.get(f"/checkout/groups/{GROUP}", headers=headers).status_code == 404
    assert api.get("/checkout/groups/not-a-uuid", headers=headers).status_code == 422


def test_expired_group_is_flagged_not_payable(
    fake: FakeClient, api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_spine(fake, kind="ticket", status="expired")
    body = api.get(f"/checkout/groups/{GROUP}", headers=_as(monkeypatch, OWNER)).json()
    assert body["expired"] is True
    assert body["payable"] is False


def test_payments_disabled_offers_no_online_methods(
    fake: FakeClient, api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_spine(fake, kind="service_deposit")
    monkeypatch.setattr("app.routers.checkout_group.payments_enabled", lambda: False)
    body = api.get(f"/checkout/groups/{GROUP}", headers=_as(monkeypatch, OWNER)).json()
    assert body["available_methods"] == []


def test_rate_limited_returns_429(
    fake: FakeClient, api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_spine(fake, kind="ticket")
    monkeypatch.setattr(
        "app.routers.checkout_group.bump_rate_counter", lambda **_kwargs: (False, 30)
    )
    res = api.get(f"/checkout/groups/{GROUP}", headers=_as(monkeypatch, OWNER))
    assert res.status_code == 429
