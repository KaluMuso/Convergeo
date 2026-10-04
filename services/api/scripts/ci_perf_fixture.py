"""Exact two-image fixture expansion, only on the disposable Performance CI database."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

PHONE = "b1000000-0000-0000-0000-000000000001"
GADGET = "b1000000-0000-0000-0000-000000000003"
PRODUCT = "b0000000-0000-0000-0000-000000000001"
CATEGORY = "c0000000-0000-0000-0000-000000000001"
PHONE_IMAGE = "b2000000-0000-0000-0000-000000000001"
GADGET_IMAGE = "b2000000-0000-0000-0000-000000000003"
MEDIA = "ci-perf/smartphone-x1"
LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def require_isolated_harness(env: Mapping[str, str]) -> str:
    required = {
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "CI_PERF_HARNESS": "1",
        "NEXT_PUBLIC_CI_PERF_HARNESS": "1",
        "NEXT_PUBLIC_DEPLOYMENT_PLANE": "preview",
        "NEXT_PUBLIC_SITE_URL": "http://localhost:3000",
        "ENV": "development",
        "SUPABASE_URL": "http://127.0.0.1:54321",
        "SUPABASE_DB_URL": LOCAL_DSN,
    }
    if any(env.get(key) != value for key, value in required.items()):
        raise ValueError("Performance fixture requires the exact disposable CI harness")
    if env.get("VERCEL") or env.get("VERCEL_ENV"):
        raise ValueError("Performance fixture cannot run on Vercel")
    origin = env.get("NEXT_PUBLIC_API_BASE_URL", "")
    url = urlsplit(origin)
    try:
        address = ipaddress.IPv4Address(url.hostname or "")
    except ipaddress.AddressValueError as error:
        raise ValueError("Performance fixture requires an assigned RFC1918 API origin") from error
    private = any(
        address in ipaddress.IPv4Network(network)
        for network in (
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
        )
    )
    if (
        not private
        or origin != f"http://{address}:8000"
        or env.get("CI_PERF_UPSTREAM_ORIGIN") != origin
    ):
        raise ValueError("Performance fixture API origin mismatch")
    return LOCAL_DSN


def expand_fixture(connection: Any) -> None:
    # Parent-row locks also prevent concurrent image inserts through these FKs.
    category = connection.execute(
        "SELECT id::text, name, slug, path::text, prohibited FROM public.categories "
        "WHERE id = %s FOR UPDATE",
        (CATEGORY,),
    ).fetchall()
    if category != [(CATEGORY, "Electronics", "electronics", "electronics", False)]:
        raise ValueError("Performance category preimage mismatch")
    vendors = connection.execute(
        "SELECT id::text, owner_user_id::text, slug, display_name, status "
        "FROM public.vendors WHERE id IN (%s, %s) ORDER BY id FOR UPDATE",
        ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "d0000000-0000-0000-0000-000000000001"),
    ).fetchall()
    if vendors != [
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "33333333-3333-3333-3333-333333333333",
            "lusaka-electronics",
            "Lusaka Electronics Hub",
            "active",
        ),
        (
            "d0000000-0000-0000-0000-000000000001",
            "66666666-6666-6666-6666-666666666666",
            "demo-sandbox",
            "Demo Sandbox Shop",
            "active",
        ),
    ]:
        raise ValueError("Performance vendor preimage mismatch")
    product = connection.execute(
        "SELECT id::text, slug, category_id::text, name, status "
        "FROM public.products WHERE id = %s FOR UPDATE",
        (PRODUCT,),
    ).fetchall()
    if product != [(PRODUCT, "smartphone-x1", CATEGORY, "Smartphone X1", "active")]:
        raise ValueError("Performance product preimage mismatch")
    rows = connection.execute(
        "SELECT id::text, vendor_id::text, product_id::text, title_override, "
        "price_ngwee, stock_mode, stock_qty, status, wholesale, condition "
        "FROM public.vendor_listings WHERE product_id = %s ORDER BY id FOR UPDATE",
        (PRODUCT,),
    ).fetchall()
    expected = [
        (
            PHONE,
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            PRODUCT,
            "Smartphone X1 — 128GB",
            450000,
            "tracked",
            12,
            "active",
            False,
            "new",
        ),
        (
            GADGET,
            "d0000000-0000-0000-0000-000000000001",
            PRODUCT,
            "Demo Gadget (sandbox)",
            10000,
            "always_available",
            0,
            "active",
            False,
            "new",
        ),
    ]
    if rows != expected:
        raise ValueError("Performance listing preimage mismatch")
    images = connection.execute(
        "SELECT id::text, listing_id::text, cloudinary_public_id, position "
        "FROM public.listing_images WHERE listing_id IN (%s, %s) ORDER BY id FOR UPDATE",
        (PHONE, GADGET),
    ).fetchall()
    if images != [(PHONE_IMAGE, PHONE, "vergeo5/demo/phone-a", 1)]:
        raise ValueError("Performance media preimage mismatch")
    updated = connection.execute(
        "UPDATE public.listing_images SET cloudinary_public_id = %s WHERE id = %s "
        "RETURNING id::text",
        (MEDIA, PHONE_IMAGE),
    ).fetchall()
    if updated != [(PHONE_IMAGE,)]:
        raise ValueError("Performance media update mismatch")
    connection.execute(
        "INSERT INTO public.listing_images (id, listing_id, cloudinary_public_id, position) "
        "VALUES (%s, %s, %s, 1)",
        (GADGET_IMAGE, GADGET, "demo/ci-perf-hidden-gadget"),
    )


def main() -> None:
    dsn = require_isolated_harness(os.environ)  # Before connecting or reading credentials.
    import psycopg

    # The connection context commits both operations or rolls them both back.
    with psycopg.connect(dsn) as connection:
        expand_fixture(connection)
    print("Disposable CI fixture: exact phone_a media replaced; exact demo_gadget marked demo")


if __name__ == "__main__":
    main()
