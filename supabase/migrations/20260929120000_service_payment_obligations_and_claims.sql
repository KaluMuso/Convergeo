-- Allocated by #716/5885685575. Source review and shared application are separate approvals.
-- Additive from 8f78448e. No receipt backfill: historical success is not provider proof.
-- Rollback: retain evidence tables; revert callers only after stopping new initiation.
create table public.service_payment_obligations (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id),
  job_id uuid not null references public.jobs(id),
  checkout_group_id uuid not null unique references public.checkout_groups(id),
  leg text not null check (leg in ('deposit', 'balance')),
  amount_ngwee bigint not null check (amount_ngwee > 0),
  work_acknowledged_at timestamptz,
  created_at timestamptz not null default now(),
  unique(order_id, leg)
);
alter table public.service_payment_obligations enable row level security;
alter table public.service_payment_obligations force row level security;
revoke all on public.service_payment_obligations from public, anon, authenticated;
grant select, insert, update on public.service_payment_obligations to service_role;

-- Historical card success is not canonical-query evidence. Do not backfill this timestamp.
alter table public.payment_collection_receipts
  add column canonical_status_verified_at timestamptz;

-- Immutable accepted financial identity; only work acknowledgement can change.
create function public.guard_service_obligation_identity() returns trigger
language plpgsql set search_path = '' as $$
begin
  if (new.id, new.order_id, new.job_id, new.checkout_group_id, new.leg, new.amount_ngwee)
     is distinct from
     (old.id, old.order_id, old.job_id, old.checkout_group_id, old.leg, old.amount_ngwee) then
    raise exception 'service obligation identity is immutable';
  end if;
  return new;
end; $$;
create trigger service_obligation_identity before update on public.service_payment_obligations
for each row execute function public.guard_service_obligation_identity();
revoke all on function public.guard_service_obligation_identity() from public, anon, authenticated;

-- A UUID link alone is not authority to consume somebody else's money.
create function public.service_obligation_is_valid(p_obligation uuid)
returns boolean language sql stable set search_path='' as $$
 select exists (
   select 1 from public.service_payment_obligations ob
   join public.orders o on o.id=ob.order_id
   join public.jobs j on j.id=ob.job_id and j.customer_id=o.customer_id
   join public.checkout_groups c on c.id=ob.checkout_group_id
     and c.customer_id=o.customer_id and c.total_ngwee=ob.amount_ngwee
   where ob.id=p_obligation and not o.cod
     and ((ob.leg='deposit' and c.id=o.checkout_group_id)
       or (ob.leg='balance' and c.id<>o.checkout_group_id))
     and exists (
       select 1 from public.order_items oi
       join public.order_item_services os on os.order_item_id=oi.id and os.job_id=j.id
       join public.job_quotes q on q.id=os.quote_id and q.job_id=j.id
         and q.provider_vendor_id=o.vendor_id and q.status='accepted'
       where oi.order_id=o.id and oi.item_kind='service_deposit'
     )
 );
$$;

create function public.order_payment_checkouts(p_order uuid)
returns table(checkout_group_id uuid) language sql stable set search_path='' as $$
 select o.checkout_group_id from public.orders o
 join public.checkout_groups c on c.id=o.checkout_group_id and c.customer_id=o.customer_id
 where o.id=p_order
 union
 select ob.checkout_group_id from public.service_payment_obligations ob
 where ob.order_id=p_order and public.service_obligation_is_valid(ob.id);
$$;

-- Original checkout is a stable shared anchor, including during metadata adoption.
-- All row-locking writers acquire ALL scoped checkouts first, then ALL payments.
-- Order row(s), then order_escrow advisory gates, follow at the caller.
create function public.lock_payment_checkout_scope(p_checkout uuid)
returns void language plpgsql set search_path='' as $$
declare ids uuid[];
begin
 select array_agg(distinct s.checkout_group_id order by s.checkout_group_id) into ids
 from (
   select p_checkout as checkout_group_id
   union
   select scope.checkout_group_id from public.orders o
   cross join lateral public.order_payment_checkouts(o.id) scope
   where o.checkout_group_id=p_checkout or exists(
     select 1 from public.service_payment_obligations ob
     where ob.order_id=o.id and ob.checkout_group_id=p_checkout
       and public.service_obligation_is_valid(ob.id))
 ) s;
 perform 1 from public.checkout_groups where id=any(ids) order by id for update;
 perform 1 from public.payments where checkout_group_id=any(ids)
   order by checkout_group_id,id for update;
end; $$;

create function public.order_has_collected_money(p_order uuid)
returns boolean language sql stable set search_path='' as $$
 select exists (
   select 1 from public.orders o
   cross join lateral public.order_payment_checkouts(o.id) scope
   join public.payments p on p.checkout_group_id=scope.checkout_group_id
   where o.id=p_order and not o.cod and (
     -- Preserve the conservative original-checkout legacy/product/event guard.
     (p.checkout_group_id=o.checkout_group_id and p.status='success')
     or exists (
       select 1 from public.payment_collection_receipts r where r.payment_id=p.id
         and r.receipt_identity->>'provider'=p.provider
         and r.receipt_identity->>'merchant_reference'=p.lenco_reference
         and r.receipt_identity->>'currency'='ZMW'
         and r.receipt_identity->>'amount_ngwee'=p.amount_ngwee::text
     )
     -- Late/ambiguous money needs resolution even when it cannot fund completion.
     or exists(select 1 from public.payment_collection_exceptions e where e.payment_id=p.id)
   )
 );
$$;
revoke all on function public.service_obligation_is_valid(uuid),
 public.order_payment_checkouts(uuid), public.lock_payment_checkout_scope(uuid),
 public.order_has_collected_money(uuid) from public,anon,authenticated;
grant execute on function public.service_obligation_is_valid(uuid),
 public.order_payment_checkouts(uuid), public.lock_payment_checkout_scope(uuid),
 public.order_has_collected_money(uuid) to service_role;

-- Q1/Q2: age, funding and old system-generated timestamps are not buyer consent.
create function public.service_buyer_acknowledged(p_job_id uuid)
returns boolean language sql stable set search_path='' as $$
 select exists (
   select 1 from public.jobs j join public.audit_log a
     on a.entity_type='job' and a.entity_id=j.id
   where j.id=p_job_id and a.action='job.work_acknowledged'
     and a.actor=j.customer_id
     and coalesce(a.after->>'system','false')='false'
 ) and exists (
   select 1 from public.audit_log p where p.entity_type='job'
     and p.entity_id=p_job_id and p.action='job.provider_completed'
 );
$$;
revoke all on function public.service_buyer_acknowledged(uuid) from public,anon,authenticated;
grant execute on function public.service_buyer_acknowledged(uuid) to service_role;

-- Provider initiation and widget resumption have the same atomic authority boundary.
-- The API checks environment gates immediately before this service-only RPC.
create function public.claim_payable_payment(
 p_checkout_id uuid, p_actor_id uuid, p_payment_id uuid, p_rail text,
 p_reference text, p_raw jsonb, p_resume boolean default false
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
 c public.checkout_groups%rowtype; o record; attempt public.payments%rowtype;
 obligation public.service_payment_obligations%rowtype;
begin
 perform public.lock_payment_checkout_scope(p_checkout_id);
 select * into c from public.checkout_groups where id=p_checkout_id for update;
 if not found or c.customer_id is distinct from p_actor_id then
   return jsonb_build_object('result','not_owned');
 end if;
 if c.status <> 'pending' or c.total_ngwee <= 0 or p_rail not in ('mtn','airtel','card') then
   return jsonb_build_object('result','not_payable');
 end if;
 select * into obligation from public.service_payment_obligations where checkout_group_id=c.id;
 if obligation.id is not null and not public.service_obligation_is_valid(obligation.id) then
   return jsonb_build_object('result','invalid_obligation');
 end if;
 if not exists(select 1 from public.orders where checkout_group_id=c.id or id=obligation.order_id) then
   return jsonb_build_object('result','order_required');
 end if;
 -- Match cancellation/settlement lock ordering: checkout -> payments -> orders.
 perform 1 from public.payments where checkout_group_id=c.id order by id for update;
 for o in select * from public.orders
   where checkout_group_id=c.id or id=obligation.order_id order by id for update
 loop
   if o.customer_id <> p_actor_id or o.cod or o.status <> 'placed' then
     return jsonb_build_object('result','order_not_payable');
   end if;
 end loop;
 if obligation.id is not null then
   perform pg_advisory_xact_lock(hashtext('order_escrow:'||obligation.order_id::text));
   if exists(select 1 from public.order_money_gates where order_id=obligation.order_id)
      or exists(select 1 from public.refunds where order_id=obligation.order_id
                and status in ('pending','processing','awaiting_payout','needs_destination','manual_review','completed'))
      or exists(select 1 from public.disputes where order_id=obligation.order_id
                and status in ('open','vendor_responded','under_review')) then
     return jsonb_build_object('result','service_funds_held');
   end if;
 end if;
 if obligation.id is not null and (
   obligation.amount_ngwee <> c.total_ngwee or
   (obligation.leg='balance' and (obligation.work_acknowledged_at is null
     or not public.service_buyer_acknowledged(obligation.job_id)))
 ) then return jsonb_build_object('result','obligation_not_payable'); end if;
 if exists(select 1 from public.payments p where p.checkout_group_id=c.id and (
     p.status='success' or
     (p.id<>p_payment_id and p.status<>'failed') or
     (p.id<>p_payment_id and coalesce(p.raw->>'terminal_provider_failure','false')<>'true')
 )) then return jsonb_build_object('result','unresolved_attempt'); end if;
 if exists(select 1 from public.payment_collection_exceptions e join public.payments p on p.id=e.payment_id
           where p.checkout_group_id=c.id) then
   return jsonb_build_object('result','collection_exception');
 end if;
 if p_resume then
   select * into attempt from public.payments where id=p_payment_id;
   if not found or attempt.checkout_group_id<>c.id or attempt.rail<>'card'
      or attempt.lenco_reference<>p_reference or attempt.status not in ('initiated','ussd_pushed','pay_offline') then
     return jsonb_build_object('result','not_resumable');
   end if;
 else
   insert into public.payments(id,checkout_group_id,provider,rail,lenco_reference,amount_ngwee,status,raw)
   values(p_payment_id,c.id,'lenco',p_rail,p_reference,c.total_ngwee,'initiated',coalesce(p_raw,'{}'));
 end if;
 return jsonb_build_object('result','claimed','payment_id',p_payment_id,
                          'amount_ngwee',c.total_ngwee,'obligation_id',obligation.id);
end; $$;
revoke all on function public.claim_payable_payment(uuid,uuid,uuid,text,text,jsonb,boolean)
 from public,anon,authenticated;
grant execute on function public.claim_payable_payment(uuid,uuid,uuid,text,text,jsonb,boolean) to service_role;

create function public.create_service_payment_obligations(
 p_order_id uuid, p_job_id uuid, p_customer_id uuid, p_total bigint, p_deposit bigint
) returns void language plpgsql security definer set search_path='' as $$
declare o public.orders%rowtype; balance_checkout uuid;
begin
 perform public.lock_payment_checkout_scope(
   (select checkout_group_id from public.orders where id=p_order_id));
 select * into strict o from public.orders where id=p_order_id for update;
 if o.customer_id<>p_customer_id or o.status<>'placed' or p_total<=0
    or p_deposit<=0 or p_deposit>p_total
    or (o.commission_snapshot->'lines'->0->>'line_total_ngwee')::bigint is distinct from p_total
    or not exists(select 1 from public.order_items oi
      join public.order_item_services os on os.order_item_id=oi.id and os.job_id=p_job_id
      join public.jobs j on j.id=os.job_id and j.customer_id=p_customer_id
      join public.job_quotes q on q.id=os.quote_id and q.job_id=j.id
        and q.status='accepted' and q.provider_vendor_id=o.vendor_id
      where oi.order_id=o.id and oi.item_kind='service_deposit'
        and oi.qty=1 and oi.unit_price_ngwee=p_deposit) then
   raise exception 'invalid service obligation';
 end if;
 insert into public.service_payment_obligations(order_id,job_id,checkout_group_id,leg,amount_ngwee)
 values(o.id,p_job_id,o.checkout_group_id,'deposit',p_deposit);
 if p_total>p_deposit then
   insert into public.checkout_groups(customer_id,idempotency_key,subtotal_ngwee,delivery_fee_ngwee,total_ngwee,status)
   values(p_customer_id,'service-balance-'||o.id,p_total-p_deposit,0,p_total-p_deposit,'pending')
   returning id into balance_checkout;
   insert into public.service_payment_obligations(order_id,job_id,checkout_group_id,leg,amount_ngwee)
   values(o.id,p_job_id,balance_checkout,'balance',p_total-p_deposit);
 end if;
end; $$;
revoke all on function public.create_service_payment_obligations(uuid,uuid,uuid,bigint,bigint)
 from public,anon,authenticated;
grant execute on function public.create_service_payment_obligations(uuid,uuid,uuid,bigint,bigint)
 to service_role;

create function public.record_collection_failure(p_payment_id uuid,p_observation jsonb)
returns void language plpgsql security definer set search_path='' as $$
declare p public.payments%rowtype; cg uuid;
begin
 select checkout_group_id into cg from public.payments where id=p_payment_id;
 perform public.lock_payment_checkout_scope(cg);
 perform 1 from public.checkout_groups where id=cg for update;
 select * into strict p from public.payments where id=p_payment_id for update;
 if p.provider<>'lenco' or p_observation->>'reference' is distinct from p.lenco_reference
    or p_observation->>'currency' is distinct from 'ZMW'
    or (p_observation->>'amount_ngwee')::bigint is distinct from p.amount_ngwee
    or p_observation->>'provider_outcome' is distinct from 'failed'
    or (nullif(p.raw->>'provider_reference','') is not null and
        p.raw->>'provider_reference' is distinct from p_observation->>'provider_reference') then
   raise exception 'terminal collection identity mismatch';
 end if;
 update public.payments set raw=coalesce(raw,'{}') || jsonb_build_object(
   'terminal_provider_failure',true,'terminal_observation',p_observation)
 where id=p.id and status<>'success';
end; $$;
revoke all on function public.record_collection_failure(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.record_collection_failure(uuid,jsonb) to service_role;
