# Supabase SECURITY DEFINER inventory and remediation contract

**Observed:** 2026-08-13 through read-only Supabase Security Advisors on
production (`0071`) and isolated sandbox (future-schema tip). This document
classifies warnings; it does not change grants or run SQL.

Supabase's current guidance is to prefer invoker functions, pin `search_path`
for any necessary definer function, revoke default `PUBLIC` execution, and
grant only the role that needs a callable RPC. The relevant guidance is
[Database Functions](https://supabase.com/docs/guides/database/functions) and
[RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

## Classification

| Class | Functions | Required treatment |
| --- | --- | --- |
| Trigger/internal only | `guard_kyc_record_integrity`, `validate_service_review_verified_engagement`, `clip_products_guard`, `enquiry_threads_guard`, `guard_vendor_licence_status_update`, `listing_location_stock_guard`, `rfq_threads_guard`, `storefront_collection_items_guard` | Revoke direct execution from `PUBLIC`, `anon`, and `authenticated`; trigger invocation remains intact. Prove a direct RPC is denied and its guarded table transition still works. |
| Service-only RPC | `search_query_facets`, `clip_bump_counter`, `clip_record_spend`, `reset_clip_kill_switch`, `record_listing_view` | Grant only `service_role`; prove anon/authenticated are denied and the FastAPI service path remains functional. `clip_bump_counter` is intended this way already, so advisor drift is a verification failure, not a reason to broaden a grant. |
| Narrow user RPC | `vendor_follower_count` | Keep `authenticated` only after a real-owner / non-owner / admin matrix proves it returns a count and never identities. Revoke `PUBLIC` and `anon`. |
| Deliberately public derived boolean | `vendor_licence_is_valid` | May be `anon`/`authenticated` because it returns only a boolean and unknown vendors are indistinguishable from invalid ones. Prove no licence number, dates, or reviewer notes are disclosed. |
| RLS helper — do not blindly revoke | `has_role`, `is_verified_business` | Both are referenced from existing RLS policies. Removing execution without a policy-compatible replacement can break authorization. First inventory every policy caller, then add a tightly scoped policy/RPC design and prove all affected RLS cells before changing grants. |

## Other advisor findings

- `audit_log`, `notification_outbox`, `order_money_gates`, `rate_counters`, and
  `stock_reservations` report RLS with no policies. They are intended service/
  trigger/internal tables, but this must be proven by direct anon and
  authenticated denial tests—not silenced by disabling RLS.
- `listing_line_total_ngwee` is reported with a mutable search path in sandbox.
  It is an immutable arithmetic helper. Before changing it, prove every
  relation/operator reference is schema-qualified and pin the path in a
  separate additive hardening migration with replay and function-result tests.
- `pg_trgm` and `vector` are installed in `public`. Moving extensions after
  production use has broad operator/type dependency risk; treat it as a
  dedicated compatibility project, not an in-window incidental change.
- Leaked-password protection is an Auth dashboard/operational decision, not a
  migration workaround; record its status separately.

## Required evidence before any grant/search-path migration

1. Capture advisor output for both projects and record the source SHA.
2. Enumerate exact function signatures plus direct API callers and trigger or
   RLS references; overloaded functions require signature-specific grants.
3. Rehearse a **narrow** additive change in sandbox: execute denied for every
   internal function, allowed only for the documented caller, trigger and RLS
   regression matrix still green, and no Data API endpoint becomes broader.
4. Pin `search_path` only with fully qualified object references or an empty
   path plus explicit schemas. Never add `SECURITY DEFINER` merely to bypass an
   RLS failure.
5. Re-run Security Advisors and attach before/after evidence to the production
   change window. No blanket revocation is accepted because it can silently
   break RLS policy evaluation.
