-- 0053: translation_overrides — admin-editable localization overrides.
--
-- Backs the admin translator's inline editing. An override sets a locale's value
-- for a namespaced message key, layered over the committed message files (which
-- stay the source of truth the apps bundle). Admins edit here, then export the
-- merged result back into packages/i18n/messages/<locale>/<namespace>.json.
--
-- Reversible: drop the table.

create table public.translation_overrides (
  id uuid primary key default gen_random_uuid(),
  locale text not null,
  namespace text not null,
  message_key text not null,
  value text not null,
  updated_by uuid references auth.users (id),
  updated_at timestamptz not null default now(),
  unique (locale, namespace, message_key)
);

create index translation_overrides_locale_ns_idx
  on public.translation_overrides (locale, namespace);

create trigger translation_overrides_set_updated_at
  before update on public.translation_overrides
  for each row execute function public.set_updated_at();

alter table public.translation_overrides enable row level security;

-- Admin-only. Translations are managed by admins; the API reads/writes via the
-- service role (which bypasses RLS), so these policies are defense-in-depth.
create policy translation_overrides_select_admin
  on public.translation_overrides
  for select
  to authenticated
  using (public.has_role('admin'));

create policy translation_overrides_insert_admin
  on public.translation_overrides
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy translation_overrides_update_admin
  on public.translation_overrides
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy translation_overrides_delete_admin
  on public.translation_overrides
  for delete
  to authenticated
  using (public.has_role('admin'));
