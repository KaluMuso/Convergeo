-- #716/5918974162 reserved 203100. Forward correction; published 120003 is immutable.
-- Retry metadata adoption with scoped locks and explicit cross-order ambiguity holds.
-- No receipt/ledger/status backfill, grants, function signatures or commercial changes.
-- Rollback: retain adopted metadata and holds; do not delete money/evidence.
-- Ambiguities remain durably held in audit_log, never guessed or silently adopted.
do $$
declare o public.orders%rowtype; spine record; total bigint; reason text;
begin
 for o in select * from public.orders orders
          where status='placed' and exists(select 1 from public.order_items
            where order_id=orders.id and item_kind='service_deposit')
          and not exists(select 1 from public.service_payment_obligations where order_id=orders.id)
          order by id
 loop
   -- Same checkout/payment -> order lock order used by financial writers.
   perform public.lock_payment_checkout_scope(o.checkout_group_id);
   select * into o from public.orders where id=o.id for update;
   if not found or o.status<>'placed' or exists(
      select 1 from public.service_payment_obligations where order_id=o.id) then
     continue;
   end if;
   reason:=null;
   select count(*) as links, (array_agg(os.job_id))[1] as job_id,
          (array_agg(oi.unit_price_ngwee))[1] as deposit
   into spine
   from public.order_items oi
   join public.order_item_services os on os.order_item_id=oi.id
   join public.jobs j on j.id=os.job_id and j.status='accepted' and j.customer_id=o.customer_id
   join public.job_quotes q on q.id=os.quote_id and q.job_id=j.id
     and q.status='accepted' and q.provider_vendor_id=o.vendor_id
   join public.checkout_groups c on c.id=o.checkout_group_id and c.customer_id=o.customer_id
     and c.total_ngwee=oi.unit_price_ngwee
   where oi.order_id=o.id and oi.item_kind='service_deposit' and oi.qty=1;
   if exists(select 1 from public.service_payment_obligations
             where checkout_group_id=o.checkout_group_id and order_id<>o.id) then
     reason:='checkout_linked_to_other_obligation';
   elsif exists(select 1 from public.orders other_order
                where other_order.checkout_group_id=o.checkout_group_id and other_order.id<>o.id) then
     reason:='checkout_shared_by_orders';
   elsif exists(select 1 from public.checkout_groups
                where idempotency_key='service-balance-'||o.id::text) then
     -- Never reuse or overwrite an orphaned/foreign deterministic balance checkout.
     reason:='balance_checkout_already_exists';
   elsif spine.links<>1 or o.cod or
      (select count(*) from public.order_items where order_id=o.id and item_kind='service_deposit')<>1 then
     reason:='ambiguous_service_spine';
   elsif (select count(distinct oi.order_id) from public.order_item_services os
          join public.order_items oi on oi.id=os.order_item_id
          where os.job_id=spine.job_id and oi.item_kind='service_deposit')<>1 then
     reason:='multiple_orders_for_job';
   elsif o.commission_snapshot->>'basis' is distinct from 'total_job_value'
      or jsonb_typeof(o.commission_snapshot->'lines') is distinct from 'array' then
     reason:='invalid_snapshot';
   elsif jsonb_array_length(o.commission_snapshot->'lines')<>1
      or coalesce(o.commission_snapshot->'lines'->0->>'line_total_ngwee','') !~ '^[0-9]{1,18}$' then
     reason:='invalid_snapshot_total';
   else
     total:=(o.commission_snapshot->'lines'->0->>'line_total_ngwee')::bigint;
     if spine.deposit<=0 or total<spine.deposit then reason:='invalid_obligation_amounts'; end if;
   end if;
   if reason is null then
     perform public.create_service_payment_obligations(o.id,spine.job_id,o.customer_id,total,spine.deposit);
   elsif not exists(select 1 from public.audit_log
                    where entity_type='order' and entity_id=o.id
                      and action='service.obligation_adoption_held') then
     insert into public.audit_log(actor,action,entity_type,entity_id,after)
     values(null,'service.obligation_adoption_held','order',o.id,jsonb_build_object('reason',reason));
   end if;
 end loop;
end; $$;
