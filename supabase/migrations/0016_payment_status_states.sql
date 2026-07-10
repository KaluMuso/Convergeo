-- M08-P04: Widen payments.status CHECK for USSD-push lifecycle states.
-- initiated = created; additive drop + re-add (reversible).

alter table public.payments
  drop constraint if exists payments_status_check;

alter table public.payments
  add constraint payments_status_check
  check (status in (
    'initiated',
    'ussd_pushed',
    'pay_offline',
    'success',
    'failed',
    'expired',
    'cancelled'
  ));

comment on column public.payments.status is
  'Payment lifecycle: initiated (created) → ussd_pushed → pay_offline → success|failed|expired|cancelled.';
