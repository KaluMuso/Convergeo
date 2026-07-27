# M18 — WhatsApp vendor-intake private-pilot checklist

> **Governing decision:** `D35` (narrowly amends `D15`) · **Runbook:** `docs/ops/waha-vendor-intake.md`
> **Flag:** `waha_vendor_intake`, default `false`. **Nothing below may be started until the founder has
> recorded Stage-1 approval** (`waha-vendor-intake.md` §10).
>
> Placed at `docs/plan/intake-pilot-checklist.md` rather than `docs/plan/launch/` — the repo keeps
> plan documents flat (`launch-checklist.md`, `m17-video-feed.md`), and a one-file subdirectory would
> have been the only one of its kind.

This checklist is the **operator's** side of M18-P08. The code side — the automated proof that the
lane cannot publish — lives in `services/api/tests/e2e/test_intake_pilot.py` and runs in CI on every
push. Passing tests are a **precondition**, not evidence of a pilot: a pilot is only live when a human
has ticked the boxes below and recorded the decision.

---

## 0. What the automated suite already proves

You do **not** need to re-prove these by hand. They are asserted in CI, and a regression fails the
build before it can reach the pilot number.

| Property                                                               | Test                                                         |
| ---------------------------------------------------------------------- | ------------------------------------------------------------ |
| Inbound creates a private record, never a listing                      | `test_inbound_creates_a_private_record_and_never_a_listing`  |
| A duplicate delivery is harmless (no second session/message/audit row) | `test_duplicate_delivery_is_harmless`                        |
| Missing details are recorded as **data**, never messaged               | `test_missing_details_are_recorded_as_data_not_messaged`     |
| The full chain reaches `active` **only** after a human approves        | `test_full_chain_ends_active_only_after_a_human_approves`    |
| Group message cannot publish                                           | `test_group_message_cannot_publish`                          |
| Unknown number cannot publish                                          | `test_unknown_number_cannot_publish`                         |
| Invalid signature cannot publish                                       | `test_invalid_signature_cannot_publish`                      |
| A **valid SHA-256** signature is still refused (lane separation)       | `test_valid_sha256_signature_is_still_refused`               |
| Flag off cannot publish                                                | `test_flag_off_cannot_publish`                               |
| Prohibited class cannot publish                                        | `test_prohibited_class_cannot_publish`                       |
| Media failure cannot publish (lands recoverable)                       | `test_media_failure_cannot_publish`                          |
| A vendor cannot submit another vendor's session                        | `test_a_vendor_cannot_submit_another_vendors_session`        |
| Kill switch stops ingestion **without harming existing drafts**        | `test_kill_switch_stops_ingestion_without_harming_drafts`    |
| Kill switch leaves Lane 1 intact                                       | `test_kill_switch_leaves_lane_1_intact`                      |
| Retention sweep minimises content but keeps the audit                  | `test_retention_sweep_minimises_content_but_keeps_the_audit` |
| Logs carry no raw body and no full MSISDN                              | `test_logs_never_carry_a_raw_body_or_a_full_msisdn`          |

What the suite **cannot** prove, and why this checklist exists: that the intake number is genuinely
separate from the Cloud API number, that the WAHA host is genuinely isolated, that a real vendor
understood the opt-in, and that a human actually rehearsed the kill switch on live infrastructure.
Those are physical facts about your deployment, not properties of the code.

---

## 1. Pre-flight (mirrors runbook R1)

- [ ] `D35` present in `00-decisions.md`; `waha-vendor-intake.md` read end to end.
- [ ] Migrations `0072`–`0075` applied; `waha_vendor_intake` row exists and is **`false`**.
- [ ] `waha_intake_vendor_allowlist` holds **only** the hand-picked pilot vendor IDs.
- [ ] All six `WAHA_INTAKE_*` secrets set on the isolated host's secret store — **never** in the repo.
- [ ] `INTERNAL_INTAKE_TOKEN` set (non-default) so the M18-P07 sweeps can run.
- [ ] **NB-7 three-way separation proven and written into §10 Stage 1**:
      `WAHA_INTAKE_SENDER_E164` ≠ Cloud API sender ≠ any `waha.vergeo.company`/ZedApply sender.
- [ ] **NB-8 host isolation confirmed**: WAHA is not co-tenant with Vergeo5 `api`/`caddy` or ZedApply.
- [ ] Webhook reachable only over TLS and only from `WAHA_INTAKE_ALLOWED_IPS`.
- [ ] Both n8n workflows imported (`waha-intake-sweeps.json`, `waha-intake-digest.json`) and confirmed
      **inactive** — activation is a separate, deliberate operator action.

## 2. Vendor enrolment (consent — D35 §12)

- [ ] Each pilot vendor gave an **explicit, timestamped opt-in**; `intake_vendor_bindings` row exists
      with `consent_source` recorded.
- [ ] Each vendor was told, in language they use: which number to message, that content becomes a
      **private draft only**, that nothing is published until they submit and Vergeo5 approves, and
      how to opt out.
- [ ] Disenrolment tested for at least one vendor: `opted_out_at` set ⇒ their messages now drop as
      `dropped_unverified`.
- [ ] **No vendor was cold-messaged** on the intake number. (The lane cannot send at all, but confirm
      no one did it manually from the device.)

## 3. Live drill (mirrors runbook R2 steps 4–6)

Run each on the real pilot infrastructure and record the audit disposition observed.

| #   | Action                                                          | Expected                                                | Observed disposition | Date | Operator |
| --- | --------------------------------------------------------------- | ------------------------------------------------------- | -------------------- | ---- | -------- |
| 1   | Pilot vendor sends photo + price from their verified number     | private draft created, **no outbound reply**            | `draft_created`      |      |          |
| 2   | Same message delivered twice (or WAHA retries)                  | no second draft, no second audit row                    | `draft_created` ×1   |      |          |
| 3   | Non-verified number messages the intake number                  | dropped, **no reply**                                   | `dropped_unverified` |      |          |
| 4   | Intake number added to a WhatsApp **group**, message sent there | dropped, no draft                                       | `dropped_group`      |      |          |
| 5   | Request with a bad signature                                    | `403`, nothing parsed                                   | `rejected_auth`      |      |          |
| 6   | Vendor opens the review page, corrects a field, submits         | listing created **`draft`**, never `active`             | —                    |      |          |
| 7   | Admin approves in the admin app                                 | listing becomes `active`; action appears in `audit_log` | —                    |      |          |

- [ ] After the drill, `vendor_listings` contains **no** row that reached `active` without step 7.

## 4. Kill-switch drill (mirrors runbook R4 — required for Stage 2)

- [ ] With work in flight, set `waha_vendor_intake = false` in the admin app.
- [ ] Confirm subsequent events audit as `dropped_flag_off` and create nothing.
- [ ] Confirm the pilot vendor's **existing draft is intact and still openable** in the vendor app.
- [ ] Confirm **Lane 1 is unaffected**: trigger a normal order notification and see it deliver.
- [ ] Record who ran the drill and when. Re-enable only by a recorded decision.

## 5. Retention & privacy (D35 §12)

- [ ] `waha-intake-sweeps.json` activated (or the endpoints called manually) and observed to run.
- [ ] After the retention window, confirm `intake_messages.raw_excerpt` is `NULL` for old rows while
      the message id, kind and **audit dispositions survive**.
- [ ] Confirm expired **unredeemed** review links are gone and **redeemed** ones are kept.
- [ ] Spot-check application logs: no raw message body, no full MSISDN.

## 6. Stage-2 exit criteria (founder sign-off)

All must hold before production widening. Any failure ⇒ **flip the flag off and stop**.

- [ ] No ban or quality event on the intake number for the whole pilot window.
- [ ] **Audit-verified**: zero group, customer, OTP, payment, or support messages processed.
- [ ] Draft quality acceptable to the reviewer — extraction is helping, not creating rework.
- [ ] The kill-switch and incident drills (§4, runbook R5) were rehearsed at least once.
- [ ] Media-failure and provider-error rates reviewed and judged acceptable.
- [ ] Founder records the go decision. **Widening the allowlist is itself an audited config change.**

### Sign-off

| Decision              | Date | Founder | Notes |
| --------------------- | ---- | ------- | ----- |
| Stage 1 — pilot start |      |         |       |
| Stage 2 — production  |      |         |       |
| Any abort / roll-back |      |         |       |

---

## Related

- `docs/ops/waha-vendor-intake.md` — Part A architecture, Part B runbook (R1–R6)
- `docs/plan/02-pebbles/M18-vendor-whatsapp-intake.md` — pebble spec P00–P08
- `docs/ops/n8n-workflows.md` — `waha-intake-sweeps.json`, `waha-intake-digest.json`
- `services/api/tests/e2e/test_intake_pilot.py` — the automated half of this proof
