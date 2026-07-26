# WAHA verified-vendor product-intake lane — architecture decision & operator runbook

**Status:** DESIGN / NOT BUILT · flag-gated, default-off · **Decision:** `D35` (amends `D15`) in `docs/plan/00-decisions.md`
**Scope owner (single approver):** Founder (`convergeozambia@gmail.com`)
**Last updated:** 2026-07-26

> This document narrowly re-opens WAHA (the unofficial WhatsApp HTTP gateway) for **one** purpose — letting an already-KYC-verified vendor send product photos/details over a 1:1 WhatsApp chat so the platform can draft a catalog listing for human review. It does **not** authorise WAHA for anything else. `D15` ("official Cloud API only; WAHA banned") remains in force for **every** customer-facing and transactional channel.
>
> **Nothing here is installed or wired.** This is a spec + runbook. A later implementation pebble builds it behind the `waha_vendor_intake` flag (default off) only after the pilot approval in Part B §10. No application code, migration, WAHA deployment, or production config changes ship with this document.

---

## Part A — Architecture Decision

### 1. Context & the conflict being resolved

- **`D15` (locked 2026-07-06):** WhatsApp is **official Meta Cloud API only**; WAHA is **banned from production _and_ dev**. Rationale: a self-hosted WhatsApp-Web session can be banned by WhatsApp at any time, and a banned number mid-beta is a trust catastrophe. Meta's free test number removes any dev need for WAHA. This holds.
- **Founder direction (2026-07):** permit WAHA for **direct verified-vendor product intake only** — vendors in Zambia overwhelmingly already run their shops from WhatsApp, and asking them to re-enter a catalogue in a web form is the single biggest onboarding drop-off. A 1:1 "send me your product photos" intake removes that friction.
- **Standing risk flags this decision must respect (vision-audit 2026-07-19):**
  - **NB-7 / X-10** — a shared `waha.vergeo.company` session already runs under the wider "Convergeo" brand (agency/ZedApply growth-messaging). A WhatsApp ban on _that_ number/brand must **never** be able to contaminate Vergeo5's official Cloud API notifications. The official Cloud API sender **must be a separate number** from any WAHA sender.
  - **NB-8 / X-11** — the OCI Always-Free VM co-hosts Vergeo5 api/caddy/n8n **+ WAHA + ZedApply `zedcv-backend`**. Noisy-neighbour and blast-radius risk is real.

The resolution is **strict lane separation**: WAHA becomes a physically and logically isolated **inbound intake side-channel** that can only ever produce _draft_ data, never send a customer message, and never touch money, auth, or support.

### 2. Decision (D35, narrow)

WAHA is permitted **solely** as an **inbound, 1:1, verified-vendor product-intake** channel that produces **draft** catalog listings for human review. It is:

- **feature-flagged** (`waha_vendor_intake`, default `false` — the kill switch);
- **isolated** from the Cloud API path (separate number, separate account authority, separate host/compartment, separate secrets);
- **inbound-only for content** (the sole permitted outbound is a single automated receipt acknowledgement to the same verified vendor);
- **never** a channel for customers, notifications, OTP, payments, support, or moderation;
- **never** an approver — an LLM may _suggest_ structured listing fields, but publication, KYC, payment, and moderation stay on the existing guarded, audited, human-in-the-loop paths.

All of `D15`'s guarantees for every other channel are unchanged.

### 3. The two lanes (authoritative table)

|                                      | **Lane 1 — Cloud API (official)**                       | **Lane 2 — WAHA vendor-intake**                                        |
| ------------------------------------ | ------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Provider**                         | Meta WhatsApp Business Cloud API                        | Self-hosted WAHA gateway                                               |
| **Governed by**                      | `D15` (unchanged)                                       | `D35` (this doc)                                                       |
| **Direction**                        | Outbound transactional + inbound STOP/START             | **Inbound** vendor product messages; **one** outbound receipt ack only |
| **Audience**                         | Customers, vendors, founder alerts                      | **Verified vendors only** (KYC ≥ T1, `vendors.status='active'`)        |
| **Message shape**                    | Approved Meta templates + 24h service window            | Free-form 1:1 chat from the vendor                                     |
| **Purpose**                          | Order/payment/shipping/OTP/KYC/RFQ notifications        | Draft-listing intake **only**                                          |
| **Number**                           | Dedicated Cloud API number (`WHATSAPP_PHONE_NUMBER_ID`) | **Separate** dedicated `+260` intake number                            |
| **Sends customer messages?**         | Yes (its whole job)                                     | **Never**                                                              |
| **Handles OTP / payment / support?** | OTP yes; payment/support via app                        | **Never — forbidden**                                                  |
| **Groups / broadcast?**              | N/A                                                     | **Forbidden — dropped at ingestion**                                   |
| **Can publish / approve anything?**  | No                                                      | **No — drafts only, human approves**                                   |
| **Ban blast radius**                 | Notifications (mitigated by SMS/email fallback)         | **Vendor intake only** — Lane 1 untouched by design                    |
| **Kill switch**                      | (channel is core)                                       | `feature_flags.waha_vendor_intake = false`                             |

**The invariant:** a failure, ban, or compromise in Lane 2 must leave Lane 1 fully operational. Lane separation is what makes re-admitting WAHA acceptable under the NB-7/NB-8 risks.

### 4. One-to-one-only & verified-vendor enforcement

Enforced **at ingestion**, fail-closed, in this order. Any check that fails → **drop, audit, do not process** (no reply, no draft):

1. **Flag on.** `feature_flags.waha_vendor_intake` must be `true`. Off ⇒ ignore every event (kill switch).
2. **Webhook authenticated.** HMAC signature + source-IP allowlist + TLS + replay window all pass (§7). Fail ⇒ `403`, drop.
3. **1:1 only.** The chat/JID must be an **individual** conversation. Any **group** conversation (WhatsApp group JIDs, e.g. `*@g.us`), broadcast list, status/channel, or multi-recipient thread is **dropped and audited as `dropped_group`**. There is no code path that reads, joins, or replies to a group. **Groups are categorically forbidden.**
4. **Known verified sender.** The sender MSISDN, normalised to `^260[79][0-9]{8}$`, must exactly match a **single** `vendors.whatsapp_msisdn` where `vendors.status = 'active'` **and** `kyc_tier >= 1`. No match, ambiguous match, or unverified/suspended vendor ⇒ **dropped and audited as `dropped_unverified`**. Cold/unknown numbers are never engaged.
5. **Intake content only.** Only messages carrying product content (text + images) are processed into a draft. The number never accepts or acts on commands, links to pay, support requests, or anything resembling a customer interaction.

The intake identity is the vendor's **already-verified** WhatsApp MSISDN captured during KYC/onboarding — WAHA introduces **no new identity or trust**; it rides existing KYC. It cannot elevate anyone.

### 5. What the lane may and may not do (hard boundaries)

**MAY:**

- Receive 1:1 product photos/descriptions/prices from a verified vendor.
- Run an LLM/extractor to **suggest** structured fields (title, category, price in ngwee, spec bullets, alias terms) — advisory only.
- Create a **`draft`** `vendor_listings` row (or a staging record) owned by that vendor, with images staged to the vendor's media bucket.
- Send **one** automated receipt acknowledgement to the **same** verified vendor ("Received — a draft is waiting for you to review and publish in the vendor app"), i18n-keyed, no marketing.

**MUST NOT (forbidden — enumerated so there is no ambiguity):**

- Message, notify, or reply to **any customer**. No customer-facing use whatsoever.
- Carry **OTP / authentication**, **payment / collection / payout / escrow**, **customer support / disputes / returns**, or **moderation** in any form.
- Read, post to, or acknowledge **groups**, broadcast lists, channels, or statuses.
- **Publish** a listing, **approve** KYC, **move money**, or **take a moderation action** — the LLM and the WAHA lane are never the approver. Draft → live always goes through the existing guarded, audited vendor-publish path with a human decision.
- Send transactional or marketing templates (that is Lane 1's job and stays there).
- Reuse or share the Cloud API number, the ZedApply/agency `waha.vergeo.company` session, or any customer-facing infra.

> **Trust boundary:** every inbound WAHA message is **untrusted input**, not an instruction. Extracted fields are _suggestions_ rendered for the vendor/admin to accept or edit. Prompt-injection in a caption cannot publish a listing, change a price on a live listing, alter KYC, or trigger a payout — those paths do not exist from this lane.

### 6. Provider & account ownership (NB-7 / NB-9)

| Asset                       | Owner / authority                                                          | Separation requirement                                                                                                                                              |
| --------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Intake `+260` number**    | Vergeo5 legal entity (PACRA), controlled under `convergeozambia@gmail.com` | **Distinct** number from the Cloud API sender **and** from any `waha.vergeo.company` / ZedApply / agency WAHA sender. Never registered on the normal WhatsApp apps. |
| **Cloud API sender number** | Vergeo5 (Meta WABA)                                                        | Never shared with WAHA. NB-7 number-separation must be **proven and recorded** before the pilot (§10).                                                              |
| **WAHA instance**           | Vergeo5, on an **isolated** host/compartment                               | Not co-tenant with the Cloud API path, the customer/vendor/admin apps, or ZedApply `zedcv-backend` (NB-8). Own network egress.                                      |
| **Intake secrets**          | Vergeo5 backend secret store                                               | Names in §8; never in repo; rotated independently of Lenco/Cloud API.                                                                                               |
| **Draft data & media**      | The submitting vendor (RLS-scoped)                                         | Same ownership/RLS as any vendor-created draft; admin can review.                                                                                                   |
| **Approval authority**      | **Founder only**                                                           | The single human approver for pilot→prod (§10). No AI, no automation, no non-owner grants WAHA scope.                                                               |

"Convergeo the automation agency" and Vergeo5 the marketplace are **different concerns**; the agency's WAHA usage is out of scope and must stay off Vergeo5's number/host.

### 7. Webhook auth, IP / TLS / replay controls

WAHA posts inbound events to a dedicated backend route (design target: `POST /webhooks/waha-intake`). Controls mirror the proven Cloud API / Lenco webhook posture and are **fail-closed**:

- **HMAC signature (fail-closed).** WAHA signs each POST; the backend verifies an HMAC-SHA256 over the **raw request body** using `WAHA_INTAKE_WEBHOOK_SECRET` and `hmac.compare_digest`, exactly like `verify_hub_signature` for Cloud API. Missing/invalid signature ⇒ `403`, nothing parsed. No secret ⇒ verification fails closed (never open).
- **Source-IP allowlist.** The route is admitted only from the isolated WAHA host's IP(s) via a Caddy `remote_ip` matcher fed by `WAHA_INTAKE_ALLOWED_IPS` (space-separated CIDRs, quoted — same pattern as `ADMIN_ALLOWED_IPS`). All other sources rejected at the edge before FastAPI.
- **TLS only.** Callback is `https://` end to end (Caddy auto-HTTPS / Let's Encrypt, as the API already runs). No plaintext callback is ever configured.
- **Replay protection.** Two layers: (a) an idempotency key `(provider='waha', event_id=<waha message id>)` deduped through the existing `webhook_events` UNIQUE `(provider, event_id)` constraint — a replayed or retried event is a no-op; (b) a **freshness window** — reject events whose signed timestamp is older than a small skew (design target ±5 min) so a captured old POST cannot be replayed after the dedupe row is pruned.
- **Least privilege.** The handler runs service-role for the draft insert only; it cannot reach money, auth, or moderation tables. Rate-limited like every mutating route (declared in `ratelimit_policies.py` when built).

### 8. Secrets — **names only** (never values; never committed)

Added to `infra/.env.example` **by the future implementation pebble**, not now. Values live only in the isolated host's secret store.

| Name                         | Purpose                                                                                                                                   |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `WAHA_INTAKE_BASE_URL`       | Internal URL of the isolated WAHA instance the backend calls (host/routing, not a secret).                                                |
| `WAHA_INTAKE_API_KEY`        | Bearer/API key the backend presents to the WAHA API; also the key WAHA requires on its own API.                                           |
| `WAHA_INTAKE_SESSION`        | WAHA session name bound to the dedicated intake number.                                                                                   |
| `WAHA_INTAKE_WEBHOOK_SECRET` | Shared secret for the inbound HMAC-SHA256 signature (`openssl rand -hex 32`).                                                             |
| `WAHA_INTAKE_ALLOWED_IPS`    | Space-separated CIDR allowlist for the Caddy `remote_ip` matcher on the intake route (quoted).                                            |
| `WAHA_INTAKE_SENDER_E164`    | The dedicated `+260` intake number — recorded to **assert it differs** from the Cloud API sender and any agency WAHA sender (NB-7 check). |

These are **distinct** from `WHATSAPP_*` (Cloud API) and `LENCO_*` and rotate on their own schedule. Rotating `WAHA_INTAKE_*` never re-keys Cloud API or Lenco.

### 9. Feature flag & kill switch

- **Flag:** `waha_vendor_intake` in the existing `public.feature_flags` table (`0008_config.sql`) — **default `false`**, admin-write / public-read, **FORCE RLS**, and every change **audited** by the `config_audit` trigger. (A row for it is inserted by the implementation pebble's migration, not by this doc.)
- **Kill switch = flip to `false`.** Effect is immediate and deploy-free: the ingestion handler's first check is the flag (§4.1), so every subsequent event is ignored. No draft is created; no ack is sent.
- **Optional pilot scoping:** a `platform_config` key (e.g. `waha_intake_vendor_allowlist`) can restrict processing to explicitly allowlisted `vendor_id`s during the pilot, so "on" never means "open to all vendors" before §10 sign-off.
- **Independence:** the flag gates **only** Lane 2. Turning it off has zero effect on Cloud API notifications, SMS/email fallback, or any money path.

### 10. Pilot → production approval

Gated, human-approved, reversible. **The founder is the sole approver at every gate; no AI/automation approves.**

- **Stage 0 — Design (now).** This doc + `D35`. Flag off. Nothing installed. No number, no host, no secrets.
- **Stage 1 — Pilot (founder-approved).** Entry gates, all required:
  1. Dedicated intake number provisioned; **NB-7 separation proven** — `WAHA_INTAKE_SENDER_E164` ≠ Cloud API sender ≠ any `waha.vergeo.company`/ZedApply sender — and recorded here.
  2. WAHA on an **isolated** host/compartment (NB-8), not co-tenant with the Cloud API path or customer infra.
  3. Webhook controls (§7) implemented and tested fail-closed; audit logging (§11) live.
  4. Consent + retention (§12) implemented; vendor opt-in copy approved.
  5. Flag on **only** for a small, named allowlist of hand-picked verified vendors; time-boxed; success/abort criteria written.
- **Stage 2 — Production (founder sign-off).** Only after the pilot meets exit criteria: no ban/quality event on the intake number; no group/customer/payment/support message ever processed (audit-verified); draft quality acceptable; the incident/kill-switch drill (Part B R4–R5) rehearsed once. Founder records the go decision; widening the vendor allowlist is itself an audited config change.
- **Any gate fails ⇒ flip the flag off and stop.** Production status is never inferred from "code complete"; it requires the recorded founder decision — mirroring the project's Go/No-Go discipline.

### 11. Audit logs

Every inbound intake event is recorded to an **append-only** audit trail (mirrors `webhook_events` / `config_audit` / admin-audit conventions):

- **Per event:** `event_id` (WAHA message id), received-at, sender MSISDN (minimised per §12), matched `vendor_id` **or** `null`, message type, media object refs, LLM-suggested fields, and **disposition** — one of `draft_created`, `dropped_group`, `dropped_unverified`, `dropped_flag_off`, `rejected_auth`, `error`.
- **Flag/allowlist changes:** captured by the `feature_flags` / `platform_config` → `config_audit` trigger (actor, before/after).
- **Draft → publish:** stays on the existing guarded vendor-publish path and its **admin/audit** trail. The WAHA lane's record ends at "draft_created"; it never records an approval because it never approves.
- **Retention of the audit trail** follows §12 (message content/PII minimised; disposition + IDs kept for operational review).

### 12. Consent & retention

- **Consent (opt-in, recorded).** A vendor is enrolled in WAHA intake only after an **explicit, timestamped opt-in** (vendor-app toggle or signed vendor-agreement clause), stored and audited like `profiles.dpa_consent_at` / vendor-agreement consent in `notification-compliance.md`. Enrolment states which number they'll message and that content is used solely to draft their own listings. Opt-out removes them from the allowlist immediately; a `STOP`-style keyword on the intake number also disenrolls. No vendor is ever cold-messaged on this number.
- **Data minimisation.** Only what's needed to draft a listing. Sender MSISDN is matched then stored **minimised** (reference the vendor row, not a free-floating phone log). No customer PII ever transits this lane (it is vendor-only by construction).
- **Retention (aligned to `data-retention.md`).**
  - **Raw inbound message text/media** used for extraction: kept only until the draft is created and the vendor has reviewed, then **purged** on a short window (design target ≤ 30 days), via an idempotent, service-role sweep + n8n tick — the same shape as the analytics-retention sweeper.
  - **Product images the vendor chooses to publish** become normal listing media under the standard media pipeline and its lifecycle (not "message data").
  - **Audit dispositions + IDs** (no message body) kept for operational review; person-links minimised on the same cadence as the 30-day analytics person-link sweep.
  - **Nothing tax-bound** lives in this lane (no orders/payments/invoices), so no 7-year retention attaches here.
- **Zambia DPA / WhatsApp ToS.** Vendor-only, consent-based, 1:1, no harvested lists (NB-10), no customer contact — keeping the lane within DPA and WhatsApp's acceptable-use posture. Business-messaging on WAHA still carries WhatsApp-ban risk, which the incident runbook (Part B R5) and the isolation design bound.

---

## Part B — Operator runbook

Operational steps for the **founder/operator**. **Do not run any of this until §10 Stage 1 is founder-approved.** Until then the lane stays design-only, flag off, nothing installed.

### R1. Pre-flight checklist (before enabling anything)

- [ ] `D35` present in `00-decisions.md`; this doc reviewed.
- [ ] Dedicated `+260` intake number acquired, **not** on any WhatsApp app, **not** the Cloud API number, **not** the agency `waha.vergeo.company` number. Record it as `WAHA_INTAKE_SENDER_E164` and **write the three-way "different number" confirmation into §10 Stage 1**.
- [ ] WAHA runs on an **isolated** host/compartment (NB-8); confirm it is not co-tenant with Vergeo5 api/caddy or ZedApply `zedcv-backend`.
- [ ] `WAHA_INTAKE_*` secrets generated (`openssl rand -hex 32` for the webhook secret) and stored **only** in that host's secret store — never in the repo.
- [ ] Webhook route reachable **only** over TLS and **only** from `WAHA_INTAKE_ALLOWED_IPS`; signature verification tested fail-closed (bad signature ⇒ `403`).
- [ ] `waha_vendor_intake` flag exists and is `false`; pilot `waha_intake_vendor_allowlist` holds the hand-picked pilot vendor IDs.
- [ ] Audit logging (§11) and retention sweep (§12) verified working in the pilot environment.

### R2. Enable the pilot

1. Confirm every R1 box is ticked and the founder has recorded Stage 1 approval.
2. Admin app → config → set `waha_vendor_intake = true` (change is auto-audited via `config_audit`).
3. Verify the allowlist is non-empty and scoped to the pilot vendors only.
4. Send a test product message **from a pilot vendor's verified number** → confirm: draft created, single ack received, audit row `draft_created`, **no** customer contact anywhere.
5. Send from a **non-verified** number → confirm `dropped_unverified`, no reply.
6. Add the test number to a WhatsApp **group** and message there → confirm `dropped_group`, no reply, no draft.

### R3. Daily / ongoing checks

- Watch the intake number's WhatsApp quality/ban status. Any warning ⇒ go to R5.
- Skim audit dispositions: a rise in `dropped_unverified` / `rejected_auth` may signal misconfig or probing.
- Confirm the retention sweep ran (no raw message backlog beyond the window).
- Confirm **zero** entries that look like customer contact, OTP, payment, support, or group activity — any such entry is an incident (R5).

### R4. Kill switch (instant disable)

**When:** ban warning, compromise, abuse, secret leak, or **any** sign the lane touched a customer / OTP / payment / support / group.

1. Admin app → config → set `waha_vendor_intake = false`. Takes effect immediately, no deploy — ingestion ignores all further events.
2. Confirm via audit that new events now record `dropped_flag_off` (or stop entirely).
3. Lane 1 (Cloud API notifications) is unaffected by design — verify a normal order notification still sends.

### R5. Incident response

| Trigger                                                            | Immediate action                                                                                        | Follow-up                                                                                                                                                                           |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Intake number **banned/flagged** by WhatsApp                       | Kill switch (R4).                                                                                       | Because the lane is isolated + inbound-only, **Lane 1 is untouched** — confirm notifications still flow. Assess number replacement; do **not** move intake to the Cloud API number. |
| Number/session **compromised**                                     | Kill switch; revoke `WAHA_INTAKE_SESSION`; rotate `WAHA_INTAKE_API_KEY` + `WAHA_INTAKE_WEBHOOK_SECRET`. | Re-provision on the isolated host; review audit for anything drafted while compromised (drafts are unpublished — nothing went live).                                                |
| **Secret leak** (`WAHA_INTAKE_*`)                                  | Kill switch; rotate the leaked secret(s) immediately.                                                   | Rotation does **not** affect Lenco/Cloud API secrets (separate). Confirm `.env` never entered the repo.                                                                             |
| **Group / customer / payment / support** message observed in audit | Kill switch.                                                                                            | Root-cause the enforcement gap (§4/§5) before re-enabling; this is a scope breach, treat as high severity.                                                                          |
| Webhook **auth-failure** spike                                     | Verify `WAHA_INTAKE_ALLOWED_IPS` + secret; the route is fail-closed so no bad data is processed.        | If it is probing, keep the flag off until the source is understood.                                                                                                                 |
| Suspected **co-tenancy contamination** (NB-8)                      | Kill switch; isolate the WAHA host further.                                                             | Escalate the VM-isolation plan (VE-P08); do not run intake co-tenant with the Cloud API path.                                                                                       |

**Notify:** send the founder alert over the existing Cloud API founder-alert path (`FOUNDER_WHATSAPP_E164`) — **not** over WAHA. After any incident, record a short post-incident note and the re-enable decision (founder-approved) before flipping the flag back on.

### R6. Decommission / rollback

WAHA intake is fully reversible: set `waha_vendor_intake = false`, stop the WAHA container, revoke the session, delete the `WAHA_INTAKE_*` secrets, and (optionally) release the intake number. Drafts already created remain as ordinary vendor drafts under the vendor's ownership; no customer-facing surface ever depended on this lane, so removal is invisible to customers.

---

## Related

- `docs/plan/00-decisions.md` — **D15** (Cloud-API-only, WAHA ban) and **D35** (this narrow amendment).
- `docs/ops/whatsapp-cloud-api-setup.md` — Lane 1 official Cloud API (unchanged).
- `docs/ops/notification-compliance.md` · `docs/ops/data-retention.md` — consent/retention conventions this lane mirrors.
- `docs/production-readiness/2026-07-19/vision-audit/02-open-questions.md` — **NB-7** (number separation), **NB-8** (host isolation), **NB-10** (no harvested lists).
- `services/api/app/routers/webhooks_whatsapp.py` · `services/api/app/services/payments/webhook_verify.py` — the fail-closed HMAC + `webhook_events` idempotency patterns Lane 2 reuses.
