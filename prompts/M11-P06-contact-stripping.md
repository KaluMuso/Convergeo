> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 16 (parallel). **Touch ONLY your files below.** **⚠ You are the SOLE Wave-16 editor of `services/api/app/routers/quotes.py`.** **Run the FULL `uv run pytest` before reporting.**

# M11-P06 — Pre-acceptance contact-info stripping

## 1. Context

**Grounded against as-built `master` (M11-P03 quotes MERGED):**

- **`quotes.py` (M11-P03, merged)** has a `message` field (`max_length=4000`) on quote submit — this is the pre-acceptance write path you guard. **You are the sole Wave-16 editor of `quotes.py`.**
- **Platform-disintermediation guard:** strip contact info **pre-acceptance only** (post-acceptance exchange is fine/necessary). Replace stripped spans with a notice token; log stripped content for moderation; repeated evasion flags the provider.
- **Zambian number patterns:** `+260…`, `09x…`, `07x…` incl. spaced/dotted evasion (`09 7 1 …`, `zero nine seven`), `wa.me`/WhatsApp links, emails. **False-positive guard: prices like `K970` must NOT be stripped.**
- **Notice token is server-side** (a constant/moderation namespace) — **do NOT touch `services.json`** (M11-P04 owns it this wave).
  Spec: `docs/plan/02-pebbles/M11-services-rfq.md` §M11-P06.

## 2. Objective & scope

A `contact_strip` moderation util (regex + normalization) applied to pre-acceptance quote/message write paths; stripped content logged for moderation; repeated-evasion flag threshold. Post-acceptance messages untouched.
**Non-goals:** no quote lifecycle change (reuse M11-P03), no post-acceptance stripping, no services.json edit, no new payment/UI.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/moderation/contact_strip.py` (`strip_contacts(text) -> StripResult{clean_text, stripped_spans, hit_count}`; phone/email/wa.me/spaced-digit/spelled-digit patterns; replace with a server-side notice token) · `services/api/tests/test_contact_strip.py`
- **Modify:** `services/api/app/routers/quotes.py` (apply `strip_contacts` on the pre-acceptance `message` write path; log stripped content + increment an evasion counter; flag the provider at threshold — reuse the existing rate-counter/flags pattern if present, else a minimal counter)
  **Guardrail: nothing else. Do NOT edit `services.json` (M11-P04), engagement/accept code, other routers, db.ts, migrations. If a migration seems needed for a moderation log, DON'T add one — log via the existing `audit_log`/moderation table or a service-role insert into an existing table, and record the choice in DEVIATIONS.**

## 4. Implementation spec

- **`contact_strip.py`:** compile patterns for: E.164 `+260…`; local `09x`/`07x` (7–10 digits, tolerate spaces/dots/dashes between digits); spelled digits (`zero|one|…|nine` sequences ≥6); `wa.me/…`, `whatsapp` links; emails. Normalize whitespace/dots before matching so `09 7 1` and `09.7.1` are caught. **Guard prices:** a `K`/`ZMW`-prefixed number or a ≤4-digit amount alone is NOT a phone — exclude. Return `clean_text` (spans replaced by the notice token), `stripped_spans`, `hit_count`.
- **`quotes.py` wiring:** on quote submit (pre-acceptance), run `strip_contacts(message)`; persist `clean_text`; if `hit_count>0`, log the original stripped span for moderation + bump a per-provider evasion counter; at a config threshold (default e.g. 3) set a provider flag. Post-acceptance messages (if any pass through here) are NOT stripped — gate on job/quote status.

## 5–9. Security etc.

Pre-acceptance only (status-gated); stripped originals logged server-side (not shown to the counterparty); false-positive guard on prices; evasion threshold flags provider; no PII leak in the clean text; no secrets.

## 10. Tests (RUN before reporting)

`test_contact_strip.py`: **evasion corpus ≥15 patterns** (`09 7 1 234 567`, `zero nine seven one…`, `wa.me/26097…`, `+260 97 …`, dotted, email) all caught; **false-positive guard** (`K970`, `ZMW 1,200`, `50000 kwacha` NOT stripped); pre-acceptance stripped vs post-acceptance untouched; threshold flag triggers. Full `uv run pytest`, `uv run ruff check .`, `uv run mypy .`.

## 11. Acceptance criteria / DoD

- [ ] Evasion corpus caught per fixtures; post-acceptance messages untouched; false positives (prices) preserved; flag threshold triggers.
- [ ] No services.json edit; no migration; full API suite green; ruff/mypy clean.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M11-P06 — Pre-acceptance contact-info stripping
**STATUS/FILES/DEVIATIONS** (the pattern set + normalization; price false-positive guard; where stripped content is logged; the flag threshold mechanism) **/TESTS** (paste evasion-corpus + false-positive + pre/post-acceptance + threshold + full-pytest tail) **/EXCERPTS** the `strip_contacts` core + the quotes.py write-path wiring — nothing else **/QUESTIONS**
