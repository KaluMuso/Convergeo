# Admin console audit (origin/master 0bb3243f) - read-only

Method: cross-checked every `/admin/...` fetch path in apps/admin against FastAPI decorators in services/api/app/routers/admin_*.py (static regex; ~190 routes). No dead endpoints or method mismatches found (only false positives from template-literal parsing). Findings below are UX/visual/operator-flow. Known items (analytics stuck loading, moderation similar-products category UUID) excluded.

Paths are relative to apps/admin/app/[locale]/ unless noted.

## Top 15 (ranked by operator impact)

1. **Primary buttons invisible in dark mode (white on near-white).** In dark theme `--primary` is #fafafa (also #5fc49c/#60a5fa/#fbbf24 in accent themes) but 15 files hardcode `bg-primary ... text-white`. Affects Save/Confirm on all Config editors (zones, area pricing, categories, commissions, platform, diff-confirm dialog, tab bar), Merch, merge-confirm, related-products save, dispatch board/card/courier manager, support send/reply. Fix: replace with `adminPrimaryButtonClass` (`_components/admin-primary-button.ts`) or `text-[var(--primary-btn-fg)]` (token already exists, used in ConfirmModal). Files: config/_components/{DeliveryZoneEditor,AreaPricingEditor,ConfigPageShell,ConfirmDiffDialog,CategoryTreeEditor,CommissionEditor,PlatformEditor}.tsx, merch/_components/MerchBoard.tsx, moderation/products/_components/{MergeConfirmDialog,RelatedProductsEditor}.tsx, orders/_components/{DispatchBoard,CourierManager,DispatchCard}.tsx, support/_components/{SupportInbox,ReplyComposer}.tsx. (FlagActionDialog L77 and OffersBoard L345 use conditional `text-white` too - check the non-danger branch.)
2. **Roles: assign admin role by pasting a raw account UUID, assignments listed as `<code>uuid</code> · role`.** Operator cannot tell who holds a role; superadmin confirm prompt also shows UUID. Fix: add `GET /admin/accounts/lookup?q=` (email/name/phone, superadmin) or reuse profiles search; picker in roles-board; join display_name/email into assignments response. Files: roles/roles-board.tsx, services/api/app/routers/admin_roles.py, lib/roles-api.ts.
3. **Audit log shows raw actor UUID and entity UUID; filters require UUIDs.** `{actor}` and `entity_id` printed directly; `buildAuditQuery` rejects non-UUID input, so "who did X" needs UUID copy/paste. Fix: API enriches `actor_name/actor_email` (and entity label for vendor/product/order) on AuditEntryOut; UI shows name + small UUID; actor filter accepts email/name (resolve server side); add CSV export optional. Files: audit-log/audit-log-board.tsx, services/api/app/routers/admin_audit_log.py.
4. **Orders page is a blank search form; no recent/needs-attention list.** `/admin/orders/search` returns 422 when no criteria, so landing shows nothing; results show only vendor + phone + raw order UUID (`font-mono`), no total, status chip, date, buyer name. Fix: default to latest 50 (relax the 422 guard, order by created_at desc), add status/total/created columns and short order ref, add "load more" cursor. Files: orders/_components/OrderSearch.tsx, services/api/app/routers/admin_orders.py (search handler ~L320-420).
5. **Destructive actions styled with nonexistent `text-error` token + native `window.confirm`.** `--color-error` is not defined (theme uses `danger`), so Deactivate account, Revoke role, Delete role render as plain underlined text, not red; confirmations use browser `confirm()` (no reason, not themed, blocked in some embeds). Also Home-feed delete uses `window.confirm`. Fix: `text-danger` + shared `ConfirmModal` (`_components/ConfirmModal.tsx`, already supports destructive + reason). Files: roles/roles-board.tsx, accounts/accounts-board.tsx, home-feed/_components/HomeFeedBoard.tsx (L209), merch/_components/MerchBoard.tsx.
6. **Role and account lists use bare `rounded border` (default currentColor border) and ad-hoc `p-3` cards.** Harsh black/white borders, inconsistent with `border-border bg-surface` used elsewhere; roles/accounts/audit pages look unthemed. Fix: swap to token classes (`border border-border bg-surface rounded-lg`), inputs get `border-border bg-surface`. Files: roles/roles-board.tsx, accounts/accounts-board.tsx, audit-log/audit-log-board.tsx (about 12 occurrences).
7. **Catalog oversight (Services, Inventory) silently truncate at 100 rows with no search/pagination/status filter.** `.limit(100)` in admin_catalog_oversight.py; `_components/oversight-list.tsx` is a plain `<ul>` of `String(item.id)` fallbacks (title may fall back to the UUID). Fix: add `q`, `status`, `limit/offset` (or cursor), "showing N of M" and a search box; never fall back to id for title (use "Untitled"). Files: _components/oversight-list.tsx, services/page.tsx, inventory/page.tsx, services/api/app/routers/admin_catalog_oversight.py.
8. **Lists capped without any pagination: Business (100), Extras requests (200), Trials (200), Branches (200), Support lookups (20-50), Orders (50).** No "next page", no total, operator cannot know rows are hidden. Fix: return `{items,total,next_cursor}` and add shared "Load more" (audit-log already has `next_before` pattern to copy). Files: business/_components/BusinessQueue.tsx + api.ts, extras/_components/ExtrasQueue.tsx, trials/_components/TrialsBoard.tsx, branches/_components/BranchQueue.tsx; routers admin_business.py, admin_extras.py, admin_branches.py.
9. **Accounts directory: no search, no pagination, shows `user_id` UUID line under every name, deactivation reason input is per-row inline with no modal summary.** Fix: add search box (name/email/role), paginate, hide UUID behind copy button (`_components/CopyButton.tsx` exists), move reason into ConfirmModal. Files: accounts/accounts-board.tsx, services/api/app/routers/admin_accounts.py.
10. **Vendor shown as raw UUID in event advance debts, clip pilot, and compare cards.** AdvanceDebts L193 prints `debt.vendor_id` only (no name returned); ClipPilotPanel prints id as second line (name fallback OK); moderation ProductCompareCard prints `category_id` UUID (category similar-products known, but the compare card field is the same bug class: verify it is covered). Fix: API returns `vendor_display_name` for debts; UI shows name, id behind CopyButton. Files: events/_components/AdvanceDebts.tsx, services/api/app/routers/admin_event_advance_debts.py, clips/_components/ClipPilotPanel.tsx.
11. **Decision flows without mandatory reasons / uneven confirmation.** Reason required on KYC/disputes/business reject/trials, but not enforced on: coupons (platform) disable, home-feed delete, merch slot publish, catalog restore, flags dismiss (verify FlagActionDialog). Define one rule: any state change that is customer/vendor-visible or irreversible requires reason >=3 chars + modal summary. Files: coupons/admin-coupons.tsx (shared CouponManager in packages/ui), home-feed/_components/HomeFeedBoard.tsx, catalog/_components/CatalogControlBoard.tsx.
12. **Desktop ops density: single-column card lists and `max-w-3xl` pages.** Coupons wraps in `max-w-3xl`; roles/accounts/audit use stacked `<li>` cards instead of tables, so 1440px screens show a narrow column with big whitespace; KYC/disputes/orders use tables (good) - align the rest. Fix: table layout with sticky header for roles assignments, accounts, audit log (columns: time, actor, action, entity, outcome; expandable diff row). Files: audit-log/audit-log-board.tsx, accounts/accounts-board.tsx, roles/roles-board.tsx, coupons/admin-coupons.tsx.
13. **Accessibility gaps on custom dialogs.** Hand-rolled modals (FlagActionDialog, PendingCanonicalQueue overlay, OffersBoard confirm, ConfirmDiffDialog, mobile nav drawer) use `fixed inset-0 bg-black/40`; verify focus trap, Escape, `aria-modal`, return focus (only ConfirmModal is the reference implementation). Fix: route all through one `<Dialog>`/ConfirmModal. Files: moderation/flags/_components/FlagActionDialog.tsx, moderation/products/_components/PendingCanonicalQueue.tsx, offers/_components/OffersBoard.tsx, config/_components/ConfirmDiffDialog.tsx.
14. **Tables lack sortable/filterable headers and sticky headers; queues cannot be searched.** KYC queue, dispute queue, flags queue have no search by vendor name and no sort besides disputes (age/value). Fix: client-side filter input + sort on SLA/submitted for first 100 rows; sticky `thead`. Files: kyc/_components/KycQueue.tsx, disputes/_components/DisputeQueue.tsx, moderation/flags/_components/FlagQueue.tsx.
15. **Audit-log "details" is raw JSON dump.** `<pre>` of before/after with no diff highlight; hard to scan. Fix: render changed keys only (before -> after) with a "raw" toggle. File: audit-log/audit-log-board.tsx.

## Batch assignment (exclusive file ownership)

### Batch A - dark-mode button fix + token cleanup (15 files, no new i18n keys, no API)
Items 1, 6 (token parts), 13 partial (ConfirmDiffDialog only).
- config/_components/DeliveryZoneEditor.tsx
- config/_components/AreaPricingEditor.tsx
- config/_components/ConfigPageShell.tsx
- config/_components/ConfirmDiffDialog.tsx
- config/_components/CategoryTreeEditor.tsx
- config/_components/CommissionEditor.tsx
- config/_components/PlatformEditor.tsx
- merch/_components/MerchBoard.tsx
- moderation/products/_components/MergeConfirmDialog.tsx
- moderation/products/_components/RelatedProductsEditor.tsx
- orders/_components/DispatchBoard.tsx
- orders/_components/CourierManager.tsx
- orders/_components/DispatchCard.tsx
- support/_components/SupportInbox.tsx
- support/_components/ReplyComposer.tsx
Add a vitest/grep guard (new test file under apps/admin/lib) that fails on `bg-primary` + `text-white` in the same className.

### Batch B - operator flows: roles/accounts/audit/orders/oversight (15 files)
Items 2, 3, 4, 5, 6, 7, 9, 10, 12, 15 (items 8, 11, 13-14 deferred to a follow-up wave).
- roles/roles-board.tsx
- lib/roles-api.ts
- accounts/accounts-board.tsx
- audit-log/audit-log-board.tsx
- orders/_components/OrderSearch.tsx
- _components/oversight-list.tsx
- events/_components/AdvanceDebts.tsx
- moderation/flags/_components/FlagActionDialog.tsx
- offers/_components/OffersBoard.tsx
- services/api/app/routers/admin_roles.py
- services/api/app/routers/admin_accounts.py
- services/api/app/routers/admin_audit_log.py
- services/api/app/routers/admin_orders.py
- services/api/app/routers/admin_catalog_oversight.py
- packages/i18n/messages/en/admin.json (sole owner of i18n edits; add keys for the new search/picker/empty states, mirror to other locales if the sweep requires)
(FlagActionDialog and OffersBoard are in B because of the conditional `text-white` on non-danger branch plus dialog a11y; A must not touch them.)

Deferred wave C (not in batches): items 8, 11, 13, 14 (pagination for business/extras/trials/branches, reason enforcement on coupons/home-feed/catalog, shared dialog a11y, queue search/sort).

Caveats: findings 8, 11, 13, 14 and the FlagActionDialog/OffersBoard branches were identified by pattern scan, not line-by-line verification; confirm before implementing. Analytics pages, clips detail, KYC doc viewer, dispute evidence viewer, merch editors and translations were not deeply audited.
