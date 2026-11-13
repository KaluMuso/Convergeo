-- Merchant review M1/M2/M3: protected API writes and atomic quota admission.
-- Additive correction: published migration bytes are not replaced.
begin;

-- Listing writes require the existing moderated, KYC-aware service API.
-- Availability reads and service claim/release/sweep privileges are retained.
revoke insert, update, delete on public.vendor_listings from anon, authenticated;

create function public.guard_listing_minimum_identity() returns trigger
language plpgsql security invoker set search_path = pg_catalog, public
as $$
begin
  if new.min_steps is distinct from old.min_steps then
    raise sqlstate 'PT409' using message = 'stock.units_immutable';
  end if;
  return new;
end;
$$;
create trigger listing_minimum_identity_guard before update on public.vendor_listings
  for each row execute function public.guard_listing_minimum_identity();

create function public.guard_vendor_listing_admission() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_tier integer;
  v_max integer;
  v_count bigint;
begin
  if new.status not in ('draft', 'active', 'paused') then return new; end if;
  if tg_op = 'UPDATE' then
    if old.vendor_id = new.vendor_id and old.status in ('draft', 'active', 'paused') then
      return new;
    end if;
  end if;
  -- Dedicated admission scope, not the catalog/cart scope or a vendors row
  -- lock: stock adjustments already hold vendors FOR SHARE. The subsequent
  -- SPI queries obtain fresh READ COMMITTED snapshots after any lock wait.
  -- Repeatable-read callers must retry: their snapshot cannot count a newer
  -- admission. Do not silently certify a stale quota count.
  if current_setting('transaction_isolation') <> 'read committed' then
    raise sqlstate '40001' using message = 'listing_admission_requires_read_committed';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('listing-admission:' || new.vendor_id::text, 0));
  select coalesce(max(tier), 1) into v_tier from public.kyc_records
    where vendor_id = new.vendor_id and status = 'approved';
  select max_listings into v_max from public.vendor_quotas where tier = v_tier;
  if v_max is null then
    raise sqlstate 'PT500' using message = 'listing_quota_missing';
  end if;
  select count(*) into v_count from public.vendor_listings
    where vendor_id = new.vendor_id and status in ('draft', 'active', 'paused')
      and id <> new.id;
  if v_count >= v_max then
    raise sqlstate 'PT403' using message = 'listing_cap_exceeded';
  end if;
  return new;
end;
$$;
create trigger vendor_listing_admission_guard before insert or update on public.vendor_listings
  for each row execute function public.guard_vendor_listing_admission();
revoke all on function public.guard_vendor_listing_admission() from public, anon, authenticated;
revoke all on function public.guard_listing_minimum_identity() from public, anon, authenticated;

commit;
