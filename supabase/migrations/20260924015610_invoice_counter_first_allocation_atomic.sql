-- Serialize creation and allocation on the series' unique key, including the
-- first two concurrent callers. The increment rolls back with its transaction.
create or replace function public.next_invoice_no(p_series text)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  allocated bigint;
begin
  insert into public.invoice_counters as counter (series, next_no)
  values (p_series, 2)
  on conflict (series) do update
    set next_no = counter.next_no + 1
  returning next_no - 1 into allocated;
  return allocated;
end;
$$;

revoke execute on function public.next_invoice_no(text) from public, anon, authenticated;
grant execute on function public.next_invoice_no(text) to service_role;

comment on function public.next_invoice_no(text) is
  'Allocates invoice numbers atomically per series, including first use; transactional rollback preserves the counter.';
