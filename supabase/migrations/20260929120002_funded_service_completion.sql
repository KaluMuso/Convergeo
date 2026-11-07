-- Forward migration. Single transaction for acknowledgement and (only when funded) release.
-- No new commission/deposit/cancellation/release-delay terms. Uses accepted snapshot.
-- Q1/Q2: automatic retries may finish acknowledged funding, never manufacture acknowledgement.
create function public.confirm_funded_service(
 p_job_id uuid, p_actor_id uuid, p_system boolean default false
) returns jsonb language plpgsql security definer set search_path='' as $$
declare
 o public.orders%rowtype; j public.jobs%rowtype; ob record;
 total bigint; funded bigint; balance_due bigint; commission bigint; net bigint;
 snap jsonb; rate bigint; escrow_balance bigint; escrow uuid; revenue uuid; payable uuid;
 txn uuid; was_ack boolean; balance_created boolean := false;
begin
 select * into strict j from public.jobs where id=p_job_id;
 if p_system is null or p_actor_id is null then raise exception 'service actor required'; end if;
 if not p_system and j.customer_id<>p_actor_id then raise exception 'service owner required'; end if;
 select order_id into o.id from public.service_payment_obligations
 where job_id=j.id and leg='deposit';
 if o.id is null then raise exception 'service obligation migration required'; end if;
 -- Lock all checkout rows before any payment row; identical to claim/cancellation.
 perform public.lock_payment_checkout_scope(
   (select checkout_group_id from public.orders where id=o.id));
 select * into strict o from public.orders where id=o.id for update;
 perform pg_advisory_xact_lock(hashtext('order_escrow:'||o.id::text));
 if exists(select 1 from public.service_payment_obligations
           where order_id=o.id and not public.service_obligation_is_valid(id)) then
   raise exception 'invalid service obligation linkage';
 end if;
 if o.status='completed' then
   return jsonb_build_object('status','completed','already_confirmed',true,'order_id',o.id,
      'balance_ngwee',0,'released',false,'net_ngwee',0);
 end if;
 if o.status<>'placed' or j.status<>'accepted' then raise exception 'service not completable'; end if;
 if not exists(select 1 from public.audit_log where entity_type='job' and entity_id=j.id
               and action='job.provider_completed') then raise exception 'provider completion required'; end if;
 if exists(select 1 from public.disputes where order_id=o.id and status in ('open','vendor_responded','under_review'))
    or exists(select 1 from public.refunds where order_id=o.id and status not in ('rejected','cancelled','failed'))
    or exists(select 1 from public.order_money_gates where order_id=o.id and gate='refund')
    or exists(select 1 from public.ledger_transactions where order_id=o.id and kind in ('refund_lane1','refund_lane2','clawback')) then
   raise exception 'service funds held';
 end if;
 select public.service_buyer_acknowledged(j.id) into was_ack;
 if not was_ack then
   -- This is deliberately before acknowledgement, invoicing, commission or release.
   -- Keep historical system audit rows unchanged; they are not upgraded to consent.
   if p_system then raise exception 'buyer acknowledgement required'; end if;
   insert into public.audit_log(actor,action,entity_type,entity_id,after)
   values(p_actor_id,'job.work_acknowledged','job',j.id,
          jsonb_build_object('system',false));
 end if;
 update public.service_payment_obligations set work_acknowledged_at=coalesce(work_acknowledged_at,now())
 where order_id=o.id;
 -- Invoice the balance once, without posting cash or marking any receipt successful.
 for ob in select * from public.service_payment_obligations where order_id=o.id and leg='balance' loop
   if not exists(select 1 from public.order_items where order_id=o.id and item_kind='service_balance') then
     insert into public.order_items(order_id,item_kind,qty,unit_price_ngwee)
     values(o.id,'service_balance',1,ob.amount_ngwee);
     balance_created:=true;
   end if;
 end loop;
 snap:=o.commission_snapshot;
 if snap->>'basis'<>'total_job_value' or jsonb_array_length(snap->'lines')<>1 then
   raise exception 'invalid service snapshot'; end if;
 total:=(snap->'lines'->0->>'line_total_ngwee')::bigint;
 rate:=(snap->'lines'->0->>'rate_bps')::bigint;
 if total<=0 or rate<0 or rate>10000 or total is null or rate is null
    or coalesce((snap->'lines'->0->>'wholesale')::boolean,false) then
   raise exception 'invalid service snapshot arithmetic'; end if;
 if (select sum(amount_ngwee) from public.service_payment_obligations where order_id=o.id)<>total then
   raise exception 'obligation snapshot mismatch'; end if;
 select coalesce(sum(ob.amount_ngwee),0) into funded
 from public.service_payment_obligations ob
 where ob.order_id=o.id and exists(
   select 1 from public.payments p join public.payment_collection_receipts r on r.payment_id=p.id
   join public.ledger_transactions t on t.payment_id=p.id and t.order_id=ob.order_id and t.kind='escrow_hold'
   where p.checkout_group_id=ob.checkout_group_id and p.status='success'
     and p.amount_ngwee=ob.amount_ngwee
     and r.receipt_identity->>'merchant_reference'=p.lenco_reference
     and r.receipt_identity->>'provider'=p.provider
     and (r.receipt_identity->>'amount_ngwee')::bigint=ob.amount_ngwee
     and r.receipt_identity->>'currency'='ZMW'
     and (p.rail<>'card' or r.canonical_status_verified_at is not null)
 );
 balance_due:=total-funded;
 if balance_due>0 then
   return jsonb_build_object('status','awaiting_payment','order_id',o.id,'already_confirmed',false,
      'balance_ngwee',balance_due,'balance_created',balance_created,'released',false,'net_ngwee',0);
 end if;
 if funded<>total then raise exception 'service funding mismatch'; end if;
 -- Fail closed on legacy partial capture/release; do not silently recapture or infer receipts.
 if exists(select 1 from public.ledger_transactions where order_id=o.id
           and kind in ('commission_capture','release_to_vendor')) then
   raise exception 'legacy service financial state requires review'; end if;
 select id into strict escrow from public.ledger_accounts where kind='escrow' and vendor_id is null;
 select -coalesce(sum(lp.amount_ngwee),0) into escrow_balance
 from public.ledger_transactions t join public.ledger_postings lp on lp.transaction_id=t.id
 where t.order_id=o.id and lp.account_id=escrow;
 if escrow_balance<>total then raise exception 'service escrow differs from validated funding'; end if;
 insert into public.order_money_gates(order_id,gate) values(o.id,'release') on conflict(order_id) do nothing;
 commission:=floor(total::numeric*rate/10000)::bigint;
 net:=total-commission;
 if commission>0 then
   select id into strict revenue from public.ledger_accounts where kind='commission_revenue' and vendor_id is null;
   insert into public.ledger_transactions(kind,idempotency_key,order_id)
   values('commission_capture','release-'||o.id||'-commission-0',o.id) returning id into txn;
   insert into public.ledger_postings(transaction_id,account_id,amount_ngwee)
   values(txn,escrow,commission),(txn,revenue,-commission);
 end if;
 if net>0 then
   insert into public.ledger_accounts(kind,vendor_id) values('vendor_payable',o.vendor_id) on conflict do nothing;
   select id into strict payable from public.ledger_accounts where kind='vendor_payable' and vendor_id=o.vendor_id;
   insert into public.ledger_transactions(kind,idempotency_key,order_id)
   values('release_to_vendor','release-'||o.id,o.id) returning id into txn;
   insert into public.ledger_postings(transaction_id,account_id,amount_ngwee)
   values(txn,escrow,net),(txn,payable,-net);
 end if;
 perform set_config('app.order_actor',p_actor_id::text,true);
 perform set_config('app.order_note','Service completed from validated obligations',true);
 update public.orders set status='completed' where id=o.id;
 update public.jobs set status='completed' where id=j.id;
 insert into public.audit_log(actor,action,entity_type,entity_id,after)
 values(case when p_system then null else p_actor_id end,'job.confirmed','job',j.id,
        jsonb_build_object('status','completed','funded_ngwee',funded));
 return jsonb_build_object('status','completed','order_id',o.id,'already_confirmed',false,
     'balance_ngwee',0,'balance_created',balance_created,'released',true,'net_ngwee',net);
end; $$;
revoke all on function public.confirm_funded_service(uuid,uuid,boolean) from public,anon,authenticated;
grant execute on function public.confirm_funded_service(uuid,uuid,boolean) to service_role;
