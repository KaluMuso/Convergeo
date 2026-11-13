-- The platform bootstrap grants ALL on new public tables to service_role.
-- Four later tables narrowed client roles but left bootstrap privileges on
-- service_role. Retain only their explicit SELECT/INSERT[/UPDATE] grants.
REVOKE DELETE, REFERENCES, TRIGGER, TRUNCATE ON TABLE
  public.cart_merge_receipts,
  public.payment_collection_exceptions,
  public.payment_collection_receipts,
  public.service_payment_obligations
FROM service_role;

REVOKE UPDATE ON TABLE public.cart_merge_receipts FROM service_role;

-- MAINTAIN is a PostgreSQL 17+ table privilege. Keep its fixed SQL text out
-- of the PostgreSQL 15 parser while still removing the PG17 bootstrap grant.
DO $acl_hardening$
BEGIN
  IF current_setting('server_version_num')::integer >= 170000 THEN
    EXECUTE 'REVOKE MAINTAIN ON TABLE
      public.cart_merge_receipts,
      public.payment_collection_exceptions,
      public.payment_collection_receipts,
      public.service_payment_obligations
      FROM service_role';
  END IF;
END;
$acl_hardening$;
