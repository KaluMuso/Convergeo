-- COD order admission reads the vendor tier quota through the service-role
-- PostgREST client. Give the server writer only the required table read.
grant select on table public.vendor_quotas to service_role;
