-- Forward service collection settlement; retain original receipt/exception semantics.
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
  v_receipt_identity jsonb;
  v_accepted_receipt public.payment_collection_receipts%rowtype;
  v_late_reason text;
  v_obligation public.service_payment_obligations%rowtype;
begin
  if nullif(btrim(p_note), '') is null then
    raise exception 'payment transition note is required';
  end if;

  -- Shared scope: ordered linked checkouts -> payments -> orders -> escrow gate.
  select checkout_group_id into v_checkout_id
  from public.payments where id = p_payment_id;
  if v_checkout_id is null then
    raise exception 'payment % not found', p_payment_id;
  end if;
  perform public.lock_payment_checkout_scope(v_checkout_id);
  select * into v_checkout
  from public.checkout_groups where id = v_checkout_id for update;
  select * into v_payment
  from public.payments where id = p_payment_id for update;
  if v_payment.checkout_group_id is distinct from v_checkout_id then
    raise exception 'payment checkout changed during collection';
  end if;

  select * into v_obligation from public.service_payment_obligations
  where checkout_group_id = v_checkout_id;
  if v_obligation.id is not null and not public.service_obligation_is_valid(v_obligation.id) then
    -- Do not allocate to the unrelated order; retain the actual provider observation.
    v_late_reason := 'service_obligation_link_invalid';
    v_obligation := null;
  end if;
  if v_payment.rail = 'card' and
     coalesce((p_observation->>'canonical_status_verified')::boolean, false) is not true then
    raise exception 'canonical card verification required';
  end if;

  -- Retain D1 identity validation under the decision lock.
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
  v_receipt_identity := jsonb_build_object(
    'provider', v_payment.provider,
    'provider_reference', v_provider_reference,
    'merchant_reference', v_payment.lenco_reference,
    'currency', p_observation->>'currency',
    'amount_ngwee', v_payment.amount_ngwee
  );
  if v_obligation.id is not null then
    v_receipt_identity := v_receipt_identity || jsonb_build_object(
      'obligation_id',v_obligation.id,'order_id',v_obligation.order_id,'leg',v_obligation.leg);
  end if;

  -- Keep the existing ordered order lock before deciding any financial result.
  for v_order in
    select o.id, o.status, o.vendor_id,
           coalesce(v_obligation.amount_ngwee, coalesce((
             select sum(oi.qty * oi.unit_price_ngwee)
             from public.order_items oi where oi.order_id = o.id
           ), 0) + o.delivery_fee_ngwee) as gross_ngwee
    from public.orders o
    where o.checkout_group_id = v_checkout_id or o.id = v_obligation.order_id
    order by o.id
    for update of o
  loop
    v_cancelled_order := v_cancelled_order or v_order.status = 'cancelled'
      or (v_obligation.id is not null and v_order.status <> 'placed');
    if v_order.gross_ngwee > 0 then
      v_order_count := v_order_count + 1;
      v_order_total := v_order_total + v_order.gross_ngwee;
    end if;
  end loop;

  if v_obligation.id is not null then
    perform pg_advisory_xact_lock(hashtext('order_escrow:'||v_obligation.order_id::text));
  end if;

  select * into v_accepted_receipt
  from public.payment_collection_receipts
  where payment_id = p_payment_id
  for update;

  v_prior_status := v_payment.status;
  if v_payment.status = 'success' then
    if found and
       (v_accepted_receipt.receipt_identity - 'obligation_id' - 'order_id' - 'leg') =
       (v_receipt_identity - 'obligation_id' - 'order_id' - 'leg') then
      if v_payment.rail='card' then
        update public.payment_collection_receipts set canonical_status_verified_at=now()
        where payment_id=p_payment_id;
      end if;
      return jsonb_build_object('result', 'duplicate', 'from_status', 'success');
    elsif found then
      v_late_reason := 'distinct_provider_collection';
    else
      v_late_reason := 'accepted_receipt_identity_unavailable';
    end if;
  elsif v_checkout.status in ('expired', 'abandoned') then
    v_late_reason := 'checkout_' || v_checkout.status;
  end if;

  select id into v_existing
  from public.ledger_transactions
  where checkout_group_id = v_checkout_id
    and kind in ('charge_received', 'escrow_hold')
  order by created_at, id limit 1;

  if v_late_reason is null then
    if v_prior_status = 'cancelled' then
      v_late_reason := 'payment_cancelled';
    elsif v_obligation.id is not null and exists(
      select 1 from public.order_money_gates where order_id=v_obligation.order_id and gate='refund'
    ) then
      v_late_reason := 'service_refund_in_progress';
    elsif v_obligation.leg = 'balance' and v_obligation.work_acknowledged_at is null then
      v_late_reason := 'service_balance_not_payable';
    elsif v_cancelled_order then
      v_late_reason := 'order_cancelled';
    elsif v_existing is not null then
      v_late_reason := 'checkout_already_allocated';
    elsif exists (
      select 1 from public.payments
      where checkout_group_id = v_checkout_id
        and id <> p_payment_id
        and status = 'success'
    ) then
      v_late_reason := 'sibling_payment_success';
    end if;
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

  -- Insert durable receipt identity before the paid state and all duplicate
  -- outcomes.  A transaction failure rolls it back with ledger/audit/outbox.
  insert into public.payment_collection_receipts (
    payment_id, receipt_identity, provider_reference, canonical_status_verified_at
  ) values (
    p_payment_id, v_receipt_identity, v_provider_reference,
    case when v_payment.rail='card' then now() else null end
  );
  update public.payments set status = 'success' where id = p_payment_id;
  if v_checkout.status <> 'completed' then
    update public.checkout_groups set status = 'completed' where id = v_checkout_id;
  end if;

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
             coalesce(v_obligation.amount_ngwee, coalesce((
               select sum(oi.qty * oi.unit_price_ngwee)
               from public.order_items oi where oi.order_id = o.id
             ), 0) + o.delivery_fee_ngwee) as gross_ngwee
      from public.orders o
      where o.checkout_group_id = v_checkout_id or o.id = v_obligation.order_id
      order by o.id
    loop
      if v_order.gross_ngwee <= 0 then
        continue;
      end if;
      insert into public.ledger_transactions (
        kind, idempotency_key, checkout_group_id, order_id, payment_id
      ) values (
        'escrow_hold', case when v_obligation.id is null then 'escrow-hold-' || v_order.id
          else 'service-funding-' || v_obligation.id end, v_checkout_id,
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

revoke all on function public.apply_prepaid_collection_success(uuid, uuid, text, jsonb)
  from public, anon, authenticated;
grant execute on function public.apply_prepaid_collection_success(uuid, uuid, text, jsonb)
  to service_role;
