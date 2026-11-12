-- Checkout reservation TTL is read by the non-superuser service client.
GRANT SELECT ON TABLE public.platform_config TO service_role;
