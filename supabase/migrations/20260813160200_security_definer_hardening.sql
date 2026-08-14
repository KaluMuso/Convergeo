-- Canonicalize sandbox rehearsal 20260813072511 (security-definer hardening).
-- Moves role/business checks into private SECURITY DEFINER helpers, keeps
-- public.has_role as SECURITY INVOKER delegator, and relocates extensions.

create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to anon, authenticated, service_role;

create or replace function private.has_role(required_role text)
returns boolean
language sql
stable
security definer
set search_path = public, extensions
as $$
  select exists (
    select 1
    from public.user_roles
    where user_id = auth.uid()
      and role = required_role
  )
$$;

revoke all on function private.has_role(text) from public;
grant execute on function private.has_role(text) to anon, authenticated, service_role;

create or replace function public.has_role(required_role text)
returns boolean
language sql
stable
security invoker
set search_path = private, public, extensions
as $$
  select private.has_role(required_role)
$$;

revoke all on function public.has_role(text) from public;
grant execute on function public.has_role(text) to anon, authenticated, service_role;

create or replace function private.is_verified_business(uid uuid)
returns boolean
language sql
stable
security definer
set search_path = public, extensions
as $$
  select exists (
    select 1
    from public.business_buyers
    where user_id = uid
      and status = 'verified'
  )
$$;

revoke all on function private.is_verified_business(uuid) from public;
grant execute on function private.is_verified_business(uuid) to service_role;

drop function if exists public.is_verified_business(uuid);

revoke all on function public.guard_kyc_record_integrity()
  from public, anon, authenticated;
grant execute on function public.guard_kyc_record_integrity()
  to postgres, service_role;

revoke all on function public.validate_service_review_verified_engagement()
  from public, anon, authenticated;
grant execute on function public.validate_service_review_verified_engagement()
  to postgres, service_role;

revoke all on function public.search_query_facets(text, vector, jsonb)
  from public, anon, authenticated;
grant execute on function public.search_query_facets(text, vector, jsonb)
  to service_role;

create schema if not exists extensions;
revoke all on schema extensions from public, anon, authenticated;

alter extension pg_trgm set schema extensions;
alter extension vector set schema extensions;
