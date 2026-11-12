-- Carry #762 listing variants through #718/#756's atomic cart paths.
--
-- 1. apply_login_cart_merge (same signature; body from 20260923234129):
--    * line snapshots add `listing_variant_id` only when a line has one, so
--      variant-free carts compare exactly as before;
--    * quantity conservation is keyed by (listing, variant): a guest line for
--      another variant of a listing the account cart holds must be removed
--      explicitly (audited in the receipt), never folded into the other variant;
--    * still exactly one proposed line per listing; merged lines keep their
--      variant (insert and on-conflict update).
-- 2. apply_cart_add_idempotent_v2 = the 20261009110000 keyed-add body plus
--    p_listing_variant_id. The request body must name the same variant; an
--    existing line with another variant returns 'stale' so the API re-reads and
--    refuses with cart.variant_conflict. A new name (not an overload) keeps
--    PostgREST resolution unambiguous and the old API working during deploy;
--    the v1 function is left in place for rollback.
--
-- Additive. Down: re-apply apply_login_cart_merge from
-- 20260923234129_cart_merge_product_authority.sql and
-- drop function public.apply_cart_add_idempotent_v2(uuid, uuid, text, text, jsonb, uuid, integer, integer, uuid, bigint, boolean, uuid, uuid);

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
  ) || case when ci.listing_variant_id is null then '{}'::jsonb
       else jsonb_build_object('listing_variant_id', ci.listing_variant_id::text) end
  order by ci.id), '[]'::jsonb)
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
  ) || case when ci.listing_variant_id is null then '{}'::jsonb
       else jsonb_build_object('listing_variant_id', ci.listing_variant_id::text) end
  order by ci.id), '[]'::jsonb)
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
      select listing_id, coalesce(listing_variant_id::text, '') variant, sum(qty)::bigint qty
      from jsonb_to_recordset(p_expected_user_items || p_expected_guest_items)
        item(listing_id uuid, listing_variant_id uuid, qty integer)
      group by 1, 2
    ), proposed as (
      select listing_id, coalesce(listing_variant_id::text, '') variant,
             sum(qty)::bigint qty, count(*)::bigint row_count
      from jsonb_to_recordset(p_merged_items)
        item(listing_id uuid, listing_variant_id uuid, qty integer)
      group by 1, 2
    ), removed as (
      select listing_id, coalesce(listing_variant_id::text, '') variant,
             sum(qty)::bigint qty, count(*)::bigint row_count
      from jsonb_to_recordset(p_removed_items)
        item(listing_id uuid, listing_variant_id uuid, qty integer)
      group by 1, 2
    )
    select 1
    from source
    full join proposed using (listing_id, variant)
    full join removed using (listing_id, variant)
    where source.qty is distinct from coalesce(proposed.qty, 0) + coalesce(removed.qty, 0)
       or coalesce(proposed.row_count, 1) <> 1
       or coalesce(removed.row_count, 1) <> 1
       or (proposed.listing_id is not null and removed.listing_id is not null)
  ) or exists (
    -- One cart line per listing: two variants of a listing never merge into one.
    select 1
    from jsonb_to_recordset(p_merged_items) item(listing_id uuid)
    group by item.listing_id
    having count(*) > 1
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
    rfq_thread_id,
    listing_variant_id
  )
  select
    p_user_cart_id,
    proposal.listing_id,
    proposal.qty,
    proposal.unit_price_ngwee,
    proposal.wholesale,
    proposal.pickup_location_id,
    proposal.rfq_thread_id,
    proposal.listing_variant_id
  from jsonb_to_recordset(p_merged_items) as proposal(
    listing_id uuid,
    qty integer,
    unit_price_ngwee bigint,
    wholesale boolean,
    pickup_location_id uuid,
    rfq_thread_id uuid,
    listing_variant_id uuid
  )
  on conflict (cart_id, listing_id) do update set
    qty = excluded.qty,
    unit_price_ngwee = excluded.unit_price_ngwee,
    wholesale = excluded.wholesale,
    pickup_location_id = excluded.pickup_location_id,
    rfq_thread_id = excluded.rfq_thread_id,
    listing_variant_id = excluded.listing_variant_id;

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

create function public.apply_cart_add_idempotent_v2(
  p_cart_id uuid,
  p_user_id uuid,
  p_guest_token text,
  p_key text,
  p_body jsonb,
  p_listing_id uuid,
  p_qty integer,
  p_expected_qty integer,
  p_expected_location_id uuid,
  p_unit_price_ngwee bigint,
  p_wholesale boolean,
  p_location_id uuid,
  p_listing_variant_id uuid
)
returns text
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_cart public.carts%rowtype;
  v_body jsonb;
  v_qty integer;
  v_location_id uuid;
  v_variant_id uuid;
begin
  if (p_user_id is null) = (p_guest_token is null) then
    raise exception 'cart.owner_invalid' using errcode = '42501';
  end if;
  if p_key is null or p_key !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' then
    raise exception 'cart.idempotency_key_invalid' using errcode = '22023';
  end if;
  if p_body is null or jsonb_typeof(p_body) <> 'object'
    or p_body->>'listing_id' is distinct from p_listing_id::text
    or p_body->>'qty' is distinct from p_qty::text
    or p_body->>'listing_variant_id' is distinct from p_listing_variant_id::text
    or p_qty < 1 or p_unit_price_ngwee < 1 then
    raise exception 'cart.add_parameters_invalid' using errcode = '22023';
  end if;

  -- Serialize keyed adds for this cart, including distinct keys. The API
  -- revalidates after a stale line snapshot. This lock does not serialize
  -- inventory across carts or writes from callers using the unkeyed path.
  select * into v_cart from public.carts where id = p_cart_id for update;
  if not found or v_cart.status <> 'active'
    or (p_user_id is not null and v_cart.user_id is distinct from p_user_id)
    or (p_guest_token is not null and
        (v_cart.user_id is not null or v_cart.guest_token is distinct from p_guest_token)) then
    raise exception 'cart.owner_mismatch' using errcode = '42501';
  end if;

  select request_body into v_body
  from public.cart_add_requests
  where cart_id = p_cart_id and idempotency_key = p_key;
  if found then
    if v_body <> p_body then
      raise exception 'cart.idempotency_mismatch' using errcode = 'P0001';
    end if;
    return 'replayed';
  end if;

  select qty, pickup_location_id, listing_variant_id into v_qty, v_location_id, v_variant_id
  from public.cart_items
  where cart_id = p_cart_id and listing_id = p_listing_id
  for update;
  if found then
    if v_qty is distinct from p_expected_qty
      or v_location_id is distinct from p_expected_location_id
      -- One line per listing: a different variant is never incremented into it.
      or v_variant_id is distinct from p_listing_variant_id then
      return 'stale';
    end if;
    update public.cart_items
    set qty = v_qty + p_qty,
        unit_price_ngwee = p_unit_price_ngwee,
        wholesale = p_wholesale,
        pickup_location_id = p_location_id
    where cart_id = p_cart_id and listing_id = p_listing_id;
  else
    if p_expected_qty is not null or p_expected_location_id is not null then
      return 'stale';
    end if;
    insert into public.cart_items (
      cart_id, listing_id, qty, unit_price_ngwee, wholesale, pickup_location_id,
      listing_variant_id
    ) values (
      p_cart_id, p_listing_id, p_qty, p_unit_price_ngwee, p_wholesale, p_location_id,
      p_listing_variant_id
    );
  end if;

  insert into public.cart_add_requests (cart_id, idempotency_key, request_body)
  values (p_cart_id, p_key, p_body);
  return 'applied';
end;
$$;

revoke all on function public.apply_cart_add_idempotent_v2(
  uuid, uuid, text, text, jsonb, uuid, integer, integer, uuid, bigint, boolean, uuid, uuid
) from public, anon, authenticated;
grant execute on function public.apply_cart_add_idempotent_v2(
  uuid, uuid, text, text, jsonb, uuid, integer, integer, uuid, bigint, boolean, uuid, uuid
) to service_role;
