"""Native SQL observations/fixture cleanup for the disposable perf cart drill."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "e2e/results/cart-response-drill/private-state.json"
DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def main() -> None:
    if (
        os.environ.get("CART_DRILL_LOCAL") != "1"
        or os.environ.get("SUPABASE_URL") != "http://127.0.0.1:54321"
        or os.environ.get("SUPABASE_DB_URL") != DSN
        or str(os.getuid()) != os.environ.get("CART_DRILL_UID")
        or os.getuid() == 0
    ):
        raise ValueError("Drill requires the dedicated UID and fixed disposable stack")
    action = sys.argv[1]
    payload = json.load(sys.stdin)
    with psycopg.connect(DSN, connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("set statement_timeout='3s'; set lock_timeout='1s'")
        if action == "bind":
            if STATE.exists():
                raise ValueError("Fixture already bound")
            cart, listing = str(UUID(payload["cart"])), str(UUID(payload["listing"]))
            cur.execute("select user_id, status from public.carts where id=%s", (cart,))
            if cur.fetchone() != (None, "active"):
                raise ValueError("Expected established synthetic guest cart")
            cur.execute(
                "select count(*) from public.cart_items where cart_id=%s", (cart,)
            )
            assert cur.fetchone() == (0,)
            cur.execute(
                "select price_ngwee, stock_mode, stock_qty, wholesale, status "
                "from public.vendor_listings where id=%s",
                (listing,),
            )
            row = cur.fetchone()
            assert row is not None and row[3:] == (False, "active")
            cur.execute(
                "select id::text from public.funnel_events where stage='cart_add' "
                "and customer_id is null and snapshot->'lines' @> %s::jsonb",
                (json.dumps([{"listing_id": listing}]),),
            )
            state = {
                "cart": cart,
                "listing": listing,
                "price": row[0],
                "stock_mode": row[1],
                "stock_qty": row[2],
                "prior_events": [r[0] for r in cur.fetchall()],
            }
            STATE.write_text(json.dumps(state))
            print(json.dumps({"price": row[0], "guest": True, "empty": True}))
            return
        state = json.loads(STATE.read_text())
        cart, listing = state["cart"], state["listing"]
        if action == "price":
            cur.execute(
                "update public.vendor_listings set price_ngwee=%s, "
                "stock_mode='tracked', stock_qty=10 where id=%s",
                (state["price"] + 100, listing),
            )
        elif action == "stock":
            cur.execute(
                "update public.vendor_listings set stock_qty=1 where id=%s", (listing,)
            )
        elif action == "restore-stock":
            cur.execute(
                "update public.vendor_listings set stock_qty=10 where id=%s", (listing,)
            )
        elif action not in {"observe", "cleanup"}:
            raise ValueError("Unknown fixture action")
        cur.execute(
            "select id::text from public.funnel_events where stage='cart_add' "
            "and customer_id is null and snapshot->'lines' @> %s::jsonb",
            (json.dumps([{"listing_id": listing}]),),
        )
        new_events = [r[0] for r in cur.fetchall() if r[0] not in state["prior_events"]]
        if action == "cleanup":
            cur.execute(
                "update public.vendor_listings set price_ngwee=%s, stock_mode=%s, "
                "stock_qty=%s where id=%s",
                (state["price"], state["stock_mode"], state["stock_qty"], listing),
            )
            cur.execute(
                "delete from public.funnel_events where id=any(%s::uuid[])",
                (new_events,),
            )
            cur.execute(
                "delete from public.carts where id=%s and user_id is null", (cart,)
            )
            assert cur.rowcount == 1
            conn.commit()
            STATE.unlink()
            print(json.dumps({"cleaned": True}))
            return
        cur.execute(
            "select qty, unit_price_ngwee from public.cart_items "
            "where cart_id=%s and listing_id=%s",
            (cart, listing),
        )
        item = cur.fetchone()
        cur.execute(
            "select count(*) from public.cart_add_requests where cart_id=%s", (cart,)
        )
        count = cur.fetchone()
        assert count is not None
        result: dict[str, Any] = {
            "qty": item[0] if item else 0,
            "stored_price": item[1] if item else None,
            "claims": count[0],
            "events": len(new_events),
        }
        if "key" in payload:
            cur.execute(
                "select request_body from public.cart_add_requests "
                "where cart_id=%s and idempotency_key=%s",
                (cart, payload["key"]),
            )
            claim = cur.fetchone()
            result["key_committed"] = claim is not None
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Native disposable drill observation failed", file=sys.stderr)
        raise SystemExit(1) from None
