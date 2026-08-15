# Privileged function security audit — 2026-08-15 (SEC-DB-01)

**Scope:** Supabase Security Advisor `SECURITY DEFINER` EXECUTE findings on staging (`iyasmrmbcrvlfxpzescb`) and production (`dpadrlxukcjbewpqympu`).

**Migration:** `20260815194500_privileged_function_execute_hardening.sql` (after `20260813160200`).

**Apply:** staging first via normal `db push` after ledger repair. **Do not apply to production in this PR.**

---

## Classification key

| Class               | Meaning                                                                   |
| ------------------- | ------------------------------------------------------------------------- |
| SAFE_INTENDED       | Callable by anon/authenticated by design; discloses only policy-safe data |
| SERVICE_ROLE_ONLY   | Backend / trigger internal; revoked from anon/authenticated               |
| INTERNAL_WORKER_RPC | n8n / service_role ticks only                                             |
| AUTHENTICATED_RPC   | Authenticated-only public RPC                                             |
| FIXED_BY_60200      | Addressed in `20260813160200_security_definer_hardening.sql`              |
| FIXED_BY_194500     | Addressed in this migration                                               |

---

## Functions audited (Security Advisor + migration trace)

| Function                                               | Class             | Action                                                                           |
| ------------------------------------------------------ | ----------------- | -------------------------------------------------------------------------------- |
| `private.has_role(text)`                               | SERVICE_ROLE_ONLY | FIXED_BY_60200 — grant anon/authenticated for RLS evaluation via invoker wrapper |
| `public.has_role(text)`                                | SAFE_INTENDED     | FIXED_BY_60200 — SECURITY INVOKER delegator                                      |
| `private.is_verified_business(uuid)`                   | SERVICE_ROLE_ONLY | FIXED_BY_60200 — service_role only; public wrapper dropped                       |
| `public.is_verified_business(uuid)`                    | SUPERSEDED        | FIXED_BY_60200 — dropped; API uses service_role table reads                      |
| `public.guard_kyc_record_integrity()`                  | SERVICE_ROLE_ONLY | FIXED_BY_60200                                                                   |
| `public.validate_service_review_verified_engagement()` | SERVICE_ROLE_ONLY | FIXED_BY_60200                                                                   |
| `public.search_query_facets(...)`                      | SERVICE_ROLE_ONLY | FIXED_BY_60200                                                                   |
| `public.clip_bump_counter(...)`                        | SERVICE_ROLE_ONLY | FIXED_BY_194500 — re-assert after rehearsal drift                                |
| `public.clip_record_spend(...)`                        | SERVICE_ROLE_ONLY | FIXED_BY_194500                                                                  |
| `public.reset_clip_kill_switch(text)`                  | SERVICE_ROLE_ONLY | FIXED_BY_194500                                                                  |
| `public.clip_products_guard()`                         | SERVICE_ROLE_ONLY | FIXED_BY_194500 — trigger guard                                                  |
| `public.enquiry_threads_guard()`                       | SERVICE_ROLE_ONLY | FIXED_BY_194500                                                                  |
| `public.listing_location_stock_guard()`                | SERVICE_ROLE_ONLY | FIXED_BY_194500                                                                  |
| `public.rfq_threads_guard()`                           | SERVICE_ROLE_ONLY | FIXED_BY_194500                                                                  |
| `public.storefront_collection_items_guard()`           | SERVICE_ROLE_ONLY | FIXED_BY_194500                                                                  |
| `public.guard_vendor_licence_status_update()`          | SERVICE_ROLE_ONLY | FIXED_BY_194500                                                                  |
| `public.vendor_licence_is_valid(uuid, text)`           | SAFE_INTENDED     | No change — boolean badge RPC (0084)                                             |
| `public.vendor_follower_count(uuid)`                   | AUTHENTICATED_RPC | No change — vendor metric only (0083)                                            |
| `public.product_class_customer_released(char)`         | SAFE_INTENDED     | Already revoked from PUBLIC; granted anon/authenticated (64106)                  |
| `public.listing_line_total_ngwee(bigint, integer)`     | SAFE_INTENDED     | FIXED_BY_194500 — pinned search_path (immutable SQL helper)                      |
| `public.bump_rate_counter(...)`                        | SERVICE_ROLE_ONLY | Already correct in 160000                                                        |
| `public.record_listing_view(...)`                      | SERVICE_ROLE_ONLY | Already correct in 160100                                                        |
| `public.approve_kyc_vendor(...)`                       | SERVICE_ROLE_ONLY | Already correct in 150000                                                        |

All other `SECURITY DEFINER` functions from migrations `0001`–`0096` were swept in `0050` or subsequent guarded migrations (`0056`–`0063`, `20260809214010`, etc.).

---

## Environment action (not in migration)

| Item                                | Owner   | Notes                                                                 |
| ----------------------------------- | ------- | --------------------------------------------------------------------- |
| Supabase leaked-password protection | Founder | Enable on staging + production Auth settings after user-impact review |

---

## Verification

```sql
-- No anon/authenticated EXECUTE on internal trigger guards:
SELECT routine_name, grantee
FROM information_schema.routine_privileges
WHERE routine_schema = 'public'
  AND routine_name IN (
    'clip_products_guard', 'enquiry_threads_guard',
    'listing_location_stock_guard', 'rfq_threads_guard',
    'storefront_collection_items_guard', 'guard_vendor_licence_status_update'
  )
  AND grantee IN ('anon', 'authenticated')
ORDER BY 1, 2;
-- expect 0 rows

-- Service-role-only clip RPCs:
SELECT routine_name, grantee
FROM information_schema.routine_privileges
WHERE routine_schema = 'public'
  AND routine_name IN ('clip_bump_counter', 'clip_record_spend', 'reset_clip_kill_switch')
  AND grantee IN ('anon', 'authenticated');
-- expect 0 rows
```

Automated: `services/api/tests/rls/test_privileged_function_grants.py`
