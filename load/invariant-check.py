#!/usr/bin/env python3
"""Post-load-run money-safety invariant check for Vergeo5.

Run this AFTER a k6 checkout load run against the SAME database the run hit. It is the
ground-truth proof that concurrency did not corrupt money or inventory. Three invariants:

  1. ZERO OVERSELLS   — no tracked listing ever went negative. The claim path decrements
                        stock in-place under the guard `stock_qty >= qty` and the column
                        carries CHECK (stock_qty >= 0). If a race ever let two checkouts
                        claim the last unit, stock_qty would be driven below zero (or the
                        CHECK would have aborted the write). Any tracked row with
                        stock_qty < 0, or any active hold on an out-of-stock listing, is an
                        oversell.
  2. LEDGER BALANCED  — double-entry holds. Every ledger_transaction's postings sum to 0
                        (per-transaction), AND the whole ledger sums to 0 (system-wide). A
                        half-posted transaction (one leg written, its sibling lost under
                        load) shows up as a non-zero sum — money created or destroyed.
  3. INVOICE GAPLESS  — ZRA-ready sequential numbering. Per series the invoice `no` values
                        must run 1..N with no holes (min = 1 AND max = count). A hole means
                        a number was allocated by next_invoice_no() but its invoice row was
                        rolled back — a gap a tax auditor would flag.

Exit code is NON-ZERO if any invariant is violated. No credentials are embedded; the DB
URL comes from SUPABASE_DB_URL (falls back to the repo's local-dev default). This mirrors
the psql-subprocess pattern already used by services/api (app/services/stock/claim.py) so
it needs no extra Python dependency.

Usage:
    SUPABASE_DB_URL=postgresql://user:pass@host:5432/db python3 load/invariant-check.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

DEFAULT_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


@dataclass(frozen=True)
class Invariant:
    key: str
    title: str
    sql: str
    # A violation is any returned row (each row describes an offending record/aggregate).


# --- Invariant 1: zero oversells ------------------------------------------------------
# (a) no tracked listing is negative; (b) no ACTIVE (unexpired) hold sits on a listing
# that is already out of stock — that pairing can only exist if stock was handed out past
# zero. Both surface as rows here.
OVERSELL_SQL = """
SELECT 'negative_stock' AS violation, vl.id::text, vl.stock_qty
FROM public.vendor_listings vl
WHERE vl.stock_mode = 'tracked'
  AND vl.stock_qty IS NOT NULL
  AND vl.stock_qty < 0
UNION ALL
SELECT 'oversold_hold' AS violation, vl.id::text, vl.stock_qty
FROM public.vendor_listings vl
WHERE vl.stock_mode = 'tracked'
  AND vl.stock_qty IS NOT NULL
  AND vl.stock_qty < 0
  AND EXISTS (
    SELECT 1 FROM public.stock_reservations sr
    WHERE sr.listing_id = vl.id
      AND sr.expires_at > timezone('utc', now())
  );
"""

# --- Invariant 2: ledger balanced -----------------------------------------------------
# (a) per-transaction imbalance rows; (b) a single system-wide imbalance row (only emitted
# when the global sum is non-zero).
LEDGER_SQL = """
SELECT 'txn_imbalance' AS violation, lp.transaction_id::text,
       sum(lp.amount_ngwee) AS imbalance_ngwee
FROM public.ledger_postings lp
GROUP BY lp.transaction_id
HAVING sum(lp.amount_ngwee) <> 0
UNION ALL
SELECT 'system_imbalance' AS violation, NULL::text,
       (SELECT coalesce(sum(amount_ngwee), 0) FROM public.ledger_postings)
WHERE (SELECT coalesce(sum(amount_ngwee), 0) FROM public.ledger_postings) <> 0;
"""

# --- Invariant 3: gapless invoice numbers ---------------------------------------------
# unique(series, no) already blocks duplicates, so count <= max always; a hole makes
# max(no) > count(*). A series must start at 1. Any offending series is a row.
INVOICE_GAP_SQL = """
SELECT series,
       count(*)  AS invoice_count,
       min(no)   AS min_no,
       max(no)   AS max_no
FROM public.invoices
GROUP BY series
HAVING min(no) <> 1
    OR max(no) <> count(*);
"""

INVARIANTS: tuple[Invariant, ...] = (
    Invariant("oversell", "Zero oversells (no negative / oversold stock)", OVERSELL_SQL),
    Invariant("ledger", "Ledger balanced (per-txn and system-wide)", LEDGER_SQL),
    Invariant("invoice_gap", "Invoice numbers gapless per series", INVOICE_GAP_SQL),
)


def _db_url() -> str:
    return os.environ.get("SUPABASE_DB_URL", DEFAULT_DB_URL)


def _run_query(sql: str) -> list[str]:
    """Return non-empty result rows (pipe-delimited). Raises on psql error."""
    proc = subprocess.run(
        ["psql", _db_url(), "-v", "ON_ERROR_STOP=1", "-At", "-F", "|"],
        input=sql,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"psql failed: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    print(f"Vergeo5 load invariant-check against {_db_url().split('@')[-1]}")
    failures = 0
    for inv in INVARIANTS:
        try:
            rows = _run_query(inv.sql)
        except RuntimeError as exc:
            print(f"[ERROR] {inv.key}: {exc}", file=sys.stderr)
            failures += 1
            continue
        if rows:
            failures += 1
            print(f"[FAIL] {inv.title}: {len(rows)} violation(s)")
            for row in rows[:20]:
                print(f"        - {row}")
            if len(rows) > 20:
                print(f"        ... {len(rows) - 20} more")
        else:
            print(f"[PASS] {inv.title}")

    if failures:
        print(f"\nINVARIANT CHECK FAILED — {failures} invariant(s) violated.", file=sys.stderr)
        return 1
    print("\nINVARIANT CHECK PASSED — no oversell, ledger balanced, invoices gapless.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
