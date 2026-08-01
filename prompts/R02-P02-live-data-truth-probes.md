> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P02 — Live data-truth probes (catalogue reachability) `[OPS]`

## 1. Context

**Wave R2-A.** Source: `docs/plan/r02/01-strategy-convergence.md` §1.4, §3.9 (row 9.8), §5.

`scripts/ops/verify_live.sh` proves the API is **up** and **at the expected commit**. It does not
prove the site has anything to sell. On **2026-08-01** every gate a human would read as "green" was
compatible with this live reality on `dpadrlxukcjbewpqympu`:

| Probe                                                           | Value        |
| --------------------------------------------------------------- | ------------ |
| `vendor_listings` where `status='active'`                       | 134          |
| …of those, **demo-tagged** (excluded from all public discovery) | **134**      |
| ⇒ publicly discoverable listings                                | **0**        |
| `vendor_locations`                                              | **0**        |
| `search_documents` with non-null `lat`+`lng`                    | **0 of 288** |

Demo exclusion is deliberate (D25 / VC-P06 — `app/services/search/__init__.py:410-411`,
`routers/catalog.py:499-502`, `supabase/migrations/0068_…:52-62`) and keys on
`listing_images.cloudinary_public_id` matching `demo`, `demo/%` or `%/demo/%`. It is **silent**: an
empty storefront and a healthy one look identical from every existing gate.

**Read this before scoping — four things already exist. Do not rebuild them:**

| Already implemented                                                          | Where                                      |
| ---------------------------------------------------------------------------- | ------------------------------------------ |
| `/fingerprint` returning `git_sha` / `image_tag` / `supabase_project_ref`    | `services/api/app/routers/health.py:33-47` |
| Deploy stamping `GIT_SHA` + `API_IMAGE_TAG` into the container               | `infra/redeploy-api.sh:33-61`              |
| **G9 fails on `SHA_UNKNOWN`** and on SHA mismatch                            | `scripts/ops/verify_live.sh:474-490`       |
| **G0 compares the live ledger to the repo** and checks FORCE RLS on 3 tables | `scripts/ops/verify_live.sh:252-270`       |

The `GIT_SHA=unknown` recorded on 2026-07-23 therefore means the **running container predates that
plumbing** — it is closed by re-deploying (operational step O2), **not** by writing code. Any change
to the fingerprint path in this pebble is out of scope and will be rejected in review.

**Type:** `[OPS]` — one bash script plus its runbook. **No application code, no migration, no
frontend.**

## 2. Objective & scope

Add the missing dimension — **is there anything reachable to buy?** — to the existing verifier, and
fix the one place where G0 reports a fact it cannot render meaningfully.

**In scope:**

1. A new **`DATA`** gate in the `verify_live.sh` matrix.
2. A correctness fix to `check_g0`'s reporting (specified in §4.2, designed in R02-P03).

**Non-goals — do NOT do these:**

- **Do not touch the fingerprint path** (`health.py`, `redeploy-api.sh`, `check_g1_api`, `check_g9`).
- **Do not write to the database.** Every probe is `SELECT`-only. No `INSERT`, `UPDATE`, `DELETE`,
  `CREATE`, or `SET` beyond a read-only transaction.
- **Do not apply migrations**, flip a flag, activate a workflow, or deploy.
- **Do not add a dependency.** `psql` + `curl` + bash, exactly as the script already assumes.
- Do not change any existing gate's PASS/FAIL semantics other than G0's **detail string and missing-set
  reporting** — G0's pass condition stays as it is.
- Do not edit `scripts/ops/launch_gates.sh` (separate orchestrator) or `scripts/ci/migration-replay.sh`
  (local replay, no live DB).

## 3. Files (modify/create ONLY these)

- `scripts/ops/verify_live.sh` — **you are the sole editor of this file this wave.**
- `docs/ops/deploy-verify-runbook.md` — document the new gate, its env knobs and how to read it.

**Guardrail: modify ONLY these two files.** R02-P03 depends on this pebble and edits neither.

## 4. Implementation spec

### 4.1 The `DATA` gate

Follow the file's existing idiom exactly: a `check_data()` function, `set_gate DATA PASS|FAIL|SKIP
"<detail>"`, registered in the gate list at `:534`, and honouring `--dry-run` (SKIP) the way
`check_g0` does at `:241-244`.

**Guard clauses first**, mirroring `check_g0:236-249`: SKIP when `SUPABASE_DB_URL` is unset, SKIP on
`--dry-run`, SKIP when `psql` is absent. A missing read-only DSN is not a failure.

**Probe three numbers in a single round trip** (one `psql -tA -c` with a single row, not three
connections):

- `discoverable_listings` — active listings that are **not** demo-tagged and **not** wholesale.
  Mirror the live rule rather than inventing one: demo is
  `lower(cloudinary_public_id) = 'demo' OR LIKE 'demo/%' OR LIKE '%/demo/%'` per
  `0068_…:59-62`; wholesale is `vendor_listings.wholesale = true` per D28.
- `vendor_locations` — total row count.
- `geo_coverage` — `search_documents` rows with non-null `lat` **and** `lng`, over the total.

**Thresholds, via env with documented defaults:**

| Knob                        | Default | Meaning                                        |
| --------------------------- | ------- | ---------------------------------------------- |
| `MIN_DISCOVERABLE_LISTINGS` | `1`     | below ⇒ **FAIL** — nothing is buyable          |
| `MIN_VENDOR_LOCATIONS`      | `1`     | below ⇒ **FAIL** — distance discovery is inert |
| `MIN_GEO_COVERAGE_PCT`      | `50`    | below ⇒ **WARN** in the detail, not a FAIL     |

Zero discoverable listings and zero locations are **failures, not warnings** — that is the whole point
of the gate. Partial geo coverage is a warning because a vendor mid-onboarding is a normal state.

**The detail string must be readable by a tired operator at 23:00.** Not `data=0/0/0`. Something like:

```
discoverable=0 (134 active, 134 demo-excluded, 0 wholesale-excluded) locations=0 geo=0/288 (0%)
```

The parenthetical is the part that prevents a wasted hour — an operator seeing `active=134` and
`discoverable=0` immediately knows the catalogue is demo-tagged, not missing.

### 4.2 The `check_g0` reporting fix

`check_g0:252-256` reads `max(version)` from `supabase_migrations.schema_migrations` and compares it
to the repo's last **filename prefix** (`REPO_MIGRATION_TIP`, `:93`).

Production's ledger does not use filename-shaped keys throughout: `0052` is stored as
`version=20260717100303, name=0052_product_relations`, and several rows are numerically out of order
(`0052` before `0051`, `0070` before `0069`). Because timestamp strings sort above `00…` strings,
`max(version)` returns `20260724080307`. The gate then prints
`live_tip=20260724080307 repo_tip=0079` — it fails, **correctly**, but names neither the problem nor
the remedy.

`schema_migrations` carries **both** `version` and `name`, so the numeric prefix is always recoverable.

- Derive each applied migration's numeric prefix from `name` when it matches `^[0-9]{4}`, else from
  `version`.
- Compare that **set** against the repo's filename prefixes.
- Report the **missing set explicitly**, truncated sensibly: `missing=0072,0073,0074,0075,0076,0077,0078,0079`.
- Keep reporting the raw `max(version)` alongside, labelled as such, so key-shape drift stays visible.
- **Do not change when G0 fails** — only what it says when it does. A behaviour change here would
  silently alter the go/no-go reading.

Verify your SQL against both shapes before reporting: the clean sequential ledger (`0001`…`0079`) and
the mixed ledger described above.

## 9. Security

- **Read-only.** Every statement is a `SELECT`. Prefer opening the session read-only where the
  script's existing `psql` idiom allows it.
- Never print `SUPABASE_DB_URL`, any DSN, key or token — the script's standing contract is "never
  prints secrets" (`:6`). Row counts are not secrets; connection strings are.
- No new network egress beyond the DB the script already contacts.
- Failure must be graceful: a `psql` error becomes `SKIP` with a reason, never an unhandled non-zero
  that aborts the whole matrix before later gates run.

## 10. Tests (RUN before reporting)

- `bash -n scripts/ops/verify_live.sh` (parse) and `shellcheck scripts/ops/verify_live.sh` if
  available — no new warnings versus the pre-change baseline.
- `bash scripts/ops/verify_live.sh --dry-run` — matrix prints, `DATA` reports SKIP, exit code
  unchanged from baseline.
- `bash scripts/ops/verify_live.sh` with `SUPABASE_DB_URL` **unset** — `DATA` SKIPs with a reason;
  the script does not abort.
- Against a local/disposable Postgres seeded to mimic each case, paste the resulting detail line:
  1. zero discoverable listings ⇒ `DATA FAIL`;
  2. some discoverable listings and locations ⇒ `DATA PASS`;
  3. listings present but geo coverage under the floor ⇒ `PASS` with a coverage warning.
- G0 reporting proved against **both** ledger shapes (clean and mixed), pasting the detail string for
  each.
- Confirm the existing gates' statuses are byte-identical to baseline on a dry run.

## 11. Acceptance criteria / DoD

- [ ] `DATA` gate registered in the matrix, honouring `--dry-run` and the missing-DSN SKIP path.
- [ ] Probes are `SELECT`-only, in a single round trip, and mirror the live demo/wholesale rules by
      reference rather than by a re-invented predicate.
- [ ] Zero discoverable listings ⇒ **FAIL**; zero `vendor_locations` ⇒ **FAIL**; low geo coverage ⇒
      warning only. All three demonstrated.
- [ ] Detail string names the _cause_ (active vs demo-excluded vs wholesale-excluded), not just totals.
- [ ] `check_g0` reports the **missing migration set**; verified against both ledger shapes; its
      **pass/fail condition is unchanged**.
- [ ] No secret, DSN, key or token printed on any path.
- [ ] `health.py`, `infra/redeploy-api.sh`, `check_g1_api`, `check_g9` **not modified**
      (`git diff --exit-code` on those paths).
- [ ] Nothing applied, deployed, seeded, flipped or activated by this pebble.
- [ ] Runbook documents the gate, the three env knobs, their defaults, and how to read the output.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** R02-P02 — Live data-truth probes (catalogue reachability)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the `--dry-run` matrix and the three seeded-case detail lines
**EXCERPTS:** the `DATA` probe SQL, and the G0 missing-set SQL with its output on both ledger shapes
**SECRETS:** confirm explicitly that no DSN/key/token is printed on any path, including error paths
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
