# Document Audit Contract — Vergeo5 / Convergeo

**Audit date:** 2026-07-18  
**Mode:** READ-ONLY production readiness baseline  
**Audience:** Parallel document-audit sessions comparing business/source documents against the live platform

This contract is mandatory for every subsequent audit row. Do not invent evidence. Do not treat repository HEAD, migration files, or docs as deployed reality without a live check.

---

## 1. Evidence labels

| Label             | Meaning                                                                                                                                                                | When to use                                                 |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| **VERIFIED**      | Direct live evidence confirms the fact (HTTP response, Vercel deployment metadata, applied migration row, n8n workflow state, read-only SQL aggregate, or equivalent). | Prefer this. Cite the exact probe.                          |
| **PARTIAL**       | Some supporting evidence exists, but a conclusive claim requires another check or access.                                                                              | State what is proven and what is still open.                |
| **MISSING**       | The expected artifact/feature/workflow/config is absent where it should exist.                                                                                         | Cite the empty search / empty registry / 404 / disabled UI. |
| **CONFLICT**      | Two or more evidence sources disagree.                                                                                                                                 | Cite both sides; do not pick a winner without hierarchy.    |
| **NOT_AUDITABLE** | Access, credentials, or observability required for a safe conclusive check is unavailable.                                                                             | Record the exact missing access — never assume.             |

Rules:

- Never mark a known risk **resolved** without **VERIFIED** live evidence that the failure mode cannot occur.
- Repository implementation alone may support **PARTIAL** (code path exists / missing), never **VERIFIED** for production behavior.
- Documentation alone is never **VERIFIED**.

---

## 2. Source-of-truth hierarchy

When sources disagree, prefer higher ranks:

1. **Live database / API / deployment evidence**  
   Applied migrations, HTTP health, public catalog responses, Vercel production deployment SHAs, n8n active workflow list, Cloudflare/Access responses.
2. **Applied migrations and infrastructure configuration**  
   `supabase_migrations.schema_migrations`, Vercel project domains, compose/Caddy/env _names_ (not values), GHCR image tags when readable.
3. **Repository implementation**  
   `apps/*`, `services/api`, `packages/*`, `infra/n8n/*.json`, workflow YAML, tests.
4. **Documentation**  
   `docs/plan/*`, `docs/ops/*`, `README.md`, launch checklists, distilled concept docs.

If (1) is unavailable for a claim, label **NOT_AUDITABLE** (or **PARTIAL** if (2)/(3) still constrain the claim).

---

## 3. Standard row format

Every requirement or inventory record MUST use this row shape:

| Column                      | Description                                                                     |
| --------------------------- | ------------------------------------------------------------------------------- |
| **source reference**        | Business doc path/page, ticket, decision ID, or prior audit ID                  |
| **extracted fact**          | Atomic claim copied/paraphrased from the source (no secrets/PII)                |
| **target entity/table/API** | Table, route, app, workflow, or env _name_                                      |
| **matching key**            | Stable join key (slug, migration version, workflow id, flag name, route path)   |
| **evidence**                | Probe result summary + pointer (URL path, query name, deployment id) — redacted |
| **status**                  | `VERIFIED` \| `PARTIAL` \| `MISSING` \| `CONFLICT` \| `NOT_AUDITABLE`           |
| **impact**                  | User/money/security/ops consequence if wrong or absent                          |
| **recommended action**      | Smallest safe next step                                                         |
| **owner**                   | Founder / eng surface / ops                                                     |

Markdown table template:

```md
| source reference       | extracted fact | target entity/table/API | matching key | evidence | status   | impact | recommended action | owner |
| ---------------------- | -------------- | ----------------------- | ------------ | -------- | -------- | ------ | ------------------ | ----- |
| D18 / launch-checklist | …              | …                       | …            | …        | VERIFIED | …      | …                  | …     |
```

---

## 4. Data classes

Classify every audited fact into exactly one class:

1. **Requirements / policies** — decisions, compliance, escrow rules, COD caps, feature flags, launch gates.
2. **Master records** — customers/profiles, vendors, products/catalogue, categories, ticket types (identity of sellable things).
3. **Operational records** — orders, payments, deliveries/pickup, tickets issued, payouts, disputes, ledger transactions.
4. **Documents / media** — KYC docs, invoices, listing images, Cloudinary public IDs, private storage buckets.
5. **Role / access requirements** — RBAC roles, RLS policies, admin Access, internal tokens, who may read/write what.

---

## 5. Privacy & safety rules

- **READ-ONLY only.** No INSERT/UPDATE/DELETE/migrate/seed/deploy/rotate/trigger-payment/activate-workflow.
- **Never print** secrets, tokens, passwords, private URLs with credentials, full customer PII, payment references (`ord-*`/`pay-*`/`rfd-*` values), or raw row dumps.
- SQL: prefer `BEGIN READ ONLY;` + narrowly scoped `SELECT` aggregates / `information_schema` / `pg_catalog`.
- Redact phones, emails, addresses, landmarks, GPS, NRC, TPIN, MoMo MSISDNs in all reports.
- Money: report counts and ngwee aggregates only when necessary; never dump ledger lines with references.
- Prefer least-privilege / service catalog APIs over direct DB when sufficient.

---

## 6. Session hygiene for parallel audits

- Branch from / compare against this dated folder: `docs/production-readiness/2026-07-18/foundation/`.
- Do **not** overwrite these foundation files; add dated follow-ups under a new path or `…/follow-ups/`.
- Re-run the safe command pack in `executive-baseline.md` at session start; record new evidence timestamps.
- If production diverges from this baseline, open a **CONFLICT** row rather than silently editing the baseline.
