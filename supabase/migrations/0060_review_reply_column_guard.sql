-- 0060_review_reply_column_guard.sql
-- Column guard for vendor review replies — the "column guard in M15" deferred at
-- 0007_trust_ops.sql (reviews_vendor_reply_update comment).
--
-- The vendor-reply UPDATE policies on public.reviews (0007) and public.service_reviews
-- (0054) gate only the ROW (the caller owns the reviewed listing / is the job's
-- provider vendor) — they impose no COLUMN restriction, and both tables carry a broad
-- `grant update ... to authenticated`. A vendor can therefore PATCH their own review's
-- rating / body / status directly via PostgREST (inflate their star rating, hide a
-- negative review by flipping status to 'removed'), corrupting review_aggregates and
-- the 0034 search rating boost and subverting the verified-purchase guarantee.
--
-- These BEFORE UPDATE triggers reject any change to a non-reply column for
-- non-admin / non-service sessions, allowing only vendor_reply / vendor_reply_at
-- (updated_at is maintained by set_updated_at). Admins (has_role('admin')) and the
-- service-role API keep full moderation control. Mirrors public.guard_vendor_status_update
-- (0002_identity_vendors.sql). Additive + reversible.
--
-- Down (manual):
--   drop trigger reviews_guard_reply_columns on public.reviews;
--   drop trigger service_reviews_guard_reply_columns on public.service_reviews;
--   drop function public.guard_review_reply_columns();
--   drop function public.guard_service_review_reply_columns();

create or replace function public.guard_review_reply_columns()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
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

create trigger reviews_guard_reply_columns
  before update on public.reviews
  for each row
  execute function public.guard_review_reply_columns();

create or replace function public.guard_service_review_reply_columns()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
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

create trigger service_reviews_guard_reply_columns
  before update on public.service_reviews
  for each row
  execute function public.guard_service_review_reply_columns();
