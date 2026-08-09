"""SQL builders for staging synthetic seed and scoped cleanup."""

from __future__ import annotations

from app.staging.synthetic_contract import (
    CATALOG_FIXTURES,
    CATEGORY_FIXTURE,
    KYC_FIXTURES,
    PERSONAS,
    SEED_PREFIX,
    VENDOR_LOCATIONS,
    persona_by_key,
)

IMAGE_IDS: dict[str, str] = {
    "f1000000-0000-4000-8000-000000000001": "11000000-0000-4000-8000-000000000001",
    "f1000000-0000-4000-8000-000000000002": "11000000-0000-4000-8000-000000000002",
    "f1000000-0000-4000-8000-000000000003": "11000000-0000-4000-8000-000000000003",
    "f1000000-0000-4000-8000-000000000004": "11000000-0000-4000-8000-000000000004",
    "f1000000-0000-4000-8000-000000000005": "11000000-0000-4000-8000-000000000005",
}


def _auth_users_sql() -> str:
    parts = ["BEGIN;"]
    for persona in PERSONAS:
        parts.append(
            f"""
INSERT INTO auth.users (
  instance_id, id, aud, role, email, phone, encrypted_password,
  email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) VALUES (
  '00000000-0000-0000-0000-000000000000', '{persona.user_id}', 'authenticated',
  'authenticated', '{persona.email}', '{persona.phone}', 'staging-hash-not-real',
  timezone('utc', now()), '{{}}'::jsonb, '{{}}'::jsonb,
  timezone('utc', now()), timezone('utc', now())
) ON CONFLICT (id) DO NOTHING;
"""
        )
    parts.append("COMMIT;")
    return "\n".join(parts)


def build_seed_sql() -> str:
    """Build idempotent SQL from fixed synthetic constants (no user input)."""
    sql_parts = [
        "BEGIN;",
        "SET LOCAL role service_role;",
        'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';',
    ]

    for persona in PERSONAS:
        sql_parts.append(
            f"INSERT INTO public.profiles (id, phone, display_name) "
            f"VALUES ('{persona.user_id}', '{persona.phone}', '{persona.handle}') "
            f"ON CONFLICT (id) DO UPDATE SET "
            f"phone = EXCLUDED.phone, display_name = EXCLUDED.display_name;"
        )
        sql_parts.append(
            f"INSERT INTO public.user_roles (user_id, role) "
            f"VALUES ('{persona.user_id}', '{persona.user_role}') "
            f"ON CONFLICT (user_id, role) DO NOTHING;"
        )
        if persona.vendor_id:
            tier = "NULL" if persona.kyc_tier is None else str(persona.kyc_tier)
            sql_parts.append(
                f"""
INSERT INTO public.vendors (
  id, owner_user_id, slug, display_name, status, kyc_tier
) VALUES (
  '{persona.vendor_id}', '{persona.user_id}', '{persona.slug}', '{persona.handle}',
  '{persona.vendor_status}', {tier}
) ON CONFLICT (id) DO UPDATE SET
  slug = EXCLUDED.slug,
  display_name = EXCLUDED.display_name,
  status = EXCLUDED.status,
  kyc_tier = EXCLUDED.kyc_tier;
"""
            )

    for record in KYC_FIXTURES:
        vendor_id = persona_by_key(record.vendor_key).vendor_id
        reviewed_by = record.reviewed_by
        reviewer_sql = f"'{reviewed_by}'" if reviewed_by else "NULL"
        reviewed_at_sql = "timezone('utc', now())" if reviewed_by else "NULL"
        reason = record.decision_reason
        reason_sql = f"'{reason}'" if reason else "NULL"
        sql_parts.append(
            f"""
INSERT INTO public.kyc_records (
  id, vendor_id, tier, doc_storage_paths, momo_name_match, status,
  reviewed_by, reviewed_at, decision_reason
) VALUES (
  '{record.id}', '{vendor_id}', {record.tier},
  ARRAY[]::text[], '{{"matched": true}}'::jsonb, '{record.status}',
  {reviewer_sql}, {reviewed_at_sql}, {reason_sql}
) ON CONFLICT (id) DO NOTHING;
"""
        )

    business_buyer = persona_by_key("BUSINESS_BUYER")
    sql_parts.append(
        f"""
INSERT INTO public.business_buyers (
  id, user_id, legal_name, registration_no, status, verified_at
) VALUES (
  '{business_buyer.business_buyer_id}', '{business_buyer.user_id}',
  '{business_buyer.business_legal_name}', '{business_buyer.business_registration_no}',
  'verified', timezone('utc', now())
) ON CONFLICT (id) DO UPDATE SET
  legal_name = EXCLUDED.legal_name,
  registration_no = EXCLUDED.registration_no,
  status = EXCLUDED.status,
  verified_at = EXCLUDED.verified_at;
"""
    )

    category = CATEGORY_FIXTURE
    sql_parts.append(
        f"""
INSERT INTO public.categories (
  id, name, slug, path, commission_key, prohibited, position
) VALUES (
  '{category["category_id"]}', '{category["category_name"]}',
  '{category["category_slug"]}', '{category["category_path"]}',
  '{category["commission_key"]}', false, 9999
) ON CONFLICT (id) DO NOTHING;
"""
    )

    for product in CATALOG_FIXTURES:
        sql_parts.append(
            f"""
INSERT INTO public.products (
  id, name, slug, spec, category_id, aliases, status
) VALUES (
  '{product.product_id}', '{product.product_name}',
  '{product.product_slug}', '{{}}'::jsonb, '{product.category_id}',
  ARRAY['{product.product_alias}']::text[], '{product.product_status}'
) ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  slug = EXCLUDED.slug,
  status = EXCLUDED.status;
"""
        )
        for listing in product.listings:
            vendor_id = persona_by_key(listing.vendor_key).vendor_id
            sql_parts.append(
                f"""
INSERT INTO public.vendor_listings (
  id, vendor_id, product_id, price_ngwee, condition, stock_mode, stock_qty,
  wholesale, moq, returnable, status, sku
) VALUES (
  '{listing.listing_id}', '{vendor_id}',
  '{product.product_id}', {listing.price_ngwee}, 'new',
  'tracked', {listing.stock_qty}, {'true' if listing.wholesale else 'false'},
  {listing.moq}, {'true' if listing.returnable else 'false'},
  '{listing.listing_status}', '{listing.sku}'
) ON CONFLICT (id) DO UPDATE SET
  price_ngwee = EXCLUDED.price_ngwee,
  stock_qty = EXCLUDED.stock_qty,
  wholesale = EXCLUDED.wholesale,
  moq = EXCLUDED.moq,
  status = EXCLUDED.status,
  sku = EXCLUDED.sku;
"""
            )
            image_id = IMAGE_IDS[listing.listing_id]
            sql_parts.append(
                f"""
INSERT INTO public.listing_images (
  id, listing_id, cloudinary_public_id, position
) VALUES (
  '{image_id}',
  '{listing.listing_id}', '{product.image_public_id}', 1
) ON CONFLICT (listing_id, position) DO UPDATE SET
  cloudinary_public_id = EXCLUDED.cloudinary_public_id;
"""
            )

    for location in VENDOR_LOCATIONS:
        vendor_id = persona_by_key(location.vendor_key).vendor_id
        sql_parts.append(
            f"""
INSERT INTO public.vendor_locations (
  id, vendor_id, lat, lng, landmark, label, area, city, province,
  phone_e164, is_primary, status
) VALUES (
  '{location.location_id}', '{vendor_id}', {location.lat}, {location.lng},
  '{location.landmark}', '{location.label}', '{location.area}',
  '{location.city}', '{location.province}', '{location.phone_e164}',
  {'true' if location.is_primary else 'false'}, 'active'
) ON CONFLICT (id) DO UPDATE SET
  lat = EXCLUDED.lat,
  lng = EXCLUDED.lng,
  landmark = EXCLUDED.landmark,
  label = EXCLUDED.label,
  status = EXCLUDED.status,
  is_primary = EXCLUDED.is_primary;
"""
        )

    location_stock_parts: list[str] = []
    for product in CATALOG_FIXTURES:
        for listing in product.listings:
            if listing.location_stock_qty is None:
                continue
            vendor_key = listing.vendor_key
            location = next(loc for loc in VENDOR_LOCATIONS if loc.vendor_key == vendor_key)
            location_stock_parts.append(
                f"""
INSERT INTO public.listing_location_stock (listing_id, location_id, stock_qty)
VALUES ('{listing.listing_id}', '{location.location_id}', {listing.location_stock_qty})
ON CONFLICT (listing_id, location_id) DO UPDATE SET stock_qty = EXCLUDED.stock_qty;
"""
            )

    sql_parts.append("COMMIT;")
    if location_stock_parts:
        # Branch stock rows are inserted as the migration owner (postgres). service_role
        # lacks a stable SET ROLE grant on every CI/bare-Postgres shim, while postgres
        # must seed deterministic QA fixtures without tripping RLS (owner bypass).
        sql_parts.extend(["BEGIN;", *location_stock_parts, "COMMIT;"])
    return _auth_users_sql() + "\n" + "\n".join(sql_parts)


def build_cleanup_sql() -> str:
    """Delete only deterministic synthetic contract rows (prefix + known UUIDs)."""
    listing_ids = ", ".join(
        f"'{listing.listing_id}'"
        for product in CATALOG_FIXTURES
        for listing in product.listings
    )
    product_ids = ", ".join(f"'{product.product_id}'" for product in CATALOG_FIXTURES)
    vendor_ids = ", ".join(
        f"'{persona.vendor_id}'"
        for persona in PERSONAS
        if persona.vendor_id is not None
    )
    user_ids = ", ".join(f"'{persona.user_id}'" for persona in PERSONAS)
    location_ids = ", ".join(f"'{loc.location_id}'" for loc in VENDOR_LOCATIONS)
    kyc_ids = ", ".join(f"'{record.id}'" for record in KYC_FIXTURES)
    business_buyer_id = persona_by_key("BUSINESS_BUYER").business_buyer_id

    return f"""
BEGIN;
DELETE FROM public.listing_location_stock
WHERE listing_id IN ({listing_ids});
COMMIT;

BEGIN;
SET LOCAL role service_role;
SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';

-- Transactional rows created by QA drivers (scoped to synthetic checkout keys).
DELETE FROM public.payments
WHERE checkout_group_id IN (
  SELECT id FROM public.checkout_groups
  WHERE idempotency_key LIKE '{SEED_PREFIX}-txn-%'
);
DELETE FROM public.order_items
WHERE order_id IN (
  SELECT id FROM public.orders
  WHERE checkout_group_id IN (
    SELECT id FROM public.checkout_groups
    WHERE idempotency_key LIKE '{SEED_PREFIX}-txn-%'
  )
);
DELETE FROM public.orders
WHERE checkout_group_id IN (
  SELECT id FROM public.checkout_groups
  WHERE idempotency_key LIKE '{SEED_PREFIX}-txn-%'
);
DELETE FROM public.checkout_groups
WHERE idempotency_key LIKE '{SEED_PREFIX}-txn-%';

DELETE FROM public.listing_images
WHERE listing_id IN ({listing_ids})
   OR cloudinary_public_id LIKE 'staging-synthetic/{SEED_PREFIX}%';

DELETE FROM public.vendor_listings
WHERE id IN ({listing_ids})
   OR sku LIKE '{SEED_PREFIX}%';

DELETE FROM public.products
WHERE id IN ({product_ids})
   OR slug LIKE '{SEED_PREFIX}%';

DELETE FROM public.vendor_locations
WHERE id IN ({location_ids});

DELETE FROM public.kyc_records
WHERE id IN ({kyc_ids});

DELETE FROM public.business_buyers
WHERE id = '{business_buyer_id}';

DELETE FROM public.vendors
WHERE id IN ({vendor_ids})
   OR slug LIKE '{SEED_PREFIX}%';

DELETE FROM public.user_roles
WHERE user_id IN ({user_ids});

DELETE FROM public.profiles
WHERE id IN ({user_ids});

DELETE FROM public.categories
WHERE slug = '{CATEGORY_FIXTURE["category_slug"]}';

DELETE FROM auth.users
WHERE id IN ({user_ids});

COMMIT;
"""


def verification_queries() -> dict[str, str]:
    product_a = CATALOG_FIXTURES[0]
    listing_ids = ", ".join(f"'{listing.listing_id}'" for listing in product_a.listings)
    return {
        "multiseller_count": (
            "SELECT count(*)::int FROM public.vendor_listings "
            f"WHERE product_id = '{product_a.product_id}' "
            "AND status = 'active' AND wholesale = false"
        ),
        "multiseller_listings": (
            "SELECT count(*)::int FROM public.vendor_listings "
            f"WHERE id IN ({listing_ids}) AND status = 'active'"
        ),
        "location_stock_rows": (
            "SELECT count(*)::int FROM public.listing_location_stock "
            f"WHERE listing_id IN ({listing_ids})"
        ),
        "oos_stock": (
            "SELECT coalesce(stock_qty, -1)::int FROM public.vendor_listings "
            "WHERE sku LIKE '%-list-prd-c-oos'"
        ),
        "wholesale_product_d": (
            "SELECT wholesale::text FROM public.vendor_listings "
            "WHERE sku LIKE '%-list-prd-d-wholesale'"
        ),
        "zero_price_guard": (
            "SELECT count(*)::int FROM public.vendor_listings "
            f"WHERE sku LIKE '{SEED_PREFIX}%' AND price_ngwee < 1"
        ),
    }


def parse_verification(results: dict[str, list[str]]) -> None:
    multiseller = int(results["multiseller_count"][0])
    if multiseller < 2:
        raise RuntimeError("multiseller product A verification failed")
    if results["multiseller_listings"] != ["2"]:
        raise RuntimeError("multiseller listing pair verification failed")
    location_rows = int(results["location_stock_rows"][0])
    if location_rows < 2:
        raise RuntimeError("location stock verification failed")
    if results["oos_stock"] != ["0"]:
        raise RuntimeError("out-of-stock product C verification failed")
    if results["wholesale_product_d"] != ["true"]:
        raise RuntimeError("wholesale-only product D verification failed")
    if results["zero_price_guard"] != ["0"]:
        raise RuntimeError("zero-price guard failed for synthetic listings")


__all__ = [
    "IMAGE_IDS",
    "build_cleanup_sql",
    "build_seed_sql",
    "parse_verification",
    "verification_queries",
]
