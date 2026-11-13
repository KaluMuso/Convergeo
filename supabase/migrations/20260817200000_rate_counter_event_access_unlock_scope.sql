-- Additive: declare event_access_unlock_ip so private-event unlock cannot
-- hit bump_rate_counter against an undeclared scope. Safe on fresh replay.

insert into private.rate_counter_scope_manifest (scope) values
  ('event_access_unlock_ip')
on conflict (scope) do nothing;

alter table public.rate_counters drop constraint if exists rate_counters_scope_check;

alter table public.rate_counters add constraint rate_counters_scope_check check (
  scope in (
    'admin_support_actor', 'admin_support_ip', 'analytics_collect_ip', 'ask_ip',
    'auth_ip', 'auth_number', 'beta_feedback_ip', 'beta_redeem_ip', 'clip_comment',
    'clip_like', 'clip_link', 'clip_report', 'clip_view', 'discovery_read_ip',
    'enquiries_ip_close', 'enquiries_ip_create', 'enquiries_ip_message',
    'enquiries_user_close', 'enquiries_user_create', 'enquiries_user_message',
    'event_access_unlock_ip',
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
