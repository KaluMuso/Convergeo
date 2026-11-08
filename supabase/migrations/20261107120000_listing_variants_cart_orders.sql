-- Listing variants (colour / size / storage) for apparel and phone vendors.
--
-- REUSES the Product Strategy contract (20260813064106):
--   * listing_option_groups / listing_option_values hold the vendor-owned axes
--     ("Colour": Red/Blue, "Size": S/M/L). A new `kind` column separates these
--     purchasable variant axes from the existing Class-E specification options.
--   * vendor_listing_variants holds one row per purchasable combination with its
--     SKU, stock, optional price override (integer ngwee) and photo. It can now
--     describe a listing-defined combination (option_value_ids) as well as the
--     original canonical product_variant link.
--   * cart_items / order_item_products carry the chosen variant; the order line
--     also snapshots the human label so history survives later edits.
--
-- Additive only. Two NOT NULL relaxations on vendor_listing_variants
-- (product_variant_id, price_ngwee) widen what the table accepts and keep every
-- existing row valid. Reversal (manual): drop the function, triggers, policies,
-- indexes and columns added below, then
--   alter table public.vendor_listing_variants alter column price_ngwee set not null,
--     alter column product_variant_id set not null;
-- which only succeeds while no listing-defined variant rows exist.

-- ---------------------------------------------------------------------------
-- 1. Variant axes on the existing listing option tables
-- ---------------------------------------------------------------------------

alter table public.listing_option_groups
  add column if not exists kind text not null default 'specification',
  add column if not exists display text not null default 'pill';

alter table public.listing_option_values
  add column if not exists swatch_hex text;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'listing_option_groups_kind_check') then
    alter table public.listing_option_groups add constraint listing_option_groups_kind_check
      check (kind in ('specification', 'variant'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'listing_option_groups_display_check') then
    alter table public.listing_option_groups add constraint listing_option_groups_display_check
      check (display in ('pill', 'swatch'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'listing_option_values_swatch_hex_check') then
    alter table public.listing_option_values add constraint listing_option_values_swatch_hex_check
      check (swatch_hex is null or swatch_hex ~ '^#[0-9A-Fa-f]{6}$');
  end if;
end
$$;

create index if not exists listing_option_groups_listing_kind_idx
  on public.listing_option_groups (listing_id, kind, position);

-- ---------------------------------------------------------------------------
-- 2. Listing-defined purchasable variants
-- ---------------------------------------------------------------------------

alter table public.vendor_listing_variants
  alter column product_variant_id drop not null,
  -- NULL = inherit the listing price; a value is the per-variant override.
  alter column price_ngwee drop not null,
  add column if not exists option_value_ids uuid[] not null default '{}'::uuid[],
  add column if not exists status text not null default 'active',
  add column if not exists position integer not null default 1;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'vendor_listing_variants_status_check') then
    alter table public.vendor_listing_variants add constraint vendor_listing_variants_status_check
      check (status in ('active', 'archived'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'vendor_listing_variants_identity_check') then
    alter table public.vendor_listing_variants add constraint vendor_listing_variants_identity_check
      check (product_variant_id is not null or cardinality(option_value_ids) > 0);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'vendor_listing_variants_position_check') then
    alter table public.vendor_listing_variants add constraint vendor_listing_variants_position_check
      check (position between 1 and 500);
  end if;
end
$$;

-- option_value_ids are stored sorted by the writer function, so array equality
-- identifies a combination.
create unique index if not exists vendor_listing_variants_listing_options_unique
  on public.vendor_listing_variants (listing_id, option_value_ids)
  where product_variant_id is null;
create unique index if not exists vendor_listing_variants_listing_sku_unique
  on public.vendor_listing_variants (listing_id, lower(sku_override))
  where sku_override is not null;

create or replace function public.guard_vendor_listing_variant_options()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_matched integer;
begin
  if cardinality(new.option_value_ids) = 0 then
    return new;
  end if;
  select count(distinct v.id) into v_matched
  from public.listing_option_values v
  join public.listing_option_groups g on g.id = v.group_id
  where v.id = any(new.option_value_ids)
    and g.listing_id = new.listing_id
    and g.kind = 'variant';
  if v_matched <> cardinality(new.option_value_ids) then
    raise exception 'variant options must be variant values of listing %', new.listing_id
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

revoke execute on function public.guard_vendor_listing_variant_options() from public, anon, authenticated;

drop trigger if exists vendor_listing_variants_options_guard on public.vendor_listing_variants;
create trigger vendor_listing_variants_options_guard
  before insert or update of option_value_ids, listing_id on public.vendor_listing_variants
  for each row execute function public.guard_vendor_listing_variant_options();

-- ---------------------------------------------------------------------------
-- 3. Cart lines and order lines carry the chosen variant
-- ---------------------------------------------------------------------------

alter table public.cart_items
  -- Cart lines are ephemeral: a hard-deleted variant drops its line.
  add column if not exists listing_variant_id uuid
    references public.vendor_listing_variants (id) on delete cascade;

alter table public.order_item_products
  -- Ordered variants are archived, never deleted (restrict keeps history honest).
  add column if not exists listing_variant_id uuid
    references public.vendor_listing_variants (id) on delete restrict,
  add column if not exists variant_snapshot jsonb not null default '{}'::jsonb;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'order_item_products_variant_snapshot_object_check') then
    alter table public.order_item_products add constraint order_item_products_variant_snapshot_object_check
      check (jsonb_typeof(variant_snapshot) = 'object');
  end if;
end
$$;

create index if not exists cart_items_listing_variant_id_idx
  on public.cart_items (listing_variant_id) where listing_variant_id is not null;
create index if not exists order_item_products_listing_variant_id_idx
  on public.order_item_products (listing_variant_id) where listing_variant_id is not null;

-- A line's variant must belong to the line's own listing — enforced at the
-- database boundary, not only in the API.
create or replace function public.guard_line_variant_matches_listing()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.listing_variant_id is null then
    return new;
  end if;
  if not exists (
    select 1 from public.vendor_listing_variants lv
    where lv.id = new.listing_variant_id and lv.listing_id = new.listing_id
  ) then
    raise exception 'variant % does not belong to listing %', new.listing_variant_id, new.listing_id
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

revoke execute on function public.guard_line_variant_matches_listing() from public, anon, authenticated;

drop trigger if exists cart_items_variant_matches_listing on public.cart_items;
create trigger cart_items_variant_matches_listing
  before insert or update of listing_variant_id, listing_id on public.cart_items
  for each row execute function public.guard_line_variant_matches_listing();

drop trigger if exists order_item_products_variant_matches_listing on public.order_item_products;
create trigger order_item_products_variant_matches_listing
  before insert or update of listing_variant_id, listing_id on public.order_item_products
  for each row execute function public.guard_line_variant_matches_listing();

-- ---------------------------------------------------------------------------
-- 4. RLS: variant axes are public for released active listings of any class;
--    owners read their own rows (archived included). Writes stay service-role
--    mediated through public.vendor_replace_listing_variants().
-- ---------------------------------------------------------------------------

drop policy if exists listing_option_groups_public_variant_select on public.listing_option_groups;
create policy listing_option_groups_public_variant_select on public.listing_option_groups
  for select using (
    kind = 'variant'
    and exists (
      select 1 from public.vendor_listings l
      where l.id = listing_option_groups.listing_id
        and l.status = 'active'
        and public.product_class_customer_released(l.product_class)
    )
  );

drop policy if exists listing_option_values_public_variant_select on public.listing_option_values;
create policy listing_option_values_public_variant_select on public.listing_option_values
  for select using (
    exists (
      select 1 from public.listing_option_groups g
      join public.vendor_listings l on l.id = g.listing_id
      where g.id = listing_option_values.group_id
        and g.kind = 'variant'
        and l.status = 'active'
        and public.product_class_customer_released(l.product_class)
    )
  );

drop policy if exists listing_option_groups_owner_select on public.listing_option_groups;
create policy listing_option_groups_owner_select on public.listing_option_groups
  for select to authenticated using (
    exists (
      select 1 from public.vendor_listings l
      join public.vendors v on v.id = l.vendor_id
      where l.id = listing_option_groups.listing_id and v.owner_user_id = (select auth.uid())
    )
  );

drop policy if exists listing_option_values_owner_select on public.listing_option_values;
create policy listing_option_values_owner_select on public.listing_option_values
  for select to authenticated using (
    exists (
      select 1 from public.listing_option_groups g
      join public.vendor_listings l on l.id = g.listing_id
      join public.vendors v on v.id = l.vendor_id
      where g.id = listing_option_values.group_id and v.owner_user_id = (select auth.uid())
    )
  );

drop policy if exists vendor_listing_variants_owner_select on public.vendor_listing_variants;
create policy vendor_listing_variants_owner_select on public.vendor_listing_variants
  for select to authenticated using (
    exists (
      select 1 from public.vendor_listings l
      join public.vendors v on v.id = l.vendor_id
      where l.id = vendor_listing_variants.listing_id and v.owner_user_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- 5. Atomic vendor write path
-- ---------------------------------------------------------------------------
--
-- p_groups:   [{"name": "Colour", "display": "swatch",
--               "values": [{"label": "Red", "swatch_hex": "#C0392B"}, ...]}, ...]
-- p_variants: [{"options": ["Red", "M"], "sku": "DRS-RED-M", "stock_qty": 4,
--               "price_ngwee": 25000 | null, "compare_at_ngwee": null,
--               "image_public_id": "..." | null, "status": "active"}, ...]
--   `options` lists one value label per group, in group order.
--
-- Group/value ids are preserved when names/labels are unchanged so existing
-- variants, carts and orders keep pointing at the same rows. Variants missing
-- from the payload are archived when an order references them, else deleted
-- (their cart lines cascade). Tracked listings get stock_qty = sum of active
-- variant stock so the existing listing-level reservation pool stays coherent.

create or replace function public.vendor_replace_listing_variants(
  p_listing_id uuid,
  p_groups jsonb,
  p_variants jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_listing public.vendor_listings%rowtype;
  v_group jsonb;
  v_value jsonb;
  v_variant jsonb;
  v_group_pos integer := 0;
  v_value_pos integer;
  v_offset integer;
  v_group_id uuid;
  v_value_id uuid;
  v_group_ids uuid[] := '{}'::uuid[];
  v_option_ids uuid[];
  v_label text;
  v_existing_id uuid;
  v_kept_ids uuid[] := '{}'::uuid[];
  v_variant_pos integer := 0;
  v_group_count integer;
  v_archived integer := 0;
  v_deleted integer := 0;
  v_stock_sum bigint;
  v_untracked integer;
begin
  if jsonb_typeof(p_groups) <> 'array' or jsonb_typeof(p_variants) <> 'array' then
    raise exception 'variant payload must be arrays' using errcode = 'check_violation';
  end if;

  select * into v_listing from public.vendor_listings where id = p_listing_id for update;
  if not found then
    raise exception 'listing % not found', p_listing_id using errcode = 'no_data_found';
  end if;

  -- Remember the old ids by name/label before the variant groups are rebuilt.
  create temporary table if not exists pg_temp.vrv_old_values (
    group_name text, value_label text, group_id uuid, value_id uuid
  ) on commit drop;
  delete from pg_temp.vrv_old_values;
  insert into pg_temp.vrv_old_values
  select lower(g.name), lower(v.label), g.id, v.id
  from public.listing_option_groups g
  left join public.listing_option_values v on v.group_id = g.id
  where g.listing_id = p_listing_id and g.kind = 'variant';

  delete from public.listing_option_groups where listing_id = p_listing_id and kind = 'variant';

  select coalesce(max(position), 0) into v_offset
  from public.listing_option_groups where listing_id = p_listing_id;

  v_group_count := jsonb_array_length(p_groups);
  for v_group in select value from jsonb_array_elements(p_groups) loop
    v_group_pos := v_group_pos + 1;
    select o.group_id into v_group_id from pg_temp.vrv_old_values o
      where o.group_name = lower(btrim(v_group->>'name')) limit 1;
    insert into public.listing_option_groups (id, listing_id, name, required, position, kind, display)
    values (
      coalesce(v_group_id, gen_random_uuid()), p_listing_id, btrim(v_group->>'name'), true,
      v_offset + v_group_pos, 'variant', coalesce(v_group->>'display', 'pill')
    )
    returning id into v_group_id;
    v_group_ids := v_group_ids || v_group_id;

    v_value_pos := 0;
    for v_value in select value from jsonb_array_elements(v_group->'values') loop
      v_value_pos := v_value_pos + 1;
      select o.value_id into v_value_id from pg_temp.vrv_old_values o
        where o.group_name = lower(btrim(v_group->>'name'))
          and o.value_label = lower(btrim(v_value->>'label'))
        limit 1;
      insert into public.listing_option_values (id, group_id, label, price_delta_ngwee, deterministic, position, swatch_hex)
      values (
        coalesce(v_value_id, gen_random_uuid()), v_group_id, btrim(v_value->>'label'), 0, true,
        v_value_pos, nullif(v_value->>'swatch_hex', '')
      );
    end loop;
  end loop;

  for v_variant in select value from jsonb_array_elements(p_variants) loop
    v_variant_pos := v_variant_pos + 1;
    if jsonb_array_length(v_variant->'options') <> v_group_count then
      raise exception 'variant % must pick one value per option group', v_variant_pos
        using errcode = 'check_violation';
    end if;
    v_option_ids := '{}'::uuid[];
    for i in 1 .. v_group_count loop
      v_label := btrim(v_variant->'options'->>(i - 1));
      select v.id into v_value_id from public.listing_option_values v
        where v.group_id = v_group_ids[i] and lower(v.label) = lower(v_label);
      if v_value_id is null then
        raise exception 'variant % references unknown value %', v_variant_pos, v_label
          using errcode = 'check_violation';
      end if;
      v_option_ids := v_option_ids || v_value_id;
    end loop;
    select array_agg(x order by x) into v_option_ids from unnest(v_option_ids) as x;

    select lv.id into v_existing_id from public.vendor_listing_variants lv
      where lv.listing_id = p_listing_id and lv.product_variant_id is null
        and lv.option_value_ids = v_option_ids;

    if v_existing_id is null then
      insert into public.vendor_listing_variants (
        listing_id, option_value_ids, sku_override, price_ngwee, compare_at_ngwee,
        stock_qty, image_public_id, status, position
      ) values (
        p_listing_id, v_option_ids, nullif(btrim(v_variant->>'sku'), ''),
        (v_variant->>'price_ngwee')::bigint, (v_variant->>'compare_at_ngwee')::bigint,
        (v_variant->>'stock_qty')::integer, nullif(v_variant->>'image_public_id', ''),
        coalesce(v_variant->>'status', 'active'), v_variant_pos
      ) returning id into v_existing_id;
    else
      update public.vendor_listing_variants set
        sku_override = nullif(btrim(v_variant->>'sku'), ''),
        price_ngwee = (v_variant->>'price_ngwee')::bigint,
        compare_at_ngwee = (v_variant->>'compare_at_ngwee')::bigint,
        stock_qty = (v_variant->>'stock_qty')::integer,
        image_public_id = nullif(v_variant->>'image_public_id', ''),
        status = coalesce(v_variant->>'status', 'active'),
        position = v_variant_pos,
        updated_at = timezone('utc', now())
      where id = v_existing_id;
    end if;
    v_kept_ids := v_kept_ids || v_existing_id;
  end loop;

  -- Variants no longer offered: archive when ordered, otherwise delete.
  with stale as (
    select lv.id from public.vendor_listing_variants lv
    where lv.listing_id = p_listing_id and lv.product_variant_id is null
      and not (lv.id = any(v_kept_ids))
  ), ordered as (
    update public.vendor_listing_variants lv set status = 'archived', updated_at = timezone('utc', now())
    from stale
    where lv.id = stale.id
      and exists (select 1 from public.order_item_products oip where oip.listing_variant_id = lv.id)
    returning lv.id
  )
  select count(*) into v_archived from ordered;

  -- An archived row may keep option ids of values that were since removed; the
  -- order snapshot holds the label, and only status is ever updated on it.
  delete from public.vendor_listing_variants lv
  where lv.listing_id = p_listing_id and lv.product_variant_id is null
    and not (lv.id = any(v_kept_ids))
    and not exists (select 1 from public.order_item_products oip where oip.listing_variant_id = lv.id);
  get diagnostics v_deleted = row_count;

  if v_listing.stock_mode = 'tracked' then
    select coalesce(sum(stock_qty), 0), count(*) filter (where stock_qty is null)
      into v_stock_sum, v_untracked
    from public.vendor_listing_variants
    where listing_id = p_listing_id and status = 'active' and product_variant_id is null;
    if v_untracked = 0 and v_variant_pos > 0 then
      update public.vendor_listings set stock_qty = v_stock_sum::integer where id = p_listing_id;
    end if;
  end if;

  return jsonb_build_object(
    'groups', v_group_count,
    'variants', cardinality(v_kept_ids),
    'archived', v_archived,
    'deleted', v_deleted
  );
end;
$$;

revoke execute on function public.vendor_replace_listing_variants(uuid, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.vendor_replace_listing_variants(uuid, jsonb, jsonb) to service_role;

comment on function public.vendor_replace_listing_variants(uuid, jsonb, jsonb) is
  'Service-role only. Atomically replaces a listing''s variant axes and purchasable variants; the API validates ownership and payload shape first.';

-- ---------------------------------------------------------------------------
-- 6. Per-variant stock commit at order placement
-- ---------------------------------------------------------------------------
--
-- Listing-level stock is still reserved at checkout (stock_reservations is keyed
-- per listing). The variant row is the finer-grained authority: the order
-- transaction calls this to lock and decrement it, and the whole order rolls
-- back if a variant sold out in the meantime.

create or replace function public.consume_listing_variant_stock(p_variant_id uuid, p_qty integer)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_row public.vendor_listing_variants%rowtype;
begin
  select * into v_row from public.vendor_listing_variants where id = p_variant_id for update;
  if not found or v_row.status <> 'active' then
    raise exception 'VARIANT_UNAVAILABLE:%', p_variant_id using errcode = 'check_violation';
  end if;
  if v_row.stock_qty is null then
    return;
  end if;
  if v_row.stock_qty < p_qty then
    raise exception 'VARIANT_OUT_OF_STOCK:%:%', p_variant_id, v_row.stock_qty using errcode = 'check_violation';
  end if;
  update public.vendor_listing_variants
    set stock_qty = stock_qty - p_qty, updated_at = timezone('utc', now())
    where id = p_variant_id;
end;
$$;

revoke execute on function public.consume_listing_variant_stock(uuid, integer) from public, anon, authenticated;
grant execute on function public.consume_listing_variant_stock(uuid, integer) to service_role;

-- ---------------------------------------------------------------------------
-- 6. service_role table grants. The API reads variant axes/variants through
--    PostgREST with the service-role key (PDP, cart, checkout); the base
--    migration only granted SELECT to anon/authenticated, so those reads 403'd
--    ("Start API" fixture probe on /products/{slug}). Writes still go through
--    vendor_replace_listing_variants(); RLS stays enforced for client roles.
-- ---------------------------------------------------------------------------

grant select, insert, update, delete on table
  public.listing_option_groups,
  public.listing_option_values,
  public.vendor_listing_variants
to service_role;
