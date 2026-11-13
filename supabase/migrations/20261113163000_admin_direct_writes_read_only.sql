-- 2026-11 analytics/RBAC audit, decision D1 (founder-approved 2026-11-13).
--
-- 20261113100000 made the six money tables read-only for the legacy `admin` role.
-- The same M03 pattern -- a permissive policy on has_role('admin') for INSERT/UPDATE/
-- DELETE plus table write grants to `authenticated` -- remained on 75 more tables:
-- orders and order lines, invoices and the invoice counter, KYC, vendors, disputes,
-- tickets, profiles, addresses, catalogue, events, services, intake and every config
-- table. An admin browser token could write all of them through PostgREST, past the
-- API's state machines, idempotency and audit_log.
--
-- Checked before writing this (2026-11-13, against a local replay of every migration):
--   * the admin app has no database client: every admin action goes through the API,
--     which writes as service_role (BYPASSRLS) and is unaffected;
--   * the API's user-token clients (cart, checkout, orders_create, account, privacy,
--     follows) only write carts, cart_items, addresses and profiles, which keep their
--     owner policies and grants;
--   * no SECURITY INVOKER function or trigger writes any table below (every writing
--     trigger function is SECURITY DEFINER);
--   * no runbook, n8n job or script writes these tables with a user token.
--
-- Treatment, table by table (explicit lists):
--   1. every admin write policy is dropped; tables whose admin policy was the FOR ALL
--      `<t>_admin_all` get `<t>_admin_select`, so admins keep reading;
--   2. three owner policies that OR-ed in has_role('admin') are recreated owner-only
--      (plus an admin SELECT policy where the ALL policy was the admin's read path);
--   3. a client write grant is revoked from anon and authenticated only where no
--      remaining policy could use it (owner, customer, vendor and guest writes keep
--      theirs); TRUNCATE, REFERENCES and TRIGGER are revoked from both everywhere.
-- service_role grants and every non-admin policy are untouched. A post-condition
-- refuses to commit while any public policy still grants an admin write.
--
-- Known residual (documented in docs/admin/governance.md): 17 guard trigger functions
-- still exempt has_role('admin'); after this migration that exemption is only reachable
-- by an admin who is also the owning customer/vendor of the row. Revoke `admin` from
-- anyone who also trades on the platform.
--
-- Down (manual): docs/audit/2026-11-analytics-rbac/d1-down.sql restores the previous
-- policies and grants exactly; it was generated from the pre-migration catalogue and
-- exercised on the same local replay.

do $$
declare
  t text;
begin
  -- 1a. FOR ALL admin policies become SELECT-only.
  foreach t in array array[
    'addresses', 'business_buyers', 'cart_items', 'carts',
    'category_product_policies', 'clip_comments', 'clip_likes', 'clip_products',
    'clip_reports', 'courier_partner_zones', 'courier_partners', 'disputes',
    'event_categories', 'event_instances', 'events', 'flags', 'fx_rates',
    'intake_draft_fields', 'intake_field_provenance', 'intake_media',
    'intake_messages', 'intake_sessions', 'intake_vendor_bindings',
    'invoice_counters', 'invoices', 'job_quotes', 'jobs', 'kyc_records',
    'listing_evidence', 'listing_images', 'listing_option_groups',
    'listing_option_values', 'listing_specification_snapshots', 'order_events',
    'order_item_products', 'order_item_services', 'order_item_tickets',
    'order_items', 'orders', 'product_relations', 'product_variant_groups',
    'product_variant_values', 'product_variants', 'products', 'profiles', 'returns',
    'reviews', 'service_categories', 'service_reviews', 'services',
    'ticket_type_instances', 'ticket_type_price_tiers', 'ticket_types', 'tickets',
    'user_recently_viewed', 'user_saves', 'user_wishlist',
    'vendor_listing_variants', 'vendor_listings', 'vendor_locations', 'vendors',
    'video_clips'
  ]
  loop
    execute format('drop policy if exists %I on public.%I', t || '_admin_all', t);
    execute format('drop policy if exists %I on public.%I', t || '_admin_select', t);
    execute format(
      'create policy %I on public.%I for select to authenticated '
      'using (public.has_role(''admin''))',
      t || '_admin_select', t
    );
    execute format(
      'comment on policy %I on public.%I is %L',
      t || '_admin_select', t,
      'Platform admins may read; admin writes go through the API as service_role (2026-11 RBAC D1).'
    );
  end loop;
end
$$;

-- 1b. Config tables had separate admin INSERT/UPDATE/DELETE policies; their SELECT
-- policies (public, authenticated or admin) already cover admin reads.
drop policy if exists categories_admin_delete on public.categories;
drop policy if exists categories_admin_insert on public.categories;
drop policy if exists categories_admin_update on public.categories;
drop policy if exists commission_rates_delete_admin on public.commission_rates;
drop policy if exists commission_rates_insert_admin on public.commission_rates;
drop policy if exists commission_rates_update_admin on public.commission_rates;
drop policy if exists delivery_zones_delete_admin on public.delivery_zones;
drop policy if exists delivery_zones_insert_admin on public.delivery_zones;
drop policy if exists delivery_zones_update_admin on public.delivery_zones;
drop policy if exists feature_flags_delete_admin on public.feature_flags;
drop policy if exists feature_flags_insert_admin on public.feature_flags;
drop policy if exists feature_flags_update_admin on public.feature_flags;
drop policy if exists merch_slots_delete_admin on public.merch_slots;
drop policy if exists merch_slots_insert_admin on public.merch_slots;
drop policy if exists merch_slots_update_admin on public.merch_slots;
drop policy if exists platform_config_delete_admin on public.platform_config;
drop policy if exists platform_config_insert_admin on public.platform_config;
drop policy if exists platform_config_update_admin on public.platform_config;
drop policy if exists prohibited_categories_delete_admin on public.prohibited_categories;
drop policy if exists prohibited_categories_insert_admin on public.prohibited_categories;
drop policy if exists prohibited_categories_update_admin on public.prohibited_categories;
drop policy if exists synonyms_admin_delete on public.synonyms;
drop policy if exists synonyms_admin_insert on public.synonyms;
drop policy if exists synonyms_admin_update on public.synonyms;
drop policy if exists translation_overrides_delete_admin on public.translation_overrides;
drop policy if exists translation_overrides_insert_admin on public.translation_overrides;
drop policy if exists translation_overrides_update_admin on public.translation_overrides;
drop policy if exists vendor_quotas_delete_admin on public.vendor_quotas;
drop policy if exists vendor_quotas_insert_admin on public.vendor_quotas;
drop policy if exists vendor_quotas_update_admin on public.vendor_quotas;

-- 2. Owner policies that also admitted admins: recreate owner-only, add admin read.
drop policy if exists vendor_licences_owner_update on public.vendor_licences;
create policy vendor_licences_owner_update on public.vendor_licences
  for update to authenticated
  using (exists (
    select 1 from public.vendors v
    where v.id = vendor_licences.vendor_id and v.owner_user_id = (select auth.uid())
  ));

drop policy if exists vendor_storefront_collections_owner_all
  on public.vendor_storefront_collections;
create policy vendor_storefront_collections_owner_all on public.vendor_storefront_collections
  for all to authenticated
  using (exists (
    select 1 from public.vendors v
    where v.id = vendor_storefront_collections.vendor_id
      and v.owner_user_id = (select auth.uid())
  ))
  with check (exists (
    select 1 from public.vendors v
    where v.id = vendor_storefront_collections.vendor_id
      and v.owner_user_id = (select auth.uid())
  ));
drop policy if exists vendor_storefront_collections_admin_select
  on public.vendor_storefront_collections;
create policy vendor_storefront_collections_admin_select on public.vendor_storefront_collections
  for select to authenticated using (public.has_role('admin'));

drop policy if exists vendor_storefront_collection_items_owner_all
  on public.vendor_storefront_collection_items;
create policy vendor_storefront_collection_items_owner_all
  on public.vendor_storefront_collection_items
  for all to authenticated
  using (exists (
    select 1 from public.vendor_storefront_collections c
    join public.vendors v on v.id = c.vendor_id
    where c.id = vendor_storefront_collection_items.collection_id
      and v.owner_user_id = (select auth.uid())
  ))
  with check (exists (
    select 1 from public.vendor_storefront_collections c
    join public.vendors v on v.id = c.vendor_id
    where c.id = vendor_storefront_collection_items.collection_id
      and v.owner_user_id = (select auth.uid())
  ));
drop policy if exists vendor_storefront_collection_items_admin_select
  on public.vendor_storefront_collection_items;
create policy vendor_storefront_collection_items_admin_select
  on public.vendor_storefront_collection_items
  for select to authenticated using (public.has_role('admin'));

-- 3. Revoke client write grants that no remaining policy can use.
do $$
declare
  t text;
begin
  -- No remaining client INSERT/UPDATE/DELETE policy.
  foreach t in array array[
    'categories', 'category_product_policies', 'commission_rates',
    'courier_partner_zones', 'courier_partners', 'delivery_zones',
    'event_categories', 'feature_flags', 'fx_rates', 'intake_field_provenance',
    'intake_media', 'intake_messages', 'invoice_counters', 'invoices',
    'kyc_records', 'listing_evidence', 'listing_option_groups',
    'listing_option_values', 'listing_specification_snapshots', 'merch_slots',
    'order_events', 'order_item_products', 'order_item_services',
    'order_item_tickets', 'order_items', 'orders', 'platform_config',
    'product_relations', 'product_variant_groups', 'product_variant_values',
    'product_variants', 'prohibited_categories', 'service_categories', 'synonyms',
    'tickets', 'translation_overrides', 'vendor_listing_variants', 'vendor_quotas'
  ]
  loop
    execute format('revoke insert, update, delete on public.%I from anon, authenticated', t);
  end loop;
  -- No remaining client UPDATE/DELETE policy.
  foreach t in array array[
    'clip_reports', 'disputes', 'flags', 'products', 'returns'
  ]
  loop
    execute format('revoke update, delete on public.%I from anon, authenticated', t);
  end loop;
  -- No remaining client INSERT/DELETE policy.
  foreach t in array array[
    'intake_draft_fields', 'intake_sessions', 'intake_vendor_bindings', 'profiles'
  ]
  loop
    execute format('revoke insert, delete on public.%I from anon, authenticated', t);
  end loop;
  -- No remaining client DELETE policy.
  foreach t in array array[
    'business_buyers', 'job_quotes', 'reviews', 'service_reviews',
    'vendor_licences', 'vendors'
  ]
  loop
    execute format('revoke delete on public.%I from anon, authenticated', t);
  end loop;
  -- No remaining client UPDATE policy.
  foreach t in array array[
    'clip_comments', 'clip_likes', 'user_saves', 'user_wishlist'
  ]
  loop
    execute format('revoke update on public.%I from anon, authenticated', t);
  end loop;
  -- Every D1 table: no client role may truncate (bypasses RLS), reference or trigger.
  foreach t in array array[
    'addresses', 'business_buyers', 'cart_items', 'carts', 'categories',
    'category_product_policies', 'clip_comments', 'clip_likes', 'clip_products',
    'clip_reports', 'commission_rates', 'courier_partner_zones', 'courier_partners',
    'delivery_zones', 'disputes', 'event_categories', 'event_instances', 'events',
    'feature_flags', 'flags', 'fx_rates', 'intake_draft_fields',
    'intake_field_provenance', 'intake_media', 'intake_messages', 'intake_sessions',
    'intake_vendor_bindings', 'invoice_counters', 'invoices', 'job_quotes', 'jobs',
    'kyc_records', 'listing_evidence', 'listing_images', 'listing_option_groups',
    'listing_option_values', 'listing_specification_snapshots', 'merch_slots',
    'order_events', 'order_item_products', 'order_item_services',
    'order_item_tickets', 'order_items', 'orders', 'platform_config',
    'product_relations', 'product_variant_groups', 'product_variant_values',
    'product_variants', 'products', 'profiles', 'prohibited_categories', 'returns',
    'reviews', 'service_categories', 'service_reviews', 'services', 'synonyms',
    'ticket_type_instances', 'ticket_type_price_tiers', 'ticket_types', 'tickets',
    'translation_overrides', 'user_recently_viewed', 'user_saves', 'user_wishlist',
    'vendor_licences', 'vendor_listing_variants', 'vendor_listings',
    'vendor_locations', 'vendor_quotas', 'vendor_storefront_collection_items',
    'vendor_storefront_collections', 'vendors', 'video_clips'
  ]
  loop
    execute format(
      'revoke truncate, references, trigger on public.%I from anon, authenticated', t
    );
  end loop;
end
$$;

-- Post-condition: no policy on a public table grants a write through has_role('admin').
do $$
declare
  leftover text;
begin
  select string_agg(tablename || '.' || policyname, ', ' order by tablename, policyname)
    into leftover
    from pg_policies
   where schemaname = 'public'
     and cmd <> 'SELECT'
     and (coalesce(qual, '') || coalesce(with_check, '')) ~ 'has_role\(''admin''';
  if leftover is not null then
    raise exception 'D1: admin write policies remain: %', leftover;
  end if;
end
$$;
