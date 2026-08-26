"""STG-SEED-04 — staging-synthetic media is a plane-scoped exception, not a hole.

Regression coverage for the ``fix/staging-synthetic-catalog-policy`` fix: the
canonical strict-E2E product ``stg-rv-20260719-product-a`` 404s on the direct PDP
route because ``build_product_detail`` reused the exact same "hide from public
discovery" predicate that legacy ``demo/`` media gets, and that predicate is
environment-unaware — it filters ``staging-synthetic/`` media identically on
every plane, including the one plane (staging) where that prefix is the *only*
thing that can legitimately carry it.

Policy under test:
  legacy demo/     staging -> excluded   |  production -> excluded
  staging-synthetic  staging -> ELIGIBLE |  production -> excluded  | unknown -> excluded

Every test in this file must fail against the pre-fix code (which ignores plane
entirely and always excludes staging-synthetic/) and pass against the fix.
"""

from __future__ import annotations

import pytest
from app.errors import AppError
from app.routers.products import ProductDetailResponse, build_product_detail
from app.services.listings.demo import (
    fetch_demo_listing_ids,
    is_non_genuine_public_id,
)

from tests.test_demo_exclusion import _Store

SYNTHETIC_LISTING_ID = "a1000000-0000-4000-8000-000000000001"
SYNTHETIC_VENDOR_ID = "b1000000-0000-4000-8000-000000000001"
SYNTHETIC_PRODUCT_ID = "e1000000-0000-4000-8000-000000000001"
SYNTHETIC_IMAGE_PUBLIC_ID = "staging-synthetic/stg-rv-20260719/product-a"


# ── 1-2. legacy demo/ — unconditional on every plane ────────────────────────


@pytest.mark.parametrize("env", ["staging", "production", "development", "", "banana"])
def test_legacy_demo_excluded_on_every_plane(env: str) -> None:
    assert is_non_genuine_public_id("demo/products/itel-a70", env=env) is True


# ── 3. staging-synthetic/ — eligible on staging ──────────────────────────────


def test_staging_synthetic_eligible_on_staging() -> None:
    assert is_non_genuine_public_id(SYNTHETIC_IMAGE_PUBLIC_ID, env="staging") is False


# ── 4. staging-synthetic/ — remains excluded in production ──────────────────


def test_staging_synthetic_excluded_in_production() -> None:
    assert is_non_genuine_public_id(SYNTHETIC_IMAGE_PUBLIC_ID, env="production") is True


# ── 5. unknown/missing plane fails closed ────────────────────────────────────


@pytest.mark.parametrize(
    "env",
    ["development", "", "unknown", "STAGING-TYPO", "prod", "  ", "stagin", "staging2"],
)
def test_staging_synthetic_fails_closed_on_unrecognized_plane(env: str) -> None:
    """Only the exact literal "staging" (case/whitespace-normalized — matching
    env_guards' own .strip().lower() convention) opens the exception. Anything
    else — including a near-miss typo or a value that merely contains "staging"
    as a substring — must keep the exclusion on."""
    assert is_non_genuine_public_id(SYNTHETIC_IMAGE_PUBLIC_ID, env=env) is True


def test_staging_synthetic_normalizes_case_and_whitespace_like_env_guards() -> None:
    """Matches env_guards' own .strip().lower() convention exactly — not a
    separate normalization rule."""
    assert is_non_genuine_public_id(SYNTHETIC_IMAGE_PUBLIC_ID, env="Staging ") is False
    assert is_non_genuine_public_id(SYNTHETIC_IMAGE_PUBLIC_ID, env=" STAGING") is False


def test_staging_synthetic_excluded_when_env_kwarg_omitted_and_process_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No caller-supplied env AND no process ENV var at all -> the module's own
    default ("development") applies -> still excluded. A missing deployment-plane
    variable must never accidentally behave as staging."""
    monkeypatch.delenv("ENV", raising=False)
    assert is_non_genuine_public_id(SYNTHETIC_IMAGE_PUBLIC_ID) is True


def test_staging_synthetic_reads_process_env_when_no_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no explicit env= kwarg, the process ENV var is the source of truth —
    proving the decision uses the canonical environment primitive, not some
    caller-supplied default that could be steered by request input."""
    monkeypatch.setenv("ENV", "staging")
    assert is_non_genuine_public_id(SYNTHETIC_IMAGE_PUBLIC_ID) is False

    monkeypatch.setenv("ENV", "production")
    assert is_non_genuine_public_id(SYNTHETIC_IMAGE_PUBLIC_ID) is True


# ── 6. ordinary media is untouched on every plane ────────────────────────────


@pytest.mark.parametrize("env", ["staging", "production", "development", None])
def test_ordinary_media_remains_genuine_everywhere(env: str | None) -> None:
    assert is_non_genuine_public_id("vergeo5/catalog/phone-a", env=env) is False


# ── caller coverage: the wrapper actually threads env through ───────────────


def test_fetch_demo_listing_ids_threads_env_through() -> None:
    store = _Store()
    store.listing_images = [
        {
            "listing_id": SYNTHETIC_LISTING_ID,
            "cloudinary_public_id": SYNTHETIC_IMAGE_PUBLIC_ID,
            "position": 1,
        }
    ]
    assert fetch_demo_listing_ids(store, [SYNTHETIC_LISTING_ID], env="staging") == set()
    assert fetch_demo_listing_ids(store, [SYNTHETIC_LISTING_ID], env="production") == {
        SYNTHETIC_LISTING_ID
    }
    # Default (no env kwarg) must not silently behave as staging.
    assert fetch_demo_listing_ids(store, [SYNTHETIC_LISTING_ID]) == {SYNTHETIC_LISTING_ID}


# ── behavioral regression at the parent filtering layer ──────────────────────


def _seed_synthetic_product(store: _Store) -> None:
    store.vendors = [
        {
            "id": SYNTHETIC_VENDOR_ID,
            "slug": "stg-rv-20260719-vend-apr",
            "display_name": "Synthetic approved vendor A",
            "status": "active",
            "preferred_badge": False,
            "kyc_tier": 1,
            "description": None,
            "logo_url": None,
            "cover_url": None,
            "whatsapp_msisdn": None,
            "created_at": "2026-07-13T10:51:42Z",
            "vendor_locations": [],
        }
    ]
    store.products = [
        {
            "id": SYNTHETIC_PRODUCT_ID,
            "slug": "stg-rv-20260719-product-a",
            "name": "Synthetic multiseller product A",
            "status": "active",
            "brand": None,
            "description": None,
            "spec": {},
            "category_id": "cat-electronics",
            "merged_into_id": None,
        }
    ]
    store.vendor_listings = [
        {
            "id": SYNTHETIC_LISTING_ID,
            "vendor_id": SYNTHETIC_VENDOR_ID,
            "product_id": SYNTHETIC_PRODUCT_ID,
            "title_override": None,
            "price_ngwee": 250_000,
            "condition": "new",
            "stock_mode": "tracked",
            "stock_qty": 25,
            "moq": 1,
            "wholesale": False,
            "status": "active",
            "created_at": "2026-07-13T10:51:42Z",
            "vendors": {
                "id": SYNTHETIC_VENDOR_ID,
                "slug": "stg-rv-20260719-vend-apr",
                "display_name": "Synthetic approved vendor A",
                "preferred_badge": False,
                "status": "active",
                "vendor_locations": [],
            },
        }
    ]
    store.listing_images = [
        {
            "listing_id": SYNTHETIC_LISTING_ID,
            "cloudinary_public_id": SYNTHETIC_IMAGE_PUBLIC_ID,
            "position": 1,
        }
    ]


def test_parent_filter_retains_synthetic_only_listing_on_staging() -> None:
    store = _Store()
    _seed_synthetic_product(store)
    excluded = fetch_demo_listing_ids(store, [SYNTHETIC_LISTING_ID], env="staging")
    assert SYNTHETIC_LISTING_ID not in excluded


def test_parent_filter_excludes_synthetic_only_listing_in_production() -> None:
    store = _Store()
    _seed_synthetic_product(store)
    excluded = fetch_demo_listing_ids(store, [SYNTHETIC_LISTING_ID], env="production")
    assert SYNTHETIC_LISTING_ID in excluded


# ── end-to-end: the exact bug — build_product_detail must not 404 on staging ─


def test_product_detail_does_not_404_on_staging_for_synthetic_only_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact reported defect: an active canonical product with an active
    listing whose ONLY image is staging-synthetic must not become
    product.not_found on the staging plane. Fails against pre-fix code (which
    always excludes staging-synthetic/, regardless of ENV) and passes after."""
    monkeypatch.setenv("ENV", "staging")
    store = _Store()
    _seed_synthetic_product(store)

    detail = build_product_detail(store, "stg-rv-20260719-product-a")

    assert isinstance(detail, ProductDetailResponse)
    assert detail.listing_count == 1
    assert {listing.id for listing in detail.listings} == {SYNTHETIC_LISTING_ID}


def test_product_detail_still_404s_on_production_for_synthetic_only_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense-in-depth: the same fixture shape, on the production plane, must
    still 404 exactly as it does today — production behavior is unchanged."""
    monkeypatch.setenv("ENV", "production")
    store = _Store()
    _seed_synthetic_product(store)

    with pytest.raises(AppError) as exc:
        build_product_detail(store, "stg-rv-20260719-product-a")
    assert exc.value.http_status == 404
    assert exc.value.code == "product.not_found"


def test_product_detail_404s_when_env_unset_for_synthetic_only_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed: with ENV entirely unset, synthetic-only inventory must not
    become visible — the safe default is production-like exclusion."""
    monkeypatch.delenv("ENV", raising=False)
    store = _Store()
    _seed_synthetic_product(store)

    with pytest.raises(AppError) as exc:
        build_product_detail(store, "stg-rv-20260719-product-a")
    assert exc.value.http_status == 404
    assert exc.value.code == "product.not_found"
