-- RLS policy-contract remediation.
--
-- The M15 reply guards deliberately allow direct database maintenance when no
-- request JWT exists. Their former `session_user = postgres` bypass was too
-- broad for an impersonated request: a request with authenticated claims can
-- still arrive over a postgres-owned connection in a test or pool. Preserve
-- the maintenance escape hatch only when there are no request claims at all.

create or replace function public.guard_review_reply_columns()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  request_claims text := coalesce(current_setting('request.jwt.claims', true), '');
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  -- Direct psql maintenance/migration work has no JWT. A request carrying
  -- claims must never inherit this escape hatch merely because its connection
  -- is owned by postgres or supabase_admin.
  if request_claims = '' and session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if new.rating is distinct from old.rating
    or new.body is distinct from old.body
    or new.photos is distinct from old.photos
    or new.status is distinct from old.status
    or new.order_item_id is distinct from old.order_item_id
    or new.id is distinct from old.id
    or new.created_at is distinct from old.created_at then
    raise exception 'only vendor_reply fields may be updated on a review';
  end if;

  return new;
end;
$$;

create or replace function public.guard_service_review_reply_columns()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  request_claims text := coalesce(current_setting('request.jwt.claims', true), '');
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  if request_claims = '' and session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if new.rating is distinct from old.rating
    or new.body is distinct from old.body
    or new.status is distinct from old.status
    or new.job_id is distinct from old.job_id
    or new.provider_vendor_id is distinct from old.provider_vendor_id
    or new.customer_id is distinct from old.customer_id
    or new.id is distinct from old.id
    or new.created_at is distinct from old.created_at then
    raise exception 'only vendor_reply fields may be updated on a service review';
  end if;

  return new;
end;
$$;
