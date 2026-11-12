from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from tests.test_listing_manage import (
    LISTING_A_ID,
    FakeSupabaseClient,
    _auth_headers,
)
from tests.test_listing_manage import (
    fake_client as fake_client,
)
from tests.test_listing_manage import (
    manage_client as manage_client,
)


@pytest.mark.parametrize("sale_unit,step,minimum", [("kg", 250, 4), ("each", 1000, 1)])
def test_manage_rejects_changed_minimum_without_mutation(
    manage_client: TestClient,
    fake_client: FakeSupabaseClient,
    sale_unit: str,
    step: int,
    minimum: int,
) -> None:
    stored = fake_client.tables["vendor_listings"].rows[0]
    stored.update(sale_unit=sale_unit, unit_step_milli=step, min_steps=minimum)
    before = deepcopy(stored)
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}",
        headers=_auth_headers(),
        json={"min_steps": minimum + 1},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stock.authority_required"
    assert stored == before
