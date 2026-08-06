#!/usr/bin/env python3
"""Idempotent seeder for the Convergeo service/vendor category taxonomy.

Populates public.service_categories from the Strategy Brief §5 catalogue
(docs/concept/Convergeo_Strategy_Bible.pdf, pp.86–94). Structural data only —
no vendors, users, or products.

Usage:
  python scripts/seed_taxonomy.py
  SUPABASE_DB_URL=postgresql://... python scripts/seed_taxonomy.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from app.schemas.service_categories import ServiceCategoryRow  # noqa: E402
from psycopg import AsyncConnection  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from taxonomy.convergeo_service_catalogue import CONVERGEO_SERVICE_TAXONOMY  # noqa: E402

DEFAULT_DB_URL = os.environ.get(
    "SUPABASE_DB_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """URL-safe slug from a display name."""
    value = name.lower().replace("&", "and")
    value = _SLUG_RE.sub("-", value).strip("-")
    return value or "category"


def flatten_taxonomy() -> list[ServiceCategoryRow]:
    """Expand vertical → sub-category tree into flat rows with materialized paths."""
    rows: list[ServiceCategoryRow] = []
    for vertical_index, vertical in enumerate(CONVERGEO_SERVICE_TAXONOMY):
        vertical_slug = slugify(vertical["name"])
        rows.append(
            ServiceCategoryRow(
                slug=vertical_slug,
                parent_slug=None,
                name=vertical["name"],
                path=vertical_slug,
                sort=vertical_index,
                is_active=True,
            )
        )
        for sub_index, sub in enumerate(vertical.get("subcategories", [])):
            sub_slug = slugify(sub["name"])
            rows.append(
                ServiceCategoryRow(
                    slug=sub_slug,
                    parent_slug=vertical_slug,
                    name=sub["name"],
                    path=f"{vertical_slug}/{sub_slug}",
                    archetype=sub.get("archetype"),
                    regulator=sub.get("regulator"),
                    sort=sub_index,
                    is_active=True,
                )
            )
    return rows


UPSERT_SQL = """
insert into public.service_categories (
  slug,
  parent_slug,
  name,
  path,
  archetype,
  regulator,
  sort,
  is_active
) values (
  %(slug)s,
  %(parent_slug)s,
  %(name)s,
  %(path)s,
  %(archetype)s,
  %(regulator)s,
  %(sort)s,
  %(is_active)s
)
on conflict (slug) do nothing
"""


async def seed_taxonomy(conn: AsyncConnection[Any], *, dry_run: bool) -> dict[str, int]:
    rows = flatten_taxonomy()
    verticals = sum(1 for row in rows if row.parent_slug is None)
    subcategories = len(rows) - verticals

    if dry_run:
        return {
            "verticals": verticals,
            "subcategories": subcategories,
            "total": len(rows),
            "inserted": 0,
            "already_present": 0,
        }

    inserted = 0
    for row in rows:
        params = row.model_dump()
        result = await conn.execute(UPSERT_SQL, params)
        if result.rowcount and result.rowcount > 0:
            inserted += 1

    await conn.commit()

    count_row = await conn.execute(
        "select count(*)::int as total from public.service_categories"
    )
    total_in_db = (await count_row.fetchone())["total"]  # type: ignore[index]

    return {
        "verticals": verticals,
        "subcategories": subcategories,
        "total": len(rows),
        "inserted": inserted,
        "already_present": len(rows) - inserted,
        "total_in_db": total_in_db,
    }


async def ensure_table(conn: AsyncConnection[Any]) -> None:
    check = await conn.execute(
        "select to_regclass('public.service_categories')::text as rel"
    )
    row = await check.fetchone()
    if row and row["rel"]:
        return
    msg = (
        "public.service_categories does not exist. Apply migrations first "
        "(supabase db reset or migration 0092_service_categories.sql)."
    )
    raise RuntimeError(msg)


async def run(db_url: str, *, dry_run: bool) -> dict[str, int]:
    async with await AsyncConnection.connect(db_url, row_factory=dict_row) as conn:
        await ensure_table(conn)
        return await seed_taxonomy(conn, dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed Convergeo service category taxonomy (idempotent)."
    )
    parser.add_argument(
        "--db-url",
        default=DEFAULT_DB_URL,
        help="Postgres connection URL (default: SUPABASE_DB_URL or local Supabase)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned counts without writing to the database",
    )
    args = parser.parse_args()

    try:
        stats = asyncio.run(run(args.db_url, dry_run=args.dry_run))
    except Exception as exc:  # noqa: BLE001 — CLI entrypoint
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    mode = "dry-run" if args.dry_run else "applied"
    print(f"Convergeo service taxonomy seed ({mode})")
    print(f"  verticals: {stats['verticals']}")
    print(f"  subcategories: {stats['subcategories']}")
    print(f"  catalogue total: {stats['total']}")
    if not args.dry_run:
        print(f"  newly inserted this run: {stats['inserted']}")
        print(f"  skipped (already present): {stats['already_present']}")
        print(f"  total rows in database: {stats['total_in_db']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
