-- Allocated in #716/5914277388. Draft only: no shared application authorized.
-- Quantity is AVAILABLE sale steps, already net of stock_reservations.
-- No reservation row is changed, counted-total API or branch conversion added.
begin;

create table public.vendor_stock_operations (
  vendor_id uuid not null references public.vendors(id),
  operation_id uuid not null,
  actor_id uuid not null,
  input jsonb not null,
  outcome jsonb,
  created_at timestamptz not null default now(),
  primary key (vendor_id, operation_id)
);
alter table public.vendor_stock_operations enable row level security;
alter table public.vendor_stock_operations force row level security;
revoke all on public.vendor_stock_operations from public, anon, authenticated, service_role;
comment on table public.vendor_stock_operations is
  'Immutable vendor adjustment input/outcome, including original available before/after and reason. Access only through service RPC; not a reservation ledger.';

create function public.adjust_vendor_stock(
  p_actor_id uuid, p_vendor_id uuid, p_listing_id uuid, p_location_id uuid,
  p_operation_id uuid, p_delta integer, p_reason text,
  p_sale_unit text, p_unit_step_milli integer
) returns jsonb
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_input jsonb;
  v_operation public.vendor_stock_operations%rowtype;
  v_listing public.vendor_listings%rowtype;
  v_branch boolean;
  v_old integer;
  v_new integer;
  v_result jsonb;
begin
  -- Authentication comes from the protected API; this RPC is service-only.
  perform 1 from public.vendors
    where id = p_vendor_id and owner_user_id = p_actor_id for share;
  if not found then
    return jsonb_build_object('ok', false, 'status', 403, 'code', 'stock.forbidden');
  end if;
  if p_operation_id is null or p_listing_id is null or p_delta is null
     or p_delta = 0 or p_delta not between -999999 and 999999
     or p_reason is null or length(btrim(p_reason)) not between 1 and 240
     or p_sale_unit is null or p_unit_step_milli is null or p_unit_step_milli <= 0 then
    return jsonb_build_object('ok', false, 'status', 422, 'code', 'stock.invalid');
  end if;
  v_input := jsonb_build_object('actor_id', p_actor_id, 'vendor_id', p_vendor_id,
    'listing_id', p_listing_id, 'location_id', p_location_id, 'kind', 'delta',
    'delta', p_delta, 'reason', p_reason, 'sale_unit', p_sale_unit,
    'unit_step_milli', p_unit_step_milli);
  insert into public.vendor_stock_operations(vendor_id, operation_id, actor_id, input)
    values (p_vendor_id, p_operation_id, p_actor_id, v_input)
    on conflict (vendor_id, operation_id) do nothing;
  select * into strict v_operation from public.vendor_stock_operations
    where vendor_id = p_vendor_id and operation_id = p_operation_id for update;
  if v_operation.input <> v_input then
    return jsonb_build_object('ok', false, 'status', 409, 'code', 'stock.operation_conflict');
  end if;
  if v_operation.outcome is not null then return v_operation.outcome; end if;

  begin
    select exists(select 1 from public.listing_location_stock
      where listing_id = p_listing_id) into v_branch;
    -- Match the existing writer ordering: row locks, then the existing AFTER
    -- cart_write_barrier shared scope lock. Never acquire an exclusive cart lock.
    -- Branch writers share the listing metadata lock; different branches proceed.
    if v_branch then
      select * into v_listing from public.vendor_listings
        where id = p_listing_id and vendor_id = p_vendor_id for share;
    else
      select * into v_listing from public.vendor_listings
        where id = p_listing_id and vendor_id = p_vendor_id for update;
    end if;
    if not found then raise sqlstate 'PT403' using message = 'stock.forbidden'; end if;
    if v_listing.stock_mode <> 'tracked' or v_listing.product_class = 'E'
       or v_listing.fulfilment_mode = 'made_to_order'
       or v_listing.status not in ('draft', 'active', 'paused') then
      raise sqlstate 'PT409' using message = 'stock.not_adjustable';
    end if;
    if v_listing.sale_unit <> p_sale_unit or v_listing.unit_step_milli <> p_unit_step_milli then
      raise sqlstate 'PT409' using message = 'stock.units_changed';
    end if;
    -- Fail if topology changed since selection; conversion/provisioning is not
    -- authorized by this delta operation, and cannot silently target the pool.
    if v_branch <> exists(select 1 from public.listing_location_stock
                           where listing_id = p_listing_id) then
      raise sqlstate 'PT409' using message = 'stock.location_changed';
    end if;
    if v_branch then
      if p_location_id is null then
        raise sqlstate 'PT409' using message = 'stock.location_required';
      end if;
      perform 1 from public.vendor_locations where id = p_location_id
        and vendor_id = p_vendor_id and status = 'active' for share;
      if not found then raise sqlstate 'PT409' using message = 'stock.invalid_location'; end if;
      select stock_qty into v_old from public.listing_location_stock
        where listing_id = p_listing_id and location_id = p_location_id for update;
      if not found then raise sqlstate 'PT409' using message = 'stock.invalid_location'; end if;
    else
      if p_location_id is not null then
        raise sqlstate 'PT409' using message = 'stock.invalid_location';
      end if;
      v_old := v_listing.stock_qty;
    end if;
    if v_old is null or v_old::bigint + p_delta < 0
       or v_old::bigint + p_delta > 2147483647 then
      raise sqlstate 'PT409' using message = 'stock.insufficient';
    end if;
    if v_branch then
      update public.listing_location_stock set stock_qty = stock_qty + p_delta
        where listing_id = p_listing_id and location_id = p_location_id
        returning stock_qty into v_new;
    else
      update public.vendor_listings set stock_qty = stock_qty + p_delta
        where id = p_listing_id returning stock_qty into v_new;
    end if;
    v_result := jsonb_build_object('ok', true, 'operation_id', p_operation_id,
      'listing_id', p_listing_id, 'location_id', p_location_id, 'kind', 'delta',
      'delta', p_delta, 'old_qty', v_old, 'new_qty', v_new, 'reason', p_reason,
      'sale_unit', p_sale_unit, 'unit_step_milli', p_unit_step_milli);
  exception
    when sqlstate 'PT403' then
      v_result := jsonb_build_object('ok', false, 'status', 403, 'code', sqlerrm);
    when sqlstate 'PT409' then
      v_result := jsonb_build_object('ok', false, 'status', 409, 'code', sqlerrm);
  end;
  -- Business rejection is durable too. Unexpected SQL failures abort the whole
  -- transaction, including the operation claim; no false success is persisted.
  v_result := v_result || jsonb_build_object('operation_id', p_operation_id);
  update public.vendor_stock_operations set outcome = v_result
    where vendor_id = p_vendor_id and operation_id = p_operation_id;
  return v_result;
end;
$$;
revoke all on function public.adjust_vendor_stock(uuid,uuid,uuid,uuid,uuid,integer,text,text,integer)
  from public, anon, authenticated;
grant execute on function public.adjust_vendor_stock(uuid,uuid,uuid,uuid,uuid,integer,text,text,integer)
  to service_role;

-- Authenticated direct table updates must not bypass the protected API.
-- Service claim/release/sweep remain unchanged and retain their existing grants.
create function public.guard_vendor_inventory_edit() returns trigger
language plpgsql security invoker set search_path = pg_catalog, public
as $$
begin
  if tg_op = 'DELETE' then
    if current_user in ('authenticated', 'anon') then
      raise sqlstate 'PT403' using message = 'stock.authority_required';
    end if;
    return old;
  end if;
  if (new.sale_unit, new.unit_step_milli, new.stock_mode, new.fulfilment_mode)
      is distinct from (old.sale_unit, old.unit_step_milli, old.stock_mode, old.fulfilment_mode) then
    raise sqlstate 'PT409' using message = 'stock.units_immutable';
  end if;
  if current_user in ('authenticated', 'anon') and new.stock_qty is distinct from old.stock_qty then
    raise sqlstate 'PT403' using message = 'stock.authority_required';
  end if;
  return new;
end;
$$;
create trigger vendor_inventory_edit_guard before update or delete on public.vendor_listings
  for each row execute function public.guard_vendor_inventory_edit();

-- Owner CRUD on vendor_locations otherwise allows a cascade to erase branch
-- stock and SET NULL a reservation's location, misrouting its later release.
-- Closing a branch remains supported; moving/deleting stocked topology does not.
create function public.guard_stock_location_identity() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
begin
  if tg_op = 'UPDATE' then
    if (new.id, new.vendor_id) is not distinct from (old.id, old.vendor_id) then
      return new;
    end if;
  end if;
  if exists(select 1 from public.listing_location_stock where location_id = old.id)
     or exists(select 1 from public.stock_reservations where location_id = old.id) then
    raise sqlstate 'PT409' using message = 'stock.location_in_use';
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end;
$$;
create trigger stock_location_identity_guard before update or delete on public.vendor_locations
  for each row execute function public.guard_stock_location_identity();

commit;
