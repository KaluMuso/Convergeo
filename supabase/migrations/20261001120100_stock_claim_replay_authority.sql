-- Merchant review M4: bind a claim before consuming availability, and retain
-- its identity after release/sweep so a lost response cannot consume twice.
begin;

create table public.stock_claim_identities (
  listing_id uuid not null references public.vendor_listings(id) on delete cascade,
  checkout_group_id uuid not null references public.checkout_groups(id) on delete cascade,
  qty integer not null check (qty > 0),
  location_id uuid,
  remaining_stock_qty integer,
  state text not null check (state in ('pending', 'claimed', 'released', 'rejected')),
  created_at timestamptz not null default now(),
  primary key (listing_id, checkout_group_id)
);
alter table public.stock_claim_identities enable row level security;
alter table public.stock_claim_identities force row level security;
revoke all on public.stock_claim_identities from public, anon, authenticated, service_role;

-- Adopt live claims without decrementing again. The historical original
-- remaining quantity is unavailable; compatible replay reads current stock.
insert into public.stock_claim_identities(listing_id, checkout_group_id, qty, location_id, state)
  select listing_id, checkout_group_id, qty, location_id, 'claimed'
  from public.stock_reservations;

create function public.close_stock_claim_identity() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
begin
  update public.stock_claim_identities set state = 'released'
    where listing_id = old.listing_id and checkout_group_id = old.checkout_group_id;
  return old;
end;
$$;
create trigger stock_claim_identity_release after delete on public.stock_reservations
  for each row execute function public.close_stock_claim_identity();

create function public.claim_stock_reservation(
  p_listing_id uuid, p_checkout_group_id uuid, p_qty integer,
  p_location_id uuid, p_expires_at timestamptz
) returns integer
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_claim public.stock_claim_identities%rowtype;
  v_listing public.vendor_listings%rowtype;
  v_branch boolean;
  v_remaining integer;
begin
  if p_listing_id is null or p_checkout_group_id is null or p_qty is null
     or p_qty <= 0 or p_expires_at is null then
    raise sqlstate 'PT422' using message = 'stock.invalid_claim';
  end if;
  insert into public.stock_claim_identities(listing_id, checkout_group_id, qty, location_id, state)
    values(p_listing_id, p_checkout_group_id, p_qty, p_location_id, 'pending')
    on conflict (listing_id, checkout_group_id) do nothing;
  select * into strict v_claim from public.stock_claim_identities
    where listing_id = p_listing_id and checkout_group_id = p_checkout_group_id for update;
  if v_claim.qty <> p_qty or v_claim.location_id is distinct from p_location_id then return null; end if;
  if v_claim.state in ('released', 'rejected') then return null; end if;
  if v_claim.state = 'claimed' then
    -- No reservation row lock: release/sweep delete the reservation then mark
    -- this identity terminal. Replaying before that terminalization is a
    -- read of the original claim, never another stock mutation. This avoids
    -- identity/reservation lock inversion with the established release path.
    if not exists(select 1 from public.stock_reservations
      where listing_id = p_listing_id and checkout_group_id = p_checkout_group_id
        and qty = p_qty and location_id is not distinct from p_location_id) then
      return null;
    end if;
    if v_claim.remaining_stock_qty is not null then return v_claim.remaining_stock_qty; end if;
    if p_location_id is null then
      select stock_qty into v_remaining from public.vendor_listings where id = p_listing_id;
    else
      select stock_qty into v_remaining from public.listing_location_stock
        where listing_id = p_listing_id and location_id = p_location_id;
    end if;
    return v_remaining;
  end if;

  select exists(select 1 from public.listing_location_stock
    where listing_id = p_listing_id) into v_branch;
  if v_branch then
    select * into v_listing from public.vendor_listings where id = p_listing_id for share;
  else
    select * into v_listing from public.vendor_listings where id = p_listing_id for update;
  end if;
  if not found or v_listing.stock_mode <> 'tracked'
     or v_listing.product_class = 'E' or v_listing.fulfilment_mode = 'made_to_order'
     or v_branch <> (p_location_id is not null)
     or v_branch <> exists(select 1 from public.listing_location_stock where listing_id = p_listing_id)
  then
    update public.stock_claim_identities set state = 'rejected'
      where listing_id = p_listing_id and checkout_group_id = p_checkout_group_id;
    return null;
  end if;
  -- Match adjustment ordering: listing metadata, branch metadata, stock row,
  -- then the existing AFTER shared cart barrier. No exclusive cart wait.
  if v_branch then
    perform 1 from public.vendor_locations where id = p_location_id
      and vendor_id = v_listing.vendor_id and status = 'active' for share;
    if found then
      update public.listing_location_stock set stock_qty = stock_qty - p_qty
        where listing_id = p_listing_id and location_id = p_location_id and stock_qty >= p_qty
        returning stock_qty into v_remaining;
    end if;
  else
    update public.vendor_listings set stock_qty = stock_qty - p_qty
      where id = p_listing_id and stock_qty >= p_qty returning stock_qty into v_remaining;
  end if;
  if v_remaining is null then
    update public.stock_claim_identities set state = 'rejected'
      where listing_id = p_listing_id and checkout_group_id = p_checkout_group_id;
    return null;
  end if;
  insert into public.stock_reservations(listing_id, checkout_group_id, qty, expires_at, location_id)
    values(p_listing_id, p_checkout_group_id, p_qty, p_expires_at, p_location_id);
  update public.stock_claim_identities set state = 'claimed', remaining_stock_qty = v_remaining
    where listing_id = p_listing_id and checkout_group_id = p_checkout_group_id;
  return v_remaining;
end;
$$;
revoke all on function public.claim_stock_reservation(uuid,uuid,integer,uuid,timestamptz)
  from public, anon, authenticated;
grant execute on function public.claim_stock_reservation(uuid,uuid,integer,uuid,timestamptz) to service_role;
revoke all on function public.close_stock_claim_identity() from public, anon, authenticated;

commit;
