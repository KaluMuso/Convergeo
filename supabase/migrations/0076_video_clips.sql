-- M17-P01 — Vergeo Clips: durable clip lifecycle, ownership constraints & RLS.
--
-- Binding spec: docs/plan/m17-video-feed.md (§2 D-V1–D-V9, §4 data model).
--
-- Six additive tables, FORCE RLS on every one. The design principle throughout:
-- **put the invariant in the database, not in the application.** Three things in
-- particular are enforced here rather than in a router, because a router can be
-- bypassed by a future endpoint and a constraint cannot:
--
--   1. A clip may link at most 3 listings, and every linked listing must belong
--      to the clip's own vendor. A vendor advertising a rival's listing on their
--      clip is impossible at the DB layer, not merely unimplemented.
--   2. Likes / reports / views are idempotent **by constraint** (unique keys),
--      not by an application read-then-write that races.
--   3. Denormalised counters have no client UPDATE grant at all. They move only
--      through SECURITY DEFINER functions, so a compromised client token cannot
--      inflate a vendor's like count.
--
-- Public visibility is `status = 'published'` and nothing else. The moment a clip
-- leaves that status — takedown, or a vendor suspension cascade — it stops being
-- publicly selectable in the same statement. That is what makes takedown
-- "instant-hide" rather than "hidden once some cache expires".
--
-- Reversible: drop the tables in reverse dependency order, then the functions.

-- ---------------------------------------------------------------------------
-- Clips
-- ---------------------------------------------------------------------------
create table public.video_clips (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  status text not null default 'draft' check (
    status in ('draft', 'screening', 'pending_review', 'published', 'rejected', 'taken_down')
  ),
  -- Cloudinary is the only place video bytes live; we keep references, never blobs.
  cloudinary_public_id text,
  poster_url text,
  -- {"480p": {...}, "720p": {...}} — populated by the M17-P02 transcode webhook.
  renditions jsonb not null default '{}'::jsonb,
  -- D-V3: <=60s recorded. The cap is a CHECK so a mis-set preset cannot smuggle
  -- a 10-minute video into the feed and blow the delivery budget.
  duration_s integer check (duration_s is null or (duration_s > 0 and duration_s <= 60)),
  caption text,
  category_id uuid references public.categories (id) on delete set null,
  -- Denormalised counters. NO client UPDATE grant — see the grants block.
  like_count integer not null default 0 check (like_count >= 0),
  comment_count integer not null default 0 check (comment_count >= 0),
  view_count integer not null default 0 check (view_count >= 0),
  published_at timestamptz,
  rejection_reason text,
  taken_down_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- The feed's hot path: published clips newest-first. Partial, because nothing
-- else is ever ranked.
create index video_clips_published_idx
  on public.video_clips (published_at desc)
  where status = 'published';

create index video_clips_vendor_status_idx
  on public.video_clips (vendor_id, status, created_at desc);

create index video_clips_category_idx
  on public.video_clips (category_id)
  where status = 'published';

create trigger video_clips_set_updated_at
  before update on public.video_clips
  for each row execute function public.set_updated_at();

comment on table public.video_clips is
  'M17 Vergeo Clips. Public visibility is status=published only; counters are server-managed.';
comment on column public.video_clips.duration_s is
  'D-V3 cap: clips are <=60s. Enforced by CHECK so a bad preset cannot inflate delivery cost.';

-- ---------------------------------------------------------------------------
-- Clip -> listing links (shoppability)
-- ---------------------------------------------------------------------------
create table public.clip_products (
  id uuid primary key default gen_random_uuid(),
  clip_id uuid not null references public.video_clips (id) on delete cascade,
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  sort_order integer not null default 0 check (sort_order >= 0 and sort_order < 3),
  created_at timestamptz not null default now(),
  unique (clip_id, listing_id)
);

create index clip_products_clip_idx on public.clip_products (clip_id, sort_order);
create index clip_products_listing_idx on public.clip_products (listing_id);

-- The two invariants that must hold even if every router is wrong.
--
-- Cross-vendor linking is the one with teeth: without it a vendor could attach a
-- competitor's listing to their own clip and harvest the add-to-cart traffic.
-- Checking it only in the API would leave that open to the next endpoint someone
-- writes.
create or replace function public.clip_products_guard()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  clip_vendor uuid;
  listing_vendor uuid;
  link_count integer;
begin
  select vendor_id into clip_vendor from public.video_clips where id = new.clip_id;
  if clip_vendor is null then
    raise exception 'clip % does not exist', new.clip_id
      using errcode = 'foreign_key_violation';
  end if;

  select vendor_id into listing_vendor
  from public.vendor_listings
  where id = new.listing_id;
  if listing_vendor is null then
    raise exception 'listing % does not exist', new.listing_id
      using errcode = 'foreign_key_violation';
  end if;

  if listing_vendor <> clip_vendor then
    raise exception 'clip_products: listing % does not belong to the clip''s vendor', new.listing_id
      using errcode = 'check_violation';
  end if;

  -- <=3 links per clip (spec §4). Counted inside the trigger so concurrent
  -- inserts cannot both see 2 and both succeed: the row lock taken by the
  -- SELECT ... FOR UPDATE on the parent clip serialises them.
  perform 1 from public.video_clips where id = new.clip_id for update;

  select count(*) into link_count
  from public.clip_products
  where clip_id = new.clip_id
    and (tg_op = 'INSERT' or id <> new.id);

  if link_count >= 3 then
    raise exception 'clip_products: a clip may link at most 3 listings'
      using errcode = 'check_violation';
  end if;

  return new;
end;
$$;

create trigger clip_products_guard_trg
  before insert or update on public.clip_products
  for each row execute function public.clip_products_guard();

comment on function public.clip_products_guard() is
  'DB-layer enforcement of the two clip-link invariants: <=3 per clip, and the listing '
  'must belong to the clip''s own vendor. Deliberately not application-only.';

-- ---------------------------------------------------------------------------
-- Likes — race-safety IS the primary key
-- ---------------------------------------------------------------------------
create table public.clip_likes (
  clip_id uuid not null references public.video_clips (id) on delete cascade,
  user_id uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (clip_id, user_id)
);

create index clip_likes_user_idx on public.clip_likes (user_id, created_at desc);

comment on table public.clip_likes is
  'S5 race-safety: double-like is impossible by primary key. No application-level dedupe.';

-- ---------------------------------------------------------------------------
-- Comments
-- ---------------------------------------------------------------------------
create table public.clip_comments (
  id uuid primary key default gen_random_uuid(),
  clip_id uuid not null references public.video_clips (id) on delete cascade,
  author_id uuid not null references public.profiles (id) on delete cascade,
  body text not null check (length(btrim(body)) between 1 and 500),
  status text not null default 'visible' check (status in ('visible', 'hidden')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index clip_comments_clip_idx
  on public.clip_comments (clip_id, created_at desc)
  where status = 'visible';

create trigger clip_comments_set_updated_at
  before update on public.clip_comments
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Reports — one per (clip, reporter), feeds the P07 admin queue
-- ---------------------------------------------------------------------------
create table public.clip_reports (
  id uuid primary key default gen_random_uuid(),
  clip_id uuid not null references public.video_clips (id) on delete cascade,
  reporter_id uuid not null references public.profiles (id) on delete cascade,
  reason text not null check (length(btrim(reason)) between 1 and 500),
  created_at timestamptz not null default now(),
  unique (clip_id, reporter_id)
);

create index clip_reports_clip_idx on public.clip_reports (clip_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Views — deduped per user per day (M17-P03's ">=3s watched" rule)
-- ---------------------------------------------------------------------------
-- Not in the spec's §4 table list, but its "view counted at >=3s watched, deduped
-- per user/day" rule needs somewhere to record the dedupe key. Storing the date
-- (not the timestamp) is what makes the unique constraint express "once a day".
create table public.clip_views (
  id uuid primary key default gen_random_uuid(),
  clip_id uuid not null references public.video_clips (id) on delete cascade,
  -- NOT NULL on purpose: the unique key below IS the dedupe, and in Postgres
  -- NULL <> NULL, so a nullable user_id would let every anonymous view insert a
  -- fresh row and quietly break the "once per user per day" promise. Anonymous
  -- plays are analytics-only (analytics_events), never counted here.
  user_id uuid not null references public.profiles (id) on delete cascade,
  viewed_on date not null default (now() at time zone 'utc')::date,
  created_at timestamptz not null default now(),
  unique (clip_id, user_id, viewed_on)
);

create index clip_views_clip_idx on public.clip_views (clip_id, viewed_on desc);

comment on table public.clip_views is
  'Dedupe ledger for the >=3s view rule. UNIQUE (clip, user, day) is the dedupe.';

-- ---------------------------------------------------------------------------
-- Server-managed counters — SECURITY DEFINER only
-- ---------------------------------------------------------------------------
-- Counters are derived facts. Letting a client write them would let a vendor
-- inflate their own engagement, so no client role gets UPDATE on the columns and
-- these functions are the only movement path.
create or replace function public.clip_bump_counter(
  p_clip_id uuid,
  p_column text,
  p_delta integer
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  new_value integer;
begin
  if p_column not in ('like_count', 'comment_count', 'view_count') then
    raise exception 'clip_bump_counter: unknown counter %', p_column
      using errcode = 'check_violation';
  end if;

  -- Relative update (not read-then-write) so concurrent bumps cannot lose one.
  execute format(
    'update public.video_clips set %I = greatest(0, %I + $1) where id = $2 returning %I',
    p_column, p_column, p_column
  )
  into new_value
  using p_delta, p_clip_id;

  if new_value is null then
    raise exception 'clip_bump_counter: clip % not found', p_clip_id
      using errcode = 'no_data_found';
  end if;

  return new_value;
end;
$$;

comment on function public.clip_bump_counter(uuid, text, integer) is
  'The ONLY path that moves a clip counter. Relative update, so concurrent bumps do not '
  'lose an increment. No client role holds UPDATE on the counter columns.';

-- ---------------------------------------------------------------------------
-- RLS — ENABLE + FORCE on every table
-- ---------------------------------------------------------------------------
alter table public.video_clips enable row level security;
alter table public.video_clips force row level security;
alter table public.clip_products enable row level security;
alter table public.clip_products force row level security;
alter table public.clip_likes enable row level security;
alter table public.clip_likes force row level security;
alter table public.clip_comments enable row level security;
alter table public.clip_comments force row level security;
alter table public.clip_reports enable row level security;
alter table public.clip_reports force row level security;
alter table public.clip_views enable row level security;
alter table public.clip_views force row level security;

-- Clips: public sees PUBLISHED ONLY, and only from an active vendor (mirrors the
-- vendor_listings rule — a suspended vendor's clips vanish with the storefront).
create policy video_clips_public_published_select
  on public.video_clips
  for select
  using (
    status = 'published'
    and exists (
      select 1 from public.vendors v
      where v.id = video_clips.vendor_id
        and v.status = 'active'
    )
  );

comment on policy video_clips_public_published_select on public.video_clips is
  'Published clips from active vendors only. Takedown is instant-hide: the moment status '
  'leaves published this policy stops matching.';

create policy video_clips_owner_select
  on public.video_clips
  for select
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = video_clips.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy video_clips_owner_insert
  on public.video_clips
  for insert
  to authenticated
  with check (
    exists (
      select 1 from public.vendors v
      where v.id = video_clips.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

-- Owners may edit their own clip metadata. Status changes still go through the
-- guarded transition functions (convention #4) — this policy is what stops a
-- vendor editing *someone else's* clip, not what governs the lifecycle.
create policy video_clips_owner_update
  on public.video_clips
  for update
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = video_clips.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.vendors v
      where v.id = video_clips.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy video_clips_owner_delete
  on public.video_clips
  for delete
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = video_clips.vendor_id
        and v.owner_user_id = (select auth.uid())
        and video_clips.status = 'draft'
    )
  );

create policy video_clips_admin_all
  on public.video_clips
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- Links: visible with the clip; writable by the owning vendor only.
create policy clip_products_public_select
  on public.clip_products
  for select
  using (
    exists (
      select 1 from public.video_clips c
      join public.vendors v on v.id = c.vendor_id
      where c.id = clip_products.clip_id
        and c.status = 'published'
        and v.status = 'active'
    )
  );

create policy clip_products_owner_all
  on public.clip_products
  for all
  to authenticated
  using (
    exists (
      select 1
      from public.video_clips c
      join public.vendors v on v.id = c.vendor_id
      where c.id = clip_products.clip_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.video_clips c
      join public.vendors v on v.id = c.vendor_id
      where c.id = clip_products.clip_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy clip_products_admin_all
  on public.clip_products
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- Likes: anyone may read the like set of a published clip; a user writes only
-- their own like row.
create policy clip_likes_public_select
  on public.clip_likes
  for select
  using (
    exists (
      select 1 from public.video_clips c
      where c.id = clip_likes.clip_id
        and c.status = 'published'
    )
  );

create policy clip_likes_self_insert
  on public.clip_likes
  for insert
  to authenticated
  with check (
    user_id = (select auth.uid())
    and exists (
      select 1 from public.video_clips c
      where c.id = clip_likes.clip_id
        and c.status = 'published'
    )
  );

create policy clip_likes_self_delete
  on public.clip_likes
  for delete
  to authenticated
  using (user_id = (select auth.uid()));

create policy clip_likes_admin_all
  on public.clip_likes
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- Comments: visible ones on published clips are public; authors write their own.
create policy clip_comments_public_select
  on public.clip_comments
  for select
  using (
    status = 'visible'
    and exists (
      select 1 from public.video_clips c
      where c.id = clip_comments.clip_id
        and c.status = 'published'
    )
  );

create policy clip_comments_author_select
  on public.clip_comments
  for select
  to authenticated
  using (author_id = (select auth.uid()));

create policy clip_comments_author_insert
  on public.clip_comments
  for insert
  to authenticated
  with check (
    author_id = (select auth.uid())
    and exists (
      select 1 from public.video_clips c
      where c.id = clip_comments.clip_id
        and c.status = 'published'
    )
  );

create policy clip_comments_author_delete
  on public.clip_comments
  for delete
  to authenticated
  using (author_id = (select auth.uid()));

create policy clip_comments_admin_all
  on public.clip_comments
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- Reports: a reporter may file and read their own; only admin sees the queue.
-- Deliberately NO vendor read policy — letting a vendor see who reported them
-- invites retaliation.
create policy clip_reports_self_select
  on public.clip_reports
  for select
  to authenticated
  using (reporter_id = (select auth.uid()));

create policy clip_reports_self_insert
  on public.clip_reports
  for insert
  to authenticated
  with check (reporter_id = (select auth.uid()));

create policy clip_reports_admin_all
  on public.clip_reports
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- Views: a dedupe ledger, not a public read surface. Admin only; the service role
-- writes it. Exposing per-user view rows publicly would be a privacy leak.
create policy clip_views_admin_select
  on public.clip_views
  for select
  to authenticated
  using (public.has_role('admin'));

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------
-- Read surfaces the feed needs, plus the narrow client writes (like / comment /
-- report). NOTE what is deliberately absent: no UPDATE on video_clips for anon or
-- authenticated, so the counter columns are unreachable from a client token even
-- though the row itself is selectable.
grant select on table public.video_clips to anon, authenticated;
grant insert, delete on table public.video_clips to authenticated;
-- Column-level UPDATE: editable metadata only. like_count / comment_count /
-- view_count are absent from this list, so a client token cannot move them even
-- with a matching RLS policy. `status` is absent too — the lifecycle belongs to
-- the guarded transition functions (convention #4), not to a client UPDATE.
grant update (caption, category_id, cloudinary_public_id, poster_url, renditions, duration_s)
  on table public.video_clips to authenticated;
grant select on table public.clip_products to anon, authenticated;
grant insert, update, delete on table public.clip_products to authenticated;
grant select on table public.clip_likes to anon, authenticated;
grant insert, delete on table public.clip_likes to authenticated;
grant select on table public.clip_comments to anon, authenticated;
grant insert, delete on table public.clip_comments to authenticated;
grant insert on table public.clip_reports to authenticated;
grant select on table public.clip_reports to authenticated;

grant select, insert, update, delete on table public.video_clips to service_role;
grant select, insert, update, delete on table public.clip_products to service_role;
grant select, insert, update, delete on table public.clip_likes to service_role;
grant select, insert, update, delete on table public.clip_comments to service_role;
grant select, insert, update, delete on table public.clip_reports to service_role;
grant select, insert, update, delete on table public.clip_views to service_role;

-- The counter function is service-role only: the API decides when a like or view
-- is legitimate, then asks the database to move the number.
revoke all on function public.clip_bump_counter(uuid, text, integer) from public;
grant execute on function public.clip_bump_counter(uuid, text, integer) to service_role;
