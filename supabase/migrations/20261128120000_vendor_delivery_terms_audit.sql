-- Vendor free-delivery minimum order + audit of every change to who pays delivery.
--
-- vendors.free_delivery_min_ngwee: the smallest vendor basket that qualifies for that
-- vendor's free delivery (default K300, vendor may raise it). The platform floor lives
-- in platform_config (vendor_free_delivery_min_floor_ngwee, K300) so the founder can
-- change it without a deploy; pricing takes the larger of the two at checkout.
--
-- Audit every change to who pays delivery, atomically with the change itself.
--
-- A vendor's free-delivery choices (vendors.free_delivery_all / free_delivery_method,
-- vendor_listings.free_delivery) decide whether the vendor bears the courier fee, so
-- a change must never land unlogged. Triggers write the audit_log row in the same
-- statement and transaction as the UPDATE, whichever code path made it (the vendor
-- API, an admin tool, a script). If the audit insert fails the change rolls back.
--
-- The actor is the signed-in user when there is one (auth.uid(), so an admin's change is
-- logged as the admin); service-role calls from the vendor API carry no end-user JWT, so
-- they fall back to the shop owner (the only role that can change these through the API).
--
-- Additive only. Reversible:
--   delete from public.platform_config where key = 'vendor_free_delivery_min_floor_ngwee';
--   alter table public.vendors drop column if exists free_delivery_min_ngwee;
--   drop trigger if exists vendor_listings_audit_free_delivery on public.vendor_listings;
--   drop trigger if exists vendors_audit_delivery_terms on public.vendors;
--   drop function if exists public.audit_vendor_listing_free_delivery();
--   drop function if exists public.audit_vendor_delivery_terms();

alter table public.vendors
  add column if not exists free_delivery_min_ngwee bigint not null default 30000
  check (free_delivery_min_ngwee >= 0);

insert into public.platform_config (key, value, description) values
  ('vendor_free_delivery_min_floor_ngwee', '30000'::jsonb,
   'Smallest vendor basket (ngwee) a vendor-funded free delivery may require; vendors can raise their own minimum but not go below this.')
on conflict (key) do nothing;

create or replace function public.audit_vendor_delivery_terms()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if new.free_delivery_all is distinct from old.free_delivery_all
     or new.free_delivery_method is distinct from old.free_delivery_method
     or new.free_delivery_min_ngwee is distinct from old.free_delivery_min_ngwee then
    insert into public.audit_log (actor, action, entity_type, entity_id, before, after)
    values (
      coalesce(auth.uid(), new.owner_user_id),
      'vendor.delivery_terms.update',
      'vendor',
      new.id,
      jsonb_build_object(
        'free_delivery_all', old.free_delivery_all,
        'free_delivery_method', old.free_delivery_method,
        'free_delivery_min_ngwee', old.free_delivery_min_ngwee
      ),
      jsonb_build_object(
        'free_delivery_all', new.free_delivery_all,
        'free_delivery_method', new.free_delivery_method,
        'free_delivery_min_ngwee', new.free_delivery_min_ngwee
      )
    );
  end if;
  return new;
end;
$$;

create or replace function public.audit_vendor_listing_free_delivery()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_owner uuid;
begin
  if new.free_delivery is distinct from old.free_delivery then
    select owner_user_id into v_owner from public.vendors where id = new.vendor_id;
    insert into public.audit_log (actor, action, entity_type, entity_id, before, after)
    values (
      coalesce(auth.uid(), v_owner),
      'vendor.listing_free_delivery.update',
      'vendor_listing',
      new.id,
      jsonb_build_object('free_delivery', old.free_delivery, 'vendor_id', new.vendor_id),
      jsonb_build_object('free_delivery', new.free_delivery, 'vendor_id', new.vendor_id)
    );
  end if;
  return new;
end;
$$;

revoke execute on function public.audit_vendor_delivery_terms() from public, anon, authenticated;
revoke execute on function public.audit_vendor_listing_free_delivery() from public, anon, authenticated;

drop trigger if exists vendors_audit_delivery_terms on public.vendors;
create trigger vendors_audit_delivery_terms
  after update of free_delivery_all, free_delivery_method, free_delivery_min_ngwee on public.vendors
  for each row execute function public.audit_vendor_delivery_terms();

drop trigger if exists vendor_listings_audit_free_delivery on public.vendor_listings;
create trigger vendor_listings_audit_free_delivery
  after update of free_delivery on public.vendor_listings
  for each row execute function public.audit_vendor_listing_free_delivery();
