"""Deterministic staging-only synthetic marketplace contract (STG-SEED-04).

All identifiers use the reserved ``stg-rv-20260719`` prefix. Nothing here may
reference production hosts, project refs, or consumer email domains.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, fields
from typing import Any, Final, Literal

from app.core.env_guards import (
    PROD_API_HOST,
    PROD_SUPABASE_PROJECT_REF,
    STAGING_SUPABASE_PROJECT_REF,
    StagingIsolationError,
    assert_staging_api_host_isolated,
    assert_staging_project_target,
    assert_staging_supabase_isolated,
    extract_supabase_project_ref,
)

# Synthetic prefix reserved in staging-test-data-register.md
SEED_PREFIX: Final = "stg-rv-20260719"

# Cloudinary public_id prefix for synthetic listing media. Distinct from the
# legacy demo seed prefix (``demo/``). Public discovery excludes both via
# ``app.services.listings.demo.is_non_genuine_public_id``.
SYNTHETIC_IMAGE_PREFIX: Final = f"staging-synthetic/{SEED_PREFIX}"

PersonaKey = Literal[
    "CUSTOMER_A",
    "CUSTOMER_B",
    "APPROVED_VENDOR_A",
    "APPROVED_VENDOR_B",
    "PENDING_VENDOR",
    "BUSINESS_BUYER",
    "VENDOR_UNVERIFIED",
    "ADMIN_UNAUTHORIZED",
    "ADMIN_KYC_REVIEWER",
]

ProductKey = Literal["PRODUCT_A", "PRODUCT_B", "PRODUCT_C", "PRODUCT_D"]

VENDOR_STATUSES = frozenset({"draft", "pending_kyc", "active", "suspended"})
VALID_KYC_TIERS = frozenset({1, 2, 3})
KYC_RECORD_STATUSES = frozenset(
    {"submitted", "under_review", "approved", "rejected", "suspended", "revoked"}
)
PRODUCT_STATUSES = frozenset({"pending_moderation", "active", "merged"})
LISTING_STATUSES = frozenset({"draft", "active", "paused", "removed"})
LISTING_CONDITIONS = frozenset({"new", "refurbished"})
STOCK_MODES = frozenset({"tracked", "always_available"})

FORBIDDEN_SUBSTRINGS = (
    PROD_SUPABASE_PROJECT_REF,
    PROD_API_HOST,
)


@dataclass(frozen=True, slots=True)
class PersonaFixture:
    key: PersonaKey
    role: str
    handle: str
    email: str
    phone: str
    user_id: str
    user_role: str
    vendor_id: str | None = None
    slug: str | None = None
    vendor_status: str | None = None
    kyc_tier: int | None = None
    business_buyer_id: str | None = None
    business_legal_name: str | None = None
    business_registration_no: str | None = None


@dataclass(frozen=True, slots=True)
class ListingFixture:
    listing_id: str
    vendor_key: Literal["APPROVED_VENDOR_A", "APPROVED_VENDOR_B"]
    sku: str
    price_ngwee: int
    stock_qty: int
    wholesale: bool
    moq: int
    returnable: bool
    listing_status: str
    location_stock_qty: int | None = None


@dataclass(frozen=True, slots=True)
class ProductFixture:
    key: ProductKey
    category_id: str
    product_id: str
    product_name: str
    product_slug: str
    product_alias: str
    product_status: str
    listings: tuple[ListingFixture, ...]
    image_public_id: str


@dataclass(frozen=True, slots=True)
class KycFixture:
    id: str
    vendor_key: Literal["PENDING_VENDOR", "APPROVED_VENDOR_A", "APPROVED_VENDOR_B"]
    tier: int
    status: str
    reviewed_by: str | None = None
    decision_reason: str | None = None


@dataclass(frozen=True, slots=True)
class VendorLocationFixture:
    location_id: str
    vendor_key: Literal["APPROVED_VENDOR_A", "APPROVED_VENDOR_B"]
    lat: float
    lng: float
    landmark: str
    label: str
    area: str
    city: str
    province: str
    phone_e164: str
    is_primary: bool = True


PERSONAS: tuple[PersonaFixture, ...] = (
    PersonaFixture(
        key="CUSTOMER_A",
        role="customer_buyer",
        handle=f"{SEED_PREFIX}-cust-01",
        email=f"{SEED_PREFIX}-cust-01@staging.vergeo5.test",
        phone="+260970000001",
        user_id="a1000000-0000-4000-8000-000000000001",
        user_role="customer",
    ),
    PersonaFixture(
        key="CUSTOMER_B",
        role="customer_buyer_b",
        handle=f"{SEED_PREFIX}-cust-02",
        email=f"{SEED_PREFIX}-cust-02@staging.vergeo5.test",
        phone="+260970000007",
        user_id="a1000000-0000-4000-8000-000000000007",
        user_role="customer",
    ),
    PersonaFixture(
        key="VENDOR_UNVERIFIED",
        role="vendor_unverified",
        handle=f"{SEED_PREFIX}-vend-unv",
        email=f"{SEED_PREFIX}-vend-unv@staging.vergeo5.test",
        phone="+260970000002",
        user_id="a1000000-0000-4000-8000-000000000002",
        vendor_id="b1000000-0000-4000-8000-000000000002",
        slug=f"{SEED_PREFIX}-vend-unv",
        user_role="vendor",
        vendor_status="draft",
        kyc_tier=None,
    ),
    PersonaFixture(
        key="PENDING_VENDOR",
        role="vendor_kyc_submitted",
        handle=f"{SEED_PREFIX}-vend-sub",
        email=f"{SEED_PREFIX}-vend-sub@staging.vergeo5.test",
        phone="+260970000003",
        user_id="a1000000-0000-4000-8000-000000000003",
        vendor_id="b1000000-0000-4000-8000-000000000003",
        slug=f"{SEED_PREFIX}-vend-sub",
        user_role="vendor",
        vendor_status="pending_kyc",
        kyc_tier=None,
    ),
    PersonaFixture(
        key="APPROVED_VENDOR_A",
        role="vendor_approved_a",
        handle=f"{SEED_PREFIX}-vend-apr",
        email=f"{SEED_PREFIX}-vend-apr@staging.vergeo5.test",
        phone="+260970000004",
        user_id="a1000000-0000-4000-8000-000000000004",
        vendor_id="b1000000-0000-4000-8000-000000000004",
        slug=f"{SEED_PREFIX}-vend-apr",
        user_role="vendor",
        vendor_status="active",
        kyc_tier=1,
    ),
    PersonaFixture(
        key="APPROVED_VENDOR_B",
        role="vendor_approved_b",
        handle=f"{SEED_PREFIX}-vend-apr-b",
        email=f"{SEED_PREFIX}-vend-apr-b@staging.vergeo5.test",
        phone="+260970000008",
        user_id="a1000000-0000-4000-8000-000000000008",
        vendor_id="b1000000-0000-4000-8000-000000000005",
        slug=f"{SEED_PREFIX}-vend-apr-b",
        user_role="vendor",
        vendor_status="active",
        kyc_tier=1,
    ),
    PersonaFixture(
        key="BUSINESS_BUYER",
        role="business_buyer",
        handle=f"{SEED_PREFIX}-biz-buy",
        email=f"{SEED_PREFIX}-biz-buy@staging.vergeo5.test",
        phone="+260970000009",
        user_id="a1000000-0000-4000-8000-000000000009",
        user_role="customer",
        business_buyer_id="13000000-0000-4000-8000-000000000001",
        business_legal_name=f"{SEED_PREFIX} synthetic PACRA buyer",
        business_registration_no=f"{SEED_PREFIX}-PACRA-0001",
    ),
    PersonaFixture(
        key="ADMIN_UNAUTHORIZED",
        role="admin_unauthorized",
        handle=f"{SEED_PREFIX}-adm-bad",
        email=f"{SEED_PREFIX}-adm-bad@staging.vergeo5.test",
        phone="+260970000005",
        user_id="a1000000-0000-4000-8000-000000000005",
        user_role="customer",
    ),
    PersonaFixture(
        key="ADMIN_KYC_REVIEWER",
        role="admin_kyc_reviewer",
        handle=f"{SEED_PREFIX}-adm-kyc",
        email=f"{SEED_PREFIX}-adm-kyc@staging.vergeo5.test",
        phone="+260970000006",
        user_id="a1000000-0000-4000-8000-000000000006",
        user_role="admin",
    ),
)

KYC_FIXTURES: tuple[KycFixture, ...] = (
    KycFixture(
        id="c1000000-0000-4000-8000-000000000003",
        vendor_key="PENDING_VENDOR",
        tier=1,
        status="submitted",
    ),
    KycFixture(
        id="c1000000-0000-4000-8000-000000000004",
        vendor_key="APPROVED_VENDOR_A",
        tier=1,
        status="approved",
        reviewed_by="a1000000-0000-4000-8000-000000000006",
        decision_reason="synthetic staging approval",
    ),
    KycFixture(
        id="c1000000-0000-4000-8000-000000000005",
        vendor_key="APPROVED_VENDOR_B",
        tier=1,
        status="approved",
        reviewed_by="a1000000-0000-4000-8000-000000000006",
        decision_reason="synthetic staging approval",
    ),
)

CATEGORY_FIXTURE: dict[str, Any] = {
    "category_id": "d1000000-0000-4000-8000-000000000001",
    "category_name": "Synthetic staging catalogue",
    "category_slug": f"{SEED_PREFIX}-catalogue",
    "category_path": f"/{SEED_PREFIX}-catalogue",
    "commission_key": "default",
}

VENDOR_LOCATIONS: tuple[VendorLocationFixture, ...] = (
    VendorLocationFixture(
        location_id="12000000-0000-4000-8000-000000000004",
        vendor_key="APPROVED_VENDOR_A",
        lat=-15.4167,
        lng=28.2833,
        landmark=f"Opposite {SEED_PREFIX} vendor A pickup gate",
        label="Main shop",
        area="Lusaka",
        city="Lusaka",
        province="Lusaka",
        phone_e164="+260970000004",
        is_primary=True,
    ),
    VendorLocationFixture(
        location_id="12000000-0000-4000-8000-000000000005",
        vendor_key="APPROVED_VENDOR_B",
        lat=-15.3920,
        lng=28.3220,
        landmark=f"Near {SEED_PREFIX} vendor B collection point",
        label="Kabwata stall",
        area="Kabwata",
        city="Lusaka",
        province="Lusaka",
        phone_e164="+260970000008",
        is_primary=True,
    ),
)

def persona_by_key(key: PersonaKey | str) -> PersonaFixture:
    for persona in PERSONAS:
        if persona.key == key:
            return persona
    raise KeyError(f"unknown persona key: {key}")


CATALOG_FIXTURES: tuple[ProductFixture, ...] = (
    ProductFixture(
        key="PRODUCT_A",
        category_id=CATEGORY_FIXTURE["category_id"],
        product_id="e1000000-0000-4000-8000-000000000001",
        product_name="Synthetic multiseller product A",
        product_slug=f"{SEED_PREFIX}-product-a",
        product_alias=f"{SEED_PREFIX}-product-a",
        product_status="active",
        image_public_id=f"{SYNTHETIC_IMAGE_PREFIX}/product-a",
        listings=(
            ListingFixture(
                listing_id="f1000000-0000-4000-8000-000000000001",
                vendor_key="APPROVED_VENDOR_A",
                sku=f"{SEED_PREFIX}-list-prd-a-vend-a",
                price_ngwee=12_500,
                stock_qty=25,
                wholesale=False,
                moq=1,
                returnable=False,
                listing_status="active",
                location_stock_qty=25,
            ),
            ListingFixture(
                listing_id="f1000000-0000-4000-8000-000000000002",
                vendor_key="APPROVED_VENDOR_B",
                sku=f"{SEED_PREFIX}-list-prd-a-vend-b",
                price_ngwee=14_900,
                stock_qty=18,
                wholesale=False,
                moq=1,
                returnable=False,
                listing_status="active",
                location_stock_qty=18,
            ),
        ),
    ),
    ProductFixture(
        key="PRODUCT_B",
        category_id=CATEGORY_FIXTURE["category_id"],
        product_id="e1000000-0000-4000-8000-000000000002",
        product_name="Synthetic standard retail product B",
        product_slug=f"{SEED_PREFIX}-product-b",
        product_alias=f"{SEED_PREFIX}-product-b",
        product_status="active",
        image_public_id=f"{SYNTHETIC_IMAGE_PREFIX}/product-b",
        listings=(
            ListingFixture(
                listing_id="f1000000-0000-4000-8000-000000000003",
                vendor_key="APPROVED_VENDOR_A",
                sku=f"{SEED_PREFIX}-list-prd-b",
                price_ngwee=8_750,
                stock_qty=40,
                wholesale=False,
                moq=1,
                returnable=False,
                listing_status="active",
                location_stock_qty=40,
            ),
        ),
    ),
    ProductFixture(
        key="PRODUCT_C",
        category_id=CATEGORY_FIXTURE["category_id"],
        product_id="e1000000-0000-4000-8000-000000000003",
        product_name="Synthetic out-of-stock product C",
        product_slug=f"{SEED_PREFIX}-product-c",
        product_alias=f"{SEED_PREFIX}-product-c",
        product_status="active",
        image_public_id=f"{SYNTHETIC_IMAGE_PREFIX}/product-c",
        listings=(
            ListingFixture(
                listing_id="f1000000-0000-4000-8000-000000000004",
                vendor_key="APPROVED_VENDOR_A",
                sku=f"{SEED_PREFIX}-list-prd-c-oos",
                price_ngwee=5_500,
                stock_qty=0,
                wholesale=False,
                moq=1,
                returnable=False,
                listing_status="active",
                location_stock_qty=0,
            ),
        ),
    ),
    ProductFixture(
        key="PRODUCT_D",
        category_id=CATEGORY_FIXTURE["category_id"],
        product_id="e1000000-0000-4000-8000-000000000004",
        product_name="Synthetic wholesale-only product D",
        product_slug=f"{SEED_PREFIX}-product-d",
        product_alias=f"{SEED_PREFIX}-product-d",
        product_status="active",
        image_public_id=f"{SYNTHETIC_IMAGE_PREFIX}/product-d",
        listings=(
            ListingFixture(
                listing_id="f1000000-0000-4000-8000-000000000005",
                vendor_key="APPROVED_VENDOR_B",
                sku=f"{SEED_PREFIX}-list-prd-d-wholesale",
                price_ngwee=45_000,
                stock_qty=120,
                wholesale=True,
                moq=10,
                returnable=False,
                listing_status="active",
                location_stock_qty=120,
            ),
        ),
    ),
)

def product_fixture(key: ProductKey | str) -> ProductFixture:
    for product in CATALOG_FIXTURES:
        if product.key == key:
            return product
    raise KeyError(f"unknown product key: {key}")


# Back-compat alias for older tests referencing a single catalogue fixture.
CATALOG_FIXTURE: dict[str, Any] = {
    **CATEGORY_FIXTURE,
    "product_id": CATALOG_FIXTURES[0].product_id,
    "product_name": CATALOG_FIXTURES[0].product_name,
    "product_slug": CATALOG_FIXTURES[0].product_slug,
    "product_alias": CATALOG_FIXTURES[0].product_alias,
    "product_status": CATALOG_FIXTURES[0].product_status,
    "listing_id": CATALOG_FIXTURES[0].listings[0].listing_id,
    "vendor_id": persona_by_key("APPROVED_VENDOR_A").vendor_id,
    "listing_sku": CATALOG_FIXTURES[0].listings[0].sku,
    "price_ngwee": CATALOG_FIXTURES[0].listings[0].price_ngwee,
    "condition": "new",
    "stock_mode": "tracked",
    "stock_qty": CATALOG_FIXTURES[0].listings[0].stock_qty,
    "wholesale": False,
    "moq": 1,
    "returnable": False,
    "listing_status": "active",
}

# Legacy FIXTURES list shape for scripts that still iterate dict rows.
FIXTURES: list[dict[str, Any]] = [
    {
        "role": p.role,
        "handle": p.handle,
        "email": p.email,
        "phone": p.phone,
        "user_id": p.user_id,
        "user_role": p.user_role,
        **(
            {
                "vendor_id": p.vendor_id,
                "slug": p.slug,
                "vendor_status": p.vendor_status,
                "kyc_tier": p.kyc_tier,
            }
            if p.vendor_id
            else {}
        ),
    }
    for p in PERSONAS
    if p.key
    not in {"BUSINESS_BUYER"}  # business buyer is a profile + business_buyers row
]

KYC_FIXTURES_LEGACY: list[dict[str, Any]] = [
    {
        "id": k.id,
        "vendor_id": persona_by_key(k.vendor_key).vendor_id,
        "tier": k.tier,
        "status": k.status,
        **({"reviewed_by": k.reviewed_by} if k.reviewed_by else {}),
        **({"decision_reason": k.decision_reason} if k.decision_reason else {}),
    }
    for k in KYC_FIXTURES
]


def all_synthetic_user_ids() -> frozenset[str]:
    return frozenset(p.user_id for p in PERSONAS)


def all_synthetic_vendor_ids() -> frozenset[str]:
    return frozenset(
        p.vendor_id for p in PERSONAS if p.vendor_id is not None
    )


def all_synthetic_listing_ids() -> frozenset[str]:
    ids: set[str] = set()
    for product in CATALOG_FIXTURES:
        for listing in product.listings:
            ids.add(listing.listing_id)
    return frozenset(ids)


def all_synthetic_location_ids() -> frozenset[str]:
    return frozenset(loc.location_id for loc in VENDOR_LOCATIONS)


def all_contract_uuid_literals() -> frozenset[str]:
    """Every deterministic identifier destined for a PostgreSQL uuid column."""
    ids: set[str] = set()
    for persona in PERSONAS:
        ids.add(persona.user_id)
        if persona.vendor_id is not None:
            ids.add(persona.vendor_id)
        if persona.business_buyer_id is not None:
            ids.add(persona.business_buyer_id)
    for record in KYC_FIXTURES:
        ids.add(record.id)
        if record.reviewed_by is not None:
            ids.add(record.reviewed_by)
    ids.add(str(CATEGORY_FIXTURE["category_id"]))
    for product in CATALOG_FIXTURES:
        ids.add(product.category_id)
        ids.add(product.product_id)
        for listing in product.listings:
            ids.add(listing.listing_id)
    ids.update(all_synthetic_location_ids())
    from app.staging.seed_sql import IMAGE_IDS

    ids.update(IMAGE_IDS.values())
    return frozenset(ids)


def _assert_valid_uuid_literals() -> None:
    for value in sorted(all_contract_uuid_literals()):
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise StagingIsolationError(
                f"synthetic fixture UUID is not Postgres-compatible: {value}"
            ) from exc


def _assert_no_production_markers(payload: str) -> None:
    lower = payload.lower()
    for marker in FORBIDDEN_SUBSTRINGS:
        if marker.lower() in lower:
            raise StagingIsolationError(
                f"synthetic seed payload must not contain production marker: {marker}"
            )
    if re.search(r"@(gmail|yahoo|outlook|hotmail)\.", lower):
        raise StagingIsolationError("synthetic seed must not use consumer email domains")


def assert_contract_valid() -> None:
    """Validate fixture purity and schema-aligned field values."""
    _assert_valid_uuid_literals()
    vendor_ids = all_synthetic_vendor_ids()
    user_ids = all_synthetic_user_ids()

    for persona in PERSONAS:
        blob = " ".join(str(getattr(persona, f.name)) for f in fields(persona))
        _assert_no_production_markers(blob)
        if SEED_PREFIX not in persona.handle:
            raise StagingIsolationError(
                f"fixture handle missing seed prefix: {persona.handle}"
            )
        if persona.vendor_id is not None:
            status = persona.vendor_status
            if status not in VENDOR_STATUSES:
                raise StagingIsolationError(f"invalid synthetic vendor status: {status}")
            tier = persona.kyc_tier
            if tier is not None and (not isinstance(tier, int) or tier not in VALID_KYC_TIERS):
                raise StagingIsolationError(f"invalid synthetic vendor KYC tier: {tier}")

    for record in KYC_FIXTURES:
        vendor_id = persona_by_key(record.vendor_key).vendor_id
        if vendor_id not in vendor_ids:
            raise StagingIsolationError("synthetic KYC record references an unknown vendor")
        if record.tier not in VALID_KYC_TIERS:
            raise StagingIsolationError(f"invalid synthetic KYC record tier: {record.tier}")
        if record.status not in KYC_RECORD_STATUSES:
            raise StagingIsolationError(f"invalid synthetic KYC record status: {record.status}")
        if record.status == "approved":
            if record.reviewed_by not in user_ids or not record.decision_reason:
                raise StagingIsolationError(
                    "approved synthetic KYC record requires a seeded reviewer and reason"
                )

    catalog_blob = " ".join(str(v) for v in CATEGORY_FIXTURE.values())
    _assert_no_production_markers(catalog_blob)
    for field in ("category_slug", "category_path"):
        if SEED_PREFIX not in str(CATEGORY_FIXTURE[field]):
            raise StagingIsolationError(
                f"synthetic catalogue fixture field missing seed prefix: {field}"
            )

    for product in CATALOG_FIXTURES:
        blob = " ".join(
            str(v)
            for v in (
                product.product_slug,
                product.product_alias,
                product.image_public_id,
                *[listing.sku for listing in product.listings],
            )
        )
        _assert_no_production_markers(blob)
        if product.product_status not in PRODUCT_STATUSES:
            raise StagingIsolationError("invalid synthetic product status")
        for listing in product.listings:
            vendor_id = persona_by_key(listing.vendor_key).vendor_id
            if vendor_id not in vendor_ids:
                raise StagingIsolationError("listing references unknown vendor")
            if listing.listing_status not in LISTING_STATUSES:
                raise StagingIsolationError("invalid listing status")
            if listing.price_ngwee < 1:
                raise StagingIsolationError("price_ngwee must be a positive integer")
            if listing.stock_qty < 0:
                raise StagingIsolationError("stock_qty must be non-negative")
            if product.key == "PRODUCT_C" and listing.stock_qty != 0:
                raise StagingIsolationError("product C must have zero stock")
            if product.key == "PRODUCT_D" and not listing.wholesale:
                raise StagingIsolationError("product D must be wholesale-only")
            if product.key != "PRODUCT_D" and listing.wholesale:
                raise StagingIsolationError("retail products must not be wholesale")
            if listing.location_stock_qty is not None and listing.location_stock_qty < 0:
                raise StagingIsolationError("location stock must be non-negative")

    product_a = product_fixture("PRODUCT_A")
    if len(product_a.listings) < 2:
        raise StagingIsolationError("product A requires multiseller listings")


def resolve_project_ref(
    *,
    supabase_url: str,
    db_url: str,
    staging_project_id: str,
) -> str | None:
    if supabase_url:
        ref = extract_supabase_project_ref(supabase_url)
        if ref:
            return ref
    if db_url:
        from urllib.parse import urlparse

        host = urlparse(db_url).hostname or ""
        match = re.search(r"([a-z0-9]{20})\.supabase\.", host)
        if match:
            return match.group(1)
        match = re.search(r"postgres\.([a-z0-9]{20})", host)
        if match:
            return match.group(1)
    staging_id = staging_project_id.strip().lower()
    return staging_id or None


def guard_seed_targets(
    *,
    supabase_url: str,
    db_url: str,
    api_host: str,
    staging_project_id: str,
    require_exact_project: bool,
) -> None:
    ref = resolve_project_ref(
        supabase_url=supabase_url,
        db_url=db_url,
        staging_project_id=staging_project_id,
    )
    if ref:
        assert_staging_supabase_isolated(f"https://{ref}.supabase.co", env="staging")
        if require_exact_project:
            assert_staging_project_target(ref, require_exact=True)
    elif supabase_url:
        assert_staging_supabase_isolated(supabase_url, env="staging")

    staging_id = staging_project_id.strip().lower()
    if staging_id == PROD_SUPABASE_PROJECT_REF:
        raise StagingIsolationError(
            "STAGING_SUPABASE_PROJECT_ID equals production project ref"
        )
    if require_exact_project:
        assert_staging_project_target(
            staging_id or ref,
            require_exact=True,
        )
    if api_host:
        assert_staging_api_host_isolated(api_host, env="staging")


__all__ = [
    "CATALOG_FIXTURE",
    "CATALOG_FIXTURES",
    "CATEGORY_FIXTURE",
    "FIXTURES",
    "KYC_FIXTURES",
    "KYC_FIXTURES_LEGACY",
    "PERSONAS",
    "SEED_PREFIX",
    "STAGING_SUPABASE_PROJECT_REF",
    "SYNTHETIC_IMAGE_PREFIX",
    "VENDOR_LOCATIONS",
    "all_contract_uuid_literals",
    "all_synthetic_listing_ids",
    "all_synthetic_location_ids",
    "all_synthetic_user_ids",
    "all_synthetic_vendor_ids",
    "assert_contract_valid",
    "guard_seed_targets",
    "persona_by_key",
    "product_fixture",
    "resolve_project_ref",
]
