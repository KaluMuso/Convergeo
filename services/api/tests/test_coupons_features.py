"""Gift privacy, birthday consent/minors/29-Feb, flags and refund coupon shares (fakes only)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from app.errors import AppError
from app.routers import account_birthday as birthday_mod
from app.routers import checkout_extras as extras
from app.routers import customer_orders as orders_mod
from app.routers import internal_birthdays as tick_mod
from app.services.coupons.manage import CouponCreateRequest, build_coupon_row
from app.services.coupons.store import map_reservation_error, require_flag
from app.services.refunds import execute as refund_mod

USER = "11111111-1111-1111-1111-111111111111"
VENDOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _Query:
    def __init__(self, table: _Table) -> None:
        self.table = table
        self.filters: list[tuple[str, str, Any]] = []
        self.single = False
        self.payload: dict[str, Any] | None = None
        self.op = "select"

    def select(self, *_: Any, **__: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self.filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> _Query:
        self.filters.append(("neq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self.filters.append(("in", column, list(values)))
        return self

    def order(self, *_: Any, **__: Any) -> _Query:
        return self

    def limit(self, *_: Any) -> _Query:
        return self

    def maybe_single(self) -> _Query:
        self.single = True
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, column, value in self.filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "neq" and row.get(column) == value:
                return False
            if op == "in" and row.get(column) not in value:
                return False
        return True

    def execute(self) -> SimpleNamespace:
        rows = [row for row in self.table.rows if self._match(row)]
        if self.op == "update" and self.payload is not None:
            for row in rows:
                row.update(self.payload)
        if self.op == "delete":
            self.table.rows = [row for row in self.table.rows if not self._match(row)]
        if self.single:
            return SimpleNamespace(data=rows[0] if rows else None)
        return SimpleNamespace(data=rows)


class _Table:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, *_: Any, **__: Any) -> _Query:
        return _Query(self)

    def insert(self, payload: dict[str, Any]) -> _Query:
        self.rows.append(dict(payload))
        query = _Query(self)
        query.filters.append(("eq", "__never__", object()))
        return query

    def upsert(self, payload: dict[str, Any], **_: Any) -> _Query:
        return self.insert(payload)

    def update(self, payload: dict[str, Any]) -> _Query:
        query = _Query(self)
        query.op, query.payload = "update", payload
        return query

    def delete(self) -> _Query:
        query = _Query(self)
        query.op = "delete"
        return query


class _Client:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_result: Any = "coupon-id"

    def table(self, name: str) -> _Table:
        return self.tables.setdefault(name, _Table())

    def rpc(self, name: str, params: dict[str, Any]) -> SimpleNamespace:
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rpc_result))


class _Service:
    def __init__(self) -> None:
        self.client = _Client()


def _flags(service: _Service, **flags: bool) -> None:
    service.client.table("feature_flags").rows.extend(
        {"flag": flag, "enabled": enabled} for flag, enabled in flags.items()
    )


# --- flags ---------------------------------------------------------------------


def test_flags_default_off_fail_closed() -> None:
    service = _Service()
    with pytest.raises(AppError) as exc:
        require_flag(service, "coupons")
    assert exc.value.code == "feature_disabled"


# --- gift privacy --------------------------------------------------------------


def _gift(**overrides: Any) -> extras.GiftRequest:
    base: dict[str, Any] = {
        "session_id": "c" * 36,
        "recipient_name": "  Mary   Banda ",
        "recipient_phone": "0971 234 567",
        "message": "Happy birthday!",
        "recipient_agreed": True,
    }
    base.update(overrides)
    return extras.GiftRequest(**base)


def test_gift_requires_recipient_consent() -> None:
    with pytest.raises(AppError) as exc:
        extras._validated_gift(_gift(recipient_agreed=False))
    assert exc.value.code == "gift.consent_required"


def test_gift_normalises_and_masks_recipient_phone() -> None:
    name, phone, message = extras._validated_gift(_gift())
    assert (name, phone, message) == ("Mary Banda", "+260971234567", "Happy birthday!")
    masked = extras.mask_phone(phone)
    assert masked is not None and "1234" not in masked and masked.endswith("567")


@pytest.mark.parametrize("message", ["see www.spam.example", "https://x.zm/pay"])
def test_gift_message_rejects_links(message: str) -> None:
    with pytest.raises(AppError) as exc:
        extras._validated_gift(_gift(message=message))
    assert exc.value.code == "gift.message_invalid"


def test_gift_rejects_non_zambian_phone() -> None:
    with pytest.raises(AppError) as exc:
        extras._validated_gift(_gift(recipient_phone="+44 20 7946 0000"))
    assert exc.value.code == "gift.phone_invalid"


def test_gift_pickup_pin_is_never_shown_to_the_payer() -> None:
    service = _Service()
    order_row = {"id": "o-1", "status": "ready", "fulfilment": "pickup", "is_gift": True}
    service.client.table("orders").rows.append(
        {"id": "o-1", "pickup_pin": "123456", "pickup_qr_token": "qr"}
    )
    creds = orders_mod._load_pickup_credentials(service, order_row)
    assert creds is not None
    assert creds.pin is None and creds.qr_token is None and creds.sent_to_recipient


def test_gift_receipt_model_has_no_price_fields() -> None:
    fields = set(orders_mod.GiftReceiptOut.model_fields) | set(
        orders_mod.GiftReceiptItemOut.model_fields
    )
    assert not any("ngwee" in field or "price" in field for field in fields)


def test_vendor_pickup_pin_goes_to_recipient_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import vendor_orders as vendor_mod

    service = _Service()
    captured: dict[str, Any] = {}

    def fake_enqueue(_client: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(
        "app.services.notifications.dedupe.enqueue_outbox_row", fake_enqueue, raising=True
    )
    vendor_mod._enqueue_gift_pickup_pin(
        service,
        order_id="o-1",
        gift={"recipient_name": "Mary", "recipient_phone": "+260971234567", "shop_name": "S"},
        pin="482913",
        version=2,
    )
    assert captured["payload"]["to"] == "+260971234567"
    assert "recipient_id" not in captured["payload"]
    assert "482913" not in captured["entity_id"]  # the PIN never lands in a dedupe key


# --- coupon admin/vendor validation -------------------------------------------


def _create(**overrides: Any) -> CouponCreateRequest:
    base: dict[str, Any] = {
        "code": "shop20",
        "kind": "percent",
        "percent_bps": 2_000,
        "starts_on": "2026-12-01",
        "ends_on": "2026-12-31",
    }
    base.update(overrides)
    return CouponCreateRequest(**base)


def test_vendor_coupon_is_forced_onto_own_shop_and_capped() -> None:
    row = build_coupon_row(
        _create(), funder="vendor", vendor_id=VENDOR, actor_id=USER, max_percent_bps=5_000
    )
    assert row["scope"] == "vendor" and row["scope_vendor_id"] == VENDOR
    assert row["code"] == "SHOP20" and row["funder"] == "vendor"
    # Inclusive end date: valid all of 31 Dec Lusaka time (exclusive 1 Jan 00:00 +02:00).
    assert row["ends_at"].startswith("2027-01-01T00:00:00+02:00")
    with pytest.raises(AppError):
        build_coupon_row(
            _create(percent_bps=6_000),
            funder="vendor",
            vendor_id=VENDOR,
            actor_id=USER,
            max_percent_bps=5_000,
        )
    with pytest.raises(AppError):
        build_coupon_row(
            _create(scope="category", scope_id="c" * 36),
            funder="vendor",
            vendor_id=VENDOR,
            actor_id=USER,
        )


def test_coupon_dates_must_be_ordered() -> None:
    with pytest.raises(AppError):
        build_coupon_row(
            _create(ends_on="2026-11-30"), funder="platform", vendor_id=None, actor_id=USER
        )


@pytest.mark.parametrize(
    ("marker", "code"),
    [
        ("ERROR: COUPON_LIMIT:total", "coupon.limit_reached"),
        ("ERROR: COUPON_LIMIT:user", "coupon.already_used"),
        ("ERROR: COUPON_BUDGET:exhausted", "coupon.budget_exhausted"),
        ("ERROR: COUPON_INVALID:expired", "coupon.expired"),
    ],
)
def test_reservation_markers_map_to_customer_errors(marker: str, code: str) -> None:
    error = map_reservation_error(marker)
    assert error is not None and error.code == code and error.http_status == 409


# --- refunds carry the coupon share -----------------------------------------------


def _refund_service(funder: str) -> _Service:
    service = _Service()
    service.client.table("order_items").rows.append(
        {"order_id": "o-1", "qty": 2, "unit_price_ngwee": 10_000}
    )
    service.client.table("refunds").rows.append(
        {"order_id": "o-1", "status": "failed", "breakdown": {"coupon_discount_ngwee": 999}}
    )
    return service


@pytest.mark.parametrize("funder", ["platform", "vendor"])
def test_refund_returns_only_what_the_customer_paid(funder: str) -> None:
    service = _refund_service(funder)
    order = {"delivery_fee_ngwee": 3_000, "coupon_discount_ngwee": 2_000, "coupon_funder": funder}
    share = refund_mod._coupon_share(
        service,
        order=order,
        order_id="o-1",
        refunded_items_ngwee=20_000,
    )
    assert share.discount_ngwee == 2_000  # failed refunds never count as returned
    assert share.promo_return_ngwee == (2_000 if funder == "platform" else 0)
    amount, lane1, _ = refund_mod._compute_lane_amounts(
        service_client=service,
        order=order,
        order_id="o-1",
        lane=1,
        return_transport_ngwee=0,
        coupon_share=share,
    )
    assert lane1 is not None and amount == 20_000 + 3_000 - 2_000


def test_partial_return_gets_proportional_share() -> None:
    service = _refund_service("platform")
    order = {"coupon_discount_ngwee": 2_000, "coupon_funder": "platform"}
    share = refund_mod._coupon_share(
        service,
        order=order,
        order_id="o-1",
        refunded_items_ngwee=10_000,
    )
    assert share.discount_ngwee == 1_000


# --- birthdays ---------------------------------------------------------------------


def test_birthday_validation_and_age() -> None:
    assert birthday_mod.valid_birthday(29, 2, None)
    assert not birthday_mod.valid_birthday(29, 2, 2023)
    assert not birthday_mod.valid_birthday(31, 4, None)
    assert birthday_mod.age_on(date(2026, 11, 13), day=14, month=11, year=2008) == 17
    assert birthday_mod.age_on(date(2026, 11, 14), day=14, month=11, year=2008) == 18


def test_feb_29_greeted_on_feb_28_in_non_leap_years() -> None:
    assert tick_mod.birthday_keys_for(date(2027, 2, 28)) == [(2, 28), (2, 29)]
    assert tick_mod.birthday_keys_for(date(2028, 2, 28)) == [(2, 28)]
    assert tick_mod.birthday_keys_for(date(2028, 2, 29)) == [(2, 29)]


def _birthday_service(*, flags: bool = True) -> _Service:
    service = _Service()
    _flags(service, birthday_greetings=flags, coupons=flags)
    rows = [
        # consenting adult with a completed order → greeted
        {
            "user_id": "u-adult",
            "birth_day": 13,
            "birth_month": 11,
            "birth_year": None,
            "consent_at": "x",
            "adult_confirmed_at": "x",
        },
        # minor (year present) → never targeted
        {
            "user_id": "u-minor",
            "birth_day": 13,
            "birth_month": 11,
            "birth_year": 2012,
            "consent_at": "x",
            "adult_confirmed_at": "x",
        },
        # no consent timestamp → no greeting
        {
            "user_id": "u-noconsent",
            "birth_day": 13,
            "birth_month": 11,
            "birth_year": None,
            "consent_at": None,
            "adult_confirmed_at": "x",
        },
        # adult without any completed order → not eligible
        {
            "user_id": "u-nobuy",
            "birth_day": 13,
            "birth_month": 11,
            "birth_year": 1990,
            "consent_at": "x",
            "adult_confirmed_at": "x",
        },
    ]
    service.client.table("profile_birthdays").rows.extend(rows)
    service.client.table("profiles").rows.extend(
        {"id": user, "phone": "+260971000000", "deleted_at": None}
        for user in ("u-adult", "u-minor", "u-noconsent", "u-nobuy")
    )
    service.client.table("orders").rows.extend(
        [
            {"customer_id": "u-adult", "status": "completed"},
            {"customer_id": "u-minor", "status": "completed"},
            {"customer_id": "u-nobuy", "status": "placed"},
        ]
    )
    return service


def test_birthday_tick_targets_only_consenting_adults() -> None:
    service = _birthday_service()
    result = tick_mod.birthday_tick(service, on="2026-11-13")
    assert result.issued == 1 and result.candidates == 4 and result.not_eligible == 3
    [(name, params)] = service.client.rpc_calls
    assert name == "issue_birthday_greeting" and params["p_user_id"] == "u-adult"
    assert params["p_code"].startswith("BDAY-") and params["p_year"] == 2026


def test_birthday_tick_rerun_issues_nothing_new() -> None:
    service = _birthday_service()
    service.client.rpc_result = None  # the DB unique key says "already greeted this year"
    result = tick_mod.birthday_tick(service, on="2026-11-13")
    assert result.issued == 0 and result.already_issued == 1


def test_birthday_tick_is_a_noop_while_flags_are_off() -> None:
    service = _birthday_service(flags=False)
    result = tick_mod.birthday_tick(service, on="2026-11-13")
    assert result.skipped == "disabled" and service.client.rpc_calls == []


def test_birthday_requires_consent_and_refuses_minors(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _Service()
    _flags(service, birthday_greetings=True)
    monkeypatch.setattr(birthday_mod, "bump_rate_counter", lambda **_: (True, 0))
    user = SimpleNamespace(id=USER)

    def put(**body: Any) -> Any:
        payload = {"day": 1, "month": 6, "consent": True, "adult_confirmed": True, **body}
        return birthday_mod.put_birthday(
            birthday_mod.BirthdayIn(**payload),
            user,  # type: ignore[arg-type]
            service,
        )

    with pytest.raises(AppError) as exc:
        put(consent=False)
    assert exc.value.code == "birthday.consent_required"
    with pytest.raises(AppError) as exc:
        put(adult_confirmed=False)
    assert exc.value.code == "birthday.adult_required"
    with pytest.raises(AppError) as exc:
        put(year=2015)
    assert exc.value.code == "birthday.minor"
    assert service.client.table("profile_birthdays").rows == []  # a minor's date is never stored
