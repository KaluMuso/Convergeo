-- At-most-one successful payment per checkout group — DB backstop against
-- retry + late-success double settlement (two payments.status=success for one
-- checkout). Settlement is already idempotent per checkout in the API; this
-- index prevents a second SUCCESS row if the app path is bypassed.
-- Additive + reversible.
-- Down (manual): drop index public.payments_checkout_group_success_uniq;

do $$
declare
  offending int;
begin
  select count(*)
  into offending
  from (
    select checkout_group_id
    from public.payments
    where status = 'success'
    group by checkout_group_id
    having count(*) > 1
  ) dups;

  if offending > 0 then
    raise exception
      'cannot add payments_checkout_group_success_uniq: % checkout_group(s) already have multiple success payments',
      offending;
  end if;
end $$;

create unique index payments_checkout_group_success_uniq
  on public.payments (checkout_group_id)
  where status = 'success';

comment on index public.payments_checkout_group_success_uniq is
  'At-most-one successful payment per checkout_group_id; DB backstop against retry + late-success double settlement.';
