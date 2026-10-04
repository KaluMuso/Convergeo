from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import psycopg
import pytest
from scripts import ci_perf_fixture as fixture

ENV = {
    "CI": "true",
    "GITHUB_ACTIONS": "true",
    "CI_PERF_HARNESS": "1",
    "NEXT_PUBLIC_CI_PERF_HARNESS": "1",
    "NEXT_PUBLIC_DEPLOYMENT_PLANE": "preview",
    "NEXT_PUBLIC_SITE_URL": "http://localhost:3000",
    "ENV": "development",
    "SUPABASE_URL": "http://127.0.0.1:54321",
    "SUPABASE_DB_URL": fixture.LOCAL_DSN,
    "NEXT_PUBLIC_API_BASE_URL": "http://10.1.2.3:8000",
    "CI_PERF_UPSTREAM_ORIGIN": "http://10.1.2.3:8000",
}


class FixtureConnection:
    def __init__(self) -> None:
        root = Path(__file__).parent / "fixtures" / "demo"
        ids = json.loads((root / "ids.json").read_text())
        entities = json.loads((root / "entities.json").read_text())
        self.category = [(fixture.CATEGORY, "Electronics", "electronics", "electronics", False)]
        self.vendors = [
            (
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "33333333-3333-3333-3333-333333333333",
                "lusaka-electronics",
                "Lusaka Electronics Hub",
                "active",
            ),
            (
                "d0000000-0000-0000-0000-000000000001",
                "66666666-6666-6666-6666-666666666666",
                "demo-sandbox",
                "Demo Sandbox Shop",
                "active",
            ),
        ]
        self.product = [
            (fixture.PRODUCT, "smartphone-x1", fixture.CATEGORY, "Smartphone X1", "active")
        ]
        self.listings = [
            (
                ids["listings"][row["id_key"]],
                ids["vendors"][row["vendor_key"]],
                fixture.PRODUCT,
                row["title_override"],
                row["price_ngwee"],
                row["stock_mode"],
                row["stock_qty"],
                row["status"],
                False,
                row["condition"],
            )
            for row in entities["listings"]
            if row["product_key"] == "phone"
        ]
        self.images = [(fixture.PHONE_IMAGE, fixture.PHONE, "vergeo5/demo/phone-a", 1)]
        self.statements: list[str] = []
        self.committed = False
        self.rolled_back = False
        self.fail_insert = False
        self.saved_images = copy.deepcopy(self.images)

    def __enter__(self) -> FixtureConnection:
        self.saved_images = copy.deepcopy(self.images)
        return self

    def __exit__(self, kind: Any, _value: Any, _trace: Any) -> None:
        if kind:
            self.images = self.saved_images
            self.rolled_back = True
        else:
            self.committed = True

    def execute(self, sql: str, params: tuple[Any, ...]) -> Mock:
        self.statements.append(sql)
        if "FROM public.categories" in sql:
            return Mock(fetchall=lambda: self.category)
        if "FROM public.vendors" in sql:
            return Mock(fetchall=lambda: self.vendors)
        if "FROM public.products" in sql:
            return Mock(fetchall=lambda: self.product)
        if "FROM public.vendor_listings" in sql:
            return Mock(fetchall=lambda: self.listings)
        if "FROM public.listing_images" in sql:
            return Mock(fetchall=lambda: self.images)
        if sql.startswith("UPDATE"):
            self.images = [(fixture.PHONE_IMAGE, fixture.PHONE, params[0], 1)]
            return Mock(fetchall=lambda: [(fixture.PHONE_IMAGE,)])
        if sql.startswith("INSERT"):
            if self.fail_insert:
                raise ValueError("constraint failure")
            self.images.append((params[0], params[1], params[2], 1))
            return Mock()
        raise AssertionError("Unexpected fixture SQL")


def test_exact_guard_and_two_media_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FixtureConnection()
    connect = Mock(return_value=connection)
    monkeypatch.setattr(psycopg, "connect", connect)
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    fixture.main()
    connect.assert_called_once_with(fixture.LOCAL_DSN)
    assert connection.committed and not connection.rolled_back
    assert connection.images == [
        (fixture.PHONE_IMAGE, fixture.PHONE, fixture.MEDIA, 1),
        (fixture.GADGET_IMAGE, fixture.GADGET, "demo/ci-perf-hidden-gadget", 1),
    ]
    assert all("FOR UPDATE" in query for query in connection.statements[:5])
    assert (
        len([query for query in connection.statements if query.startswith(("UPDATE", "INSERT"))])
        == 2
    )


@pytest.mark.parametrize("key", list(ENV))
def test_missing_context_rejected_before_connection(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = dict(ENV)
    del env[key]
    connect = Mock()
    monkeypatch.setattr(psycopg, "connect", connect)
    with pytest.raises(ValueError):
        fixture.require_isolated_harness(env)
    connect.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [
        {"SUPABASE_DB_URL": "postgresql://postgres:postgres@shared.test:54322/postgres"},
        {"SUPABASE_DB_URL": fixture.LOCAL_DSN + "?host=shared.test"},
        {"SUPABASE_URL": "https://shared.supabase.co"},
        {"VERCEL": "1"},
        {"VERCEL_ENV": "preview"},
        {"NEXT_PUBLIC_DEPLOYMENT_PLANE": "production"},
        {"NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:8000"},
        {"NEXT_PUBLIC_API_BASE_URL": "http://10.1.2.3:8000/path"},
        {"CI_PERF_UPSTREAM_ORIGIN": "http://10.1.2.4:8000"},
    ],
)
def test_remote_and_divergent_context_rejected(overrides: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        fixture.require_isolated_harness({**ENV, **overrides})


@pytest.mark.parametrize(
    "change",
    [
        "category",
        "vendor",
        "product",
        "listing_price",
        "extra_listing",
        "phone_image",
        "extra_image",
        "existing_gadget_image",
    ],
)
def test_preimage_mismatch_cannot_write(change: str) -> None:
    connection = FixtureConnection()
    if change == "category":
        connection.category = []
    elif change == "vendor":
        connection.vendors = []
    elif change == "product":
        connection.product = []
    elif change == "listing_price":
        row = list(connection.listings[0])
        row[4] = 449999
        connection.listings[0] = tuple(row)
    elif change == "extra_listing":
        connection.listings.append(connection.listings[0])
    elif change == "phone_image":
        connection.images = [(fixture.PHONE_IMAGE, fixture.PHONE, "unexpected/image", 1)]
    elif change == "extra_image":
        connection.images.append(("extra", fixture.PHONE, "extra/image", 2))
    else:
        connection.images.append((fixture.GADGET_IMAGE, fixture.GADGET, "existing/image", 1))
    with pytest.raises(ValueError), connection:
        fixture.expand_fixture(connection)
    assert connection.rolled_back
    assert not any(query.startswith(("UPDATE", "INSERT")) for query in connection.statements)


def test_failed_second_operation_rolls_back_first() -> None:
    connection = FixtureConnection()
    connection.fail_insert = True
    before = copy.deepcopy(connection.images)
    with pytest.raises(ValueError), connection:
        fixture.expand_fixture(connection)
    assert connection.rolled_back and connection.images == before and not connection.committed
