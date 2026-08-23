"""SQL builders for staging synthetic seed and scoped cleanup."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.staging.synthetic_contract import (
    CATALOG_FIXTURES,
    CATEGORY_FIXTURE,
    EVENTS,
    KYC_FIXTURES,
    PERSONAS,
    SEED_PREFIX,
    VENDOR_LOCATIONS,
    persona_by_key,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.staging.ticket_credentials import TicketCredential

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


def build_seed_sql(
    ticket_credentials: tuple[TicketCredential, ...] | None = None,
) -> str:
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
    # Events come last: they reference the vendors and profiles seeded above.
    sql_parts.append(build_events_sql(ticket_credentials))
    if location_stock_parts:
        # Branch stock rows are inserted as the migration owner (postgres). service_role
        # lacks a stable SET ROLE grant on every CI/bare-Postgres shim, while postgres
        # must seed deterministic QA fixtures without tripping RLS (owner bypass).
        sql_parts.extend(["BEGIN;", *location_stock_parts, "COMMIT;"])
    return _auth_users_sql() + "\n" + "\n".join(sql_parts)


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def build_events_sql(
    ticket_credentials: tuple[TicketCredential, ...] | None = None,
) -> str:
    """Events, instances, ticket types and issued tickets for the scanner journey.

    `ticket_credentials` carries the run-scoped sealed PIN / QR secret. When it is
    absent the ticket rows are still created (identity is canonical) but with a
    NULL pin_hash, so a scanner run without the staging service-role key fails
    visibly at verification rather than appearing to pass.
    """
    by_ticket = {c.ticket_id: c for c in (ticket_credentials or ())}
    parts = ["BEGIN;"]
    for event in EVENTS:
        organiser = persona_by_key(event.organiser_key)
        parts.append(
            f"""
INSERT INTO public.events (
  id, organiser_vendor_id, slug, title, event_type, status, visibility,
  platform_fee_payer, venue, city, landmark, lat, lng, images
) VALUES (
  '{event.event_id}', '{organiser.vendor_id}', '{_sql_literal(event.slug)}',
  '{_sql_literal(event.title)}', '{event.event_type}', '{event.status}',
  '{event.visibility}', '{event.platform_fee_payer}',
  '{_sql_literal(event.venue)}', '{_sql_literal(event.city)}',
  '{_sql_literal(event.landmark)}', {event.lat}, {event.lng}, '{{}}'
) ON CONFLICT (id) DO UPDATE SET
  organiser_vendor_id = EXCLUDED.organiser_vendor_id,
  slug = EXCLUDED.slug,
  title = EXCLUDED.title,
  event_type = EXCLUDED.event_type,
  status = EXCLUDED.status,
  visibility = EXCLUDED.visibility,
  platform_fee_payer = EXCLUDED.platform_fee_payer,
  venue = EXCLUDED.venue,
  city = EXCLUDED.city,
  landmark = EXCLUDED.landmark,
  lat = EXCLUDED.lat,
  lng = EXCLUDED.lng;

INSERT INTO public.event_instances (id, event_id, starts_at, ends_at, capacity, status)
VALUES (
  '{event.instance_id}', '{event.event_id}', '{event.starts_at}',
  '{event.ends_at}', {event.capacity}, 'scheduled'
) ON CONFLICT (id) DO UPDATE SET
  starts_at = EXCLUDED.starts_at,
  ends_at = EXCLUDED.ends_at,
  capacity = EXCLUDED.capacity,
  status = EXCLUDED.status;
"""
        )
        for ticket_type in event.ticket_types:
            qty_cap = "NULL" if ticket_type.qty_cap is None else str(ticket_type.qty_cap)
            parts.append(
                f"""
INSERT INTO public.ticket_types (
  id, event_id, kind, pass_kind, name, price_ngwee, qty_cap, attendee_named
) VALUES (
  '{ticket_type.ticket_type_id}', '{event.event_id}', '{ticket_type.kind}',
  '{ticket_type.pass_kind}', '{_sql_literal(ticket_type.name)}',
  {ticket_type.price_ngwee}, {qty_cap}, {str(ticket_type.attendee_named).lower()}
) ON CONFLICT (id) DO UPDATE SET
  kind = EXCLUDED.kind,
  pass_kind = EXCLUDED.pass_kind,
  name = EXCLUDED.name,
  price_ngwee = EXCLUDED.price_ngwee,
  qty_cap = EXCLUDED.qty_cap,
  attendee_named = EXCLUDED.attendee_named;

INSERT INTO public.ticket_type_instances (instance_id, ticket_type_id, allocation)
VALUES ('{event.instance_id}', '{ticket_type.ticket_type_id}', {ticket_type.allocation})
ON CONFLICT (instance_id, ticket_type_id) DO UPDATE SET
  allocation = EXCLUDED.allocation;
"""
            )
        for ticket in event.tickets:
            holder = persona_by_key(ticket.holder_key)
            credential = by_ticket.get(ticket.ticket_id)
            pin_hash = f"'{credential.pin_hash}'" if credential else "NULL"
            qr_secret = f"'{credential.qr_secret}'" if credential else "NULL"
            parts.append(
                f"""
INSERT INTO public.tickets (
  id, instance_id, ticket_type_id, holder_user_id, status, pin_hash, qr_secret,
  checked_in_at
) VALUES (
  '{ticket.ticket_id}', '{event.instance_id}', '{ticket.ticket_type_id}',
  '{holder.user_id}', '{ticket.status}', {pin_hash}, {qr_secret}, NULL
) ON CONFLICT (id) DO UPDATE SET
  instance_id = EXCLUDED.instance_id,
  ticket_type_id = EXCLUDED.ticket_type_id,
  holder_user_id = EXCLUDED.holder_user_id,
  status = EXCLUDED.status,
  pin_hash = EXCLUDED.pin_hash,
  qr_secret = EXCLUDED.qr_secret,
  -- Re-seeding restores an un-scanned ticket so verify-then-duplicate-reject
  -- is reproducible on every run.
  checked_in_at = NULL;
"""
            )
    parts.append("COMMIT;")
    return "\n".join(parts)


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
    event_ids = ", ".join(f"'{event.event_id}'" for event in EVENTS)
    instance_ids = ", ".join(f"'{event.instance_id}'" for event in EVENTS)
    ticket_type_ids = ", ".join(
        f"'{t.ticket_type_id}'" for event in EVENTS for t in event.ticket_types
    )
    ticket_ids = ", ".join(
        f"'{t.ticket_id}'" for event in EVENTS for t in event.tickets
    )

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

-- Events before vendors/profiles: tickets reference holders and events
-- reference the organiser vendor.
DELETE FROM public.tickets
WHERE id IN ({ticket_ids})
   OR instance_id IN ({instance_ids});

DELETE FROM public.ticket_type_instances
WHERE instance_id IN ({instance_ids})
   OR ticket_type_id IN ({ticket_type_ids});

DELETE FROM public.ticket_types
WHERE id IN ({ticket_type_ids})
   OR event_id IN ({event_ids});

DELETE FROM public.event_instances
WHERE id IN ({instance_ids})
   OR event_id IN ({event_ids});

DELETE FROM public.events
WHERE id IN ({event_ids})
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
        "event_published": (
            "SELECT count(*)::int FROM public.events "
            f"WHERE slug LIKE '{SEED_PREFIX}%' AND status = 'published'"
        ),
        "event_instances_scheduled": (
            "SELECT count(*)::int FROM public.event_instances ei "
            "JOIN public.events e ON e.id = ei.event_id "
            f"WHERE e.slug LIKE '{SEED_PREFIX}%' AND ei.status = 'scheduled'"
        ),
        "event_ticket_types": (
            "SELECT count(*)::int FROM public.ticket_types tt "
            "JOIN public.events e ON e.id = tt.event_id "
            f"WHERE e.slug LIKE '{SEED_PREFIX}%'"
        ),
        "issued_tickets": (
            "SELECT count(*)::int FROM public.tickets t "
            "JOIN public.event_instances ei ON ei.id = t.instance_id "
            "JOIN public.events e ON e.id = ei.event_id "
            f"WHERE e.slug LIKE '{SEED_PREFIX}%' "
            "AND t.status = 'issued' AND t.checked_in_at IS NULL"
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
    if int(results["event_published"][0]) < len(EVENTS):
        raise RuntimeError("synthetic event verification failed")
    if int(results["event_instances_scheduled"][0]) < len(EVENTS):
        raise RuntimeError("synthetic event instance verification failed")
    expected_types = sum(len(e.ticket_types) for e in EVENTS)
    if int(results["event_ticket_types"][0]) < expected_types:
        raise RuntimeError("synthetic ticket type verification failed")
    expected_tickets = sum(
        1 for e in EVENTS for t in e.tickets if t.status == "issued"
    )
    if int(results["issued_tickets"][0]) < expected_tickets:
        raise RuntimeError(
            "synthetic issued-ticket verification failed — the scanner journey "
            "needs an un-scanned ticket"
        )


__all__ = [
    "IMAGE_IDS",
    "build_cleanup_sql",
    "build_events_sql",
    "build_seed_sql",
    "parse_verification",
    "verification_queries",
]
