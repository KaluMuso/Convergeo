-- One database decision owns prepaid success, its ledger allocation and outbox intent.
-- A provider-confirmed collection that loses to cancellation or another attempt is
-- retained for reconciliation/refund without crediting ordinary checkout escrow.
-- Unknown merchant references use the existing signed webhook store as a
-- service-role-visible quarantine; clearing processed_at permits manual replay.
alter table public.webhook_events
  add column quarantine_reason text
    check (quarantine_reason in (
      'missing_merchant_reference', 'unknown_merchant_reference'
    )),
  add column quarantined_at timestamptz;
create index webhook_events_quarantine_idx
  on public.webhook_events (quarantined_at)
  where quarantined_at is not null;

create table public.payment_collection_exceptions (
  id uuid primary key default gen_random_uuid(),
  payment_id uuid not null references public.payments (id) on delete restrict,
  provider_reference text not null,
  reason text not null,
  first_observation jsonb not null,
  latest_observation jsonb not null,
  occurrences integer not null default 1 check (occurrences > 0),
  resolved_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (payment_id, provider_reference)
);

alter table public.payment_collection_exceptions enable row level security;
alter table public.payment_collection_exceptions force row level security;
revoke all on public.payment_collection_exceptions from public, anon, authenticated;
grant select, insert, update on public.payment_collection_exceptions to service_role;

create or replace function public.apply_prepaid_collection_success(
  p_payment_id uuid,
  p_actor_id uuid,
  p_note text,
  p_observation jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_checkout_id uuid;
  v_checkout public.checkout_groups%rowtype;
  v_payment public.payments%rowtype;
  v_prior_status text;
  v_existing uuid;
  v_cash uuid;
  v_escrow uuid;
  v_order record;
  v_order_count integer := 0;
  v_order_total bigint := 0;
  v_cancelled_order boolean := false;
  v_txn uuid;
  v_provider_reference text;
  v_late_reason text;
begin
  if nullif(btrim(p_note), '') is null then
    raise exception 'payment transition note is required';
  end if;

  -- Every success attempt takes checkout, payment, then ordered order locks.
  -- The existing cancellation writer updates the payment row, so this row lock
  -- also serializes the winner against cancellation on independent connections.
  select checkout_group_id into v_checkout_id
  from public.payments where id = p_payment_id;
  if v_checkout_id is null then
    raise exception 'payment % not found', p_payment_id;
  end if;
  select * into v_checkout
  from public.checkout_groups where id = v_checkout_id for update;
  select * into v_payment
  from public.payments where id = p_payment_id for update;
  if v_payment.checkout_group_id is distinct from v_checkout_id then
    raise exception 'payment checkout changed during collection';
  end if;

  -- Repeat the D1 identity check under the decision lock. Python validates
  -- the provider document before this call; this prevents a changed payment
  -- row between that validation and the financial commit.
  if v_payment.provider <> 'lenco'
     or p_observation->>'reference' is distinct from v_payment.lenco_reference
     or p_observation->>'currency' is distinct from 'ZMW'
     or (p_observation->>'amount_ngwee')::bigint is distinct from v_payment.amount_ngwee
     or (
       nullif(v_payment.raw->>'provider_reference', '') is not null
       and p_observation->>'provider_reference'
           is distinct from v_payment.raw->>'provider_reference'
     ) then
    raise exception 'provider collection identity changed for payment %', p_payment_id;
  end if;
  v_provider_reference := coalesce(
    nullif(p_observation->>'provider_reference', ''),
    v_payment.lenco_reference
  );

  if v_payment.status = 'success' then
    return jsonb_build_object('result', 'duplicate', 'from_status', 'success');
  end if;
  v_prior_status := v_payment.status;

  -- Lock each order before deciding whether the checkout is still payable.
  -- Amounts are the same order-item + delivery-fee calculation as D1.
  for v_order in
    select o.id, o.status, o.vendor_id,
           coalesce((
             select sum(oi.qty * oi.unit_price_ngwee)
             from public.order_items oi where oi.order_id = o.id
           ), 0) + o.delivery_fee_ngwee as gross_ngwee
    from public.orders o
    where o.checkout_group_id = v_checkout_id
    order by o.id
    for update of o
  loop
    v_cancelled_order := v_cancelled_order or v_order.status = 'cancelled';
    if v_order.gross_ngwee > 0 then
      v_order_count := v_order_count + 1;
      v_order_total := v_order_total + v_order.gross_ngwee;
    end if;
  end loop;

  select id into v_existing
  from public.ledger_transactions
  where checkout_group_id = v_checkout_id
    and kind in ('charge_received', 'escrow_hold')
  order by created_at, id limit 1;

  if v_prior_status = 'cancelled' then
    v_late_reason := 'payment_cancelled';
  elsif v_cancelled_order then
    v_late_reason := 'order_cancelled';
  elsif v_existing is not null then
    v_late_reason := 'checkout_already_allocated';
  elsif exists (
    select 1 from public.payments
    where checkout_group_id = v_checkout_id and status = 'success'
  ) then
    v_late_reason := 'sibling_payment_success';
  end if;

  if v_late_reason is not null then
    insert into public.payment_collection_exceptions (
      payment_id, provider_reference, reason, first_observation,
      latest_observation
    ) values (
      p_payment_id, v_provider_reference, v_late_reason, p_observation,
      p_observation
    )
    on conflict (payment_id, provider_reference) do update
      set latest_observation = excluded.latest_observation,
          occurrences = public.payment_collection_exceptions.occurrences + 1,
          updated_at = timezone('utc', now());
    insert into public.audit_log (
      actor, action, entity_type, entity_id, before, after
    ) values (
      p_actor_id, 'payment.collection_exception', 'payment', p_payment_id,
      jsonb_build_object('status', v_prior_status),
      jsonb_build_object('reason', v_late_reason, 'provider_reference',
                         v_provider_reference, 'note', p_note)
    );
    return jsonb_build_object('result', 'late_collection',
                              'from_status', v_prior_status,
                              'reason', v_late_reason);
  end if;

  if v_prior_status not in (
    'initiated', 'ussd_pushed', 'pay_offline', 'failed', 'expired'
  ) then
    raise exception 'illegal payment success transition from %', v_prior_status;
  end if;
  if v_order_count > 0 and v_order_total <> v_payment.amount_ngwee then
    raise exception 'checkout order gross % does not match payment %',
      v_order_total, v_payment.amount_ngwee;
  end if;

  select id into strict v_cash from public.ledger_accounts
  where kind = 'platform_cash' and vendor_id is null;
  select id into strict v_escrow from public.ledger_accounts
  where kind = 'escrow' and vendor_id is null;

  update public.payments set status = 'success' where id = p_payment_id;

  if v_order_count = 0 then
    insert into public.ledger_transactions (
      kind, idempotency_key, checkout_group_id, payment_id
    ) values (
      'charge_received', 'prepaid-charge-checkout-' || v_checkout_id,
      v_checkout_id, p_payment_id
    ) returning id into v_txn;
    insert into public.ledger_postings (transaction_id, account_id, amount_ngwee)
    values (v_txn, v_cash, v_payment.amount_ngwee),
           (v_txn, v_escrow, -v_payment.amount_ngwee);
  else
    for v_order in
      select o.id,
             coalesce((
               select sum(oi.qty * oi.unit_price_ngwee)
               from public.order_items oi where oi.order_id = o.id
             ), 0) + o.delivery_fee_ngwee as gross_ngwee
      from public.orders o
      where o.checkout_group_id = v_checkout_id
      order by o.id
    loop
      if v_order.gross_ngwee <= 0 then
        continue;
      end if;
      insert into public.ledger_transactions (
        kind, idempotency_key, checkout_group_id, order_id, payment_id
      ) values (
        'escrow_hold', 'escrow-hold-' || v_order.id, v_checkout_id,
        v_order.id, p_payment_id
      ) returning id into v_txn;
      insert into public.ledger_postings (
        transaction_id, account_id, amount_ngwee
      ) values (v_txn, v_cash, v_order.gross_ngwee),
               (v_txn, v_escrow, -v_order.gross_ngwee);
    end loop;
  end if;

  insert into public.audit_log (
    actor, action, entity_type, entity_id, before, after
  ) values (
    p_actor_id, 'payment.transition', 'payment', p_payment_id,
    jsonb_build_object('status', v_prior_status),
    jsonb_build_object('status', 'success', 'note', p_note)
  );

  insert into public.notification_outbox (
    dedupe_key, channel, template, payload, status
  ) values (
    'payment_received:' || v_checkout_id || ':whatsapp',
    'whatsapp', 'payment_received',
    jsonb_build_object(
      'payment_id', p_payment_id,
      'checkout_group_id', v_checkout_id,
      'order_reference', v_payment.lenco_reference,
      'amount_ngwee', v_payment.amount_ngwee,
      'recipient_id', v_checkout.customer_id
    ), 'pending'
  ) on conflict (dedupe_key) do nothing;

  insert into public.notification_outbox (
    dedupe_key, channel, template, payload, status
  )
  select 'order_placed:' || o.id || ':whatsapp', 'whatsapp',
         'vendor_new_order',
         jsonb_build_object(
           'order_id', o.id, 'order_reference', o.id,
           'recipient_id', v.owner_user_id
         ), 'pending'
  from public.orders o
  join public.vendors v on v.id = o.vendor_id
  where o.checkout_group_id = v_checkout_id
    and o.status <> 'cancelled'
    and v.owner_user_id is not null
  on conflict (dedupe_key) do nothing;

  return jsonb_build_object('result', 'applied',
                            'from_status', v_prior_status);
end;
$$;

revoke all on function public.apply_prepaid_collection_success(
  uuid, uuid, text, jsonb
) from public, anon, authenticated;
grant execute on function public.apply_prepaid_collection_success(
  uuid, uuid, text, jsonb
) to service_role;
