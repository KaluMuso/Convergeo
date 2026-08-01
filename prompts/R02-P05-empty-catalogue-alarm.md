> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P05 — Empty-catalogue alarm (admin)

## 1. Context

**Wave R2-B.** Source: `docs/plan/r02/01-strategy-convergence.md` §1.4, §5.

"Zero publicly discoverable listings" is currently indistinguishable from "everything is fine". It was
discovered on **2026-08-01** by running ad-hoc SQL during a discovery session — not by any dashboard,
alert or gate. Verified read-only on production `dpadrlxukcjbewpqympu` that day:

| Probe                                                  | Value        |
| ------------------------------------------------------ | ------------ |
| `vendor_listings` where `status='active'`              | 134          |
| …demo-tagged, therefore excluded from public discovery | **134**      |
| ⇒ publicly discoverable                                | **0**        |
| `vendor_locations`                                     | **0**        |
| `search_documents` with non-null `lat`+`lng`           | **0 of 288** |

The admin dashboard already aggregates the platform's other truths — GMV, orders by status, payout
liabilities, reconciliation, AI spend, a funnel snapshot — in `build_dashboard`
(`services/api/app/routers/admin_dashboards.py:322`), behind a short cache
(`_get_cached_dashboard:340`, `clear_dashboard_cache:106`). Catalogue reachability is the one number
missing, and it is the one that decides whether anything else on the page can happen at all.

**Type:** `[CODE]` — API + admin app. **No migration.**

## 2. Objective & scope

Make an unreachable catalogue impossible to miss from the admin dashboard.

**Non-goals — do NOT do these:**

- **Do not change any exclusion rule.** Report what the rules already do.
- **Do not add notifications, WhatsApp alerts, or n8n workflows.** This is a dashboard tile. Paging
  someone is a separate decision with its own consent and quiet-hours rules (D15, dispatcher).
- **Do not touch `routers/vendor_listings*.py` or the vendor app** — R02-P04 owns those.
- **Do not touch `scripts/ops/verify_live.sh`** — R02-P02 owns it. The two read the same rules and
  report to different audiences; neither calls the other and neither is the other's source of truth.
- Do not add a migration, a stored counter, or a dependency. Compute live.
- Do not restructure `build_dashboard` or the cache — add to them.

## 3. Files (create/modify ONLY these)

- `services/api/app/routers/admin_dashboards.py`
- `services/api/tests/test_admin_dashboard_catalogue.py` **(new)**
- `apps/admin/app/[locale]/page.tsx` and/or `apps/admin/app/[locale]/_components/**` — the tile.
- `packages/i18n/messages/en/admin.json` — new keys under a single new `dashboard.catalogue.*` subtree.
  **English only** — `bem`/`nya` have no `admin.json` by design (operator-facing; see R02-P08).

**Guardrail: modify ONLY these files.**

## 4. Implementation spec

1. **Three numbers, computed live** in the style of the existing `_count_table` / `_orders_by_status`
   helpers:
   - **publicly discoverable listings** — active, not demo-tagged, not wholesale-only. Mirror the
     live rules by reusing `app/services/listings/demo.py` rather than re-deriving the prefix test;
     wholesale is `vendor_listings.wholesale` per D28.
   - **vendor locations** — total rows.
   - **search geo coverage** — `search_documents` with non-null `lat` **and** `lng`, over total.

2. **The tile must show the arithmetic, not just the answer.** `0 discoverable` alone sends an admin
   hunting. `0 discoverable — 134 active, 134 demo-excluded, 0 wholesale-gated` ends the hunt in one
   read. The decomposition is the feature.

3. **Severity.** Zero discoverable listings or zero vendor locations reads as an **alarm** state, not a
   neutral statistic — use the existing token-driven warning treatment, no ad-hoc colours. Low geo
   coverage is informational: a vendor mid-onboarding is normal.

4. **Cache.** Reuse the existing dashboard cache rather than adding a second one, and make sure the
   new queries do not turn a cached page into three extra round trips per request. Keep the count
   queries cheap — `count(*)` with the existing indexes, no sequential scan over `search_documents`
   joins.

5. **Honesty about demo data.** The tile is the natural place to state plainly that demo listings are
   excluded from public discovery **by design (D25 / VC-P06)** — so an admin reading `134 active,
0 discoverable` understands this is the system working, not a fault. One sentence, in i18n copy.

## 9. Security

- Admin-only, behind the existing `admin_base` mount and its role check — do not weaken it. Cloudflare
  Access still fronts the origin (D33); this tile is not a reason to expose anything publicly.
- No PII: counts only. Do not surface vendor names, listing titles or user identifiers in the tile.
- Add no route if the existing dashboard endpoint can carry the payload — then
  `core/ratelimit_policies.py` needs no row and the M15-P04 startup assert stays satisfied. If you
  must add one, add its policy row in the same diff and say so.

## 10. Tests (RUN before reporting)

- `uv run pytest services/api/tests/test_admin_dashboard_catalogue.py` — cover: all-demo catalogue ⇒
  discoverable 0 with the decomposition correct; mixed catalogue ⇒ correct split; wholesale-only
  listing excluded from discoverable but counted as wholesale-gated; zero locations ⇒ alarm state.
- `uv run pytest services/api/tests/test_admin_dashboards.py` (or existing) — no existing tile changed.
- `uv run ruff check .` · `uv run mypy app tests scripts`
- `pnpm test --filter admin` · `pnpm lint` · `pnpm typecheck`
- Confirm the dashboard's query count did not grow per request beyond the new counts — state the
  before/after in the report.

## 11. Acceptance criteria / DoD

- [ ] Three numbers on the dashboard, computed live, reusing `demo.py` rather than re-deriving the rule.
- [ ] The tile shows the decomposition (active / demo-excluded / wholesale-gated), not just a total.
- [ ] Zero discoverable **or** zero locations renders as an alarm state using existing design tokens.
- [ ] One line of copy stating demo exclusion is by design (D25 / VC-P06).
- [ ] Reuses the existing dashboard cache; no second cache; query count reported.
- [ ] Zero hardcoded user-facing strings; keys under `dashboard.catalogue.*` in EN `admin.json` only.
- [ ] No migration, no stored counter, no notification, no n8n workflow, no dependency.
- [ ] `scripts/ops/verify_live.sh`, `routers/vendor_listings*.py` and the vendor app untouched.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** R02-P05 — Empty-catalogue alarm (admin)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the pytest/vitest summary lines
**EXCERPTS:** the three count queries and the tile's rendered copy in the alarm state
**QUERY COUNT:** dashboard round trips before vs after
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
