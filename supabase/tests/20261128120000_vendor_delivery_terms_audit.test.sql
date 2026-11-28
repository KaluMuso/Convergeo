-- Free-delivery changes are audited atomically (trigger, same transaction as the UPDATE).
-- Requires the migration chain through 20261128120000.
-- Run: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/20261128120000_vendor_delivery_terms_audit.test.sql
\set ON_ERROR_STOP on
begin;

do $$
declare
  v_owner uuid := gen_random_uuid();
  v_admin uuid := gen_random_uuid();
  v_vendor uuid;
  v_listing uuid;
  n int;
  a record;
begin
  insert into auth.users (id) values (v_owner) on conflict do nothing;
  insert into public.profiles (id) values (v_owner) on conflict do nothing;
  select id into v_vendor from public.vendors where owner_user_id = v_owner;
  if v_vendor is null then
    insert into public.vendors (owner_user_id, slug, display_name)
    values (v_owner, 'audit-' || substr(v_owner::text, 1, 8), 'Audit shop')
    returning id into v_vendor;
  end if;

  -- Unrelated column: no audit row.
  update public.vendors set description = 'x' where id = v_vendor;
  select count(*) into n from public.audit_log
   where entity_id = v_vendor and action = 'vendor.delivery_terms.update';
  if n <> 0 then raise exception 'unrelated update was audited'; end if;

  -- Shop terms change: one row with before/after, actor = owner.
  update public.vendors set free_delivery_all = true, free_delivery_method = 'self_delivery'
   where id = v_vendor;
  select * into a from public.audit_log
   where entity_id = v_vendor and action = 'vendor.delivery_terms.update'
     and after ->> 'free_delivery_method' = 'self_delivery';
  if a.actor <> v_owner
     or (a.before ->> 'free_delivery_all')::boolean is not false
     or (a.after ->> 'free_delivery_all')::boolean is not true
     or a.after ->> 'free_delivery_method' <> 'self_delivery' then
    raise exception 'wrong audit row for vendor terms: %', a;
  end if;

  -- Same value again: no new row.
  update public.vendors set free_delivery_all = true where id = v_vendor;
  select count(*) into n from public.audit_log
   where entity_id = v_vendor and action = 'vendor.delivery_terms.update';
  if n <> 1 then raise exception 'no-op update was audited (% rows)', n; end if;

  -- A signed-in admin's change is logged as the admin, not the owner.
  perform set_config('request.jwt.claim.sub', v_admin::text, true);
  update public.vendors set free_delivery_method = 'platform_courier' where id = v_vendor;
  perform set_config('request.jwt.claim.sub', '', true);
  select * into a from public.audit_log
   where entity_id = v_vendor and action = 'vendor.delivery_terms.update'
     and after ->> 'free_delivery_method' = 'platform_courier';
  if a.actor is distinct from v_admin then
    raise exception 'admin change not attributed to admin: %', a;
  end if;

  -- Minimum order: defaults to K300, a raise is audited with before/after, negatives rejected.
  if (select free_delivery_min_ngwee from public.vendors where id = v_vendor) <> 30000 then
    raise exception 'default free_delivery_min_ngwee is not 30000';
  end if;
  update public.vendors set free_delivery_min_ngwee = 50000 where id = v_vendor;
  select * into a from public.audit_log
   where entity_id = v_vendor and action = 'vendor.delivery_terms.update'
     and (after ->> 'free_delivery_min_ngwee')::bigint = 50000;
  if (a.before ->> 'free_delivery_min_ngwee')::bigint <> 30000
     or (a.after ->> 'free_delivery_min_ngwee')::bigint <> 50000 then
    raise exception 'minimum change not audited: %', a;
  end if;
  begin
    update public.vendors set free_delivery_min_ngwee = -1 where id = v_vendor;
    raise exception 'negative minimum was accepted';
  exception when check_violation then
    null;
  end;
  if not exists (select 1 from public.platform_config
                  where key = 'vendor_free_delivery_min_floor_ngwee' and value = '30000'::jsonb) then
    raise exception 'platform floor config row missing';
  end if;

  -- Listing-level flag.
  select id into v_listing from public.vendor_listings where vendor_id = v_vendor limit 1;
  if v_listing is not null then
    update public.vendor_listings set free_delivery = true where id = v_listing;
    select * into a from public.audit_log
     where entity_id = v_listing and action = 'vendor.listing_free_delivery.update';
    if a.actor <> v_owner or (a.after ->> 'free_delivery')::boolean is not true then
      raise exception 'wrong audit row for listing: %', a;
    end if;
  end if;
end;
$$;

rollback;
