# M11 — Services & RFQ — Pebbles

6 pebbles. Deliberately thin (D2): post-a-job → quotes → accept → deposit/balance via escrow. Reuses M05 discovery, M08 money, M09 states. Owns i18n namespace `services`.

---

### M11-P01 — Service listings & provider profiles `M`
**Deps:** M03-P03, M05-P05/P08 · **Files:** `apps/customer/app/[locale]/(shop)/services/page.tsx` (browse: 8 service verticals, area filter), `(shop)/s/[slug]/page.tsx` (detail: portfolio gallery, service area, from-price optional, response-time badge, request-quote CTA), vendor-side `apps/vendor/app/services/page.tsx` (+new/edit), `services/api/app/routers/services_listings.py`, `packages/i18n/messages/en/services.json`
Provider profile enhancements: response-time badge computed from quote history (median first-response, updated nightly); services flow into `search_documents` (triggers exist — verify projection).
**AC:** from-price optional renders "from K__" or "ask for quote"; badge tiers (fast <2h / same-day / slow) correct; searchable in unified search.
**Tests:** badge computation fixtures, browse filters, RLS (draft services hidden).

### M11-P02 — Post-a-job (RFQ) `M`
**Deps:** P01, M04-P04 · **Files:** `apps/customer/app/[locale]/(shop)/services/post-job/page.tsx` (near-zero-friction form: description, category, preferred date, budget band, photos optional), `services/api/app/services/rfq/broadcast.py` (**match by category + service-area, cap ~8 providers**, notify via outbox), `app/routers/jobs.py`, `services/api/tests/test_rfq.py`
Job lifecycle (open→quoted→accepted→completed|cancelled|expired 7d); broadcast selection: matching providers ranked by badge/rating/proximity, capped (config); guest can draft, must auth to post.
**AC:** cap respected; no matching providers → honest "we'll notify you" + admin visibility; job expiry auto-closes with notice.
**Tests:** matching/cap logic, expiry job, authz (only owner sees own job details pre-quote).

### M11-P03 — Quotes: submit, inbox, compare `M`
**Deps:** P02 · **Files:** `apps/vendor/app/jobs/page.tsx` (matched-jobs inbox + quote form: amount, message, validity), `services/api/app/routers/quotes.py`, customer compare UI `apps/customer/app/[locale]/account/jobs/page.tsx` + `jobs/[id]/page.tsx` (quote cards side-by-side: price, rating, badge, response time)
**Providers can never see rivals' quotes** (RLS from M03-P03 + API tests); customer compares; decline-with-reason optional; quote withdrawal before acceptance.
**AC:** rival-quote isolation proven at API layer too; compare sorts by price/rating; withdrawn quotes drop from compare.
**Tests:** isolation (provider A fetches job quotes → own only), quote validity expiry, compare ordering.

### M11-P04 — Accept → deposit & balance via escrow `L`
**Deps:** P03, M08-P05/P08/P12 · **Files:** `services/api/app/services/rfq/engagement.py` (accept → order with item_kind=service_deposit; deposit % config, default from D2 model; balance order item on completion; **12% commission basis on total job value**, snapshot), acceptance UI `apps/customer/app/[locale]/account/jobs/[id]/_components/accept-flow.tsx`, `services/api/tests/test_service_escrow.py`
Accept creates the money spine: deposit through standard checkout/payment (M07/M08 reuse); provider notified; completion (P05) triggers balance request → payment → escrow release per rules.
**AC:** commission = 12% of deposit+balance exactly once (not double-counted); deposit refundable per dispute rules pre-work; ledger balanced across both legs.
**Tests:** two-leg commission math, cancellation-after-deposit refund path, snapshot immunity.

### M11-P05 — Completion, confirmation & review `M`
**Deps:** P04, M09-P06 pattern, M15-P01 (review write API — if not yet merged, ship behind interface) · **Files:** `services/api/app/routers/job_completion.py` (provider marks complete → customer confirms → balance settlement + release), completion UI `apps/customer/app/[locale]/account/jobs/[id]/_components/complete-confirm.tsx`, provider side `apps/vendor/app/jobs/[id]/page.tsx`
Confirm flow mirrors order confirm (48h auto-confirm after marked-complete, config); review gated on completed job (verified-engagement review, feeds vendor rating).
**AC:** balance release follows confirm exactly once; auto-confirm honors window; review only post-completion.
**Tests:** double-confirm idempotency, auto-confirm job, review gating.

### M11-P06 — Pre-acceptance contact-info stripping `M`
**Deps:** P03 · **Files:** `services/api/app/services/moderation/contact_strip.py` (regex + normalization: +260/09x/07x phone patterns incl. spaced/dotted evasion, WhatsApp links/wa.me, email patterns; replace with notice token), applied in quote/message write paths (`app/routers/quotes.py` modification — **same file as P03, sequenced later wave**), `services/api/tests/test_contact_strip.py`
Platform-disintermediation guard: strip pre-acceptance only (post-acceptance contact exchange is fine and necessary); stripped content logged for moderation review; repeated evasion flags provider.
**AC:** evasion corpus (spaced digits "09 7 1…", "zero nine seven", wa.me links) caught per fixture list; post-acceptance messages untouched; flag threshold triggers.
**Tests:** evasion corpus fixtures (≥15 patterns), false-positive guard (prices "K970" NOT stripped), pre/post acceptance behavior.
