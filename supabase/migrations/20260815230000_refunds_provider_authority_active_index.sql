-- REFUND-PROVIDER-AUTHORITY: in-flight payout states occupy source_key until
-- provider confirms MoMo delivery (completed) or terminal failure.

drop index if exists public.refunds_source_key_active_uniq;

create unique index refunds_source_key_active_uniq
  on public.refunds (source_key)
  where status in (
    'pending',
    'processing',
    'awaiting_payout',
    'needs_destination',
    'manual_review',
    'completed'
  );

comment on index public.refunds_source_key_active_uniq is
  'At-most-one active/in-flight/settled refund per source_key; failed rows may retry under a new key.';
