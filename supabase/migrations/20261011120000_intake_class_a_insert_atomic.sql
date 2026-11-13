-- Local source allocation: 20261011120000, intake Class-A insertion only.
-- Dependencies: 0003_catalog and 20260813064106_product_strategy_core_contract.
-- Existing tables, constraints, RLS and triggers are retained. No backfill.
-- Down: drop function public.insert_intake_class_a_listing(uuid, uuid, uuid, jsonb);

create function public.insert_intake_class_a_listing(
  p_vendor_id uuid,
  p_product_id uuid,
  p_expected_category_id uuid,
  p_listing_payload jsonb
)
returns table (id uuid, status text, product_id uuid)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  canonical public.products%rowtype;
  category public.categories%rowtype;
  listing public.vendor_listings%rowtype;
  key text;
  value jsonb;
  allowed_keys constant text[] := array[
    'vendor_id', 'product_id', 'title_override', 'description', 'price_ngwee',
    'compare_at_ngwee', 'product_class', 'condition', 'condition_detail',
    'sale_unit', 'unit_step_milli', 'min_steps', 'fulfilment_mode',
    'lead_time_days', 'vendor_capacity_per_week', 'defect_notes', 'stock_mode',
    'stock_qty', 'wholesale', 'price_tiers', 'moq', 'returnable',
    'return_window_hours', 'status'
  ];
begin
  -- EXECUTE grants are the first boundary; don't infer authority from JWT JSON.
  if current_user <> 'service_role' then
    raise exception 'intake_insert_service_role_required' using errcode = '42501';
  end if;
  if p_vendor_id is null or p_product_id is null or p_expected_category_id is null
     or jsonb_typeof(p_listing_payload) is distinct from 'object' then
    raise exception 'intake_insert_payload_invalid' using errcode = '22023';
  end if;
  for key, value in select * from jsonb_each(p_listing_payload) loop
    if not (key = any(allowed_keys)) then
      raise exception 'intake_insert_payload_invalid' using errcode = '22023';
    end if;
    if key in ('price_ngwee', 'unit_step_milli', 'min_steps', 'moq') then
      if jsonb_typeof(value) <> 'number' or value::text !~ '^[0-9]+$' then
        raise exception 'intake_insert_payload_invalid' using errcode = '22023';
      end if;
    elsif key = 'stock_qty' then
      if value <> 'null'::jsonb and
         (jsonb_typeof(value) <> 'number' or value::text !~ '^[0-9]+$') then
        raise exception 'intake_insert_payload_invalid' using errcode = '22023';
      end if;
    elsif key in ('title_override', 'description') then
      if jsonb_typeof(value) not in ('string', 'null') then
        raise exception 'intake_insert_payload_invalid' using errcode = '22023';
      end if;
    elsif key in ('wholesale', 'returnable') then
      if jsonb_typeof(value) <> 'boolean' then
        raise exception 'intake_insert_payload_invalid' using errcode = '22023';
      end if;
    elsif key in ('compare_at_ngwee', 'lead_time_days', 'vendor_capacity_per_week',
                  'defect_notes', 'price_tiers', 'return_window_hours') then
      if value <> 'null'::jsonb then
        raise exception 'intake_insert_payload_invalid' using errcode = '22023';
      end if;
    elsif jsonb_typeof(value) <> 'string' then
      raise exception 'intake_insert_payload_invalid' using errcode = '22023';
    end if;
  end loop;
  -- Missing/JSON-null values cannot silently acquire a default. Only the
  -- listing-owned description is optional in the current intake handoff.
  if not (p_listing_payload ?& array_remove(allowed_keys, 'description')) then
    raise exception 'intake_insert_payload_invalid' using errcode = '22023';
  end if;
  if (p_listing_payload->>'vendor_id') is distinct from p_vendor_id::text
     or (p_listing_payload->>'product_id') is distinct from p_product_id::text
     or (p_listing_payload->>'status') is distinct from 'draft'
     or (p_listing_payload->>'product_class') is distinct from 'A'
     or (p_listing_payload->>'sale_unit') is distinct from 'each'
     or (p_listing_payload->>'unit_step_milli') is distinct from '1000'
     or (p_listing_payload->>'min_steps') is distinct from '1'
     or (p_listing_payload->>'fulfilment_mode') is distinct from 'stocked'
     or (p_listing_payload->>'moq') is distinct from '1'
     or (p_listing_payload->'wholesale') is distinct from 'false'::jsonb
     or (p_listing_payload->'returnable') is distinct from 'false'::jsonb
     or (p_listing_payload->>'condition') not in ('new', 'refurbished')
     or (p_listing_payload->>'condition_detail') is distinct from
        (p_listing_payload->>'condition')
     or coalesce(char_length(btrim(p_listing_payload->>'title_override')), 0) = 0
     or (p_listing_payload->>'stock_mode') not in ('tracked', 'always_available')
     or ((p_listing_payload->>'stock_mode') = 'tracked'
         and p_listing_payload->'stock_qty' = 'null'::jsonb)
     or ((p_listing_payload->>'stock_mode') = 'always_available'
         and p_listing_payload->'stock_qty' <> 'null'::jsonb) then
    raise exception 'intake_insert_payload_invalid' using errcode = '22023';
  end if;

  -- SHARE (not KEY SHARE) blocks non-key class/status/unit/category updates.
  -- Locks live through the insert and the surrounding PostgREST transaction.
  select p.* into canonical from public.products p
    where p.id = p_product_id for share;
  if not found or canonical.status is distinct from 'active' then
    raise exception 'intake_canonical_unavailable' using errcode = '23514';
  end if;
  if canonical.product_class is distinct from 'A' then
    raise exception 'intake_canonical_class' using errcode = '23514';
  end if;
  if canonical.sale_unit is distinct from 'each'
     or canonical.base_unit is distinct from 'each'
     or canonical.base_units_per_sale_unit_milli is distinct from 1000 then
    raise exception 'intake_canonical_units' using errcode = '23514';
  end if;
  if canonical.category_id is distinct from p_expected_category_id then
    raise exception 'intake_canonical_category' using errcode = '23514';
  end if;
  select c.* into category from public.categories c
    where c.id = canonical.category_id for share;
  if not found or category.prohibited is distinct from false then
    raise exception 'intake_canonical_category' using errcode = '23514';
  end if;

  listing := jsonb_populate_record(null::public.vendor_listings, p_listing_payload);
  -- Explicit columns prevent payload-supplied IDs/timestamps/provenance. Every
  -- existing table constraint and trigger executes on this ordinary INSERT.
  return query insert into public.vendor_listings as inserted (
    vendor_id, product_id, title_override, description, price_ngwee,
    compare_at_ngwee, product_class, condition, condition_detail, sale_unit,
    unit_step_milli, min_steps, fulfilment_mode, lead_time_days,
    vendor_capacity_per_week, defect_notes, stock_mode, stock_qty, wholesale,
    price_tiers, moq, returnable, return_window_hours, status
  ) values (
    listing.vendor_id, listing.product_id, listing.title_override, listing.description,
    listing.price_ngwee, listing.compare_at_ngwee, listing.product_class,
    listing.condition, listing.condition_detail, listing.sale_unit,
    listing.unit_step_milli, listing.min_steps, listing.fulfilment_mode,
    listing.lead_time_days, listing.vendor_capacity_per_week, listing.defect_notes,
    listing.stock_mode, listing.stock_qty, listing.wholesale, listing.price_tiers,
    listing.moq, listing.returnable, listing.return_window_hours, listing.status
  ) returning inserted.id, inserted.status, inserted.product_id;
end;
$$;

revoke all on function public.insert_intake_class_a_listing(uuid, uuid, uuid, jsonb)
  from public, anon, authenticated;
grant execute on function public.insert_intake_class_a_listing(uuid, uuid, uuid, jsonb)
  to service_role;

comment on function public.insert_intake_class_a_listing(uuid, uuid, uuid, jsonb) is
  'Intake-only draft Class-A insert. Service-role caller retains API ownership/quota checks; '
  'canonical/category validation and INSERT share row locks in one transaction. '
  'Does not serialize intake submissions, enforce concurrent quotas or publish listings.';
