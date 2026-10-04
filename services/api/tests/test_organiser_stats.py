"""Organiser sales rows preserve valid free-text tier names and existing totals."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from app.errors import AppError
from app.routers.organiser_stats import _load_sales_by_type
from app.routers.ticket_types import TicketTypeCreateRequest
from app.services.db import SqlResult, _render_row

EVENT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
TYPE_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.parametrize("name", ["VIP | Balcony", "VIP\nBalcony", 'VIP "Balcony"', "VIP — Ndola"])
def test_sales_preserve_valid_tier_names_and_counts(name: str) -> None:
    request = TicketTypeCreateRequest(kind="tier", name=name, price_ngwee=15000)
    row = {
        "ticket_type_id": TYPE_ID,
        "kind": request.kind,
        "name": request.name,
        "price_ngwee": request.price_ngwee,
        "sold": 3,
        "checked_in": 2,
        "revenue_ngwee": 45000,
    }
    # Exercise the same one-column text projection used by the DB adapter.
    result = SqlResult(ok=True, rows=[_render_row((json.dumps(row),))])
    with patch("app.routers.organiser_stats.run_sql_script", return_value=result):
        sales = _load_sales_by_type(EVENT_ID)

    assert [sale.model_dump() for sale in sales] == [row]


def test_free_rsvp_reports_zero_revenue_for_nominal_storage_price() -> None:
    row = {
        "ticket_type_id": TYPE_ID,
        "kind": "free_rsvp",
        "name": "Community | Guests",
        "price_ngwee": 0,
        "sold": 3,
        "checked_in": 2,
        "revenue_ngwee": 3,
    }
    result = SqlResult(ok=True, rows=[json.dumps(row)])
    with patch("app.routers.organiser_stats.run_sql_script", return_value=result):
        sales = _load_sales_by_type(EVENT_ID)

    assert [sale.model_dump() for sale in sales] == [{**row, "revenue_ngwee": 0}]


def test_empty_sales_remain_empty() -> None:
    with patch(
        "app.routers.organiser_stats.run_sql_script", return_value=SqlResult(ok=True, rows=[])
    ):
        assert _load_sales_by_type(EVENT_ID) == []


def test_failed_sales_query_is_not_reported_as_zero_sales() -> None:
    with patch(
        "app.routers.organiser_stats.run_sql_script",
        return_value=SqlResult(ok=False, rows=[], error="query failed"),
    ), pytest.raises(AppError) as error:
        _load_sales_by_type(EVENT_ID)

    assert error.value.code == "stats_query_failed"
