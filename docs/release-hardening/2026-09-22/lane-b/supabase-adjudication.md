# Supabase security-advisor adjudication

Observation only. Production was not mutated.

- Project inspected read-only: production ref `dpadrlxukcjbewpqympu`
- Observed at: `2026-09-22T12:46:31.115Z`
- Advisor result: 15 `INFO` RLS-enabled/no-policy tables, 2 anonymous SECURITY DEFINER warnings, 3 authenticated SECURITY DEFINER warnings, and leaked-password protection disabled.

## SECURITY DEFINER functions

| Function                                       | EXECUTE grants                              | Intended caller/evidence                                                                                                                                                             | Least-privilege finding                                                                                                                                                                                                    | Disposition                                                                                                                                                                              |
| ---------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `public.product_class_customer_released(char)` | `anon`, `authenticated`, `service_role`     | Boolean feature flag used by four customer-facing RLS policies and a product-strategy enforcement trigger                                                                            | Public boolean lookup is intentional; owner is `postgres`; SQL stable SECURITY DEFINER; `search_path` is empty and referenced objects are qualified                                                                        | Retain grants; no migration in Lane B                                                                                                                                                    |
| `public.vendor_follower_count(uuid)`           | `authenticated`, `service_role`; not `anon` | Vendor/admin metric; body checks vendor ownership through `auth.uid()` or `public.has_role('admin')` before counting                                                                 | Grant scope matches intended authenticated caller. `search_path=public` is not presently hijackable by `anon`/`authenticated` because they lack `CREATE` on `public`, but an empty, fully qualified search path is tighter | Bounded migration follow-up; do not revoke blindly                                                                                                                                       |
| `public.vendor_licence_is_valid(uuid,text)`    | `anon`, `authenticated`, `service_role`     | Boolean licence/badge helper. Existing readiness audit classifies it as intentional, but current source search found no live runtime caller outside generated types/tests/migrations | Public grant may be legacy. Function is SQL stable SECURITY DEFINER with `search_path=public`; underlying licence table is not directly selectable by `anon`                                                               | Owner must confirm the public badge contract. If retained, add caller/authorization tests and qualify objects with empty search path; otherwise revoke only after call-site confirmation |

The underlying tables inspected are RLS-enabled with forced RLS. Direct table grants and function grants were reviewed separately; a SECURITY DEFINER warning is not by itself proof that the function is exploitable.

## RLS-enabled tables with no policies

The advisor listed: `audit_log`, `event_access_credentials`, `event_affiliates`, `event_campaigns`, `event_gmv_reservations`, `event_promo_codes`, `event_refund_jobs`, `event_reschedules`, `event_settlement_snapshots`, `event_team_invites`, `event_team_members`, `notification_outbox`, `order_money_gates`, `rate_counters`, and `stock_reservations`.

These are informational observations, not automatically missing policies. Their names and current grants are consistent with service-only/internal state for several tables. A follow-up must map each legitimate caller before adding any policy; blanket policies would widen access and are not justified.

## Configuration action

Leaked-password protection is disabled and is a production Auth configuration action, not a database migration. An authorized operator must enable it in the Supabase Auth password-security settings, record the change/effective time, and verify the intended login/reset behavior. Lane B made no configuration change.

## Separation of work

- **Code change:** dependency locks, fail-closed audit parser/tests, and exact non-secret gitleaks fixture classification.
- **Database migration:** none in this candidate. Search-path hardening/caller-contract changes require a separate reviewed migration.
- **Production configuration:** enable leaked-password protection through an authorized operator change.
- **Manual/external configuration:** explicit security-owner decision for the two unpatched `extract-zip` advisories; hosted CI and independent review after publication authorization.
