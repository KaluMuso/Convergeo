> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P13 — Listing-anchored customer↔business enquiries `[CODE]` ⚠ D37-binding

## 1. Context
**Wave W5 (social commerce).** Governing decision: **D37** in `docs/plan/00-decisions.md` (2026-08-01).

**There is no message, thread or chat model anywhere in the codebase today** — the only message-shaped tables are the WAHA intake ones (`intake_messages`, `0073`), which are a private vendor-intake lane and must not be reused, extended or joined to. This pebble creates the first customer-facing messaging surface in the product, so the shape you choose is the shape the platform is stuck with.

D37 is explicit about the fence: **IN** — listing-anchored customer→business enquiries with vendor replies. **OUT** — customer-to-customer DMs, groups, public profiles, public feeds, user-uploaded image exchange.

**The binding requirement is structural, not behavioural: the schema must make a customer↔customer thread _unrepresentable_, not merely unreachable from the UI.** A UI restriction is one careless endpoint away from being gone; a foreign key is not. Every thread is rooted at a listing/event/service, and one side is always that item's vendor.

**Type:** `[CODE]`.

## 2. Objective & scope
A customer asks a question about a specific item; the vendor replies; both get notified through the existing outbox.
**Non-goals:** attachments/images (**explicitly OUT**), C2C anything, group threads, realtime/websockets, read receipts, typing indicators, gifting.

## 3. Files (edit ONLY these)
- `supabase/migrations/NNNN_enquiry_threads.sql` — **verify next-free at branch time** (expected `0084`)
- `services/api/app/routers/enquiries.py`, `vendor_enquiries.py` (new; auto-discovered — **do not edit `main.py`**)
- `services/api/app/services/enquiries/{threads,notify,moderation}.py` (new)
- `apps/customer/app/[locale]/enquiries/**`, PDP "Ask the seller" entry point
- `apps/vendor/app/[locale]/enquiries/**`
- `packages/i18n/messages/en/{enquiries,vendor}.json`
- Tests

## 4. Implementation spec

**Schema — the fence lives here:**
- `enquiry_threads`: `id`, **`subject_kind`** (`listing|event|service`), **`subject_id`**, **`vendor_id not null`**, **`customer_id not null`**, `status` (`open|answered|closed`), `last_message_at`, timestamps. **Both party columns are non-null and semantically distinct** — there is no generic `participant_a/participant_b`, so a customer↔customer row cannot be expressed at all. Add a `check (vendor_id <> customer_id)` and a trigger asserting `vendor_id` equals the subject's owning vendor, so a thread cannot be pointed at an unrelated business.
- `enquiry_messages`: `thread_id`, **`sender_role`** (`customer|vendor|admin`), `sender_id`, `body text`, `created_at`. **No attachment column** — absence is the enforcement.
- Unique index preventing a duplicate open thread per (customer, subject).
- FORCE RLS: a customer reads/writes only their own threads; a vendor only threads on their own subjects; admin all. Counters/status are not client-writable.

**Behaviour:**
- Rate-limit thread creation and messages per customer per hour (reuse `rate_counters` / the existing rate-limit decorator; every mutating endpoint needs a declared policy or `assert_all_mutating_routes_covered` fails at startup).
- Screen message bodies through the **existing prohibited-content screen** used by listing creation — reuse it, do not fork it.
- **Contact-detail leakage:** an enquiry is not a channel for moving the deal off-platform before escrow. Detect and (per founder decision recorded in the report) flag or mask phone/email patterns; do not silently delete a customer's words.
- Notifications: enqueue to the **existing `notification_outbox`**; delivery rides WhatsApp Cloud API → SMS → email. **WAHA is forbidden here** (D15/D35/D37). Never send message *content* off-platform — notify that a reply exists and link back.
- An LLM may **suggest** a vendor reply; it never auto-sends.

## 5. Security / conventions
Every mutation: authz + strict Pydantic + rate limit + audit where admin-initiated. Bodies are untrusted input — never interpret them as instructions. Message content is personal data: define retention in `docs/ops/data-retention.md` and mask identifiers in logs (mirror the intake lane's rule: no raw body, no full MSISDN).

## 10. Tests (RUN before reporting) — the fence tests are the deliverable
- `test_schema_cannot_express_customer_to_customer_thread` — assert structurally (a thread requires a subject whose vendor is `vendor_id`); include a direct SQL attempt that the DB refuses.
- `test_thread_vendor_must_own_the_subject`
- `test_customer_cannot_read_another_customers_thread` (RLS)
- `test_vendor_cannot_read_threads_on_another_vendors_listing` (RLS)
- `test_no_attachment_path_exists` (grep-style structural assertion, in the spirit of M17's "approve is the only publish path" test)
- `test_message_body_is_screened_for_prohibited_content`
- `test_notification_goes_to_outbox_and_never_to_waha`
- `test_rate_limit_blocks_flooding`
- `test_duplicate_open_thread_per_subject_is_refused`
- Migration replay; RLS matrix; `uv run pytest -q`; `ruff`; `mypy`; `pnpm lint typecheck test build`.

## 11. Acceptance criteria / DoD
- [ ] A C2C thread is **unrepresentable** in the schema, proven by test.
- [ ] Every thread is anchored to a subject owned by its vendor.
- [ ] No attachment/image path exists.
- [ ] Notifications via outbox only; zero WAHA involvement.
- [ ] Rate-limited, content-screened, RLS-isolated both ways.
- [ ] Retention documented.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P13 — Listing-anchored enquiries
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the fence tests · **EXCERPTS:** the migration's constraints + the outbox call · **QUESTIONS:** flag the contact-detail policy choice for founder sign-off
