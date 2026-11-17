-- Vendor weekly digest (proposal E3; feature flag `vendor_weekly_digest`, default OFF).
--
-- private.vendor_weekly_digest(p_now, p_send) computes, per ACTIVE vendor for
-- the 7 days before p_now: orders (not cancelled), sales (integer ngwee, order
-- lines), the top item (by units, then sales), new followers, pending actions
-- (orders waiting on the vendor + open disputes + requested returns) and the
-- next payout (oldest pending/processing). Vendors with no orders, no new
-- followers and nothing pending are skipped. With p_send it enqueues, keyed by
-- vendor + Lusaka week (idempotent): a WhatsApp outbox row (template
-- vendor_weekly_digest) and an in-app vendor notification.
--
-- Additive only. Reversible (manual):
--   drop function if exists private.vendor_weekly_digest(timestamptz, boolean);
--   delete from public.feature_flags where flag = 'vendor_weekly_digest';

insert into public.feature_flags (flag, enabled, description) values
  ('vendor_weekly_digest', false,
   'Weekly seller digest (WhatsApp + in-app), Monday 08:00 Lusaka via n8n.')
on conflict (flag) do nothing;

create or replace function private.vendor_weekly_digest(
  p_now timestamptz default timezone('utc', now()),
  p_send boolean default false
)
returns setof jsonb
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_from timestamptz := p_now - interval '7 days';
  v_week text := to_char(p_now at time zone 'Africa/Lusaka', 'IYYY-"W"IW');
  v_row record;
  v_doc jsonb;
begin
  for v_row in
    with orders_w as (
      select o.vendor_id, o.id
      from public.orders o
      where o.created_at >= v_from and o.created_at < p_now and o.status <> 'cancelled'
    ),
    sales as (
      select ow.vendor_id, count(distinct ow.id) as orders,
             coalesce(sum(oi.qty::bigint * oi.unit_price_ngwee), 0)::bigint as sales_ngwee
      from orders_w ow
      left join public.order_items oi on oi.order_id = ow.id
      group by ow.vendor_id
    ),
    top_item as (
      select distinct on (ow.vendor_id) ow.vendor_id, oi.title_snapshot as title
      from orders_w ow
      join public.order_items oi on oi.order_id = ow.id
      where oi.title_snapshot is not null
      group by ow.vendor_id, oi.title_snapshot
      order by ow.vendor_id, sum(oi.qty) desc, sum(oi.qty::bigint * oi.unit_price_ngwee) desc,
               oi.title_snapshot
    ),
    followers as (
      select vendor_id, count(*) as n
      from public.vendor_follows
      where created_at >= v_from and created_at < p_now
      group by vendor_id
    ),
    pending as (
      select vendor_id, count(*) as n from (
        select o.vendor_id from public.orders o
          where o.status in ('placed', 'confirmed', 'processing')
        union all
        select o.vendor_id from public.disputes d join public.orders o on o.id = d.order_id
          where d.status = 'open'
        union all
        select o.vendor_id from public.returns r
          join public.order_items oi on oi.id = r.order_item_id
          join public.orders o on o.id = oi.order_id
          where r.status = 'requested'
      ) p group by vendor_id
    ),
    next_payout as (
      select distinct on (vendor_id) vendor_id, amount_ngwee, created_at
      from public.payouts
      where status in ('pending', 'processing')
      order by vendor_id, created_at
    )
    select v.id, v.owner_user_id, v.display_name,
           coalesce(s.orders, 0)::int as orders,
           coalesce(s.sales_ngwee, 0)::bigint as sales_ngwee,
           t.title as top_item,
           coalesce(f.n, 0)::int as new_followers,
           coalesce(p.n, 0)::int as pending_actions,
           np.amount_ngwee as next_payout_ngwee,
           np.created_at as next_payout_created_at
    from public.vendors v
    left join sales s on s.vendor_id = v.id
    left join top_item t on t.vendor_id = v.id
    left join followers f on f.vendor_id = v.id
    left join pending p on p.vendor_id = v.id
    left join next_payout np on np.vendor_id = v.id
    where v.status = 'active'
      and (coalesce(s.orders, 0) > 0 or coalesce(f.n, 0) > 0 or coalesce(p.n, 0) > 0)
    order by v.id
  loop
    v_doc := jsonb_build_object(
      'vendor_id', v_row.id,
      'owner_user_id', v_row.owner_user_id,
      'shop_name', v_row.display_name,
      'week', v_week,
      'orders', v_row.orders,
      'sales_ngwee', v_row.sales_ngwee,
      'top_item', v_row.top_item,
      'new_followers', v_row.new_followers,
      'pending_actions', v_row.pending_actions,
      'next_payout_ngwee', v_row.next_payout_ngwee,
      'next_payout_created_at', v_row.next_payout_created_at
    );
    if p_send then
      insert into public.notification_outbox (dedupe_key, channel, template, payload, status)
      values (
        'vendor_weekly_digest:' || v_row.id::text || '-' || v_week || ':whatsapp',
        'whatsapp', 'vendor_weekly_digest',
        v_doc || jsonb_build_object('recipient_id', v_row.owner_user_id),
        'pending'
      )
      on conflict (dedupe_key) do nothing;
      perform private.enqueue_in_app_notification(
        v_row.owner_user_id, 'vendor', 'vendor_weekly_digest',
        jsonb_build_object(
          'orders', v_row.orders,
          -- Pre-formatted K amount (integer arithmetic only, no float).
          'sales', 'K' || to_char(v_row.sales_ngwee / 100, 'FM999,999,999,990') || '.'
                   || lpad((v_row.sales_ngwee % 100)::text, 2, '0'),
          'followers', v_row.new_followers, 'pending_actions', v_row.pending_actions
        ),
        '/analytics', 'vendor_weekly_digest:' || v_row.id::text || '-' || v_week
      );
    end if;
    return next v_doc;
  end loop;
end;
$$;

revoke all on function private.vendor_weekly_digest(timestamptz, boolean)
  from public, anon, authenticated;
grant execute on function private.vendor_weekly_digest(timestamptz, boolean) to service_role;
