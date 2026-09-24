-- The vendor collections API uses get_supabase_client() (service_role).
-- 0094 granted browser roles but omitted service_role in bare/target PG replay.
-- Preserve existing browser grants and RLS policies; add only the API writer.
grant select, insert, update, delete on table public.vendor_storefront_collections
  to service_role;
grant select, insert, update, delete on table public.vendor_storefront_collection_items
  to service_role;
