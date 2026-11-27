from __future__ import annotations

from typing import Any

from app.routers.customer_orders import _load_order_items as customer_items
from app.routers.vendor_order_queue import _load_items_by_order
from app.routers.vendor_orders import _load_order_items as vendor_items
from app.services.order_item_titles import display_title, resolve_missing_titles


class _Resp:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _Query:
    def __init__(self, client: _Client, name: str) -> None:
        self.client = client
        self.name = name
        self.ids: list[str] | None = None

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def eq(self, *_a: Any) -> _Query:
        return self

    def in_(self, _col: str, values: list[str]) -> _Query:
        self.ids = values
        return self

    def execute(self) -> _Resp:
        self.client.calls.append(self.name)
        rows = self.client.tables.get(self.name, [])
        if self.name == "order_item_products" and self.ids is not None:
            rows = [r for r in rows if r["order_item_id"] in self.ids]
        return _Resp(rows)


class _Client:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.calls: list[str] = []
        self.client = self

    def table(self, name: str) -> _Query:
        return _Query(self, name)


def _link(item_id: str, override: str | None, product: str | None) -> dict[str, Any]:
    return {
        "order_item_id": item_id,
        "listings": {
            "id": "l-" + item_id,
            "title_override": override,
            "products": {"name": product} if product else None,
        },
    }


ITEMS = [
    {"id": "a", "order_id": "order-1", "qty": 1, "unit_price_ngwee": 100, "title_snapshot": None},
    {"id": "b", "order_id": "order-1", "qty": 2, "unit_price_ngwee": 100, "title_snapshot": "  "},
    {
        "id": "c",
        "order_id": "order-1",
        "qty": 1,
        "unit_price_ngwee": 100,
        "title_snapshot": "Snapshot wins",
    },
    {"id": "d", "order_id": "order-1", "qty": 1, "unit_price_ngwee": 100, "title_snapshot": None},
    {"id": "e", "order_id": "order-1", "qty": 1, "unit_price_ngwee": 100, "title_snapshot": None},
]
LINKS = [
    _link("a", None, "Solar lamp"),
    _link("b", "Override title", "Ignored product"),
    _link("c", None, "Should not be used"),
    _link("d", None, None),
]


def test_resolve_missing_titles_single_batched_query() -> None:
    client = _Client({"order_item_products": LINKS})
    resolved = resolve_missing_titles(client, ITEMS)
    assert resolved == {"a": "Solar lamp", "b": "Override title"}
    assert client.calls == ["order_item_products"]


def test_no_lookup_when_all_snapshots_present() -> None:
    client = _Client({})
    resolve_missing_titles(client, [ITEMS[2]])
    assert client.calls == []


def test_display_title_precedence() -> None:
    resolved = {"a": "Solar lamp"}
    assert display_title(ITEMS[2], resolved) == "Snapshot wins"
    assert display_title(ITEMS[0], resolved) == "Solar lamp"
    assert display_title(ITEMS[4], resolved) is None


def _titles(items: list[Any]) -> list[str | None]:
    return [item.title for item in items]


def test_customer_and_vendor_serializers_resolve_titles() -> None:
    for loader in (customer_items, vendor_items):
        client = _Client({"order_items": ITEMS, "order_item_products": LINKS})
        items = loader(client, "order-1")
        assert _titles(items) == ["Solar lamp", "Override title", "Snapshot wins", None, None]
        assert client.calls.count("order_item_products") == 1


def test_vendor_queue_preview_resolves_titles_in_one_query() -> None:
    rows = [{**ITEMS[0], "order_id": "o1"}, {**ITEMS[1], "order_id": "o2"}]
    client = _Client({"order_items": rows, "order_item_products": LINKS})
    grouped = _load_items_by_order(client, ["o1", "o2"])
    assert grouped["o1"][0]["title_snapshot"] == "Solar lamp"
    assert grouped["o2"][0]["title_snapshot"] == "Override title"
    assert client.calls.count("order_item_products") == 1


def test_customer_list_loader_resolves_titles_once_for_many_orders() -> None:
    from app.routers.customer_orders import _load_order_items_many

    order_ids = [f"o{i}" for i in range(20)]
    rows = [
        {
            "id": f"i{i}",
            "order_id": f"o{i}",
            "qty": 1,
            "unit_price_ngwee": 100,
            "title_snapshot": None,
        }
        for i in range(20)
    ]
    links = [_link(f"i{i}", None, f"Product {i}") for i in range(20)]
    client = _Client({"order_items": rows, "order_item_products": links})
    grouped = _load_order_items_many(client, order_ids)
    assert [grouped[o][0].title for o in order_ids] == [f"Product {i}" for i in range(20)]
    assert client.calls == ["order_items", "order_item_products"]
