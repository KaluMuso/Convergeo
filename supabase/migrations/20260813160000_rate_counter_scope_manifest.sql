-- Canonicalize sandbox rehearsal 20260813072110 (rate-counter scope manifest).
-- Declares every API rate-limit scope in a private manifest and validates
-- bump_rate_counter against it. Safe on fresh replay and when rehearsal DDL
-- is already present.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table if not exists private.rate_counter_scope_manifest (
  scope text primary key check (scope ~ '^[a-z0-9_]+$')
);

insert into private.rate_counter_scope_manifest (scope) values
  ('admin_support_actor'),
  ('admin_support_ip'),
  ('analytics_collect_ip'),
  ('ask_ip'),
  ('auth_ip'),
  ('auth_number'),
  ('beta_feedback_ip'),
  ('beta_redeem_ip'),
  ('clip_comment'),
  ('clip_like'),
  ('clip_link'),
  ('clip_report'),
  ('clip_view'),
  ('discovery_read_ip'),
  ('enquiries_ip_close'),
  ('enquiries_ip_create'),
  ('enquiries_ip_message'),
  ('enquiries_user_close'),
  ('enquiries_user_create'),
  ('enquiries_user_message'),
  ('internal_cron'),
  ('intake_link_mint'),
  ('intake_link_redeem'),
  ('invoice_download'),
  ('job_complete_ip'),
  ('job_complete_user'),
  ('job_confirm_ip'),
  ('job_confirm_user'),
  ('jobs_ip'),
  ('jobs_user'),
  ('listing_report_ip'),
  ('listing_report_user'),
  ('otp_ip'),
  ('otp_number'),
  ('quotes_ip'),
  ('quotes_user'),
  ('returns_ip'),
  ('returns_user'),
  ('reviews_ip_reply'),
  ('reviews_ip_submit'),
  ('reviews_user_reply'),
  ('reviews_user_submit'),
  ('rfq_accept_ip'),
  ('rfq_accept_user'),
  ('rfq_ip_create'),
  ('rfq_ip_message'),
  ('rfq_ip_quote'),
  ('rfq_user_create'),
  ('rfq_user_message'),
  ('rfq_user_quote'),
  ('search_geo_ip'),
  ('service_book_ip'),
  ('service_book_user'),
  ('service_reviews_ip_reply'),
  ('service_reviews_ip_submit'),
  ('service_reviews_user_reply'),
  ('service_reviews_user_submit'),
  ('telemetry_frontend_errors_ip'),
  ('telemetry_views_ip'),
  ('ticket_transfer_cancel_ip'),
  ('ticket_transfer_cancel_user'),
  ('ticket_transfer_claim_ip'),
  ('ticket_transfer_claim_user'),
  ('ticket_transfer_initiate_ip'),
  ('ticket_transfer_initiate_user'),
  ('ticket_verify_ip'),
  ('ticket_verify_user'),
  ('vendor_collections_write'),
  ('vendor_follow'),
  ('vendor_licence_apply'),
  ('vendor_payout_method_change'),
  ('vendor_payouts_read'),
  ('webhook_cloudinary'),
  ('webhook_waha_intake'),
  ('write_admin'),
  ('write_payment'),
  ('write_sensitive'),
  ('write_standard')
on conflict (scope) do nothing;

revoke all on table private.rate_counter_scope_manifest from public, anon, authenticated;

alter table public.rate_counters drop constraint if exists rate_counters_scope_check;

alter table public.rate_counters add constraint rate_counters_scope_check check (
  scope in (
    'admin_support_actor', 'admin_support_ip', 'analytics_collect_ip', 'ask_ip',
    'auth_ip', 'auth_number', 'beta_feedback_ip', 'beta_redeem_ip', 'clip_comment',
    'clip_like', 'clip_link', 'clip_report', 'clip_view', 'discovery_read_ip',
    'enquiries_ip_close', 'enquiries_ip_create', 'enquiries_ip_message',
    'enquiries_user_close', 'enquiries_user_create', 'enquiries_user_message',
    'internal_cron', 'intake_link_mint', 'intake_link_redeem', 'invoice_download',
    'job_complete_ip', 'job_complete_user', 'job_confirm_ip', 'job_confirm_user',
    'jobs_ip', 'jobs_user', 'listing_report_ip', 'listing_report_user', 'otp_ip',
    'otp_number', 'quotes_ip', 'quotes_user', 'returns_ip', 'returns_user',
    'reviews_ip_reply', 'reviews_ip_submit', 'reviews_user_reply',
    'reviews_user_submit', 'rfq_accept_ip', 'rfq_accept_user', 'rfq_ip_create',
    'rfq_ip_message', 'rfq_ip_quote', 'rfq_user_create', 'rfq_user_message',
    'rfq_user_quote', 'search_geo_ip', 'service_book_ip', 'service_book_user',
    'service_reviews_ip_reply', 'service_reviews_ip_submit',
    'service_reviews_user_reply', 'service_reviews_user_submit',
    'telemetry_frontend_errors_ip', 'telemetry_views_ip',
    'ticket_transfer_cancel_ip', 'ticket_transfer_cancel_user',
    'ticket_transfer_claim_ip', 'ticket_transfer_claim_user',
    'ticket_transfer_initiate_ip', 'ticket_transfer_initiate_user',
    'ticket_verify_ip', 'ticket_verify_user', 'vendor_collections_write',
    'vendor_follow', 'vendor_licence_apply', 'vendor_payout_method_change',
    'vendor_payouts_read', 'webhook_cloudinary', 'webhook_waha_intake',
    'write_admin', 'write_payment', 'write_sensitive', 'write_standard'
  )
);

create or replace function public.bump_rate_counter(
  p_scope text,
  p_key text,
  p_window interval,
  p_limit integer
)
returns table (allowed boolean, retry_after_seconds integer)
language plpgsql
security definer
set search_path = public, private, extensions
as $$
declare
  v_window_start timestamptz;
  v_expires_at timestamptz;
  v_count integer;
  v_existing_count integer;
  v_existing_expires timestamptz;
  v_window_seconds double precision;
begin
  if not exists (
    select 1 from private.rate_counter_scope_manifest where scope = p_scope
  ) then
    raise exception 'invalid rate counter scope: %', p_scope;
  end if;

  if p_limit <= 0 then
    raise exception 'p_limit must be positive';
  end if;

  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'bump_rate_counter requires service role';
  end if;

  v_window_seconds := extract(epoch from p_window);
  if v_window_seconds <= 0 then
    raise exception 'p_window must be positive';
  end if;

  v_window_start := to_timestamp(
    floor(extract(epoch from now()) / v_window_seconds) * v_window_seconds
  );
  v_expires_at := v_window_start + p_window;

  insert into public.rate_counters as rc (scope, key, window_start, count, expires_at)
  values (p_scope, p_key, v_window_start, 1, v_expires_at)
  on conflict (scope, key, window_start)
  do update
    set count = rc.count + 1
  where rc.count < p_limit
  returning rc.count, rc.expires_at
  into v_count, v_expires_at;

  if found then
    allowed := true;
    retry_after_seconds := greatest(
      0,
      ceil(extract(epoch from (v_expires_at - now())))::integer
    );
    return next;
    return;
  end if;

  select rc.count, rc.expires_at
  into v_existing_count, v_existing_expires
  from public.rate_counters rc
  where rc.scope = p_scope
    and rc.key = p_key
    and rc.window_start = v_window_start
  for update;

  if v_existing_count is null then
    insert into public.rate_counters (scope, key, window_start, count, expires_at)
    values (p_scope, p_key, v_window_start, 1, v_expires_at)
    on conflict (scope, key, window_start) do nothing;

    select rc.count, rc.expires_at
    into v_existing_count, v_existing_expires
    from public.rate_counters rc
    where rc.scope = p_scope
      and rc.key = p_key
      and rc.window_start = v_window_start
    for update;
  end if;

  if v_existing_count < p_limit then
    update public.rate_counters rc
    set count = rc.count + 1
    where rc.scope = p_scope
      and rc.key = p_key
      and rc.window_start = v_window_start
      and rc.count < p_limit
    returning rc.count, rc.expires_at
    into v_count, v_expires_at;

    if found then
      allowed := true;
      retry_after_seconds := greatest(
        0,
        ceil(extract(epoch from (v_expires_at - now())))::integer
      );
      return next;
      return;
    end if;
  end if;

  allowed := false;
  retry_after_seconds := greatest(
    1,
    ceil(extract(epoch from (v_existing_expires - now())))::integer
  );
  return next;
end;
$$;

revoke all on function public.bump_rate_counter(text, text, interval, integer)
  from public, anon, authenticated;
grant execute on function public.bump_rate_counter(text, text, interval, integer)
  to service_role;
