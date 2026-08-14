-- Canonicalize sandbox rehearsals 20260813072110 + 20260813072919 (listing telemetry).
-- Adds surface dimension to dedup PK and replaces the 4-arg record_listing_view
-- overload with a 6-arg contract that keeps 4-arg callers working via defaults.

alter table public.listing_view_dedup
  add column if not exists surface text not null default 'unknown'
  check (surface in ('home', 'plp', 'storefront', 'pdp', 'unknown'));

alter table public.listing_view_dedup drop constraint if exists listing_view_dedup_pkey;

alter table public.listing_view_dedup
  add primary key (session_id, listing_id, day, view_kind, surface);

create index if not exists listing_view_dedup_surface_day_idx
  on public.listing_view_dedup (surface, day desc);

drop function if exists public.record_listing_view(uuid, uuid, date, text);

create or replace function public.record_listing_view(
  p_session_id uuid,
  p_listing_id uuid,
  p_day date,
  p_view_kind text,
  p_surface text default 'unknown',
  p_viewer_user_id uuid default null
)
returns integer
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if p_view_kind not in ('impression', 'pdp_view')
     or p_surface not in ('home', 'plp', 'storefront', 'pdp', 'unknown') then
    raise exception 'invalid listing view telemetry dimensions';
  end if;

  if p_viewer_user_id is not null
     and exists (
       select 1
       from public.vendor_listings vl
       join public.vendors v on v.id = vl.vendor_id
       where vl.id = p_listing_id
         and v.owner_user_id = p_viewer_user_id
     ) then
    return 0;
  end if;

  insert into public.listing_view_dedup (session_id, listing_id, day, view_kind, surface)
  values (p_session_id, p_listing_id, p_day, p_view_kind, p_surface)
  on conflict do nothing;

  if not found then
    return 0;
  end if;

  insert into public.listing_analytics as la (listing_id, day, impressions, pdp_views)
  values (
    p_listing_id,
    p_day,
    case when p_view_kind = 'impression' then 1 else 0 end,
    case when p_view_kind = 'pdp_view' then 1 else 0 end
  )
  on conflict (listing_id, day) do update
    set impressions = la.impressions + excluded.impressions,
        pdp_views = la.pdp_views + excluded.pdp_views,
        updated_at = timezone('utc', now());

  return 1;
end;
$$;

revoke all on function public.record_listing_view(uuid, uuid, date, text, text, uuid)
  from public, anon, authenticated;
grant execute on function public.record_listing_view(uuid, uuid, date, text, text, uuid)
  to service_role;
