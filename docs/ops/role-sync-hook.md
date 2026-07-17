# Role-sync custom access token hook

Auto-provisions vendor/admin roles into the JWT so login works end-to-end
without manually editing Supabase App Metadata.

## The gap this closes

The vendor and admin middleware gate on `user.app_metadata.roles`
(`packages/auth/src/roles.ts` → `getRolesFromUser`). Signup only ever grants the
`customer` role (`0010_profile_bootstrap.sql`), and KYC approval sets
`vendors.status` — **nothing writes `vendor`/`admin` into
`app_metadata.roles`**. So today a vendor/admin must have their role set by hand
(Dashboard → Authentication → the user → App Metadata) in addition to a
`public.user_roles` row.

The hook in `0051_custom_access_token_role_hook.sql` reads `public.user_roles`
on every token mint and injects the roles into `app_metadata.roles`. After it's
enabled, granting a role is a single insert:

```sql
insert into public.user_roles (user_id, role) values ('<uid>', 'vendor');
```

(The user must re-authenticate or refresh their token for the new claim to land.)

## Enable it

The migration only **creates** the function — it is dormant until registered.

- **Hosted project (production/staging):** Dashboard → Authentication → Hooks →
  **Custom Access Token** → enable → select `public.custom_access_token_hook`.
- **Local / self-host:** uncomment the stanza in `supabase/config.toml`:

  ```toml
  [auth.hook.custom_access_token]
  enabled = true
  uri = "pg-functions://postgres/public/custom_access_token_hook"
  ```

## ⚠️ Test in staging first

The hook runs on **every** token mint — a runtime error breaks **all logins**.
Before enabling in production:

1. Apply `0051` and enable the hook in **staging**.
2. Seed a role: `insert into public.user_roles (user_id, role) values ('<uid>', 'vendor');`
3. Sign that user in and decode their access token (jwt.io or
   `supabase.auth.getSession()` → inspect `access_token`). Confirm
   `app_metadata.roles` contains `["vendor"]`.
4. Confirm a user with **no** `user_roles` row still logs in (roles = `[]`).
5. Only then enable on production.

## Rollback

Disable the hook in the Dashboard (or re-comment the config stanza), then:

```sql
drop policy if exists "auth_admin_read_user_roles" on public.user_roles;
revoke execute on function public.custom_access_token_hook(jsonb) from supabase_auth_admin;
drop function if exists public.custom_access_token_hook(jsonb);
```

## Related follow-up (not included here)

The admin header's "Sign out" is a plain link to `/login` that does not clear
the Supabase session — a separate small fix (call `supabase.auth.signOut()`).
