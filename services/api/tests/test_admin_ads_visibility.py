"""Ads visibility rules: blocked/removed targets, suspended advertisers, expired
merch slots and remove-with-reason — plus authz on the new ads routes."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from app.routers.admin_merch import resolve_slots_for_display
from fastapi.testclient import TestClient
from tests import test_home_feed as _base
from tests.test_home_feed import (
    ADMIN_ID,
    CUSTOMER_ID,
    NOW,
    FakeClient,
    _feed_client,
    _login,
    _page,
    _placement,
    _section,
)

# Reuse the home-feed fakes/fixtures (service client, TestClient, trending stub).
fake = _base.fake
http = _base.http
_no_trending = _base._no_trending

LISTING = "aaaaaaaa-0000-4000-8000-000000000001"
EVENT = "aaaaaaaa-0000-4000-8000-000000000002"
VENDOR = "bbbbbbbb-0000-4000-8000-000000000001"


def _catalog(client: FakeClient, *, listing: str = "active", vendor: str = "active") -> None:
    client.table("vendors").rows = [
        {"id": VENDOR, "status": vendor, "display_name": "Shop", "slug": "shop"}
    ]
    client.table("vendor_listings").rows = [
        {"id": LISTING, "status": listing, "vendor_id": VENDOR, "title_override": "Phone"}
    ]
    client.table("events").rows = [
        {
            "id": EVENT,
            "status": "published",
            "organiser_vendor_id": VENDOR,
            "title": "Gig",
            "slug": "gig",
        }
    ]


def _ads_page(client: FakeClient) -> Any:
    return _page(client, page_size=8)


def _targeted_client(**catalog: str) -> FakeClient:
    client = _feed_client(
        [_section("ad1", "ad_slot", 1)],
        [
            _placement("ad-listing", target_kind="listing", target_id=LISTING),
            _placement(
                "slide-event",
                placement_type="carousel_slide",
                target_kind="event",
                target_id=EVENT,
            ),
        ],
    )
    _catalog(client, **catalog)
    return client


def test_targeted_ads_serve_while_target_is_visible() -> None:
    page = _ads_page(_targeted_client())
    assert [s.ad.placement_id for s in page.sections if s.ad] == ["ad-listing"]
    assert [slide.placement_id for slide in page.carousel] == ["slide-event"]
    assert all(slide.sponsored for slide in page.carousel)


@pytest.mark.parametrize("listing_status", ["paused", "removed", "draft"])
def test_active_placement_with_hidden_or_removed_target_never_serves(listing_status: str) -> None:
    page = _ads_page(_targeted_client(listing=listing_status))
    assert [s.ad for s in page.sections if s.ad] == []


def test_suspended_vendor_hides_every_ad_pointing_at_its_catalog() -> None:
    page = _ads_page(_targeted_client(vendor="suspended"))
    assert [s.ad for s in page.sections if s.ad] == []
    assert page.carousel == []


def test_suspended_vendor_advertiser_is_not_served() -> None:
    client = _feed_client(
        [_section("ad1", "ad_slot", 1)],
        [_placement("ad-v", advertiser_kind="vendor", advertiser_vendor_id=VENDOR)],
    )
    _catalog(client, vendor="suspended")
    assert [s.ad for s in _ads_page(client).sections if s.ad] == []


def test_expired_and_paused_placements_never_serve_even_with_visible_target() -> None:
    client = _feed_client(
        [_section("ad1", "ad_slot", 1)],
        [
            _placement(
                "ad-expired",
                target_kind="listing",
                target_id=LISTING,
                ends_at=(NOW - timedelta(seconds=1)).isoformat(),
            ),
            _placement("ad-paused", status="paused", target_kind="listing", target_id=LISTING),
        ],
    )
    _catalog(client)
    assert [s.ad for s in _ads_page(client).sections if s.ad] == []


# ---------------------------------------------------------------------------
# Merch slots: expired / paused never render as a fallback
# ---------------------------------------------------------------------------


def _slot(slot_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": slot_id,
        "slot_key": "hero",
        "variant_key": "carousel",
        "payload": {},
        "schedule_from": None,
        "schedule_to": None,
        "position": 0,
        "active": True,
        **extra,
    }


def test_expired_merch_slot_is_not_used_as_fallback() -> None:
    expired = _slot(
        "11111111-1111-4111-8111-000000000001",
        schedule_from=(NOW - timedelta(days=3)).isoformat(),
        schedule_to=(NOW - timedelta(days=1)).isoformat(),
    )
    paused = _slot("11111111-1111-4111-8111-000000000002", active=False)
    assert resolve_slots_for_display([expired, paused], now=NOW) == []


def test_paused_default_slot_is_not_used_as_fallback() -> None:
    default_off = _slot(
        "11111111-1111-4111-8111-000000000003", active=False, payload={"is_default": True}
    )
    assert resolve_slots_for_display([default_off], now=NOW) == []


# ---------------------------------------------------------------------------
# Admin HTTP: target validation, remove-with-reason, authz
# ---------------------------------------------------------------------------


def _create_body(**extra: Any) -> dict[str, Any]:
    return {
        "advertiser_kind": "external",
        "advertiser_name": "Acme Ltd",
        "placement_type": "feed_slot",
        "image_public_id": "ads/acme",
        "headline": "Acme sale",
        "cta_href": "/l/" + LISTING,
        "starts_at": (NOW - timedelta(days=1)).isoformat(),
        "ends_at": (NOW + timedelta(days=400)).isoformat(),
        **extra,
    }


def test_admin_cannot_target_a_blocked_listing(
    http: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _catalog(fake, listing="removed")
    headers = _login(monkeypatch, ADMIN_ID, frozenset({"admin"}))
    response = http.post(
        "/admin/ads/placements",
        headers=headers,
        json=_create_body(target_kind="listing", target_id=LISTING),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ad_target_not_visible"


def test_admin_targets_listing_and_list_reports_suppression(
    http: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _catalog(fake)
    headers = _login(monkeypatch, ADMIN_ID, frozenset({"admin"}))
    created = http.post(
        "/admin/ads/placements",
        headers=headers,
        json=_create_body(target_kind="listing", target_id=LISTING),
    )
    assert created.status_code == 201, created.text
    assert created.json()["target_kind"] == "listing"
    fake.table("vendors").rows[0]["status"] = "suspended"
    listed = http.get("/admin/ads/placements", headers=headers).json()
    assert listed[0]["target_visible"] is False

    targets = http.get("/admin/ads/targets?kind=listing&q=pho", headers=headers)
    assert targets.status_code == 200
    assert targets.json()[0]["href"] == f"/l/{LISTING}"
    assert targets.json()[0]["visible"] is False
    assert http.get("/admin/ads/targets?kind=orders", headers=headers).status_code == 422


def test_removing_a_placement_requires_a_reason(
    http: TestClient, fake: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _login(monkeypatch, ADMIN_ID, frozenset({"admin"}))
    created = http.post("/admin/ads/placements", headers=headers, json=_create_body())
    pid = created.json()["id"]
    http.post(
        f"/admin/ads/placements/{pid}/transition", headers=headers, json={"to_status": "scheduled"}
    )
    no_reason = http.post(
        f"/admin/ads/placements/{pid}/transition", headers=headers, json={"to_status": "ended"}
    )
    assert no_reason.status_code == 422
    ended = http.post(
        f"/admin/ads/placements/{pid}/transition",
        headers=headers,
        json={"to_status": "ended", "reason": "Advertiser withdrew"},
    )
    assert ended.status_code == 200 and ended.json()["status"] == "ended"


def test_ad_target_picker_refuses_anon_customer_and_unrelated_operator(
    http: TestClient, monkeypatch: pytest.MonkeyPatch, fake: FakeClient
) -> None:
    path = "/admin/ads/targets?kind=listing"
    assert http.get(path).status_code == 401
    assert (
        http.get(
            path, headers=_login(monkeypatch, CUSTOMER_ID, frozenset({"customer"}))
        ).status_code
        == 403
    )
    fake.table("admin_roles").rows = [{"key": "rbac_finance", "permissions": ["finance.read"]}]
    operator = _login(monkeypatch, CUSTOMER_ID, frozenset({"rbac_finance"}))
    assert http.get(path, headers=operator).status_code == 403
    fake.table("admin_roles").rows = [{"key": "rbac_ads", "permissions": ["ads.manage"]}]
    ads_operator = _login(monkeypatch, CUSTOMER_ID, frozenset({"rbac_ads"}))
    assert http.get(path, headers=ads_operator).status_code == 200
