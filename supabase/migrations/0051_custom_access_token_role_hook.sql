-- 0051: Custom access token hook — auto-sync public.user_roles → JWT app_metadata.roles.
--
-- Closes the role-provisioning gap: today a vendor/admin's role must be set BY HAND
-- in Supabase App Metadata (the vendor/admin middleware gates on
-- user.app_metadata.roles — see packages/auth/src/roles.ts), because nothing syncs
-- public.user_roles into the token. This hook injects the caller's roles into
-- app_metadata.roles on every token mint, so inserting a row into user_roles is all
-- that's needed to grant a role.
--
-- ⚠️ DORMANT UNTIL ENABLED. Creating this function changes nothing on its own — the
-- hook only runs once it is registered:
--   * Hosted project: Dashboard → Authentication → Hooks → Custom Access Token →
--     select public.custom_access_token_hook.
--   * Local / self-host: uncomment the [auth.hook.custom_access_token] stanza in
--     supabase/config.toml with
--       uri = "pg-functions://postgres/public/custom_access_token_hook"
--
-- ⚠️ TEST IN STAGING FIRST. The hook runs on EVERY token mint; a runtime error here
-- breaks all logins. Verify a token contains app_metadata.roles for a user with a
-- user_roles row before enabling in production. See docs/ops/role-sync-hook.md.
--
-- Reversible: drop the policy, revoke the grants, drop the function.

create or replace function public.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
security invoker
set search_path = public
as $$
declare
  claims jsonb;
  user_roles text[];
begin
  select coalesce(array_agg(role order by role), array[]::text[])
  into user_roles
  from public.user_roles
  where user_id = (event->>'user_id')::uuid;

  claims := coalesce(event->'claims', '{}'::jsonb);
  if claims ? 'app_metadata' then
    claims := jsonb_set(claims, '{app_metadata,roles}', to_jsonb(user_roles));
  else
    claims := jsonb_set(
      claims, '{app_metadata}', jsonb_build_object('roles', to_jsonb(user_roles))
    );
  end if;

  return jsonb_set(event, '{claims}', claims);
end;
$$;

-- The hook is invoked by the supabase_auth_admin role; it must be able to call the
-- function and read public.user_roles. No other role should execute it.
grant usage on schema public to supabase_auth_admin;
grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook(jsonb) from anon, authenticated, public;
grant select on table public.user_roles to supabase_auth_admin;

-- user_roles has RLS enabled with no policies (deny-all by design). Add a SELECT
-- policy scoped ONLY to the auth admin so the hook can read roles at token mint.
drop policy if exists "auth_admin_read_user_roles" on public.user_roles;
create policy "auth_admin_read_user_roles" on public.user_roles
  as permissive for select to supabase_auth_admin using (true);

comment on function public.custom_access_token_hook(jsonb) is
  'Supabase custom access token hook: injects public.user_roles into JWT app_metadata.roles. Dormant until registered as the custom_access_token auth hook.';
