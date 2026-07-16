-- 0050: Revoke EXECUTE on SECURITY DEFINER functions from anon/authenticated.
--
-- Supabase's security advisor flags every SECURITY DEFINER function that anon or
-- authenticated can execute (Postgres grants EXECUTE to PUBLIC by default). Since
-- the app's backend calls these with the service-role key and the frontend never
-- calls any Postgres function directly (no client `.rpc()` — verified), no browser
-- role needs to invoke them. Trigger functions fire regardless of caller EXECUTE.
--
-- This revokes EXECUTE from PUBLIC/anon/authenticated and re-grants service_role
-- on the 45 definer functions that are internal (triggers + backend RPCs).
--
-- Intentionally EXEMPT (must stay callable by anon/authenticated):
--   * has_role(text)          — evaluated inside RLS policies (0007_trust_ops)
--   * is_verified_business(uuid) — explicitly granted to anon/authenticated in 0038
--
-- Reversible: `grant execute on function public.<name>(<args>) to public;` per fn.


revoke execute on function public.audit_config_change() from public, anon, authenticated;
grant execute on function public.audit_config_change() to service_role;
revoke execute on function public.audit_orders_status_change() from public, anon, authenticated;
grant execute on function public.audit_orders_status_change() to service_role;
revoke execute on function public.embedding_jobs_enqueue_trigger() from public, anon, authenticated;
grant execute on function public.embedding_jobs_enqueue_trigger() to service_role;
revoke execute on function public.guard_business_buyer_status_update() from public, anon, authenticated;
grant execute on function public.guard_business_buyer_status_update() to service_role;
revoke execute on function public.guard_listing_image_count() from public, anon, authenticated;
grant execute on function public.guard_listing_image_count() to service_role;
revoke execute on function public.guard_orders_pickup_tokens() from public, anon, authenticated;
grant execute on function public.guard_orders_pickup_tokens() to service_role;
revoke execute on function public.guard_orders_status_update() from public, anon, authenticated;
grant execute on function public.guard_orders_status_update() to service_role;
revoke execute on function public.guard_profile_owner_update() from public, anon, authenticated;
grant execute on function public.guard_profile_owner_update() to service_role;
revoke execute on function public.guard_ticket_client_mutation() from public, anon, authenticated;
grant execute on function public.guard_ticket_client_mutation() to service_role;
revoke execute on function public.guard_vendor_listing_status_update() from public, anon, authenticated;
grant execute on function public.guard_vendor_listing_status_update() to service_role;
revoke execute on function public.guard_vendor_status_update() from public, anon, authenticated;
grant execute on function public.guard_vendor_status_update() to service_role;
revoke execute on function public.handle_new_user() from public, anon, authenticated;
grant execute on function public.handle_new_user() to service_role;
revoke execute on function public.reviews_recompute_aggregate_trigger() from public, anon, authenticated;
grant execute on function public.reviews_recompute_aggregate_trigger() to service_role;
revoke execute on function public.search_sync_events_trigger() from public, anon, authenticated;
grant execute on function public.search_sync_events_trigger() to service_role;
revoke execute on function public.search_sync_listings_trigger() from public, anon, authenticated;
grant execute on function public.search_sync_listings_trigger() to service_role;
revoke execute on function public.search_sync_products_trigger() from public, anon, authenticated;
grant execute on function public.search_sync_products_trigger() to service_role;
revoke execute on function public.search_sync_services_trigger() from public, anon, authenticated;
grant execute on function public.search_sync_services_trigger() to service_role;
revoke execute on function public.search_sync_ticket_types_trigger() from public, anon, authenticated;
grant execute on function public.search_sync_ticket_types_trigger() to service_role;
revoke execute on function public.search_sync_vendors_trigger() from public, anon, authenticated;
grant execute on function public.search_sync_vendors_trigger() to service_role;
revoke execute on function public.validate_review_verified_purchase() from public, anon, authenticated;
grant execute on function public.validate_review_verified_purchase() to service_role;
revoke execute on function public.ask_monthly_cap_usd_micros() from public, anon, authenticated;
grant execute on function public.ask_monthly_cap_usd_micros() to service_role;
revoke execute on function public.ask_read_config_int(p_key text, p_default integer) from public, anon, authenticated;
grant execute on function public.ask_read_config_int(p_key text, p_default integer) to service_role;
revoke execute on function public.bump_rate_counter(p_scope text, p_key text, p_window interval, p_limit integer) from public, anon, authenticated;
grant execute on function public.bump_rate_counter(p_scope text, p_key text, p_window interval, p_limit integer) to service_role;
revoke execute on function public.claim_embedding_jobs(p_limit integer) from public, anon, authenticated;
grant execute on function public.claim_embedding_jobs(p_limit integer) to service_role;
revoke execute on function public.cleanup_expired_rate_counters() from public, anon, authenticated;
grant execute on function public.cleanup_expired_rate_counters() to service_role;
revoke execute on function public.embedding_enqueue_document(p_search_document_id uuid, p_entity_kind text, p_entity_id uuid) from public, anon, authenticated;
grant execute on function public.embedding_enqueue_document(p_search_document_id uuid, p_entity_kind text, p_entity_id uuid) to service_role;
revoke execute on function public.expand_search_terms(p_query text) from public, anon, authenticated;
grant execute on function public.expand_search_terms(p_query text) to service_role;
revoke execute on function public.finalize_ask_answer(p_reservation_id uuid, p_tokens integer, p_model text, p_usd_micros bigint) from public, anon, authenticated;
grant execute on function public.finalize_ask_answer(p_reservation_id uuid, p_tokens integer, p_model text, p_usd_micros bigint) to service_role;
revoke execute on function public.next_invoice_no(p_series text) from public, anon, authenticated;
grant execute on function public.next_invoice_no(p_series text) to service_role;
revoke execute on function public.recompute_all_review_aggregates() from public, anon, authenticated;
grant execute on function public.recompute_all_review_aggregates() to service_role;
revoke execute on function public.recompute_review_aggregate(p_entity_kind text, p_entity_id uuid) from public, anon, authenticated;
grant execute on function public.recompute_review_aggregate(p_entity_kind text, p_entity_id uuid) to service_role;
revoke execute on function public.recompute_review_aggregate_for_order_item(p_order_item_id uuid) from public, anon, authenticated;
grant execute on function public.recompute_review_aggregate_for_order_item(p_order_item_id uuid) to service_role;
revoke execute on function public.redeem_beta_invite(p_code text) from public, anon, authenticated;
grant execute on function public.redeem_beta_invite(p_code text) to service_role;
revoke execute on function public.reserve_ask_quota(p_user_id uuid, p_guest_key text, p_client_ip inet, p_question_hash text) from public, anon, authenticated;
grant execute on function public.reserve_ask_quota(p_user_id uuid, p_guest_key text, p_client_ip inet, p_question_hash text) to service_role;
revoke execute on function public.reset_ask_kill_switch(p_month_key text) from public, anon, authenticated;
grant execute on function public.reset_ask_kill_switch(p_month_key text) to service_role;
revoke execute on function public.review_bayes_value(p_rating_sum integer, p_rating_count integer) from public, anon, authenticated;
grant execute on function public.review_bayes_value(p_rating_sum integer, p_rating_count integer) to service_role;
revoke execute on function public.search_cascade_vendor_children(p_vendor_id uuid) from public, anon, authenticated;
grant execute on function public.search_cascade_vendor_children(p_vendor_id uuid) to service_role;
revoke execute on function public.search_mark_unpublished(p_entity_kind text, p_entity_id uuid) from public, anon, authenticated;
grant execute on function public.search_mark_unpublished(p_entity_kind text, p_entity_id uuid) to service_role;
revoke execute on function public.search_remove_document(p_entity_kind text, p_entity_id uuid) from public, anon, authenticated;
grant execute on function public.search_remove_document(p_entity_kind text, p_entity_id uuid) to service_role;
revoke execute on function public.search_rrf(query text, query_embedding vector, filters jsonb) from public, anon, authenticated;
grant execute on function public.search_rrf(query text, query_embedding vector, filters jsonb) to service_role;
revoke execute on function public.search_upsert_event(p_event_id uuid) from public, anon, authenticated;
grant execute on function public.search_upsert_event(p_event_id uuid) to service_role;
revoke execute on function public.search_upsert_listing(p_listing_id uuid) from public, anon, authenticated;
grant execute on function public.search_upsert_listing(p_listing_id uuid) to service_role;
revoke execute on function public.search_upsert_product(p_product_id uuid) from public, anon, authenticated;
grant execute on function public.search_upsert_product(p_product_id uuid) to service_role;
revoke execute on function public.search_upsert_service(p_service_id uuid) from public, anon, authenticated;
grant execute on function public.search_upsert_service(p_service_id uuid) to service_role;
revoke execute on function public.search_upsert_vendor(p_vendor_id uuid) from public, anon, authenticated;
grant execute on function public.search_upsert_vendor(p_vendor_id uuid) to service_role;

-- Added after the initial sweep: a same-event guard trigger from the
-- ticket_type_instances work (also a trigger fn — fires regardless of caller EXECUTE).
revoke execute on function public.guard_ticket_type_instance_same_event() from public, anon, authenticated;
grant execute on function public.guard_ticket_type_instance_same_event() to service_role;
