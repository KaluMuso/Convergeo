# Vendor role lifecycle

Portal identity (`public.user_roles.role = vendor`) is distinct from commercial
capability (`vendors.status` + KYC eligibility).

## Where the role is granted

Authoritative grant: `transition_approve` in
`services/api/app/services/kyc/state_machine.py`, via
`ensure_vendor_owner_role`.

The grant is:

- service-role only (API, never the browser);
- tied to `vendors.owner_user_id` of an already-`active` Vendor;
- idempotent (`user_roles_user_id_role_key`);
- auditable (`audit_log` action `kyc.approve`, `after.vendor_role`);
- rolled back if the grant fails after KYC/vendor rows were updated, so we do
  not leave `vendors.status = active` without the owner role.

Signup (`0010_profile_bootstrap.sql`) still grants **customer only**. Draft
Vendor creation, onboarding, KYC submit, and pending KYC do **not** grant
`vendor`.

## Status contract

| Event | Vendor / KYC | `user_roles.vendor` | Commercial capability |
| ----- | ------------ | ------------------- | --------------------- |
| Signup | none | no | none |
| Draft / onboarding / KYC submitted | `draft` / `pending_kyc` | no | not privileged |
| **KYC approved** | `vendors.status=active`, KYC `approved` | **grant exactly once** | privileged (`active`) |
| KYC rejected | KYC `rejected`; vendor unchanged | no grant | not privileged |
| Suspend | vendor `suspended`, KYC `suspended`, tier cleared | **keep** | blocked (`PRIVILEGED_VENDOR_STATUSES` is `active`/`pending_kyc` only) |
| Compliance suspend | `suspended_compliance` | **keep** | listings removed / selling blocked by status |
| KYC revoked | vendor `draft`, KYC `revoked` | **keep** | not privileged; owner can remediate in the portal |
| Reactivation | re-submit then re-approve | idempotent keep | restored when `active` again |

Do not strip `vendor` on every non-active status. A suspended Vendor still
needs portal access to see compliance/remediation state.

API listing/payout/wholesale checks must keep using Vendor status and KYC
eligibility, not the role alone.

## JWT / middleware

Vendor Next.js middleware reads JWT `app_metadata.roles`. The custom access
token hook (`0051`) copies `user_roles` into that claim **only after it is
registered**. Enabling the hook is a separate staging-first operator step;
see `docs/ops/role-sync-hook.md`. Do not enable it from this change.

Until the hook is registered, a `user_roles.vendor` row is sufficient for the
API (`get_current_user` loads `public.user_roles`) but Vendor frontend
middleware will still treat the user as a non-Vendor.
