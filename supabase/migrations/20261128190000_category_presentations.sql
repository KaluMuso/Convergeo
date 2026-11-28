-- Admin-controlled category presentation: icon, banner image, banner title and
-- banner description per category, edited in the admin app.
--
-- Additive only: one new table, one validation function and one trigger. No
-- existing object is altered (public.categories is untouched, so the customer
-- category queries keep working before and after this migration is applied).
--
-- Media lives on Cloudinary (public delivery, f_auto/q_auto); only the public
-- ids are stored here. Copy is per-locale jsonb ({"en": "...", "bem": "..."});
-- the API falls back to "en" when a locale has no text of its own.
--
-- Access model: service-role only (RLS enabled + forced, client grants
-- revoked). The public read (`GET /categories/presentation`, cached) and the
-- admin writes (`PUT/DELETE /admin/config/categories/{id}/presentation`,
-- audited) both run in the API after the API's own authz checks.
--
-- Down (manual, reversible — no existing data is touched):
--   drop table if exists public.category_presentations;
--   drop function if exists public.is_valid_category_copy(jsonb, integer);

create function public.is_valid_category_copy(copy jsonb, max_len integer)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select jsonb_typeof(copy) = 'object'
    and not exists (
      select 1
      from jsonb_each(copy) as entry(locale, body)
      where entry.locale not in ('en', 'bem', 'nya', 'fr', 'zh')
         or jsonb_typeof(entry.body) <> 'string'
         or char_length(btrim(entry.body #>> '{}')) not between 1 and max_len
    );
$$;

comment on function public.is_valid_category_copy(jsonb, integer) is
  'True when copy is a {locale: text} object over supported locales with 1..max_len chars each.';

revoke all on function public.is_valid_category_copy(jsonb, integer) from public, anon, authenticated;
grant execute on function public.is_valid_category_copy(jsonb, integer) to service_role;

create table public.category_presentations (
  category_id uuid primary key references public.categories (id) on delete cascade,
  icon_public_id text check (
    icon_public_id is null
    or (icon_public_id ~ '^[A-Za-z0-9_./-]{1,255}$' and icon_public_id !~ '\.\.')
  ),
  banner_public_id text check (
    banner_public_id is null
    or (banner_public_id ~ '^[A-Za-z0-9_./-]{1,255}$' and banner_public_id !~ '\.\.')
  ),
  -- Banner title: max 60 characters per locale.
  banner_title_i18n jsonb not null default '{}'::jsonb
    check (public.is_valid_category_copy(banner_title_i18n, 60)),
  -- Banner description: max 160 characters per locale.
  banner_description_i18n jsonb not null default '{}'::jsonb
    check (public.is_valid_category_copy(banner_description_i18n, 160)),
  updated_by uuid,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create trigger category_presentations_set_updated_at
  before update on public.category_presentations
  for each row execute function public.set_updated_at();

alter table public.category_presentations enable row level security;
alter table public.category_presentations force row level security;
revoke all on public.category_presentations from public, anon, authenticated;
grant select, insert, update, delete on public.category_presentations to service_role;

comment on table public.category_presentations is
  'Admin-edited category icon/banner (Cloudinary public ids) and per-locale banner copy. Service role only; read via GET /categories/presentation.';
