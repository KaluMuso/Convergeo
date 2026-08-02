-- R02-P14 — following a vendor (D37).
--
-- Saves already exist (`user_wishlist`, `user_recently_viewed`, 0066) and clip
-- share pages already exist (M17-P08). Follows do not. This adds only the
-- missing piece.
--
-- D37 keeps this deliberately one-directional: following a vendor is a COMMERCE
-- SUBSCRIPTION, not a social graph. There is no follower list, no "people you
-- may know", no public profile to follow a person to. The line that enforces it
-- is below in the policies: a vendor may count their followers but may never
-- read who they are.
--
-- That is not only D37 tidiness — under the Zambia DPA, "this shop knows you
-- follow it" is a disclosure nobody consented to, and an aggregate is the
-- safe default.

create table if not exists public.vendor_follows (
  user_id uuid not null references auth.users (id) on delete cascade,
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (user_id, vendor_id)
);

comment on table public.vendor_follows is
  'Customer follows a vendor: a commerce subscription (new-listing notifications), never a social graph. Vendors see counts, never identities (D37).';

create index if not exists vendor_follows_vendor_idx
  on public.vendor_follows (vendor_id);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.vendor_follows enable row level security;
alter table public.vendor_follows force row level security;

-- A user reads and writes only their own follow rows. Idempotency comes from
-- the primary key, not from application logic: the insert is attempted
-- unconditionally and the constraint absorbs a double-tap, exactly as M17 did
-- for clip likes. A read-then-write would race on exactly the double-tap it is
-- meant to handle.
drop policy if exists vendor_follows_owner_select on public.vendor_follows;
create policy vendor_follows_owner_select
  on public.vendor_follows
  for select
  to authenticated
  using (user_id = (select auth.uid()));

drop policy if exists vendor_follows_owner_insert on public.vendor_follows;
create policy vendor_follows_owner_insert
  on public.vendor_follows
  for insert
  to authenticated
  with check (
    user_id = (select auth.uid())
    and exists (
      select 1 from public.vendors v
      where v.id = vendor_follows.vendor_id
        and v.status = 'active'
    )
  );

drop policy if exists vendor_follows_owner_delete on public.vendor_follows;
create policy vendor_follows_owner_delete
  on public.vendor_follows
  for delete
  to authenticated
  using (user_id = (select auth.uid()));

comment on policy vendor_follows_owner_select on public.vendor_follows is
  'A user sees only their own follows. There is deliberately no vendor-side SELECT policy: a vendor must not learn who follows them.';

-- No UPDATE policy: a follow has nothing to amend. Unfollowing is a DELETE,
-- and re-following re-inserts. Leaving UPDATE unreachable keeps `created_at`
-- honest as the moment consent was given.
revoke all on public.vendor_follows from anon, authenticated;
grant select, insert, delete on public.vendor_follows to authenticated;

-- ---------------------------------------------------------------------------
-- Aggregate-only follower count for vendors.
-- ---------------------------------------------------------------------------
-- SECURITY DEFINER so it can count rows the caller cannot read, and restricted
-- to the vendor's own owner. This is the ONLY way a vendor learns anything
-- about their followers, and it returns a number and nothing else.
create or replace function public.vendor_follower_count(p_vendor_id uuid)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  total integer;
begin
  if not exists (
    select 1 from public.vendors v
    where v.id = p_vendor_id
      and (v.owner_user_id = (select auth.uid()) or public.has_role('admin'))
  ) then
    raise exception 'not authorised to read follower counts for vendor %', p_vendor_id;
  end if;

  select count(*) into total
  from public.vendor_follows f
  where f.vendor_id = p_vendor_id;

  return total;
end;
$$;

comment on function public.vendor_follower_count(uuid) is
  'Aggregate follower count for a vendor the caller owns (or admin). Deliberately returns a count only — never follower identities (D37).';

revoke all on function public.vendor_follower_count(uuid) from public, anon;
grant execute on function public.vendor_follower_count(uuid) to authenticated;
