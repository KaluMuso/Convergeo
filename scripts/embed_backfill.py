#!/usr/bin/env python3
"""Enqueue and process embedding jobs for search_documents missing embeddings."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.embeddings.batch import EMBEDDING_BATCH_LIMIT, process_embedding_tick  # noqa: E402
from app.settings import get_settings  # noqa: E402
from app.supabase_client import get_supabase_service_client  # noqa: E402


def _configure_env() -> None:
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    os.environ.setdefault("SUPABASE_ANON_KEY", "anon-key")
    os.environ.setdefault("ENV", "development")


def enqueue_missing_documents(*, dry_run: bool) -> int:
    service = get_supabase_service_client()
    response = (
        service.client.table("search_documents")
        .select("id,entity_kind,entity_id")
        .eq("is_public", True)
        .is_("embedding", "null")
        .execute()
    )
    rows = response.data or []
    if dry_run:
        print(f"Would enqueue {len(rows)} search_documents")
        return len(rows)

    enqueued = 0
    for row in rows:
        service.client.rpc(
            "embedding_enqueue_document",
            {
                "p_search_document_id": row["id"],
                "p_entity_kind": row["entity_kind"],
                "p_entity_id": row["entity_id"],
            },
        ).execute()
        enqueued += 1

    print(f"Enqueued {enqueued} embedding jobs")
    return enqueued


async def process_until_idle(*, batch_limit: int, max_rounds: int) -> dict[str, float | int]:
    service = get_supabase_service_client()
    totals = {"processed": 0, "dead": 0, "cost_usd": 0.0, "rounds": 0}

    for _ in range(max_rounds):
        result = await process_embedding_tick(service, limit=batch_limit)
        totals["rounds"] = int(totals["rounds"]) + 1
        totals["processed"] = int(totals["processed"]) + result.processed
        totals["dead"] = int(totals["dead"]) + result.dead
        totals["cost_usd"] = float(totals["cost_usd"]) + result.cost_usd
        if result.processed == 0 and result.dead == 0:
            break

    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enqueue-only",
        action="store_true",
        help="Only enqueue jobs for documents missing embeddings",
    )
    parser.add_argument(
        "--process-only",
        action="store_true",
        help="Only run embedding ticks (skip enqueue)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many documents would be enqueued without writing",
    )
    parser.add_argument(
        "--batch-limit",
        type=int,
        default=EMBEDDING_BATCH_LIMIT,
        help=f"Jobs claimed per tick (max {EMBEDDING_BATCH_LIMIT})",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=1000,
        help="Maximum tick rounds when processing",
    )
    args = parser.parse_args()

    _configure_env()
    get_settings.cache_clear()
    get_supabase_service_client.cache_clear()

    if not args.process_only:
        enqueue_missing_documents(dry_run=args.dry_run)
        if args.dry_run or args.enqueue_only:
            return 0

    totals = asyncio.run(
        process_until_idle(batch_limit=args.batch_limit, max_rounds=args.max_rounds)
    )
    print(
        "Backfill complete:",
        f"processed={totals['processed']}",
        f"dead={totals['dead']}",
        f"cost_usd={totals['cost_usd']:.8f}",
        f"rounds={totals['rounds']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
