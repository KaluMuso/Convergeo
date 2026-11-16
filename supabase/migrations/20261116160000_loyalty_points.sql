-- Convergeo Points v1 (proposal A1 + A2; feature flag `loyalty_points`, default OFF).
--
-- An append-only points ledger. Integer points only; a points balance is the
-- SUM of a user's rows. Points never convert to cash: the only outbound path is
-- `redeem` into a platform-funded coupon, which waits for the coupon engine
-- (PR #792, not on release yet). The `redeem` reason is reserved here so that
-- seam needs no schema change (TODO-after-#792: private.points_redeem_for_coupon).
--
--   points_ledger                 append-only rows; customers read only their own
--   private.points_award_order    earn after the return window (idempotent)
--   private.points_reverse_order  claw back on refund / return (idempotent)
--   private.points_award_review   reward the act of a verified review (idempotent)
--   private.points_expire_inactive 12-month inactivity expiry (idempotent)
--   private.points_admin_adjust   founder correction with a mandatory note
--   private.points_sweep          the n8n / internal tick that runs all of the above
--   public.points_summary         balance + lifetime for the API (service role only)
--   public.points_liability       outstanding points x points_ngwee_per_point
--
-- Writes happen ONLY inside these SECURITY DEFINER functions (no client
-- INSERT/UPDATE/DELETE grant, FORCE RLS, an append-only trigger).
--
-- Earn rules (all from platform_config, integer):
--   * 1 point per `points_earn_ngwee_per_point` ngwee (default 100 = K1) of the
--     customer-paid item value (order lines after offers, net of completed
--     refunds; the delivery fee earns nothing);
--   * only once the order is delivered / COD-collected, escrow has been released
--     (prepaid) and the return window has passed (largest returnable window on
--     the order, default `points_return_window_default_hours`), with no open
--     dispute and no open return;
--   * capped by `points_cap_per_order` and `points_cap_per_day` (Lusaka day,
--     every earn reason counts);
--   * never on the vendor owner's own order. Gift-to-self: TODO-after-#792 (the
--     gift-order columns are not on release yet; add the recipient check there).
--
-- Additive only. Reversible (manual; safe while the flag has never been on —
-- otherwise export points_ledger first, the balances are a customer promise):
--   drop trigger if exists reviews_points_award on public.reviews;
--   drop trigger if exists refunds_points_reverse on public.refunds;
--   drop function if exists private.points_review_trigger();
--   drop function if exists private.points_refund_trigger();
--   drop function if exists public.points_liability();
--   drop function if exists public.points_summary(uuid);
--   drop function if exists private.points_sweep(timestamptz);
--   drop function if exists private.points_admin_adjust(uuid, integer, text, uuid, text);
--   drop function if exists private.points_expire_inactive(timestamptz);
--   drop function if exists private.points_award_review(uuid, timestamptz);
--   drop function if exists private.points_reverse_order(uuid);
--   drop function if exists private.points_award_order(uuid, timestamptz);
--   drop function if exists private.points_insert(uuid, integer, text, text, uuid, uuid, uuid, text, timestamptz);
--   drop function if exists private.points_day_earned(uuid, timestamptz);
--   drop function if exists private.points_cfg(text, bigint);
--   drop table if exists public.points_ledger;
--   drop function if exists private.points_ledger_append_only();
--   delete from public.feature_flags where flag = 'loyalty_points';
--   delete from public.platform_config where key like 'points\_%';
--   delete from private.rate_counter_scope_manifest where scope = 'points_read';
--   -- then rebuild rate_counters_scope_check from the manifest (block 6 below).

-- ---------------------------------------------------------------------------
-- 1. Flag + config
-- ---------------------------------------------------------------------------

insert into public.feature_flags (flag, enabled, description) values
  ('loyalty_points', false,
   'Convergeo Points: earn on completed orders and verified reviews, /account/rewards.')
on conflict (flag) do nothing;

insert into public.platform_config (key, value, description) values
  ('points_ngwee_per_point', '5'::jsonb,
   'Liability value of one point in ngwee (5 = 0.5% return at 1 point per K1). Never cash.'),
  ('points_earn_ngwee_per_point', '100'::jsonb,
   'Earn rate: customer-paid ngwee per point earned (100 = 1 point per K1).'),
  ('points_cap_per_order', '2000'::jsonb,
   'Abuse cap: most points one order can earn.'),
  ('points_cap_per_day', '5000'::jsonb,
   'Abuse cap: most points one customer can earn per Lusaka day (all earn reasons).'),
  ('points_review_award', '30'::jsonb,
   'Points for a verified review (the act, never the rating).'),
  ('points_review_photo_bonus', '20'::jsonb,
   'Extra points when the verified review has a photo.'),
  ('points_return_window_default_hours', '48'::jsonb,
   'Return window used when no line on the order states one.'),
  ('points_expiry_inactive_days', '365'::jsonb,
   'Points expire after this many days with no points activity.'),
  ('points_coupon_threshold', '500'::jsonb,
   'Points needed for the next reward coupon (rewards page progress bar).')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- 2. Ledger
-- ---------------------------------------------------------------------------

create table if not exists public.points_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  points integer not null,
  reason text not null check (reason in (
    'order_completed', 'review', 'reversal', 'redeem', 'expire', 'admin_adjust'
  )),
  idempotency_key text not null unique
    check (idempotency_key ~ '^[-._:A-Za-z0-9]{1,160}$'),
  order_id uuid references public.orders (id) on delete set null,
  review_id uuid references public.reviews (id) on delete set null,
  reverses_entry_id uuid references public.points_ledger (id) on delete set null,
  actor uuid,
  note text check (note is null or char_length(note) <= 500),
  created_at timestamptz not null default timezone('utc', now()),
  -- Signs follow the reason. A zero row records an earn that hit a cap, so the
  -- order is settled and never retried.
  constraint points_ledger_sign_check check (
    (reason in ('order_completed', 'review') and points >= 0)
    or (reason in ('reversal', 'redeem', 'expire') and points < 0)
    or (reason = 'admin_adjust' and points <> 0)
  )
);

create index if not exists points_ledger_user_created_idx
  on public.points_ledger (user_id, created_at desc, id desc);
create index if not exists points_ledger_order_idx
  on public.points_ledger (order_id) where order_id is not null;

comment on table public.points_ledger is
  'Convergeo Points: append-only, integer points, balance = sum(points). Written only by private.points_* functions. Never cash.';

alter table public.points_ledger enable row level security;
alter table public.points_ledger force row level security;

drop policy if exists points_ledger_select_own on public.points_ledger;
create policy points_ledger_select_own on public.points_ledger
  for select to authenticated
  using (user_id = auth.uid());

revoke all on public.points_ledger from public, anon, authenticated;
grant select on public.points_ledger to authenticated;
grant select on public.points_ledger to service_role;

create or replace function private.points_ledger_append_only()
returns trigger
language plpgsql
as $$
begin
  raise exception 'points_ledger is append-only' using errcode = '42501';
end;
$$;

drop trigger if exists points_ledger_append_only on public.points_ledger;
create trigger points_ledger_append_only
  before update or delete on public.points_ledger
  for each row
  execute function private.points_ledger_append_only();

-- ---------------------------------------------------------------------------
-- 3. Helpers
-- ---------------------------------------------------------------------------

create or replace function private.points_cfg(p_key text, p_default bigint)
returns bigint
language sql
stable
security definer
set search_path = public, private
as $$
  select coalesce(
    (select case when jsonb_typeof(value) = 'number' then (value #>> '{}')::bigint
                 when jsonb_typeof(value) = 'string' and (value #>> '{}') ~ '^[0-9]+$'
                   then (value #>> '{}')::bigint end
       from public.platform_config where key = p_key),
    p_default
  );
$$;

-- Points a user already earned (order + review) on the Lusaka day of p_now.
create or replace function private.points_day_earned(p_user uuid, p_now timestamptz)
returns bigint
language sql
stable
security definer
set search_path = public, private
as $$
  select coalesce(sum(points), 0)::bigint
  from public.points_ledger
  where user_id = p_user
    and reason in ('order_completed', 'review')
    and (created_at at time zone 'Africa/Lusaka')::date = (p_now at time zone 'Africa/Lusaka')::date;
$$;

-- The single insert path. Returns the new row id, or null when the key exists.
-- Notifies on a positive earn: in-app row + WhatsApp outbox row (template
-- points_earned; dedupe by entry), both idempotent by key.
create or replace function private.points_insert(
  p_user uuid,
  p_points integer,
  p_reason text,
  p_key text,
  p_order uuid,
  p_review uuid,
  p_actor uuid,
  p_note text,
  p_now timestamptz
)
returns uuid
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_id uuid;
  v_balance bigint;
begin
  insert into public.points_ledger (
    user_id, points, reason, idempotency_key, order_id, review_id, actor, note, created_at
  ) values (
    p_user, p_points, p_reason, p_key, p_order, p_review, p_actor, p_note, p_now
  )
  on conflict (idempotency_key) do nothing
  returning id into v_id;

  if v_id is not null and p_points > 0 and p_reason in ('order_completed', 'review') then
    select coalesce(sum(points), 0) into v_balance
    from public.points_ledger where user_id = p_user;
    perform private.enqueue_in_app_notification(
      p_user, 'customer', 'points_earned',
      jsonb_build_object('points', p_points, 'balance', v_balance),
      '/account/rewards', 'points_earned:' || v_id::text
    );
    insert into public.notification_outbox (dedupe_key, channel, template, payload, status)
    values (
      'points_earned:' || v_id::text || ':whatsapp', 'whatsapp', 'points_earned',
      jsonb_build_object(
        'recipient_id', p_user, 'points', p_points, 'balance', v_balance,
        'threshold', private.points_cfg('points_coupon_threshold', 500),
        'reason', p_reason
      ),
      'pending'
    )
    on conflict (dedupe_key) do nothing;
  end if;
  return v_id;
end;
$$;

-- ---------------------------------------------------------------------------
-- 4. Transitions
-- ---------------------------------------------------------------------------

-- Earn for one order. Outcomes: awarded | already_awarded | flag_off | capped |
-- not_yet | not_eligible:<reason>. Safe to call any number of times.
create or replace function private.points_award_order(
  p_order uuid,
  p_now timestamptz default timezone('utc', now())
)
returns text
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_order record;
  v_owner uuid;
  v_delivered_at timestamptz;
  v_window_hours integer;
  v_paid bigint;
  v_refunded bigint;
  v_points bigint;
  v_day_left bigint;
  v_key text := 'earn-ord-' || p_order::text;
begin
  if not coalesce((select enabled from public.feature_flags where flag = 'loyalty_points'), false) then
    return 'flag_off';
  end if;
  if exists (select 1 from public.points_ledger where idempotency_key = v_key) then
    return 'already_awarded';
  end if;

  select id, customer_id, vendor_id, status, cod into v_order
  from public.orders where id = p_order;
  if not found then
    return 'not_eligible:order_not_found';
  end if;
  if v_order.status not in ('delivered', 'completed') then
    return 'not_eligible:status_' || v_order.status;
  end if;

  select owner_user_id into v_owner from public.vendors where id = v_order.vendor_id;
  if v_owner = v_order.customer_id then
    return 'not_eligible:self_order';
  end if;
  -- TODO-after-#792: also refuse a gift order whose recipient is the buyer.

  select max(created_at) into v_delivered_at
  from public.order_events
  where order_id = p_order and to_status in ('delivered', 'completed');
  if v_delivered_at is null then
    return 'not_eligible:no_delivery_event';
  end if;

  select coalesce(
           max(greatest(48, least(168, vl.return_window_hours))) filter (
             where vl.returnable and vl.return_window_hours is not null
           ),
           private.points_cfg('points_return_window_default_hours', 48)::integer
         )
    into v_window_hours
  from public.order_items oi
  left join public.order_item_products oip on oip.order_item_id = oi.id
  left join public.vendor_listings vl on vl.id = oip.listing_id
  where oi.order_id = p_order;

  if p_now < v_delivered_at + make_interval(hours => v_window_hours) then
    return 'not_yet';
  end if;

  if not v_order.cod and v_order.status <> 'completed' and not exists (
    select 1 from public.ledger_transactions
    where order_id = p_order and kind = 'release_to_vendor'
  ) then
    return 'not_yet';
  end if;

  if exists (
    select 1 from public.disputes
    where order_id = p_order and status in ('open', 'vendor_responded')
  ) then
    return 'not_yet';
  end if;
  if exists (
    select 1 from public.returns r
    join public.order_items oi on oi.id = r.order_item_id
    where oi.order_id = p_order and r.status in ('requested', 'approved')
  ) then
    return 'not_yet';
  end if;

  select coalesce(sum(qty::bigint * unit_price_ngwee), 0) into v_paid
  from public.order_items where order_id = p_order;
  select coalesce(sum(amount_ngwee), 0) into v_refunded
  from public.refunds where order_id = p_order and status = 'completed';

  -- Serialise per user so the day cap holds under concurrent sweeps.
  perform pg_advisory_xact_lock(hashtextextended('points:' || v_order.customer_id::text, 0));
  if exists (select 1 from public.points_ledger where idempotency_key = v_key) then
    return 'already_awarded';
  end if;

  v_points := greatest(v_paid - v_refunded, 0)
              / greatest(private.points_cfg('points_earn_ngwee_per_point', 100), 1);
  v_points := least(v_points, private.points_cfg('points_cap_per_order', 2000));
  v_day_left := greatest(
    private.points_cfg('points_cap_per_day', 5000)
      - private.points_day_earned(v_order.customer_id, p_now),
    0
  );
  v_points := least(v_points, v_day_left);

  perform private.points_insert(
    v_order.customer_id, v_points::integer, 'order_completed', v_key,
    p_order, null, null,
    case when v_points = 0 then 'capped_or_zero' end, p_now
  );
  return case when v_points = 0 then 'capped' else 'awarded' end;
end;
$$;

-- Reverse points for refunded value. Target = what the order should have
-- earned at today's refund total (same rate and per-order cap); anything above
-- it is reversed. The key carries the refund total, so each refund state is
-- applied at most once and a replay is a no-op. Runs even with the flag off.
create or replace function private.points_reverse_order(p_order uuid)
returns integer
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_user uuid;
  v_earned bigint;
  v_net bigint;
  v_paid bigint;
  v_refunded bigint;
  v_target bigint;
  v_delta bigint;
  v_earn_id uuid;
begin
  select user_id, points, id into v_user, v_earned, v_earn_id
  from public.points_ledger
  where idempotency_key = 'earn-ord-' || p_order::text;
  if v_user is null or v_earned = 0 then
    return 0;
  end if;

  select coalesce(sum(points), 0) into v_net
  from public.points_ledger
  where order_id = p_order and reason in ('order_completed', 'reversal');

  select coalesce(sum(qty::bigint * unit_price_ngwee), 0) into v_paid
  from public.order_items where order_id = p_order;
  select coalesce(sum(amount_ngwee), 0) into v_refunded
  from public.refunds where order_id = p_order and status = 'completed';

  v_target := least(
    greatest(v_paid - v_refunded, 0)
      / greatest(private.points_cfg('points_earn_ngwee_per_point', 100), 1),
    v_earned
  );
  v_delta := v_net - v_target;
  if v_delta <= 0 then
    return 0;
  end if;

  insert into public.points_ledger (
    user_id, points, reason, idempotency_key, order_id, reverses_entry_id, note
  ) values (
    v_user, -v_delta::integer, 'reversal',
    'reverse-ord-' || p_order::text || '-' || v_refunded::text,
    p_order, v_earn_id, 'refund_or_return'
  )
  on conflict (idempotency_key) do nothing;
  return v_delta::integer;
end;
$$;

-- Reward a verified review (one per order item already). The rating is never read.
create or replace function private.points_award_review(
  p_review uuid,
  p_now timestamptz default timezone('utc', now())
)
returns text
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_customer uuid;
  v_owner uuid;
  v_status text;
  v_order_status text;
  v_photos integer;
  v_points bigint;
  v_key text := 'review-' || p_review::text;
begin
  if not coalesce((select enabled from public.feature_flags where flag = 'loyalty_points'), false) then
    return 'flag_off';
  end if;
  if exists (select 1 from public.points_ledger where idempotency_key = v_key) then
    return 'already_awarded';
  end if;

  select o.customer_id, v.owner_user_id, r.status, o.status, cardinality(r.photos)
    into v_customer, v_owner, v_status, v_order_status, v_photos
  from public.reviews r
  join public.order_items oi on oi.id = r.order_item_id
  join public.orders o on o.id = oi.order_id
  join public.vendors v on v.id = o.vendor_id
  where r.id = p_review;
  if v_customer is null then
    return 'not_eligible:review_not_found';
  end if;
  if v_status <> 'published' then
    return 'not_eligible:review_' || v_status;
  end if;
  if v_order_status not in ('delivered', 'completed') then
    return 'not_eligible:unverified';
  end if;
  if v_owner = v_customer then
    return 'not_eligible:self_order';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('points:' || v_customer::text, 0));
  v_points := private.points_cfg('points_review_award', 30)
              + case when coalesce(v_photos, 0) > 0
                     then private.points_cfg('points_review_photo_bonus', 20) else 0 end;
  v_points := least(
    v_points,
    greatest(private.points_cfg('points_cap_per_day', 5000)
             - private.points_day_earned(v_customer, p_now), 0)
  );
  perform private.points_insert(
    v_customer, v_points::integer, 'review', v_key, null, p_review, null,
    case when v_points = 0 then 'capped_or_zero' end, p_now
  );
  return case when v_points = 0 then 'capped' else 'awarded' end;
end;
$$;

-- Expire the whole positive balance after N days with no points activity.
-- Keyed by the last-activity instant, so it fires once per dormant spell.
create or replace function private.points_expire_inactive(
  p_now timestamptz default timezone('utc', now())
)
returns integer
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_row record;
  v_count integer := 0;
  v_days integer := private.points_cfg('points_expiry_inactive_days', 365)::integer;
begin
  for v_row in
    select user_id, sum(points) as balance, max(created_at) as last_at
    from public.points_ledger
    group by user_id
    having sum(points) > 0 and max(created_at) < p_now - make_interval(days => v_days)
  loop
    insert into public.points_ledger (user_id, points, reason, idempotency_key, note, created_at)
    values (
      v_row.user_id, -v_row.balance::integer, 'expire',
      'expire-' || v_row.user_id::text || '-' || extract(epoch from v_row.last_at)::bigint::text,
      'inactive_' || v_days::text || 'd', p_now
    )
    on conflict (idempotency_key) do nothing;
    v_count := v_count + 1;
  end loop;
  return v_count;
end;
$$;

create or replace function private.points_admin_adjust(
  p_user uuid,
  p_points integer,
  p_key text,
  p_actor uuid,
  p_note text
)
returns uuid
language plpgsql
security definer
set search_path = public, private
as $$
begin
  if p_actor is null or coalesce(btrim(p_note), '') = '' then
    raise exception 'admin points adjustment needs an actor and a note' using errcode = '22023';
  end if;
  return private.points_insert(
    p_user, p_points, 'admin_adjust', 'adjust-' || p_key, null, null, p_actor, p_note,
    timezone('utc', now())
  );
end;
$$;

-- The tick: earn for orders past their window, re-check reversals, expire.
create or replace function private.points_sweep(
  p_now timestamptz default timezone('utc', now())
)
returns jsonb
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_order uuid;
  v_outcome text;
  v_awarded integer := 0;
  v_reversed integer := 0;
  v_expired integer := 0;
begin
  -- Reversals first and regardless of the flag: refunds must always claw back.
  for v_order in
    select distinct pl.order_id
    from public.points_ledger pl
    join public.refunds rf on rf.order_id = pl.order_id and rf.status = 'completed'
    where pl.reason = 'order_completed' and pl.points > 0
  loop
    if private.points_reverse_order(v_order) > 0 then
      v_reversed := v_reversed + 1;
    end if;
  end loop;

  if not coalesce((select enabled from public.feature_flags where flag = 'loyalty_points'), false) then
    return jsonb_build_object('enabled', false, 'awarded', 0, 'reversed', v_reversed, 'expired', 0);
  end if;

  for v_order in
    select o.id
    from public.orders o
    where o.status in ('delivered', 'completed')
      and o.updated_at > p_now - interval '60 days'
      and not exists (
        select 1 from public.points_ledger pl
        where pl.idempotency_key = 'earn-ord-' || o.id::text
      )
    order by o.updated_at
    limit 2000
  loop
    v_outcome := private.points_award_order(v_order, p_now);
    if v_outcome = 'awarded' then
      v_awarded := v_awarded + 1;
    end if;
  end loop;

  v_expired := private.points_expire_inactive(p_now);
  return jsonb_build_object(
    'enabled', true, 'awarded', v_awarded, 'reversed', v_reversed, 'expired', v_expired
  );
end;
$$;

create or replace function public.points_summary(p_user uuid)
returns jsonb
language sql
stable
security definer
set search_path = public, private
as $$
  select jsonb_build_object(
    'balance', coalesce(sum(points), 0),
    'lifetime_earned', coalesce(sum(points) filter (where points > 0 and reason <> 'admin_adjust'), 0),
    'last_activity_at', max(created_at)
  )
  from public.points_ledger
  where user_id = p_user;
$$;

-- Outstanding (positive balances only) and its ngwee liability for reconciliation.
create or replace function public.points_liability()
returns jsonb
language sql
stable
security definer
set search_path = public, private
as $$
  with balances as (
    select sum(points)::bigint as b from public.points_ledger group by user_id
  )
  select jsonb_build_object(
    'points_outstanding', coalesce(sum(b) filter (where b > 0), 0),
    'ngwee_per_point', private.points_cfg('points_ngwee_per_point', 5),
    'liability_ngwee',
      coalesce(sum(b) filter (where b > 0), 0) * private.points_cfg('points_ngwee_per_point', 5)
  )
  from balances;
$$;

-- ---------------------------------------------------------------------------
-- 5. Hooks (never break the money path: failures only warn; the sweep retries)
-- ---------------------------------------------------------------------------

create or replace function private.points_refund_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
begin
  if new.status = 'completed' and (tg_op = 'INSERT' or old.status is distinct from 'completed') then
    begin
      perform private.points_reverse_order(new.order_id);
    exception when others then
      raise warning 'points_reverse_order skipped (order %, sqlstate %): %',
        new.order_id, sqlstate, sqlerrm;
    end;
  end if;
  return null;
end;
$$;

drop trigger if exists refunds_points_reverse on public.refunds;
create trigger refunds_points_reverse
  after insert or update of status on public.refunds
  for each row
  execute function private.points_refund_trigger();

create or replace function private.points_review_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
begin
  begin
    perform private.points_award_review(new.id);
  exception when others then
    raise warning 'points_award_review skipped (review %, sqlstate %): %',
      new.id, sqlstate, sqlerrm;
  end;
  return null;
end;
$$;

drop trigger if exists reviews_points_award on public.reviews;
create trigger reviews_points_award
  after insert on public.reviews
  for each row
  execute function private.points_review_trigger();

-- Grants: nothing to clients; service role may call the read/ops entry points.
revoke all on function private.points_ledger_append_only() from public, anon, authenticated;
revoke all on function private.points_cfg(text, bigint) from public, anon, authenticated;
revoke all on function private.points_day_earned(uuid, timestamptz) from public, anon, authenticated;
revoke all on function private.points_insert(uuid, integer, text, text, uuid, uuid, uuid, text, timestamptz)
  from public, anon, authenticated;
revoke all on function private.points_award_order(uuid, timestamptz) from public, anon, authenticated;
revoke all on function private.points_reverse_order(uuid) from public, anon, authenticated;
revoke all on function private.points_award_review(uuid, timestamptz) from public, anon, authenticated;
revoke all on function private.points_expire_inactive(timestamptz) from public, anon, authenticated;
revoke all on function private.points_admin_adjust(uuid, integer, text, uuid, text)
  from public, anon, authenticated;
revoke all on function private.points_sweep(timestamptz) from public, anon, authenticated;
revoke all on function private.points_refund_trigger() from public, anon, authenticated;
revoke all on function private.points_review_trigger() from public, anon, authenticated;
revoke all on function public.points_summary(uuid) from public, anon, authenticated;
revoke all on function public.points_liability() from public, anon, authenticated;
grant execute on function public.points_summary(uuid) to service_role;
grant execute on function public.points_liability() to service_role;
grant execute on function private.points_sweep(timestamptz) to service_role;
grant execute on function private.points_award_order(uuid, timestamptz) to service_role;

-- ---------------------------------------------------------------------------
-- 6. Rate scope: manifest + constraint rebuilt from the FULL manifest
-- ---------------------------------------------------------------------------

insert into private.rate_counter_scope_manifest (scope) values ('points_read')
on conflict (scope) do nothing;

do $$
declare
  v_list text;
begin
  select string_agg(quote_literal(scope), ', ' order by scope)
    into v_list
  from private.rate_counter_scope_manifest;
  execute 'alter table public.rate_counters drop constraint if exists rate_counters_scope_check';
  execute format(
    'alter table public.rate_counters add constraint rate_counters_scope_check check (scope in (%s))',
    v_list
  );
end;
$$;
