-- create_orders_atomic reads the category commission schedule through the
-- service-role PostgREST client. Earlier grants omitted that server role.
-- This grants only the existing server writer its required read capability.
grant select on table public.commission_rates to service_role;
