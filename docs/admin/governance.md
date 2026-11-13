# Admin governance (founder decisions 2026-11-13)

Source: `docs/audit/2026-11-analytics-rbac/report.md` (section G) and the founder's
answers of 2026-11-13: "D1–D5 as recommended, D6: none yet", a separate services
permission, in-app delivery-partner consent, and — when convenient — specialised roles,
a customer-support role, an audit-log screen and admin account management.

## Roles and permissions

| Role / permission  | What it reaches                                                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `superadmin`       | Everything, including role definitions, assignments, admin accounts and the audit log                                                      |
| `admin` (legacy)   | Everything at the API except role/account management and the audit log (`audit.read` is never implied)                                     |
| `finance.read`     | Order search and detail, disputes list/detail and notes, finance tiles on the dashboard                                                    |
| `finance.operate`  | D2: refunds, escrow release/hold, order intervention, dispute decisions and notes, COD confirm/refuse (plus the finance reads)             |
| `support.manage`   | Customer lookup with **masked phone numbers**, contact log, outbound support message, disputes read and internal notes                     |
| `services.manage`  | Services list, pause/restore a service listing, service providers, RFQ request moderation (close open/quoted requests)                     |
| `events.manage`    | High-value verification, events list, organisers, unpublish (sold tickets stay valid), cancel (paid tickets queued for refund)             |
| `logistics.manage` | Courier dispatch board, couriers, dispatch requests, handover codes, manual order dispatch. Same name as the logistics blueprint (Phase 0) |
| `audit.read`       | The read-only audit-log viewer                                                                                                             |

`analytics.read`, `products.manage`, `vendors.manage`, `ads.manage`, `services.read` and
`inventory.read` are unchanged. A superadmin combines permissions into `rbac_*` roles on
the Admin roles screen. No second approver exists yet (D2 says "once volume justifies").

Source of truth: `services/api/app/core/auth.py` (`_ADMIN_ROUTE_PERMISSION_SPEC`) and the
reviewed role × route matrix `services/api/tests/test_admin_role_route_matrix.py`.

## Deactivating an administrator (D4)

**Deactivate = revoke every admin role.** Use Admin accounts → Deactivate (superadmin
only): it removes `superadmin`, `admin`, `moderator` and every `rbac_*` role in one
transaction (`public.deactivate_admin_account`), requires a reason, and writes an
`admin.account.deactivate` audit row. The API re-reads roles on every request, so the
next call with the same token is refused. The Supabase login is **not** banned: the
person keeps customer or vendor access they had. The last superadmin cannot be removed,
and a superadmin cannot deactivate their own account. A Supabase ban is not checked by
the API — do not rely on it.

## Database posture (D1)

Migration `20261113163000_admin_direct_writes_read_only.sql` removed every
`has_role('admin')` write policy on public tables (75 tables, after S1's six money
tables). Admins read through `<table>_admin_select`; every admin write goes through the
API as `service_role`, past state machines and the audit log. Manual down:
`docs/audit/2026-11-analytics-rbac/d1-down.sql`.

Residual, by design for now: 17 guard trigger functions still exempt `has_role('admin')`
from "server-controlled column" checks. After D1 that exemption is reachable only by an
admin who is also the owner of the row (their own profile, their own vendor). **Do not
give `admin` to anyone who also trades on the platform**; give them a scoped `rbac_*`
role instead.

## Audit trail (report S5)

`public.audit_log` now records `actor_roles` (filled from `user_roles` at insert when the
writer does not supply them), `outcome` (`success`, `denied`, `failed`), `request_id` and
`reason`. It is append-only for every role, `service_role` included (UPDATE, DELETE and
TRUNCATE are refused by trigger). Refused attempts by operators on admin routes are
written as `admin.access.denied` with `outcome = denied` (customers and vendors probing
`/admin` are not recorded). Login success/failure still lives only in Supabase Auth logs.

The Audit log screen (`/audit-log`) filters by actor, action (a trailing dot matches a
family, e.g. `admin.orders.`), resource type and ID, outcome and date range, and masks
phone numbers, emails, names, addresses, codes and tokens in `before`/`after`.

## Delivery-partner consent (Zambia DPA 2021)

Customers allow or withdraw "share my name, phone and address with the delivery partner"
in Account → Privacy or at checkout (delivery orders only; the checkbox is optional and
unticked by default). Each answer is a row in `public.privacy_consents` with the notice
version (`2026-11-13`), source and timestamp; the newest row wins and history cannot be
edited. A courier dispatch is refused (API `409 delivery_consent_required`, and the
`dispatch_requests_require_delivery_consent` trigger) unless the customer's current
answer is yes; the courier message is also withheld after a withdrawal. Pickup orders
never reach a courier. Without consent, deliver with Vergeo5 staff or ask the customer.

When the consent wording changes materially, bump `DELIVERY_PARTNER_NOTICE_VERSION`
(API) and `DELIVERY_CONSENT_VERSION` (customer app) together, and update
`has_delivery_partner_consent()` if older versions must stop counting.
