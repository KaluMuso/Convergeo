-- Shared canonical product photos + content-hash dedup (post-pilot capacity work,
-- founder-approved 2026-11-13). Additive and reversible.
--
-- * `product_images`: photos owned by the CANONICAL product. Every listing that
--   points at the product shows them, so five shops selling the same phone no
--   longer need five uploads of it. Written only by the API (admin moderation,
--   or seeded from the proposing listing when the product is approved).
-- * `listing_images.content_sha256`: sha256 of the uploaded bytes, recorded on
--   new uploads so the vendor app can skip re-uploading a photo the vendor
--   already has or that is already the product's canonical photo.
-- * The ≤8-per-listing rule is unchanged: the DB guard still caps a listing's
--   own photos at 8, and the API shows canonical photos only in the slots the
--   vendor's own photos leave free (own + canonical ≤ 8).
-- * Public images stay on Cloudinary (D26). Gated by `shared_canonical_photos`
--   (default off): with the flag off nothing reads or writes these objects.
--
-- Reversal:
--   drop table public.product_images;
--   drop function public.guard_product_image_count();
--   drop index public.listing_images_content_sha256_idx;
--   alter table public.listing_images drop column content_sha256;
--   delete from public.feature_flags where flag = 'shared_canonical_photos';
begin;

insert into public.feature_flags (flag, enabled, description) values
  ('shared_canonical_photos', false,
   'Listings reuse canonical product photos; sha256 upload dedup')
on conflict (flag) do nothing;

alter table public.listing_images
  add column content_sha256 text
    check (content_sha256 is null or content_sha256 ~ '^[0-9a-f]{64}$');

create index listing_images_content_sha256_idx
  on public.listing_images (content_sha256)
  where content_sha256 is not null;

create table public.product_images (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products (id) on delete cascade,
  cloudinary_public_id text not null
    check (char_length(cloudinary_public_id) between 1 and 500),
  position integer not null check (position between 1 and 8),
  content_sha256 text check (content_sha256 is null or content_sha256 ~ '^[0-9a-f]{64}$'),
  source_listing_image_id uuid references public.listing_images (id) on delete set null,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint product_images_product_position_key unique (product_id, position),
  constraint product_images_product_public_id_key unique (product_id, cloudinary_public_id)
);

create index product_images_content_sha256_idx
  on public.product_images (content_sha256)
  where content_sha256 is not null;

create trigger product_images_set_updated_at
  before update on public.product_images
  for each row execute function public.set_updated_at();

create function public.guard_product_image_count() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_count integer;
begin
  perform pg_advisory_xact_lock(hashtextextended('product-images:' || new.product_id::text, 0));
  select count(*)::integer into v_count from public.product_images
    where product_id = new.product_id;
  if v_count >= 8 then
    raise exception 'product cannot have more than 8 images';
  end if;
  return new;
end;
$$;

revoke all on function public.guard_product_image_count() from public, anon, authenticated;

create trigger product_images_guard_count
  before insert on public.product_images
  for each row execute function public.guard_product_image_count();

-- RLS: public read for ACTIVE products only (same visibility as the product);
-- admins see all. No client writes — the API writes with the service role and
-- records an admin audit_log row.
alter table public.product_images enable row level security;

revoke all on public.product_images from public, anon, authenticated;
grant select on public.product_images to anon, authenticated;
grant all on public.product_images to service_role;

create policy product_images_public_active_select
  on public.product_images
  for select
  using (
    public.has_role('admin')
    or exists (
      select 1 from public.products p
      where p.id = product_images.product_id
        and p.status = 'active'
    )
  );

commit;
