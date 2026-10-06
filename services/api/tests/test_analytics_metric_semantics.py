"""DB-free contracts: event counts do not establish payment or conversion.

All query results are synthetic; these tests never execute SQL or migrations.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from app.errors import AppError
from app.routers import vendor_analytics as vendor
from app.services.analytics import events
from app.services.orders.audit import SqlResult

VENDOR = "a9100000-0000-0000-0000-000000000001"


def test_order_placement_is_not_payment_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(_sql: str) -> SqlResult:
        return SqlResult(
            ok=True,
            rows=["order_placed|3", "payment_start|2", "checkout_start|2", "payment_success|9"],
        )

    monkeypatch.setattr(events, "run_sql_script", run)
    report = events.query_funnel(7)
    assert report.event_counts == {
        "search": 0,
        "product_view": 0,
        "cart": 0,
        "checkout": 4,
        "order_placed": 3,
    }
    assert report.count("order_placed") == 3
    assert report.count("pay") == 3  # deprecated, historically order placement
    assert report.steps["pay"] == 3
    assert "order_placed" not in report.steps
    assert "pay" not in report.event_counts
    assert report.count("payment_success") == 0  # no fabricated paid metric
    assert sum(report.steps.values()) == 7
    assert sum(report.event_counts.values()) == 7


def test_historical_dictionary_and_serialized_contract() -> None:
    historical = {
        "window_days": 7,
        "steps": {"search": 1, "product_view": 2, "cart": 3, "checkout": 4, "pay": 5},
    }
    report = events.FunnelReport(**json.loads(json.dumps(historical)))
    assert json.loads(json.dumps(asdict(report))) == historical
    assert events.FUNNEL_STEPS == ("search", "product_view", "cart", "checkout", "pay")
    assert events.EVENT_TYPE_TO_STEP["order_placed"] == "pay"
    assert events.EVENT_TYPE_TO_COUNT_STEP["order_placed"] == "order_placed"
    assert set(report.event_counts) == set(events.EVENT_COUNT_STEPS)
    assert report.event_counts["order_placed"] == report.steps["pay"] == 5
    assert report.count("order_placed") == report.count("pay") == 5
    assert sum(report.event_counts.values()) == sum(report.steps.values()) == 15


@pytest.mark.parametrize(
    "orders,activity,ratio", [(3, 1, 300.0), (1, 3, 33.3), (0, 2, 0.0), (2, 0, None), (0, 0, None)]
)
def test_explicit_activity_ratio_and_legacy_values(
    monkeypatch: pytest.MonkeyPatch, orders: int, activity: int, ratio: float | None
) -> None:
    queries: list[str] = []

    def run(sql: str) -> SqlResult:
        queries.append(sql)
        if "WITH days" in sql and "order_items" in sql:
            return SqlResult(ok=True, rows=[f"2026-10-02|12345|{orders}"])
        if "funnel_events" in sql:
            return SqlResult(ok=True, rows=[f"2026-10-02|{activity}"])
        return SqlResult(ok=True, rows=[])

    monkeypatch.setattr(vendor, "run_sql_script", run)
    result = vendor.compute_vendor_analytics(VENDOR, 7)
    assert result.cart_activity_events_by_day == [activity]
    assert result.views_by_day == [activity]  # legacy event-count value retained
    assert result.order_activity_ratio.orders_total == orders
    assert result.order_activity_ratio.cart_activity_events_total == activity
    assert result.order_activity_ratio.orders_per_100_cart_activity_events == ratio
    assert result.conversion_hint.orders_total == orders
    assert result.conversion_hint.views_total == activity
    assert result.conversion_hint.conversion_pct == (ratio if ratio is not None else 0.0)
    assert result.sales_ngwee_by_day == [12345]  # money calculation unchanged
    payload = result.model_dump()
    assert payload["order_activity_ratio"]["orders_per_100_cart_activity_events"] == ratio
    activity_sql = next(sql for sql in queries if "funnel_events" in sql)
    assert "SELECT DISTINCT fe.id" in activity_sql  # duplicate listing lines aren't events
    assert "fe.stage IN ('cart_add', 'checkout_start')" in activity_sql
    assert f"vendor_id = '{VENDOR}'::uuid" in activity_sql
    assert "JOIN vl ON vl.id::text = line ->> 'listing_id'" in activity_sql


def test_legacy_fields_are_deprecated_in_schema() -> None:
    schema = vendor.VendorAnalyticsResponse.model_json_schema()
    assert schema["properties"]["views_by_day"]["deprecated"] is True
    assert schema["properties"]["conversion_hint"]["deprecated"] is True
    hint = vendor.ConversionHint.model_json_schema()["properties"]
    assert hint["views_total"]["deprecated"] is True
    assert hint["conversion_pct"]["deprecated"] is True


def test_query_failure_is_not_a_zero_activity_report(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_sql: str) -> SqlResult:
        return SqlResult(ok=False, rows=[], error="synthetic failure")

    monkeypatch.setattr(vendor, "run_sql_script", fail)
    with pytest.raises(AppError):
        vendor.compute_vendor_analytics(VENDOR, 7)


def test_vendor_scope_validation_precedes_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    def never(_sql: str) -> SqlResult:
        pytest.fail("invalid vendor must not query")

    monkeypatch.setattr(vendor, "run_sql_script", never)
    with pytest.raises(AppError):
        vendor.compute_vendor_analytics("not-a-vendor-uuid", 7)
