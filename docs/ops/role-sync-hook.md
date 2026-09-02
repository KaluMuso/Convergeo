# Role-sync custom access token hook

Auto-provisions vendor/admin roles into the JWT so login works end-to-end
without manually editing Supabase App Metadata.

**Staging: CONFIRMED ENABLED.** Live Auth logs prove `public.
custom_access_token_hook` runs on token mint for staging and correctly
writes `public.user_roles` into `claims.app_metadata.roles` (verified via a
fresh Vendor OTP verification for the canonical approved-vendor persona).
**Production registration status is unchanged and still unverified** — do
not assume production behaves the same without independently confirming it
there first.

**Supabase projects (read-only verification):**

| Environment       | Project          | Ref                    |
| ----------------- | ---------------- | ---------------------- |
| Staging / sandbox | `vergeo-sandbox` | `iyasmrmbcrvlfxpzescb` |
| Production        | `Vergeo5`        | `dpadrlxukcjbewpqympu` |

On both projects, `public.custom_access_token_hook` exists and
`auth_admin_read_user_roles` is present on `public.user_roles`. Hook
**registration** in the Auth Dashboard remains unverified — treat as
`HOOK_REGISTRATION_UNVERIFIED` until an operator exports Dashboard evidence.

## The gap this closes

The vendor and admin middleware gate on the roles carried in the **verified
access token claims** (`packages/auth/src/middleware.ts` → `updateSession()`
→ `supabase.auth.getClaims()` → `packages/auth/src/roles.ts` →
`getRolesFromClaims(claims)`). Signup only ever grants the `customer` role
(`0010_profile_bootstrap.sql`). KYC approval now inserts
`public.user_roles.vendor` for `vendors.owner_user_id` (see
`docs/ops/vendor-role-lifecycle.md`) — **that row does not appear in any
issued token's claims until this hook is registered**.

The hook in `0051_custom_access_token_role_hook.sql` reads `public.user_roles`
on every token mint and injects the roles into `claims.app_metadata.roles`.
After it's enabled, granting a role is a single insert (already performed by
`ensure_vendor_owner_role`):

```sql
insert into public.user_roles (user_id, role) values ('<uid>', 'vendor');
```

(The user must re-authenticate or refresh their token for the new claim to
land.)

**Historical note:** middleware previously read `user.app_metadata.roles`
from the `User` object `getUser()` returns (`getRolesFromUser`) — a
DIFFERENT object from the token claims this hook writes into. The hook
mutates the issued token's claims only, never `auth.users.
raw_app_meta_data` (which is what `User.app_metadata` reflects), so that
old read path could never see a role granted this way even with the hook
correctly enabled and running. `getRolesFromUser` still exists for the one
other caller that genuinely needs the `User` object shape
(`apps/customer/.../vendor-portal-hub-card.tsx`, a cosmetic UI decision,
never a security gate) — middleware itself no longer calls it.

## Enable it (staging first — later operator work)

The migration only **creates** the function — it is dormant until registered.

- **Hosted project (production/staging):** Dashboard → Authentication → Hooks →
  **Custom Access Token** → enable → select `public.custom_access_token_hook`.
- **Local / self-host:** uncomment the stanza in `supabase/config.toml`:

  ```toml
  [auth.hook.custom_access_token]
  enabled = true
  uri = "pg-functions://postgres/public/custom_access_token_hook"
  ```

## Staging-first enablement checklist

The hook runs on **every** token mint — a runtime error can break **all
logins**. Do not skip staging certification.

1. **Backup / current config evidence.** Screenshot or export the Auth Hooks
   page for staging and production before any change. Record whether Custom
   Access Token is off (expected) or already pointed at another function.
2. **Verify function and grants** on the target project:
   - `public.custom_access_token_hook(jsonb)` exists.
   - `EXECUTE` granted to `supabase_auth_admin` only (revoked from
     `anon` / `authenticated` / `public`).
   - `auth_admin_read_user_roles` policy exists on `public.user_roles`.
3. **Enable the hook in STAGING only.** Do not enable production in the same
   change window.
4. **Authenticate a synthetic customer.** Decode the access token. Confirm
   `app_metadata.roles` is `["customer"]` (or the customer's actual
   `user_roles` set) and login succeeds.
5. **Authenticate a synthetic vendor** whose owner has `user_roles.vendor`
   after KYC approval. Confirm `app_metadata.roles` contains `"vendor"` and
   does **not** contain `"admin"`.
6. **Verify JWT `app_metadata.roles`** matches `public.user_roles` for both
   users. Confirm an account with only `customer` cannot pass Vendor
   middleware.
7. **Invalid-hook lockout drill.** Temporarily point the hook at a function
   that raises, or revoke execute, and confirm **all** logins fail — then
   restore immediately. This proves the blast radius and the rollback path
   before production. Do this only on staging.
8. **Test token refresh.** After granting `vendor` to an already-authenticated
   user, refresh the session and confirm the new claim appears without a full
   sign-out if refresh invokes the hook.
9. **Only after staging certification** consider Production, with the same
   backup evidence, synthetic customer/vendor checks, and a documented
   rollback owner.

## Rollback

Disable the hook in the Dashboard (or re-comment the config stanza). Do **not**
drop the function as part of a login incident unless the enabled hook is the
broken object; disabling registration is enough to restore default token mint.

If the function itself must be removed after disablement:

```sql
drop policy if exists "auth_admin_read_user_roles" on public.user_roles;
revoke execute on function public.custom_access_token_hook(jsonb) from supabase_auth_admin;
drop function if exists public.custom_access_token_hook(jsonb);
```

## Related follow-up (not included here)

The admin header's "Sign out" is a plain link to `/login` that does not clear
the Supabase session — a separate small fix (call `supabase.auth.signOut()`).
