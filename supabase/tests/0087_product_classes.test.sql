-- R02-P16 product-class schema contract.
-- Run after migrations 0085 and 0087 with: supabase test db

begin;

set local search_path to public, extensions;

select extensions.plan(26);

select extensions.has_column(
  'public', 'vendor_listings', 'sale_unit', 'sale unit column exists'
);
select extensions.has_column(
  'public', 'vendor_listings', 'unit_step_milli', 'integer unit step column exists'
);
select extensions.has_column(
  'public', 'vendor_listings', 'min_steps', 'minimum step count column exists'
);
select extensions.has_column(
  'public', 'vendor_listings', 'fulfilment_mode', 'fulfilment mode column exists'
);
select extensions.has_column(
  'public', 'vendor_listings', 'lead_time_days', 'lead time column exists'
);
select extensions.has_column(
  'public', 'vendor_listings', 'defect_notes', 'used-condition defect notes column exists'
);
select extensions.has_column(
  'public', 'vendor_listings', 'product_class', 'product class column exists'
);
select extensions.has_column(
  'public', 'vendor_listings', 'vendor_capacity_per_week', 'weekly capacity column exists'
);

select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_sale_unit_check'
  ),
  'sale units are constrained'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_product_class_check'
  ),
  'product classes are constrained to the strategy enum'
);
select extensions.ok(
  exists (
    select 1
    from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_condition_check'
      and pg_get_constraintdef(oid) like '%used%'
  ),
  'listing condition enum includes used'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_each_is_whole_check'
  ),
  'discrete items require a whole-unit step'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_lead_time_check'
  ),
  'made-to-order lead time is constrained'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_used_needs_notes_check'
  ),
  'used listings require meaningful defect notes'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_class_d_condition_check'
  ),
  'Class D is constrained to used condition'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_class_e_fields_check'
  ),
  'Class E requires made-to-order lead time and capacity'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_capacity_only_class_e_check'
  ),
  'weekly capacity is exclusive to Class E'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_standalone_class_check'
  ),
  'Class D/E canonical attachment is guarded in the database'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_standalone_title_check'
  ),
  'Class D/E standalone titles are guarded in the database'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_per_measure_wholesale_check'
  ),
  'deferred per-measure wholesale is guarded in the database'
);
select extensions.ok(
  exists (
    select 1 from pg_constraint
    where conrelid = 'public.vendor_listings'::regclass
      and conname = 'vendor_listings_class_e_capacity_floor_check'
  ),
  'Class E capacity must cover a minimum purchase'
);
select extensions.ok(
  exists (
    select 1
    from pg_indexes
    where schemaname = 'public'
      and tablename = 'order_item_products'
      and indexname = 'order_item_products_listing_id_idx'
      and indexdef like '%(listing_id)%'
  ),
  'Class E committed-quantity lookup is index-backed'
);
select extensions.ok(
  exists (
    select 1 from pg_trigger
    where tgrelid = 'public.vendor_listings'::regclass
      and tgname = 'vendor_listings_active_used_evidence_guard'
      and not tgisinternal
  ),
  'active used evidence trigger is installed'
);
select extensions.ok(
  exists (
    select 1 from pg_trigger
    where tgrelid = 'public.listing_images'::regclass
      and tgname = 'listing_images_used_evidence_delete_guard'
      and not tgisinternal
  ),
  'last used-evidence image delete is guarded'
);
select extensions.ok(
  exists (
    select 1 from pg_trigger
    where tgrelid = 'public.listing_images'::regclass
      and tgname = 'listing_images_used_evidence_move_guard'
      and not tgisinternal
  ),
  'moving the last used-evidence image is guarded'
);

-- Five half-metre steps are 2.5 metres. Money remains exact integer ngwee.
select extensions.is(
  public.listing_line_total_ngwee(18750::bigint, 5),
  93750::bigint,
  'half-metre step line total uses exact integer multiplication'
);

select * from extensions.finish();

rollback;
