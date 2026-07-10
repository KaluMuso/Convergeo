-- M09-P01: Enrich audit_orders_status_change() with actor + note from transaction-local GUCs.
-- Reversible: restore the 0005_orders.sql function body (auth.uid() only, no note column).

create or replace function public.audit_orders_status_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  audit_actor uuid;
  audit_note text;
begin
  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    audit_actor := coalesce(
      nullif(current_setting('app.order_actor', true), '')::uuid,
      auth.uid()
    );
    audit_note := nullif(current_setting('app.order_note', true), '');

    insert into public.order_events (order_id, actor, from_status, to_status, note)
    values (new.id, audit_actor, old.status, new.status, audit_note);
  end if;

  return new;
end;
$$;

comment on function public.audit_orders_status_change() is
  'Append-only order status audit. Service-role transitions set app.order_actor and app.order_note via set_config before UPDATE.';
