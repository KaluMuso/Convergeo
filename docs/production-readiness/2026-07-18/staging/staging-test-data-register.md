# Staging test-data register — 2026-07-19

**Purpose:** Track uniquely prefixed staging-only records for repeatability and controlled cleanup.  
**Session status:** **NO ROWS CREATED** — Phase 2 blocked by missing staging separation (`staging-blockers.md` SB-01/SB-02).

---

## Safety declaration

| Check                                                | Result                        |
| ---------------------------------------------------- | ----------------------------- |
| Staging DB project ref ≠ prod `dpadrlxukcjbewpqympu` | **FAIL** — no staging project |
| Staging API host ≠ `api.vergeo5.com`                 | **FAIL** — no staging API     |
| Staging payment provider = Lenco sandbox             | **UNPROVEN**                  |
| Mutations executed this session                      | **NONE**                      |

Therefore the register below is a **plan only**. Redacted ID columns remain empty until a proven staging stack exists.

---

## Naming convention (reserved)

Prefix: `stg-rv-20260719`  
Slug pattern: `stg-rv-20260719-<role>-<nn>`  
Cleanup owner: staging release engineer (same wave that seeds)

Never reuse these prefixes on production.

---

## Planned fixture set (not created)

| Logical role                    | Planned handle             | Planned purpose                  | Created? | Redacted IDs | Cleanup                           |
| ------------------------------- | -------------------------- | -------------------------------- | -------- | ------------ | --------------------------------- |
| Customer buyer                  | `stg-rv-20260719-cust-01`  | browse + checkout                | NO       | —            | delete profile/orders after drill |
| Unverified vendor               | `stg-rv-20260719-vend-unv` | KYC gate / bare tier freeze      | NO       | —            | delete vendor + listings          |
| Vendor KYC submitted            | `stg-rv-20260719-vend-sub` | submit → under_review            | NO       | —            | delete kyc_records + docs         |
| Approved vendor (auditable KYC) | `stg-rv-20260719-vend-apr` | catalogue + release path         | NO       | —            | retain until post-drill wipe      |
| Unauthorized admin-like user    | `stg-rv-20260719-adm-bad`  | expect 403 on KYC review         | NO       | —            | revoke roles                      |
| Authorized KYC reviewer         | `stg-rv-20260719-adm-kyc`  | start-review / approve / suspend | NO       | —            | revoke after drill                |
| Product listing                 | `stg-rv-20260719-list-prd` | product checkout/release         | NO       | —            | unpublish/delete                  |
| Service job fixture             | `stg-rv-20260719-job-01`   | service release path             | NO       | —            | cancel/delete                     |
| Event order fixture             | `stg-rv-20260719-evt-01`   | event release + tickets          | NO       | —            | refund/cancel staging only        |
| Checkout / payment (sandbox)    | `stg-rv-20260719-pay-*`    | MoMo + card collection           | NO       | —            | void/sandbox only                 |

---

## Money / ledger IDs (to fill after S1–S3)

| Rail            | payment_id (redacted) | order_id (redacted) | CHARGE_RECEIVED txn | COMMISSION_CAPTURE | RELEASE_TO_VENDOR | Notes   |
| --------------- | --------------------- | ------------------- | ------------------- | ------------------ | ----------------- | ------- |
| MoMo sandbox    | —                     | —                   | —                   | —                  | —                 | not run |
| Card sandbox    | —                     | —                   | —                   | —                  | —                 | not run |
| Product release | —                     | —                   | —                   | —                  | —                 | not run |
| Service release | —                     | —                   | —                   | —                  | —                 | not run |
| Event release   | —                     | —                   | —                   | —                  | —                 | not run |
| Webhook replay  | —                     | —                   | —                   | n/a                | n/a               | not run |

---

## KYC drill IDs (to fill after S5)

| Step          | vendor_id (redacted) | kyc_record_id (redacted) | reviewer_id (redacted) | Result  |
| ------------- | -------------------- | ------------------------ | ---------------------- | ------- |
| submit        | —                    | —                        | —                      | not run |
| start-review  | —                    | —                        | —                      | not run |
| approve       | —                    | —                        | —                      | not run |
| reject        | —                    | —                        | —                      | not run |
| suspend       | —                    | —                        | —                      | not run |
| revoke        | —                    | —                        | —                      | not run |
| orphan report | —                    | n/a                      | —                      | not run |

---

## Cleanup checklist (future)

- [ ] Cancel open staging orders / release holds
- [ ] Delete `stg-rv-20260719-*` listings, vendors, profiles
- [ ] Remove private KYC objects under staging storage prefix
- [ ] Confirm ledger orphan count for prefix = 0
- [ ] Rotate any temporary Access / OTP test grants

**Current cleanup:** nothing to clean — no staging writes performed.
