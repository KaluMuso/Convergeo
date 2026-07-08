-- M04-P01: Bootstrap profiles + default customer role on auth.users signup.

-- SECURITY DEFINER + pinned search_path: the trigger runs on auth.users insert (no JWT).
-- It must insert into RLS-protected public tables without exposing a client-callable bypass.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id)
  values (new.id)
  on conflict (id) do nothing;

  insert into public.user_roles (user_id, role)
  values (new.id, 'customer')
  on conflict (user_id, role) do nothing;

  return new;
end;
$$;

comment on function public.handle_new_user() is
  'After-insert on auth.users: idempotent profiles row + default customer role.';

create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();
