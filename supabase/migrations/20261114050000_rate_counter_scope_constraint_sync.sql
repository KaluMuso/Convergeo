-- Hotfix: rate-limit scopes used by the API but rejected by rate_counters_scope_check.
-- 20261113130000_in_app_notifications added notifications_read/notifications_write/
-- web_push_subscribe to the manifest only, and checkout_group_read_user was never
-- registered, so bump_rate_counter raised a check violation (HTTP 500 on
-- /me/notifications/unseen-count and the checkout-group read).
-- Additive: widens the allowed set; no data change.
-- Rollback: re-create the constraint with the list from
-- 20260817200000_rate_counter_event_access_unlock_scope.sql (only safe once no rows
-- use the four scopes added here).

insert into private.rate_counter_scope_manifest (scope) values
  ('checkout_group_read_user'),
  ('notifications_read'),
  ('notifications_write'),
  ('web_push_subscribe')
on conflict (scope) do nothing;

alter table public.rate_counters drop constraint if exists rate_counters_scope_check;

alter table public.rate_counters add constraint rate_counters_scope_check check (
  scope in (
    'admin_support_actor', 'admin_support_ip', 'analytics_collect_ip', 'ask_ip',
    'auth_ip', 'auth_number', 'beta_feedback_ip', 'beta_redeem_ip',
    'checkout_group_read_user', 'clip_comment', 'clip_like', 'clip_link',
    'clip_report', 'clip_view', 'discovery_read_ip', 'enquiries_ip_close',
    'enquiries_ip_create', 'enquiries_ip_message', 'enquiries_user_close',
    'enquiries_user_create', 'enquiries_user_message', 'event_access_unlock_ip',
    'intake_link_mint', 'intake_link_redeem', 'internal_cron', 'invoice_download',
    'job_complete_ip', 'job_complete_user', 'job_confirm_ip', 'job_confirm_user',
    'jobs_ip', 'jobs_user', 'listing_report_ip', 'listing_report_user',
    'notifications_read', 'notifications_write', 'otp_ip', 'otp_number', 'quotes_ip',
    'quotes_user', 'returns_ip', 'returns_user', 'reviews_ip_reply',
    'reviews_ip_submit', 'reviews_user_reply', 'reviews_user_submit', 'rfq_accept_ip',
    'rfq_accept_user', 'rfq_ip_create', 'rfq_ip_message', 'rfq_ip_quote',
    'rfq_user_create', 'rfq_user_message', 'rfq_user_quote', 'search_geo_ip',
    'service_book_ip', 'service_book_user', 'service_reviews_ip_reply',
    'service_reviews_ip_submit', 'service_reviews_user_reply',
    'service_reviews_user_submit', 'telemetry_frontend_errors_ip',
    'telemetry_views_ip', 'ticket_transfer_cancel_ip', 'ticket_transfer_cancel_user',
    'ticket_transfer_claim_ip', 'ticket_transfer_claim_user',
    'ticket_transfer_initiate_ip', 'ticket_transfer_initiate_user', 'ticket_verify_ip',
    'ticket_verify_user', 'vendor_collections_write', 'vendor_follow',
    'vendor_licence_apply', 'vendor_payout_method_change', 'vendor_payouts_read',
    'web_push_subscribe', 'webhook_cloudinary', 'webhook_waha_intake', 'write_admin',
    'write_payment', 'write_sensitive', 'write_standard'
  )
);
