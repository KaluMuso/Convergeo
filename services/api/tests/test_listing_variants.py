"""Listing variants: purchase validation, price/stock semantics, vendor editor API,
and cart add validation (variant must belong to the listing; inactive rejected)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.services.cart.read_path import listing_cart_access_conflict, variant_stock_conflict
from app.services.listings.variants import (
    GroupSpec,
    VariantSpec,
    build_variant_sets,
    effective_price_ngwee,
    overlay_listing_for_variant,
    resolve_variant_for_purchase,
    snapshot_options,
    validate_variant_payload,
    variant_available_qty,
)
from fastapi.testclient import TestClient

LISTING = "10101010-1010-1010-1010-101010101010"
OTHER_LISTING = "20202020-2020-2020-2020-202020202020"
VENDOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_VENDOR = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER = "11111111-1111-1111-1111-111111111111"

G_COLOUR = "c0000000-0000-0000-0000-000000000001"
G_SIZE = "c0000000-0000-0000-0000-000000000002"
V_RED = "d0000000-0000-0000-0000-000000000001"
V_BLUE = "d0000000-0000-0000-0000-000000000002"
V_S = "d0000000-0000-0000-0000-000000000003"
V_M = "d0000000-0000-0000-0000-000000000004"
VAR_RED_S = "e0000000-0000-0000-0000-000000000001"
VAR_RED_M = "e0000000-0000-0000-0000-000000000002"
VAR_BLUE_S = "e0000000-0000-0000-0000-000000000003"
VAR_ARCHIVED = "e0000000-0000-0000-0000-000000000004"
VAR_OTHER_LISTING = "e0000000-0000-0000-0000-000000000005"


def _listing(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": LISTING,
        "vendor_id": VENDOR,
        "price_ngwee": 20_000,
        "stock_mode": "tracked",
        "stock_qty": 10,
        "status": "active",
        "product_class": "A",
        "fulfilment_mode": "stocked",
        "sale_unit": "each",
        "wholesale": False,
        "moq": 1,
        "price_tiers": None,
    }
    row.update(overrides)
    return row


GROUP_ROWS: list[dict[str, Any]] = [
    {"id": G_COLOUR, "listing_id": LISTING, "name": "Colour", "display": "swatch", "position": 1},
    {"id": G_SIZE, "listing_id": LISTING, "name": "Size", "display": "pill", "position": 2},
]
VALUE_ROWS: list[dict[str, Any]] = [
    {"id": V_RED, "group_id": G_COLOUR, "label": "Red", "swatch_hex": "#C0392B", "position": 1},
    {"id": V_BLUE, "group_id": G_COLOUR, "label": "Blue", "swatch_hex": None, "position": 2},
    {"id": V_S, "group_id": G_SIZE, "label": "S", "position": 1},
    {"id": V_M, "group_id": G_SIZE, "label": "M", "position": 2},
]
VARIANT_ROWS: list[dict[str, Any]] = [
    {
        "id": VAR_RED_S,
        "listing_id": LISTING,
        "option_value_ids": [V_S, V_RED],
        "sku_override": "DRS-R-S",
        "price_ngwee": None,
        "stock_qty": 2,
        "status": "active",
        "position": 1,
    },
    {
        "id": VAR_RED_M,
        "listing_id": LISTING,
        "option_value_ids": [V_RED, V_M],
        "sku_override": "DRS-R-M",
        "price_ngwee": 25_000,
        "stock_qty": 0,
        "status": "active",
        "position": 2,
        "image_public_id": "vergeo/red-m",
    },
    {
        "id": VAR_BLUE_S,
        "listing_id": LISTING,
        "option_value_ids": [V_BLUE, V_S],
        "sku_override": None,
        "price_ngwee": None,
        "stock_qty": None,
        "status": "active",
        "position": 3,
    },
    {
        "id": VAR_ARCHIVED,
        "listing_id": LISTING,
        "option_value_ids": [V_BLUE, V_M],
        "status": "archived",
        "position": 4,
    },
    {
        "id": VAR_OTHER_LISTING,
        "listing_id": OTHER_LISTING,
        "option_value_ids": [V_RED],
        "status": "active",
        "position": 1,
    },
]


def _sets() -> dict[str, Any]:
    return build_variant_sets(
        [LISTING, OTHER_LISTING],
        group_rows=GROUP_ROWS,
        value_rows=VALUE_ROWS,
        variant_rows=VARIANT_ROWS,
    )


# ---------------------------------------------------------------------------
# Purchase validation
# ---------------------------------------------------------------------------


class TestResolveVariantForPurchase:
    def test_variant_required_when_listing_has_options(self) -> None:
        with pytest.raises(AppError) as excinfo:
            resolve_variant_for_purchase(
                _sets()[LISTING], listing=_listing(), variant_id=None, qty=1
            )
        assert excinfo.value.code == "cart.variant_required"
        assert excinfo.value.http_status == 422

    def test_listing_without_options_needs_no_variant(self) -> None:
        empty = build_variant_sets([LISTING], group_rows=[], value_rows=[], variant_rows=[])
        assert (
            resolve_variant_for_purchase(empty[LISTING], listing=_listing(), variant_id=None, qty=1)
            is None
        )

    def test_variant_of_another_listing_is_rejected(self) -> None:
        with pytest.raises(AppError) as excinfo:
            resolve_variant_for_purchase(
                _sets()[LISTING], listing=_listing(), variant_id=VAR_OTHER_LISTING, qty=1
            )
        assert excinfo.value.code == "cart.variant_invalid"
        assert excinfo.value.http_status == 422

    def test_unknown_variant_gets_same_answer_as_foreign_variant(self) -> None:
        with pytest.raises(AppError) as unknown:
            resolve_variant_for_purchase(
                _sets()[LISTING],
                listing=_listing(),
                variant_id="ffffffff-ffff-ffff-ffff-ffffffffffff",
                qty=1,
            )
        assert unknown.value.code == "cart.variant_invalid"

    def test_archived_variant_is_rejected(self) -> None:
        with pytest.raises(AppError) as excinfo:
            resolve_variant_for_purchase(
                _sets()[LISTING], listing=_listing(), variant_id=VAR_ARCHIVED, qty=1
            )
        assert excinfo.value.code == "cart.variant_unavailable"
        assert excinfo.value.http_status == 409

    def test_qty_above_variant_stock_is_rejected(self) -> None:
        with pytest.raises(AppError) as excinfo:
            resolve_variant_for_purchase(
                _sets()[LISTING], listing=_listing(), variant_id=VAR_RED_S, qty=3
            )
        assert excinfo.value.code == "cart.variant_out_of_stock"
        assert excinfo.value.details["available_qty"] == 2

    def test_sold_out_variant_is_rejected_even_when_listing_has_stock(self) -> None:
        with pytest.raises(AppError) as excinfo:
            resolve_variant_for_purchase(
                _sets()[LISTING], listing=_listing(stock_qty=50), variant_id=VAR_RED_M, qty=1
            )
        assert excinfo.value.code == "cart.variant_out_of_stock"

    def test_valid_variant_is_returned(self) -> None:
        variant = resolve_variant_for_purchase(
            _sets()[LISTING], listing=_listing(), variant_id=VAR_RED_S, qty=2
        )
        assert variant is not None and variant.id == VAR_RED_S

    def test_untracked_variant_stock_is_unlimited_at_variant_level(self) -> None:
        variant = resolve_variant_for_purchase(
            _sets()[LISTING], listing=_listing(), variant_id=VAR_BLUE_S, qty=9
        )
        assert variant is not None

    def test_always_available_listing_ignores_variant_stock(self) -> None:
        variant = _sets()[LISTING].get(VAR_RED_M)
        assert variant is not None
        assert variant_available_qty(_listing(stock_mode="always_available"), variant) is None


class TestPriceAndOverlay:
    def test_override_wins_and_null_inherits(self) -> None:
        sets = _sets()[LISTING]
        assert effective_price_ngwee(_listing(), sets.get(VAR_RED_M)) == 25_000
        assert effective_price_ngwee(_listing(), sets.get(VAR_RED_S)) == 20_000

    def test_overlay_prices_line_as_variant_and_labels_in_group_order(self) -> None:
        view = overlay_listing_for_variant(_listing(), _sets()[LISTING], VAR_RED_M)
        assert view["price_ngwee"] == 25_000
        assert view["_variant_options"] == [
            {"group": "Colour", "value": "Red"},
            {"group": "Size", "value": "M"},
        ]
        assert view["_variant_available_qty"] == 0
        assert view["_variant_image_public_id"] == "vergeo/red-m"

    def test_overlay_flags_archived_and_missing_choice(self) -> None:
        archived = overlay_listing_for_variant(_listing(), _sets()[LISTING], VAR_ARCHIVED)
        assert archived["_variant_unavailable"] is True
        assert archived["price_ngwee"] == 20_000
        missing = overlay_listing_for_variant(_listing(), _sets()[LISTING], None)
        assert missing["_variant_required"] is True

    def test_read_path_surfaces_variant_conflicts(self) -> None:
        archived = overlay_listing_for_variant(_listing(), _sets()[LISTING], VAR_ARCHIVED)
        conflict = listing_cart_access_conflict(LISTING, archived, business_eligible=False)
        assert conflict is not None and conflict.code == "cart.variant_unavailable"
        missing = overlay_listing_for_variant(_listing(), _sets()[LISTING], None)
        conflict = listing_cart_access_conflict(LISTING, missing, business_eligible=False)
        assert conflict is not None and conflict.code == "cart.variant_required"

    def test_checkout_stock_guard(self) -> None:
        view = overlay_listing_for_variant(_listing(), _sets()[LISTING], VAR_RED_S)
        assert variant_stock_conflict(LISTING, view, 2) is None
        conflict = variant_stock_conflict(LISTING, view, 3)
        assert conflict is not None and conflict["code"] == "cart.variant_out_of_stock"

    def test_snapshot_options_is_defensive(self) -> None:
        assert snapshot_options(None) == []
        assert snapshot_options({"options": "bad"}) == []
        assert snapshot_options({"options": [{"group": "Size", "value": "M"}, {"x": 1}]}) == [
            {"group": "Size", "value": "M"}
        ]


# ---------------------------------------------------------------------------
# Vendor payload semantics
# ---------------------------------------------------------------------------


def _groups() -> list[GroupSpec]:
    return [
        GroupSpec(name="Colour", display="swatch", values=(("Red", "#C0392B"), ("Blue", None))),
        GroupSpec(name="Size", display="pill", values=(("S", None), ("M", None))),
    ]


def _variant(*options: str, **overrides: Any) -> VariantSpec:
    fields: dict[str, Any] = {
        "options": options,
        "sku": None,
        "stock_qty": 1,
        "price_ngwee": None,
        "compare_at_ngwee": None,
        "image_public_id": None,
        "status": "active",
    }
    fields.update(overrides)
    return VariantSpec(**fields)


def _reason(groups: list[GroupSpec], variants: list[VariantSpec], **listing: Any) -> str:
    with pytest.raises(AppError) as excinfo:
        validate_variant_payload(
            groups, variants, listing=_listing(**listing), listing_image_ids=["img/1"]
        )
    assert excinfo.value.code == "variants.invalid"
    return str(excinfo.value.details["reason"])


class TestValidateVariantPayload:
    def test_valid_matrix_passes(self) -> None:
        validate_variant_payload(
            _groups(),
            [
                _variant("Red", "S", sku="R-S", image_public_id="img/1"),
                _variant("blue", "m", price_ngwee=25_000, compare_at_ngwee=30_000),
            ],
            listing=_listing(),
            listing_image_ids=["img/1"],
        )

    def test_clearing_all_options_is_allowed(self) -> None:
        validate_variant_payload([], [], listing=_listing(), listing_image_ids=[])

    @pytest.mark.parametrize(
        ("variants", "reason"),
        [
            ([_variant("Red")], "optionPerGroup"),
            ([_variant("Pink", "S")], "unknownValue"),
            ([_variant("Red", "S"), _variant("red", "s")], "duplicateCombination"),
            ([_variant("Red", "S", sku="A"), _variant("Red", "M", sku="a")], "duplicateSku"),
            ([_variant("Red", "S", sku="bad sku")], "invalidSku"),
            ([_variant("Red", "S", price_ngwee=0)], "invalidPrice"),
            ([_variant("Red", "S", compare_at_ngwee=20_000)], "invalidCompareAt"),
            ([_variant("Red", "S", image_public_id="img/elsewhere")], "imageNotOnListing"),
            ([_variant("Red", "S", status="archived")], "activeVariantRequired"),
            ([], "variantsRequired"),
        ],
    )
    def test_invalid_variants(self, variants: list[VariantSpec], reason: str) -> None:
        assert _reason(_groups(), variants) == reason

    def test_group_rules(self) -> None:
        dup = [_groups()[0], GroupSpec(name="colour", display="pill", values=(("X", None),))]
        assert _reason(dup, [_variant("Red", "X")]) == "duplicateGroup"
        bad_swatch = [GroupSpec(name="Colour", display="swatch", values=(("Red", "red"),))]
        assert _reason(bad_swatch, [_variant("Red")]) == "invalidSwatch"
        dup_value = [GroupSpec(name="Size", display="pill", values=(("S", None), ("s", None)))]
        assert _reason(dup_value, [_variant("S")]) == "duplicateValue"
        assert _reason([], [_variant("Red")]) == "groupsRequired"

    def test_listing_kinds_that_cannot_have_variants(self) -> None:
        variants = [_variant("Red", "S")]
        assert _reason(_groups(), variants, product_class="E") == "classEUnsupported"
        assert _reason(_groups(), variants, wholesale=True) == "wholesaleUnsupported"
        assert _reason(_groups(), variants, sale_unit="metre") == "measuredUnsupported"


# ---------------------------------------------------------------------------
# Vendor editor endpoint
# ---------------------------------------------------------------------------


class _Query:
    def __init__(self, store: _Store, table: str) -> None:
        self.store = store
        self.table = table
        self.filters: list[tuple[str, Any]] = []
        self.single = False

    def select(self, *_args: Any, **_kwargs: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self.filters.append((column, lambda row, v=value: row.get(column) == v))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        allowed = set(values)
        self.filters.append((column, lambda row: row.get(column) in allowed))
        return self

    def maybe_single(self) -> _Query:
        self.single = True
        return self

    def limit(self, _n: int) -> _Query:
        return self

    def execute(self) -> MagicMock:
        rows = [
            row
            for row in self.store.tables.get(self.table, [])
            if all(predicate(row) for _column, predicate in self.filters)
        ]
        response = MagicMock()
        response.data = (rows[0] if rows else None) if self.single else rows
        return response


class _Store:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "vendors": [
                {"id": VENDOR, "owner_user_id": USER, "status": "active", "kyc_tier": 1},
            ],
            "vendor_listings": [
                {
                    **_listing(),
                    "listing_images": [
                        {
                            "id": "img-row",
                            "listing_id": LISTING,
                            "cloudinary_public_id": "img/1",
                            "position": 1,
                        }
                    ],
                },
                {**_listing(id=OTHER_LISTING, vendor_id=OTHER_VENDOR), "listing_images": []},
            ],
            "listing_option_groups": [{**row, "kind": "variant"} for row in GROUP_ROWS],
            "listing_option_values": list(VALUE_ROWS),
            "vendor_listing_variants": [
                {**row, "product_variant_id": None} for row in VARIANT_ROWS
            ],
        }
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        self.rpc_calls.append((name, params))
        call = MagicMock()
        call.execute.return_value = MagicMock(data={"variants": len(params["p_variants"])})
        return call


@pytest.fixture
def vendor_api() -> Generator[tuple[TestClient, _Store], None, None]:
    store = _Store()
    wrapper = MagicMock()
    wrapper.client = store
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: wrapper
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=USER, roles=frozenset({"vendor"}), token="t"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, store
    app.dependency_overrides.clear()


def _put_body() -> dict[str, Any]:
    return {
        "groups": [
            {
                "name": "Colour",
                "display": "swatch",
                "values": [{"label": "Red", "swatch_hex": "#C0392B"}, {"label": "Blue"}],
            },
            {"name": "Size", "values": [{"label": "S"}, {"label": "M"}]},
        ],
        "variants": [
            {"options": ["Red", "S"], "sku": "R-S", "stock_qty": 3, "image_public_id": "img/1"},
            {"options": ["Blue", "M"], "stock_qty": 1, "price_ngwee": 25_000},
        ],
    }


class TestVendorVariantsEndpoint:
    def test_get_returns_groups_and_variants_with_labels(
        self, vendor_api: tuple[TestClient, _Store]
    ) -> None:
        client, _store = vendor_api
        response = client.get(f"/vendor/listings/{LISTING}/variants")
        assert response.status_code == 200, response.text
        body = response.json()
        assert [group["name"] for group in body["groups"]] == ["Colour", "Size"]
        red_m = next(v for v in body["variants"] if v["id"] == VAR_RED_M)
        assert red_m["options"] == ["Red", "M"]
        assert red_m["price_ngwee"] == 25_000

    def test_put_calls_atomic_writer_with_normalised_payload(
        self, vendor_api: tuple[TestClient, _Store]
    ) -> None:
        client, store = vendor_api
        response = client.put(f"/vendor/listings/{LISTING}/variants", json=_put_body())
        assert response.status_code == 200, response.text
        name, params = store.rpc_calls[0]
        assert name == "vendor_replace_listing_variants"
        assert params["p_listing_id"] == LISTING
        assert params["p_variants"][1]["price_ngwee"] == 25_000
        assert params["p_groups"][0]["values"][0] == {"label": "Red", "swatch_hex": "#C0392B"}

    def test_put_rejects_other_vendors_listing(self, vendor_api: tuple[TestClient, _Store]) -> None:
        client, store = vendor_api
        response = client.put(f"/vendor/listings/{OTHER_LISTING}/variants", json=_put_body())
        assert response.status_code == 403
        assert store.rpc_calls == []

    def test_put_rejects_semantic_errors_before_writing(
        self, vendor_api: tuple[TestClient, _Store]
    ) -> None:
        client, store = vendor_api
        body = _put_body()
        body["variants"][1]["options"] = ["Red", "S"]
        response = client.put(f"/vendor/listings/{LISTING}/variants", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["details"]["reason"] == "duplicateCombination"
        assert store.rpc_calls == []

    def test_put_rejects_float_money(self, vendor_api: tuple[TestClient, _Store]) -> None:
        client, store = vendor_api
        body = _put_body()
        body["variants"][1]["price_ngwee"] = 250.5
        response = client.put(f"/vendor/listings/{LISTING}/variants", json=body)
        assert response.status_code == 422
        assert store.rpc_calls == []

    def test_customer_role_is_forbidden(self, vendor_api: tuple[TestClient, _Store]) -> None:
        client, _store = vendor_api
        client.app.dependency_overrides[get_current_user] = lambda: CurrentUser(  # type: ignore[attr-defined]
            id=USER, roles=frozenset({"customer"}), token="t"
        )
        response = client.put(f"/vendor/listings/{LISTING}/variants", json=_put_body())
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Cart add endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def cart_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, MagicMock], None, None]:
    from app.routers import cart as cart_router

    writer = MagicMock()
    monkeypatch.setattr(cart_router, "fetch_listing", lambda *_a, **_k: _listing())
    monkeypatch.setattr(cart_router, "_variant_set_for", lambda listing_id: _sets()[listing_id])
    monkeypatch.setattr(cart_router, "_business_eligible_for_user", lambda _uid: False)
    monkeypatch.setattr(cart_router, "_resolve_line_location_id", lambda *_a, **_k: None)
    monkeypatch.setattr(cart_router, "_enforce_listing_cart_rules", lambda *_a, **_k: None)
    monkeypatch.setattr(cart_router, "service_db_client", lambda: writer)
    monkeypatch.setattr(cart_router, "_fetch_cart_items", lambda *_a, **_k: [])
    monkeypatch.setattr(cart_router, "fetch_listings_for_items", lambda _items: {})
    monkeypatch.setattr(cart_router, "emit_cart_add", lambda **_k: None)
    monkeypatch.setattr(cart_router, "validate_clip_attribution", lambda *_a, **_k: None)

    owner = cart_router.CartOwner(cart_id="cart-1", user_id=None, guest_token="g", is_guest=True)
    existing = MagicMock()
    existing.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(  # noqa: E501
        data=[]
    )
    monkeypatch.setattr(cart_router, "_db_client_for_owner", lambda *_a, **_k: existing)

    app = create_app()
    app.dependency_overrides[cart_router._resolve_cart_owner] = lambda: owner
    app.dependency_overrides[get_supabase_client] = lambda: MagicMock()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, writer
    app.dependency_overrides.clear()


def _inserted(writer: MagicMock) -> dict[str, Any]:
    return writer.table.return_value.insert.call_args.args[0]  # type: ignore[no-any-return]


class TestCartAddVariantValidation:
    def test_missing_variant_rejected(self, cart_api: tuple[TestClient, MagicMock]) -> None:
        client, writer = cart_api
        response = client.post("/cart/items", json={"listing_id": LISTING, "qty": 1})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cart.variant_required"
        writer.table.return_value.insert.assert_not_called()

    def test_variant_of_other_listing_rejected(
        self, cart_api: tuple[TestClient, MagicMock]
    ) -> None:
        client, writer = cart_api
        response = client.post(
            "/cart/items",
            json={"listing_id": LISTING, "qty": 1, "listing_variant_id": VAR_OTHER_LISTING},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cart.variant_invalid"
        writer.table.return_value.insert.assert_not_called()

    def test_inactive_variant_rejected(self, cart_api: tuple[TestClient, MagicMock]) -> None:
        client, writer = cart_api
        response = client.post(
            "/cart/items",
            json={"listing_id": LISTING, "qty": 1, "listing_variant_id": VAR_ARCHIVED},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "cart.variant_unavailable"
        writer.table.return_value.insert.assert_not_called()

    def test_valid_variant_persists_with_override_price(
        self, cart_api: tuple[TestClient, MagicMock], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routers import cart as cart_router

        client, writer = cart_api
        rows = [dict(row, stock_qty=4) if row["id"] == VAR_RED_M else row for row in VARIANT_ROWS]
        stocked = build_variant_sets(
            [LISTING], group_rows=GROUP_ROWS, value_rows=VALUE_ROWS, variant_rows=rows
        )
        monkeypatch.setattr(cart_router, "_variant_set_for", lambda _lid: stocked[LISTING])
        response = client.post(
            "/cart/items",
            json={"listing_id": LISTING, "qty": 2, "listing_variant_id": VAR_RED_M},
        )
        assert response.status_code == 200, response.text
        row = _inserted(writer)
        assert row["listing_variant_id"] == VAR_RED_M
        assert row["unit_price_ngwee"] == 25_000
        assert isinstance(row["unit_price_ngwee"], int)
