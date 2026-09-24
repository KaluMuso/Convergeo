from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.services.cart.merge import MergedCartItem
from fastapi import Response

USER_ID = "11111111-1111-1111-1111-111111111111"
USER_CART_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
GUEST_CART_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER_LISTING_ID = "10101010-1010-1010-1010-101010101010"
GUEST_LISTING_ID = "20202020-2020-2020-2020-202020202020"
CONCURRENT_LISTING_ID = "30303030-3030-3030-3030-303030303030"


def _line(listing_id: str) -> dict[str, Any]:
    return {
        "id": f"line-{listing_id}",
        "listing_id": listing_id,
        "qty": 1,
        "unit_price_ngwee": 10_000,
        "wholesale": False,
    }


class _LegacyRaceStore:
    """Deterministically exposes the old delete/insert interleaving.

    Request A deletes U and pauses. Request B reads the now-empty account cart
    plus G and reaches its delete. A then inserts U+G; B deletes that result and
    inserts its stale G-only proposal. No sleeps are involved.
    """

    def __init__(self) -> None:
        self.account_items = [_line(USER_LISTING_ID)]
        self.guest_items = [_line(GUEST_LISTING_ID)]
        self.guest_status = "active"
        self._lock = threading.Lock()
        self._atomic_lock = threading.Lock()
        self.a_deleted = threading.Event()
        self.b_ready_to_delete = threading.Event()
        self.a_inserted = threading.Event()
        self.rpc_calls = 0
        self.return_stale_once = False

    def read(self, cart_id: str) -> list[dict[str, Any]]:
        if cart_id == GUEST_CART_ID:
            return [dict(item) for item in self.guest_items]
        with self._lock:
            return [dict(item) for item in self.account_items]

    def delete_account_items(self) -> None:
        request_name = threading.current_thread().name
        if request_name == "merge-a":
            with self._lock:
                self.account_items = []
            self.a_deleted.set()
            assert self.b_ready_to_delete.wait(timeout=5)
            return

        assert self.a_deleted.wait(timeout=5)
        self.b_ready_to_delete.set()
        assert self.a_inserted.wait(timeout=5)
        with self._lock:
            self.account_items = []

    def insert_account_items(self, items: list[dict[str, Any]]) -> None:
        with self._lock:
            self.account_items = [dict(item) for item in items]
        if threading.current_thread().name == "merge-a":
            self.a_inserted.set()

    def apply_atomic(self, params: dict[str, Any]) -> dict[str, str]:
        request_name = threading.current_thread().name
        self.rpc_calls += 1
        if request_name == "merge-a":
            self._atomic_lock.acquire()
            self.a_deleted.set()
            assert self.b_ready_to_delete.wait(timeout=5)
        else:
            self.b_ready_to_delete.set()
            self._atomic_lock.acquire()

        try:
            if self.guest_status == "converted":
                return {"outcome": "already_converted"}
            if self.return_stale_once:
                self.return_stale_once = False
                with self._lock:
                    self.account_items.append(_line(CONCURRENT_LISTING_ID))
                return {"outcome": "stale_snapshot"}
            self.account_items = [
                {"id": f"merged-{index}", **dict(item)}
                for index, item in enumerate(params["p_merged_items"])
            ]
            self.guest_status = "converted"
            return {"outcome": "applied"}
        finally:
            self._atomic_lock.release()


class _Query:
    def __init__(
        self,
        store: _LegacyRaceStore,
        *,
        operation: str | None = None,
        payload: list[dict[str, Any]] | None = None,
    ) -> None:
        self.store = store
        self.operation = operation
        self.payload = payload

    def delete(self) -> _Query:
        self.operation = "delete"
        return self

    def insert(self, payload: list[dict[str, Any]]) -> _Query:
        self.operation = "insert"
        self.payload = payload
        return self

    def eq(self, _field: str, _value: Any) -> _Query:
        return self

    def execute(self) -> SimpleNamespace:
        if self.operation == "delete":
            self.store.delete_account_items()
        elif self.operation == "insert":
            assert self.payload is not None
            self.store.insert_account_items(self.payload)
        return SimpleNamespace(data=[])


class _Client:
    def __init__(self, store: _LegacyRaceStore) -> None:
        self.store = store

    def table(self, table_name: str) -> _Query:
        assert table_name == "cart_items"
        return _Query(self.store)

    def rpc(self, function_name: str, params: dict[str, Any]) -> _RpcQuery | _StaticRpcQuery:
        if function_name == "ensure_account_cart":
            return _StaticRpcQuery(USER_CART_ID)
        assert function_name == "apply_login_cart_merge"
        return _RpcQuery(self.store, params)


class _StaticRpcQuery:
    def __init__(self, data: Any) -> None:
        self.data = data

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.data)


class _RpcQuery:
    def __init__(self, store: _LegacyRaceStore, params: dict[str, Any]) -> None:
        self.store = store
        self.params = params

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.store.apply_atomic(self.params))


def _merge_proposal(
    *,
    user_items: list[dict[str, Any]],
    guest_items: list[dict[str, Any]],
    **_kwargs: Any,
) -> tuple[list[MergedCartItem], list[Any]]:
    return (
        [
            MergedCartItem(
                listing_id=str(item["listing_id"]),
                qty=int(item["qty"]),
                unit_price_ngwee=int(item["unit_price_ngwee"]),
                wholesale=bool(item["wholesale"]),
            )
            for item in user_items + guest_items
        ],
        [],
    )


def test_ambiguous_concurrent_merge_preserves_account_and_guest_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry while request A is still executing must not replace U with G."""
    from app.routers import cart
    from app.services.cart import merge_atomic
    from app.services.rfq import listing_cart_authority

    store = _LegacyRaceStore()
    user_client = _Client(store)
    service_client = _Client(store)

    monkeypatch.setattr(cart, "_resolve_guest_token", lambda _request, _settings: "guest-token")
    monkeypatch.setattr(cart, "get_user_client", lambda _token, _settings: user_client)
    monkeypatch.setattr(
        cart,
        "_fetch_active_cart_by_user",
        lambda _client, _user_id: {"id": USER_CART_ID, "user_id": USER_ID, "status": "active"},
    )
    monkeypatch.setattr(
        cart,
        "fetch_active_cart_by_guest",
        lambda _token: {"id": GUEST_CART_ID, "guest_token": "guest-token", "status": "active"},
    )
    monkeypatch.setattr(cart, "_fetch_cart_items", lambda _client, cart_id: store.read(cart_id))
    monkeypatch.setattr(cart, "fetch_listings_for_items", lambda _items: {})
    monkeypatch.setattr(
        listing_cart_authority,
        "fetch_rfq_threads_for_items",
        lambda _client, _items: {},
    )
    monkeypatch.setattr(cart, "merge_cart_items", _merge_proposal)
    monkeypatch.setattr(merge_atomic, "fetch_cart_merge_authority", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(cart, "_business_eligible_for_user", lambda _user_id: False)
    monkeypatch.setattr(cart, "service_db_client", lambda: service_client)
    monkeypatch.setattr(cart, "_clear_guest_cookie", lambda _response: None)
    monkeypatch.setattr(cart, "_cart_response", lambda **kwargs: kwargs)

    def run_request(request_name: str) -> None:
        threading.current_thread().name = request_name
        asyncio.run(
            cart.merge_cart_on_login(
                Response(),
                cast(Any, SimpleNamespace(id=USER_ID, token=f"token-{request_name}")),
                cast(Any, SimpleNamespace()),
                cast(Any, SimpleNamespace()),
            )
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        request_a = executor.submit(run_request, "merge-a")
        assert store.a_deleted.wait(timeout=5)
        request_b = executor.submit(run_request, "merge-b")
        request_a.result(timeout=10)
        request_b.result(timeout=10)

    assert {item["listing_id"] for item in store.account_items} == {
        USER_LISTING_ID,
        GUEST_LISTING_ID,
    }


def _patch_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    store: _LegacyRaceStore,
    *,
    guest_token: str | None = "guest-token",
) -> None:
    from app.routers import cart
    from app.services.cart import merge_atomic
    from app.services.rfq import listing_cart_authority

    client = _Client(store)
    monkeypatch.setattr(cart, "_resolve_guest_token", lambda _request, _settings: guest_token)
    monkeypatch.setattr(cart, "get_user_client", lambda _token, _settings: client)
    monkeypatch.setattr(
        cart,
        "_fetch_active_cart_by_user",
        lambda _client, _user_id: {"id": USER_CART_ID, "user_id": USER_ID, "status": "active"},
    )
    monkeypatch.setattr(
        cart,
        "fetch_active_cart_by_guest",
        lambda _token: (
            {
                "id": GUEST_CART_ID,
                "guest_token": "guest-token",
                "status": "active",
            }
            if store.guest_status == "active"
            else None
        ),
    )
    monkeypatch.setattr(cart, "_fetch_cart_items", lambda _client, cart_id: store.read(cart_id))
    monkeypatch.setattr(cart, "fetch_listings_for_items", lambda _items: {})
    monkeypatch.setattr(
        listing_cart_authority,
        "fetch_rfq_threads_for_items",
        lambda _client, _items: {},
    )
    monkeypatch.setattr(cart, "merge_cart_items", _merge_proposal)
    monkeypatch.setattr(merge_atomic, "fetch_cart_merge_authority", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(cart, "_business_eligible_for_user", lambda _user_id: False)
    monkeypatch.setattr(cart, "service_db_client", lambda: client)
    monkeypatch.setattr(cart, "_clear_guest_cookie", lambda _response: None)
    monkeypatch.setattr(cart, "_cart_response", lambda **kwargs: kwargs)


def _run_endpoint() -> None:
    from app.routers import cart

    asyncio.run(
        cart.merge_cart_on_login(
            Response(),
            cast(Any, SimpleNamespace(id=USER_ID, token="token")),
            cast(Any, SimpleNamespace()),
            cast(Any, SimpleNamespace()),
        )
    )


def test_second_request_after_conversion_is_non_destructive_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _LegacyRaceStore()
    _patch_endpoint(monkeypatch, store)

    _run_endpoint()
    first_result = [dict(item) for item in store.account_items]
    _run_endpoint()

    assert store.rpc_calls == 1
    assert store.account_items == first_result
    assert {item["listing_id"] for item in store.account_items} == {
        USER_LISTING_ID,
        GUEST_LISTING_ID,
    }


def test_no_guest_cookie_never_rewrites_authenticated_cart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _LegacyRaceStore()
    _patch_endpoint(monkeypatch, store, guest_token=None)
    original = [dict(item) for item in store.account_items]

    _run_endpoint()

    assert store.rpc_calls == 0
    assert store.account_items == original


def test_stale_account_snapshot_recomputes_without_losing_concurrent_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _LegacyRaceStore()
    store.return_stale_once = True
    _patch_endpoint(monkeypatch, store)

    _run_endpoint()

    assert store.rpc_calls == 2
    assert {item["listing_id"] for item in store.account_items} == {
        USER_LISTING_ID,
        GUEST_LISTING_ID,
        CONCURRENT_LISTING_ID,
    }
