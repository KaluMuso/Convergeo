-- M09-P03: Pickup QR/PIN token storage on orders (pickup fulfilment).
-- Reversible:
--   DROP TRIGGER IF EXISTS orders_guard_pickup_tokens ON public.orders;
--   DROP FUNCTION IF EXISTS public.guard_orders_pickup_tokens();
--   ALTER TABLE public.orders
--     DROP COLUMN IF EXISTS pickup_token_version,
--     DROP COLUMN IF EXISTS pickup_collected_at,
--     DROP COLUMN IF EXISTS pickup_pin_hash,
--     DROP COLUMN IF EXISTS pickup_qr_secret;

alter table public.orders
  add column if not exists pickup_qr_secret text,
  add column if not exists pickup_pin_hash text,
  add column if not exists pickup_collected_at timestamptz,
  add column if not exists pickup_token_version int not null default 0;

comment on column public.orders.pickup_qr_secret is
  'Signed QR payload for vendor pickup verification; server-issued only.';
comment on column public.orders.pickup_pin_hash is
  'PBKDF2 hash of the 6-digit pickup PIN; plaintext never stored.';
comment on column public.orders.pickup_collected_at is
  'Single-use claim timestamp; set atomically on successful pickup verify.';
comment on column public.orders.pickup_token_version is
  'Monotonic token generation; re-issue bumps version and invalidates prior QR/PIN.';

-- Pickup token fields are server-controlled (mirrors tickets.qr_secret/pin_hash guard in 0004).
create or replace function public.guard_orders_pickup_tokens()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;

  if tg_op = 'INSERT' then
    if new.pickup_qr_secret is not null
      or new.pickup_pin_hash is not null
      or new.pickup_collected_at is not null
      or coalesce(new.pickup_token_version, 0) <> 0 then
      raise exception 'order pickup tokens are server-controlled';
    end if;
  end if;

  if tg_op = 'UPDATE' then
    if new.pickup_qr_secret is distinct from old.pickup_qr_secret
      or new.pickup_pin_hash is distinct from old.pickup_pin_hash
      or new.pickup_collected_at is distinct from old.pickup_collected_at
      or new.pickup_token_version is distinct from old.pickup_token_version then
      raise exception 'order pickup tokens are server-controlled';
    end if;
  end if;

  if tg_op = 'DELETE' then
    raise exception 'orders cannot be deleted by clients';
  end if;

  return new;
end;
$$;

create trigger orders_guard_pickup_tokens
  before insert or update or delete on public.orders
  for each row
  execute function public.guard_orders_pickup_tokens();

comment on function public.guard_orders_pickup_tokens() is
  'Blocks client writes to pickup_qr_secret, pickup_pin_hash, pickup_collected_at, pickup_token_version.';
