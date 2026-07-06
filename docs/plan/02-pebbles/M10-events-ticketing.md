# M10 — Events & Ticketing — Pebbles

9 pebbles. Dynamic QR = HMAC over rotating 60s windows, ±1 window tolerance; scanner is offline-first PWA; oversell impossible at capacity. Events browse/detail display shipped in M05-P11 — M10 owns organiser flows, purchase, wallet, scanning.

---

### M10-P01 — Organiser event CRUD `M`
**Deps:** M03-P03, M12-P02 (KYC reuse) · **Files:** `apps/vendor/app/events/page.tsx` (list), `events/new/page.tsx`, `events/[id]/edit/page.tsx`, `services/api/app/routers/organiser_events.py`, `packages/i18n/messages/en/events.json` gains organiser keys (**sequenced after M05-P11's wave**)
Organiser flag on KYC'd vendors; event create/edit: title, category (6), venue + lat/lng + landmark, images (Cloudinary ≤8), description, instances (date/time, capacity); publish flow (draft→published→ended|cancelled); edit restrictions after sales exist (venue/date changes flag ticket-holder notification).
**AC:** non-KYC vendor cannot create; post-sale date change triggers notification event; instance capacity ≥ sold count enforced on edit.
**Tests:** authz, edit-restriction matrix, publish validation (past date rejected).

### M10-P02 — Ticket types & oversell-safe inventory `M`
**Deps:** P01 · **Files:** `services/api/app/services/tickets/inventory.py` (atomic capacity claims per instance+type), `app/routers/ticket_types.py`, `apps/vendor/app/events/[id]/tickets/page.tsx` (type config UI)
Types per D2: fixed price, multi-tier (e.g. Standard/VIP), free RSVP; per-type qty caps + per-instance capacity; **atomic claim** (same pattern as M07-P02) — no oversell at boundary under concurrency; per-customer purchase cap option.
**AC:** race test: capacity-1 with two concurrent buyers → exactly one ticket; tier prices ngwee; free type = 0 ngwee (not null).
**Tests:** concurrency at capacity boundary, cap per customer, tier config validation.

### M10-P03 — Purchase & RSVP through checkout `L`
**Deps:** P02, M07-P06, M08 (core done) · **Files:** `services/api/app/services/tickets/purchase.py` (cart integration: item_kind=ticket, claim on checkout, issue on payment success; **free RSVP path skips payment**, still issues tickets + order record), purchase CTA wiring `apps/customer/app/[locale]/(shop)/e/[slug]/_components/ticket-picker.tsx` (replaces M05-P11 stub), `services/api/tests/test_ticket_purchase.py`
Commission: 5% paid tickets, **0% free events** (snapshot per M08-P12); tickets issued only after verified payment (or immediately for RSVP); capacity claim honors reservation TTL.
**AC:** payment failure releases claimed capacity; RSVP capped by capacity; issued ticket count = paid qty exactly (idempotent webhook replay safe).
**Tests:** failure-release, RSVP flow, idempotent issuance on webhook replay, commission 0% free.

### M10-P04 — Ticket wallet (dynamic QR + PIN) `L`
**Deps:** P03 · **Files:** `services/api/app/services/tickets/qr.py` (**HMAC(ticket_secret, floor(now/60s)) rotating code**; payload: ticket id + window counter + sig), `app/routers/ticket_wallet.py`, `apps/customer/app/[locale]/account/tickets/page.tsx` (wallet list), `tickets/[id]/page.tsx` (live QR w/ 60s progress ring, 6-digit PIN backup, event info), PWA cache rules for wallet route (serwist config fragment `apps/customer/sw-wallet.ts`)
Wallet **offline-viewable** — but the ticket secret NEVER ships to the client: offline mode shows **pre-generated window codes for a bounded horizon** (server issues the next N window tokens on each sync) + PIN fallback. A screenshot of a QR dies with its 60s window.
**AC:** QR changes every 60s; stale screenshot fails verify (P06 test); offline wallet shows valid codes for the cached horizon + degrades to PIN; other users' tickets inaccessible.
**Tests:** rotation timing, horizon expiry behavior, RLS on wallet, transfer-state rendering.

### M10-P05 — Organiser scanner PWA `L`
**Deps:** P04, P06 · **Files:** `apps/vendor/app/events/[id]/scan/page.tsx`, `scan/_components/` (camera scanner, result flash green/red + count), `apps/vendor/app/events/[id]/scan/_lib/offline-store.ts` (IndexedDB: ticket verification cache synced pre-event, pending check-in queue), serwist config fragment `apps/vendor/sw-scanner.ts`
Offline-first: pre-event sync downloads instance's ticket verification data (ids + secrets server-side-derived window hashes for the event horizon); offline scans validated locally, queued, **first-scan-wins** reconciled on sync; live check-in count (online) / local count (offline); clock-skew tolerance ±1 window.
**AC:** airplane-mode scan works end-to-end; duplicate scan (either device) flagged red on reconcile; skewed-clock device (±60s) still validates.
**Tests:** offline validate/queue/sync cycle, first-scan-wins conflict (two devices same ticket), skew simulation.

### M10-P06 — Verify API & check-in `L`
**Deps:** P04 · **Files:** `services/api/app/routers/ticket_verify.py` (organiser-scoped: QR window validation ±1, PIN fallback, **atomic single-use check-in**, batch endpoint for offline-queue sync w/ first-scan-wins resolution), `services/api/tests/test_ticket_verify.py`
Organiser can verify only own events' tickets; check-in transitions ticket status atomically; batch sync resolves conflicts deterministically (earliest scan timestamp wins, later flagged duplicate).
**AC:** window ±1 accepted, ±2 rejected; concurrent verify races → one check-in; batch replay idempotent; screenshot-after-60s fails (integration with P04).
**Tests:** window matrix, race, batch conflict resolution + idempotency, cross-organiser denial, void/transferred ticket rejection.

### M10-P07 — Transfer-to-friend `M`
**Deps:** P04 · **Files:** `services/api/app/routers/ticket_transfer.py` (initiate by phone number, until T-6h; recipient claims on signup/login; **old QR/PIN void, reissued secret**), `apps/customer/app/[locale]/account/tickets/[id]/transfer/page.tsx`, transfer-claim banner `apps/customer/app/[locale]/account/tickets/_components/claim-banner.tsx`
No resale (D2 scope): free transfer only, one pending transfer at a time, cancellable before claim; notifications via outbox.
**AC:** original ticket unusable post-claim (verify rejects); T-6h cutoff enforced; unclaimed transfer cancellable; checked-in ticket untransferable.
**Tests:** cutoff boundary, void-after-claim verify rejection, double-transfer guard, claim by new-signup phone.

### M10-P08 — Organiser dashboard-lite & event escrow timing `M`
**Deps:** P03, P06, M08-P08 · **Files:** `apps/vendor/app/events/[id]/dashboard/page.tsx` (sales by type, revenue ngwee→formatK, check-in progress live-ish poll), `services/api/app/routers/organiser_stats.py`, `app/services/escrow/event_release.py` (D5: **event ≤14d out → release T+24h post-event; further out → 50% at T-7d, 50% at T+1d**; cancellation → refund-all path hook)
Escrow timing rules plug into M08-P08 engine as event-kind rules; organiser sees pending/released split.
**AC:** both timing branches post correct ledger transactions on schedule; cancelled event blocks releases + flags mass refund (admin-executed); stats match ticket truth.
**Tests:** timing rule matrix (13d vs 15d out), cancellation hold, stats aggregation.

### M10-P09 — Events SEO & discovery polish `S`
**Deps:** P03, M05-P09 · **Files:** `apps/customer/app/[locale]/(shop)/e/[slug]/_components/event-jsonld.tsx` (Event schema w/ offers, availability, performer/organiser), sitemap events chunk update `apps/customer/app/sitemap-events.ts` (new file), calendar `.ics` download endpoint `services/api/app/routers/event_ics.py`
Event JSON-LD (validates in Rich Results), ticket availability signals, `.ics` add-to-calendar, past-event pages marked (noindex after +30d).
**AC:** Rich Results test passes for paid + free fixture events; ics imports correctly (Google/Outlook); sold-out reflected in offers availability.
**Tests:** JSON-LD goldens (ngwee→decimal ZMW offers), ics format, noindex logic.
