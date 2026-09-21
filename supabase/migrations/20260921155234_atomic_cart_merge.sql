-- Customer login cart merge: one database transaction, safe across API workers.
--
-- Python remains the authority for authentication, signed guest-cookie
-- verification, listing availability, price/MOQ/wholesale derivation, and RFQ
-- authority. This migration provides only the concurrency boundary around the
-- already-derived proposal.

-- Every ordinary cart-line mutation takes a row lock on its parent cart. The
-- merge RPC takes the same lock before checking its optimistic snapshot, so an
-- insert/update/delete cannot become a phantom between snapshot validation and
-- replacement. This is per cart; it is not a cart_items table lock.
create or replace function public.lock_cart_for_item_mutation()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_cart_id uuid;
  v_cart_status text;
begin
  if tg_op = 'INSERT' then
    select status into v_cart_status
    from public.carts
    where id = new.cart_id
    for update;
    if not found then
      raise exception 'cart parent is not accessible'
        using errcode = '42501';
    end if;
    if v_cart_status is distinct from 'active' then
      raise exception 'cart changed while item mutation was waiting'
        using errcode = '40001';
    end if;
    return new;
  end if;

  if tg_op = 'DELETE' then
    perform 1 from public.carts where id = old.cart_id for update;
    return old;
  end if;

  -- Moving a line between carts is not an API operation today, but lock both
  -- parents in UUID order so a future service-role path cannot introduce a
  -- lock-order inversion.
  for v_cart_id in
    select cart_id
    from (values (old.cart_id), (new.cart_id)) as parent(cart_id)
    group by cart_id
    order by cart_id
  loop
    select status into v_cart_status
    from public.carts
    where id = v_cart_id
    for update;
    if not found then
      raise exception 'cart parent is not accessible'
        using errcode = '42501';
    end if;
    if v_cart_status is distinct from 'active' then
      raise exception 'cart changed while item mutation was waiting'
        using errcode = '40001';
    end if;
  end loop;
  return new;
end;
$$;

drop trigger if exists cart_items_lock_parent_cart_trg on public.cart_items;
create trigger cart_items_lock_parent_cart_trg
  before insert or update or delete on public.cart_items
  for each row
  execute function public.lock_cart_for_item_mutation();

comment on function public.lock_cart_for_item_mutation() is
  'Serializes cart_items writes with atomic login merge by locking only the affected parent cart row(s).';

revoke all on function public.lock_cart_for_item_mutation() from public;
revoke execute on function public.lock_cart_for_item_mutation()
  from public, anon, authenticated;
grant execute on function public.lock_cart_for_item_mutation()
  to postgres, service_role;

create or replace function public.apply_login_cart_merge(
  p_user_id uuid,
  p_user_cart_id uuid,
  p_guest_cart_id uuid,
  p_guest_token text,
  p_expected_user_items jsonb,
  p_expected_guest_items jsonb,
  p_merged_items jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_user_cart public.carts%rowtype;
  v_guest_cart public.carts%rowtype;
  v_actual_user_items jsonb;
  v_actual_guest_items jsonb;
begin
  -- Defence in depth in addition to EXECUTE revocation. The browser roles
  -- cannot invoke this function and a caller cannot self-assert service_role.
  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '')
       is distinct from 'service_role' then
    raise exception 'apply_login_cart_merge requires service role'
      using errcode = '42501';
  end if;

  if p_user_id is null
     or p_user_cart_id is null
     or p_guest_cart_id is null
     or nullif(btrim(p_guest_token), '') is null then
    raise exception 'cart merge identity is required'
      using errcode = '22023';
  end if;

  if jsonb_typeof(p_expected_user_items) is distinct from 'array'
     or jsonb_typeof(p_expected_guest_items) is distinct from 'array'
     or jsonb_typeof(p_merged_items) is distinct from 'array' then
    raise exception 'cart merge snapshots and proposal must be arrays'
      using errcode = '22023';
  end if;

  -- Deterministic cart-row lock order. The cart_items trigger makes every
  -- ordinary line mutation contend on the same parent row lock.
  perform 1
  from public.carts c
  where c.id in (p_user_cart_id, p_guest_cart_id)
  order by c.id
  for update;

  select c.*
  into v_user_cart
  from public.carts c
  where c.id = p_user_cart_id;

  if not found
     or v_user_cart.user_id is distinct from p_user_id
     or v_user_cart.status is distinct from 'active' then
    raise exception 'account cart ownership mismatch'
      using errcode = '42501';
  end if;

  select c.*
  into v_guest_cart
  from public.carts c
  where c.id = p_guest_cart_id;

  if not found
     or v_guest_cart.user_id is not null
     or v_guest_cart.guest_token is distinct from p_guest_token
     or v_guest_cart.status not in ('active', 'converted') then
    raise exception 'guest cart identity mismatch'
      using errcode = '42501';
  end if;

  -- A concurrent request that completed this exact guest conversion wins.
  -- Never apply the second request's stale proposal over the completed cart.
  if v_guest_cart.status = 'converted' then
    return jsonb_build_object('outcome', 'already_converted');
  end if;

  perform 1
  from public.cart_items ci
  where ci.cart_id in (p_user_cart_id, p_guest_cart_id)
  order by ci.cart_id, ci.id
  for update;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'id', ci.id::text,
        'listing_id', ci.listing_id::text,
        'qty', ci.qty,
        'unit_price_ngwee', ci.unit_price_ngwee,
        'wholesale', ci.wholesale,
        'pickup_location_id',
          case when ci.pickup_location_id is null then null else ci.pickup_location_id::text end,
        'rfq_thread_id',
          case when ci.rfq_thread_id is null then null else ci.rfq_thread_id::text end
      ) order by ci.id
    ),
    '[]'::jsonb
  )
  into v_actual_user_items
  from public.cart_items ci
  where ci.cart_id = p_user_cart_id;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'id', ci.id::text,
        'listing_id', ci.listing_id::text,
        'qty', ci.qty,
        'unit_price_ngwee', ci.unit_price_ngwee,
        'wholesale', ci.wholesale,
        'pickup_location_id',
          case when ci.pickup_location_id is null then null else ci.pickup_location_id::text end,
        'rfq_thread_id',
          case when ci.rfq_thread_id is null then null else ci.rfq_thread_id::text end
      ) order by ci.id
    ),
    '[]'::jsonb
  )
  into v_actual_guest_items
  from public.cart_items ci
  where ci.cart_id = p_guest_cart_id;

  if v_actual_user_items is distinct from p_expected_user_items
     or v_actual_guest_items is distinct from p_expected_guest_items then
    return jsonb_build_object('outcome', 'stale_snapshot');
  end if;

  delete from public.cart_items ci where ci.cart_id = p_user_cart_id;

  insert into public.cart_items (
    cart_id,
    listing_id,
    qty,
    unit_price_ngwee,
    wholesale,
    rfq_thread_id
  )
  select
    p_user_cart_id,
    proposal.listing_id,
    proposal.qty,
    proposal.unit_price_ngwee,
    proposal.wholesale,
    proposal.rfq_thread_id
  from jsonb_to_recordset(p_merged_items) as proposal(
    listing_id uuid,
    qty integer,
    unit_price_ngwee bigint,
    wholesale boolean,
    rfq_thread_id uuid
  );

  update public.carts c
  set status = 'converted'
  where c.id = p_guest_cart_id
    and c.status = 'active';

  if not found then
    raise exception 'guest cart changed during merge'
      using errcode = '40001';
  end if;

  return jsonb_build_object('outcome', 'applied');
end;
$$;

comment on function public.apply_login_cart_merge(uuid, uuid, uuid, text, jsonb, jsonb, jsonb) is
  'Atomically validates cart ownership and snapshots, applies a trusted API-derived merge proposal, and converts the signed guest cart. service_role only.';

revoke all on function public.apply_login_cart_merge(uuid, uuid, uuid, text, jsonb, jsonb, jsonb)
  from public;
revoke execute on function public.apply_login_cart_merge(uuid, uuid, uuid, text, jsonb, jsonb, jsonb)
  from public, anon, authenticated;
grant execute on function public.apply_login_cart_merge(uuid, uuid, uuid, text, jsonb, jsonb, jsonb)
  to postgres, service_role;
