-- Optional, owner-scoped idempotency for POST /cart/items.
-- Reversible (after callers stop sending keys): drop function, then drop table.

create table public.cart_add_requests (
  cart_id uuid not null references public.carts (id) on delete cascade,
  idempotency_key text not null check (length(idempotency_key) between 1 and 128),
  request_body jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (cart_id, idempotency_key)
);

alter table public.cart_add_requests enable row level security;
alter table public.cart_add_requests force row level security;
revoke all on public.cart_add_requests from public, anon, authenticated;
grant select, insert on public.cart_add_requests to service_role;

comment on table public.cart_add_requests is
  'Service-only cart add claims. A claim and its cart line increment commit in one transaction.';

create function public.apply_cart_add_idempotent(
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
  p_location_id uuid
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
    or p_qty < 1 or p_unit_price_ngwee < 1 then
    raise exception 'cart.add_parameters_invalid' using errcode = '22023';
  end if;

  -- Serialize all keyed adds for this cart, including distinct keys. The API
  -- revalidates price and stock if its expected line snapshot went stale.
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

  select qty, pickup_location_id into v_qty, v_location_id
  from public.cart_items
  where cart_id = p_cart_id and listing_id = p_listing_id
  for update;
  if found then
    if v_qty is distinct from p_expected_qty
      or v_location_id is distinct from p_expected_location_id then
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
      cart_id, listing_id, qty, unit_price_ngwee, wholesale, pickup_location_id
    ) values (
      p_cart_id, p_listing_id, p_qty, p_unit_price_ngwee, p_wholesale, p_location_id
    );
  end if;

  insert into public.cart_add_requests (cart_id, idempotency_key, request_body)
  values (p_cart_id, p_key, p_body);
  return 'applied';
end;
$$;

revoke all on function public.apply_cart_add_idempotent(
  uuid, uuid, text, text, jsonb, uuid, integer, integer, uuid, bigint, boolean, uuid
) from public, anon, authenticated;
grant execute on function public.apply_cart_add_idempotent(
  uuid, uuid, text, text, jsonb, uuid, integer, integer, uuid, bigint, boolean, uuid
) to service_role;
