-- FIX-B: at-most-one active/settled refund per order — DB backstop against refund
-- double-execution (double payout + double escrow drain). Additive + reversible.
-- Down (manual): drop index public.refunds_order_id_active_uniq;

-- Fail loudly if existing data already violates the invariant, so the index build
-- cannot silently succeed against a table that already carries duplicate refunds.
do $$
declare
  offending int;
begin
  select count(*)
  into offending
  from (
    select order_id
    from public.refunds
    where status in ('pending', 'processing', 'completed')
    group by order_id
    having count(*) > 1
  ) dups;

  if offending > 0 then
    raise exception
      'cannot add refunds_order_id_active_uniq: % order(s) already have multiple active/settled refunds',
      offending;
  end if;
end $$;

create unique index refunds_order_id_active_uniq
  on public.refunds (order_id)
  where status in ('pending', 'processing', 'completed');

comment on index public.refunds_order_id_active_uniq is
  'At-most-one active/settled (pending|processing|completed) refund per order; DB backstop against refund double-execution.';
