from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from fastapi.testclient import TestClient

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
LISTING_A1 = "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1"
LISTING_A2 = "a2a2a2a2-a2a2-a2a2-a2a2-a2a2a2a2a2a2"
LISTING_B1 = "b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1"
TOKEN = "ExponentPushToken[abcdefghijklmnop1234]"
H = {"Authorization": "Bearer t"}


class Q:
    def __init__(self, table: T) -> None:
        self.t = table
        self.f: list[tuple[str, str, Any]] = []
        self.op: str | None = None
        self.payload: Any = None
        self.conflict: str | None = None
        self.single = False
        self.ord: tuple[str, bool] | None = None

    def select(self, _c: str, **_k: Any) -> Q:
        return self

    def eq(self, c: str, v: Any) -> Q:
        self.f.append(("eq", c, v))
        return self

    def is_(self, c: str, v: str) -> Q:
        self.f.append(("is", c, None if v == "null" else v))
        return self

    def order(self, c: str, *, desc: bool = False) -> Q:
        self.ord = (c, desc)
        return self

    def maybe_single(self) -> Q:
        self.single = True
        return self

    def update(self, p: dict[str, Any]) -> Q:
        self.op, self.payload = "update", p
        return self

    def upsert(self, p: dict[str, Any], on_conflict: str) -> Q:
        self.op, self.payload, self.conflict = "upsert", p, on_conflict
        return self

    def _match(self, r: dict[str, Any]) -> bool:
        return all(r.get(c) == v for _o, c, v in self.f)

    def execute(self) -> MagicMock:
        if self.op == "upsert":
            assert self.conflict is not None
            for r in self.t.rows:
                if r.get(self.conflict) == self.payload[self.conflict]:
                    r.update(self.payload)
                    return MagicMock(data=[dict(r)])
            row = {"id": str(uuid4()), **self.payload}
            self.t.rows.append(row)
            return MagicMock(data=[dict(row)])
        if self.op == "update":
            out = []
            for r in self.t.rows:
                if self._match(r):
                    r.update(self.payload)
                    out.append(dict(r))
            return MagicMock(data=out)
        rows = [dict(r) for r in self.t.rows if self._match(r)]
        if self.ord:
            rows.sort(key=lambda r: r.get(self.ord[0]) or "", reverse=self.ord[1])  # type: ignore[index]
        if self.single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class T:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(Q(self), name)


class FakeClient:
    def __init__(self) -> None:
        self.tables = {n: T() for n in ("vendors", "device_tokens", "vendor_listings")}

    def table(self, name: str) -> T:
        return self.tables[name]


def _listing(lid: str, vendor: str, barcode: str | None, title: str = "Phone") -> dict[str, Any]:
    return {
        "id": lid,
        "vendor_id": vendor,
        "title_override": title,
        "price_ngwee": 150_000,
        "status": "active",
        "stock_mode": "tracked",
        "stock_qty": 4,
        "barcode": barcode,
        "products": None,
    }


@pytest.fixture
def fake() -> FakeClient:
    f = FakeClient()
    f.tables["vendors"].rows += [
        {"id": VENDOR_A, "owner_user_id": USER_A, "status": "active"},
        {"id": VENDOR_B, "owner_user_id": USER_B, "status": "active"},
    ]
    f.tables["vendor_listings"].rows += [
        _listing(LISTING_A1, VENDOR_A, "6001234567890"),
        _listing(LISTING_A2, VENDOR_A, None, "Laptop"),
        _listing(LISTING_B1, VENDOR_B, "6009999999999", "Other shop phone"),
    ]
    return f


def _client(
    monkeypatch: pytest.MonkeyPatch, fake: FakeClient, user: str, roles: frozenset[str]
) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user, "exp": 9_999_999_999},
    )
    monkeypatch.setattr("app.core.auth._load_user_roles", lambda uid, sc: roles)
    wrapper = MagicMock()
    wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: wrapper)
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: wrapper
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def vendor_a(
    monkeypatch: pytest.MonkeyPatch, fake: FakeClient
) -> Generator[TestClient, None, None]:
    yield from _client(monkeypatch, fake, USER_A, frozenset({"vendor"}))


@pytest.fixture
def customer(
    monkeypatch: pytest.MonkeyPatch, fake: FakeClient
) -> Generator[TestClient, None, None]:
    yield from _client(monkeypatch, fake, USER_A, frozenset({"customer"}))


# ---- devices ----
def test_register_device_creates_row_and_hides_token(
    vendor_a: TestClient, fake: FakeClient
) -> None:
    r = vendor_a.post(
        "/vendor/devices",
        headers=H,
        json={"token": TOKEN, "platform": "android", "app_version": "0.1.0"},
    )
    assert r.status_code == 200
    assert set(r.json()) == {"id", "platform"}
    row = fake.tables["device_tokens"].rows[0]
    assert row["user_id"] == USER_A and row["vendor_id"] == VENDOR_A and row["token"] == TOKEN


def test_register_is_idempotent_and_clears_revocation(
    vendor_a: TestClient, fake: FakeClient
) -> None:
    first = vendor_a.post(
        "/vendor/devices", headers=H, json={"token": TOKEN, "platform": "android"}
    ).json()
    vendor_a.delete(f"/vendor/devices/{first['id']}", headers=H)
    assert fake.tables["device_tokens"].rows[0]["revoked_at"] is not None
    second = vendor_a.post(
        "/vendor/devices", headers=H, json={"token": TOKEN, "platform": "android"}
    ).json()
    assert second["id"] == first["id"]
    assert len(fake.tables["device_tokens"].rows) == 1
    assert fake.tables["device_tokens"].rows[0]["revoked_at"] is None


@pytest.mark.parametrize(
    "token",
    [
        "not-a-token-at-all-just-text",
        "ExponentPushToken[short]",
        "ExponentPushToken[bad chars here!!!]",
    ],
)
def test_register_rejects_bad_token(vendor_a: TestClient, token: str) -> None:
    r = vendor_a.post("/vendor/devices", headers=H, json={"token": token, "platform": "android"})
    assert r.status_code in (400, 422)


def test_register_rejects_unknown_platform_and_extra_fields(vendor_a: TestClient) -> None:
    assert vendor_a.post(
        "/vendor/devices", headers=H, json={"token": TOKEN, "platform": "web"}
    ).status_code in (400, 422)
    assert vendor_a.post(
        "/vendor/devices",
        headers=H,
        json={"token": TOKEN, "platform": "ios", "vendor_id": VENDOR_B},
    ).status_code in (400, 422)


def test_non_vendor_cannot_register(customer: TestClient, fake: FakeClient) -> None:
    r = customer.post("/vendor/devices", headers=H, json={"token": TOKEN, "platform": "android"})
    assert r.status_code == 403
    assert fake.tables["device_tokens"].rows == []


def test_oldest_devices_revoked_beyond_cap(vendor_a: TestClient, fake: FakeClient) -> None:
    for i in range(11):
        fake.tables["device_tokens"].rows.append(
            {
                "id": str(uuid4()),
                "user_id": USER_A,
                "vendor_id": VENDOR_A,
                "token": f"ExponentPushToken[old{i:04d}abcdefghij]",
                "last_seen_at": f"2026-11-01T10:{i:02d}:00+00:00",
                "revoked_at": None,
            }
        )
    assert (
        vendor_a.post(
            "/vendor/devices", headers=H, json={"token": TOKEN, "platform": "android"}
        ).status_code
        == 200
    )
    rows = fake.tables["device_tokens"].rows
    active = [r for r in rows if r["revoked_at"] is None]
    assert len(active) == 10
    assert any(r["token"] == TOKEN for r in active)
    revoked_tokens = {r["token"] for r in rows if r["revoked_at"] is not None}
    assert revoked_tokens == {
        "ExponentPushToken[old0000abcdefghij]",
        "ExponentPushToken[old0001abcdefghij]",
    }


def test_revoke_only_own_device(vendor_a: TestClient, fake: FakeClient) -> None:
    fake.tables["device_tokens"].rows.append(
        {
            "id": "c0c0c0c0-c0c0-c0c0-c0c0-c0c0c0c0c0c0",
            "user_id": USER_B,
            "vendor_id": VENDOR_B,
            "token": TOKEN,
            "revoked_at": None,
        }
    )
    r = vendor_a.delete("/vendor/devices/c0c0c0c0-c0c0-c0c0-c0c0-c0c0c0c0c0c0", headers=H)
    assert r.status_code == 404
    assert fake.tables["device_tokens"].rows[0]["revoked_at"] is None


def test_revoke_bad_id_is_404(vendor_a: TestClient) -> None:
    assert vendor_a.delete("/vendor/devices/not-a-uuid", headers=H).status_code == 404


# ---- barcode ----
def test_lookup_finds_own_listing(vendor_a: TestClient) -> None:
    r = vendor_a.get("/vendor/listings/by-barcode/6001234567890", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert (
        body["listing_id"] == LISTING_A1
        and body["price_ngwee"] == 150_000
        and body["title"] == "Phone"
    )


def test_lookup_never_leaks_other_vendors_barcode(vendor_a: TestClient) -> None:
    assert vendor_a.get("/vendor/listings/by-barcode/6009999999999", headers=H).status_code == 404


def test_lookup_unknown_and_malformed_are_404(vendor_a: TestClient) -> None:
    assert vendor_a.get("/vendor/listings/by-barcode/0000000000000", headers=H).status_code == 404
    assert vendor_a.get("/vendor/listings/by-barcode/a%20b", headers=H).status_code == 404


def test_lookup_requires_vendor(customer: TestClient) -> None:
    assert customer.get("/vendor/listings/by-barcode/6001234567890", headers=H).status_code == 403


def test_set_barcode_on_own_listing(vendor_a: TestClient, fake: FakeClient) -> None:
    r = vendor_a.put(
        f"/vendor/listings/{LISTING_A2}/barcode", headers=H, json={"barcode": " 5012345678900 "}
    )
    assert r.status_code == 200 and r.json()["barcode"] == "5012345678900"
    assert [x for x in fake.tables["vendor_listings"].rows if x["id"] == LISTING_A2][0][
        "barcode"
    ] == "5012345678900"


def test_set_barcode_rejects_duplicate_on_same_vendor(vendor_a: TestClient) -> None:
    r = vendor_a.put(
        f"/vendor/listings/{LISTING_A2}/barcode", headers=H, json={"barcode": "6001234567890"}
    )
    assert r.status_code == 409


def test_same_barcode_on_same_listing_is_ok_and_other_vendor_may_reuse(
    vendor_a: TestClient,
) -> None:
    assert (
        vendor_a.put(
            f"/vendor/listings/{LISTING_A1}/barcode", headers=H, json={"barcode": "6001234567890"}
        ).status_code
        == 200
    )
    assert (
        vendor_a.put(
            f"/vendor/listings/{LISTING_A2}/barcode", headers=H, json={"barcode": "6009999999999"}
        ).status_code
        == 200
    )


def test_clear_barcode(vendor_a: TestClient) -> None:
    r = vendor_a.put(f"/vendor/listings/{LISTING_A1}/barcode", headers=H, json={"barcode": None})
    assert r.status_code == 200 and r.json()["barcode"] is None


def test_cannot_set_barcode_on_foreign_listing(vendor_a: TestClient, fake: FakeClient) -> None:
    r = vendor_a.put(
        f"/vendor/listings/{LISTING_B1}/barcode", headers=H, json={"barcode": "1111222233334"}
    )
    assert r.status_code == 404
    assert [x for x in fake.tables["vendor_listings"].rows if x["id"] == LISTING_B1][0][
        "barcode"
    ] == "6009999999999"


@pytest.mark.parametrize("bad", ["abc", "has space 123", "x" * 65, "12;DROP", ""])
def test_set_barcode_rejects_bad_values(vendor_a: TestClient, bad: str) -> None:
    assert vendor_a.put(
        f"/vendor/listings/{LISTING_A2}/barcode", headers=H, json={"barcode": bad}
    ).status_code in (400, 422)


def test_set_barcode_requires_vendor(customer: TestClient) -> None:
    assert (
        customer.put(
            f"/vendor/listings/{LISTING_A2}/barcode", headers=H, json={"barcode": "1111222233334"}
        ).status_code
        == 403
    )
