-- Extend the existing per-authority protocol without changing buyer consent.
-- AFTER ROW matches existing writers: merge always uses try/NOWAIT locks.
create or replace function public.product_cart_write_barrier()
returns trigger language plpgsql security invoker
set search_path = pg_catalog, public
as $$
declare
  v_old uuid;
  v_new uuid;
  v_id uuid;
begin
  if tg_op <> 'INSERT' then v_old := old.id; end if;
  if tg_op <> 'DELETE' then v_new := new.id; end if;
  for v_id in
    select distinct value from unnest(array[v_old, v_new]) value
    where value is not null order by value
  loop
    perform pg_advisory_xact_lock_shared(public.cart_scope_key('product', v_id));
  end loop;
  return null;
end;
$$;

create trigger products_cart_write_barrier_trg
  after insert or update or delete on public.products
  for each row execute function public.product_cart_write_barrier();

revoke all on function public.product_cart_write_barrier() from public, anon, authenticated;

create or replace function public.apply_login_cart_merge(
  p_user_id uuid,
  p_user_cart_id uuid,
  p_guest_cart_id uuid,
  p_guest_token text,
  p_expected_user_items jsonb,
  p_expected_guest_items jsonb,
  p_expected_authority jsonb,
  p_merged_items jsonb,
  p_removed_items jsonb,
  p_resolution jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_user_cart public.carts%rowtype;
  v_guest_cart public.carts%rowtype;
  v_receipt public.cart_merge_receipts%rowtype;
  v_actual_user_items jsonb;
  v_actual_guest_items jsonb;
  v_actual_authority jsonb;
  v_listing_ids uuid[];
  v_rfq_thread_ids uuid[];
  v_id uuid;
begin
  -- Hosted PostgREST connects as authenticator and SET LOCAL ROLEs from the
  -- verified JWT. current_user is therefore the reliable effective role;
  -- session_user and the removed request.jwt.claim.role legacy GUC are not.
  if current_user is distinct from 'service_role' then
    raise insufficient_privilege using message = 'apply_login_cart_merge requires service role';
  end if;

  if p_user_id is null
     or p_user_cart_id is null
     or p_guest_cart_id is null
     or nullif(btrim(p_guest_token), '') is null then
    raise invalid_parameter_value using message = 'cart merge identity is required';
  end if;

  if jsonb_typeof(p_expected_user_items) is distinct from 'array'
     or jsonb_typeof(p_expected_guest_items) is distinct from 'array'
     or jsonb_typeof(p_expected_authority) is distinct from 'object'
     or jsonb_typeof(p_merged_items) is distinct from 'array'
     or jsonb_typeof(p_removed_items) is distinct from 'array'
     or jsonb_typeof(p_resolution) is distinct from 'object' then
    raise invalid_parameter_value using message = 'cart merge payload has an invalid shape';
  end if;

  -- All advisory attempts are non-waiting: an ordinary writer can already
  -- hold a row lock when its AFTER ROW trigger reaches the shared scope lock.
  -- Returning stale releases all acquired locks at the end of this RPC.
  if not pg_try_advisory_xact_lock(public.cart_scope_key('cart', least(p_user_cart_id, p_guest_cart_id))) then
    return jsonb_build_object('outcome', 'stale_snapshot');
  end if;
  if not pg_try_advisory_xact_lock(public.cart_scope_key('cart', greatest(p_user_cart_id, p_guest_cart_id))) then
    return jsonb_build_object('outcome', 'stale_snapshot');
  end if;

  perform 1
  from public.carts c
  where c.id in (p_user_cart_id, p_guest_cart_id)
  order by c.id
  for update nowait;

  select c.* into v_user_cart
  from public.carts c
  where c.id = p_user_cart_id;

  if not found
     or v_user_cart.user_id is distinct from p_user_id
     or v_user_cart.status is distinct from 'active' then
    raise insufficient_privilege using message = 'account cart ownership mismatch';
  end if;

  select * into v_receipt
  from public.cart_merge_receipts r
  where r.guest_cart_id = p_guest_cart_id;

  if found then
    if v_receipt.user_id is distinct from p_user_id
       or v_receipt.user_cart_id is distinct from p_user_cart_id then
      raise sqlstate 'PT409' using message = 'guest cart was already merged into another account';
    end if;
    return jsonb_build_object('outcome', 'already_converted');
  end if;

  select c.* into v_guest_cart
  from public.carts c
  where c.id = p_guest_cart_id;

  if not found
     or v_guest_cart.user_id is not null
     or v_guest_cart.guest_token is distinct from p_guest_token
     or v_guest_cart.status is distinct from 'active' then
    raise insufficient_privilege using message = 'guest cart identity mismatch';
  end if;

  perform 1
  from public.cart_items ci
  where ci.cart_id in (p_user_cart_id, p_guest_cart_id)
  order by ci.cart_id, ci.id
  for update nowait;

  select coalesce(jsonb_agg(jsonb_build_object(
    'id', ci.id::text,
    'listing_id', ci.listing_id::text,
    'qty', ci.qty,
    'unit_price_ngwee', ci.unit_price_ngwee,
    'wholesale', ci.wholesale,
    'pickup_location_id', case when ci.pickup_location_id is null then null else ci.pickup_location_id::text end,
    'rfq_thread_id', case when ci.rfq_thread_id is null then null else ci.rfq_thread_id::text end
  ) order by ci.id), '[]'::jsonb)
  into v_actual_user_items
  from public.cart_items ci
  where ci.cart_id = p_user_cart_id;

  select coalesce(jsonb_agg(jsonb_build_object(
    'id', ci.id::text,
    'listing_id', ci.listing_id::text,
    'qty', ci.qty,
    'unit_price_ngwee', ci.unit_price_ngwee,
    'wholesale', ci.wholesale,
    'pickup_location_id', case when ci.pickup_location_id is null then null else ci.pickup_location_id::text end,
    'rfq_thread_id', case when ci.rfq_thread_id is null then null else ci.rfq_thread_id::text end
  ) order by ci.id), '[]'::jsonb)
  into v_actual_guest_items
  from public.cart_items ci
  where ci.cart_id = p_guest_cart_id;

  if v_actual_user_items is distinct from p_expected_user_items
     or v_actual_guest_items is distinct from p_expected_guest_items then
    return jsonb_build_object('outcome', 'stale_snapshot');
  end if;

  select coalesce(array_agg(distinct value::uuid order by value::uuid), array[]::uuid[])
  into v_listing_ids
  from (
    select item ->> 'listing_id' as value
    from jsonb_array_elements(p_expected_user_items || p_expected_guest_items) item
  ) source_ids
  where nullif(value, '') is not null;

  select coalesce(array_agg(distinct value::uuid order by value::uuid), array[]::uuid[])
  into v_rfq_thread_ids
  from (
    select item ->> 'rfq_thread_id' as value
    from jsonb_array_elements(p_expected_user_items || p_expected_guest_items) item
  ) source_ids
  where nullif(value, '') is not null;

  -- Acquire authority scopes in a deterministic order before the snapshot.
  -- A writer that modified a row but has not reached its AFTER trigger can
  -- finish only after this transaction, giving a valid merge-before-write order.
  for v_id in select unnest(v_listing_ids) order by 1 loop
    if not pg_try_advisory_xact_lock(public.cart_scope_key('listing', v_id)) then
      return jsonb_build_object('outcome', 'stale_authority');
    end if;
  end loop;
  -- Listing scopes freeze product membership, including concurrent relinks.
  -- Product AFTER writers may already hold row locks: never wait here.
  for v_id in
    select distinct vl.product_id from public.vendor_listings vl
    where vl.id = any(v_listing_ids) and vl.product_id is not null
    order by vl.product_id
  loop
    if not pg_try_advisory_xact_lock(public.cart_scope_key('product', v_id)) then
      return jsonb_build_object('outcome', 'stale_authority');
    end if;
  end loop;
  for v_id in select unnest(v_rfq_thread_ids) order by 1 loop
    if not pg_try_advisory_xact_lock(public.cart_scope_key('rfq', v_id)) then
      return jsonb_build_object('outcome', 'stale_authority');
    end if;
  end loop;
  if not pg_try_advisory_xact_lock(public.cart_scope_key('buyer', p_user_id)) then
    return jsonb_build_object('outcome', 'stale_authority');
  end if;

  select public.cart_merge_authority(p_user_id, v_listing_ids, v_rfq_thread_ids)
  into v_actual_authority;

  if v_actual_authority is distinct from p_expected_authority then
    return jsonb_build_object('outcome', 'stale_authority');
  end if;

  if exists (
    select 1
    from jsonb_to_recordset(p_merged_items) proposal(listing_id uuid, pickup_location_id uuid)
    where (
      proposal.pickup_location_id is null
      and exists (
        select 1
        from jsonb_to_recordset(p_expected_user_items || p_expected_guest_items)
          source_line(listing_id uuid, pickup_location_id uuid)
        where source_line.listing_id = proposal.listing_id
          and source_line.pickup_location_id is not null
      )
    ) or (
      proposal.pickup_location_id is not null
      and not exists (
        select 1
        from jsonb_to_recordset(p_expected_user_items || p_expected_guest_items)
          source_line(listing_id uuid, pickup_location_id uuid)
        where source_line.listing_id = proposal.listing_id
          and source_line.pickup_location_id = proposal.pickup_location_id
      )
    ) or (
      1 < (
        select count(distinct source_line.pickup_location_id)
        from jsonb_to_recordset(p_expected_user_items || p_expected_guest_items)
          source_line(listing_id uuid, pickup_location_id uuid)
        where source_line.listing_id = proposal.listing_id
          and source_line.pickup_location_id is not null
      )
      and p_resolution -> 'pickup_location_choices' ->> proposal.listing_id::text
        is distinct from proposal.pickup_location_id::text
    )
  ) then
    raise sqlstate 'PT409' using message = 'pickup location must be preserved or explicitly resolved';
  end if;

  -- A trusted API proposal still has to conserve every source quantity. Any
  -- omitted quantity must appear in the explicit, audited removal set.
  if exists (
    with source as (
      select listing_id, sum(qty)::bigint qty
      from jsonb_to_recordset(p_expected_user_items || p_expected_guest_items)
        item(listing_id uuid, qty integer)
      group by listing_id
    ), proposed as (
      select listing_id, sum(qty)::bigint qty, count(*)::bigint row_count
      from jsonb_to_recordset(p_merged_items) item(listing_id uuid, qty integer)
      group by listing_id
    ), removed as (
      select listing_id, sum(qty)::bigint qty, count(*)::bigint row_count
      from jsonb_to_recordset(p_removed_items) item(listing_id uuid, qty integer)
      group by listing_id
    )
    select 1
    from source
    full join proposed using (listing_id)
    full join removed using (listing_id)
    where source.qty is distinct from coalesce(proposed.qty, 0) + coalesce(removed.qty, 0)
       or coalesce(proposed.row_count, 1) <> 1
       or coalesce(removed.row_count, 1) <> 1
       or (proposed.listing_id is not null and removed.listing_id is not null)
  ) then
    raise sqlstate 'PT409' using message = 'cart merge must conserve or explicitly remove every source quantity';
  end if;

  insert into public.cart_items (
    cart_id,
    listing_id,
    qty,
    unit_price_ngwee,
    wholesale,
    pickup_location_id,
    rfq_thread_id
  )
  select
    p_user_cart_id,
    proposal.listing_id,
    proposal.qty,
    proposal.unit_price_ngwee,
    proposal.wholesale,
    proposal.pickup_location_id,
    proposal.rfq_thread_id
  from jsonb_to_recordset(p_merged_items) as proposal(
    listing_id uuid,
    qty integer,
    unit_price_ngwee bigint,
    wholesale boolean,
    pickup_location_id uuid,
    rfq_thread_id uuid
  )
  on conflict (cart_id, listing_id) do update set
    qty = excluded.qty,
    unit_price_ngwee = excluded.unit_price_ngwee,
    wholesale = excluded.wholesale,
    pickup_location_id = excluded.pickup_location_id,
    rfq_thread_id = excluded.rfq_thread_id;

  delete from public.cart_items ci
  where ci.cart_id = p_user_cart_id
    and not exists (
      select 1
      from jsonb_to_recordset(p_merged_items) proposal(listing_id uuid)
      where proposal.listing_id = ci.listing_id
    );

  update public.carts c
  set status = 'converted'
  where c.id = p_guest_cart_id and c.status = 'active';

  if not found then
    raise serialization_failure using message = 'guest cart changed during merge';
  end if;

  insert into public.cart_merge_receipts (
    guest_cart_id,
    user_id,
    user_cart_id,
    resolution,
    source_items
  ) values (
    p_guest_cart_id,
    p_user_id,
    p_user_cart_id,
    p_resolution,
    p_expected_user_items || p_expected_guest_items
  );

  return jsonb_build_object('outcome', 'applied');
end;
$$;
