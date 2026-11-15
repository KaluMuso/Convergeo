from __future__ import annotations

from typing import Any

import pytest
from app.errors import AppError
from app.routers.admin_business import _enqueue_business_notification
from app.services.business.access import (
    resolve_business_eligibility,
)
from app.services.business.store import upsert_application

USER = "11111111-1111-1111-1111-111111111111"


# --- Minimal PostgREST-ish fake with a shared, mutable store ----------------
class _Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: dict[str, list[dict[str, Any]]], table: str) -> None:
        self._store = store
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._single = False
        self._mode = "select"
        self._payload: Any = None
        self._select = "*"

    def select(self, columns: str = "*", **_k: Any) -> _Query:
        self._select = columns
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[str]) -> _Query:
        self._filters.append(("in", column, list(values)))
        return self

    def order(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def limit(self, n: int) -> _Query:
        self._limit = n
        return self

    def maybe_single(self) -> _Query:
        self._single = True
        return self

    def insert(self, row: Any) -> _Query:
        self._mode = "insert"
        self._payload = row
        return self

    def update(self, row: Any) -> _Query:
        self._mode = "update"
        self._payload = row
        return self

    def _apply(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        plain_filters = [item for item in self._filters if "." not in item[1]]
        dotted_filters = [item for item in self._filters if "." in item[1]]

        out = rows
        for op, col, val in plain_filters:
            if op == "eq":
                out = [r for r in out if r.get(col) == val]
            elif op == "in":
                allowed = set(val)
                out = [r for r in out if r.get(col) in allowed]

        if self._table == "vendor_listings" and "vendors!" in self._select:
            out = [_enrich_listing_row(row, self._store) for row in out]

        for _op, col, val in dotted_filters:
            parent, child = col.split(".", 1)
            filtered: list[dict[str, Any]] = []
            for row in out:
                nested = row.get(parent)
                if isinstance(nested, list):
                    nested = nested[0] if nested else None
                if isinstance(nested, dict) and nested.get(child) == val:
                    filtered.append(row)
            out = filtered
        return out

    def execute(self) -> _Result:
        table_rows = self._store.setdefault(self._table, [])
        if self._mode == "insert":
            rows = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = [dict(r) for r in rows]
            table_rows.extend(inserted)
            return _Result([dict(r) for r in inserted])
        if self._mode == "update":
            matched = self._apply(table_rows)
            for row in matched:
                row.update(self._payload)
            return _Result([dict(r) for r in matched])
        rows = self._apply(list(table_rows))
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._single:
            return _Result(dict(rows[0]) if rows else None)
        return _Result([dict(r) for r in rows])


class FakeClient:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self._store = store

    def table(self, name: str) -> _Query:
        return _Query(self._store, name)


class FakeService:
    def __init__(self, client: FakeClient) -> None:
        self.client = client


def _service(store: dict[str, list[dict[str, Any]]]) -> FakeService:
    return FakeService(FakeClient(store))


def _enrich_listing_row(
    listing: dict[str, Any],
    store: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    vendor_id = listing.get("vendor_id")
    product_id = listing.get("product_id")
    listing_id = listing.get("id")
    vendors = [
        row
        for row in store.get("vendors", [])
        if row.get("id") == vendor_id and row.get("status") == "active"
    ]
    vendor = vendors[0] if vendors else None
    products = [
        row
        for row in store.get("products", [])
        if row.get("id") == product_id and row.get("status") == "active"
    ]
    images = [
        row for row in store.get("listing_images", []) if row.get("listing_id") == listing_id
    ]
    return {
        **listing,
        "vendors": vendor,
        "products": products[0] if products else None,
        "listing_images": images,
    }


# --- Resolver ---------------------------------------------------------------
class TestResolver:
    def test_verified_is_eligible(self) -> None:
        svc = _service({"business_buyers": [{"user_id": USER, "status": "verified"}]})
        access = resolve_business_eligibility(USER, svc)
        assert access.eligible is True
        assert access.status == "verified"

    def test_pending_is_not_eligible(self) -> None:
        svc = _service({"business_buyers": [{"user_id": USER, "status": "pending"}]})
        access = resolve_business_eligibility(USER, svc)
        assert access.eligible is False
        assert access.status == "pending"

    def test_no_application_is_not_eligible(self) -> None:
        access = resolve_business_eligibility(USER, _service({"business_buyers": []}))
        assert access.eligible is False
        assert access.status is None

    def test_suspended_is_not_eligible(self) -> None:
        """R02-P06: suspension must revoke wholesale immediately.

        `suspended` is a valid business_buyers status (0038) but nothing
        asserted it here — only `pending` and "no application" were covered, so
        an eligibility rule written as `status != 'rejected'` would have passed
        the suite while handing tier pricing to a suspended buyer.
        """
        svc = _service({"business_buyers": [{"user_id": USER, "status": "suspended"}]})
        access = resolve_business_eligibility(USER, svc)
        assert access.eligible is False
        assert access.status == "suspended"

    def test_rejected_is_not_eligible(self) -> None:
        svc = _service({"business_buyers": [{"user_id": USER, "status": "rejected"}]})
        access = resolve_business_eligibility(USER, svc)
        assert access.eligible is False
        assert access.status == "rejected"

    def test_only_verified_of_all_valid_statuses_is_eligible(self) -> None:
        """Pins the rule to an allowlist. If a status is ever added to 0038's
        CHECK constraint, this fails until someone decides deliberately whether
        it grants wholesale — the safe default being that it does not."""
        from app.services.business.access import VALID_STATUSES

        eligible = {
            status
            for status in VALID_STATUSES
            if resolve_business_eligibility(
                USER, _service({"business_buyers": [{"user_id": USER, "status": status}]})
            ).eligible
        }
        assert eligible == {"verified"}


# --- Application lifecycle --------------------------------------------------
class TestUpsertApplication:
    def test_new_application_is_pending(self) -> None:
        store: dict[str, list[dict[str, Any]]] = {"business_buyers": []}
        row = upsert_application(
            _service(store),
            user_id=USER,
            legal_name="Acme Ltd",
            registration_no="PACRA-123",
            tpin=None,
        )
        assert row["status"] == "pending"
        assert store["business_buyers"][0]["user_id"] == USER

    def test_rejected_can_reapply(self) -> None:
        store = {
            "business_buyers": [
                {"user_id": USER, "status": "rejected", "legal_name": "Old"}
            ]
        }
        row = upsert_application(
            _service(store),
            user_id=USER,
            legal_name="Acme Ltd",
            registration_no="PACRA-123",
            tpin="1000000000",
        )
        assert row["status"] == "pending"
        assert row["legal_name"] == "Acme Ltd"

    def test_verified_cannot_resubmit(self) -> None:
        store = {"business_buyers": [{"user_id": USER, "status": "verified"}]}
        with pytest.raises(AppError) as exc:
            upsert_application(
                _service(store),
                user_id=USER,
                legal_name="Acme Ltd",
                registration_no="PACRA-123",
                tpin=None,
            )
        assert exc.value.code == "business.already_decided"
        assert exc.value.http_status == 409


class TestAdminBusinessNotification:
    def test_verify_enqueues_email_to_buyer(self) -> None:
        store: dict[str, list[dict[str, Any]]] = {"notification_outbox": []}
        buyer = {"id": "b1", "user_id": USER, "legal_name": "Acme Ltd"}
        enqueued = _enqueue_business_notification(
            _service(store), buyer=buyer, template="business_verified"
        )
        assert enqueued is True
        rows = store["notification_outbox"]
        assert len(rows) == 1
        assert rows[0]["template"] == "business_verified"
        assert rows[0]["channel"] == "email"
        assert rows[0]["payload"]["recipient_id"] == USER

    def test_reject_includes_reason(self) -> None:
        store: dict[str, list[dict[str, Any]]] = {"notification_outbox": []}
        buyer = {"id": "b1", "user_id": USER, "legal_name": "Acme"}
        _enqueue_business_notification(
            _service(store), buyer=buyer, template="business_rejected", reason="Invalid PACRA no."
        )
        assert store["notification_outbox"][0]["payload"]["reason"] == "Invalid PACRA no."

    def test_missing_user_id_skips(self) -> None:
        store: dict[str, list[dict[str, Any]]] = {"notification_outbox": []}
        enqueued = _enqueue_business_notification(
            _service(store), buyer={"id": "b1", "user_id": ""}, template="business_verified"
        )
        assert enqueued is False
        assert store["notification_outbox"] == []


class TestNoCustomerWholesaleSurface:
    """Wholesale prices are vendor-app only: the customer gate and feed are gone."""

    def test_wholesale_feed_and_gate_removed(self) -> None:
        import app.routers.catalog as catalog
        import app.services.business.access as access

        assert not hasattr(catalog, "list_wholesale_supplies")
        assert not hasattr(access, "require_wholesale_access")
