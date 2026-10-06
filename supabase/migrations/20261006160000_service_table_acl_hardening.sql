-- The platform bootstrap grants ALL on new public tables to service_role.
-- Four later tables narrowed client roles but left bootstrap privileges on
-- service_role. Retain only their explicit SELECT/INSERT[/UPDATE] grants.
REVOKE DELETE, MAINTAIN, REFERENCES, TRIGGER, TRUNCATE ON TABLE
  public.cart_merge_receipts,
  public.payment_collection_exceptions,
  public.payment_collection_receipts,
  public.service_payment_obligations
FROM service_role;

REVOKE UPDATE ON TABLE public.cart_merge_receipts FROM service_role;
