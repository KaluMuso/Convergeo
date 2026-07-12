> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** No migration (reuse `next_invoice_no`). Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-F — Invoice numbering not gapless (🟡 #3)

## Finding

`services/api/app/services/invoicing/builder.py:175` — `issue_receipt`/`issue_tax_invoice` call `allocate_invoice_number(series)` and then `_persist_invoice(payload)` as **two independent operations**. `allocate_invoice_number` (allocation.py:19) runs `SELECT public.next_invoice_no(series)` via `run_sql_script`, which spawns a standalone autocommitting psql process. If the subsequent invoice-row insert fails, the allocated number is already committed and lost → a GAP in the sequence. ZRA requires **gapless sequential invoice numbers**.

## Required fix

- **Allocate the number and insert the invoice row in ONE transaction** so a persist failure rolls back the number allocation (no gap). Options: (a) do `SELECT next_invoice_no(series)` and the `INSERT INTO invoices …` in a single `run_sql_script` BEGIN…COMMIT block; or (b) push both into one `SECURITY DEFINER` SQL function called once. Prefer (a) (no migration). Either way: number is consumed **iff** the invoice row is persisted.
- Money stays integer ngwee; invoice fields unchanged.

## Files (ONLY)

- Modify `services/api/app/services/invoicing/builder.py`, `services/api/app/services/invoicing/allocation.py`
- Add/extend `services/api/tests/test_invoicing.py` (or the existing invoicing test)
- **Do NOT touch** db.ts, migrations (reuse existing `next_invoice_no`), pdf.py/vsdc.py, other services.

## Tests (RUN)

Gaplessness under failure: allocate a number, force the invoice insert to fail → assert the sequence did NOT advance (the next successful invoice reuses that number; no hole). Happy path: sequential invoices are contiguous per series (min=1, max=count). **Full `uv run pytest`** + ruff + mypy.

## Report

STATUS/FILES/DEVIATIONS (how allocation + insert became one transaction) /TESTS (paste the failure-no-gap + contiguous-sequence + full-pytest tail) /EXCERPTS the combined allocate+insert transaction /QUESTIONS.
